"""Agente 2 (card emergency): LangChain v1, create_agent. A diferencia de
fraud_agent (100% codigo), este flujo SI usa un LLM para conversar.

Por que aqui si y en fraud_agent no: entender "me robaron la tarjeta" o
"sí, bloquéala" es lenguaje libre del cliente -- la parte que el reto llama
"controlled automation" necesita un LLM para esa conversacion. Pero los
PASOS son fijos (SELECT_CARD -> CONFIRM_BLOCK -> BLOCK_AND_VERIFY ->
ASK_CHARGE, ver docs/STATE_MACHINE2.md) y los decide `CardEmergencyService`
(código puro), nunca el texto del LLM:

- LLM: conversa, pide la info que falte y llama a la tool del paso actual.
- CardEmergencyService (código): decide el siguiente estado real.
- Orquestador: lee `next_step` (no la prosa del LLM) para avanzar.

El `session_id` NO es parámetro de ninguna tool: se fija al crear el agente,
igual que en `validator_agent/agent.py`.
"""
from __future__ import annotations

from typing import Optional

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from ..config.settings import settings
from ..prompts.card_emergency import BASE_PROMPT
from ..prompts.validation import LANG_NAMES
from .service import CardEmergencyService, EmergencyResult


class CardEmergencyAgent:
    """Una instancia por conversación."""

    def __init__(self, service: CardEmergencyService, session_id: str, model: Optional[str] = None):
        self.service = service
        self.session_id = session_id
        self.last_result: EmergencyResult = service.start(session_id)

        @tool
        def pick_card(product_number: str) -> dict:
            """Selecciona la tarjeta que el cliente identificó (número o últimos dígitos)."""
            self.last_result = service.select_card(session_id, product_number)
            return self._for_llm()

        @tool
        def confirm_block(confirmed: bool) -> dict:
            """Registra si el cliente confirma bloquear la tarjeta ahora (true) o no (false)."""
            self.last_result = service.confirm_block(session_id, confirmed)
            return self._for_llm()

        @tool
        def report_charge(has_charge: bool) -> dict:
            """Registra si el cliente menciona un cargo puntual que no reconoce (true/false)."""
            self.last_result = service.ask_charge(session_id, has_charge)
            return self._for_llm()

        @dynamic_prompt
        def prompt_with_language(request: ModelRequest) -> str:
            lang = service.validator.get_session(session_id).language or settings.policy.default_language
            return BASE_PROMPT.format(lang_name=LANG_NAMES.get(lang, LANG_NAMES["es"]))

        self.agent = create_agent(
            model=model or settings.llm_model,
            tools=[pick_card, confirm_block, report_charge],
            middleware=[prompt_with_language],
            checkpointer=InMemorySaver(),
        )

    def _for_llm(self) -> dict:
        """Lo único que ve el modelo: nunca datos del cliente fuera de lo necesario."""
        r = self.last_result
        return {
            "next_step": r.next_step,
            "cards": r.cards,
            "card": r.card,
            "escalation": None if not r.escalation else {
                "queue": r.escalation.queue,
                "priority": r.escalation.priority,
                "reason": r.escalation.reason,
            },
        }

    def chat(self, user_text: str) -> dict:
        out = self.agent.invoke(
            {"messages": [{"role": "user", "content": user_text}]},
            config={"configurable": {"thread_id": self.session_id},
                    "recursion_limit": 8},
        )
        reply = out["messages"][-1].content

        # Decisión de ruteo: viene del SERVICIO, no del texto del LLM
        r = self.last_result
        return {
            "reply": reply,
            "state": r.state.value,
            "next_step": r.next_step,
            "card": r.card,
            "escalation": None if not r.escalation else {
                "queue": r.escalation.queue,
                "priority": r.escalation.priority,
                "reason": r.escalation.reason,
                "context": r.escalation.context,
            },
        }
