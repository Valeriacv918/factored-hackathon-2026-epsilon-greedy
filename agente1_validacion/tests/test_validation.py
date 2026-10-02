"""Tests del agente 1 con datos SINTÉTICOS (sin BigQuery ni LLM)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from validation_agent.language import detect_language
from validation_agent.repository import (CustomerRecord, InMemoryCustomerRepository, Product)
from validation_agent.validator import IdentityValidator, Status, parse_dob

CUSTOMERS = {
    "1020304050": CustomerRecord("1020304050", date(1990, 4, 3), (
        Product("4111222233334444", "credit_card", "active"),
        Product("00987654321", "savings", "active"),
    )),
    "99887766": CustomerRecord("99887766", date(1985, 12, 1), (
        Product("5500111122223333", "debit_card", "active"),
    )),
    "55555555": CustomerRecord("55555555", None, ()),   # registro incompleto
}


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def env():
    clock = Clock()
    repo = InMemoryCustomerRepository(CUSTOMERS)
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
    v, sid, *_ = env
    r = v.verify(sid, "1020304050", "31/02/1990", "4111222233334444")
    assert r.status == Status.INVALID_FORMAT
    assert v.get_session(sid).failed_attempts == 0


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
def test_bigquery_down_fails_safe():
    v = IdentityValidator(InMemoryCustomerRepository(CUSTOMERS, fail=True))
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
