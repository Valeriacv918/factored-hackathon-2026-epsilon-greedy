from datetime import datetime, timedelta, timezone
from bank_agent.clients.identity import McpIdentityChecker
from bank_agent.clients.contracts import ServiceFailure
from bank_agent.nodes.validator_agent.validator import IdentityValidator, Status, normalize_document

class Client:
    def __init__(self, result):
        self.result=result; self.calls=[]
    def call(self,name,args):
        self.calls.append((name,args))
        if isinstance(self.result,Exception): raise self.result
        return self.result

def test_document_only_and_canonical_identity():
    client=Client({"status":"verified","customer_id":"CLI-ONE",
        "product_numbers":["12345678"],"session_token":"signed-token",
        "expires_at":(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()})
    v=IdentityValidator(McpIdentityChecker(client))
    sid=v.new_session().session_id
    assert v.verify(sid,"1.020.304.050","1990-04-03","1234 5678").status==Status.VERIFIED
    assert client.calls==[("verify_identity",{"document_number":"1020304050",
        "date_of_birth":"1990-04-03","product_number":"12345678"})]
    assert v.get_session(sid).customer_id=="CLI-ONE"
    assert v.get_session(sid).session_token=="signed-token"
    assert v.can_access_product(sid,"12345678")
    assert normalize_document("CLI-ONE") is None

def test_mismatch_and_outage_fail_closed():
    for reply,status in [({"status":"failed","attempts_left":2},Status.FAILED),
                         (ServiceFailure("network"),Status.SERVICE_UNAVAILABLE)]:
        v=IdentityValidator(McpIdentityChecker(Client(reply)))
        sid=v.new_session().session_id
        assert v.verify(sid,"1020304050","1990-04-03","12345678").status==status
        assert not v.is_authenticated(sid)

def test_validated_session_supplies_token_and_expiry_blocks_data():
    from bank_agent.clients.mcp_services import McpServices
    from bank_agent.clients.sessions import StaticSessions
    from bank_agent.clients.contracts import SessionExpired
    import pytest
    client=Client({"status":"verified","customer_id":"CLI-ONE",
        "product_numbers":["12345678"],"session_token":"signed-token",
        "expires_at":(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()})
    services=McpServices(client,StaticSessions({}),None)
    services._identity_validator=IdentityValidator(McpIdentityChecker(client))
    v=services._identity_validator
    sid=v.new_session().session_id
    assert v.verify(sid,"1020304050","1990-04-03","12345678").status==Status.VERIFIED
    client.result={"cards":[]}
    services.tool("list_cards",session_ref=sid,customer_id="CLI-ONE",
                  arguments={"session_token":"forged","customer_id":"OTHER"})
    assert client.calls[-1]==("list_cards",{"session_token":"signed-token"})
    v.get_session(sid).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    count=len(client.calls)
    with pytest.raises(SessionExpired):
        services.tool("list_cards",session_ref=sid,customer_id="CLI-ONE",arguments={})
    assert len(client.calls)==count
