"""Structured JSON events for the MCP server, same shape as the agent's
(apps/agent/src/bank_agent/observability.py): `ts, level, service, event, conversation_id, node`.

Events: `tool` (one per tools/call) and `bq.query` (one per BigQuery job). The agent sends
conversation_id/node in each call's _meta; CorrelationMiddleware puts them in context for
every event logged while the tool runs. They are caller-supplied, so they are only used
for logs and job labels, never for authorization.

Logs go to stderr: over stdio, stdout is the JSON-RPC channel.
"""
import contextlib
import contextvars
import datetime as dt
import json
import logging
import re
import sys
import time
from collections.abc import Mapping
from typing import Any

SERVICE = "mcp"

logger = logging.getLogger("bank_mcp.events")
_conversation: contextvars.ContextVar[str | None] = contextvars.ContextVar("conversation_id", default=None)
_node: contextvars.ContextVar[str | None] = contextvars.ContextVar("node", default=None)


def current() -> dict[str, str | None]:
    return {"conversation_id": _conversation.get(), "node": _node.get()}


@contextlib.contextmanager
def bind(**values: str | None):
    tokens = [(var, var.set(values[key])) for key, var in (("conversation_id", _conversation), ("node", _node))
              if key in values]
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(level, event, extra={"event_data": {"service": SERVICE, "event": event, **current(), **fields}})


def conversation_label() -> str | None:
    """The conversation id as a BigQuery label value (lowercase, [a-z0-9_-], 63 chars)."""
    cid = _conversation.get()
    return re.sub(r"[^a-z0-9_-]", "_", cid.lower())[:63] if cid else None


def _meta_value(meta: Mapping, key: str) -> str | None:
    value = meta.get(key)
    return str(value)[:128] if value is not None else None


def _is_error(result: Any) -> bool:
    if isinstance(result, Mapping):
        return bool(result.get("isError") or result.get("is_error"))
    return bool(getattr(result, "is_error", False) or getattr(result, "isError", False))


class CorrelationMiddleware:
    """For tools/call: bind the caller's conversation_id/node and log one `tool` event."""

    async def __call__(self, ctx, call_next):
        if ctx.method != "tools/call":
            return await call_next(ctx)
        meta = ctx.meta if isinstance(ctx.meta, Mapping) else {}
        tool = (ctx.params or {}).get("name")
        started = time.perf_counter()
        with bind(conversation_id=_meta_value(meta, "conversation_id"), node=_meta_value(meta, "node")):
            try:
                result = await call_next(ctx)
            except Exception as exc:
                log_event("tool", tool=tool, ms=_ms(started), status="error", error=type(exc).__name__)
                raise
            log_event("tool", tool=tool, ms=_ms(started), status="error" if _is_error(result) else "ok")
            return result


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


class JsonFormatter(logging.Formatter):
    """Events as they are; any other record (SDK, startup) as event "log". `severity` is for Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        data = getattr(record, "event_data", None) or {
            "service": SERVICE, "event": "log", "logger": record.name, "message": record.getMessage()}
        line = {"ts": dt.datetime.fromtimestamp(record.created, dt.timezone.utc).isoformat(),
                "level": record.levelname, "severity": record.levelname, **data}
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
