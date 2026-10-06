# factored-hackathon-2026-epsilon-greedy

AI-first **transaction-dispute intake** agent for a LATAM bank (Spanish and Portuguese), built for the Factored AI & Data Hackathon 2026.

> The LLM understands and writes. Deterministic code decides, acts and verifies.

## Status

This repository combines the existing analysis notebook with the GCP data
pipelines, a LangGraph agent and an MCP server.
The deployed web application runs the LangGraph identity-validation and triage
flow in Spanish and Portuguese and talks to an MCP server over BigQuery. It
detects the conversation language before identity verification, asks the user
to choose Spanish or Portuguese when a short greeting is ambiguous, and keeps
the selected language throughout the forms and responses. Identity factors are
submitted through a form directly to MCP verification, not sent to the LLM.
The MCP server reads `bank_curated` and records simulated card blocks, disputes,
handoffs and notifications in `bank_sandbox`
([MCP and sandbox](docs/mcp-sandbox.md)).

**Live web app:** [Epsilon Bank](https://bank-agent-web-jpr3xtgwsa-uc.a.run.app)
on Cloud Run in `us-central1`. The app, MCP subprocess configuration and
Spanish/Portuguese language-selection flow are deployed. See the
[web deployment guide](docs/deploy-web.md), [agent setup](apps/agent/README.md)
and [MCP server](apps/mcp-server/README.md) for implementation details and
operational limits. Account tools remain pending.

## Try it online

### 👉 [Open the live demo](https://bank-agent-demo-676773032351.us-east4.run.app/)

https://bank-agent-demo-676773032351.us-east4.run.app/

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
| **Docs** | `docs/` (architecture, state machine, MCP/sandbox, deploy, data platform) |

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
│   └── inventory/              GCP inventory snapshot (2026-10-01)
│
├── evals/cases/                Triage evaluation set and runner
├── scripts/
│   ├── run_disputes.py         Terminal demo of the full flow (also chat_*.py, try_triage.py)
│   └── verify/                 Local checks (check_local.py, sandbox_contract.py, audits)
├── docs/                       Architecture, state machine, MCP/sandbox, deploy, data platform
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
| Data pipeline checks | `data/ingestion`, `data/dataform/tests`, `infra/bigquery/sandbox` | Dataform source sync/compile only | `python scripts/verify/check_local.py` (see below) |

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

## Data engineering status

Project `hackaton-509923`, region `us-central1`. Review configuration and permissions
before running cloud commands.

- **Raw contracts:** all seven structural contracts are versioned in
  `data/contracts/raw/`.
- **Ingestion:** `data/ingestion` implements CSV contract validation, row-count
  reconciliation, raw-table publication and audit events. The GCP audit
  recorded seven Cloud Run Jobs with successful latest runs as of October 1,
  2026; this is a point-in-time snapshot, not a live status check.
- **Transformation:** `data/dataform` contains seven curated table pipelines,
  contracts, generation tests and table verification queries.
- **Profiling:** `data/profiling` contains BigQuery profiling and diagnostic
  queries for the source tables.
- **Dataform CI:** the `Sync Dataform` GitHub Actions workflow validates,
  uploads and compiles source on `main`. Its latest recorded successful run was
  October 3, 2026. It does not execute SQL or publish curated tables.
- **Still to automate:** there is no end-to-end orchestrator connecting the
  Cloud Run ingestion jobs to Dataform, and curated-table execution remains a
  separate, reviewed operation. The initial orchestration area is documented
  in [`infra/workflows`](infra/workflows/README.md); the GCP audit and
  [Dataform guide](data/dataform/README.md) describe the execution boundaries.

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
and [GCP audit results](docs/gcp-audit-2026-10-01.md). GitHub-to-GCP
authentication for the Dataform workflow is configured; see
[GitHub to Google Cloud](docs/github-gcp-connection.md). The workflow compiles
changes but does not execute SQL.
- **Ingestion** (`data/ingestion`): validates CSV contracts, reconciles row counts,
  publishes raw tables and writes audit events.
- **Transformation** (`data/dataform`): the seven curated table pipelines. The
  `Sync Dataform` GitHub workflow validates, uploads and compiles them on `main`
  ([setup](docs/github-gcp-connection.md)); running a table stays a manual step.
- **Profiling** (`data/profiling`): writes observations to BigQuery audit tables.
- **Sandbox** ([infra/bigquery/sandbox](infra/bigquery/sandbox/README.md)): storage for
  the simulated actions, deployed separately from Dataform.

Run order, statuses, quality rules and the GCP audit: [data platform](docs/data-platform.md).

## Local verification

With Python and Node on PATH, run from the repository root:

```bash
python scripts/verify/check_local.py
```

This runs CSV validation unit tests, Dataform generation tests and sandbox
contract checks. It requires no cloud credentials and does not deploy anything.
The GitHub workflow separately validates and compiles Dataform source; neither
local checks nor compilation replace reviewed BigQuery table execution.

## Documentation

- [Architecture](docs/architecture.md)
- [Conversation state machine](docs/state-machine.md)
- [MCP and sandbox](docs/mcp-sandbox.md)
- [Web front and deployment](docs/deploy-web.md)
- [Logging and observability](docs/observability.md)
- [Data platform: operations, quality and audit](docs/data-platform.md)
- [GitHub to Google Cloud](docs/github-gcp-connection.md)
- [Original profiling findings](docs/findings_tables.txt)
- [Migration inventory](docs/migration-inventory.md)

Each deployable component stays independently configurable. Future MCP tools
must handle data quality flags and unresolved references explicitly. A complaint
link to a product does not establish ownership or authorize product access.

## Submission checklist (due Oct 5 to hackathon.admin@factored.ai)

- [x] Deployed link: [Epsilon Bank](https://bank-agent-web-jpr3xtgwsa-uc.a.run.app)
- [ ] 4-6 slide presentation
- [ ] Video pitch: working demo + core architecture decisions
- [ ] Demo cases in ES and PT: normal resolution, ambiguous/unsupported, human-required

## Banking sandbox (data engineering)

The simulation storage is versioned in
[infra/bigquery/sandbox](infra/bigquery/sandbox/README.md), with its
[versioned contract](data/contracts/sandbox/bank_sandbox_v1.json).
It includes scenario isolation, effective card-state queries, receipt checks,
and quality audits. Deployment is separate from Dataform. Cloud Shell results
shared on October 4 confirm the schema, permissions checks and one persisted
simulated card block with its audit. See the [handoff](docs/sandbox-handoff.md)
for evidence and limits. The MCP server writes card blocks, disputes, handoffs and
notifications to it; see [MCP and sandbox](docs/mcp-sandbox.md). Account tools are still pending.

Offline check: `python scripts/verify/sandbox_contract.py --check`.
- Component READMEs: [agent](apps/agent/README.md), [MCP server](apps/mcp-server/README.md),
  [Dataform](data/dataform/README.md), [ingestion](data/ingestion/README.md),
  [sandbox](infra/bigquery/sandbox/README.md), [evals](evals/cases/README.md)
