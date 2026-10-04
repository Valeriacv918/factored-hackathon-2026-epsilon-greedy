# factored-hackathon-2026-epsilon-greedy

AI-first **transaction-dispute intake** agent for a LATAM bank (Spanish and Portuguese), built for the Factored AI & Data Hackathon 2026.

> The LLM understands and writes. Deterministic code decides, acts and verifies.

## Status

This repository combines the existing analysis notebook with the GCP data
pipelines, a LangGraph agent and an MCP server.
The agent runs an executable six-component LangGraph workflow (Spanish and
Portuguese) and talks to a read-only MCP server over BigQuery. MCP write tools
and the end-to-end deployed application remain pending. See
[agent setup](apps/agent/README.md) and [MCP server](apps/mcp-server/README.md).

## Repository structure

```text
apps/
  agent/                 # LangGraph workflow, nodes, service contracts, tests (+ tests/integration: live agent -> MCP)
  mcp-server/            # MCP: tools, services, repositories, sql, config, tests
data/
  ingestion/            # Existing Cloud Run ingestion engine and tests
  contracts/raw/        # Available structural CSV contracts
  profiling/            # BigQuery profiles and diagnostics
  dataform/             # Curated contracts, transformations and execution scripts
contracts/mcp/          # Future tool input/output schemas
config/environments/    # Future non-secret application configuration
infra/                  # cloud-run, workflows, iam placeholders
scripts/                # deploy, run, verify
evals/                 # Synthetic cases, runners and local result conventions
docs/                  # Architecture, operations, quality and existing policies
profiling.ipynb         # Existing local analysis notebook (preserved)
pyproject.toml          # Existing analysis dependencies (preserved)
uv.lock                 # Existing dependency lock (preserved)
.python-version         # Existing Python version (preserved)
```

## Local analysis setup

With Git and uv installed:

```bash
git clone https://github.com/Valeriacv918/factored-hackathon-2026-epsilon-greedy.git
cd factored-hackathon-2026-epsilon-greedy
uv sync --locked
```

The root Python environment is only the analysis environment (duckdb, pandas,
tabulate for the notebook). Each app is its own uv project with its own `.venv`
and `uv.lock`: see [apps/agent](apps/agent/README.md) and
[apps/mcp-server](apps/mcp-server/README.md). CI runs each app's tests in its own
environment (`.github/workflows/python-tests.yml`).
`.env.example` describes app settings;
the existing data scripts do not automatically read it.

## Testing

Tests run per app, each in its own environment; there is no repository-wide `pytest`.

| Layer | Where | Runs in CI | How |
|---|---|---|---|
| Agent unit tests | `apps/agent/tests/` | yes | `uv run --project apps/agent pytest apps/agent` |
| MCP server unit tests | `apps/mcp-server/tests/` | yes | `uv run --project apps/mcp-server pytest apps/mcp-server` |
| Live integration (agent → MCP → BigQuery) | `apps/agent/tests/integration/` | no (opt-in) | `uv run --project apps/agent pytest apps/agent -m integration` |
| LLM quality evaluations | `evals/` | no | metrics, not pass/fail |
| Data pipeline checks | `data/ingestion`, `data/dataform/tests` | Dataform only | `python scripts/verify/check_local.py` (see below) |

Unit tests need no network, GCP or model. Integration tests need ADC and
`SESSION_SIGNING_KEY` plus `DEV_SESSIONS=dev=<token>`, with the token from
`uv run --project apps/mcp-server bank-mcp-token <customer_id>`. Layout and conventions:
[apps/agent/tests](apps/agent/tests/README.md), [apps/mcp-server/tests](apps/mcp-server/tests/README.md).

## Data and source files

`data/` now contains **versioned pipeline source code**. Dataset files are not
versioned: `.gitignore` excludes CSV, Parquet, Avro and generated deliveries.
The existing notebook keeps its `data/<table_name>/**/*.csv` paths; place local
input data there as needed without changing the notebook. Do not replace the
source subdirectories with dataset exports.

Do not commit credentials, runtime .env files, service account keys, notebook
outputs containing customer data, or `last_compilation.json`. Git ignore rules
do not remove sensitive content from an already tracked notebook; review its
outputs before committing notebook changes.

## GCP pipelines

Existing target: project `hackaton-509923`, region `us-central1`.
Review configuration and permissions before running cloud commands.

- Ingestion: `data/ingestion` validates CSV contracts, reconciles row counts,
  publishes raw tables and writes audit events.
- Transformation: `data/dataform` contains the seven curated table pipelines.
- Profiling: `data/profiling` writes observations to BigQuery audit tables.
- Orchestration across Cloud Run and Dataform remains pending.

In Cloud Shell, from the repository root:

```bash
cd data/dataform
python3 upload_workspace.py
# Only after COMPILED, select the intended table:
python3 execute_compilation.py --table daily_exchange_rates
```

These commands upload and execute cloud work. They are not local setup commands.
Wait for completion, then use the corresponding `verify_*.sql`. Do not execute
all tags together or concurrent runs. See [the runbook](docs/runbook.md).
`data/ingestion/setup.sh` provisions resources and deploys customers; it is not
a routine command or a deployment script for every existing job.

All seven structural raw contracts are now present. The missing four were recovered
from the October 1 GCP export; see [contract inventory](data/contracts/raw/README.md)
and [GCP audit results](docs/gcp-audit-2026-10-01.md). The `Sync Dataform` GitHub
Actions workflow now validates, uploads, and compiles Dataform changes on `main`;
it becomes active after the one-time Workload Identity Federation setup in
[GitHub to Google Cloud](docs/github-gcp-connection.md). It does not execute SQL.

## Local verification

With Python and Node on PATH, run from the repository root:

```bash
python scripts/verify/check_local.py
```

This runs CSV validation unit tests and all seven Dataform generation tests.
It requires no cloud credentials and does not deploy anything. Full ingestion
integration mocks additionally require `data/ingestion/requirements.txt`.
Local tests do not replace Dataform compilation and BigQuery execution.

## Documentation

- [Architecture](docs/architecture.md)
- [Operations and recovery](docs/runbook.md)
- [Data quality rules and exceptions](docs/data-quality.md)
- [Business policy research](docs/policies.md)
- [Original profiling findings](docs/findings_tables.txt)
- [Migration inventory](docs/migration-inventory.md)

Each deployable component stays independently configurable. Future MCP tools
must handle data quality flags and unresolved references explicitly. A complaint
link to a product does not establish ownership or authorize product access.

## Submission checklist (due Oct 5 to hackathon.admin@factored.ai)

- [ ] Deployed link
- [ ] 4Ã¢â‚¬â€œ6 slide presentation
- [ ] Video pitch: working demo + core architecture decisions
- [ ] Demo cases in ES and PT: normal resolution, ambiguous/unsupported, human-required
