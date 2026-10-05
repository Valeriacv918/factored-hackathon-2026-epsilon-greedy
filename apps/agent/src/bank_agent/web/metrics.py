"""Statistics for the side panel: live conversations and the offline triage evaluation.

Live numbers come from the conversation.summary events this process emits (observability.py),
kept in memory: they cover the conversations served since the process started, which is why
the service runs with a single instance. They hold outcomes, routing and counts, never
customer, card or ticket identifiers.

Offline numbers come from the latest triage evaluation run in evals/cases/results: a labeled,
synthetic held-out set, reported as offline and never as a production measurement.
"""
import csv
import logging
import os
import threading
from collections import Counter, deque
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]

# How a conversation ended (outcome values set by the graph nodes).
RESOLVED = {"dispute_filed", "explained", "fraud_intake_complete", "approved"}   # verified, no human
ESCALATED = {"escalated"}                                                         # verified handoff ticket
HUMAN_NO_TICKET = {"human_required", "human_requested"}
ABSTAINED = {"out_of_scope", "outside_window", "existing_case", "cancelled"}
FAILED = {"service_unavailable", "authentication_required", "transaction_unresolved", "unknown_status"}
GROUPS = (("resolved", RESOLVED), ("escalated", ESCALATED), ("human_no_ticket", HUMAN_NO_TICKET),
          ("abstained", ABSTAINED), ("failed", FAILED))


def outcome_group(outcome: str | None) -> str:
    return next((name for name, values in GROUPS if outcome in values), "other")


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile; None when there are no values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), round(p / 100 * len(ordered) + 0.5)))
    return ordered[rank - 1]


def price_per_mtok() -> tuple[float, float]:
    """USD per million input/output tokens. Defaults are an assumption for the configured model."""
    return (float(os.environ.get("LLM_PRICE_INPUT_PER_MTOK", "0.15")),
            float(os.environ.get("LLM_PRICE_OUTPUT_PER_MTOK", "0.75")))


class LiveMetrics(logging.Handler):
    """Logging handler that keeps every conversation.summary and aggregates them on demand."""

    def __init__(self, maxlen: int = 2000):
        super().__init__(level=logging.INFO)
        self._summaries: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        data = getattr(record, "event_data", None)
        if data and data.get("event") == "conversation.summary":
            with self._lock:
                self._summaries.append(dict(data))

    def snapshot(self, active: int = 0) -> dict[str, Any]:
        with self._lock:
            rows = list(self._summaries)
        price_in, price_out = price_per_mtok()
        groups = Counter(outcome_group(r.get("outcome")) for r in rows)
        total = len(rows)
        tickets = [r for r in rows if r.get("ticket_created")]
        cost = sum((r.get("input_tokens") or 0) * price_in + (r.get("output_tokens") or 0) * price_out
                   for r in rows) / 1_000_000
        system_ms = [r["step_ms"] for r in rows if r.get("step_ms") is not None]
        duration_ms = [r["duration_ms"] for r in rows if r.get("duration_ms") is not None]
        by_language = {}
        for lang in sorted({r.get("language") or "?" for r in rows}):
            subset = [r for r in rows if (r.get("language") or "?") == lang]
            by_language[lang] = {"conversations": len(subset),
                                 "resolved": sum(outcome_group(r.get("outcome")) == "resolved" for r in subset)}
        return {
            "conversations": total,
            "active": active,
            "outcomes": {name: groups.get(name, 0) for name, _ in GROUPS} | {"other": groups.get("other", 0)},
            "containment": None if not total else round(1 - (groups["escalated"] + groups["human_no_ticket"]) / total, 3),
            "tickets": {"total": len(tickets),
                        "by_queue": dict(Counter(r.get("queue") or "general" for r in tickets)),
                        "by_priority": dict(Counter(r.get("priority") or "-" for r in tickets))},
            "actions": {"cards_blocked": sum(r.get("cards_blocked") or 0 for r in rows),
                        "cases_filed": sum(r.get("cases_filed") or 0 for r in rows)},
            "intents": dict(Counter(r.get("intent") or "unclassified" for r in rows)),
            "by_language": by_language,
            "latency_ms": {"system_p50": percentile(system_ms, 50), "system_p95": percentile(system_ms, 95),
                           "attention_p50": percentile(duration_ms, 50), "attention_p95": percentile(duration_ms, 95),
                           "llm_total": round(sum(r.get("llm_ms") or 0 for r in rows), 1),
                           "mcp_total": round(sum(r.get("mcp_ms") or 0 for r in rows), 1)},
            "cost_usd": {"total": round(cost, 6),
                         "per_conversation": round(cost / total, 6) if total else None,
                         "per_resolved": round(cost / groups["resolved"], 6) if groups["resolved"] else None,
                         "price_per_mtok": {"input": price_in, "output": price_out}},
            "tool_errors": sum(r.get("errors") or 0 for r in rows),
            "recent": [{"outcome": r.get("outcome"), "group": outcome_group(r.get("outcome")),
                        "intent": r.get("intent"), "language": r.get("language"),
                        "ticket": bool(r.get("ticket_created")), "attention_ms": r.get("duration_ms"),
                        "system_ms": r.get("step_ms")} for r in reversed(rows[-8:])],
        }


def offline_triage(results_dir: Path | None = None) -> dict[str, Any] | None:
    """Accuracy and critical errors per model and language in the latest triage evaluation run."""
    folder = results_dir or Path(os.environ.get("EVAL_RESULTS_DIR") or REPO_ROOT / "evals" / "cases" / "results")
    runs = sorted(folder.glob("triage_*.csv"))
    if not runs:
        return None
    with runs[-1].open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    table: dict[tuple[str, str], dict[str, int]] = {}
    for row in rows:
        cell = table.setdefault((row["model"], row["lang"]), {"cases": 0, "correct": 0, "critical": 0})
        cell["cases"] += 1
        cell["correct"] += row.get("ok") == "1"
        cell["critical"] += row.get("critical") == "1"
    return {"run": runs[-1].stem, "cases": len({row["id"] for row in rows}),
            "results": [{"model": model, "language": lang, **cell,
                         "accuracy": round(cell["correct"] / cell["cases"], 3)}
                        for (model, lang), cell in sorted(table.items())]}
