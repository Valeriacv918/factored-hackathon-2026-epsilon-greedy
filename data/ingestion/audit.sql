CREATE TABLE IF NOT EXISTS `hackaton-509923.bank_ops.pipeline_events` (
  event_id STRING,
  run_id STRING,
  event_time TIMESTAMP,
  table_name STRING,
  event STRING,
  status STRING,
  details_json STRING
)
PARTITION BY DATE(event_time)
CLUSTER BY table_name, run_id
OPTIONS(partition_expiration_days=30);

CREATE OR REPLACE VIEW `hackaton-509923.bank_ops.pipeline_runs` AS
SELECT
  run_id,
  table_name,
  MIN(event_time) AS started_at,
  MAX(event_time) AS last_event_at,
  ARRAY_AGG(STRUCT(status, event, details_json)
    ORDER BY event_time DESC LIMIT 1)[OFFSET(0)] AS latest,
  MAX(IF(event = 'manifest_recorded', JSON_VALUE(details_json, '$.fingerprint'), NULL)) AS fingerprint,
  MAX(IF(event = 'manifest_recorded', JSON_VALUE(details_json, '$.contract_version'), NULL)) AS contract_version
FROM `hackaton-509923.bank_ops.pipeline_events`
GROUP BY run_id, table_name;

CREATE OR REPLACE VIEW `hackaton-509923.bank_ops.quality_results` AS
SELECT run_id, event_time, table_name, event AS control, status, details_json
FROM `hackaton-509923.bank_ops.pipeline_events`
WHERE event IN ('structural_contract', 'row_reconciliation')
   OR JSON_VALUE(details_json, '$.rule') IS NOT NULL;

-- Runs ending in RUNNING/PASSED without a terminal run_finished event must be
-- checked against the Cloud Run execution: cancellation/OOM cannot write a final event.
