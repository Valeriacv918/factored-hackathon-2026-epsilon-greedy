"""Interactive run of the disputes graph against the real MCP server and LLM.

Reads the repository .env (SCENARIO_NOW, DEV_SESSIONS, MCP_SERVER_*, LLM_MODEL,
GROQ_API_KEY). Only the read tools exist yet: block, dispute and handoff steps
fail safely and end in "service unavailable".

Use (from the repository root, with the agent venv):
  apps/agent/.venv/Scripts/python.exe scripts/run_disputes.py --session dev
  apps/agent/.venv/Scripts/python.exe scripts/run_disputes.py --session dev --debug

Inside: answer buttons by number or value, /new restarts, /quit exits.
"""
import argparse
import json
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
    if question["kind"] == "transaction_details":
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
        keys = ("language", "customer_id", "intent", "slots", "reason", "queue", "priority", "case_ids", "blocked_cards")
        print(json.dumps({k: state.get(k) for k in keys} | {"transaction": (state.get("transaction") or {}).get("id")},
                         indent=2, ensure_ascii=False))
        for step in state.get("trace", []):
            print(f"  {step['node']}:{step['phase']} -> {step['next']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default="dev", help="Session reference from DEV_SESSIONS")
    parser.add_argument("--debug", action="store_true", help="Print state and trace after each conversation")
    args = parser.parse_args()

    services = McpServices.from_env()
    graph = build_graph(services, checkpointer=InMemorySaver())
    print(f"Scenario date {services.now():%Y-%m-%d}. Session '{args.session}'. /new restarts, /quit exits.\n")
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
