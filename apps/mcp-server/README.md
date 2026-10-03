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

## Run (PowerShell, from apps/mcp-server)

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[test]"
.venv/Scripts/python.exe -m pytest -q             # no GCP needed
gcloud auth application-default login             # ADC for live queries
.venv/Scripts/python.exe -m bank_mcp              # stdio; --http for streamable HTTP
```

Config via env or `.env` (repo root or this folder): `BQ_PROJECT`/`GCP_PROJECT_ID`,
`BQ_DATASET`/`BIGQUERY_CURATED_DATASET`, `BQ_LOCATION`/`GCP_REGION`. Defaults:
hackaton-509923, bank_curated, us-central1. After changing a tool signature run
`scripts/export_contracts.py`; `tests/test_contracts.py` fails while schemas are stale.
