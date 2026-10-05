from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from bank_agent.graphs.validation_triage import build_graph
from bank_agent.graphs.state import initial_state
from bank_agent.clients.mcp_services import detect_language_lingua
from bank_agent.web.app import present
from test_validation_triage_graph import Services, VALID_FORM


def start(text):
    s = Services()
    s.detect_language = detect_language_lingua
    g = build_graph(s, checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "language-test"}}
    result = g.invoke(initial_state("language-test", "", text), cfg)
    return s, g, cfg, result


def question(result):
    return result["__interrupt__"][0].value


def test_portuguese_is_detected_and_survives_identity_form():
    s, g, cfg, result = start("Olá, preciso de ajuda porque perdi meu cartão de crédito.")
    q = question(result)
    assert q["kind"] == "identity_form" and q["language"] == "pt"
    assert "verificar sua identidade" in q["message"]
    view, _ = present(q)
    assert view["form"][0]["label"] == "Número do documento"
    result = g.invoke(Command(resume=VALID_FORM), cfg)
    q = question(result)
    assert q["language"] == "pt" and q["message"] == "Identidade verificada. Como posso ajudar?"
    assert len(s.calls) == 1


def test_short_ambiguous_greeting_requests_language_before_identity():
    s, g, cfg, result = start("Oi")
    assert question(result)["kind"] == "language"
    assert question(result)["options"] == ["es", "pt"]
    assert not s.calls
    result = g.invoke(Command(resume={"choice": "pt"}), cfg)
    assert question(result)["kind"] == "identity_form"
    assert question(result)["language"] == "pt"
    assert not s.calls


def test_spanish_and_validation_failure_keep_language():
    s, g, cfg, result = start("Necesito consultar un cargo en mi tarjeta de crédito.")
    assert question(result)["language"] == "es"
    s.broken = True
    result = g.invoke(Command(resume=VALID_FORM), cfg)
    assert result["response"] == "La validación no está disponible. No se consultarán tus productos."


def test_portuguese_validation_failure_is_translated():
    s, g, cfg, result = start("Preciso consultar uma transação no meu cartão.")
    s.broken = True
    result = g.invoke(Command(resume=VALID_FORM), cfg)
    assert result["language"] == "pt"
    assert result["response"] == "A validação não está disponível. Seus produtos não serão consultados."
