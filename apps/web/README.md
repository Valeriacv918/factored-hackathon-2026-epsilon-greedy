# Chat web (FastAPI + HTML/JS)

Chat page for the dispute agent. The customer authenticates inside the chat
(identity validator: ID + date of birth + product number via MCP `verify_identity`)
and then continues in the same chat with the LangGraph dispute workflow: graph
questions show as buttons, transaction clarifications as free text.

```text
src/bank_web/
  main.py     FastAPI app: GET / (page), POST /api/start, POST /api/chat; real wiring
  chat.py     ChatService: auth -> dispute -> done, all state on the server
  static/     index.html, app.js, styles.css (no build step)
```

The browser only holds an HttpOnly `chat_id` cookie and sends `{"text": ...}` or
`{"choice": <button value>}`. Graph state, `session_ref` and tokens stay on the
server; a choice is checked against the buttons of the pending interrupt before it
resumes the graph. Free text never confirms an action.

## Run (from the repository root)

Root `.env` as in `.env.example`: `SESSION_SIGNING_KEY`, `SCENARIO_NOW`,
`GROQ_API_KEY`, plus ADC for BigQuery (the MCP server is launched over stdio with
`MCP_SERVER_COMMAND`, or reached at `MCP_SERVER_URL`).

```bash
uv sync --project apps/web
uv run --project apps/web uvicorn bank_web.main:app --reload
# open http://localhost:8000
```

`WEB_IDENTITY=demo` validates against the synthetic customers in
`apps/agent/src/bank_agent/clients/demo_data.py` (e.g. `1020304050`, `03/04/1990`,
`4111222233334444`). Dispute tools still call MCP and reject those fake tokens, so
the graph ends safely: use it only to try the identity step and the UI.

## Tests

```bash
uv run --project apps/web pytest apps/web
```

Real dispute graph with synthetic services and a stubbed identity agent; no network or model.

## Limits (local demo)

In-memory chats, validator sessions and checkpoints (`InMemorySaver`): one process,
lost on restart. One lock serializes turns. No Dockerfile or Cloud Run setup yet.
