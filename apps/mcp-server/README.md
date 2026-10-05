# MCP

MCP server over `bank_curated` for the dispute agent. Bounded tools only;
no arbitrary SQL (see ../../docs/architecture.md). Card blocks, disputes, handoffs
and notifications are SIMULATED rows in `bank_sandbox`, inside one scenario; curated
is never modified. How the sandbox is used, and why:
[docs/mcp-sandbox.md](../../docs/mcp-sandbox.md). Account tools are not offered yet.

| Tool | Returns (agent field names, see agent `clients/README.md`) |
|---|---|
| verify_identity(document_number, date_of_birth, product_number) | status (verified / failed / locked), customer_id, session_token, product_numbers, attempts_left, locked_until, expires_at |
| find_transactions(session_token, reference_date, window_days, slots?, limit=3) | transactions[id, customer_id, card_id, status, fraud_score, amount, amount_usd, currency, date, merchant], has_more |
| list_cards(session_token) | cards[id, customer_id, last4, status, type] |
| get_card(session_token, card_id) | id, customer_id, last4, status, type |
| save_charge_explanation(session_token, conversation_id, transaction_id, observed_status) | result_id, transaction_id, observed_status, rule_id, verified |
| block_card(session_token, card_id, idempotency_key) | id (receipt) |
| read_block(session_token, id) | id, card_id, customer_id, status, verified |
| file_dispute(session_token, transaction_id, idempotency_key) | id (case) |
| read_dispute(session_token, id) | id, customer_id, transaction_id, status, verified |
| dispute_context(session_token, transaction_id) | existing_case_id, recent_dispute_count |
| create_handoff(session_token, packet, idempotency_key) | id (ticket) |
| read_handoff(session_token, id) | id, customer_id, verified |
| notify_employee(session_token, ticket_id, idempotency_key) | id (delivery) |
| read_notification(session_token, id) | id, ticket_id, customer_id, status, verified |

The last nine need `SANDBOX_SCENARIO_ID`. With it, `list_cards`/`get_card` return the
effective status (a sandbox block shows as `Blocked`) and `find_transactions` uses the
scenario clock instead of `reference_date`.

`save_charge_explanation` stores the fixed explanation (EXP-002/003/006) for a Pending,
Reversed or Declined transaction as a SIMULATED row in `bank_sandbox.agent_results`
(`infra/bigquery/sandbox/003_agent_results.sql`). It checks ownership and status in SQL,
is idempotent through a stable `result_id` (MERGE + fixed job id) and reads its row back
before returning `verified`. It does not need `SANDBOX_SCENARIO_ID` and is not
scenario-scoped. Details: [docs/validation-triage-local.md](../../docs/validation-triage-local.md).

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

## Verificación de identidad para el grafo local

`verify_identity(document_number, date_of_birth, product_number)` compara los tres
factores y la titularidad en BigQuery. `document_number` es el documento del cliente
(cédula, CURP, DNI); se ignoran espacios, puntos y guiones. El `customer_id` interno
no se acepta como entrada: se obtiene de la coincidencia.
En discordancia devuelve `status="failed"` con `attempts_left`, o `status="locked"`
con `locked_until`; nunca `customer_id`, `session_token` ni productos.
En coincidencia devuelve `status="verified"`, el `customer_id` interno, el
`session_token`, los `product_numbers` y `expires_at`; nunca la fecha de nacimiento
ni el documento. No es una herramienta para obtener datos antes de verificar.
Consulta parametrizada y limitada por el gateway; contrato en
`contracts/mcp/verify_identity.json`.
Los intentos, el bloqueo y la vigencia del token los controla el servidor
(`IDENTITY_MAX_ATTEMPTS`, `IDENTITY_LOCKOUT_MINUTES`, `SESSION_TTL_MINUTES`),
contando por documento y en memoria; IdentityValidator del cliente solo los
informa y respeta. El servidor HTTP no debe exponerse públicamente sin
autenticación y límites persistentes.

## Sandbox scenario

1. An admin creates the scenario with `infra/bigquery/sandbox/create_scenario.sql`
   (see `infra/bigquery/sandbox/README.md`); `bank-mcp` cannot create one.
2. Set `SANDBOX_SCENARIO_ID` (`.env` locally) and `SCENARIO_NOW` to its `scenario_clock`.
   On Cloud Run: `--set-env-vars SANDBOX_SCENARIO_ID=...` and
   `--service-account bank-mcp@hackaton-509923.iam.gserviceaccount.com` (never a key file).
3. Locally, run as `bank-mcp` through ADC:
   `gcloud auth application-default login --impersonate-service-account=bank-mcp@hackaton-509923.iam.gserviceaccount.com`
   (needs Token Creator on that account).

On start the server logs whether the sandbox tools are enabled.

**Idempotency.** Scope: table + scenario + customer + `idempotency_key`. `request_hash`
is the lowercase SHA-256 hex of `{"action": ..., <arguments>}` serialized with sorted
keys and no spaces (`services/sandbox.request_hash`). Same key and hash: the original
receipt. Same key, other arguments: error.

**Known limitations.**
- The conditional `INSERT ... SELECT` does not guarantee uniqueness under concurrent
  calls with the same key (BigQuery has no unique constraints).
- One scenario per server: every conversation shares it.
- `find_transactions` shows the curated status even after a dispute is filed.
- Every block, dispute, handoff and notification is SIMULATED; a notification reaches
  nobody (the table has no recipient).
- No account tools: a fraud case on an account (not a card) escalates, and a handoff
  packet's `suspended_accounts` must be empty.
- `recent_dispute_count` counts curated complaints only (subcategories
  `Cargo no reconocido`, `Cobro indebido`, 90 days before the scenario clock), so
  disputes filed during the scenario do not count toward DSP-011. Duplicates on the
  same transaction are still caught by `existing_case_id`.
