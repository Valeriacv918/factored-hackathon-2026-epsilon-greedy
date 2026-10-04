"""Clasificador LLM del Triage (estado UNDERSTAND).

El LLM lee el mensaje y devuelve un `Understanding` (intención, confianza,
wants_human y datos). NO decide la ruta: eso lo hace el router con reglas.
Las fechas relativas ("ayer", "ontem") las resuelve el LLM contra la fecha de
hoy, que se calcula en cada llamada (nunca una fecha fija).
"""
import datetime as dt
import logging
from typing import Callable

from bank_agent.config.settings import settings
from bank_agent.prompts.triage import TRIAGE_SYSTEM_PROMPT
from bank_agent.nodes.triage_agent.schemas import Intent, Understanding

logger = logging.getLogger(__name__)

# Respuesta segura si el LLM falla: confianza 0 → el router mostrará botones.
# (Las reglas de emergencia y de pedir humano se aplican igual, porque son código.)
FALLBACK = Understanding(intent=Intent.OTHER, confidence=0.0, wants_human=False)


def today() -> dt.date:
    """Fecha de hoy según el reloj del sistema, en su zona horaria local."""
    return dt.datetime.now().astimezone().date()


def system_prompt(on: dt.date) -> str:
    # Llenamos el prompt con los valores reales de Intent: si algún día cambian
    # los nombres, el prompt se actualiza solo.
    return TRIAGE_SYSTEM_PROMPT.format(
        emergency=Intent.EMERGENCY.value,
        not_me=Intent.NOT_ME.value,
        charge_error=Intent.CHARGE_ERROR.value,
        other=Intent.OTHER.value,
        today=on.isoformat(),
    )


class LLMClassifier:
    def __init__(self, structured_llm=None, max_attempts: int = 2,
                 today: Callable[[], dt.date] = today):
        """`structured_llm` y `today` se pueden reemplazar en los tests
        (un LLM falso y una fecha fija), para no gastar llamadas a Groq."""
        if structured_llm is None:
            from langchain.chat_models import init_chat_model
            llm = init_chat_model(settings.llm_model, temperature=0)   # temperature 0: respuestas estables
            # json_schema: Groq obliga al modelo a responder con el formato de Understanding.
            # (Con "function_calling", gpt-oss a veces inventa el nombre de la herramienta.)
            structured_llm = llm.with_structured_output(Understanding, method="json_schema")
        self.llm = structured_llm
        self.max_attempts = max_attempts    # regla global 3: reintentar una vez
        self.today = today
        self.calls = 0                      # para medir costo por caso

    def understand(self, text: str) -> Understanding:
        messages = [
            ("system", system_prompt(self.today())),
            ("user", f"<mensaje_cliente>{text}</mensaje_cliente>"),
        ]
        for attempt in range(1, self.max_attempts + 1):
            self.calls += 1
            try:
                result = self.llm.invoke(messages)
                if isinstance(result, Understanding):
                    return result
                return Understanding.model_validate(result)   # por si llega como dict
            except Exception as exc:
                logger.warning("Fallo del clasificador (intento %s): %s", attempt, exc)
        return FALLBACK
    