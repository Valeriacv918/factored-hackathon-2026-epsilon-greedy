"""FastAPI app: the chat page plus a two-endpoint JSON API.

Run from the repository root (reads the root .env like scripts/run_disputes.py):
  uv run --project apps/web uvicorn bank_web.main:app --reload

WEB_IDENTITY=demo validates against the SYNTHETIC customers in
clients/demo_data.py instead of MCP verify_identity. Dispute tools still go to
MCP and will reject those fake tokens, so the graph ends safely; use it only to
try the identity step and the UI.
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bank_web.chat import BadRequest, ChatService

REPO_ROOT = Path(__file__).resolve().parents[4]
STATIC = Path(__file__).parent / "static"
COOKIE = "chat_id"
log = logging.getLogger("bank_web")


class ChatRequest(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    choice: str | None = Field(default=None, max_length=200)


def build_chat_service(env=os.environ):
    """Real wiring: one MCP client shared by identity and dispute tools."""
    from langgraph.checkpoint.memory import InMemorySaver

    from bank_agent.clients.identity import InMemoryIdentityChecker, McpIdentityChecker
    from bank_agent.clients.mcp_services import McpServices, mcp_client_from_env
    from bank_agent.clients.sessions import ValidatorSessions
    from bank_agent.graphs.disputes import build_graph
    from bank_agent.nodes.validator_agent.agent import ValidationAgent
    from bank_agent.nodes.validator_agent.validator import IdentityValidator

    client = mcp_client_from_env(env)
    if env.get("WEB_IDENTITY") == "demo":
        from bank_agent.clients.demo_data import DEMO_CUSTOMERS
        identity = InMemoryIdentityChecker(DEMO_CUSTOMERS)
    else:
        identity = McpIdentityChecker(client)
    validator = IdentityValidator(identity)
    services = McpServices.from_env(env, client=client, sessions=ValidatorSessions(validator))
    graph = build_graph(services, checkpointer=InMemorySaver())   # local only; not persistent
    return ChatService(graph, lambda: ValidationAgent(validator)), services.close


def create_app(chat_service: ChatService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        close = None
        if chat_service is None:
            from dotenv import load_dotenv
            load_dotenv(REPO_ROOT / ".env")
            app.state.chats, close = build_chat_service()
        else:
            app.state.chats = chat_service
        try:
            yield
        finally:
            if close:
                close()

    app = FastAPI(title="Bank dispute chat", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def set_cookie(response: Response, chat_id: str) -> None:
        response.set_cookie(COOKIE, chat_id, httponly=True, samesite="strict")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.post("/api/start")
    def start(request: Request, response: Response):
        """New conversation: drops the previous one, if any."""
        chats: ChatService = request.app.state.chats
        chats.end(request.cookies.get(COOKIE))
        chat_id, reply = chats.start()
        set_cookie(response, chat_id)
        return reply

    @app.post("/api/chat")
    def chat(body: ChatRequest, request: Request):
        chats: ChatService = request.app.state.chats
        chat_id = request.cookies.get(COOKIE)
        if not chats.exists(chat_id):
            raise HTTPException(409, "No active conversation; start a new one.")
        try:
            return chats.send(chat_id, text=body.text, choice=body.choice)
        except BadRequest as exc:
            raise HTTPException(400, str(exc)) from None
        except KeyError:
            raise HTTPException(409, "No active conversation; start a new one.") from None
        except Exception:
            log.exception("chat turn failed")   # tokens are redacted in SessionGrant repr
            raise HTTPException(500, "Something went wrong. Try again or start a new conversation.") from None

    return app


app = create_app()
