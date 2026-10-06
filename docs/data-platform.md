# Data platform: operations, quality and audit

Project `hackaton-509923`, region `us-central1`. Pipeline details:
[data/ingestion](../data/ingestion/README.md) and [data/dataform](../data/dataform/README.md).

## Running the pipelines

1. Check the project, quotas and source data.
2. Run the matching Cloud Run ingestion job and wait for its result.
3. Run the profiles (`data/profiling`) if the source changed or the contract needs a diagnosis.
4. In `data/dataform`: `upload_workspace.py`, wait for `COMPILED`, then
   `execute_compilation.py --table <table>`. Each submission uses a new compilation and `run_id`.
5. Wait for Dataform and run the matching `verify_*.sql`.

**Order** required by current references: branches before service_agents; customers before
products; customers and products before transactions and complaints. daily_exchange_rates is
independent.

**Statuses.** `VALIDATED` does not mean published. `SUCCEEDED_WITH_REJECTIONS` is an approved
partial success: review WARN rows and quarantine. Never resubmit the same compilation. No
concurrent runs per curated table. Publications are full replacements, not incremental.
Intermediate failures can leave audit rows `RUNNING`/`VALIDATED`: check Dataform too.
Retention: staging 7 days, curated audit and quarantine 30 days.

The `Sync Dataform` GitHub Actions workflow validates, uploads and compiles Dataform changes on
`main` (it does not execute SQL); setup in [GitHub to Google Cloud](github-gcp-connection.md).

## Quality rules and exceptions

The executable source is `data/dataform/includes/*_contract.js` and `definitions/`.

| Table | Rule |
|---|---|
| customers | Strict publication; Mexico/Passport normalization. |
| products | Repeated product numbers go to quarantine; other errors block. |
| transactions | A parent in quarantine allows partial rejection; unknown customer/product without explanation, or a different owner, blocks. |
| complaints | A different owner is WARN with a per-row flag, not proof of ownership. |
| branches | Unique keys, domain Urbana → Urban, strict publication. |
| service_agents | Repeated codes go to quarantine; an unknown branch is a WARN exception, keeping the ID and its resolution status. |
| daily_exchange_rates | Composite key, positive rates and strict 12,6 precision; no filling or inverting rates. |

Do not treat earlier dates as automatically correctable: a time offset is an unconfirmed
hypothesis. Never impute amounts or currency. Some branch/agent/interaction foreign keys are
still pending where the contract says so. MCP tools must respect these flags: never ignore a
warning to attribute ownership or a branch.

## GCP audit

`scripts/verify/audit_gcp.py` is a read-only collector, run in an authenticated Cloud Shell
with `scripts/verify/audit_baseline.json` (generated from the repo; regenerate hashes after
source changes). It only makes GET API calls (auth via `gcloud auth print-access-token`): no
writes, SQL, deployments or pipeline runs. It collects Dataform workspace file hashes, recent
invocation metadata, ingestion job configuration (allowlisted env values), storage settings,
structural contract fields, BigQuery schemas and row counts. Tokens are never written; denied
resources produce `PARTIAL`. Output: a local `report.json` plus structural contract exports in a
ZIP (do not commit them). Collection is not atomic and does not check effective IAM.

**Result on 2026-10-01** (18:29 America/Bogota; snapshot in
[infra/inventory](../infra/inventory/README.md)):

- 23/23 Dataform sources match the repo by SHA-256; raw and curated schemas match the contracts.
- 7 Cloud Run jobs, last run successful, same image digest, service account `bank-ingestion`;
  Dataform runs as `bank-curation`. 5 datasets and 2 buckets in `us-central1`.
- The four missing raw contracts were recovered from this export
  ([data/contracts/raw](../data/contracts/raw/README.md)).

| Table | Raw rows | Curated rows |
|---|---:|---:|
| customers | 150000 | 150000 |
| products | 400000 | 399988 |
| transactions | 4425008 | 4424878 |
| complaints | 67095 | 67094 |
| branches | 350 | 350 |
| service_agents | 1200 | 1174 |
| daily_exchange_rates | 13164 | 13164 |

Still open: end-to-end orchestration across Cloud Run and Dataform, image provenance, and an
effective-permissions review.
