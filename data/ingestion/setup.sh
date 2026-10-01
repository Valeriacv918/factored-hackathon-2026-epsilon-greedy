#!/usr/bin/env bash
# Run in Google Cloud Shell. Creates resources; does not execute ingestion.
set -euo pipefail
export PROJECT_ID="hackaton-509923"
export SOURCE_BUCKET="factoredia_hackaton"
export OPS_BUCKET="${PROJECT_ID}-ingestion-ops"
export REGION="us-central1"
export SA="bank-ingestion@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
LOCATION="$(gcloud storage buckets describe "gs://${SOURCE_BUCKET}" --format='value(location)' | tr '[:upper:]' '[:lower:]')"
if [[ "$LOCATION" != "$REGION" ]]; then
  echo "STOP: source bucket is in ${LOCATION}. Adjust region and dataset locations before deployment."
  exit 1
fi

gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com bigquery.googleapis.com storage.googleapis.com

if ! gcloud iam service-accounts describe "$SA" >/dev/null 2>&1; then
  gcloud iam service-accounts create bank-ingestion --display-name="Bank ingestion job"
fi

if ! gcloud storage buckets describe "gs://${OPS_BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${OPS_BUCKET}" --location="$REGION" \
    --uniform-bucket-level-access --public-access-prevention \
    --default-storage-class=STANDARD --soft-delete-duration=0
fi
cat > lifecycle.json <<'JSON'
{"rule":[
  {"action":{"type":"Delete"},"condition":{"age":2,"matchesPrefix":["staging/"]}},
  {"action":{"type":"Delete"},"condition":{"age":30,"matchesPrefix":["audit/"]}}
]}
JSON
gcloud storage buckets update "gs://${OPS_BUCKET}" --lifecycle-file=lifecycle.json

gcloud storage buckets add-iam-policy-binding "gs://${SOURCE_BUCKET}" \
  --member="serviceAccount:${SA}" --role=roles/storage.objectViewer
gcloud storage buckets add-iam-policy-binding "gs://${OPS_BUCKET}" \
  --member="serviceAccount:${SA}" --role=roles/storage.objectAdmin
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA}" --role=roles/bigquery.jobUser --condition=None

for dataset in bank_raw bank_ops; do
  if ! bq show "${PROJECT_ID}:${dataset}" >/dev/null 2>&1; then
    bq --location="$REGION" mk --dataset "${PROJECT_ID}:${dataset}"
  fi
  bq --location="$REGION" query --use_legacy_sql=false \
    "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`${PROJECT_ID}.${dataset}\` TO 'serviceAccount:${SA}'"
done

bq --location="$REGION" query --use_legacy_sql=false < audit.sql

if ! gcloud artifacts repositories describe bank-pipeline --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create bank-pipeline --repository-format=docker --location="$REGION"
fi
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/bank-pipeline/ingestion:v1"
gcloud builds submit --tag "$IMAGE" .
gcloud run jobs deploy bank-ingestion-customers --image="$IMAGE" \
  --region="$REGION" --service-account="$SA" \
  --tasks=1 --parallelism=1 --max-retries=0 --task-timeout=3600s \
  --cpu=1 --memory=512Mi \
  --set-env-vars="PROJECT_ID=${PROJECT_ID},BQ_LOCATION=${REGION},OPS_BUCKET=${OPS_BUCKET},AUDIT_DATASET=bank_ops,SOURCE_URI=gs://${SOURCE_BUCKET}/dataset_v1_raw/data/customers.csv,CONTRACT_URI=gs://${SOURCE_BUCKET}/contracts/customers_v1.json,DESTINATION_TABLE=${PROJECT_ID}.bank_raw.customers,PIPELINE_VERSION=1.0.0"
echo "Deployment complete. No ingestion has run. See README for execution command."
