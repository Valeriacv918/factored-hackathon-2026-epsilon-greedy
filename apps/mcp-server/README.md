# MCP

MCP server over `bank_curated` for the dispute agent. Bounded tools only;
no arbitrary SQL (see ../../docs/architecture.md). Writes (block, dispute, handoff)
and `dispute_context` are pending a decision on where writes are stored.

| Tool | Returns (agent field names, see agent `clients/README.md`) |
|---|---|
| verify_identity(document_number, date_of_birth, product_number) | status (verified / failed / locked), customer_id, session_token, product_numbers, attempts_left, locked_until, expires_at |
| find_transactions(session_token, reference_date, window_days, slots?, limit=3) | transactions[id, customer_id, card_id, status, fraud_score, amount, amount_usd, currency, date, merchant], has_more |
| list_cards(session_token) | cards[id, customer_id, last4, status, type] |
| get_card(session_token, card_id) | id, customer_id, last4, status, type |

**Trust model.** The server decides who the customer is; it never takes
`customer_id` from a data tool's caller. The customer identifies with their
`document_number` (cédula, CURP, DNI; spaces, dots and dashes ignored). `verify_identity`
compares the three values in SQL (the date of birth is never returned) and, on a match,
returns the internal `customer_id` (for traceability) and a session token signed with `SESSION_SIGNING_KEY` (HMAC-SHA256, `SESSION_TTL_MINUTES`,
default 15). The data tools take that token and filter by its customer; a bad,
expired or forged token gets the error `session_invalid`. An unknown customer and a
wrong answer both return `failed`. After `IDENTITY_MAX_ATTEMPTS` failures (default 3)
the customer is `locked` for `IDENTITY_LOCKOUT_MINUTES` (default 15). The lockout is
kept in memory per server instance: with several Cloud Run instances each counts on
its own. Anyone holding the signing key can mint tokens, so keep it in Secret Manager.
On Cloud Run, also deploy with `--no-allow-unauthenticated` and grant `run.invoker`
only to the agent's service account.

**Who owns each limit.** The server enforces the identity limits, so it owns them
and reports them in every `verify_identity` answer (`attempts_left`, `locked_until`,
`expires_at`); the agent keeps no copy. The dispute window is the agent's policy
(`graphs/policy.Policy.window_days`), so the agent sends it as `window_days`; the
server only caps it at `MAX_SPAN_DAYS` (366).

`reference_date` anchors the
search window (the demo data ends 2026-06-18). Amounts are decimal strings;
missing `amount_usd`/`fraud_score` are returned as null, never imputed.
Column renaming lives only in `services/mapping.py`. JSON Schemas: `../../contracts/mcp`.

## Run (from the repo root, with uv)

```bash
uv sync --project apps/mcp-server
uv run --project apps/mcp-server pytest apps/mcp-server -q   # no GCP needed
gcloud auth application-default login                         # ADC for live queries
uv run --project apps/mcp-server bank-mcp                     # stdio; --http for streamable HTTP
uv run --project apps/mcp-server bank-mcp-token CLI-0001      # dev only: token for DEV_SESSIONS
```

Own env in `apps/mcp-server/.venv`, pinned by `apps/mcp-server/uv.lock`. The agent
starts this server through `MCP_SERVER_COMMAND` (see `.env.example`).

Config via env or `.env` (repo root or this folder): `BQ_PROJECT`/`GCP_PROJECT_ID`,
`BQ_DATASET`/`BIGQUERY_CURATED_DATASET`, `BQ_LOCATION`/`GCP_REGION`, and the required
`SESSION_SIGNING_KEY` (32+ characters). Defaults:
hackaton-509923, bank_curated, us-central1. After changing a tool signature run
`scripts/export_contracts.py`; `tests/test_contracts.py` fails while schemas are stale.
