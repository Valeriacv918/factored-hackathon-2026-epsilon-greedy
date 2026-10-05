import datetime as dt
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from bank_agent.graphs.validation_triage import build_graph
from bank_agent.graphs.state import initial_state
from bank_agent.nodes.triage_agent.schemas import Understanding, Intent

# Login form: the three factors, each in its own field (no LLM involved).
VALID_FORM = {"document_number": "1020304050", "date_of_birth": "1990-04-03", "product_number": "4111222233334444"}
WRONG_FORM = {**VALID_FORM, "date_of_birth": "1991-01-01"}

class Services:
    def __init__(self):
        self.auth = {}
        self.calls = []
        self.broken = False
        self.locked = False
        self.failures = 0
        self.understanding = Understanding(intent=Intent.EMERGENCY, confidence=.9, wants_human=False)
    def now(self):
        return dt.datetime(2026,6,17,tzinfo=dt.timezone.utc)
    def verify_identity(self, cid, document_number, date_of_birth, product_number):
        """Same answers as IdentityValidator: status + opaque session_ref, never customer data."""
        self.calls.append(("verify", cid))
        if self.broken:
            raise RuntimeError("unavailable")
        sid = "sid-" + cid
        if self.locked:
            return {"status": "LOCKED", "attempts_left": None, "missing_fields": [], "session_ref": sid}
        if {"document_number": document_number, "date_of_birth": date_of_birth, "product_number": product_number} == VALID_FORM:
            self.auth[sid] = "CLI-ONE"
            return {"status": "VERIFIED", "attempts_left": None, "missing_fields": [], "session_ref": sid}
        self.failures += 1
        return {"status": "FAILED", "attempts_left": 3 - self.failures, "missing_fields": [], "session_ref": sid}
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
    return g.invoke(Command(resume=VALID_FORM),c)

def test_validation_waits_and_does_not_replay_model_call_on_resume():
    s=Services();g,c,state=start(s)
    form=state["__interrupt__"][0].value
    assert form["kind"]=="identity_form" and form["fields"]==["document_number","date_of_birth","product_number"]
    assert len(s.calls)==0                       # nothing is verified or classified before the form
    state=authenticate(g,c)
    assert state["__interrupt__"][0].value["kind"]=="request_details"
    assert len(s.calls)==1                       # one verification per submitted form
    assert state["customer_id"]=="CLI-ONE"
    state=g.invoke(Command(resume={"text":"Perdí mi tarjeta"}),c)
    assert state["outcome"]=="ready_for_card_emergency"
    assert not state["blocked_cards"]
    assert s.calls[-1]==("triage","Perdí mi tarjeta")
    assert len(s.calls)==2
    assert state["validation_input"]==""
    assert state["trace"][-1]["phase"]=="classify"

def test_free_text_cannot_authenticate():
    """Only the three form fields are accepted: a chat message with the factors is rejected."""
    s=Services();g,c,state=start(s)
    assert not state["authenticated"]
    with pytest.raises(ValueError):
        g.invoke(Command(resume={"text":"1020304050 1990-04-03 4111222233334444"}),c)
    assert not any(x[0] in {"verify","triage"} for x in s.calls)

def test_first_message_is_never_classified():
    s=Services();g=build_graph(s, checkpointer=InMemorySaver());c={"configurable":{"thread_id":"one"}}
    g.invoke(initial_state("one","dev","Mi documento es 1020304050, perdí mi tarjeta"),c)
    state=authenticate(g,c)
    assert state["message"]=="" and not any(x[0]=="triage" for x in s.calls)

def test_wrong_data_shows_the_form_again_with_attempts_left():
    s=Services();g,c,_=start(s)
    state=g.invoke(Command(resume=WRONG_FORM),c)
    form=state["__interrupt__"][0].value
    assert form["kind"]=="identity_form" and "Te quedan 2 intentos" in form["message"]
    assert not state["authenticated"]
    state=authenticate(g,c)
    assert state["__interrupt__"][0].value["kind"]=="request_details"

def test_locked_identity_needs_a_human():
    s=Services();s.locked=True;g,c,_=start(s)
    state=authenticate(g,c)
    assert (state["outcome"],state["reason"])==("human_required","LOCKED") and not state["authenticated"]

def test_validation_error_is_not_success():
    s=Services();s.broken=True;g,c,_=start(s)
    state=authenticate(g,c)
    assert state["outcome"]=="service_unavailable"
    assert state["reason"]=="validation_unavailable"
    assert not state["authenticated"]

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
    assert state["__interrupt__"][0].value["kind"]=="identity_form"
    assert not state["authenticated"]
