"""WRITE_NARRATIVE + claim check (docs/state-machine.md, sección 5). 100% código salvo la llamada al modelo.

1. build_facts: arma los HECHOS VERIFICADOS desde el estado. Es lo único que ve el LLM:
   nunca el mensaje del cliente (puede traer instrucciones) ni su customer_id.
2. services.write_narrative: el LLM redacta 2-3 oraciones para el empleado.
3. claim_check: revisa que cada ID, fecha, número y acción del texto esté en los hechos,
   y que no prometa nada. Si algo no cuadra, se usa template_narrative (también desde los hechos).
"""
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from bank_agent.clients.contracts import ServiceFailure
from bank_agent.observability import log_event
from bank_agent.prompts.handoff import QUEUES, REASONS

MAX_CHARS = 600
MAX_SENTENCES = 3
TX_FIELDS = ("id", "merchant", "amount", "currency", "date", "status", "fraud_score")

# Palabras con al menos un dígito que empiezan con letra: tx-1, CASE-9, DSP-013, P1, card_42.
ID_RE = re.compile(r"\b(?=[\w-]*\d)[A-Za-z][\w-]*\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")
NEGATION_RE = re.compile(r"\b(no|nao|sin|sem|nunca|rechazo|recusou)\b")

# Se busca sobre el texto en minúsculas y sin tildes.
PROMISES = [
    r"reembols", r"estorn", r"ressarc", r"garantiz", r"garanti",
    r"devolveremos", r"devolvera", r"vamos a devolver", r"vai devolver", r"sera devolvid",
    r"\b(en|em|dentro de) \d+ (dias|horas|semanas)",
]
BLOCK_CLAIMS = [r"bloquead[ao]s?", r"bloqueo verificado", r"bloqueio verificado", r"se bloqueo",
                r"foi bloquead", r"foram bloquead"]
SUSPEND_CLAIMS = [r"suspendid[ao]s?", r"suspensa?s?", r"suspension verificada", r"suspensao verificada",
                  r"se suspendio", r"foi suspens", r"foram suspens"]
CASE_CLAIMS = [r"(disputa|caso|contestacao) (fue |foi )?(registrad|cread|abiert|abert)",
               r"se (registro|creo|abrio) (la |una |el |un )?(disputa|caso)",
               r"(registrou|abriu) (a |uma )?contestacao"]


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _decimal(value):
    try:
        number = Decimal(str(value).replace(",", "."))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def build_facts(s, policy) -> dict:
    """Hechos verificados del caso. Solo datos que el código ya comprobó."""
    language = s.get("language", "es")
    reason = s["reason"]
    es, pt = REASONS.get(reason, (reason, reason))
    txs = {t["id"]: t for t in s.get("risk_transactions", [])}
    if s.get("transaction"):
        txs[s["transaction"]["id"]] = s["transaction"]
    transactions = []
    for t in txs.values():
        row = {k: t[k] for k in TX_FIELDS if t.get(k) is not None}
        if "date" in row:
            row["date"] = str(row["date"])[:10]   # YYYY-MM-DD: la hora no le aporta al empleado
        transactions.append(row)
    facts = {
        "reason": reason,
        "reason_text": pt if language == "pt" else es,
        "queue": s["queue"],
        "priority": s["priority"],
        "transactions": transactions,
        "blocked_cards": list(s.get("blocked_cards", [])),
        "suspended_accounts": list(s.get("suspended_accounts", [])),
        "case_ids": list(s.get("case_ids", [])),
        "policy": {"fraud_score": str(policy.fraud_score), "high_amount_usd": str(policy.high_amount_usd),
                   "window_days": policy.window_days},
    }
    for key in ("policy_rule", "explanation_rule"):
        if s.get(key):
            facts[key] = s[key]
    return facts


