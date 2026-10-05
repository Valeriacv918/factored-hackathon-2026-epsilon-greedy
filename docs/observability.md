# Logging and observability

How the dispute agent and the MCP server record what happened in a conversation: which
graph steps ran, what the LLM did, which MCP tools and BigQuery queries were called, and
what it cost. Security considerations are in [SECURITY_NOTES.md](../SECURITY_NOTES.md#logging).

Code: `apps/agent/src/bank_agent/observability.py` and
`apps/mcp-server/src/bank_mcp/observability.py`. Tests: `test_observability.py` in each
app's `tests/`.

## 1. Design

- **Structured JSON lines.** Every event is one JSON object per line. Locally it goes to a
  file or the console; on Cloud Run, Cloud Logging picks it up with no extra setup (the
  `severity` field sets the log level there).
- **One conversation id end to end.** The graph binds the conversation's id while each
  node runs. The agent sends it, with the node name, in the `_meta` of every MCP tool call.
  The server puts it on its own events and on the BigQuery job labels.
- **No vendor or third-party service.** Prompts and customer data stay in our own logs
  (no LangSmith or similar).
- **Decisions by default, content on demand.** By default LLM events hold metadata and
  the decision (intent, status), not the prompt or the reply. Full prompts and outputs only
  with `LOG_LLM_CONTENT=1`, for local debugging.
- **Logging never breaks the flow.** The LLM hook is a LangChain callback, whose errors
  LangChain swallows. The other hooks only time and record around existing code.

```text
customer ──> graph node ──step──────────────────────────────┐
                │ ├─ LLM call ──llm.call / llm.result        │  agent log
                │ └─ MCP call ──mcp.call                     │  (stdout or LOG_FILE)
                │        │ _meta: conversation_id, node      ┘
                │        v
                │   MCP server ──tool──┐
                │        └─ BigQuery ──bq.query (+ job label)│  server log (stderr)
                └─ route "end" ──conversation.summary        ┘
```

## 2. Event reference

Every event has these fields:

| Field | Meaning |
|---|---|
| `ts` | UTC timestamp, ISO 8601 |
| `level`, `severity` | `INFO`, `WARNING`, `ERROR` (`severity` is for Cloud Logging) |
| `service` | `agent` or `mcp` |
| `event` | event name (below) |
| `conversation_id` | conversation (the graph's `conversation_id`, e.g. `cli-078704fc`), or null |
| `node` | graph node running at the time (e.g. `fraud_agent`), or null |

### Agent (`service: agent`)

| Event | When | Fields |
|---|---|---|
| `step` | every graph node run, in both graphs | `phase`, `next` (route chosen), `ms`. Plus `waiting: true` when the node paused for the customer (interrupt), or `error` (exception type) when it raised |
| `llm.call` | every chat-model call | `step` (`understanding`, `triage`, `narrative`, `validator`), `model`, `ms`, `status` (`ok`/`error`), `input_tokens`, `output_tokens`, `error`. With `LOG_LLM_CONTENT=1` also `messages` and `output` |
| `llm.result` | after the agent parses the LLM output | depends on `step`: **understanding** `intent`, `confidence`, `slots`, `wants_human` · **triage** `intent`, `confidence`, `wants_human`, `attempt` (or `fallback: true`) · **narrative** `chars` · **validator** `status`, `next_step`, `authenticated` |
| `mcp.call` | every MCP tool call | `tool`, `args` (sensitive keys `<redacted>`), `ms`, `status`, `error` (the server's error text) |
| `conversation.summary` | when a node routes to `end` | `steps`, `llm_calls`, `input_tokens`, `output_tokens`, `llm_ms`, `mcp_calls`, `mcp_ms`, `errors` |
| `log` | any other log record from `bank_agent.*` | `logger`, `message` |

### MCP server (`service: mcp`)

| Event | When | Fields |
|---|---|---|
| `tool` | every `tools/call` (from `CorrelationMiddleware`) | `tool`, `ms`, `status`, `error` (exception type if one escaped) |
| `bq.query` | every BigQuery job | `tool`, `sql_hash`, `status`, then `rows` and `bytes` on success, `error` (BigQuery's message) on failure |
| `log` | any other record (startup, MCP SDK) | `logger`, `message` |

`bq.query` statuses: `ok`, `rejected_cost` (dry run over the byte cap), `bad_request`,
`forbidden`, `not_found`, `timeout`, `api_error` (5xx, quota and other API errors). Failures
log the detail; what the caller receives is unchanged, except `api_error`, which returns a
generic "BigQuery is unavailable; try again.".

### Example: one fraud conversation (trimmed)

```json
{"service":"agent","event":"step","conversation_id":"cli-1a2b3c4d","node":"validator_agent","phase":"validate","next":"request_wait","ms":2140.3}
{"service":"agent","event":"llm.call","conversation_id":"cli-1a2b3c4d","node":"triage_agent","step":"triage","model":"openai/gpt-oss-120b","ms":812.4,"status":"ok","input_tokens":1450,"output_tokens":96}
{"service":"agent","event":"llm.result","conversation_id":"cli-1a2b3c4d","node":"triage_agent","step":"triage","intent":"not_me","confidence":0.93,"wants_human":false,"attempt":1}
{"service":"mcp","event":"bq.query","conversation_id":"cli-1a2b3c4d","node":"fraud_agent","tool":"block_card","sql_hash":"5f0c1e2d3a4b","status":"ok","rows":0,"bytes":0}
{"service":"mcp","event":"tool","conversation_id":"cli-1a2b3c4d","node":"fraud_agent","tool":"block_card","ms":3120.8,"status":"ok"}
{"service":"agent","event":"mcp.call","conversation_id":"cli-1a2b3c4d","node":"fraud_agent","tool":"block_card","args":{"card_id":"PRD-123","idempotency_key":"cli-1a2b3c4d:block:PRD-123"},"ms":3141.0,"status":"ok"}
{"service":"agent","event":"conversation.summary","conversation_id":"cli-1a2b3c4d","node":null,"steps":14,"llm_calls":3,"input_tokens":4210,"output_tokens":388,"llm_ms":2950.1,"mcp_calls":9,"mcp_ms":14820.6,"errors":0}
```

## 3. Configuration

Agent (environment or `.env`; see `.env.example`):

| Variable | Default | Effect |
|---|---|---|
| `LOG_FILE` | unset: stdout | write events to this file instead. `scripts/run_disputes.py` and `scripts/chat_validator.py` default to `logs/agent.jsonl`, so events don't mix with the chat |
| `LOG_LEVEL` | `INFO` | level for `bank_agent` loggers |
| `LOG_LLM_CONTENT` | unset | `1`: `llm.call` also carries prompts and outputs. `run_disputes.py --debug` sets it |

Logging is configured by calling `bank_agent.observability.configure_logging()` once at
startup (the scripts do). Without it, events are created but only reach whatever logging
setup the process already has (pytest's `caplog` in tests).

MCP server: `main()` calls `bank_mcp.observability.configure_logging()`, which writes every
log record as JSON to **stderr**. Over stdio, stdout is the JSON-RPC channel, and the
agent's MCP client inherits the server's stderr, so locally the server lines appear in the
agent's terminal. On Cloud Run they go to Cloud Logging.

## 4. Reading the logs

The scripts print the log path at startup (`Logs: .../logs/agent.jsonl`).

One conversation, in order:

```bash
python -c "import json,sys; [print(l, end='') for l in open('logs/agent.jsonl', encoding='utf-8') if json.loads(l).get('conversation_id') == sys.argv[1]]" cli-1a2b3c4d
```

With `jq`:

```bash
jq -c 'select(.conversation_id == "cli-1a2b3c4d") | {event, node, step, tool, status, next, ms}' logs/agent.jsonl
jq -c 'select(.event == "conversation.summary")' logs/agent.jsonl             # cost per conversation
jq -c 'select(.status == "error" or .error)' logs/agent.jsonl                 # failures
jq -c 'select(.event == "llm.result")' logs/agent.jsonl                       # what the LLM decided
```

Questions it answers:

- **Why did the conversation end where it did?** The `step` events: each node and the
  `next` route it chose. The last step before the summary routed to `end`.
- **What did the LLM decide?** `llm.result` (intent, confidence, validation status). To see
  the prompt itself, rerun with `--debug`.
- **Why did a tool fail?** The agent's `mcp.call` has the server's error text. The server's
  `bq.query` with the same `conversation_id` has BigQuery's message.
- **What did it cost?** `conversation.summary`: tokens, LLM and MCP time, number of calls.

In Cloud Logging, filter with `jsonPayload.conversation_id="cli-1a2b3c4d"`.

### BigQuery bytes per conversation

Every query carries the job labels `source=bank-mcp`, `tool=<tool>` and, when the agent
sent one, `conversation=<id>` (lowercase, characters outside `[a-z0-9_-]` replaced by `_`,
63 characters at most). Bytes per conversation over the last day. `INFORMATION_SCHEMA.JOBS`
needs `bigquery.jobs.listAll` on the project (e.g. BigQuery Resource Viewer); the read-only
dev account doesn't have it.

```sql
SELECT (SELECT value FROM UNNEST(labels) WHERE key = 'conversation') AS conversation,
       COUNT(*) AS jobs, SUM(total_bytes_processed) AS bytes
FROM `region-us-central1`.INFORMATION_SCHEMA.JOBS
WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND EXISTS (SELECT 1 FROM UNNEST(labels) WHERE key = 'source' AND value = 'bank-mcp')
GROUP BY conversation
ORDER BY bytes DESC
```

## 5. Privacy rules

- **Never logged**, even with `LOG_LLM_CONTENT=1`: `session_token`, `document_number`,
  `date_of_birth`, `product_number` and `product_numbers` in MCP arguments (shown as
  `<redacted>`). A handoff `packet` is logged as `reason` and `queue` only.
- **Not logged by default:** prompts, LLM replies, the validator's reply, the handoff
  narrative (only its length).
- **`LOG_LLM_CONTENT=1` logs what the customer typed**, including identity factors in
  validator prompts. Use it only on your own machine, never in a deployed service, and
  delete `logs/agent.jsonl` afterwards.
- Default logs still show what was disputed (slots, transaction and card ids): treat
  them as confidential. `logs/` is in `.gitignore`.
- The server uses the `_meta` correlation values only for logs and labels, never for
  authorization. They are capped at 128 characters.

## 6. Extending

- **New agent event:** call `log_event("name", field=value)` from
  `bank_agent.observability`. `conversation_id` and `node` are added from the current
  context. Use plain JSON values, and never pass anything from the "never logged" list.
- **New LLM call site:** attach `llm_config("<step>")` to the runnable
  (`.with_config(...)`) or to the `invoke` config. Log the parsed decision with
  `log_event("llm.result", step=...)`.
- **New MCP tool:** nothing to do. The middleware and the agent's client already log it.
  If it takes a sensitive argument, add the name to `SENSITIVE` in
  `bank_agent/observability.py`.
- **Future HTTP endpoint:** wrap each request in `bind(conversation_id=...)` and log
  `log_event("http.request", method=..., path=..., status=..., ms=...)`. Everything the
  request triggers will then carry the same id.
