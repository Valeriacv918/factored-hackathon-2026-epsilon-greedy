"""Shared fixtures: a fake BigQuery gateway, a known signing key and fresh server state."""
import datetime as dt

import pytest
from google.cloud import bigquery

from bank_mcp.config.settings import get_settings
from bank_mcp.services import session
from bank_mcp.tools import server

KEY = "test-signing-key-" + "x" * 32


class FakeGateway:
    """Answers by tool name: a list of rows, or a callable(params) -> rows. Records every query."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def table(self, name):
        return f"`p.cur.{name}`"

    def sandbox_table(self, name):
        return f"`p.sbx.{name}`"

    def query(self, sql, params, *, tool):
        values = {p.name: p.values if isinstance(p, bigquery.ArrayQueryParameter) else p.value for p in params}
        self.calls.append((tool, sql, values))
        answer = self.answers.get(tool, [])
        return answer(values) if callable(answer) else answer

    def sent(self, tool):
        return [(sql, values) for name, sql, values in self.calls if name == tool]


@pytest.fixture(autouse=True)
def server_state(monkeypatch):
    """Known key, no scenario and no leftovers from the repo .env or earlier tests."""
    monkeypatch.setenv("SESSION_SIGNING_KEY", KEY)
    monkeypatch.setenv("SANDBOX_SCENARIO_ID", "")
    get_settings.cache_clear()
    monkeypatch.setattr(server, "_scenario_state", None)
    monkeypatch.setattr(server, "_throttle", None)
    yield
    get_settings.cache_clear()


@pytest.fixture
def signing_key():
    return KEY.encode()


@pytest.fixture
def gateway(monkeypatch):
    """gateway(tool=rows, ...) installs a FakeGateway as the server's BigQuery client."""
    def install(**answers):
        gw = FakeGateway(answers)
        monkeypatch.setattr(server, "_gw", lambda: gw)
        return gw
    return install


@pytest.fixture
def token(signing_key):
    """token(customer_id) -> a valid session token for that customer."""
    return lambda customer="CLI-1": session.issue(customer, signing_key, dt.timedelta(minutes=5))
