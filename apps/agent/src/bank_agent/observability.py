"""Structured JSON events: which steps ran, what the LLM did, which MCP tools were called.

One JSON object per line with `ts, level, service, event, conversation_id, node` plus the
event's fields. The MCP server emits the same shape (bank_mcp/observability.py), and the
agent sends conversation_id/node in each tool call's _meta so both sides share the id.

Events: step, llm.call, llm.result, mcp.call, conversation.summary (the web app adds
http.request through log_event). The summary carries the conversation's outcome and
routing (OUTCOME_FIELDS) and counts, never customer, card or ticket identifiers.

Never logged: the identity factors and the session token (SENSITIVE). LLM prompts and
raw outputs only with LOG_LLM_CONTENT=1, for local debugging: validator prompts contain
the customer's document number and date of birth.
"""
import contextlib
import contextvars
import datetime as dt
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.errors import GraphBubbleUp

SERVICE = "agent"
SENSITIVE = frozenset({"session_token", "document_number", "date_of_birth", "product_number", "product_numbers"})
PACKET_FIELDS = ("reason", "queue")   # a handoff packet carries customer text: log only its routing

logger = logging.getLogger("bank_agent.events")
_conversation: contextvars.ContextVar[str | None] = contextvars.ContextVar("conversation_id", default=None)
_node: contextvars.ContextVar[str | None] = contextvars.ContextVar("node", default=None)


def current() -> dict[str, str | None]:
    return {"conversation_id": _conversation.get(), "node": _node.get()}


