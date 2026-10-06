# MCP server tests

From the repo root:

```bash
uv sync --project apps/mcp-server
uv run --project apps/mcp-server pytest apps/mcp-server                 # unit: no GCP or network (CI)
uv run --project apps/mcp-server pytest apps/mcp-server -m integration  # BigQuery dry run (opt-in)
```

| File | Covers |
|---|---|
| `conftest.py` | `FakeGateway` (answers by tool name and records every query), a known signing key, clean server state; fixtures `gateway`, `token`, `signing_key` |
| `test_contracts.py` | `contracts/mcp/*.json` matches the tool signatures (regenerate with `scripts/export_contracts.py`) |
| `test_identity.py` | `verify_identity`: normalized parameters, signed token, attempts and lockout |
| `test_session.py` | Session tokens (signature, expiry, tampering) and `LoginThrottle` |
| `test_mapping.py` | BigQuery rows → agent fields (`services/mapping.py`) |
| `test_search.py` | Parameterized `find_transactions` query (slots, date window, amount tolerance) |
| `test_timezones.py`, `test_fx.py` | Local-day date windows; currency conversion |
| `test_sandbox.py` | Sandbox tools: scenario, token customer, hashes, receipts, refusals, handoff packet schema |
| `test_charge_results.py` | `save_charge_explanation`: ownership, session, receipts and retries |
| `test_observability.py` | JSON logging |
| `test_sql_dry_run.py` | `integration`: compiles every statement of `sql/queries.py` in BigQuery with a dry run (reads and writes nothing) |

**What unit tests do not cover.** `FakeGateway` returns the rows the test gives it, so the tests
check what Python decides and sends, not the SQL: ownership, eligibility and deduplication live in
the queries. The dry run catches compilation and permission errors; query behavior is checked live
(see `docs/mcp-sandbox.md`). To check deployment permissions, run the dry run impersonating `bank-mcp`.

The agent's live tests against this server are in `apps/agent/tests/integration/`. Same
conventions as `apps/agent/tests/README.md`: no `__init__.py`, helpers as fixtures in
`conftest.py`, import `bank_mcp...`.
