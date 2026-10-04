import datetime as dt
from types import SimpleNamespace
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from bank_mcp.tools import server
from bank_mcp.services import session

class Gateway:
    def __init__(self,rows): self.rows=rows; self.calls=[]
    def table(self,name): return name
    def query(self,sql,params,tool):
        self.calls.append((sql,params,tool)); return self.rows

@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(server,"_throttle",session.LoginThrottle(3,dt.timedelta(minutes=15)))
    monkeypatch.setattr(server,"_signing_key",lambda:b"k"*32)
    monkeypatch.setattr(server,"get_settings",lambda:SimpleNamespace(session_ttl_minutes=15))

def test_document_parameters_and_signed_session(monkeypatch):
    gw=Gateway([{"customer_id":"CLI-ONE","product_numbers":["12345678"]}])
    monkeypatch.setattr(server,"_gw",lambda:gw)
    r=server.verify_identity("1.020.304.050",dt.date(1990,4,3),"12345678")
    assert r.status=="verified"
    assert session.verify(r.session_token,b"k"*32)=="CLI-ONE"
    sql,params,_=gw.calls[0]
    assert params[0].name=="document_number" and params[0].value=="1020304050"
    assert "@document_number" in sql and "c.customer_id=@" not in sql
    assert "date_of_birth" not in r.model_dump()

def test_mismatch_and_lockout(monkeypatch):
    monkeypatch.setattr(server,"_gw",lambda:Gateway([]))
    results=[server.verify_identity("1020304050",dt.date(1990,4,3),"12345678") for _ in range(3)]
    assert [r.status for r in results]==["failed","failed","locked"]
    assert all(r.customer_id is None and r.session_token is None for r in results)

def test_ambiguous_identity_fails_closed(monkeypatch):
    monkeypatch.setattr(server,"_gw",lambda:Gateway([{},{}]))
    with pytest.raises(ToolError):
        server.verify_identity("1020304050",dt.date(1990,4,3),"12345678")
