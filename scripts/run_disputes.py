"""Interactive validation/triage graph against the real MCP server and LLM.

Reads the repository .env (SCENARIO_NOW, DEV_SESSIONS, MCP_SERVER_*, LLM_MODEL,
GROQ_API_KEY). Default flow verifies identity through MCP then classifies the
request. Downstream actions are pending. --flow legacy selects the older graph.

Use (from the repository root, in the agent's uv env):
  uv run --project apps/agent scripts/run_disputes.py --session dev
  uv run --project apps/agent scripts/run_disputes.py --session dev --debug

JSON events (steps, LLM calls, MCP calls) go to logs/agent.jsonl, or LOG_FILE.
--debug also logs LLM prompts and outputs (LOG_LLM_CONTENT=1): local use only.

Inside: answer buttons by number or value, /new restarts, /quit exits.
"""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "agent" / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from bank_agent.clients.mcp_services import McpServices  # noqa: E402
from bank_agent.graphs.disputes import build_graph  # noqa: E402
from bank_agent.graphs.state import initial_state  # noqa: E402
from bank_agent.observability import configure_logging  # noqa: E402


class Quit(Exception):
    pass


class Restart(Exception):
    pass


def read(prompt: str) -> str:
    while True:
        try:
            text = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            raise Quit from None
        if text == "/quit":
            raise Quit
        if text == "/new":
            raise Restart
        if text:
            return text


def answer(question: dict) -> Command:
    print(f"\nAgent: {question['message']}")
    for key in ("transactions", "cards", "transaction"):
        if key in question:
            print(f"  {key}: {json.dumps(question[key], ensure_ascii=False)}")
    if question["kind"] == "identity_form":   # login form: each factor in its own field, never sent to an LLM
        labels = {"document_number": "Documento", "date_of_birth": "Fecha de nacimiento (AAAA-MM-DD)",
                  "product_number": "Número de producto"}
        return Command(resume={field: read(f"  {labels.get(field, field)}: ") for field in question["fields"]})
    if question["kind"] in {"transaction_details", "validation_details", "request_details"}:
        return Command(resume={"text": read("You: ")})
    options = question["options"]
    for i, option in enumerate(options, 1):
        print(f"  [{i}] {option}")
    while True:
        choice = read("Choose: ")
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return Command(resume={"choice": options[int(choice) - 1]})
        if choice in options:
            return Command(resume={"choice": choice})
        print("  Pick one of the numbers or values above.")


def conversation(graph, session_ref: str, debug: bool) -> None:
    thread = f"cli-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread}, "recursion_limit": 100}
    state = graph.invoke(initial_state(thread, session_ref, read("You: ")), config)
    while "__interrupt__" in state:
        state = graph.invoke(answer(state["__interrupt__"][0].value), config)
    print(f"\nAgent: {state.get('response')}\n  outcome={state.get('outcome')}")
    if debug:
        keys = ("language", "authenticated", "validation_status", "customer_id", "intent", "triage_route", "slots", "reason", "queue", "priority", "case_ids", "blocked_cards", "explanation_result_id")
        print(json.dumps({k: state.get(k) for k in keys} | {"transaction": (state.get("transaction") or {}).get("id")},
                         indent=2, ensure_ascii=False))
        for step in state.get("trace", []):
            print(f"  {step['node']}:{step['phase']} -> {step['next']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default="dev", help="Session reference from DEV_SESSIONS")
    parser.add_argument("--debug", action="store_true", help="Print state and trace after each conversation")
    parser.add_argument("--flow", choices=["validation-triage", "charge-error", "fraud", "fraud-escalation",
                                           "card-emergency", "card-emergency-escalation", "legacy"],
                        default="validation-triage",
                        help="validation-triage: classify only; charge-error: explain a charge; fraud: simulate fraud actions; fraud-escalation: include verified sandbox handoff and notification; legacy: general graph.")
    args = parser.parse_args()

    # JSON events go to a file so they don't interleave with the chat; --debug adds LLM prompts/outputs.
    os.environ["LOG_FILE"] = os.environ.get("LOG_FILE") or str(ROOT / "logs" / "agent.jsonl")
    if args.debug:
        os.environ["LOG_LLM_CONTENT"] = "1"
    configure_logging()

    services = McpServices.from_env()
    if args.flow in {"validation-triage", "charge-error", "fraud", "fraud-escalation",
                     "card-emergency", "card-emergency-escalation"}:
        from bank_agent.graphs.validation_triage import build_graph as build_scoped_graph
        graph = build_scoped_graph(services, checkpointer=InMemorySaver(),
            test_charge_error=args.flow in {"charge-error", "fraud", "fraud-escalation"},
            test_fraud=args.flow in {"fraud", "fraud-escalation"},
            test_escalation=args.flow in {"fraud-escalation", "card-emergency-escalation"},
            test_card_emergency=args.flow in {"card-emergency", "card-emergency-escalation"})
    else:
        graph = build_graph(services, checkpointer=InMemorySaver())
    if args.flow in {"fraud", "fraud-escalation"}:
        escalation_note = ("; escalamiento crea y verifica handoff/notificación SIMULATED" if args.flow == "fraud-escalation"
                           else "; escalamiento termina sin crear ticket")
        print(f"Prueba de fraude: bloqueos y disputas SIMULATED en sandbox{escalation_note}.")
    print(f"Scenario date {services.now():%Y-%m-%d}. Session '{args.session}'. /new restarts, /quit exits.")
    print(f"Logs: {os.environ['LOG_FILE']}\n")
    try:
        while True:
            try:
                conversation(graph, args.session, args.debug)
            except Restart:
                pass
            print("-- new conversation --\n")
    except Quit:
        pass
    finally:
        services.close()


if __name__ == "__main__":
    main()
