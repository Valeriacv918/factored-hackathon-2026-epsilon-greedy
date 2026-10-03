import datetime as dt
import json
from pathlib import Path

import pytest

from bank_agent.clients.contracts import ServiceFailure
from bank_agent.clients.understanding import Extraction, LlmUnderstanding, Slots

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "mcp" / "find_transactions.json"
NOW = dt.datetime(2026, 6, 18, 12, tzinfo=dt.timezone.utc)


class StubModel:
    def __init__(self, out):
        self.out, self.messages = out, None

    def invoke(self, messages):
        self.messages = messages
        if isinstance(self.out, Exception):
            raise self.out
        return self.out


def test_slots_match_mcp_contract():
    schema = json.loads(CONTRACT.read_text(encoding="utf-8"))["input_schema"]
    assert set(Slots.model_fields) == set(schema["$defs"]["TransactionSlots"]["properties"])


def test_extraction_returns_graph_shape_and_prompt_has_scenario_date():
    model = StubModel(Extraction(intent="not_me", confidence=0.9,
                                 slots=Slots(date="2026-06-11", amount="329,60", currency="usd")))
    out = LlmUnderstanding(model, lambda: NOW).understand("No reconozco 329,60 del 11 de junio", "es")
    assert out == {"intent": "not_me", "confidence": 0.9, "wants_human": False,
                   "slots": {"date": "2026-06-11", "amount": "329.60", "currency": "USD"}}
    assert "2026-06-18" in model.messages[0][1] and "Spanish" in model.messages[0][1]


def test_dict_output_is_validated():
    out = LlmUnderstanding(StubModel({"intent": "card_emergency", "confidence": 1}), lambda: NOW).understand("x", "pt")
    assert out["intent"] == "card_emergency" and out["slots"] == {}


@pytest.mark.parametrize("out", [{"intent": "transfer_money", "confidence": 0.9},
                                 {"intent": "not_me", "confidence": 3},
                                 {"intent": "not_me", "confidence": 0.9, "slots": {"amount": "lots"}},
                                 RuntimeError("provider down")])
def test_invalid_or_failed_extraction_is_service_failure(out):
    with pytest.raises(ServiceFailure):
        LlmUnderstanding(StubModel(out), lambda: NOW).understand("x", "es")
