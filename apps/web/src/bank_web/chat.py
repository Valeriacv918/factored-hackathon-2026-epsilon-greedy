"""Server-side chat state: identity validation first, then the dispute graph.

The browser only sends text or a button value plus an opaque chat cookie. It never
sends graph state, session_ref or tokens (apps/agent/README.md, "Integrar"):

1. auth: each message goes to ValidationAgent.chat(). When the validator (not the
   LLM text) says next_step == "triage", the validator session id becomes the
   graph's session_ref, resolved by ValidatorSessions.
2. dispute: the first message starts the graph with initial_state(); after that,
   each answer resumes the pending interrupt, checked here against the offered
   buttons before it reaches the graph.
3. done: the conversation ended (outcome or human handoff); only reset continues.
"""
import secrets
import threading
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from langgraph.types import Command

from bank_agent.graphs.state import initial_state

Phase = Literal["auth", "dispute", "done"]

WELCOME = ("Hola, soy el asistente de disputas del banco. Para empezar necesito verificar tu identidad: "
           "número de identificación, fecha de nacimiento y el número de uno de tus productos (cuenta o tarjeta).\n\n"
           "Olá! Sou o assistente de contestações do banco. Para começar, preciso verificar sua identidade: "
           "número de identificação, data de nascimento e o número de um dos seus produtos (conta ou cartão).")

READY = {"es": "Cuéntame qué pasó con tu cargo o tu tarjeta.",
         "pt": "Conte o que aconteceu com a sua cobrança ou o seu cartão."}

HANDOFF = {"es": "Te comunicaremos con un asesor humano.",
           "pt": "Vamos transferir você para um atendente humano."}

RELOGIN = {"es": "Tu sesión expiró. Verifica tu identidad de nuevo para continuar.",
           "pt": "Sua sessão expirou. Verifique sua identidade novamente para continuar."}

LABELS = {
    "yes": ("Sí", "Sim"), "no": ("No", "Não"),
    "human": ("Hablar con un asesor", "Falar com um atendente"),
    "not_me": ("No reconozco un cargo", "Não reconheço uma cobrança"),
    "charge_error": ("Error en un cargo", "Erro em uma cobrança"),
    "emergency": ("Tarjeta perdida o robada", "Cartão perdido ou roubado"),
    "other": ("Otro tema", "Outro assunto"),
    "close": ("Terminar", "Encerrar"),
    "understood": ("Entendido", "Entendi"),
    "still_wrong": ("Sigue estando mal", "Continua errado"),
    "es": ("Español", "Español"), "pt": ("Português", "Português"),
}


class BadRequest(ValueError):
    """The request does not fit the current step (wrong input type or unknown button)."""


class AuthAgent(Protocol):
    session: Any   # has session_id and language

    def chat(self, user_text: str) -> dict: ...


@dataclass
class ChatSession:
    auth: AuthAgent
    phase: Phase = "auth"
    language: str = "es"
    session_ref: str | None = None
    thread_id: str | None = None
    pending: dict | None = None   # interrupt payload awaiting an answer


