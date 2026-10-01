#!/usr/bin/env bash
# Creates datasets and a dedicated execution identity, without running SQL models.
set -euo pipefail
PROJECT_ID="hackaton-509923"
REGION="us-central1"
SA="bank-curation@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud services enable dataform.googleapis.com bigquery.googleapis.com iam.googleapis.com --project="$PROJECT_ID"
if ! gcloud iam service-accounts describe "$SA" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create bank-curation --project="$PROJECT_ID" --display-name="Dataform bank curation"
fi
for dataset in bank_stage bank_quarantine bank_ops bank_curated; do
  if ! bq --project_id="$PROJECT_ID" show "${PROJECT_ID}:${dataset}" >/dev/null 2>&1; then
    bq --project_id="$PROJECT_ID" --location="$REGION" mk --dataset "${PROJECT_ID}:${dataset}"
  fi
  LOCATION="$(bq --project_id="$PROJECT_ID" show --format=prettyjson "${PROJECT_ID}:${dataset}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["location"].lower())')"
  if [[ "$LOCATION" != "$REGION" ]]; then
    echo "STOP: ${dataset} is in ${LOCATION}, expected ${REGION}"; exit 1
  fi
  bq --project_id="$PROJECT_ID" --location="$REGION" query --use_legacy_sql=false \
    "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`${PROJECT_ID}.${dataset}\` TO 'serviceAccount:${SA}'"
done
bq --project_id="$PROJECT_ID" --location="$REGION" query --use_legacy_sql=false \
  "GRANT \`roles/bigquery.dataViewer\` ON SCHEMA \`${PROJECT_ID}.bank_raw\` TO 'serviceAccount:${SA}'"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA}" --role=roles/bigquery.jobUser --condition=None
gcloud beta services identity create --service=dataform.googleapis.com --project="$PROJECT_ID"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
AGENT="service-${PROJECT_NUMBER}@gcp-sa-dataform.iam.gserviceaccount.com"
for role in roles/iam.serviceAccountUser roles/iam.serviceAccountTokenCreator; do
  gcloud iam service-accounts add-iam-policy-binding "$SA" --project="$PROJECT_ID" \
    --member="serviceAccount:${AGENT}" --role="$role" --condition=None
done
echo "Prepared. Create repository bank-transformations and workspace development in Dataform (us-central1), using ${SA}. No model has run."
