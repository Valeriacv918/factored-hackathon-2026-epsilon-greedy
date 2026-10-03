"""Services.understand backed by an LLM with structured output.

The model only extracts intent and slots; the graph decides what happens next.
Slots mirror the MCP find_transactions `slots` argument
(contracts/mcp/find_transactions.json); tests guard against drift.
"""
import datetime as dt
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from bank_agent.clients.contracts import ServiceFailure
from bank_agent.prompts.understanding import UNDERSTANDING_PROMPT

LANGUAGE_NAMES = {"es": "Spanish", "pt": "Portuguese", "en": "English"}


class Slots(BaseModel):
    date: dt.date | None = Field(None, description="Exact transaction date, YYYY-MM-DD.")
    date_from: dt.date | None = Field(None, description="Start of a date range, YYYY-MM-DD.")
    date_to: dt.date | None = Field(None, description="End of a date range, YYYY-MM-DD.")
    amount: str | None = Field(None, pattern=r"^\d+(\.\d{1,2})?$", description='Amount as text, e.g. "329.60".')
    merchant: str | None = Field(None, max_length=100, description="Merchant name as the customer wrote it.")
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$", description="ISO 4217 code, only if stated.")

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, v):
        # "329,60" (es/pt decimal comma), "$ 329.60" -> "329.60"
        if isinstance(v, (int, float)):
            v = str(v)
        if isinstance(v, str):
            v = v.strip().lstrip("$€R").strip()
            if "," in v and "." not in v:
                v = v.replace(",", ".")
        return v

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, v):
        return v.strip().upper() if isinstance(v, str) else v


class Extraction(BaseModel):
    intent: Literal["not_me", "charge_error", "card_emergency", "other"]
    confidence: float = Field(ge=0, le=1)
    slots: Slots = Field(default_factory=Slots)
    wants_human: bool = False


class LlmUnderstanding:
    def __init__(self, model, clock: Callable[[], dt.datetime]):
        """`model` is a runnable whose invoke(messages) returns an Extraction (or its dict)."""
        self._model, self._clock = model, clock

    @classmethod
    def from_model_id(cls, model_id: str, clock: Callable[[], dt.datetime]) -> "LlmUnderstanding":
        from langchain.chat_models import init_chat_model
        return cls(init_chat_model(model_id, temperature=0).with_structured_output(Extraction), clock)

    def understand(self, text: str, language: str) -> dict[str, Any]:
        system = UNDERSTANDING_PROMPT.format(language=LANGUAGE_NAMES.get(language, "unknown"),
                                             today=self._clock().date().isoformat())
        try:
            out = self._model.invoke([("system", system), ("user", text)])
            extraction = out if isinstance(out, Extraction) else Extraction.model_validate(out)
        except ValidationError as exc:
            raise ServiceFailure("Invalid extraction schema") from exc
        except Exception as exc:  # provider, network, rate limit
            raise ServiceFailure("Understanding unavailable") from exc
        return {"intent": extraction.intent, "confidence": extraction.confidence,
                "slots": extraction.slots.model_dump(mode="json", exclude_none=True),
                "wants_human": extraction.wants_human}
