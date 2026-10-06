# Agent tests

They run in the agent's own environment (`apps/agent/.venv`), never the root one. From the repo root:

```bash
uv sync --project apps/agent                                 # once
uv run --project apps/agent pytest apps/agent                # unit tests (default, and CI)
uv run --project apps/agent pytest apps/agent -m integration # live integration (opt-in)
```

From `apps/agent`, `uv run pytest` (or `uv run pytest -m integration`) is enough.

## Layout

| File | Covers |
|---|---|
| `conftest.py` | `FakeServices` and the `fake_services` fixture: in-memory synthetic services |
| `test_graph.py` | Older general graph (`disputes.py`): ES/PT, confirmations, customer isolation, sessions, policies, retries, verification, blocks, disputes and escalation |
| `test_validation_triage_graph.py`, `test_full_flow.py`, `test_follow_up.py` | Main graph: MCP identity validation, triage, all routes, follow-up requests |
| `test_charge_test_graph.py`, `test_fraud_test_graph.py`, `test_card_emergency_test_graph.py` | Each route wired into the main graph |
| `test_scenarios_*.py`, `test_out_of_scope.py` | Full conversations per path (not_me / charge_error, card emergency, out of scope) |
| `test_sessions.py` | Session resolution (`StaticSessions`, `ValidatorSessions`) and token expiry |
| `test_escalation_handoff.py` | Employee summary: claim check, fallback template, narrator and escalation |
| `test_mcp_services.py` | `McpServices` with a fake MCP client: allowed tools and arguments, session, clock; real language detector (lingua) |
| `test_mcp_client.py` | `McpToolClient` over stdio against `mcp_echo_server.py` (errors, timeouts) |
| `test_identity_client.py` | `McpIdentityChecker`: what it sends to `verify_identity` and how it reads answers |
| `test_understanding.py` | Extraction with a simulated LLM; slots aligned with `contracts/mcp` |
| `test_triage_*.py` | Triage contract, rules, router and classifier |
| `test_validator_*.py`, `test_scoped_language.py` | Identity validator and language, with synthetic data |
| `test_fraud_agent.py`, `test_card_emergency_service.py` | Fraud and card-emergency agents with in-memory repositories |
| `test_web.py` | Web app endpoints, conversation ownership, interrupts |
| `test_observability.py`, `test_failure_logging.py` | JSON logging and failure events |
| `integration/test_live_mcp.py` | Live: real MCP server and BigQuery (below) |

**Unit tests:** no network, GCP or models.

**Integration** (`integration/`, marker `integration`): starts the real MCP server with
`uv run --project apps/mcp-server bank-mcp` in its own environment and queries `bank_curated`
with your ADC credentials (see `apps/mcp-server/README.md`). Read only: with
`SANDBOX_SCENARIO_ID` it also tests sandbox reads, but never writes (a write adds rows to the
shared scenario). It uses the `dev` entry of `DEV_SESSIONS`, the same as
`run_disputes.py --session dev`. If missing, tests are skipped.

## Reading the result

- `N passed, M deselected`: default run; the M are integration tests, excluded on purpose by
  `addopts = "-m 'not integration'"` in `pyproject.toml`.
- With `-m integration` it is the opposite.
- *skipped* means a selected test could not run (e.g. `DEV_SESSIONS` or `uv` missing), not a failure.

## Conventions

- **No `__init__.py` in `tests/`.** It made pytest alter `sys.path` and broke imports.
- **Shared helpers are fixtures in `conftest.py`**, not modules imported by name.
- **Always import `bank_agent...`**, never `src.bank_agent...`: the package is installed, and
  `src.` loads a second copy (two `settings`, failing `isinstance`).
- A new test that needs GCP, network or a real model goes in `integration/` with the marker;
  everything else must run offline.

LLM quality (e.g. the triage set) is measured in `evals/`, not here: those are metrics, not
pass/fail tests.
