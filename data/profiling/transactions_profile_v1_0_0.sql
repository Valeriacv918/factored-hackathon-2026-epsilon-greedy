-- transactions profiling v1.0.0. Run the whole script in us-central1.
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
VALUES(v_run_id, '1.0.0', 'hackaton-509923.bank_raw.transactions',
  v_snapshot, v_started, NULL, 'RUNNING', NULL, NULL);

BEGIN
  -- Single stable input shared by all metrics, even if raw is replaced later.
  CREATE TEMP TABLE profile_input AS
  SELECT * FROM `hackaton-509923.bank_raw.transactions`
  FOR SYSTEM_TIME AS OF v_snapshot;

  SET v_rows = (SELECT COUNT(*) FROM profile_input);
  ASSERT v_rows > 0 AS 'Profiling input has no records';

  CREATE TEMP TABLE measurements AS
  SELECT metric.* FROM (SELECT [
STRUCT('transaction_id' AS column_name, 'null' AS rule_id, COUNTIF(transaction_id IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('transaction_id' AS column_name, 'blank' AS rule_id, COUNTIF(transaction_id IS NOT NULL AND TRIM(transaction_id)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('transaction_id' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(transaction_id != TRIM(transaction_id)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('transaction_id' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(transaction_id))>30) AS affected_rows, 'Dictionary limit 30 after trim' AS interpretation),
STRUCT('transaction_date' AS column_name, 'null' AS rule_id, COUNTIF(transaction_date IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('transaction_date' AS column_name, 'blank' AS rule_id, COUNTIF(transaction_date IS NOT NULL AND TRIM(transaction_date)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('transaction_date' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(transaction_date != TRIM(transaction_date)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('process_date' AS column_name, 'null' AS rule_id, COUNTIF(process_date IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('process_date' AS column_name, 'blank' AS rule_id, COUNTIF(process_date IS NOT NULL AND TRIM(process_date)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('process_date' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(process_date != TRIM(process_date)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('product_id' AS column_name, 'null' AS rule_id, COUNTIF(product_id IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('product_id' AS column_name, 'blank' AS rule_id, COUNTIF(product_id IS NOT NULL AND TRIM(product_id)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('product_id' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(product_id != TRIM(product_id)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('product_id' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(product_id))>20) AS affected_rows, 'Dictionary limit 20 after trim' AS interpretation),
STRUCT('customer_id' AS column_name, 'null' AS rule_id, COUNTIF(customer_id IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('customer_id' AS column_name, 'blank' AS rule_id, COUNTIF(customer_id IS NOT NULL AND TRIM(customer_id)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('customer_id' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(customer_id != TRIM(customer_id)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('customer_id' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(customer_id))>20) AS affected_rows, 'Dictionary limit 20 after trim' AS interpretation),
STRUCT('transaction_type' AS column_name, 'null' AS rule_id, COUNTIF(transaction_type IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('transaction_type' AS column_name, 'blank' AS rule_id, COUNTIF(transaction_type IS NOT NULL AND TRIM(transaction_type)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('transaction_type' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(transaction_type != TRIM(transaction_type)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('transaction_type' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(transaction_type))>50) AS affected_rows, 'Dictionary limit 50 after trim' AS interpretation),
STRUCT('transaction_category' AS column_name, 'null' AS rule_id, COUNTIF(transaction_category IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('transaction_category' AS column_name, 'blank' AS rule_id, COUNTIF(transaction_category IS NOT NULL AND TRIM(transaction_category)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('transaction_category' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(transaction_category != TRIM(transaction_category)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('transaction_category' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(transaction_category))>50) AS affected_rows, 'Dictionary limit 50 after trim' AS interpretation),
STRUCT('amount' AS column_name, 'null' AS rule_id, COUNTIF(amount IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('amount' AS column_name, 'blank' AS rule_id, COUNTIF(amount IS NOT NULL AND TRIM(amount)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('amount' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(amount != TRIM(amount)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('currency' AS column_name, 'null' AS rule_id, COUNTIF(currency IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('currency' AS column_name, 'blank' AS rule_id, COUNTIF(currency IS NOT NULL AND TRIM(currency)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('currency' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(currency != TRIM(currency)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('currency' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(currency))>3) AS affected_rows, 'Dictionary limit 3 after trim' AS interpretation),
STRUCT('amount_usd' AS column_name, 'null' AS rule_id, COUNTIF(amount_usd IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('amount_usd' AS column_name, 'blank' AS rule_id, COUNTIF(amount_usd IS NOT NULL AND TRIM(amount_usd)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('amount_usd' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(amount_usd != TRIM(amount_usd)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('channel' AS column_name, 'null' AS rule_id, COUNTIF(channel IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('channel' AS column_name, 'blank' AS rule_id, COUNTIF(channel IS NOT NULL AND TRIM(channel)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('channel' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(channel != TRIM(channel)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('channel' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(channel))>30) AS affected_rows, 'Dictionary limit 30 after trim' AS interpretation),
STRUCT('branch_id' AS column_name, 'null' AS rule_id, COUNTIF(branch_id IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('branch_id' AS column_name, 'blank' AS rule_id, COUNTIF(branch_id IS NOT NULL AND TRIM(branch_id)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('branch_id' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(branch_id != TRIM(branch_id)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('branch_id' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(branch_id))>20) AS affected_rows, 'Dictionary limit 20 after trim' AS interpretation),
STRUCT('merchant_name' AS column_name, 'null' AS rule_id, COUNTIF(merchant_name IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('merchant_name' AS column_name, 'blank' AS rule_id, COUNTIF(merchant_name IS NOT NULL AND TRIM(merchant_name)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('merchant_name' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(merchant_name != TRIM(merchant_name)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('merchant_name' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(merchant_name))>150) AS affected_rows, 'Dictionary limit 150 after trim' AS interpretation),
STRUCT('merchant_category' AS column_name, 'null' AS rule_id, COUNTIF(merchant_category IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('merchant_category' AS column_name, 'blank' AS rule_id, COUNTIF(merchant_category IS NOT NULL AND TRIM(merchant_category)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('merchant_category' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(merchant_category != TRIM(merchant_category)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('merchant_category' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(merchant_category))>50) AS affected_rows, 'Dictionary limit 50 after trim' AS interpretation),
STRUCT('transaction_country' AS column_name, 'null' AS rule_id, COUNTIF(transaction_country IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('transaction_country' AS column_name, 'blank' AS rule_id, COUNTIF(transaction_country IS NOT NULL AND TRIM(transaction_country)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('transaction_country' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(transaction_country != TRIM(transaction_country)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('transaction_country' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(transaction_country))>50) AS affected_rows, 'Dictionary limit 50 after trim' AS interpretation),
STRUCT('transaction_city' AS column_name, 'null' AS rule_id, COUNTIF(transaction_city IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('transaction_city' AS column_name, 'blank' AS rule_id, COUNTIF(transaction_city IS NOT NULL AND TRIM(transaction_city)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('transaction_city' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(transaction_city != TRIM(transaction_city)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('transaction_city' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(transaction_city))>100) AS affected_rows, 'Dictionary limit 100 after trim' AS interpretation),
STRUCT('transaction_status' AS column_name, 'null' AS rule_id, COUNTIF(transaction_status IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('transaction_status' AS column_name, 'blank' AS rule_id, COUNTIF(transaction_status IS NOT NULL AND TRIM(transaction_status)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('transaction_status' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(transaction_status != TRIM(transaction_status)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('transaction_status' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(transaction_status))>20) AS affected_rows, 'Dictionary limit 20 after trim' AS interpretation),
STRUCT('response_code' AS column_name, 'null' AS rule_id, COUNTIF(response_code IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('response_code' AS column_name, 'blank' AS rule_id, COUNTIF(response_code IS NOT NULL AND TRIM(response_code)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('response_code' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(response_code != TRIM(response_code)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('response_code' AS column_name, 'length_exceeded' AS rule_id, COUNTIF(CHAR_LENGTH(TRIM(response_code))>10) AS affected_rows, 'Dictionary limit 10 after trim' AS interpretation),
STRUCT('is_fraud' AS column_name, 'null' AS rule_id, COUNTIF(is_fraud IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
STRUCT('is_fraud' AS column_name, 'blank' AS rule_id, COUNTIF(is_fraud IS NOT NULL AND TRIM(is_fraud)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('is_fraud' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(is_fraud != TRIM(is_fraud)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('fraud_score' AS column_name, 'null' AS rule_id, COUNTIF(fraud_score IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('fraud_score' AS column_name, 'blank' AS rule_id, COUNTIF(fraud_score IS NOT NULL AND TRIM(fraud_score)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('fraud_score' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(fraud_score != TRIM(fraud_score)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('latitude' AS column_name, 'null' AS rule_id, COUNTIF(latitude IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('latitude' AS column_name, 'blank' AS rule_id, COUNTIF(latitude IS NOT NULL AND TRIM(latitude)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('latitude' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(latitude != TRIM(latitude)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('longitude' AS column_name, 'null' AS rule_id, COUNTIF(longitude IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
STRUCT('longitude' AS column_name, 'blank' AS rule_id, COUNTIF(longitude IS NOT NULL AND TRIM(longitude)='') AS affected_rows, 'Blank; separate from original null' AS interpretation),
STRUCT('longitude' AS column_name, 'surrounding_whitespace' AS rule_id, COUNTIF(longitude != TRIM(longitude)) AS affected_rows, 'Normalization candidate' AS interpretation),
STRUCT('transaction_date' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(transaction_date),'') IS NOT NULL AND SAFE_CAST(TRIM(transaction_date) AS TIMESTAMP) IS NULL) AS affected_rows, 'TIMESTAMP parser; excludes blanks' AS interpretation),
STRUCT('process_date' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(process_date),'') IS NOT NULL AND SAFE_CAST(TRIM(process_date) AS DATE) IS NULL) AS affected_rows, 'DATE parser; excludes blanks' AS interpretation),
STRUCT('amount' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(amount),'') IS NOT NULL AND SAFE_CAST(TRIM(amount) AS BIGNUMERIC) IS NULL) AS affected_rows, 'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('amount' AS column_name, 'decimal_overflow' AS rule_id, COUNTIF(ABS(SAFE_CAST(TRIM(amount) AS BIGNUMERIC))>=10000000000000) AS affected_rows, 'DECIMAL(15,2) integer magnitude' AS interpretation),
STRUCT('amount' AS column_name, 'excess_scale' AS rule_id, COUNTIF(SAFE_CAST(TRIM(amount) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(amount) AS BIGNUMERIC),2)) AS affected_rows, 'No silent rounding to 2 decimals' AS interpretation),
STRUCT('amount_usd' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(amount_usd),'') IS NOT NULL AND SAFE_CAST(TRIM(amount_usd) AS BIGNUMERIC) IS NULL) AS affected_rows, 'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('amount_usd' AS column_name, 'decimal_overflow' AS rule_id, COUNTIF(ABS(SAFE_CAST(TRIM(amount_usd) AS BIGNUMERIC))>=10000000000000) AS affected_rows, 'DECIMAL(15,2) integer magnitude' AS interpretation),
STRUCT('amount_usd' AS column_name, 'excess_scale' AS rule_id, COUNTIF(SAFE_CAST(TRIM(amount_usd) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(amount_usd) AS BIGNUMERIC),2)) AS affected_rows, 'No silent rounding to 2 decimals' AS interpretation),
STRUCT('fraud_score' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(fraud_score),'') IS NOT NULL AND SAFE_CAST(TRIM(fraud_score) AS BIGNUMERIC) IS NULL) AS affected_rows, 'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('fraud_score' AS column_name, 'decimal_overflow' AS rule_id, COUNTIF(ABS(SAFE_CAST(TRIM(fraud_score) AS BIGNUMERIC))>=1000) AS affected_rows, 'DECIMAL(5,2) integer magnitude' AS interpretation),
STRUCT('fraud_score' AS column_name, 'excess_scale' AS rule_id, COUNTIF(SAFE_CAST(TRIM(fraud_score) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(fraud_score) AS BIGNUMERIC),2)) AS affected_rows, 'No silent rounding to 2 decimals' AS interpretation),
STRUCT('latitude' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(latitude),'') IS NOT NULL AND SAFE_CAST(TRIM(latitude) AS BIGNUMERIC) IS NULL) AS affected_rows, 'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('latitude' AS column_name, 'decimal_overflow' AS rule_id, COUNTIF(ABS(SAFE_CAST(TRIM(latitude) AS BIGNUMERIC))>=1000) AS affected_rows, 'DECIMAL(10,7) integer magnitude' AS interpretation),
STRUCT('latitude' AS column_name, 'excess_scale' AS rule_id, COUNTIF(SAFE_CAST(TRIM(latitude) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(latitude) AS BIGNUMERIC),7)) AS affected_rows, 'No silent rounding to 7 decimals' AS interpretation),
STRUCT('longitude' AS column_name, 'conversion_failed' AS rule_id, COUNTIF(NULLIF(TRIM(longitude),'') IS NOT NULL AND SAFE_CAST(TRIM(longitude) AS BIGNUMERIC) IS NULL) AS affected_rows, 'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('longitude' AS column_name, 'decimal_overflow' AS rule_id, COUNTIF(ABS(SAFE_CAST(TRIM(longitude) AS BIGNUMERIC))>=1000) AS affected_rows, 'DECIMAL(10,7) integer magnitude' AS interpretation),
STRUCT('longitude' AS column_name, 'excess_scale' AS rule_id, COUNTIF(SAFE_CAST(TRIM(longitude) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(longitude) AS BIGNUMERIC),7)) AS affected_rows, 'No silent rounding to 7 decimals' AS interpretation),
STRUCT('fraud_score' AS column_name, 'outside_range' AS rule_id, COUNTIF(SAFE_CAST(TRIM(fraud_score) AS BIGNUMERIC)<0 OR SAFE_CAST(TRIM(fraud_score) AS BIGNUMERIC)>100) AS affected_rows, 'Allowed numeric range 0 to 100' AS interpretation),
STRUCT('latitude' AS column_name, 'outside_range' AS rule_id, COUNTIF(SAFE_CAST(TRIM(latitude) AS BIGNUMERIC)<-90 OR SAFE_CAST(TRIM(latitude) AS BIGNUMERIC)>90) AS affected_rows, 'Allowed numeric range -90 to 90' AS interpretation),
STRUCT('longitude' AS column_name, 'outside_range' AS rule_id, COUNTIF(SAFE_CAST(TRIM(longitude) AS BIGNUMERIC)<-180 OR SAFE_CAST(TRIM(longitude) AS BIGNUMERIC)>180) AS affected_rows, 'Allowed numeric range -180 to 180' AS interpretation),
STRUCT('amount' AS column_name, 'negative_value' AS rule_id, COUNTIF(SAFE_CAST(TRIM(amount) AS BIGNUMERIC)<0) AS affected_rows, 'Observation; transaction semantics pending' AS interpretation),
STRUCT('amount' AS column_name, 'zero_value' AS rule_id, COUNTIF(SAFE_CAST(TRIM(amount) AS BIGNUMERIC)=0) AS affected_rows, 'Observation; no rejection agreed' AS interpretation),
STRUCT('amount_usd' AS column_name, 'negative_value' AS rule_id, COUNTIF(SAFE_CAST(TRIM(amount_usd) AS BIGNUMERIC)<0) AS affected_rows, 'Observation; transaction semantics pending' AS interpretation),
STRUCT('amount_usd' AS column_name, 'zero_value' AS rule_id, COUNTIF(SAFE_CAST(TRIM(amount_usd) AS BIGNUMERIC)=0) AS affected_rows, 'Observation; no rejection agreed' AS interpretation),
STRUCT('transaction_type' AS column_name, 'outside_dictionary_domain' AS rule_id, COUNTIF(NULLIF(TRIM(transaction_type),'') IS NOT NULL AND TRIM(transaction_type) NOT IN ('Deposit','Withdrawal','Transfer','Payment','Purchase','Adjustment')) AS affected_rows, 'Case sensitive; inspect translations before enforcing' AS interpretation),
STRUCT('transaction_category' AS column_name, 'outside_dictionary_domain' AS rule_id, COUNTIF(NULLIF(TRIM(transaction_category),'') IS NOT NULL AND TRIM(transaction_category) NOT IN ('Food','Transport','Services','Entertainment','Health','Other')) AS affected_rows, 'Case sensitive; inspect translations before enforcing' AS interpretation),
STRUCT('channel' AS column_name, 'outside_dictionary_domain' AS rule_id, COUNTIF(NULLIF(TRIM(channel),'') IS NOT NULL AND TRIM(channel) NOT IN ('ATM','Branch','Web','App','POS','Transfer')) AS affected_rows, 'Case sensitive; inspect translations before enforcing' AS interpretation),
STRUCT('transaction_status' AS column_name, 'outside_dictionary_domain' AS rule_id, COUNTIF(NULLIF(TRIM(transaction_status),'') IS NOT NULL AND TRIM(transaction_status) NOT IN ('Approved','Declined','Pending','Reversed')) AS affected_rows, 'Case sensitive; inspect translations before enforcing' AS interpretation),
STRUCT('is_fraud' AS column_name, 'unknown_boolean' AS rule_id, COUNTIF(NULLIF(TRIM(is_fraud),'') IS NOT NULL AND LOWER(TRIM(is_fraud)) NOT IN ('true','false','1','0','t','f','yes','no','y','n')) AS affected_rows, 'Candidate boolean spellings' AS interpretation),
STRUCT('process_date' AS column_name, 'before_transaction_date' AS rule_id, COUNTIF(SAFE_CAST(TRIM(process_date) AS DATE)<DATE(SAFE_CAST(TRIM(transaction_date) AS TIMESTAMP))) AS affected_rows, 'Observation; default UTC needs source confirmation' AS interpretation),
STRUCT('latitude' AS column_name, 'incomplete_coordinate_pair' AS rule_id, COUNTIF((NULLIF(TRIM(latitude),'') IS NULL)!=(NULLIF(TRIM(longitude),'') IS NULL)) AS affected_rows, 'Only one coordinate provided' AS interpretation)
  ] AS metrics FROM profile_input), UNNEST(metrics) AS metric;

  INSERT INTO measurements
  SELECT 'transaction_id','duplicate_key_excess_after_trim',COALESCE(SUM(n-1),0),
    'Excess rows per nonblank transaction ID; no row removed'
  FROM (SELECT TRIM(transaction_id) AS normalized_id, COUNT(*) AS n
    FROM profile_input WHERE NULLIF(TRIM(transaction_id),'') IS NOT NULL
    GROUP BY normalized_id HAVING COUNT(*)>1);

  INSERT INTO measurements
  SELECT '*','exact_duplicate_excess',COALESCE(SUM(n-1),0),'Additional identical business rows'
  FROM (SELECT TO_JSON_STRING(STRUCT(transaction_id,transaction_date,process_date,product_id,customer_id,transaction_type,transaction_category,amount,currency,amount_usd,channel,branch_id,merchant_name,merchant_category,transaction_country,transaction_city,transaction_status,response_code,is_fraud,fraud_score,latitude,longitude)) AS row_content,COUNT(*) AS n
    FROM profile_input GROUP BY row_content HAVING COUNT(*)>1);

  CREATE TEMP TABLE reference_customers AS
  SELECT customer_id,_curation_run_id FROM `hackaton-509923.bank_curated.customers`
  FOR SYSTEM_TIME AS OF v_snapshot;
  CREATE TEMP TABLE reference_products AS
  SELECT product_id,customer_id,currency,_curation_run_id FROM `hackaton-509923.bank_curated.products`
  FOR SYSTEM_TIME AS OF v_snapshot;
  ASSERT (SELECT COUNT(*) FROM reference_customers)>0 AS 'Publish customers before profiling';
  ASSERT (SELECT COUNT(*) FROM reference_products)>0 AS 'Publish products before profiling';
  ASSERT (SELECT COUNT(*)=COUNT(DISTINCT product_id) FROM reference_products)
    AS 'Curated product IDs must be unique';
  ASSERT (SELECT COUNT(*)=COUNT(DISTINCT customer_id) FROM reference_customers)
    AS 'Curated customer IDs must be unique';
  ASSERT (SELECT COUNT(DISTINCT _curation_run_id) FROM reference_products)=1
    AS 'Expected one published products run';

  -- Only quarantine belonging to the currently published products run.
  CREATE TEMP TABLE quarantined_products AS
  SELECT DISTINCT NULLIF(TRIM(JSON_VALUE(raw_json,'$.product_id')),'') AS product_id
  FROM `hackaton-509923.bank_quarantine.products_rejected`
  FOR SYSTEM_TIME AS OF v_snapshot
  WHERE run_id IN (SELECT DISTINCT _curation_run_id FROM reference_products);

  INSERT INTO measurements
  SELECT 'customer_id','missing_curated_customer',COUNT(*),'Nonblank customer absent from curated at snapshot'
  FROM profile_input AS t
  WHERE NULLIF(TRIM(t.customer_id),'') IS NOT NULL
    AND NOT EXISTS(SELECT 1 FROM reference_customers c WHERE c.customer_id=TRIM(t.customer_id));

  INSERT INTO measurements
  SELECT 'product_id','missing_curated_product',COUNT(*),'Includes products found in quarantine; metrics overlap'
  FROM profile_input AS t
  WHERE NULLIF(TRIM(t.product_id),'') IS NOT NULL
    AND NOT EXISTS(SELECT 1 FROM reference_products p WHERE p.product_id=TRIM(t.product_id));

  INSERT INTO measurements
  SELECT 'product_id','missing_product_found_in_quarantine',COUNT(*),'Subset of missing curated products; current published run only'
  FROM profile_input AS t
  WHERE NULLIF(TRIM(t.product_id),'') IS NOT NULL
    AND NOT EXISTS(SELECT 1 FROM reference_products p WHERE p.product_id=TRIM(t.product_id))
    AND EXISTS(SELECT 1 FROM quarantined_products q WHERE q.product_id=TRIM(t.product_id));

  INSERT INTO measurements
  SELECT 'product_id','missing_product_not_in_quarantine',COUNT(*),'Absent from curated and retained quarantine for current run'
  FROM profile_input AS t
  WHERE NULLIF(TRIM(t.product_id),'') IS NOT NULL
    AND NOT EXISTS(SELECT 1 FROM reference_products p WHERE p.product_id=TRIM(t.product_id))
    AND NOT EXISTS(SELECT 1 FROM quarantined_products q WHERE q.product_id=TRIM(t.product_id));

  INSERT INTO measurements
  SELECT 'customer_id','product_owner_mismatch',COUNT(*),'Nonblank customer differs from published product owner'
  FROM profile_input t JOIN reference_products p ON p.product_id=TRIM(t.product_id)
  WHERE NULLIF(TRIM(t.customer_id),'') IS NOT NULL AND TRIM(t.customer_id)!=p.customer_id;

  INSERT INTO measurements
  SELECT 'currency','differs_from_product_currency',COUNT(*),'Observation only; cross-currency payments may be valid'
  FROM profile_input t JOIN reference_products p ON p.product_id=TRIM(t.product_id)
  WHERE NULLIF(TRIM(t.currency),'') IS NOT NULL AND TRIM(t.currency)!=p.currency;

  CREATE TABLE IF NOT EXISTS `hackaton-509923.bank_ops.profile_domains` (
    run_id STRING,recorded_at TIMESTAMP,source_table STRING,
    column_name STRING,value STRING,row_count INT64
  ) PARTITION BY DATE(recorded_at) OPTIONS(partition_expiration_days=30);
  -- Persist metrics and terminal success together; failed runs have no
  -- partially persisted metric set.
  BEGIN TRANSACTION;
  SET v_transaction_open = TRUE;
  INSERT INTO `hackaton-509923.bank_ops.profile_domains`
  SELECT v_run_id,v_started,'hackaton-509923.bank_raw.transactions',d.column_name,d.value,COUNT(*)
  FROM profile_input,UNNEST([
STRUCT('transaction_type' AS column_name,TRIM(transaction_type) AS value),
STRUCT('transaction_category' AS column_name,TRIM(transaction_category) AS value),
STRUCT('currency' AS column_name,TRIM(currency) AS value),
STRUCT('channel' AS column_name,TRIM(channel) AS value),
STRUCT('transaction_country' AS column_name,TRIM(transaction_country) AS value),
STRUCT('transaction_status' AS column_name,TRIM(transaction_status) AS value),
STRUCT('is_fraud' AS column_name,TRIM(is_fraud) AS value)
  ]) d GROUP BY d.column_name,d.value;

  INSERT INTO `hackaton-509923.bank_ops.profile_results`
  SELECT v_run_id, v_started, 'hackaton-509923.bank_raw.transactions',
    column_name, rule_id, affected_rows, v_rows,
    IF(rule_id = 'latest_version_conflicting_keys', NULL,
       ROUND(100.0 * SAFE_DIVIDE(affected_rows, v_rows), 4)),
    interpretation
  FROM measurements;

  UPDATE `hackaton-509923.bank_ops.profile_runs`
  SET status = 'SUCCEEDED', finished_at = CURRENT_TIMESTAMP(), input_rows = v_rows,
    note=CONCAT('Reference snapshot: source_snapshot_at; customers runs: ',
      COALESCE((SELECT STRING_AGG(DISTINCT _curation_run_id,',') FROM reference_customers),'unknown'),
      '; products runs: ',
      COALESCE((SELECT STRING_AGG(DISTINCT _curation_run_id,',') FROM reference_products),'unknown'),
      '; branch FK and currency dictionary pending; observations are not publication rules')
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

DROP TABLE profile_input;
DROP TABLE measurements;

SELECT run_id, status, input_rows, source_snapshot_at
FROM `hackaton-509923.bank_ops.profile_runs`
WHERE run_id = v_run_id;

SELECT column_name, rule_id, affected_rows, total_rows, affected_pct, interpretation
FROM `hackaton-509923.bank_ops.profile_results`
WHERE run_id = v_run_id AND affected_rows > 0
ORDER BY affected_rows DESC, column_name, rule_id;

SELECT column_name,value,row_count
FROM `hackaton-509923.bank_ops.profile_domains`
WHERE run_id=v_run_id ORDER BY column_name,row_count DESC;
