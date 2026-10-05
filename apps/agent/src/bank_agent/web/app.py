"""Web front for the agent: the same graph as `run_disputes.py --flow full`, behind a small HTTP API.

- One graph and one MCP client per process, created at startup and reused by every request.
- Each conversation is a LangGraph thread with its own server-generated thread_id, owned by
  the browser that started it (an HttpOnly cookie); another browser cannot read or resume it.
- Each interrupt becomes a form, a text box or buttons. The browser only sees what it must
  show: buttons go out as {index, label} and come back as the index, so card, transaction
  and customer identifiers stay on the server (cards are shown by their last four digits).
- Identity factors go from the form straight to the graph's resume value (and from there to
  MCP verify_identity), never into a chat message or a model prompt.
- Configuration comes from the environment; nothing secret is sent to the browser.

Run locally from the repository root:
  uv run --project apps/agent bank-web
"""
import contextlib
import logging
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from bank_agent.graphs.state import initial_state
from bank_agent.observability import configure_logging, log_event
from bank_agent.web.metrics import LiveMetrics, offline_triage, outcome_group

logger = logging.getLogger(__name__)
STATIC = Path(__file__).with_name("static")
COOKIE = "bank_agent_browser"
MAX_TEXT = 1000
CONVERSATION_TTL_S = 2 * 3600
TEXT_KINDS = {"request_details", "transaction_details", "validation_details"}

# Button labels per language (es, pt). Values not listed here are never shown raw.
LABELS = {
    "yes": ("Sí", "Sim"), "no": ("No", "Não"),
    "human": ("Hablar con un asesor", "Falar com um atendente"),
    "none": ("Ninguno de estos", "Nenhuma destas"),
    "emergency": ("Tarjeta perdida o robada", "Cartão perdido ou roubado"),
    "not_me": ("Un cargo que no reconozco", "Uma compra que não reconheço"),
    "charge_error": ("Un cobro equivocado", "Uma cobrança errada"),
    "other": ("Otra consulta", "Outra solicitação"),
    "close": ("Terminar", "Encerrar"),
    "understood": ("Entendido", "Entendi"),
    "still_wrong": ("Sigue estando mal", "Continua errado"),
    "es": ("Español", "Español"), "pt": ("Português", "Português"),
}
FIELD_LABELS = {
    "document_number": ("Número de documento", "Número do documento"),
    "date_of_birth": ("Fecha de nacimiento", "Data de nascimento"),
    "product_number": ("Número de producto", "Número do produto"),
}


def masked_card(last4: Any, lang: str) -> str:
    """Only an actual last4; never fall back to the internal product ID."""
    value = str(last4 or "")
    if len(value) == 4 and value.isascii() and value.isdigit():
        return ("Tarjeta •••• " if lang == "es" else "Cartão •••• ") + value
    return "Tarjeta sin terminación disponible" if lang == "es" else "Cartão sem final disponível"


def transaction_view(tx: dict[str, Any]) -> dict[str, Any]:
    """What the customer needs to recognize a charge; the transaction ID stays on the server."""
    return {k: tx.get(k) for k in ("date", "amount", "currency", "merchant") if tx.get(k) is not None}


def transaction_label(tx: dict[str, Any]) -> str:
    parts = [str(tx.get("date") or "")[:10], f"{tx.get('amount', '')} {tx.get('currency', '')}".strip(),
             tx.get("merchant") or ""]
    return " · ".join(p for p in parts if p)


@dataclass
class Pending:
    kind: str
    options: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)


@dataclass
class Conversation:
    owner: str
    thread_id: str
    created: float = field(default_factory=time.time)
    pending: Pending | None = None
    done: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


