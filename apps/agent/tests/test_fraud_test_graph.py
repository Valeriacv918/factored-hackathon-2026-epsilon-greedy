from copy import deepcopy
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from test_charge_test_graph import ChargeServices, TX
from bank_agent.graphs.validation_triage import build_graph
from bank_agent.graphs.state import initial_state
from bank_agent.nodes.triage_agent.schemas import Understanding, Intent

class FraudServices(ChargeServices):
    def __init__(self,status="Approved",score="1"):
        super().__init__({**TX,"date":"2026-06-10T12:00:00+00:00","status":status,
                          "fraud_score":score,"card_id":"CARD-1","amount_usd":"20"})
        self.understanding=Understanding(intent=Intent.NOT_ME,confidence=.99,wants_human=False)
        self.actions=[]; self.fail_receipt=False
    def understand(self,text,language):
        return {"intent":"not_me","slots":{"date":"2026-06-10"}}
    def tool(self,name,**kwargs):
        self.actions.append(name)
        if name=="find_transactions": return super().tool(name,**kwargs)
        records={
          "get_card":{"id":"CARD-1","customer_id":"CLI-ONE","status":"Active"},
          "block_card":{"id":"BLOCK-1"},
          "read_block":{"id":"BLOCK-1","card_id":"CARD-1","status":"Blocked","verified":not self.fail_receipt},
          "dispute_context":{"existing_case_id":None,"recent_dispute_count":0},
          "file_dispute":{"id":"CASE-1"},
          "read_dispute":{"id":"CASE-1","transaction_id":"TX-1","customer_id":"CLI-ONE","verified":True},
        }
        return deepcopy(records[name])

def start(s):
    g=build_graph(s,checkpointer=InMemorySaver(),test_fraud=True,test_charge_error=True)
    c={"configurable":{"thread_id":"one"}}
    g.invoke(initial_state("one","","Hola"),c)
    g.invoke(Command(resume={"text":"valid factors"}),c)
    r=g.invoke(Command(resume={"text":"No reconozco esta compra."}),c)
    r=g.invoke(Command(resume={"choice":"TX-1"}),c)
    assert r["__interrupt__"][0].value["kind"]=="confirm_block"
    assert "block_card" not in s.actions
    return g,c,r

def test_approved_confirm_block_dispute_then_finish():
    s=FraudServices();g,c,_=start(s)
    r=g.invoke(Command(resume={"choice":"yes"}),c)
    assert r["__interrupt__"][0].value["kind"]=="confirm_dispute"
    assert "file_dispute" not in s.actions and "read_block" in s.actions
    r=g.invoke(Command(resume={"choice":"yes"}),c)
    assert r["__interrupt__"][0].value["kind"]=="more_charges"
    r=g.invoke(Command(resume={"choice":"no"}),c)
    assert r["outcome"]=="fraud_intake_complete" and r["case_ids"]==["CASE-1"]
    assert s.actions.count("block_card")==1 and s.actions.count("file_dispute")==1

def test_decline_block_never_writes():
    s=FraudServices();g,c,_=start(s)
    r=g.invoke(Command(resume={"choice":"no"}),c)
    assert r["outcome"]=="human_required"
    assert "block_card" not in s.actions and "file_dispute" not in s.actions

def test_session_expired_at_confirmation_prevents_write():
    s=FraudServices();g,c,_=start(s);s.auth.clear()
    r=g.invoke(Command(resume={"choice":"yes"}),c)
    assert r["outcome"]=="authentication_required"
    assert "block_card" not in s.actions

def test_bad_block_receipt_prevents_dispute():
    s=FraudServices();s.fail_receipt=True;g,c,_=start(s)
    r=g.invoke(Command(resume={"choice":"yes"}),c)
    assert r["outcome"]=="service_unavailable" and "file_dispute" not in s.actions

@pytest.mark.parametrize("status",["Reversed","Declined"])
def test_nonapproved_skips_dispute(status):
    s=FraudServices(status);g,c,_=start(s)
    r=g.invoke(Command(resume={"choice":"yes"}),c)
    r=g.invoke(Command(resume={"choice":"no"}),c)
    assert r["outcome"]=="fraud_intake_complete" and "file_dispute" not in s.actions

def test_pending_requires_human_after_verified_block():
    s=FraudServices("Pending");g,c,_=start(s)
    r=g.invoke(Command(resume={"choice":"yes"}),c)
    assert r["outcome"]=="human_required" and r["reason"]=="pending_fraud"
    assert r["blocked_cards"]==["CARD-1"] and "file_dispute" not in s.actions

def test_more_charges_returns_to_shared_search():
    s=FraudServices("Declined");g,c,_=start(s)
    g.invoke(Command(resume={"choice":"yes"}),c)
    r=g.invoke(Command(resume={"choice":"yes"}),c)
    assert r["__interrupt__"][0].value["kind"]=="transaction_details"
    assert r["slots"]=={} and r["transaction"]=={}

def test_not_me_with_missing_score_still_enters_fraud():
    s=FraudServices("Declined",None)
    start(s)

def test_charge_error_with_high_score_routes_to_fraud():
    s=FraudServices(score="90")
    s.understanding=Understanding(intent=Intent.CHARGE_ERROR,confidence=.99,wants_human=False)
    s.understand=lambda text,lang:{"intent":"charge_error","slots":{}}
    start(s)

def test_missing_card_reaches_human_without_writes():
    s=FraudServices();s.tx["card_id"]=None
    g=build_graph(s,checkpointer=InMemorySaver(),test_fraud=True)
    c={"configurable":{"thread_id":"one"}}
    g.invoke(initial_state("one","","Hola"),c)
    g.invoke(Command(resume={"text":"valid factors"}),c)
    g.invoke(Command(resume={"text":"No reconozco esta compra."}),c)
    r=g.invoke(Command(resume={"choice":"TX-1"}),c)
    assert r["outcome"]=="human_required" and r["reason"]=="no_blockable_card"
    assert "block_card" not in s.actions
