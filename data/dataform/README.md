# Dataform: raw → curated

Seven curated table pipelines for project `hackaton-509923`, location `us-central1`. Each one
reads a fixed version of `bank_raw.<table>`, types and validates it, writes audit and
quarantine, and publishes `bank_curated.<table>` only if its gate passes. Run order, statuses
and the quality-rule summary: [data platform](../../docs/data-platform.md).

## Layout

- `definitions/<table>.js`: the DAG of each table.
- `includes/<table>_contract.js`: the executable contract (types, required fields, domains,
  rules); `includes/*_helpers.js`, `sql_helpers.js`: shared SQL generation.
- `tests/`: local generation tests (`node tests/test.js`).
- `upload_workspace.py`, `execute_compilation.py`: upload/compile and run from Cloud Shell.
- `verify_<table>.sql`: checks to run in BigQuery after a run.
- `prepare.sh`: one-time GCP setup.

## How a table pipeline works (customers as the example)

`<table>_input → _typed → _classified → _candidate → checks → record_quality (audit + quarantine) → publish_gate (assertion) → bank_curated.<table>`

- Reads a fixed version of raw with time travel into a table isolated by `run_id`; staging keeps
  the original, a fingerprint and the input timestamp (7 days).
- Normalizes spaces and known domain values (e.g. México → Mexico, Pasaporte → Passport); blanks → NULL.
- Converts to DATE, TIMESTAMP, NUMERIC, INT64 and BOOL. Failed conversions are errors, not accepted NULLs.
- Validates required fields, lengths, catalogs and numeric ranges, with no silent rounding.
- Collapses only exact duplicate rows; keys with different content are rejected.
- Writes quarantine and metrics **before** the assertion that blocks publication.
- Reconciliation: input = accepted + rejected + discarded identical copies.
- Publishes all valid rows and sets `SUCCEEDED` in one BigQuery transaction. On failure the previous
  content stays. Publications are full replacements, not incremental.
- No imputation or invented enrichment. Timestamps without a zone are read as UTC (to be confirmed
  with the source).

Every compilation/run needs a new `run_id`. The default `preview` is for inspecting the graph and is
blocked from executing.

## Setup (once)

`bash prepare.sh` (admin identity) creates the datasets and the dedicated account, grants the
permissions and enables Dataform. It does not create the repository or run models.

1. Datasets in `us-central1`: `bank_stage`, `bank_quarantine` (plus existing `bank_raw`, `bank_ops`,
   `bank_curated`).
2. Dataform repository `bank-transformations` in `us-central1`, workspace `development`.
3. Execution identity `bank-curation@hackaton-509923.iam.gserviceaccount.com`: BigQuery Job User on the
   project, Data Viewer on `bank_raw`, Data Editor on `bank_stage`, `bank_quarantine`, `bank_ops`,
   `bank_curated`.
4. The Dataform service agent needs Service Account User and Token Creator on that account; the user
   who starts runs needs Service Account User on it.

## Upload, compile and run

From Cloud Shell, in `data/dataform`:

```bash
node tests/test.js
python3 upload_workspace.py            # uploads the project, installs deps, compiles with a new run_id
# Only after COMPILED, one table at a time:
python3 execute_compilation.py --table <table>
```

`upload_workspace.py` uses a temporary token from your gcloud session; it runs no queries. If
compilation reports missing dependencies, use *Install packages* in the workspace and compile again.
`execute_compilation.py` starts the DAG and can replace the curated table if the checks pass; it never
resubmits a compilation it already sent. Then run `verify_<table>.sql`. On `main`, the `Sync Dataform`
GitHub workflow does the upload and compile automatically (not the run).

Never run two publications of the same table at once, or all tags together.

## Audit

- `bank_ops.curation_runs`: serialized contract, version, input timestamp, status, counts, pending rules.
- `bank_ops.curation_results`: reconciliation, rejection, key and observation checks.
- `bank_ops.curation_references`: reference snapshots and run IDs used from other tables.
- `bank_quarantine.<table>_rejected`: original values and error codes; restrict access.
- Retention: audit and quarantine 30 days, staging 7 days.
- Intermediate failures can leave `RUNNING`/`VALIDATED`; the Dataform invocation status is the reference.

