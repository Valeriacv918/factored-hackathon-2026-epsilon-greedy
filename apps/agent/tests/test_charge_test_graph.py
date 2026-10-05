from copy import deepcopy
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from test_validation_triage_graph import Services, VALID_FORM
from bank_agent.graphs.validation_triage import build_graph
from bank_agent.graphs.state import initial_state
from bank_agent.nodes.triage_agent.schemas import Understanding, Intent

TX=dict(id="TX-1",customer_id="CLI-ONE",status="Reversed",fraud_score="1",
        amount="20",currency="USD",date="2026-06-10",merchant="Shop")

class ChargeServices(Services):
    def __init__(self,tx=None):
        super().__init__()
        self.understanding=Understanding(intent=Intent.CHARGE_ERROR,confidence=.99,wants_human=False)
        self.tx=deepcopy(tx or TX); self.queries=0; self.empty=False; self.saves=0; self.bad_receipt=False
    def understand(self,text,language):
        return {"intent":"charge_error","slots":{"date":"2026-06-10"}}
    def tool(self,name,**kwargs):
        if name=="save_charge_explanation":
            self.saves+=1
            return dict(result_id="saved", verified=not self.bad_receipt,
                transaction_id=self.tx["id"], observed_status=self.tx["status"],
                rule_id={"Pending":"EXP-002","Reversed":"EXP-003","Declined":"EXP-006"}[self.tx["status"]])
        assert name=="find_transactions"
        assert kwargs["arguments"]["window_days"]==90
        assert kwargs["customer_id"]=="CLI-ONE"
        self.queries+=1
        return {"transactions":[] if self.empty else [self.tx],"has_more":False}

def start(s):
    g=build_graph(s,checkpointer=InMemorySaver(),test_charge_error=True)
    c={"configurable":{"thread_id":"one"}}
    g.invoke(initial_state("one","","Hola"),c)
    g.invoke(Command(resume=VALID_FORM),c)
    r=g.invoke(Command(resume={"text":"Me cobraron dos veces una compra."}),c)
    return g,c,r

@pytest.mark.parametrize("status",["Reversed","Pending","Declined"])
def test_explanation_and_selection_do_not_requery(status):
    s=ChargeServices({**TX,"status":status});g,c,r=start(s)
    assert r["__interrupt__"][0].value["kind"]=="select_transaction"
    r=g.invoke(Command(resume={"choice":"TX-1"}),c)
    assert r["outcome"]=="explained" and s.queries==1 and s.saves==1
    assert r["explanation_result_id"]=="saved"

def test_approved_ends_without_saving():
    s=ChargeServices({**TX,"status":"Approved"})
    g,c,_=start(s)
    r=g.invoke(Command(resume={"choice":"TX-1"}),c)
    assert r["outcome"]=="approved" and not r["case_ids"] and s.saves==0

def test_high_risk_does_not_run_fraud():
    g,c,_=start(ChargeServices({**TX,"fraud_score":"90"}))
    r=g.invoke(Command(resume={"choice":"TX-1"}),c)
    assert r["outcome"]=="ready_for_fraud"
    assert not any(t["node"]=="fraud_agent" for t in r["trace"])

def test_expiry_after_selection_pause():
    s=ChargeServices();g,c,_=start(s);s.auth.clear()
    r=g.invoke(Command(resume={"choice":"TX-1"}),c)
    assert r["outcome"]=="authentication_required" and s.queries==1

def test_cross_customer_rejected():
    _,_,r=start(ChargeServices({**TX,"customer_id":"OTHER"}))
    assert r["outcome"]=="service_unavailable"

def test_no_matches_has_bounded_clarification():
    s=ChargeServices();s.empty=True;g,c,r=start(s)
    for _ in range(2):
        assert r["__interrupt__"][0].value["kind"]=="transaction_details"
        r=g.invoke(Command(resume={"text":"El 10 de junio por 20 USD."}),c)
    assert r["outcome"]=="transaction_unresolved" and s.queries==3

def test_unverified_save_never_reports_success():
    s=ChargeServices();s.bad_receipt=True
    g,c,_=start(s)
    r=g.invoke(Command(resume={"choice":"TX-1"}),c)
    assert r["outcome"]=="service_unavailable"
    assert not r.get("explanation_result_id")

def test_missing_merchant_is_selectable_and_saved():
    s=ChargeServices({**TX,"merchant":None});g,c,r=start(s)
    shown=r["__interrupt__"][0].value["transactions"][0]
    assert shown["merchant"]=="Sin comercio informado"
    r=g.invoke(Command(resume={"choice":"TX-1"}),c)
    assert r["outcome"]=="explained" and s.saves==1

def test_clarification_says_merchant_is_optional():
    s=ChargeServices();s.empty=True
    _,_,r=start(s)
    assert "comercio es opcional" in r["__interrupt__"][0].value["message"]
    assert r["reason"]=="no_matches"

def test_selection_displays_local_calendar_date():
    s=ChargeServices({**TX,"date":"2024-11-20T00:25:57+00:00",
                      "local_date":"2024-11-19","customer_timezone":"America/Bogota"})
    _,_,r=start(s)
    shown=r["__interrupt__"][0].value["transactions"][0]
    assert shown["date"]=="2024-11-19" and shown["timezone"]=="America/Bogota"