class ChatService:
    def __init__(self, graph, new_auth_agent: Callable[[], AuthAgent], *, recursion_limit: int = 100):
        self._graph, self._new_auth_agent, self._recursion_limit = graph, new_auth_agent, recursion_limit
        self._chats: dict[str, ChatSession] = {}
        # One lock for everything: the MCP stdio client and in-memory stores are shared (local demo).
        self._lock = threading.Lock()

    def start(self) -> tuple[str, dict]:
        with self._lock:
            chat_id = secrets.token_urlsafe(24)
            self._chats[chat_id] = ChatSession(self._new_auth_agent())
            return chat_id, _reply([WELCOME], "auth")

    def end(self, chat_id: str | None) -> None:
        with self._lock:
            self._chats.pop(chat_id or "", None)

    def exists(self, chat_id: str | None) -> bool:
        return bool(chat_id) and chat_id in self._chats

    def send(self, chat_id: str, *, text: str | None = None, choice: str | None = None) -> dict:
        with self._lock:
            chat = self._chats.get(chat_id)
            if chat is None:
                raise KeyError(chat_id)
            text = text.strip() if isinstance(text, str) else None
            if chat.phase == "done":
                raise BadRequest("The conversation has ended; start a new one.")
            if chat.phase == "auth":
                return self._authenticate(chat, _need_text(text, choice))
            return self._dispute(chat, text, choice)

    # --- phases ---

    def _authenticate(self, chat: ChatSession, text: str) -> dict:
        result = chat.auth.chat(text)
        chat.language = result.get("language") or chat.language
        messages = [result["reply"]]
        if result["next_step"] == "triage":
            chat.phase = "dispute"
            chat.session_ref = chat.auth.session.session_id
            chat.thread_id = f"web-{secrets.token_hex(8)}"
            chat.pending = None
            return _reply(messages, "dispute")
        if result["next_step"] == "handoff_human":
            chat.phase = "done"
            return _reply(messages + [_say(chat, HANDOFF)], "done", input="none", outcome="handoff_human")
        return _reply(messages, "auth")

    def _dispute(self, chat: ChatSession, text: str | None, choice: str | None) -> dict:
        config = {"configurable": {"thread_id": chat.thread_id}, "recursion_limit": self._recursion_limit}
        if chat.pending is None:
            state = initial_state(chat.thread_id, chat.session_ref, _need_text(text, choice))
            if chat.language in {"es", "pt"}:
                state["language"] = chat.language   # trusted: detected by the validator
            return self._render(chat, self._graph.invoke(state, config))
        if chat.pending["kind"] == "transaction_details":
            resume = {"text": _need_text(text, choice)}
        else:
            if choice is None or text:
                raise BadRequest("Choose one of the buttons.")
            if choice not in chat.pending["options"]:
                raise BadRequest("That option is not available.")
            resume = {"choice": choice}
        return self._render(chat, self._graph.invoke(Command(resume=resume), config))

    def _render(self, chat: ChatSession, result: dict) -> dict:
        if result.get("language") in {"es", "pt"}:
            chat.language = result["language"]
        if "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            chat.pending = payload
            chat.language = payload.get("language") or chat.language
            details = {k: payload[k] for k in ("transactions", "cards", "transaction") if k in payload}
            if payload["kind"] == "transaction_details":
                return _reply([payload["message"]], "dispute", details=details)
            return _reply([payload["message"]], "dispute", input="buttons", details=details,
                          options=[{"value": o, "label": _label(o, payload, chat.language)}
                                   for o in payload["options"]])
        chat.pending = None
        outcome = result.get("outcome")
        messages = [result["response"]] if result.get("response") else []
        if outcome == "authentication_required":
            chat.auth, chat.phase, chat.session_ref, chat.thread_id = self._new_auth_agent(), "auth", None, None
            return _reply(messages + [_say(chat, RELOGIN)], "auth", outcome=outcome)
        chat.phase = "done"
        return _reply(messages, "done", input="none", outcome=outcome)


def _need_text(text: str | None, choice: str | None) -> str:
    if choice is not None or not text:
        raise BadRequest("Write a message.")
    return text


def _say(chat: ChatSession, texts: dict) -> str:
    return texts.get(chat.language, texts["es"])


def _label(option: str, payload: dict, language: str) -> str:
    """Readable button text. Transaction and card ids are labeled from the payload."""
    for tx in payload.get("transactions", []):
        if tx.get("id") == option:
            return f"{tx.get('amount')} {tx.get('currency')} · {str(tx.get('date', ''))[:10]}"
    for card in payload.get("cards", []):
        if card.get("id") == option:
            return f"•••• {card.get('last4')}"
    if option in LABELS:
        es, pt = LABELS[option]
        return pt if language == "pt" else es
    return option


def _reply(messages: list[str], phase: Phase, *, input: str = "text", options=None, details=None,
           outcome: str | None = None) -> dict:
    return {"messages": messages, "phase": phase, "input": input, "options": options or [],
            "details": details or {}, "outcome": outcome}
