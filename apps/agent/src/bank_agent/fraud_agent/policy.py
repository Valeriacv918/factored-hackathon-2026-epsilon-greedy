"""Reglas de politica del flujo de fraude: 100% codigo, sin LLM.

Implementa, para el path de fraude, las reglas de docs/STATE_MACHINE2.md:
- DSP-004: disputa abierta duplicada para la misma transaccion.
- DSP-005: la transaccion es mas vieja que la ventana permitida.
- DSP-013: score > umbral, monto > umbral, o >= 2 cargos no disputados
  (denied) -> escalar al equipo de fraude, con prioridad P1 o P2.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..config.settings import FraudPolicy


@dataclass(frozen=True)
class PolicyDecision:
    rule_id: str
    outcome: str   # "duplicate" | "outside_window" | "ok"
    case_id: Optional[str] = None


def check_duplicate(existing_case_id: Optional[str]) -> Optional[PolicyDecision]:
    """DSP-004: ya existe una disputa abierta para esta transaccion."""
    if existing_case_id:
        return PolicyDecision("DSP-004", "duplicate", case_id=existing_case_id)
    return None


def check_window(transaction_date: date, today: date, policy: FraudPolicy) -> Optional[PolicyDecision]:
    """DSP-005: la transaccion es mas vieja que la ventana de disputa permitida."""
    if (today - transaction_date).days > policy.dispute_window_days:
        return PolicyDecision("DSP-005", "outside_window")
    return None


def evaluate_approved_transaction(
    transaction_date: date,
    today: date,
    existing_case_id: Optional[str],
    policy: FraudPolicy,
) -> PolicyDecision:
    """Orden DSP-004 -> DSP-005 -> ok, igual que la tabla de decision del doc."""
    dup = check_duplicate(existing_case_id)
    if dup:
        return dup
    window = check_window(transaction_date, today, policy)
    if window:
        return window
    return PolicyDecision("DSP-100", "ok")


def check_dsp013(
    max_fraud_score: float,
    max_amount_usd: float,
    denied_count: int,
    policy: FraudPolicy,
) -> bool:
    """Alguna senal fuerte de fraude a lo largo del caso -> escalar."""
    return (
        max_fraud_score > policy.fraud_score_threshold
        or max_amount_usd > policy.high_amount_usd_threshold
        or denied_count >= 2
    )


def dsp013_priority(max_fraud_score: float, denied_count: int, policy: FraudPolicy) -> str:
    """P1 si hay señal fuerte (score alto o >=2 negados); P2 si solo fue el monto."""
    if max_fraud_score > policy.fraud_score_threshold or denied_count >= 2:
        return "P1"
    return "P2"
