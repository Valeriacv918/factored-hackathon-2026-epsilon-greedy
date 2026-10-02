-- daily_exchange_rates profiling v1.0.0. Run the whole script in us-central1.
-- Persists aggregate observations only. Does not modify raw or curated.
-- Run with a user allowed to write bank_ops. No cloud credentials in this file.
-- The frozen input timestamp identifies the raw version; this is not yet
-- linked authoritatively to an ingestion run_id.
DECLARE v_run_id STRING DEFAULT GENERATE_UUID();
DECLARE v_started TIMESTAMP DEFAULT CURRENT_TIMESTAMP();
DECLARE v_snapshot TIMESTAMP DEFAULT CURRENT_TIMESTAMP();
DECLARE v_rows INT64;
DECLARE v_transaction_open BOOL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS `hackaton-509923.bank_ops.profile_runs` (
  run_id STRING, profile_version STRING, source_table STRING,
  source_snapshot_at TIMESTAMP, started_at TIMESTAMP, finished_at TIMESTAMP,
  status STRING, input_rows INT64, note STRING
)
PARTITION BY DATE(started_at)
OPTIONS(partition_expiration_days=30);

CREATE TABLE IF NOT EXISTS `hackaton-509923.bank_ops.profile_results` (
  run_id STRING, recorded_at TIMESTAMP, source_table STRING,
  column_name STRING, rule_id STRING, affected_rows INT64,
  total_rows INT64, affected_pct FLOAT64, interpretation STRING
)
PARTITION BY DATE(recorded_at)
CLUSTER BY source_table, rule_id
OPTIONS(partition_expiration_days=30);

INSERT INTO `hackaton-509923.bank_ops.profile_runs`
VALUES(v_run_id, '1.0.0', 'hackaton-509923.bank_raw.daily_exchange_rates',
  v_snapshot, v_started, NULL, 'RUNNING', NULL, NULL);

