import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from bank_agent.clients.contracts import ServiceFailure, SessionExpired  # noqa: E402
from bank_agent.clients.mcp_client import McpToolClient  # noqa: E402

SERVER = str(Path(__file__).with_name("mcp_echo_server.py"))


@pytest.fixture(scope="module")
def client():
    with McpToolClient(command=sys.executable, args=[SERVER], timeout_s=5) as c:
        yield c


def test_structured_call_reuses_one_session(client):
    assert client.call("echo", {"text": "hola"}) == {"text": "hola"}
    session = client._session
    assert client.call("echo", {"text": "olá"}) == {"text": "olá"}
    assert client._session is session


def test_tool_error_is_service_failure_without_detail(client):
    with pytest.raises(ServiceFailure) as exc:
        client.call("boom", {})
    assert "secret" not in str(exc.value)


def test_invalid_session_from_server_is_session_expired(client):
    with pytest.raises(SessionExpired):
        client.call("expired", {})


def test_timeout_is_service_failure_and_session_survives(client):
    with pytest.raises(ServiceFailure):
        client.call("slow", {})
    assert client.call("echo", {"text": "still alive"}) == {"text": "still alive"}


def test_unreachable_server_is_service_failure():
    c = McpToolClient(command=sys.executable, args=["-c", "import sys; sys.exit(1)"], timeout_s=5)
    with pytest.raises(ServiceFailure):
        c.call("echo", {"text": "x"})
    c.close()


def test_requires_exactly_one_transport():
    with pytest.raises(ValueError):
        McpToolClient()
    with pytest.raises(ValueError):
        McpToolClient(url="http://x", command="y")


def test_stdio_passes_server_config_without_llm_credentials(monkeypatch):
    import mcp.client.stdio
    captured = {}
    def capture(parameters):
        captured["parameters"] = parameters
        return object()
    monkeypatch.setattr(mcp.client.stdio, "stdio_client", capture)
    monkeypatch.setenv("SESSION_SIGNING_KEY", "test-signing-key-not-real")
    monkeypatch.setenv("SANDBOX_SCENARIO_ID", "scenario-test")
    monkeypatch.setenv("BQ_PROJECT", "project-test")
    monkeypatch.setenv("MAX_BYTES_BILLED", "10000000")
    monkeypatch.setenv("GROQ_API_KEY", "must-not-inherit")
    c = McpToolClient(command=sys.executable)
    c._transport()
    env = captured["parameters"].env
    assert env["SESSION_SIGNING_KEY"] == "test-signing-key-not-real"
    assert env["SANDBOX_SCENARIO_ID"] == "scenario-test"
    assert env["BQ_PROJECT"] == "project-test"
    assert env["MAX_BYTES_BILLED"] == "10000000"
    assert "GROQ_API_KEY" not in env