def present(question: dict[str, Any]) -> tuple[dict[str, Any], Pending]:
    """Turn an interrupt payload into what the browser shows, plus what the server keeps."""
    lang = "pt" if question.get("language") == "pt" else "es"
    i = 1 if lang == "pt" else 0
    kind = question.get("kind", "")
    view: dict[str, Any] = {"kind": kind, "language": lang, "message": question.get("message", "")}
    if "fields" in question:
        fields = [f for f in question["fields"] if isinstance(f, str)]
        view["form"] = [{"name": f, "label": FIELD_LABELS.get(f, (f, f))[i],
                         "type": "date" if f == "date_of_birth" else "text"} for f in fields]
        return view, Pending(kind, fields=fields)
    if "options" not in question or kind in TEXT_KINDS:
        view["input"] = "text"
        return view, Pending(kind)
    options = [str(o) for o in question["options"]]
    cards = {c.get("id"): c.get("last4") for c in question.get("cards", []) if isinstance(c, dict)}
    txs = {t.get("id"): t for t in question.get("transactions", []) if isinstance(t, dict)}
    labels = []
    for n, value in enumerate(options, 1):
        if value in cards:
            labels.append(masked_card(cards[value], lang))
        elif value in txs:
            labels.append(transaction_label(txs[value]))
        else:
            labels.append(LABELS.get(value, (f"Opción {n}", f"Opção {n}"))[i])
    view["options"] = [{"index": n, "label": label, "value": options[n] if options[n] in LABELS else None}
                       for n, label in enumerate(labels)]
    if kind in {"confirm_block"}:
        view["card"] = masked_card(question.get("last4"), lang)
    if isinstance(question.get("transaction"), dict):
        view["transaction"] = transaction_view(question["transaction"])
    return view, Pending(kind, options=options)


def resume_value(pending: Pending, body: dict[str, Any]) -> dict[str, Any]:
    """Validate the browser's answer against the pending interrupt and build the resume value."""
    if pending.fields:
        values = body.get("fields")
        if not isinstance(values, dict) or set(values) != set(pending.fields):
            raise ValueError("form_fields")
        if not all(isinstance(v, str) and v.strip() and len(v) <= 100 for v in values.values()):
            raise ValueError("form_fields")
        return {f: values[f].strip() for f in pending.fields}
    if pending.options:
        index = body.get("index")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(pending.options):
            raise ValueError("option")
        return {"choice": pending.options[index]}
    text = body.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise ValueError("text")
    return {"text": text.strip()}


class AgentApp:
    """Owns the graph, the MCP services and the conversation registry for this process."""

    def __init__(self, services, graph):
        self.services, self.graph = services, graph
        self.conversations: dict[str, Conversation] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "AgentApp":
        from bank_agent.clients.mcp_services import McpServices
        from bank_agent.graphs.validation_triage import build_graph
        services = McpServices.from_env()
        # Check MCP configuration before Cloud Run marks the app ready.
        try:
            services._client.start()
        except Exception:
            services.close()
            raise
        graph = build_graph(services, checkpointer=InMemorySaver(), test_charge_error=True, test_fraud=True,
                            test_escalation=True, test_card_emergency=True)   # = run_disputes.py --flow full
        return cls(services, graph)

    def close(self) -> None:
        self.services.close()

    def active(self) -> int:
        with self._lock:
            return sum(not c.done for c in self.conversations.values())

    def _prune(self) -> None:
        cutoff = time.time() - CONVERSATION_TTL_S
        with self._lock:
            for key in [k for k, c in self.conversations.items() if c.created < cutoff]:
                del self.conversations[key]

    def get(self, owner: str, thread_id: str) -> Conversation | None:
        with self._lock:
            conversation = self.conversations.get(thread_id)
        return conversation if conversation and secrets.compare_digest(conversation.owner, owner) else None

    def start(self, owner: str, message: str) -> dict[str, Any]:
        self._prune()
        thread_id = f"web-{uuid.uuid4().hex}"
        conversation = Conversation(owner=owner, thread_id=thread_id)
        with self._lock:
            self.conversations[thread_id] = conversation
        with conversation.lock:
            # session_ref is empty: the identity form creates the session; no DEV_SESSIONS shortcut here.
            return self._run(conversation, initial_state(thread_id, "", message))

    def resume(self, conversation: Conversation, body: dict[str, Any]) -> dict[str, Any]:
        with conversation.lock:
            if conversation.done or conversation.pending is None:
                raise ValueError("finished")
            value = resume_value(conversation.pending, body)
            return self._run(conversation, Command(resume=value))

    def _run(self, conversation: Conversation, payload) -> dict[str, Any]:
        config = {"configurable": {"thread_id": conversation.thread_id}, "recursion_limit": 100}
        state = self.graph.invoke(payload, config)
        trace = [{"node": t.get("node"), "next": t.get("next")} for t in state.get("trace", [])]
        if "__interrupt__" in state:
            view, conversation.pending = present({**state["__interrupt__"][0].value, "language": state.get("language")})
            return {"thread_id": conversation.thread_id, "status": "waiting", "question": view, "trace": trace}
        conversation.pending, conversation.done = None, True
        return {"thread_id": conversation.thread_id, "status": "done", "trace": trace,
                "response": state.get("response"), "outcome": state.get("outcome"),
                "group": outcome_group(state.get("outcome")), "language": state.get("language")}


