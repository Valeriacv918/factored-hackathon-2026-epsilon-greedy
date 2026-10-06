# factored-hackathon-2026-epsilon-greedy

AI-first **transaction-dispute intake** agent for a LATAM bank (Spanish and Portuguese), built for the Factored AI & Data Hackathon 2026.

> The LLM understands and writes. Deterministic code decides, acts and verifies.

## Status

This repository combines the GCP data pipelines, a LangGraph agent, its web front and an
MCP server. The agent runs an executable six-component LangGraph workflow (Spanish and
Portuguese) and talks to an MCP server over BigQuery. The server reads `bank_curated`
and records simulated card blocks, disputes, handoffs and notifications in
`bank_sandbox` ([MCP and sandbox](docs/mcp-sandbox.md)). The web front, the agent and
the MCP server (as a stdio subprocess) run in one container deployed on Cloud Run
([web front and deployment](docs/deploy-web.md)). See
[agent setup](apps/agent/README.md) and [MCP server](apps/mcp-server/README.md).

## Try it online

### 👉 [Open the live demo](https://bank-agent-web-676773032351.us-central1.run.app/)

https://bank-agent-web-676773032351.us-central1.run.app/

No setup needed. It's the same web app as the local run below, deployed on Cloud Run.
Card blocks, disputes and handoffs are simulated in the sandbox, never real.

## Quickstart (run locally)

Prerequisites:

