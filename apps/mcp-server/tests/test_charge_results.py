from types import SimpleNamespace
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from bank_mcp.tools import server
from bank_mcp.sql import charge_results

class Gateway:
    settings=SimpleNamespace(bq_project="test")
    def __init__(self): self.calls=[]; self.rows=1
    def table(self,name): return name
    def sandbox_table(self,name): return name
    def query(self,sql,params,**kwargs):
        self.calls.append((sql,{p.name:p.value for p in params},kwargs))
        return [] if "MERGE" in sql else [{}]*self.rows

def test_bound_identity_and_repeatable_job(monkeypatch):
    gw=Gateway()
    monkeypatch.setattr(server,"_gw",lambda:gw)
    monkeypatch.setattr(server,"_customer",lambda token:"authenticated-customer")
    a=server.save_charge_explanation("token","conversation","TX-1","Pending")
    b=server.save_charge_explanation("token","conversation","TX-1","Pending")
    assert a.verified and a.result_id==b.result_id
    assert gw.calls[0][1]["customer_id"]=="authenticated-customer"
    assert gw.calls[0][2]["job_id"]==gw.calls[2][2]["job_id"]
    assert "customer_id=@customer_id" in charge_results.SAVE
    assert "transaction_status=@observed_status" in charge_results.SAVE
    assert "WHEN MATCHED" not in charge_results.SAVE

def test_no_receipt_fails_closed(monkeypatch):
    gw=Gateway();gw.rows=0
    monkeypatch.setattr(server,"_gw",lambda:gw)
    monkeypatch.setattr(server,"_customer",lambda token:"customer")
    with pytest.raises(ToolError):
        server.save_charge_explanation("token","conversation","TX-1","Reversed")

def test_bad_session_does_not_query(monkeypatch):
    def invalid(token): raise ToolError("session_invalid")
    monkeypatch.setattr(server,"_customer",invalid)
    monkeypatch.setattr(server,"_gw",lambda:pytest.fail("Must not access data"))
    with pytest.raises(ToolError):
        server.save_charge_explanation("bad","conversation","TX-1","Declined")
