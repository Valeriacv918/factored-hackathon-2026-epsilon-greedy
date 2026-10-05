"""Server-side events: one `tool` event per tools/call (with the agent's correlation id
from the request _meta) and one `bq.query` event per BigQuery job, failures included.

Same JSON event contract as the agent (apps/agent/src/bank_agent/observability.py).
"""
import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
from google.api_core import exceptions as gexc

from bank_mcp import observability as obs
from bank_mcp.repositories.bigquery import BigQueryGateway, QueryError
from bank_mcp.tools import server


def events(caplog, name=None):
    return [r.event_data for r in caplog.records
            if hasattr(r, "event_data") and (name is None or r.event_data["event"] == name)]


@pytest.fixture(autouse=True)
def capture(caplog):
    caplog.set_level(logging.INFO, logger="bank_mcp")


def tools_call(name="list_cards", meta=None):
    return SimpleNamespace(method="tools/call", params={"name": name, "arguments": {}}, meta=meta)


# --- correlation middleware -------------------------------------------------------------

def test_middleware_is_registered():
    assert any(isinstance(m, obs.CorrelationMiddleware) for m in server.mcp.middleware)


def test_tools_call_binds_correlation_and_logs_tool_event(caplog):
    seen = {}

    async def call_next(ctx):
        seen.update(obs.current())
        return {"content": [], "isError": False}

    ctx = tools_call(meta={"conversation_id": "c-1", "node": "fraud_agent"})
    asyncio.run(obs.CorrelationMiddleware()(ctx, call_next))
    assert seen == {"conversation_id": "c-1", "node": "fraud_agent"}
    assert obs.current() == {"conversation_id": None, "node": None}
    [ev] = events(caplog, "tool")
    assert ev["service"] == "mcp" and ev["tool"] == "list_cards" and ev["status"] == "ok"
    assert ev["conversation_id"] == "c-1" and ev["node"] == "fraud_agent" and ev["ms"] >= 0


@pytest.mark.parametrize("result", [{"content": [], "isError": True}, SimpleNamespace(is_error=True)])
def test_tool_error_result_is_logged_as_error(caplog, result):
    async def call_next(ctx):
        return result
    asyncio.run(obs.CorrelationMiddleware()(tools_call(), call_next))
    assert events(caplog, "tool")[0]["status"] == "error"


def test_raised_exception_is_logged_and_reraised(caplog):
    async def call_next(ctx):
        raise RuntimeError("boom")
    with pytest.raises(RuntimeError):
        asyncio.run(obs.CorrelationMiddleware()(tools_call(), call_next))
    [ev] = events(caplog, "tool")
    assert ev["status"] == "error" and ev["error"] == "RuntimeError"


def test_other_methods_pass_through_without_event(caplog):
    async def call_next(ctx):
        return {}
    asyncio.run(obs.CorrelationMiddleware()(SimpleNamespace(method="tools/list", params=None, meta=None),
                                            call_next))
    assert events(caplog, "tool") == []


def test_json_formatter_writes_one_json_object(caplog):
    obs.log_event("custom", a=1)
    record = next(r for r in caplog.records if hasattr(r, "event_data"))
    line = json.loads(obs.JsonFormatter().format(record))
    assert line["event"] == "custom" and line["service"] == "mcp" and line["a"] == 1 and "ts" in line


# --- BigQuery gateway ---------------------------------------------------------------------

class FakeJob:
    total_bytes_processed = 5

    def result(self, **kwargs):
        return []


class FakeClient:
    def __init__(self, error=None):
        self.error, self.configs = error, []

    def query(self, sql, job_config=None, **kwargs):
        self.configs.append(job_config)
        if self.error:
            raise self.error
        return FakeJob()


def gateway(client):
    gw = BigQueryGateway.__new__(BigQueryGateway)   # no ADC
    gw.settings = SimpleNamespace(max_bytes_billed=10**9, bq_location="us-central1", query_timeout_s=1, max_rows=10)
    gw.client = client
    return gw


@pytest.mark.parametrize("error, status", [
    (gexc.BadRequest("detail-xyz"), "bad_request"),
    (gexc.NotFound("detail-xyz"), "not_found"),
    (gexc.Forbidden("detail-xyz"), "forbidden"),
    (gexc.ServiceUnavailable("detail-xyz"), "api_error"),
])
def test_query_failures_log_their_detail(caplog, error, status):
    with obs.bind(conversation_id="c-1"):
        with pytest.raises(QueryError) as exc:
            gateway(FakeClient(error)).query("SELECT 1", [], tool="list_cards")
    [ev] = events(caplog, "bq.query")
    assert ev["status"] == status and "detail-xyz" in ev["error"]
    assert ev["tool"] == "list_cards" and ev["conversation_id"] == "c-1"
    if status == "api_error":
        assert "detail-xyz" not in str(exc.value)   # caller gets a generic message


def test_successful_query_logs_and_labels_the_conversation(caplog):
    client = FakeClient()
    with obs.bind(conversation_id="Conv-ABC.1"):
        assert gateway(client).query("SELECT 1", [], tool="list_cards") == []
    assert all(c.labels["conversation"] == "conv-abc_1" for c in client.configs)
    [ev] = events(caplog, "bq.query")
    assert ev["status"] == "ok" and ev["rows"] == 0 and ev["bytes"] == 5 and ev["sql_hash"]


def test_query_without_conversation_has_no_conversation_label():
    client = FakeClient()
    gateway(client).query("SELECT 1", [], tool="list_cards")
    assert "conversation" not in client.configs[-1].labels
