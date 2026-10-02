"""Agente 1: Validación de identidad (LangChain v1, create_agent).

Reparto de responsabilidades (clave para el criterio "controlled automation"):
- lingua (código): detecta el idioma de cada mensaje.
- LLM: conversa, pide datos faltantes y extrae ID / fecha / producto del texto.
- IdentityValidator (código): decide si el usuario queda autenticado.
- Orquestador: lee `next_step` (no la prosa del LLM) para pasar a triage o a humano.

El `session_id` NO es un parámetro del tool: se fija en el servidor. Así el
modelo no puede (ni por prompt injection) validar o consultar otra sesión.
"""
from __future__ import annotations

from typing import Optional

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from ..config.settings import settings
from .language import detect_language
from .validator import IdentityValidator, Status
from bank_agent.prompts.validation import ALREADY_DONE, BASE_PROMPT, LANG_NAMES



class ValidationAgent:
    """Una instancia por conversación."""

    def __init__(self, validator: IdentityValidator, model: Optional[str] = None):
        self.validator = validator
        self.session = validator.new_session()
        self.last_result = None
        self.lang_ambiguous = False
        sid = self.session.session_id

        @tool
        def verify_identity(customer_id: str, date_of_birth: str, product_number: str) -> dict:
            """Verifica la identidad del cliente con su número de identificación,
            fecha de nacimiento y el número de uno de sus productos (cuenta o tarjeta).
            Devuelve solo un estado; nunca devuelve datos del cliente."""
            result = validator.verify(sid, customer_id, date_of_birth, product_number)
            self.last_result = result
            return result.for_llm()

        @dynamic_prompt
        def prompt_with_language(request: ModelRequest) -> str:
            lang = self.session.language or settings.policy.default_language
            note = ("- No estás seguro del idioma del cliente: pregúntale brevemente si "
                    "prefiere español o portugués.") if self.lang_ambiguous else ""
            return BASE_PROMPT.format(lang_name=LANG_NAMES[lang], lang_note=note)

        self.agent = create_agent(
            model=model or settings.llm_model,
            tools=[verify_identity],
            middleware=[prompt_with_language],
            checkpointer=InMemorySaver(),   # memoria de la conversación
        )

    def chat(self, user_text: str) -> dict:
        # 1) idioma (determinístico)
        lr = detect_language(user_text, previous=self.session.language)
        self.session.language = lr.language
        self.lang_ambiguous = lr.ambiguous

        # 2) Si ya está validado, el agente 1 terminó: no se llama al LLM.
        #    El orquestador debe mandar este mensaje al agente 2 (Triage).
        if self.validator.is_authenticated(self.session.session_id):
            self.last_result = None
            return {
                "reply": ALREADY_DONE[lr.language],
                "language": lr.language,
                "language_confidence": round(lr.confidence, 3),
                "status": "ALREADY_VERIFIED",
                "authenticated": True,
                "next_step": "triage",
                "handoff": None,
            }

        # 3) LLM + tool
        self.last_result = None
        out = self.agent.invoke(
            {"messages": [{"role": "user", "content": user_text}]},
            config={"configurable": {"thread_id": self.session.session_id},
                    "recursion_limit": 8},   # límite de pasos del loop
        )
        reply = out["messages"][-1].content

        # 4) decisión de ruteo: viene del VALIDADOR, no del texto del LLM
        authenticated = self.validator.is_authenticated(self.session.session_id)
        if self.last_result:
            next_step = self.last_result.next_step
            status = self.last_result.status.value
        else:
            next_step = "triage" if authenticated else "ask_user"
            status = None

        return {
            "reply": reply,
            "language": lr.language,
            "language_confidence": round(lr.confidence, 3),
            "status": status,
            "authenticated": authenticated,
            "next_step": next_step,
            "handoff": self.handoff_packet() if next_step == "handoff_human" else None,
        }

    def handoff_packet(self) -> dict:
        """Contexto para el asesor humano (requisito del reto)."""
        s = self.session
        return {
            "reason": self.last_result.status.value if self.last_result else "unknown",
            "language": s.language,
            "authenticated": s.authenticated,
            "failed_attempts": s.failed_attempts,
            "locked_until": s.locked_until.isoformat() if s.locked_until else None,
            "audit_trail": list(s.audit),        # sin PII
            "unresolved": ["Identidad del cliente no verificada"] if not s.authenticated else [],
        }