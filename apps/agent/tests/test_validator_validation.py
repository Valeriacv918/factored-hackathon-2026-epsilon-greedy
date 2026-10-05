"""Tests del agente 1 con datos SINTÉTICOS (sin BigQuery ni LLM)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from bank_agent.nodes.validator_agent.agent import system_prompt
from bank_agent.nodes.validator_agent.language import detect_language
from bank_agent.clients.identity import (CustomerRecord, IdentityResult, InMemoryIdentityChecker, Product)
from bank_agent.nodes.validator_agent.validator import IdentityValidator, Status, normalize_document, parse_dob

# document_number -> registro con el customer_id interno (trazabilidad)
CUSTOMERS = {
    "1020304050": CustomerRecord("CLI-0001", date(1990, 4, 3), (
        Product("4111222233334444", "credit_card", "active"),
        Product("00987654321", "savings", "active"),
    )),
    "99887766": CustomerRecord("CLI-0002", date(1985, 12, 1), (
        Product("5500111122223333", "debit_card", "active"),
    )),
    "55555555": CustomerRecord("CLI-0003", None, ()),   # registro incompleto
}


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def env():
    clock = Clock()
    repo = InMemoryIdentityChecker(CUSTOMERS, clock=clock)
    v = IdentityValidator(repo, clock=clock)
    return v, v.new_session().session_id, clock, repo


# --- camino normal ---
def test_verified_with_any_product(env):
    v, sid, *_ = env
    r = v.verify(sid, "1.020.304.050", "03/04/1990", "0098 7654 321")   # 2º producto
    assert r.status == Status.VERIFIED and r.next_step == "triage"
    assert r.products_count == 2
    assert v.can_access_product(sid, "4111222233334444")


def test_iso_date_ok(env):
    v, sid, *_ = env
    assert v.verify(sid, "1020304050", "1990-04-03", "4111222233334444").status == Status.VERIFIED


# --- datos faltantes / formato ---
def test_missing_fields(env):
    v, sid, *_ = env
    r = v.verify(sid, "1020304050", None, None)
    assert r.status == Status.MISSING_FIELDS
    assert set(r.missing_fields) == {"date_of_birth", "product_number"}


def test_invalid_format_does_not_consume_attempt(env):
    v, sid, _, repo = env
    r = v.verify(sid, "1020304050", "31/02/1990", "4111222233334444")
    assert r.status == Status.INVALID_FORMAT
    # The server counts attempts; a typo never reaches it.
    assert repo.calls == 0 and v.get_session(sid).failed_attempts == 0


def test_future_dob_rejected():
    assert parse_dob("01/01/2099", today=date(2026, 10, 1)) is None


# --- datos incorrectos: mensaje genérico ---
@pytest.mark.parametrize("cid,dob,prod", [
    ("1020304050", "04/03/1990", "4111222233334444"),   # fecha mal (mes/día invertidos)
    ("1020304050", "03/04/1990", "5500111122223333"),   # producto de OTRO cliente
    ("0000000000", "03/04/1990", "4111222233334444"),   # cliente inexistente
    ("55555555", "01/01/1980", "12345678"),             # registro sin fecha en BD
])
def test_wrong_data_is_generic_failure(env, cid, dob, prod):
    v, sid, *_ = env
    r = v.verify(sid, cid, dob, prod)
    assert r.status == Status.FAILED
    assert r.for_llm()["products_count"] == 0


def test_lockout_after_3_and_handoff(env):
    v, sid, clock, repo = env
    for _ in range(2):
        assert v.verify(sid, "1020304050", "01/01/1991", "4111222233334444").status == Status.FAILED
    r = v.verify(sid, "1020304050", "01/01/1991", "4111222233334444")
    assert r.status == Status.LOCKED and r.next_step == "handoff_human"
    # incluso con datos correctos sigue bloqueado y NO consulta la BD
    calls = repo.calls
    assert v.verify(sid, "1020304050", "03/04/1990", "4111222233334444").status == Status.LOCKED
    assert repo.calls == calls
    clock.now += timedelta(minutes=16)
    assert v.verify(sid, "1020304050", "03/04/1990", "4111222233334444").status == Status.VERIFIED


# --- sesión expirada / acceso no autorizado ---
def test_session_expires(env):
    v, sid, clock, _ = env
    v.verify(sid, "1020304050", "03/04/1990", "4111222233334444")
    clock.now += timedelta(minutes=16)
    assert not v.is_authenticated(sid)
    assert not v.can_access_product(sid, "4111222233334444")


def test_cannot_access_other_customers_product(env):
    v, sid, *_ = env
    v.verify(sid, "1020304050", "03/04/1990", "4111222233334444")
    assert not v.can_access_product(sid, "5500111122223333")


def test_unauthenticated_has_no_access(env):
    v, sid, *_ = env
    assert not v.can_access_product(sid, "4111222233334444")


# --- fallo de herramienta ---
def test_identity_service_down_fails_safe():
    v = IdentityValidator(InMemoryIdentityChecker(CUSTOMERS, fail=True))
    sid = v.new_session().session_id
    r = v.verify(sid, "1020304050", "03/04/1990", "4111222233334444")
    assert r.status == Status.SERVICE_UNAVAILABLE and r.next_step == "handoff_human"
    assert not v.is_authenticated(sid)


# --- privacidad ---
def test_no_pii_in_llm_output_or_audit(env):
    v, sid, *_ = env
    r = v.verify(sid, "1020304050", "03/04/1990", "4111222233334444")
    blob = str(r.for_llm()) + str(v.get_session(sid).audit)
    for secret in ("1020304050", "1990", "4111222233334444"):
        assert secret not in blob


# --- idioma ---
@pytest.mark.parametrize("text,lang", [
    ("Hola, necesito ayuda con mi tarjeta de crédito por favor", "es"),
    ("Olá, preciso de ajuda com o meu cartão de crédito, por favor", "pt"),
    ("Não reconheço uma compra que apareceu na minha fatura", "pt"),
    ("Quiero bloquear mi tarjeta porque me la robaron", "es"),
    ("Hola necesito ayuda con mi credito hipotecario", "es"),
])
def test_language_detection(text, lang):
    assert detect_language(text).language == lang


def test_short_text_keeps_previous_language():
    r = detect_language("sim", previous="pt")
    assert r.language == "pt" and r.source == "sticky"


def test_short_text_without_history_is_ambiguous():
    assert detect_language("ok").ambiguous


# El cliente contesta "¿español o portugués?" con una palabra: esa elección manda,
# aunque sea un texto corto que el detector no puede juzgar.
@pytest.mark.parametrize("text,previous,lang", [
    ("español", "pt", "es"),
    ("Español", None, "es"),
    ("espanol", "pt", "es"),
    ("en español", "pt", "es"),
    ("castellano", "pt", "es"),
    ("espanhol", "pt", "es"),
    ("portugués", "es", "pt"),
    ("português", "es", "pt"),
    ("Portugues", None, "pt"),
    ("em português", "es", "pt"),
    ("pt", "es", "pt"),
])
def test_explicit_short_choice_wins(text, previous, lang):
    r = detect_language(text, previous=previous)
    assert (r.language, r.ambiguous, r.source) == (lang, False, "choice")


def test_naming_both_languages_is_not_a_choice():
    assert detect_language("español o portugués", previous="pt").source != "choice"
    assert detect_language("es o pt").ambiguous


def test_low_confidence_guess_is_not_stored_as_the_language():
    # Primer mensaje real de un log: lingua lo creía portugués con baja confianza.
    r = detect_language("uv run --project apps/agent scripts/run_disputes.py --session dev --flow fraud --debug")
    assert r.ambiguous and r.language == "es"


def test_ambiguous_prompt_asks_in_both_languages():
    prompt = system_prompt("es", ambiguous=True)
    assert "español" in prompt and "portugués" in prompt and "prefiere" in prompt
    assert "otro idioma" in prompt          # explains that only es/pt are supported
    assert "Responde SIEMPRE en español." not in prompt


def test_known_language_prompt_uses_only_that_language():
    prompt = system_prompt("pt", ambiguous=False)
    assert "Responde SIEMPRE en portugués de Brasil." in prompt
    assert "prefiere" not in prompt


# --- verificación en el servidor MCP ---
class LockedByServer:
    """El servidor ya bloqueó al cliente (p. ej. intentos desde otra conversación)."""
    def verify(self, document_number, date_of_birth, product_number):
        return IdentityResult("locked")


def test_server_lockout_locks_this_conversation_too():
    v = IdentityValidator(LockedByServer())
    sid = v.new_session().session_id
    r = v.verify(sid, "1020304050", "03/04/1990", "4111222233334444")
    assert r.status == Status.LOCKED and r.next_step == "handoff_human"


def test_session_keeps_server_token_and_products():
    v = IdentityValidator(InMemoryIdentityChecker(CUSTOMERS))
    sid = v.new_session().session_id
    v.verify(sid, "1020304050", "03/04/1990", "4111222233334444")
    s = v.get_session(sid)
    assert s.customer_id == "CLI-0001"           # el cliente escribió su documento; se guarda su ID interno
    assert s.session_token == "test-token:CLI-0001"
    assert s.authorized_products == ("4111222233334444", "00987654321")


@pytest.mark.parametrize("raw,expected", [("1.020.304.050", "1020304050"), ("1020-304-050", "1020304050"),
                                          (" 99887766 ", "99887766"), ("gomp800101hdfrrn09", "GOMP800101HDFRRN09"),
                                          ("AB", None), ("1020_304", None), ("1" * 21, None)])
def test_normalize_document(raw, expected):
    assert normalize_document(raw) == expected


# --- los límites son del servidor ---
def test_attempts_and_lockout_come_from_the_server():
    clock = Clock()
    server = InMemoryIdentityChecker(CUSTOMERS, clock=clock, max_attempts=5, lockout=timedelta(minutes=40))
    v = IdentityValidator(server, clock=clock)
    sid = v.new_session().session_id
    lefts = [v.verify(sid, "1020304050", "01/01/1991", "4111222233334444").attempts_left for _ in range(4)]
    assert lefts == [4, 3, 2, 1]
    assert v.verify(sid, "1020304050", "01/01/1991", "4111222233334444").status == Status.LOCKED
    assert v.get_session(sid).locked_until == clock.now + timedelta(minutes=40)


def test_session_lifetime_comes_from_the_server():
    clock = Clock()
    v = IdentityValidator(InMemoryIdentityChecker(CUSTOMERS, clock=clock, ttl=timedelta(minutes=5)), clock=clock)
    sid = v.new_session().session_id
    v.verify(sid, "1020304050", "03/04/1990", "4111222233334444")
    clock.now += timedelta(minutes=4, seconds=59)
    assert v.is_authenticated(sid)
    clock.now += timedelta(seconds=1)
    assert not v.is_authenticated(sid)


def test_lockout_is_per_customer_across_conversations():
    clock = Clock()
    v = IdentityValidator(InMemoryIdentityChecker(CUSTOMERS, clock=clock), clock=clock)
    first = v.new_session().session_id
    for _ in range(3):
        v.verify(first, "1020304050", "01/01/1991", "4111222233334444")
    # A new conversation for the same customer is locked too, even with the right answer.
    second = v.new_session().session_id
    assert v.verify(second, "1020304050", "03/04/1990", "4111222233334444").status == Status.LOCKED
    # Another customer is not affected.
    third = v.new_session().session_id
    assert v.verify(third, "99887766", "01/12/1985", "5500111122223333").status == Status.VERIFIED
