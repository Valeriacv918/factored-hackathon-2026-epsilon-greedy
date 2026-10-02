-- products profiling v1.0.0. Run the whole script in us-central1.
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
VALUES(v_run_id, '1.0.1', 'hackaton-509923.bank_raw.products',
  v_snapshot, v_started, NULL, 'RUNNING', NULL, NULL);

BEGIN
  -- Single stable input shared by all metrics, even if raw is replaced later.
  CREATE TEMP TABLE profile_input AS
  SELECT * FROM `hackaton-509923.bank_raw.products`
  FOR SYSTEM_TIME AS OF v_snapshot;

  SET v_rows = (SELECT COUNT(*) FROM profile_input);
  ASSERT v_rows > 0 AS 'Profiling input has no records';

  CREATE TEMP TABLE measurements AS
  SELECT metric.* FROM (
    SELECT [
STRUCT('product_id' AS column_name, 'null' AS rule_id, COUNTIF(product_id IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('product_id' AS column_name, 'blank' AS rule_id, COUNTIF(product_id IS NOT NULL AND TRIM(product_id) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('product_id' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(product_id != TRIM(product_id)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('product_id' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(product_id)) > 20) AS affected_rows, 'Dictionary maximum 20 after trim' AS interpretation),
STRUCT('customer_id' AS column_name, 'null' AS rule_id, COUNTIF(customer_id IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('customer_id' AS column_name, 'blank' AS rule_id, COUNTIF(customer_id IS NOT NULL AND TRIM(customer_id) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('customer_id' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(customer_id != TRIM(customer_id)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('customer_id' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(customer_id)) > 20) AS affected_rows, 'Dictionary maximum 20 after trim' AS interpretation),
STRUCT('product_type' AS column_name, 'null' AS rule_id, COUNTIF(product_type IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('product_type' AS column_name, 'blank' AS rule_id, COUNTIF(product_type IS NOT NULL AND TRIM(product_type) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('product_type' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(product_type != TRIM(product_type)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('product_type' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(product_type)) > 50) AS affected_rows, 'Dictionary maximum 50 after trim' AS interpretation),
STRUCT('product_number' AS column_name, 'null' AS rule_id, COUNTIF(product_number IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('product_number' AS column_name, 'blank' AS rule_id, COUNTIF(product_number IS NOT NULL AND TRIM(product_number) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('product_number' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(product_number != TRIM(product_number)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('product_number' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(product_number)) > 30) AS affected_rows, 'Dictionary maximum 30 after trim' AS interpretation),
STRUCT('currency' AS column_name, 'null' AS rule_id, COUNTIF(currency IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('currency' AS column_name, 'blank' AS rule_id, COUNTIF(currency IS NOT NULL AND TRIM(currency) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('currency' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(currency != TRIM(currency)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('currency' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(currency)) > 3) AS affected_rows, 'Dictionary maximum 3 after trim' AS interpretation),
STRUCT('current_balance' AS column_name, 'null' AS rule_id, COUNTIF(current_balance IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('current_balance' AS column_name, 'blank' AS rule_id, COUNTIF(current_balance IS NOT NULL AND TRIM(current_balance) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('current_balance' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(current_balance != TRIM(current_balance)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('credit_limit' AS column_name, 'null' AS rule_id, COUNTIF(credit_limit IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('credit_limit' AS column_name, 'blank' AS rule_id, COUNTIF(credit_limit IS NOT NULL AND TRIM(credit_limit) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('credit_limit' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(credit_limit != TRIM(credit_limit)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('interest_rate' AS column_name, 'null' AS rule_id, COUNTIF(interest_rate IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('interest_rate' AS column_name, 'blank' AS rule_id, COUNTIF(interest_rate IS NOT NULL AND TRIM(interest_rate) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('interest_rate' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(interest_rate != TRIM(interest_rate)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('opening_date' AS column_name, 'null' AS rule_id, COUNTIF(opening_date IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('opening_date' AS column_name, 'blank' AS rule_id, COUNTIF(opening_date IS NOT NULL AND TRIM(opening_date) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('opening_date' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(opening_date != TRIM(opening_date)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('expiration_date' AS column_name, 'null' AS rule_id, COUNTIF(expiration_date IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('expiration_date' AS column_name, 'blank' AS rule_id, COUNTIF(expiration_date IS NOT NULL AND TRIM(expiration_date) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('expiration_date' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(expiration_date != TRIM(expiration_date)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('opening_branch_id' AS column_name, 'null' AS rule_id, COUNTIF(opening_branch_id IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('opening_branch_id' AS column_name, 'blank' AS rule_id, COUNTIF(opening_branch_id IS NOT NULL AND TRIM(opening_branch_id) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('opening_branch_id' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(opening_branch_id != TRIM(opening_branch_id)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('opening_branch_id' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(opening_branch_id)) > 20) AS affected_rows, 'Dictionary maximum 20 after trim' AS interpretation),
STRUCT('product_status' AS column_name, 'null' AS rule_id, COUNTIF(product_status IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('product_status' AS column_name, 'blank' AS rule_id, COUNTIF(product_status IS NOT NULL AND TRIM(product_status) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('product_status' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(product_status != TRIM(product_status)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('product_status' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(product_status)) > 20) AS affected_rows, 'Dictionary maximum 20 after trim' AS interpretation),
STRUCT('opening_channel' AS column_name, 'null' AS rule_id, COUNTIF(opening_channel IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('opening_channel' AS column_name, 'blank' AS rule_id, COUNTIF(opening_channel IS NOT NULL AND TRIM(opening_channel) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('opening_channel' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(opening_channel != TRIM(opening_channel)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('opening_channel' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(opening_channel)) > 30) AS affected_rows, 'Dictionary maximum 30 after trim' AS interpretation),
STRUCT('has_linked_app' AS column_name, 'null' AS rule_id, COUNTIF(has_linked_app IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('has_linked_app' AS column_name, 'blank' AS rule_id, COUNTIF(has_linked_app IS NOT NULL AND TRIM(has_linked_app) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('has_linked_app' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(has_linked_app != TRIM(has_linked_app)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('days_past_due' AS column_name, 'null' AS rule_id, COUNTIF(days_past_due IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('days_past_due' AS column_name, 'blank' AS rule_id, COUNTIF(days_past_due IS NOT NULL AND TRIM(days_past_due) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('days_past_due' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(days_past_due != TRIM(days_past_due)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('last_transaction_date' AS column_name, 'null' AS rule_id, COUNTIF(last_transaction_date IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('last_transaction_date' AS column_name, 'blank' AS rule_id, COUNTIF(last_transaction_date IS NOT NULL AND TRIM(last_transaction_date) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('last_transaction_date' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(last_transaction_date != TRIM(last_transaction_date)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('last_updated' AS column_name, 'null' AS rule_id, COUNTIF(last_updated IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('last_updated' AS column_name, 'blank' AS rule_id, COUNTIF(last_updated IS NOT NULL AND TRIM(last_updated) = '') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('last_updated' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(last_updated != TRIM(last_updated)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('opening_date' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(opening_date), '') IS NOT NULL AND SAFE_CAST(TRIM(opening_date) AS DATE) IS NULL) AS affected_rows, 'DATE parser; excludes blanks' AS interpretation),
STRUCT('expiration_date' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(expiration_date), '') IS NOT NULL AND SAFE_CAST(TRIM(expiration_date) AS DATE) IS NULL) AS affected_rows, 'DATE parser; excludes blanks' AS interpretation),
STRUCT('last_transaction_date' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(last_transaction_date), '') IS NOT NULL AND SAFE_CAST(TRIM(last_transaction_date) AS TIMESTAMP) IS NULL) AS affected_rows, 'TIMESTAMP parser; excludes blanks' AS interpretation),
STRUCT('last_updated' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(last_updated), '') IS NOT NULL AND SAFE_CAST(TRIM(last_updated) AS TIMESTAMP) IS NULL) AS affected_rows, 'TIMESTAMP parser; excludes blanks' AS interpretation),
STRUCT('current_balance' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(current_balance), '') IS NOT NULL AND SAFE_CAST(TRIM(current_balance) AS BIGNUMERIC) IS NULL) AS affected_rows, 'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('credit_limit' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(credit_limit), '') IS NOT NULL AND SAFE_CAST(TRIM(credit_limit) AS BIGNUMERIC) IS NULL) AS affected_rows, 'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('interest_rate' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(interest_rate), '') IS NOT NULL AND SAFE_CAST(TRIM(interest_rate) AS BIGNUMERIC) IS NULL) AS affected_rows, 'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('days_past_due' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(days_past_due), '') IS NOT NULL AND SAFE_CAST(TRIM(days_past_due) AS BIGNUMERIC) IS NULL) AS affected_rows, 'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('current_balance' AS column_name, 'decimal_overflow' AS rule_id, COUNTIF(ABS(SAFE_CAST(TRIM(current_balance) AS BIGNUMERIC)) >= 10000000000000) AS affected_rows, 'DECIMAL(15,2) integer magnitude' AS interpretation),
STRUCT('current_balance' AS column_name, 'more_than_2_decimals' AS rule_id, COUNTIF(SAFE_CAST(TRIM(current_balance) AS BIGNUMERIC) != TRUNC(SAFE_CAST(TRIM(current_balance) AS BIGNUMERIC),2)) AS affected_rows, 'Do not silently round' AS interpretation),
STRUCT('current_balance' AS column_name, 'negative_value' AS rule_id, COUNTIF(SAFE_CAST(TRIM(current_balance) AS BIGNUMERIC) < 0) AS affected_rows, 'Observation only; business policy pending' AS interpretation),
STRUCT('credit_limit' AS column_name, 'decimal_overflow' AS rule_id, COUNTIF(ABS(SAFE_CAST(TRIM(credit_limit) AS BIGNUMERIC)) >= 10000000000000) AS affected_rows, 'DECIMAL(15,2) integer magnitude' AS interpretation),
STRUCT('credit_limit' AS column_name, 'more_than_2_decimals' AS rule_id, COUNTIF(SAFE_CAST(TRIM(credit_limit) AS BIGNUMERIC) != TRUNC(SAFE_CAST(TRIM(credit_limit) AS BIGNUMERIC),2)) AS affected_rows, 'Do not silently round' AS interpretation),
STRUCT('credit_limit' AS column_name, 'negative_value' AS rule_id, COUNTIF(SAFE_CAST(TRIM(credit_limit) AS BIGNUMERIC) < 0) AS affected_rows, 'Observation only; business policy pending' AS interpretation),
STRUCT('interest_rate' AS column_name, 'decimal_overflow' AS rule_id, COUNTIF(ABS(SAFE_CAST(TRIM(interest_rate) AS BIGNUMERIC)) >= 1000) AS affected_rows, 'DECIMAL(5,2) integer magnitude' AS interpretation),
STRUCT('interest_rate' AS column_name, 'more_than_2_decimals' AS rule_id, COUNTIF(SAFE_CAST(TRIM(interest_rate) AS BIGNUMERIC) != TRUNC(SAFE_CAST(TRIM(interest_rate) AS BIGNUMERIC),2)) AS affected_rows, 'Do not silently round' AS interpretation),
STRUCT('interest_rate' AS column_name, 'negative_value' AS rule_id, COUNTIF(SAFE_CAST(TRIM(interest_rate) AS BIGNUMERIC) < 0) AS affected_rows, 'Observation only; business policy pending' AS interpretation),
STRUCT('days_past_due' AS column_name, 'fractional_value' AS rule_id, COUNTIF(SAFE_CAST(TRIM(days_past_due) AS BIGNUMERIC) != TRUNC(SAFE_CAST(TRIM(days_past_due) AS BIGNUMERIC))) AS affected_rows, 'Must be integral; decimal notation allowed' AS interpretation),
STRUCT('days_past_due' AS column_name, 'int64_overflow' AS rule_id, COUNTIF(SAFE_CAST(TRIM(days_past_due) AS BIGNUMERIC) < -9223372036854775808 OR SAFE_CAST(TRIM(days_past_due) AS BIGNUMERIC) > 9223372036854775807) AS affected_rows, 'Target INT64 bounds' AS interpretation),
STRUCT('days_past_due' AS column_name, 'negative_value' AS rule_id, COUNTIF(SAFE_CAST(TRIM(days_past_due) AS BIGNUMERIC) < 0) AS affected_rows, 'Observation; confirm business policy' AS interpretation),
STRUCT('currency' AS column_name, 'outside_dictionary_domain' AS rule_id, COUNTIF(NULLIF(TRIM(currency),'') IS NOT NULL AND TRIM(currency) NOT IN ('MXN','COP','ARS','USD')) AS affected_rows, 'Case sensitive after trim' AS interpretation),
STRUCT('product_status' AS column_name, 'outside_dictionary_domain' AS rule_id, COUNTIF(NULLIF(TRIM(product_status),'') IS NOT NULL AND TRIM(product_status) NOT IN ('Active','Blocked','Closed','Suspended')) AS affected_rows, 'Case sensitive after trim' AS interpretation),
STRUCT('opening_channel' AS column_name, 'outside_dictionary_domain' AS rule_id, COUNTIF(NULLIF(TRIM(opening_channel),'') IS NOT NULL AND TRIM(opening_channel) NOT IN ('Branch','Web','App','Call Center')) AS affected_rows, 'Case sensitive after trim' AS interpretation),
STRUCT('has_linked_app' AS column_name, 'unknown_boolean' AS rule_id, COUNTIF(NULLIF(TRIM(has_linked_app),'') IS NOT NULL AND LOWER(TRIM(has_linked_app)) NOT IN ('true','false','1','0','t','f','yes','no','y','n')) AS affected_rows, 'Candidate spellings; policy pending' AS interpretation),
STRUCT('expiration_date' AS column_name, 'before_opening' AS rule_id, COUNTIF(SAFE_CAST(TRIM(expiration_date) AS DATE) < SAFE_CAST(TRIM(opening_date) AS DATE)) AS affected_rows, 'Chronology observation' AS interpretation),
STRUCT('last_transaction_date' AS column_name, 'before_opening' AS rule_id, COUNTIF(DATE(SAFE_CAST(TRIM(last_transaction_date) AS TIMESTAMP)) < SAFE_CAST(TRIM(opening_date) AS DATE)) AS affected_rows, 'Chronology observation; UTC if timezone absent' AS interpretation),
STRUCT('last_updated' AS column_name, 'before_opening' AS rule_id, COUNTIF(DATE(SAFE_CAST(TRIM(last_updated) AS TIMESTAMP)) < SAFE_CAST(TRIM(opening_date) AS DATE)) AS affected_rows, 'Chronology observation; UTC if timezone absent' AS interpretation)
    ] AS metrics
    FROM profile_input
  ), UNNEST(metrics) AS metric;

  -- Exact copies: compare the complete row; never expose customer values.
  INSERT INTO measurements
  SELECT '*', 'exact_duplicate_excess', COALESCE(SUM(n - 1), 0),
    'Additional identical rows; overlaps with duplicate-key metrics'
  FROM (
    SELECT TO_JSON_STRING(r) AS row_content, COUNT(*) AS n
    FROM profile_input AS r
    GROUP BY row_content HAVING COUNT(*) > 1
  );

  INSERT INTO measurements
  SELECT 'product_id', 'duplicate_key_excess_after_trim', COALESCE(SUM(n - 1), 0),
    'Additional rows per nonblank trimmed key; overlaps with exact duplicates'
  FROM (
    SELECT TRIM(product_id) AS key_value, COUNT(*) AS n
    FROM profile_input WHERE NULLIF(TRIM(product_id), '') IS NOT NULL
    GROUP BY key_value HAVING COUNT(*) > 1
  );

  INSERT INTO measurements
  SELECT 'product_number', 'duplicate_key_excess_after_trim', COALESCE(SUM(n - 1), 0),
    'Additional rows per nonblank trimmed key; overlaps with exact duplicates'
  FROM (
    SELECT TRIM(product_number) AS key_value, COUNT(*) AS n
    FROM profile_input WHERE NULLIF(TRIM(product_number), '') IS NOT NULL
    GROUP BY key_value HAVING COUNT(*) > 1
  );

  -- Count distinct customer IDs with conflicting content at the latest
  -- parseable update timestamp. IDs without valid timestamps need separate review.
  INSERT INTO measurements
  WITH versioned AS (
    SELECT TRIM(product_id) AS key_value,
      SAFE_CAST(TRIM(last_updated) AS TIMESTAMP) AS update_time,
      TO_JSON_STRING(r) AS row_content
    FROM profile_input AS r
    WHERE NULLIF(TRIM(product_id), '') IS NOT NULL
  ), latest AS (
    SELECT * FROM versioned
    WHERE update_time IS NOT NULL
    QUALIFY update_time = MAX(update_time) OVER (PARTITION BY key_value)
  ), conflicts AS (
    SELECT key_value FROM latest GROUP BY key_value
    HAVING COUNT(DISTINCT row_content) > 1
  )
  SELECT 'product_id', 'latest_version_conflicting_keys', COUNT(*),
    'Counts keys, not rows; raw-content differences at latest valid timestamp'
  FROM conflicts;

  -- Freeze the published reference at the same timestamp as raw.
  CREATE TEMP TABLE reference_customers AS
  SELECT customer_id, _curation_run_id
  FROM `hackaton-509923.bank_curated.customers`
  FOR SYSTEM_TIME AS OF v_snapshot;

  ASSERT (SELECT COUNT(*) FROM reference_customers) > 0
    AS 'Published customers reference is empty';

  INSERT INTO measurements
  SELECT 'customer_id', 'missing_curated_customer', COUNT(*),
    'Nonblank product owner absent from curated customers at source_snapshot_at'
  FROM profile_input AS p
  WHERE NULLIF(TRIM(p.customer_id), '') IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM reference_customers AS c
                    WHERE c.customer_id = TRIM(p.customer_id));

  CREATE TABLE IF NOT EXISTS `hackaton-509923.bank_ops.profile_domains` (
    run_id STRING, recorded_at TIMESTAMP, source_table STRING,
    column_name STRING, value STRING, row_count INT64
  ) PARTITION BY DATE(recorded_at)
  OPTIONS(partition_expiration_days=30);

  -- Persist metrics and terminal success together; failed runs have no
  -- partially persisted metric set.
  BEGIN TRANSACTION;
  SET v_transaction_open = TRUE;
  INSERT INTO `hackaton-509923.bank_ops.profile_domains`
  SELECT v_run_id, v_started, 'hackaton-509923.bank_raw.products',
    d.column_name, d.value, COUNT(*)
  FROM profile_input,
  UNNEST([STRUCT('product_type' AS column_name, TRIM(product_type) AS value),
          STRUCT('currency', TRIM(currency)),
          STRUCT('product_status', TRIM(product_status)),
          STRUCT('opening_channel', TRIM(opening_channel)),
          STRUCT('has_linked_app', TRIM(has_linked_app))]) AS d
  GROUP BY d.column_name, d.value;

  INSERT INTO `hackaton-509923.bank_ops.profile_results`
  SELECT v_run_id, v_started, 'hackaton-509923.bank_raw.products',
    column_name, rule_id, affected_rows, v_rows,
    IF(rule_id = 'latest_version_conflicting_keys', NULL,
       ROUND(100.0 * SAFE_DIVIDE(affected_rows, v_rows), 4)),
    interpretation
  FROM measurements;

  UPDATE `hackaton-509923.bank_ops.profile_runs`
  SET status = 'SUCCEEDED', finished_at = CURRENT_TIMESTAMP(), input_rows = v_rows,
      note = CONCAT('Reference: bank_curated.customers at source_snapshot_at; curation runs: ',
        (SELECT STRING_AGG(DISTINCT _curation_run_id, ',') FROM reference_customers),
        '; product_type dictionary incomplete; branch FK pending')
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

-- Diagnose repeated numbers without returning account numbers or owner IDs.
WITH duplicate_groups AS (
SELECT TRIM(product_number) AS normalized_number,
  COUNT(*) AS rows_in_group,
  COUNT(DISTINCT TRIM(product_id)) AS distinct_products,
  COUNT(DISTINCT TRIM(customer_id)) AS distinct_customers,
  ARRAY_AGG(DISTINCT TRIM(product_type) IGNORE NULLS) AS product_types,
  ARRAY_AGG(DISTINCT TRIM(currency) IGNORE NULLS) AS currencies
FROM profile_input
WHERE NULLIF(TRIM(product_number), '') IS NOT NULL
GROUP BY normalized_number
HAVING COUNT(*) > 1
)
SELECT TO_HEX(SHA256(normalized_number)) AS product_number_hash,
  rows_in_group, distinct_products, distinct_customers, product_types, currencies
FROM duplicate_groups
ORDER BY rows_in_group DESC;

DROP TABLE profile_input;
DROP TABLE measurements;

SELECT run_id, status, input_rows, source_snapshot_at
FROM `hackaton-509923.bank_ops.profile_runs`
WHERE run_id = v_run_id;

SELECT column_name, rule_id, affected_rows, total_rows, affected_pct, interpretation
FROM `hackaton-509923.bank_ops.profile_results`
WHERE run_id = v_run_id AND affected_rows > 0
ORDER BY affected_rows DESC, column_name, rule_id;

SELECT column_name, value, row_count
FROM `hackaton-509923.bank_ops.profile_domains`
WHERE run_id = v_run_id
ORDER BY column_name, row_count DESC;
