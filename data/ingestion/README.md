# Contract-based ingestion (GCS → bank_raw)

A parameterized Cloud Run job that loads one raw table from CSV files in GCS into BigQuery
`bank_raw`, after structural validation. One job per table (seven deployed; see
[data platform](../../docs/data-platform.md)).

## What it does

1. Blocks concurrent loads of the same table with a GCS precondition lock.
2. Reads the contract from GCS and records its content, hash and generation.
3. Lists the input files and pins their generations, sizes and CRC32C in a manifest.
4. Validates UTF-8, header names/order, field count and CSV syntax (no business rules here).
5. Copies those exact generations to a private operations bucket; BigQuery loads the copies, not a
   source that could change.
6. Loads a temporary table with all columns STRING/NULLABLE, rejecting malformed records.
7. Compares its row count with the CSV reader's count.
8. Publishes with an atomic copy that replaces `bank_raw.<table>`. The previous table stays if
   validation or the temporary load fails.
9. Writes events to GCS and BigQuery plus structured logs, including whether it published.

## Files

- `main.py`: the parameterized runner.
- `validation.py`: contract and structural validation.
- `audit.sql`: event table and audit views.
- `setup.sh`: creates resources and deploys the customers job from Cloud Shell (does not run it).
- `test_validation.py`, `test_pipeline.py`: contract/CSV tests and mocked cloud tests, no GCP access.
- `Dockerfile`, `requirements.txt`: the job image.

## Test and deploy

```bash
cd data/ingestion
python3 -m unittest -v       # test_pipeline.py also needs: pip install -r requirements.txt
bash setup.sh                # admin identity, Cloud Shell
```

`setup.sh` needs permissions to enable APIs, create service accounts, grant IAM, create datasets,
build images and deploy Cloud Run jobs. It never grants Owner. If a step returns `PermissionDenied`,
keep the exact error and fix only that permission. It creates:

- Bucket `hackaton-509923-ingestion-ops` (private, `us-central1`) for snapshots and audit.
- Service account `bank-ingestion@hackaton-509923.iam.gserviceaccount.com` with Storage Object Viewer
  on the source bucket, Storage Object Admin on the operations bucket, BigQuery Job User on the
  project, and BigQuery Data Editor on `bank_raw` and `bank_ops` only.
- Datasets `bank_raw` and `bank_ops` if missing; table `bank_ops.pipeline_events` and views
  `pipeline_runs`, `quality_results`.
- Artifact Registry repo `bank-pipeline` and job `bank-ingestion-customers`.

## Run

```bash
gcloud run jobs execute bank-ingestion-customers --project=hackaton-509923 --region=us-central1 --wait
```

No schedule and no automatic retries (`max-retries=0`). Re-running loads the selected snapshot
again without duplicates, because publication replaces the table.

Each job is configured with:

| Variable | Example (customers) |
|---|---|
| `SOURCE_URI` | `gs://factoredia_hackaton/dataset_v1_raw/data/customers.csv` (a URI ending in `/` selects every object under that prefix) |
| `CONTRACT_URI` | `gs://factoredia_hackaton/contracts/customers_v1.json` |
| `DESTINATION_TABLE` | `hackaton-509923.bank_raw.customers` |

Only uncompressed CSV, all matching the same contract, each with a header. Files are processed
sequentially with bounded memory; each field is limited to 10 MiB.

## Audit

```sql
SELECT * FROM `hackaton-509923.bank_ops.pipeline_runs` ORDER BY started_at DESC LIMIT 20;
SELECT * FROM `hackaton-509923.bank_ops.quality_results` ORDER BY event_time DESC LIMIT 30;
```

In Cloud Logging, filter by the Cloud Run job and `jsonPayload.run_id`. In GCS,
`gs://hackaton-509923-ingestion-ops/audit/<run_id>/` holds the contract, manifest, per-file validation
and events. Events contain no customer values, but BigQuery job details can include values rejected by
the parser: restrict diagnostic access.

## Failures and recovery

- Invalid contract or CSV: non-zero exit, `FAILED` event, previous raw table kept.
- Audit unavailable before publishing blocks the pipeline. If it fails after the final copy, GCS/logs
  record `published: true`; check the publish job before retrying.
- Cancellation, OOM or timeout can leave a lock under `locks/` and a run without a final event. Confirm
  in Cloud Run it is no longer active, then delete ONLY that lock object to retry.
- Do not run manual loads on the same table during a job: the lock only coordinates this pipeline.
- The temporary table expires after two days and is deleted at the end; if the process dies in between,
  delete it manually.

## Cost and retention

Batch loads only (no streaming). Jobs run only when invoked. Snapshots are deleted by lifecycle after
two days; audit is kept 30 days in GCS and BigQuery partitions. No alerts, dashboards or orchestration
are configured yet.
