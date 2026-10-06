"""follow_up=True (web): offer another request after a resolved outcome; every close says goodbye."""
from langgraph.types import Command

from test_card_emergency_test_graph import NO, YES, EmergencyServices, kind, start

GOODBYE = "Gracias por comunicarte con nosotros. ¡Hasta pronto!"
THANKS = "Gracias por comunicarte. ¡Que tengas un buen día!"


def blocked(**flags):
    """Block the only card and say there is no unrecognized charge -> card_blocked."""
    s = EmergencyServices(); g, c, _ = start(s, follow_up=True, **flags)
    g.invoke(Command(resume=YES), c)
    return s, g, c, g.invoke(Command(resume=NO), c)


def test_resolved_block_offers_follow_up_then_closes_with_thanks():
    s, g, c, r = blocked()
    question = r["__interrupt__"][0].value
    assert question["kind"] == "follow_up" and question["options"] == ["yes", "no"]
    assert question["resolved"]["outcome"] == "card_blocked"
    assert question["resolved"]["response"].startswith("Listo: tu tarjeta quedó bloqueada")
    r = g.invoke(Command(resume=NO), c)
    assert "__interrupt__" not in r
    assert (r["outcome"], r["response"]) == ("card_blocked", THANKS)          # a single goodbye
    assert "create_handoff" not in s.actions


def test_yes_starts_a_new_request_without_logging_in_again():
    s, g, c, _ = blocked()
    r = g.invoke(Command(resume=YES), c)
    question = r["__interrupt__"][0].value
    assert (question["kind"], question["message"]) == ("request_details", "Cuéntame qué más necesitas.")
    assert r["requests"] == 2 and r["skipped_cards"] == [] and r["outcome"] is None and r["turns"] == 1
    r = g.invoke(Command(resume={"text": "Perdí mi tarjeta"}), c)
    assert kind(r) == "unrecognized_charge"                                   # already blocked: no re-confirm
    assert s.actions.count("block_card") == 1 and r["blocked_cards"] == ["CARD-1"]


def test_after_max_requests_a_resolved_outcome_ends_with_goodbye():
    s, g, c, _ = blocked()
    for _ in range(2):
        g.invoke(Command(resume=YES), c)
        g.invoke(Command(resume={"text": "Perdí mi tarjeta"}), c)
        r = g.invoke(Command(resume=NO), c)
    assert "__interrupt__" not in r and r["requests"] == 3
    assert r["outcome"] == "card_blocked" and r["response"].endswith(GOODBYE)


def test_escalated_outcome_skips_follow_up_and_says_goodbye_once():
    s = EmergencyServices(); g, c, _ = start(s, follow_up=True)
    r = g.invoke(Command(resume=NO), c)                                       # decline the block
    assert "__interrupt__" not in r
    assert (r["outcome"], r["reason"]) == ("human_required", "block_declined")
    assert r["response"].endswith(GOODBYE) and r["response"].count(GOODBYE) == 1


def test_session_expired_at_follow_up_requires_login_and_says_goodbye():
    s, g, c, _ = blocked(); s.auth.clear()
    r = g.invoke(Command(resume=YES), c)
    assert r["outcome"] == "authentication_required" and not r["authenticated"]
    assert r["response"].endswith(GOODBYE)


def test_without_the_flag_resolved_outcomes_still_end():
    s = EmergencyServices(); g, c, _ = start(s)
    g.invoke(Command(resume=YES), c)
    r = g.invoke(Command(resume=NO), c)
    assert "__interrupt__" not in r and r["outcome"] == "card_blocked" and GOODBYE not in r["response"]