- Git and [uv](https://docs.astral.sh/uv/).
- The gcloud CLI, signed in with application default credentials
  (`gcloud auth application-default login`) as an account that can read
  `hackaton-509923.bank_curated` and write `hackaton-509923.bank_sandbox`.
- A [Groq API key](https://console.groq.com/keys).

Steps, from a terminal:

```bash
git clone https://github.com/Valeriacv918/factored-hackathon-2026-epsilon-greedy.git
cd factored-hackathon-2026-epsilon-greedy
cp .env.example .env
```

Edit `.env` and fill the section **1. Required to run the web app**. The demo scenario
(`SANDBOX_SCENARIO_ID`, `SCENARIO_NOW`) is already filled in. Generate
`SESSION_SIGNING_KEY` with
`python -c "import secrets; print(secrets.token_urlsafe(48))"` and paste your
`GROQ_API_KEY`. The other sections can stay as they are.

```bash
uv sync --project apps/agent
uv sync --project apps/mcp-server
uv run --project apps/agent bank-web
```

Open http://localhost:8080. The agent starts the MCP server itself; JSON logs go to
stdout, or to `LOG_FILE` if set.

Terminal alternative: `uv run --project apps/agent scripts/run_disputes.py --session dev --flow full`.
It skips the identity form, so it needs `DEV_SESSIONS` (section 3 of `.env.example`).

To deploy on Cloud Run, see [web front and deployment](docs/deploy-web.md).

## Repository structure

| Area | Contents |
|---|---|
| **Applications** | `apps/agent` (LangGraph agent and web front) and `apps/mcp-server` (MCP tools over BigQuery) |
| **Data platform** | `data/` pipelines (ingestion, Dataform, profiling) and their contracts |
| **Infrastructure** | `infra/` (BigQuery sandbox) and the root `Dockerfile` (Cloud Run image) |
| **Quality** | `evals/` (LLM evaluations) and `scripts/verify/` (local checks) |
| **Docs** | `docs/` (architecture, state machine, operations, policies) |

```text
.
├── apps/
│   ├── agent/                  LangGraph agent + web front (own uv project)
│   │   ├── src/bank_agent/
│   │   │   ├── graphs/         Conversation graph, state and policy
│   │   │   ├── nodes/          Validator, triage, card emergency, fraud, charge error, escalation
│   │   │   ├── clients/        MCP client and service adapters
│   │   │   ├── prompts/        LLM prompts
│   │   │   └── web/            Web app (bank-web): API + static front
│   │   └── tests/              Unit tests; tests/integration: live agent → MCP
│   └── mcp-server/             MCP server over BigQuery (own uv project)
│       ├── src/bank_mcp/       tools, services, repositories, sql, config
│       └── tests/
│
├── contracts/mcp/              MCP tool input/output schemas
├── data/
│   ├── ingestion/              Cloud Run ingestion engine and tests
│   ├── dataform/               Curated contracts, transformations and execution scripts
│   ├── profiling/              BigQuery profiles and diagnostics
│   └── contracts/              Raw CSV contracts and the sandbox contract
│
├── infra/
│   ├── bigquery/sandbox/       Simulation storage: schema, grants, reads, audits
│   └── cloud-run/, workflows/, iam/, inventory/
├── config/environments/        Future non-secret application configuration
│
├── evals/                      Synthetic cases, runners and result conventions
├── scripts/
│   ├── run_disputes.py         Terminal demo of the full flow (also chat_*.py, try_triage.py)
│   └── verify/                 Local checks (check_local.py, sandbox_contract.py, audits)
├── docs/                       Architecture, state machine, operations, quality, policies
│
├── Dockerfile                  Web front + agent + MCP server in one Cloud Run image
├── .env.example                Configuration template (copy to .env)
└── pyproject.toml, uv.lock     Root analysis environment (not used by the apps)
```

## Testing

Tests run per app, each in its own environment; there is no repository-wide `pytest`.
Run `uv sync --project apps/<app>` once before testing an app.

| Layer | Where | Runs in CI | How |
|---|---|---|---|
| Agent unit tests | `apps/agent/tests/` | yes | `uv run --project apps/agent pytest apps/agent` |
| MCP server unit tests | `apps/mcp-server/tests/` | yes | `uv run --project apps/mcp-server pytest apps/mcp-server` |
| Live integration (agent → MCP → BigQuery) | `apps/agent/tests/integration/` | no (opt-in) | `uv run --project apps/agent pytest apps/agent -m integration` |
| LLM quality evaluations | `evals/` | no | metrics, not pass/fail |
| Data pipeline checks | `data/ingestion`, `data/dataform/tests` | Dataform only | `python scripts/verify/check_local.py` (see below) |

Unit tests need no network, GCP or model. Integration tests need, in `.env`:

1. Application default credentials (see Quickstart).
2. `SESSION_SIGNING_KEY` set.
3. A session token: `uv run --project apps/mcp-server bank-mcp-token <customer_id>`.
4. `DEV_SESSIONS=dev=<token>` with that token.

Layout and conventions:
[apps/agent/tests](apps/agent/tests/README.md), [apps/mcp-server/tests](apps/mcp-server/tests/README.md).
CI runs each app's tests in its own environment (`.github/workflows/python-tests.yml`).

## Analysis environment

The root Python project is only an analysis environment (duckdb, pandas, tabulate);
the apps do not use it. Each app is its own uv project with its own `.venv` and
`uv.lock`. To set it up, from the repository root: `uv sync --locked`.

## Data and source files

`data/` now contains **versioned pipeline source code**. Dataset files are not
versioned: `.gitignore` excludes CSV, Parquet, Avro and generated deliveries.
Do not replace the source subdirectories with dataset exports.

Do not commit credentials, runtime .env files, service account keys, or
`last_compilation.json`.

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
- [Conversation state machine](docs/STATE_MACHINE2.md)
- [Web front and deployment](docs/deploy-web.md) (Spanish)
- [MCP and sandbox](docs/mcp-sandbox.md)
- [Validation and triage local graph](docs/validation-triage-local.md) (Spanish)
- [Operations and recovery](docs/runbook.md)
- [Logging and observability](docs/observability.md)
- [Data quality rules and exceptions](docs/data-quality.md)
- [Business policy research](docs/policies.md)
- [Original profiling findings](docs/findings_tables.txt)
- [Migration inventory](docs/migration-inventory.md)

Each deployable component stays independently configurable. Future MCP tools
must handle data quality flags and unresolved references explicitly. A complaint
link to a product does not establish ownership or authorize product access.

## Banking sandbox (data engineering)

The simulation storage is versioned in
[infra/bigquery/sandbox](infra/bigquery/sandbox/README.md), with its
[versioned contract](data/contracts/sandbox/bank_sandbox_v1.json).
It includes scenario isolation, effective card-state queries, receipt checks,
and quality audits. Deployment is separate from Dataform. Cloud Shell results
shared on October 4 confirm the schema, permissions checks and one persisted
simulated card block with its audit. See the [handoff](docs/sandbox-handoff.md)
for evidence and limits. The MCP server writes card blocks, disputes, handoffs and
notifications to it; see [MCP and sandbox](docs/mcp-sandbox.md).

Offline check: `python scripts/verify/sandbox_contract.py --check`.