# --- HTTP ------------------------------------------------------------------------------------

def browser_id(request: Request) -> str | None:
    value = request.cookies.get(COOKIE)
    return value if value and len(value) == 43 else None


def error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status)


async def json_body(request: Request) -> dict[str, Any] | None:
    try:
        body = await request.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


async def start_conversation(request: Request) -> JSONResponse:
    body = await json_body(request)
    message = body.get("message") if body else None
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_TEXT:
        return error("message", 400)
    owner = browser_id(request) or secrets.token_urlsafe(32)
    try:
        result = await run_in_threadpool(request.app.state.agent.start, owner, message.strip())
    except Exception as exc:
        logger.exception("Conversation failed to start (%s)", type(exc).__name__)
        return error("agent_unavailable", 503)
    response = JSONResponse(result)
    response.set_cookie(COOKIE, owner, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https", max_age=CONVERSATION_TTL_S)
    return response


async def resume_conversation(request: Request) -> JSONResponse:
    owner = browser_id(request)
    agent: AgentApp = request.app.state.agent
    conversation = agent.get(owner, request.path_params["thread_id"]) if owner else None
    if conversation is None:
        return error("not_found", 404)
    body = await json_body(request)
    if body is None:
        return error("body", 400)
    try:
        return JSONResponse(await run_in_threadpool(agent.resume, conversation, body))
    except ValueError as exc:
        return error(f"invalid_{exc}" if str(exc) else "invalid", 400)
    except Exception as exc:
        logger.exception("Conversation step failed (%s)", type(exc).__name__)
        return error("agent_unavailable", 503)


async def metrics(request: Request) -> JSONResponse:
    agent: AgentApp = request.app.state.agent
    return JSONResponse({"live": request.app.state.metrics.snapshot(active=agent.active()),
                         "offline": request.app.state.offline,
                         "scenario_date": agent.services.now().date().isoformat()})


async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"] += [
                    (b"content-security-policy", b"default-src 'self'; img-src 'self' data:; frame-ancestors 'none'"),
                    (b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer")]
            await send(message)
        if scope["type"] == "http":
            started = time.perf_counter()
            await self.app(scope, receive, send_with_headers)
            if scope["path"].startswith("/api/"):
                log_event("http.request", method=scope["method"], path=scope["path"].split("/")[2],
                          ms=round((time.perf_counter() - started) * 1000, 1))
        else:
            await self.app(scope, receive, send)


def create_app(agent_factory=AgentApp.from_env) -> Starlette:
    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        configure_logging()
        live = LiveMetrics()
        logging.getLogger("bank_agent").addHandler(live)
        app.state.metrics, app.state.offline = live, offline_triage()
        app.state.agent = await run_in_threadpool(agent_factory)
        try:
            yield
        finally:
            app.state.agent.close()
            logging.getLogger("bank_agent").removeHandler(live)

    routes = [
        Route("/api/conversations", start_conversation, methods=["POST"]),
        Route("/api/conversations/{thread_id}/resume", resume_conversation, methods=["POST"]),
        Route("/api/metrics", metrics, methods=["GET"]),
        Route("/healthz", healthz, methods=["GET"]),
        Mount("/", StaticFiles(directory=STATIC, html=True)),
    ]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(SecurityHeaders)
    return app


def main() -> None:
    import uvicorn
    with contextlib.suppress(ImportError):
        from dotenv import load_dotenv   # local runs: the repository .env; Cloud Run sets real env vars
        load_dotenv(Path(__file__).resolve().parents[5] / ".env")
    uvicorn.run(create_app(), host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8080")))