```sql
SELECT run_id, status, input_rows, published_rows, contract_version, pending_rules
FROM `hackaton-509923.bank_ops.curation_runs` ORDER BY started_at DESC LIMIT 10;
```

Expected counts below come from the profiled data; they are computed at run time, never hard-coded.
Local tests check contracts and generated SQL, not BigQuery execution.

## Tables

### customers
Strict: any rejection blocks publication (`maxRejectedRows: 0`). Credit score integer 300–850, income
DECIMAL(12,2). Chronology observations are WARN. FK `registration_branch_id → branches` is pending
(recorded in `pending_rules`). Expected: 150000 rows, 0 rejections.

### products
Requires customers published (uses the customers version published at the start). Every row with a
repeated product number goes to quarantine (`duplicate_product_number`), no winner chosen; only that
reason allows partial publication, other errors block. `product_type` keeps the eight observed Spanish
labels. `opening_branch_id → branches` is pending. Expected: `SUCCEEDED_WITH_REJECTIONS`, 400000 in,
399988 published, 12 quarantined.

### transactions
Requires customers and products. Rejects all repeated `transaction_id`s and blocks. Partial publication
only for `product_id.quarantined_parent` (product in the products quarantine). Unknown customer,
unexplained product or a different owner block. Earlier process date, incomplete coordinates, negative
amounts and currency different from the product are WARN; `process_date` and `transaction_date` are
never shifted. Partitioned by `process_date`, clustered by `product_id, customer_id`. `branch_id` FK,
currency dictionary and timezone pending. Expected: 4425008 in, 4424878 published, 130 rejected.

### complaints
Requires customers and products. 27 fields; no closed catalog for category/subcategory/currency.
A different owner is WARN, not a rejection: `_product_owner_mismatch` (TRUE differs, FALSE matches, NULL
not evaluable) and `_quality_warnings` per row. A complaint linked to a product does not prove
ownership. Only `affected_product_id.quarantined_parent` allows partial publication. Dates are kept;
the time offset is an unconfirmed hypothesis. Chronology, negatives, missing currency and currency
different from the product are per-row warnings. Partitioned by `process_date`, clustered by
`customer_id, affected_product_id`. Expected: 67095 in, 67094 published, 1 quarantined, 44569 owner
mismatches, 22525 not comparable (empty product).

### branches
22 typed columns; México → Mexico, Urbana → Urban. TIME hours without zone, non-negative counts,
coordinates NUMERIC (scale 7) within geographic ranges. Closed branches are kept. Unique PK and
`branch_code`; any rejection blocks. Equipment/flag coherence, overnight hours and incomplete
coordinates are WARN. Expected: 350 published, 0 rejected.

### service_agents
Every row with a duplicated `employee_code` is quarantined; only that reason allows partial
publication. A repeated `agent_id` blocks. A missing assigned branch is an approved WARN exception:
the source ID is kept and `_branch_reference_status` is `NOT_PROVIDED`, `UNRESOLVED` or `RESOLVED`.
CSAT scale 2, range 1–5; `languages` stays text. Expected: 1200 in, 1174 published, 26 quarantined,
811 published with an unresolved branch.

### daily_exchange_rates
Independent of other tables. Composite key `date / source_currency / target_currency`; all
duplicate-key rows rejected and any rejection blocks. NUMERIC rates DECIMAL(12,6), strictly positive.
Buy vs sell, rate outside the interval, same-currency non-unit rate and calendar gaps are WARN. No
rounding, inversion, interpolation, forward-fill or synthetic rows; consumers must handle a missing
date/pair. Clustered by `source_currency, target_currency`. Expected: 13164 rows, 12 directed pairs,
1097 dates each, 2023-06-17 to 2026-06-17.
