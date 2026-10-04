import datetime as dt
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from bank_mcp.tools import server

class Gateway:
    def __init__(self, rows):
        self.rows=rows;self.calls=[]
    def table(self,name):
        return "`hackaton-509923.bank_curated."+name+"`"
    def query(self,sql,params,tool):
        self.calls.append((sql,{p.name:p.value for p in params},tool))
        return self.rows

def test_identity_query_binds_all_factors_and_ownership(monkeypatch):
    gw=Gateway([{"customer_id":"CLI-ONE","products":[{"product_number":"12345678",
                 "product_type":"Tarjeta Crédito","status":"Active"}]}])
    monkeypatch.setattr(server,"_gw",lambda:gw)
    result=server.verify_identity("CLI-ONE",dt.date(1990,4,3),"12345678")
    sql,params,tool=gw.calls[0]
    assert result.verified and result.customer_id=="CLI-ONE"
    assert params=={"customer_id":"CLI-ONE","date_of_birth":dt.date(1990,4,3),"product_number":"12345678"}
    assert "owned.customer_id=c.customer_id" in sql
    assert "c.date_of_birth=@date_of_birth" in sql
    assert "p.customer_id=c.customer_id" in sql
    assert "CLI-ONE" not in sql
    assert "date_of_birth" not in result.model_dump()
    assert tool=="verify_identity"

def test_identity_mismatch_is_generic(monkeypatch):
    monkeypatch.setattr(server,"_gw",lambda:Gateway([]))
    result=server.verify_identity("CLI-ONE",dt.date(1990,4,3),"12345678")
    assert result.model_dump()=={"verified":False,"customer_id":None,"products":[]}

def test_oversized_identity_is_rejected_not_truncated(monkeypatch):
    row={"customer_id":"CLI-ONE","products":[{"product_number":"12345678"}]*201}
    monkeypatch.setattr(server,"_gw",lambda:Gateway([row]))
    with pytest.raises(ToolError):
        server.verify_identity("CLI-ONE",dt.date(1990,4,3),"12345678")