def template_narrative(facts: dict, language: str) -> str:
    """Respaldo seguro: solo copia hechos. Siempre pasa el claim check (hay un test)."""
    pt = language == "pt"
    queue = QUEUES.get(facts["queue"], (facts["queue"], facts["queue"]))[1 if pt else 0]
    txs = ", ".join(
        f"{t['id']} ({' '.join(str(t[k]) for k in ('merchant', 'amount', 'currency', 'date', 'status') if k in t)})"
        for t in facts["transactions"]) or "—"
    blocked = ", ".join(facts["blocked_cards"]) or "—"
    suspended = ", ".join(facts.get("suspended_accounts", []))
    cases = ", ".join(facts["case_ids"]) or "—"
    if pt:
        suspended_clause = f" contas com transações suspensas: {suspended};" if suspended else ""
        return (f"Encaminhado para a fila {queue} com prioridade {facts['priority']}: {facts['reason_text']}. "
                f"Cobranças: {txs}; cartões bloqueados: {blocked};{suspended_clause} casos: {cases}.")
    suspended_clause = f" cuentas con transacciones suspendidas: {suspended};" if suspended else ""
    return (f"Escalado a la cola {queue} con prioridad {facts['priority']}: {facts['reason_text']}. "
            f"Cargos: {txs}; tarjetas bloqueadas: {blocked};{suspended_clause} casos: {cases}.")


def _claims(patterns, plain: str) -> bool:
    """True si el texto AFIRMA la acción (ignora 'no fue bloqueada', 'rechazó el bloqueo')."""
    for pattern in patterns:
        for match in re.finditer(pattern, plain):
            if not NEGATION_RE.search(plain[max(0, match.start() - 25):match.start()]):
                return True
    return False


def claim_check(text: str, facts: dict) -> list[str]:
    """Problemas encontrados en la narrativa. Lista vacía = se puede usar."""
    issues = []
    text = (text or "").strip()
    if not text:
        return ["empty"]
    if len(text) > MAX_CHARS:
        issues.append("too_long")
    if len(SENTENCE_END_RE.findall(text + " ")) > MAX_SENTENCES:
        issues.append("too_many_sentences")

    txs = facts["transactions"]
    suspended_accounts = facts.get("suspended_accounts", [])
    merchant_tokens = {w for t in txs for w in re.findall(r"[\w-]+", str(t.get("merchant", "")))}
    allowed_ids = ({t["id"] for t in txs} | set(facts["case_ids"]) | set(facts["blocked_cards"])
                   | set(suspended_accounts)
                   | {facts["reason"], facts["priority"], facts.get("policy_rule"), facts.get("explanation_rule")}
                   | merchant_tokens) - {None}
    allowed_dates = {t["date"] for t in txs if "date" in t}
    allowed_numbers = {n for n in (
        [_decimal(t.get(k)) for t in txs for k in ("amount", "fraud_score")]
        + [_decimal(v) for v in facts["policy"].values()]
        + [Decimal(len(txs)), Decimal(len(facts["case_ids"])), Decimal(len(facts["blocked_cards"])),
           Decimal(len(suspended_accounts))]
        + [_decimal(n) for w in merchant_tokens for n in NUMBER_RE.findall(w)]
    ) if n is not None}

    rest = text
    for token in ID_RE.findall(text):
        if token not in allowed_ids:
            issues.append(f"unknown_id:{token}")
    rest = ID_RE.sub(" ", rest)
    for date in DATE_RE.findall(rest):
        if date not in allowed_dates:
            issues.append(f"unknown_date:{date}")
    rest = DATE_RE.sub(" ", rest)
    for raw in NUMBER_RE.findall(rest):
        if _decimal(raw) not in allowed_numbers:
            issues.append(f"unknown_number:{raw}")

    plain = _plain(text)
    if any(re.search(p, plain) for p in PROMISES):
        issues.append("promise")
    if not facts["blocked_cards"] and _claims(BLOCK_CLAIMS, plain):
        issues.append("unverified_block")
    if not suspended_accounts and _claims(SUSPEND_CLAIMS, plain):
        issues.append("unverified_suspension")
    if not facts["case_ids"] and _claims(CASE_CLAIMS, plain):
        issues.append("unverified_case")
    return issues


def write_narrative(services, facts: dict, language: str) -> tuple[str, str, list[str]]:
    """(narrativa, origen "llm" | "template", problemas del claim check)."""
    fallback = template_narrative(facts, language)
    try:
        draft = services.write_narrative(facts, language)
    except ServiceFailure:
        log_event("narrative.fallback", issues=["model_unavailable"])
        return fallback, "template", ["model_unavailable"]
    issues = claim_check(draft, facts)
    if issues:
        log_event("narrative.fallback", issues=issues)
        return fallback, "template", issues
    return draft.strip(), "llm", []