@contextlib.contextmanager
def bind(**values: str | None):
    """Set conversation_id and/or node for every event logged inside the block."""
    tokens = [(var, var.set(values[key])) for key, var in (("conversation_id", _conversation), ("node", _node))
              if key in values]
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def content_enabled() -> bool:
    return os.environ.get("LOG_LLM_CONTENT", "").strip().lower() in {"1", "true", "yes"}


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def safe_args(arguments: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in arguments.items():
        if key in SENSITIVE:
            out[key] = "<redacted>"
        elif key == "packet" and isinstance(value, dict):
            out[key] = {field: value.get(field) for field in PACKET_FIELDS}
        else:
            out[key] = value
    return out


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    payload = {"service": SERVICE, "event": event, **current(), **fields}
    _accumulate(payload)
    logger.log(level, event, extra={"event_data": payload})


# --- per-conversation cost/latency summary ----------------------------------------------

_totals: dict[str, dict[str, float]] = {}
_totals_lock = threading.Lock()


# Routing labels the summary may carry; identifiers (customer, cards, cases, tickets) are only counted.
OUTCOME_FIELDS = ("outcome", "reason", "intent", "language", "triage_route", "queue", "priority",
                  "validation_status")


def _empty() -> dict[str, float]:
    return dict(steps=0, step_ms=0.0, llm_calls=0, input_tokens=0, output_tokens=0, llm_ms=0.0, mcp_calls=0,
                mcp_ms=0.0, errors=0, started=time.time())


def outcome_fields(state: dict[str, Any]) -> dict[str, Any]:
    """What the conversation.summary records about how a conversation ended."""
    return {**{key: state.get(key) for key in OUTCOME_FIELDS},
            "authenticated": bool(state.get("authenticated")), "turns": state.get("turns"),
            "ticket_created": bool(state.get("ticket_id")), "cases_filed": len(state.get("case_ids") or []),
            "cards_blocked": len(state.get("blocked_cards") or [])}


def _accumulate(payload: dict[str, Any]) -> None:
    cid, event = payload.get("conversation_id"), payload["event"]
    if cid is None or event not in {"step", "llm.call", "mcp.call"}:
        return
    with _totals_lock:
        t = _totals.setdefault(cid, _empty())
        if event == "step":
            t["steps"] += 1
            t["step_ms"] += payload.get("ms") or 0
        elif event == "llm.call":
            t["llm_calls"] += 1
            t["input_tokens"] += payload.get("input_tokens") or 0
            t["output_tokens"] += payload.get("output_tokens") or 0
            t["llm_ms"] += payload.get("ms") or 0
        else:
            t["mcp_calls"] += 1
            t["mcp_ms"] += payload.get("ms") or 0
        if payload.get("status") == "error" or payload.get("error"):
            t["errors"] += 1


def log_summary(conversation_id: str, **outcome: Any) -> None:
    """Emit conversation.summary with the totals so far (plus outcome_fields), then start over.

    duration_ms is wall time since the first event, customer pauses included; step_ms is
    the time the graph spent working."""
    with _totals_lock:
        totals = _totals.pop(conversation_id, None) or _empty()
    totals["duration_ms"] = round((time.time() - totals.pop("started")) * 1000, 1)
    for key in ("step_ms", "llm_ms", "mcp_ms"):
        totals[key] = round(totals[key], 1)
    with bind(conversation_id=conversation_id, node=None):
        log_event("conversation.summary", **totals, **outcome)


def reset() -> None:
    with _totals_lock:
        _totals.clear()


# --- graph steps ----------------------------------------------------------------------------

@contextlib.contextmanager
def logged_step(conversation_id: str | None, node: str, phase: str | None):
    """Log one `step` per node run. The caller sets info["next"] (and info["phase"]), and
    info["state"] (the state after the step) so the summary can record the outcome.

    A pause for the customer (interrupt) is logged as waiting, not as an error; the
    summary is emitted when a node routes to "end".
    """
    info: dict[str, Any] = {"next": None, "phase": phase, "state": None}
    started = time.perf_counter()
    with bind(conversation_id=conversation_id, node=node):
        try:
            yield info
        except GraphBubbleUp:
            log_event("step", phase=phase, next=None, ms=elapsed_ms(started), waiting=True)
            raise
        except Exception as exc:
            log_event("step", phase=phase, next=None, ms=elapsed_ms(started), error=type(exc).__name__)
            raise
        log_event("step", phase=info["phase"], next=info["next"], ms=elapsed_ms(started))
    if info["next"] == "end" and conversation_id:
        log_summary(conversation_id, **outcome_fields(info["state"] or {}))


# --- LLM ------------------------------------------------------------------------------------

def _messages(batches) -> list[dict[str, Any]]:
    return [{"role": m.type, "content": m.content} for batch in batches for m in batch]


class LlmLogHandler(BaseCallbackHandler):
    """One `llm.call` per chat-model call: step, model, latency, tokens, status."""

    def __init__(self) -> None:
        self._runs: dict[Any, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        params = kwargs.get("invocation_params") or {}
        run = {"started": time.perf_counter(), "context": current(),
               "step": (metadata or {}).get("llm_step"),
               "model": params.get("model") or params.get("model_name")}
        if content_enabled():
            run["messages"] = _messages(messages)
        with self._lock:
            self._runs[run_id] = run

    def _finish(self, run_id, **fields) -> None:
        with self._lock:
            run = self._runs.pop(run_id, None)
        if run is None:
            return
        extra = {"messages": run["messages"]} if "messages" in run else {}
        with bind(**run["context"]):
            log_event("llm.call", step=run["step"], model=run["model"], ms=elapsed_ms(run["started"]),
                      **fields, **extra)

    def on_llm_end(self, response, *, run_id, **kwargs):
        generation = response.generations[0][0] if response.generations and response.generations[0] else None
        message = getattr(generation, "message", None)
        usage = getattr(message, "usage_metadata", None) or {}
        fields: dict[str, Any] = {"status": "ok", "input_tokens": usage.get("input_tokens"),
                                  "output_tokens": usage.get("output_tokens")}
        if content_enabled() and message is not None:
            fields["output"] = {"content": message.content, "tool_calls": getattr(message, "tool_calls", None)}
        self._finish(run_id, **fields)

    def on_llm_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, status="error", error=type(error).__name__)


LLM_HANDLER = LlmLogHandler()


def llm_config(step: str) -> dict[str, Any]:
    """Runnable config that logs every model call under `step` (understanding, triage...)."""
    return {"callbacks": [LLM_HANDLER], "metadata": {"llm_step": step}, "run_name": step}


# --- output ---------------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    """Events as they are; any other log record as event "log". `severity` is for Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        data = getattr(record, "event_data", None) or {
            "service": SERVICE, "event": "log", "logger": record.name, "message": record.getMessage()}
        line = {"ts": dt.datetime.fromtimestamp(record.created, dt.timezone.utc).isoformat(),
                "level": record.levelname, "severity": record.levelname, **data}
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False, default=str)


_handler: logging.Handler | None = None


def configure_logging() -> logging.Handler:
    """JSON lines for every `bank_agent` logger: to LOG_FILE if set, else stdout. LOG_LEVEL sets the level."""
    global _handler
    root = logging.getLogger("bank_agent")
    if _handler is not None:
        root.removeHandler(_handler)
        _handler.close()
    path = os.environ.get("LOG_FILE")
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        _handler = logging.FileHandler(path, encoding="utf-8")
    else:
        _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(JsonFormatter())
    root.addHandler(_handler)
    root.setLevel((os.environ.get("LOG_LEVEL") or "INFO").upper())
    return _handler
