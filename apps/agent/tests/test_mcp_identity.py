from datetime import date
import pytest
from bank_agent.clients.mcp_identity import McpIdentityRepository
from bank_agent.clients.repository import RepositoryUnavailable
from bank_agent.clients.contracts import ServiceFailure
from bank_agent.nodes.validator_agent.validator import IdentityValidator, Status, normalize_id

class Client:
    def __init__(self, result):
        self.result=result;self.calls=[]
    def call(self,name,args):
        self.calls.append((name,args))
        if isinstance(self.result,Exception): raise self.result
        return self.result

def test_real_cli_id_is_preserved_and_other_document_normalization_unchanged():
    assert normalize_id(" cli-AHN8JE0OZJBO ")=="CLI-AHN8JE0OZJBO"
    assert normalize_id("1.020.304.050")=="1020304050"

def test_three_factors_go_to_mcp_and_canonical_identity_is_used():
    client=Client({"verified":True,"customer_id":"CLI-ONE",
                   "products":[{"product_number":"12345678","product_type":"Tarjeta Crédito","status":"Active"}]})
    validator=IdentityValidator(McpIdentityRepository(client))
    sid=validator.new_session().session_id
    result=validator.verify(sid,"1.020.304.050","1990-04-03","1234 5678")
    assert result.status==Status.VERIFIED
    assert validator.get_session(sid).customer_id=="CLI-ONE"
    assert client.calls==[("verify_identity",{"customer_id":"1020304050",
                 "date_of_birth":"1990-04-03","product_number":"12345678"})]
    assert validator.can_access_product(sid,"12345678")
    assert not validator.can_access_product(sid,"99999999")

def test_mismatch_does_not_authenticate():
    v=IdentityValidator(McpIdentityRepository(Client({"verified":False})))
    sid=v.new_session().session_id
    assert v.verify(sid,"CLI-ONE","1990-04-03","12345678").status==Status.FAILED
    assert not v.is_authenticated(sid)

def test_outage_fails_closed():
    v=IdentityValidator(McpIdentityRepository(Client(ServiceFailure("network"))))
    sid=v.new_session().session_id
    assert v.verify(sid,"CLI-ONE","1990-04-03","12345678").status==Status.SERVICE_UNAVAILABLE
    assert not v.is_authenticated(sid)
