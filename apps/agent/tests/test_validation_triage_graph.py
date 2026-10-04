import datetime as dt
from types import SimpleNamespace
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from bank_agent.graphs.validation_triage import build_graph
from bank_agent.graphs.state import initial_state
from bank_agent.nodes.triage_agent.schemas import Understanding, Intent

class Services:
    def __init__(self):
        self.agents = {}
        self.auth = {}
        self.calls = []
        self.claim = False
        self.broken = False
        self.understanding = Understanding(intent=Intent.EMERGENCY, confidence=.9, wants_human=False)
    def now(self):
        return dt.datetime(2026,6,17,tzinfo=dt.timezone.utc)
    def validation_agent(self, cid):
        if cid not in self.agents:
            session = SimpleNamespace(session_id="sid-"+cid, language="es")
            def chat(text):
                self.calls.append(("verify", cid, text))
                if self.broken:
                    raise RuntimeError("unavailable")
                if text == "valid factors":
                    self.auth[session.session_id] = "CLI-ONE"
                return {"reply":"Proporciona tus datos.", "language":"es",
                        "authenticated":self.claim, "next_step":"ask_user"}
            self.agents[cid] = SimpleNamespace(session=session, chat=chat)
        return self.agents[cid]
    def validate_session(self, sid):
        return self.auth.get(sid)
    def triage_understand(self, text):
        self.calls.append(("triage",text))
        return self.understanding

def start(services, cid="one"):
    graph=build_graph(services, checkpointer=InMemorySaver())
    config={"configurable":{"thread_id":cid}}
    state=graph.invoke(initial_state(cid,"dev","Hola"),config)
    return graph,config,state

def authenticate(g,c):
    return g.invoke(Command(resume={"text":"valid factors"}),c)

def test_validation_waits_and_does_not_replay_model_call_on_resume():
    s=Services();g,c,state=start(s)
    assert state["__interrupt__"][0].value["kind"]=="validation_details"
    assert len(s.calls)==1
    state=authenticate(g,c)
    assert state["__interrupt__"][0].value["kind"]=="request_details"
    assert len(s.calls)==2
    assert state["customer_id"]=="CLI-ONE"
    state=g.invoke(Command(resume={"text":"Perdí mi tarjeta"}),c)
    assert state["outcome"]=="ready_for_card_emergency"
    assert not state["blocked_cards"]
    assert s.calls[-1]==("triage","Perdí mi tarjeta")
    assert len(s.calls)==3
    assert state["validation_input"]==""
    assert state["trace"][-1]["phase"]=="classify"

def test_model_claim_cannot_bypass_identity():
    s=Services();s.claim=True
    _,_,state=start(s)
    assert not state["authenticated"]
    assert state["__interrupt__"][0].value["kind"]=="validation_details"
    assert not any(x[0]=="triage" for x in s.calls)

def test_validation_error_is_not_success():
    s=Services();s.broken=True
    _,_,state=start(s)
    assert state["outcome"]=="service_unavailable"
    assert state["reason"]=="validation_unavailable"

def test_session_expiry_before_triage_prevents_classification():
    s=Services();g,c,_=start(s)
    authenticate(g,c);s.auth.clear()
    state=g.invoke(Command(resume={"text":"un cargo"}),c)
    assert state["outcome"]=="authentication_required"
    assert not any(x[0]=="triage" for x in s.calls)

def test_uncertain_triage_waits_then_routes_without_second_model_call():
    s=Services();s.understanding=Understanding(intent=Intent.OTHER, confidence=0, wants_human=False)
    g,c,_=start(s);authenticate(g,c)
    state=g.invoke(Command(resume={"text":"algo raro"}),c)
    assert state["__interrupt__"][0].value["kind"]=="clarify_intent"
    state=g.invoke(Command(resume={"choice":"charge_error"}),c)
    assert state["outcome"]=="ready_for_transaction_search"
    assert len([x for x in s.calls if x[0]=="triage"])==1

@pytest.mark.parametrize("intent,text,outcome", [
 (Intent.NOT_ME,"No reconozco una compra","ready_for_transaction_search"),
 (Intent.OTHER,"Quiero un asesor humano","human_requested"),
 (Intent.OTHER,"Quiero conocer el clima","out_of_scope"),
])
def test_destinations_are_explicit_and_do_not_execute_downstream(intent,text,outcome):
    s=Services();s.understanding=Understanding(intent=intent,confidence=.95,wants_human=False)
    g,c,_=start(s);authenticate(g,c)
    state=g.invoke(Command(resume={"text":text}),c)
    assert state["outcome"]==outcome
    assert not state["case_ids"] and not state["blocked_cards"]

def test_conversations_do_not_share_validation_sessions():
    s=Services();g,c,_=start(s,"one");authenticate(g,c)
    _,_,state=start(s,"two")
    assert state["__interrupt__"][0].value["kind"]=="validation_details"
    assert not state["authenticated"]
