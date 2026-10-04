#!/usr/bin/env bash
# Smoke test for data engineering only. No agent or MCP implementation.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
cd "$repo_root"
test -f data/contracts/sandbox/bank_sandbox_v1.json
scenario="smoke-$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
evidence="$PWD/artifacts/sandbox/$scenario"
mkdir -p "$evidence"
printf '%s\n' "$scenario" > "$evidence/scenario_id.txt"
echo "SCENARIO: $scenario"
echo "EVIDENCE: $evidence"
trap 'echo "Stopped. Preserve the scenario ID and evidence; do not rerun blindly." >&2' ERR

python3 - "$evidence/smoke.sql" <<'PY'
from pathlib import Path
import sys
root=Path("infra/bigquery/sandbox")
def sql(name):
    body=(root/name).read_text(encoding="utf-8-sig").strip().rstrip(";")
    for key in ("scenario_id","customer_id","card_id","block_id"):
        body=body.replace("@"+key,"v_"+key)
    return body

prefix="""
DECLARE v_scenario_id STRING DEFAULT @scenario_id;
DECLARE v_customer_id STRING;
DECLARE v_card_id STRING;
DECLARE v_products_run STRING;
DECLARE v_original_hash STRING;
DECLARE v_block_id STRING DEFAULT CONCAT('smoke-',GENERATE_UUID());
ASSERT SESSION_USER()='bank-mcp@hackaton-509923.iam.gserviceaccount.com'
 AS 'Incorrect execution identity';
BEGIN TRANSACTION;
"""
pick="""
ASSERT (SELECT COUNT(*)=0 FROM `hackaton-509923.bank_sandbox.card_blocks`
 WHERE scenario_id=v_scenario_id) AS 'Smoke scenario must be empty';
SET (v_card_id,v_customer_id,v_products_run,v_original_hash)=(
 SELECT AS STRUCT p.product_id,p.customer_id,p._curation_run_id,
   TO_HEX(SHA256(TO_JSON_STRING(p)))
 FROM `hackaton-509923.bank_curated.products` p
 JOIN `hackaton-509923.bank_sandbox.scenarios` s
 ON s.scenario_id=v_scenario_id AND p._curation_run_id=s.products_run_id
 WHERE p.product_type IN ('Tarjeta Crédito','Tarjeta Débito')
   AND p.product_status='Active'
 ORDER BY p.product_id LIMIT 1
);
ASSERT v_card_id IS NOT NULL AS 'No eligible Active card';
"""
insert="""
ASSERT (SELECT COUNT(*)=1 AND COUNTIF(effective_status='Active')=1
 FROM before_cards WHERE card_id=v_card_id) AS 'Card must begin Active';
INSERT INTO `hackaton-509923.bank_sandbox.card_blocks`
(block_id,scenario_id,customer_id,idempotency_key,request_hash,created_at,
 actor_service,correlation_id,mode,contract_version,card_id,products_run_id,status)
VALUES (
 v_block_id,v_scenario_id,v_customer_id,'data-engineering-smoke-v1',
 LOWER(TO_HEX(SHA256(TO_JSON_STRING(STRUCT(
   v_scenario_id AS scenario_id,v_customer_id AS customer_id,
   v_card_id AS card_id,'block_card' AS action))))),
 CURRENT_TIMESTAMP(),SESSION_USER(),v_block_id,'SIMULATED','1.0.0',
 v_card_id,v_products_run,'Blocked'
);
"""
checks="""
ASSERT (SELECT COUNT(*)=1 AND COUNTIF(effective_status='Blocked'
 AND baseline_status='Active' AND block_id=v_block_id)=1
 FROM after_cards WHERE card_id=v_card_id) AS 'Effective state must be Blocked';
ASSERT (SELECT COUNT(*)=1 AND COUNTIF(r.verified)=1 FROM receipt_check r)
 AS 'Stored receipt must verify';
ASSERT (SELECT COUNT(*)=1 AND COUNTIF(TO_HEX(SHA256(TO_JSON_STRING(p)))=v_original_hash)=1
 FROM `hackaton-509923.bank_curated.products` p WHERE p.product_id=v_card_id)
 AS 'Curated product changed';
COMMIT TRANSACTION;
"""
post="""
ASSERT (SELECT COUNT(*)=1 AND COUNTIF(r.verified)=1 FROM persisted_receipt r)
 AS 'Receipt must verify after commit';
ASSERT (SELECT COUNT(*)=1 AND COUNTIF(TO_HEX(SHA256(TO_JSON_STRING(p)))=v_original_hash)=1
 FROM `hackaton-509923.bank_curated.products` p WHERE p.product_id=v_card_id)
 AS 'Curated product changed after commit';
SELECT 'PASSED' AS smoke_test,v_scenario_id AS scenario_id,
 v_block_id AS block_id,v_card_id AS card_id,
 'Active' AS curated_status,'Blocked' AS effective_status,'SIMULATED' AS mode;
"""
body=(prefix+sql("preflight.sql")+";\n"+pick+
      "CREATE TEMP TABLE before_cards AS\n"+sql("cards_effective.sql")+";\n"+insert+
      "CREATE TEMP TABLE after_cards AS\n"+sql("cards_effective.sql")+";\n"+
      "CREATE TEMP TABLE receipt_check AS\n"+sql("read_block.sql")+";\n"+checks+
      "CREATE TEMP TABLE persisted_receipt AS\n"+sql("read_block.sql")+";\n"+post)
Path(sys.argv[1]).write_text(body,encoding="utf-8")
PY

cuenta="$(gcloud config get-value account)"
bq query --project_id=hackaton-509923 --location=us-central1 \
  --use_legacy_sql=false --maximum_bytes_billed=1000000000 \
  --parameter="scenario_id:STRING:$scenario" \
  --parameter="created_by:STRING:$cuenta" \
  --parameter="scenario_clock:TIMESTAMP:2026-06-17 12:00:00+00" \
  < infra/bigquery/sandbox/create_scenario.sql 2>&1 | tee "$evidence/create_scenario.log"

CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT="bank-mcp@hackaton-509923.iam.gserviceaccount.com" \
bq query --project_id=hackaton-509923 --location=us-central1 \
  --use_legacy_sql=false --use_cache=false --maximum_bytes_billed=1000000000 \
  --parameter="scenario_id:STRING:$scenario" \
  < "$evidence/smoke.sql" 2>&1 | tee "$evidence/smoke.log"

bash infra/bigquery/sandbox/run_audit.sh "$scenario" 2>&1 | tee "$evidence/audit.log"
echo "PASSED: simulated block persisted, receipt verified, curated unchanged, audits passed."
echo "SCENARIO: $scenario"
echo "EVIDENCE: $evidence"
