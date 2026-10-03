# MCP

Read-only MCP server over `bank_curated` for the dispute agent. Bounded tools only;
no arbitrary SQL (see ../../docs/architecture.md). Writes (block, dispute, handoff)
and `dispute_context` are pending a decision on where writes are stored.

| Tool | Returns (agent field names, see agent `clients/README.md`) |
|---|---|
| find_transactions(customer_id, reference_date, slots?, limit=3) | transactions[id, customer_id, card_id, status, fraud_score, amount, amount_usd, currency, date, merchant], has_more |
| list_cards(customer_id) | cards[id, customer_id, last4, status, type] |
| get_card(customer_id, card_id) | id, customer_id, last4, status, type |

Every query filters by `customer_id`, which the caller must take from the
authenticated session, never from model output. `reference_date` anchors the
search window (the demo data ends 2026-06-18). Amounts are decimal strings;
missing `amount_usd`/`fraud_score` are returned as null, never imputed.
Column renaming lives only in `services/mapping.py`. JSON Schemas: `../../contracts/mcp`.

## Run (from the repo root, with uv)

```bash
uv sync --project apps/mcp-server --extra test
uv run --project apps/mcp-server pytest apps/mcp-server -q   # no GCP needed
gcloud auth application-default login                         # ADC for live queries
uv run --project apps/mcp-server bank-mcp                     # stdio; --http for streamable HTTP
```

Own env in `apps/mcp-server/.venv`, pinned by `apps/mcp-server/uv.lock`. The agent
starts this server through `MCP_SERVER_COMMAND` (see `.env.example`).

Config via env or `.env` (repo root or this folder): `BQ_PROJECT`/`GCP_PROJECT_ID`,
`BQ_DATASET`/`BIGQUERY_CURATED_DATASET`, `BQ_LOCATION`/`GCP_REGION`. Defaults:
hackaton-509923, bank_curated, us-central1. After changing a tool signature run
`scripts/export_contracts.py`; `tests/test_contracts.py` fails while schemas are stale.
