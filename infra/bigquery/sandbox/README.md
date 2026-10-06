# Banking sandbox v1

BigQuery storage for the simulated actions (card blocks, disputes, handoffs, notifications, charge
explanations) in `hackaton-509923`, `us-central1`. Every action is simulated; curated data is never
modified. How the MCP server uses it: [MCP and sandbox](../../../docs/mcp-sandbox.md).

## Files

- `001_schema.sql`: dataset and five tables; never replaces existing tables.
- `002_grants.sql`: the applied data grants (versioned; not run automatically).
- `003_agent_results.sql`: `agent_results` table for charge explanations and its grant.
- `verify_schema.sql`: compares columns/types/required with the contract.
- `create_scenario.sql`: registers a scenario, its clock and the curated reference runs.
- `preflight.sql`: requires a unique scenario and curated data without a run change.
- `cards_effective.sql`: cards with `baseline_status` and `effective_status`, by scenario/customer.
- `read_block.sql`, `read_dispute.sql`, `read_handoff.sql`, `read_notification.sql`: per-receipt
  verification (`verified=true` on exactly one row).
- `read_receipts.sql`: bounded history; does not certify each action.
- `audit_contract.sql`, `audit_references.sql`, `run_audit.sh`: quality and reference audits.
- `smoke_block.sh`: end-to-end block test in a new scenario.
- `test_reads.py`: emits BigQuery read tests with synthetic data.

The contract is `data/contracts/sandbox/bank_sandbox_v1.json` (version 1.0.0). Regenerate DDL and
audits with `python scripts/verify/sandbox_contract.py`; check consistency with `--check`. This
package deploys independently; the Dataform sync does not run it.

NOT NULL is enforced in storage. Domains, uniqueness and references are validated by the writer
(the MCP server) and audited afterwards. No unenforced keys are declared, so the optimizer never
assumes uniqueness that does not exist.

## First deployment (Cloud Shell, deploy identity)

```bash
set -euo pipefail
python3 scripts/verify/sandbox_contract.py --check
bq query --project_id=hackaton-509923 --location=us-central1 \
  --use_legacy_sql=false --maximum_bytes_billed=1000000000 \
  < infra/bigquery/sandbox/001_schema.sql
bq query --project_id=hackaton-509923 --location=us-central1 \
  --use_legacy_sql=false --maximum_bytes_billed=1000000000 \
  < infra/bigquery/sandbox/verify_schema.sql
```

Expected: jobs DONE, no failed ASSERT. Stop on any error. `IF NOT EXISTS` does not migrate an
incompatible table: write an explicit migration instead of dropping it. Do not run the whole
directory by glob.

## Create a scenario and audit it

Run as an admin, one creation at a time. Pick the clock from the case and the historical coverage
(the date below is an example).

```bash
set -euo pipefail
export SCENARIO_ID="demo-$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}"
bq query --project_id=hackaton-509923 --location=us-central1 \
  --use_legacy_sql=false --maximum_bytes_billed=1000000000 \
  --parameter="scenario_id:STRING:$SCENARIO_ID" \
  --parameter="created_by:STRING:$(gcloud config get-value account)" \
  --parameter="scenario_clock:TIMESTAMP:2026-06-17 12:00:00+00" \
  < infra/bigquery/sandbox/create_scenario.sql
bash infra/bigquery/sandbox/run_audit.sh "$SCENARIO_ID"
```

Then set `SANDBOX_SCENARIO_ID` and `SCENARIO_NOW` (the same clock) for the app.

The auditor writes to `artifacts/sandbox/<timestamp>/` (git-ignored) and exits non-zero on any
violation. The byte limit is per job, not a cumulative budget; do not raise it automatically.

Read tests without bank data or changes to permanent tables:

```bash
python3 infra/bigquery/sandbox/test_reads.py > /tmp/sandbox-read-tests.sql
bq query --project_id=hackaton-509923 --location=us-central1 \
  --use_legacy_sql=false --maximum_bytes_billed=300000000 < /tmp/sandbox-read-tests.sql
```

Full block test (creates a new scenario and keeps the simulated block as evidence; if it fails,
check whether it reached COMMIT before repeating):

```bash
bash infra/bigquery/sandbox/smoke_block.sh
```

## Runtime identity and permissions

Runtime account: `bank-mcp@hackaton-509923.iam.gserviceaccount.com` (attached to Cloud Run, or
impersonated locally; never JSON keys).

| Resource | Runtime role |
|---|---|
| Project | `roles/bigquery.jobUser` |
| `bank_curated` | `roles/bigquery.dataViewer` |
| `bank_sandbox` | `roles/bigquery.dataViewer` |
| `card_blocks`, `disputes`, `handoffs`, `notifications`, `agent_results` | `roles/bigquery.dataEditor` (table level) |
| `scenarios` | Read only (inherited from the dataset) |

The runtime identity is separate from the deploy and `bank-curation` identities; never grant Editor
on the project. Data Editor can modify and delete: it is **not** append-only, so the MCP server
exposes only closed actions. Grants are applied by an explicit admin deployment, not by a push.
Never test permissions with a real delete.

## Rules for writers

- `customer_id`, `scenario_id`, `actor_service` and `created_at` come from the server's trusted
  context, never from the model. Always insert with an explicit column list.
- `card_id` is `products.product_id` of a credit or debit card. A new block requires baseline
  `Active`; an already `Blocked` card needs no event; `Closed`/`Suspended` are rejected. No
  unblocking or later dispute transitions in v1.
- Notifications only allow `SIMULATED`: a receipt does not prove delivery. `handoffs.packet` is
  minimal JSON with no tokens.
- Keep curated (customers, products, transactions) frozen during a demo. Run IDs are not physical
  snapshots: preflight detects a run change, not manual edits inside a run. To re-curate, start a
  new scenario. Reset means a new scenario, never TRUNCATE.

Sources: [constraints](https://docs.cloud.google.com/bigquery/docs/primary-foreign-keys),
[DML](https://docs.cloud.google.com/bigquery/docs/data-manipulation-language),
[roles](https://docs.cloud.google.com/iam/docs/roles-permissions/bigquery).
