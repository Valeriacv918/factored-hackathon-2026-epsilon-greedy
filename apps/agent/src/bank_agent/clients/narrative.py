"""Services.write_narrative backed by an LLM with structured output.

The model only writes; it receives the verified facts built by the escalation node
and nothing else. nodes/escalation/handoff.py checks every claim before using it.
"""
import json
from typing import Any

from pydantic import BaseModel, Field

from bank_agent.clients.contracts import ServiceFailure
from bank_agent.prompts.handoff import HANDOFF_PROMPT, LANGUAGE_NAMES


class Narrative(BaseModel):
    text: str = Field(min_length=1, max_length=600, description="2-3 sentence case summary for the bank employee.")


class LlmNarrator:
    def __init__(self, model):
        """`model` is a runnable whose invoke(messages) returns a Narrative (or its dict)."""
        self._model = model
        self.calls = 0   # cost per case

    @classmethod
    def from_model_id(cls, model_id: str) -> "LlmNarrator":
        from langchain.chat_models import init_chat_model
        # json_schema: same reason as the triage classifier (gpt-oss on Groq).
        return cls(init_chat_model(model_id, temperature=0).with_structured_output(Narrative, method="json_schema"))

    def write(self, facts: dict[str, Any], language: str) -> str:
        system = HANDOFF_PROMPT.format(language=LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["es"]))
        user = f"<hechos>{json.dumps(facts, ensure_ascii=False, sort_keys=True)}</hechos>"
        self.calls += 1
        try:
            out = self._model.invoke([("system", system), ("user", user)])
            return (out if isinstance(out, Narrative) else Narrative.model_validate(out)).text
        except Exception as exc:  # provider, network, rate limit, invalid schema
            raise ServiceFailure("Narrative unavailable") from exc