BEGIN
  -- Single stable input shared by all metrics, even if raw is replaced later.
  CREATE TEMP TABLE profile_input AS
  SELECT * FROM `hackaton-509923.bank_raw.daily_exchange_rates`
  FOR SYSTEM_TIME AS OF v_snapshot;

  SET v_rows = (SELECT COUNT(*) FROM profile_input);
  ASSERT v_rows > 0 AS 'Profiling input has no records';

  CREATE TEMP TABLE measurements AS SELECT metric.* FROM (SELECT [
STRUCT('date' AS column_name,'null' AS rule_id,COUNTIF(`date` IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('date' AS column_name,'blank' AS rule_id,COUNTIF(`date` IS NOT NULL AND TRIM(`date`)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('date' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(`date`!=TRIM(`date`)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('source_currency' AS column_name,'null' AS rule_id,COUNTIF(`source_currency` IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('source_currency' AS column_name,'blank' AS rule_id,COUNTIF(`source_currency` IS NOT NULL AND TRIM(`source_currency`)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('source_currency' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(`source_currency`!=TRIM(`source_currency`)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('source_currency' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(`source_currency`))>3) AS affected_rows,'Dictionary maximum after trim' AS interpretation),
STRUCT('target_currency' AS column_name,'null' AS rule_id,COUNTIF(`target_currency` IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('target_currency' AS column_name,'blank' AS rule_id,COUNTIF(`target_currency` IS NOT NULL AND TRIM(`target_currency`)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('target_currency' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(`target_currency`!=TRIM(`target_currency`)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('target_currency' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(`target_currency`))>3) AS affected_rows,'Dictionary maximum after trim' AS interpretation),
STRUCT('exchange_rate' AS column_name,'null' AS rule_id,COUNTIF(`exchange_rate` IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('exchange_rate' AS column_name,'blank' AS rule_id,COUNTIF(`exchange_rate` IS NOT NULL AND TRIM(`exchange_rate`)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('exchange_rate' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(`exchange_rate`!=TRIM(`exchange_rate`)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('buy_rate' AS column_name,'null' AS rule_id,COUNTIF(`buy_rate` IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('buy_rate' AS column_name,'blank' AS rule_id,COUNTIF(`buy_rate` IS NOT NULL AND TRIM(`buy_rate`)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('buy_rate' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(`buy_rate`!=TRIM(`buy_rate`)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('sell_rate' AS column_name,'null' AS rule_id,COUNTIF(`sell_rate` IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('sell_rate' AS column_name,'blank' AS rule_id,COUNTIF(`sell_rate` IS NOT NULL AND TRIM(`sell_rate`)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('sell_rate' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(`sell_rate`!=TRIM(`sell_rate`)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('source' AS column_name,'null' AS rule_id,COUNTIF(`source` IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('source' AS column_name,'blank' AS rule_id,COUNTIF(`source` IS NOT NULL AND TRIM(`source`)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('source' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(`source`!=TRIM(`source`)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('source' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(`source`))>50) AS affected_rows,'Dictionary maximum after trim' AS interpretation),
STRUCT('source_currency' AS column_name,'noncanonical_currency_format' AS rule_id,COUNTIF(NULLIF(TRIM(source_currency),'') IS NOT NULL AND NOT REGEXP_CONTAINS(TRIM(source_currency),r'^[A-Z]{3}$')) AS affected_rows,'Format observation; not an authoritative currency catalog' AS interpretation),
STRUCT('target_currency' AS column_name,'noncanonical_currency_format' AS rule_id,COUNTIF(NULLIF(TRIM(target_currency),'') IS NOT NULL AND NOT REGEXP_CONTAINS(TRIM(target_currency),r'^[A-Z]{3}$')) AS affected_rows,'Format observation; not an authoritative currency catalog' AS interpretation),
STRUCT('date' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(`date`),'') IS NOT NULL AND SAFE_CAST(TRIM(`date`) AS DATE) IS NULL) AS affected_rows,'DATE parser; blanks excluded' AS interpretation),
STRUCT('exchange_rate' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(exchange_rate),'') IS NOT NULL AND SAFE_CAST(TRIM(exchange_rate) AS BIGNUMERIC) IS NULL) AS affected_rows,'BIGNUMERIC parser; blanks excluded' AS interpretation),
STRUCT('exchange_rate' AS column_name,'decimal_overflow' AS rule_id,COUNTIF(ABS(SAFE_CAST(TRIM(exchange_rate) AS BIGNUMERIC))>=1000000) AS affected_rows,'DECIMAL(12,6) magnitude' AS interpretation),
STRUCT('exchange_rate' AS column_name,'excess_scale' AS rule_id,COUNTIF(SAFE_CAST(TRIM(exchange_rate) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(exchange_rate) AS BIGNUMERIC),6)) AS affected_rows,'No silent rounding' AS interpretation),
STRUCT('exchange_rate' AS column_name,'nonpositive' AS rule_id,COUNTIF(SAFE_CAST(TRIM(exchange_rate) AS BIGNUMERIC)<=0) AS affected_rows,'Candidate positive-rate rule; review before enforcing' AS interpretation),
STRUCT('buy_rate' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(buy_rate),'') IS NOT NULL AND SAFE_CAST(TRIM(buy_rate) AS BIGNUMERIC) IS NULL) AS affected_rows,'BIGNUMERIC parser; blanks excluded' AS interpretation),
STRUCT('buy_rate' AS column_name,'decimal_overflow' AS rule_id,COUNTIF(ABS(SAFE_CAST(TRIM(buy_rate) AS BIGNUMERIC))>=1000000) AS affected_rows,'DECIMAL(12,6) magnitude' AS interpretation),
STRUCT('buy_rate' AS column_name,'excess_scale' AS rule_id,COUNTIF(SAFE_CAST(TRIM(buy_rate) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(buy_rate) AS BIGNUMERIC),6)) AS affected_rows,'No silent rounding' AS interpretation),
STRUCT('buy_rate' AS column_name,'nonpositive' AS rule_id,COUNTIF(SAFE_CAST(TRIM(buy_rate) AS BIGNUMERIC)<=0) AS affected_rows,'Candidate positive-rate rule; review before enforcing' AS interpretation),
STRUCT('sell_rate' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(sell_rate),'') IS NOT NULL AND SAFE_CAST(TRIM(sell_rate) AS BIGNUMERIC) IS NULL) AS affected_rows,'BIGNUMERIC parser; blanks excluded' AS interpretation),
STRUCT('sell_rate' AS column_name,'decimal_overflow' AS rule_id,COUNTIF(ABS(SAFE_CAST(TRIM(sell_rate) AS BIGNUMERIC))>=1000000) AS affected_rows,'DECIMAL(12,6) magnitude' AS interpretation),
STRUCT('sell_rate' AS column_name,'excess_scale' AS rule_id,COUNTIF(SAFE_CAST(TRIM(sell_rate) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(sell_rate) AS BIGNUMERIC),6)) AS affected_rows,'No silent rounding' AS interpretation),
STRUCT('sell_rate' AS column_name,'nonpositive' AS rule_id,COUNTIF(SAFE_CAST(TRIM(sell_rate) AS BIGNUMERIC)<=0) AS affected_rows,'Candidate positive-rate rule; review before enforcing' AS interpretation),
STRUCT('buy_rate' AS column_name,'greater_than_sell_rate' AS rule_id,COUNTIF(SAFE_CAST(TRIM(buy_rate) AS BIGNUMERIC)>SAFE_CAST(TRIM(sell_rate) AS BIGNUMERIC)) AS affected_rows,'Observation; quotation conventions need confirmation' AS interpretation),
STRUCT('exchange_rate' AS column_name,'outside_buy_sell_interval' AS rule_id,COUNTIF(SAFE_CAST(TRIM(exchange_rate) AS BIGNUMERIC)<SAFE_CAST(TRIM(buy_rate) AS BIGNUMERIC) OR SAFE_CAST(TRIM(exchange_rate) AS BIGNUMERIC)>SAFE_CAST(TRIM(sell_rate) AS BIGNUMERIC)) AS affected_rows,'Observation only; sources and timestamps may differ' AS interpretation),
STRUCT('exchange_rate' AS column_name,'same_currency_rate_not_one' AS rule_id,COUNTIF(UPPER(TRIM(source_currency))=UPPER(TRIM(target_currency)) AND SAFE_CAST(TRIM(exchange_rate) AS BIGNUMERIC)!=1) AS affected_rows,'Observation for same currency pair' AS interpretation)
] AS metrics FROM profile_input),UNNEST(metrics) AS metric;

CREATE TEMP TABLE duplicate_keys AS
SELECT SAFE_CAST(TRIM(`date`) AS DATE) AS rate_date,
 UPPER(NULLIF(TRIM(source_currency),'')) AS source_ccy,
 UPPER(NULLIF(TRIM(target_currency),'')) AS target_ccy,COUNT(*) AS n
FROM profile_input
WHERE SAFE_CAST(TRIM(`date`) AS DATE) IS NOT NULL
 AND NULLIF(TRIM(source_currency),'') IS NOT NULL AND NULLIF(TRIM(target_currency),'') IS NOT NULL
GROUP BY rate_date,source_ccy,target_ccy HAVING COUNT(*)>1;
INSERT INTO measurements
SELECT '*','composite_key_duplicate_excess',COALESCE(SUM(n-1),0),
 'Excess rows per parsed date and uppercase trimmed currency pair; excludes invalid keys'
FROM duplicate_keys;
INSERT INTO measurements
SELECT '*','rows_in_duplicate_key_groups',COALESCE(SUM(n),0),
 'All rows in duplicate groups; overlaps duplicate excess'
FROM duplicate_keys;
INSERT INTO measurements
SELECT '*','exact_duplicate_excess',COALESCE(SUM(n-1),0),'Identical business rows beyond first'
FROM (SELECT TO_JSON_STRING(STRUCT(`date`,source_currency,target_currency,exchange_rate,buy_rate,sell_rate,source)) AS row_content,COUNT(*) AS n
FROM profile_input GROUP BY row_content HAVING COUNT(*)>1);
CREATE TABLE IF NOT EXISTS `hackaton-509923.bank_ops.profile_domains` (
run_id STRING,recorded_at TIMESTAMP,source_table STRING,column_name STRING,value STRING,row_count INT64
) PARTITION BY DATE(recorded_at) OPTIONS(partition_expiration_days=30);
  -- Persist metrics and terminal success together; failed runs have no
  -- partially persisted metric set.
  BEGIN TRANSACTION;
  SET v_transaction_open = TRUE;
INSERT INTO `hackaton-509923.bank_ops.profile_domains`
SELECT v_run_id,v_started,'hackaton-509923.bank_raw.daily_exchange_rates',d.column_name,d.value,COUNT(*)
FROM profile_input,UNNEST([
STRUCT('source_currency' AS column_name,TRIM(source_currency) AS value),
STRUCT('target_currency' AS column_name,TRIM(target_currency) AS value),
STRUCT('source' AS column_name,TRIM(source) AS value)
]) d GROUP BY d.column_name,d.value;

  INSERT INTO `hackaton-509923.bank_ops.profile_results`
  SELECT v_run_id, v_started, 'hackaton-509923.bank_raw.daily_exchange_rates',
    column_name, rule_id, affected_rows, v_rows,
    IF(rule_id = 'latest_version_conflicting_keys', NULL,
       ROUND(100.0 * SAFE_DIVIDE(affected_rows, v_rows), 4)),
    interpretation
  FROM measurements;

  UPDATE `hackaton-509923.bank_ops.profile_runs`
  SET status = 'SUCCEEDED', finished_at = CURRENT_TIMESTAMP(), input_rows = v_rows, note='Composite key: date/source_currency/target_currency; no rate inversion or imputation; quotation convention and required coverage pending'
  WHERE run_id = v_run_id;
  COMMIT TRANSACTION;
  SET v_transaction_open = FALSE;

EXCEPTION WHEN ERROR THEN
  IF v_transaction_open THEN
    ROLLBACK TRANSACTION;
  END IF;
  UPDATE `hackaton-509923.bank_ops.profile_runs`
  SET status = 'FAILED', finished_at = CURRENT_TIMESTAMP(), input_rows = v_rows,
      note = 'Inspect the BigQuery script job for the error; no values copied to audit.'
  WHERE run_id = v_run_id;
  RAISE;
END;

SELECT UPPER(TRIM(source_currency)) AS source_currency,
 UPPER(TRIM(target_currency)) AS target_currency,COUNT(*) AS rows_in_pair,
 MIN(SAFE_CAST(TRIM(`date`) AS DATE)) AS first_date,
 MAX(SAFE_CAST(TRIM(`date`) AS DATE)) AS last_date,
 COUNT(DISTINCT SAFE_CAST(TRIM(`date`) AS DATE)) AS distinct_dates,
 DATE_DIFF(MAX(SAFE_CAST(TRIM(`date`) AS DATE)),MIN(SAFE_CAST(TRIM(`date`) AS DATE)),DAY)+1
 -COUNT(DISTINCT SAFE_CAST(TRIM(`date`) AS DATE)) AS missing_calendar_dates_within_span
FROM profile_input GROUP BY 1,2 ORDER BY 1,2;
DROP TABLE profile_input;
DROP TABLE measurements;

SELECT run_id, status, input_rows, source_snapshot_at
FROM `hackaton-509923.bank_ops.profile_runs`
WHERE run_id = v_run_id;

SELECT column_name, rule_id, affected_rows, total_rows, affected_pct, interpretation
FROM `hackaton-509923.bank_ops.profile_results`
WHERE run_id = v_run_id AND affected_rows > 0
ORDER BY affected_rows DESC, column_name, rule_id;

SELECT column_name,value,row_count FROM `hackaton-509923.bank_ops.profile_domains`
WHERE run_id=v_run_id ORDER BY column_name,row_count DESC;
