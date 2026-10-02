-- branches profiling v1.0.0. Run the whole script in us-central1.
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
VALUES(v_run_id, '1.0.0', 'hackaton-509923.bank_raw.branches',
  v_snapshot, v_started, NULL, 'RUNNING', NULL, NULL);

BEGIN
  -- Single stable input shared by all metrics, even if raw is replaced later.
  CREATE TEMP TABLE profile_input AS
  SELECT * FROM `hackaton-509923.bank_raw.branches`
  FOR SYSTEM_TIME AS OF v_snapshot;

  SET v_rows = (SELECT COUNT(*) FROM profile_input);
  ASSERT v_rows > 0 AS 'Profiling input has no records';

  CREATE TEMP TABLE measurements AS SELECT metric.* FROM (SELECT [
STRUCT('branch_id' AS column_name,'null' AS rule_id,COUNTIF(branch_id IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('branch_id' AS column_name,'blank' AS rule_id,COUNTIF(branch_id IS NOT NULL AND TRIM(branch_id)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('branch_id' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(branch_id!=TRIM(branch_id)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('branch_id' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(branch_id))>20) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('branch_code' AS column_name,'null' AS rule_id,COUNTIF(branch_code IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('branch_code' AS column_name,'blank' AS rule_id,COUNTIF(branch_code IS NOT NULL AND TRIM(branch_code)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('branch_code' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(branch_code!=TRIM(branch_code)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('branch_code' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(branch_code))>10) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('branch_name' AS column_name,'null' AS rule_id,COUNTIF(branch_name IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('branch_name' AS column_name,'blank' AS rule_id,COUNTIF(branch_name IS NOT NULL AND TRIM(branch_name)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('branch_name' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(branch_name!=TRIM(branch_name)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('branch_name' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(branch_name))>100) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('branch_type' AS column_name,'null' AS rule_id,COUNTIF(branch_type IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('branch_type' AS column_name,'blank' AS rule_id,COUNTIF(branch_type IS NOT NULL AND TRIM(branch_type)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('branch_type' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(branch_type!=TRIM(branch_type)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('branch_type' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(branch_type))>30) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('address' AS column_name,'null' AS rule_id,COUNTIF(address IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('address' AS column_name,'blank' AS rule_id,COUNTIF(address IS NOT NULL AND TRIM(address)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('address' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(address!=TRIM(address)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('address' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(address))>200) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('city' AS column_name,'null' AS rule_id,COUNTIF(city IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('city' AS column_name,'blank' AS rule_id,COUNTIF(city IS NOT NULL AND TRIM(city)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('city' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(city!=TRIM(city)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('city' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(city))>100) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('state' AS column_name,'null' AS rule_id,COUNTIF(state IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('state' AS column_name,'blank' AS rule_id,COUNTIF(state IS NOT NULL AND TRIM(state)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('state' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(state!=TRIM(state)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('state' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(state))>100) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('country' AS column_name,'null' AS rule_id,COUNTIF(country IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('country' AS column_name,'blank' AS rule_id,COUNTIF(country IS NOT NULL AND TRIM(country)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('country' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(country!=TRIM(country)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('country' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(country))>50) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('postal_code' AS column_name,'null' AS rule_id,COUNTIF(postal_code IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('postal_code' AS column_name,'blank' AS rule_id,COUNTIF(postal_code IS NOT NULL AND TRIM(postal_code)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('postal_code' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(postal_code!=TRIM(postal_code)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('postal_code' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(postal_code))>10) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('geographic_zone' AS column_name,'null' AS rule_id,COUNTIF(geographic_zone IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('geographic_zone' AS column_name,'blank' AS rule_id,COUNTIF(geographic_zone IS NOT NULL AND TRIM(geographic_zone)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('geographic_zone' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(geographic_zone!=TRIM(geographic_zone)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('geographic_zone' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(geographic_zone))>50) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('phone' AS column_name,'null' AS rule_id,COUNTIF(phone IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('phone' AS column_name,'blank' AS rule_id,COUNTIF(phone IS NOT NULL AND TRIM(phone)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('phone' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(phone!=TRIM(phone)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('phone' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(phone))>20) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('email' AS column_name,'null' AS rule_id,COUNTIF(email IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('email' AS column_name,'blank' AS rule_id,COUNTIF(email IS NOT NULL AND TRIM(email)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('email' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(email!=TRIM(email)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('email' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(email))>100) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('opening_time' AS column_name,'null' AS rule_id,COUNTIF(opening_time IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('opening_time' AS column_name,'blank' AS rule_id,COUNTIF(opening_time IS NOT NULL AND TRIM(opening_time)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('opening_time' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(opening_time!=TRIM(opening_time)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('closing_time' AS column_name,'null' AS rule_id,COUNTIF(closing_time IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('closing_time' AS column_name,'blank' AS rule_id,COUNTIF(closing_time IS NOT NULL AND TRIM(closing_time)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('closing_time' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(closing_time!=TRIM(closing_time)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('has_atms' AS column_name,'null' AS rule_id,COUNTIF(has_atms IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('has_atms' AS column_name,'blank' AS rule_id,COUNTIF(has_atms IS NOT NULL AND TRIM(has_atms)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('has_atms' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(has_atms!=TRIM(has_atms)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('atm_count' AS column_name,'null' AS rule_id,COUNTIF(atm_count IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('atm_count' AS column_name,'blank' AS rule_id,COUNTIF(atm_count IS NOT NULL AND TRIM(atm_count)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('atm_count' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(atm_count!=TRIM(atm_count)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('has_teller_windows' AS column_name,'null' AS rule_id,COUNTIF(has_teller_windows IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('has_teller_windows' AS column_name,'blank' AS rule_id,COUNTIF(has_teller_windows IS NOT NULL AND TRIM(has_teller_windows)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('has_teller_windows' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(has_teller_windows!=TRIM(has_teller_windows)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('teller_window_count' AS column_name,'null' AS rule_id,COUNTIF(teller_window_count IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('teller_window_count' AS column_name,'blank' AS rule_id,COUNTIF(teller_window_count IS NOT NULL AND TRIM(teller_window_count)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('teller_window_count' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(teller_window_count!=TRIM(teller_window_count)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('latitude' AS column_name,'null' AS rule_id,COUNTIF(latitude IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('latitude' AS column_name,'blank' AS rule_id,COUNTIF(latitude IS NOT NULL AND TRIM(latitude)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('latitude' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(latitude!=TRIM(latitude)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('longitude' AS column_name,'null' AS rule_id,COUNTIF(longitude IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('longitude' AS column_name,'blank' AS rule_id,COUNTIF(longitude IS NOT NULL AND TRIM(longitude)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('longitude' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(longitude!=TRIM(longitude)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('branch_opening_date' AS column_name,'null' AS rule_id,COUNTIF(branch_opening_date IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('branch_opening_date' AS column_name,'blank' AS rule_id,COUNTIF(branch_opening_date IS NOT NULL AND TRIM(branch_opening_date)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('branch_opening_date' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(branch_opening_date!=TRIM(branch_opening_date)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('branch_status' AS column_name,'null' AS rule_id,COUNTIF(branch_status IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('branch_status' AS column_name,'blank' AS rule_id,COUNTIF(branch_status IS NOT NULL AND TRIM(branch_status)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('branch_status' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(branch_status!=TRIM(branch_status)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('branch_status' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(branch_status))>20) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('opening_time' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(opening_time),'') IS NOT NULL AND SAFE_CAST(TRIM(opening_time) AS TIME) IS NULL) AS affected_rows,'TIME parser; excludes blanks' AS interpretation),
STRUCT('closing_time' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(closing_time),'') IS NOT NULL AND SAFE_CAST(TRIM(closing_time) AS TIME) IS NULL) AS affected_rows,'TIME parser; excludes blanks' AS interpretation),
STRUCT('branch_opening_date' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(branch_opening_date),'') IS NOT NULL AND SAFE_CAST(TRIM(branch_opening_date) AS DATE) IS NULL) AS affected_rows,'DATE parser; excludes blanks' AS interpretation),
STRUCT('atm_count' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(atm_count),'') IS NOT NULL AND SAFE_CAST(TRIM(atm_count) AS BIGNUMERIC) IS NULL) AS affected_rows,'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('teller_window_count' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(teller_window_count),'') IS NOT NULL AND SAFE_CAST(TRIM(teller_window_count) AS BIGNUMERIC) IS NULL) AS affected_rows,'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('latitude' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(latitude),'') IS NOT NULL AND SAFE_CAST(TRIM(latitude) AS BIGNUMERIC) IS NULL) AS affected_rows,'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('longitude' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(longitude),'') IS NOT NULL AND SAFE_CAST(TRIM(longitude) AS BIGNUMERIC) IS NULL) AS affected_rows,'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('atm_count' AS column_name,'fractional_value' AS rule_id,COUNTIF(SAFE_CAST(TRIM(atm_count) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(atm_count) AS BIGNUMERIC))) AS affected_rows,'Integer count; no silent rounding' AS interpretation),
STRUCT('atm_count' AS column_name,'int64_overflow' AS rule_id,COUNTIF(SAFE_CAST(TRIM(atm_count) AS BIGNUMERIC) < -9223372036854775808 OR SAFE_CAST(TRIM(atm_count) AS BIGNUMERIC)>9223372036854775807) AS affected_rows,'INT64 bounds' AS interpretation),
STRUCT('atm_count' AS column_name,'negative_value' AS rule_id,COUNTIF(SAFE_CAST(TRIM(atm_count) AS BIGNUMERIC)<0) AS affected_rows,'Negative equipment count' AS interpretation),
STRUCT('teller_window_count' AS column_name,'fractional_value' AS rule_id,COUNTIF(SAFE_CAST(TRIM(teller_window_count) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(teller_window_count) AS BIGNUMERIC))) AS affected_rows,'Integer count; no silent rounding' AS interpretation),
STRUCT('teller_window_count' AS column_name,'int64_overflow' AS rule_id,COUNTIF(SAFE_CAST(TRIM(teller_window_count) AS BIGNUMERIC) < -9223372036854775808 OR SAFE_CAST(TRIM(teller_window_count) AS BIGNUMERIC)>9223372036854775807) AS affected_rows,'INT64 bounds' AS interpretation),
STRUCT('teller_window_count' AS column_name,'negative_value' AS rule_id,COUNTIF(SAFE_CAST(TRIM(teller_window_count) AS BIGNUMERIC)<0) AS affected_rows,'Negative equipment count' AS interpretation),
STRUCT('latitude' AS column_name,'decimal_overflow' AS rule_id,COUNTIF(ABS(SAFE_CAST(TRIM(latitude) AS BIGNUMERIC))>=1000) AS affected_rows,'DECIMAL(10,7) magnitude' AS interpretation),
STRUCT('latitude' AS column_name,'excess_scale' AS rule_id,COUNTIF(SAFE_CAST(TRIM(latitude) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(latitude) AS BIGNUMERIC),7)) AS affected_rows,'No silent rounding' AS interpretation),
STRUCT('latitude' AS column_name,'outside_range' AS rule_id,COUNTIF(ABS(SAFE_CAST(TRIM(latitude) AS BIGNUMERIC))>90) AS affected_rows,'Coordinate magnitude up to 90' AS interpretation),
STRUCT('longitude' AS column_name,'decimal_overflow' AS rule_id,COUNTIF(ABS(SAFE_CAST(TRIM(longitude) AS BIGNUMERIC))>=1000) AS affected_rows,'DECIMAL(10,7) magnitude' AS interpretation),
STRUCT('longitude' AS column_name,'excess_scale' AS rule_id,COUNTIF(SAFE_CAST(TRIM(longitude) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(longitude) AS BIGNUMERIC),7)) AS affected_rows,'No silent rounding' AS interpretation),
STRUCT('longitude' AS column_name,'outside_range' AS rule_id,COUNTIF(ABS(SAFE_CAST(TRIM(longitude) AS BIGNUMERIC))>180) AS affected_rows,'Coordinate magnitude up to 180' AS interpretation),
STRUCT('has_atms' AS column_name,'unknown_boolean' AS rule_id,COUNTIF(NULLIF(TRIM(has_atms),'') IS NOT NULL AND LOWER(TRIM(has_atms)) NOT IN ('true','false','1','0','t','f','yes','no','y','n')) AS affected_rows,'Candidate boolean spellings' AS interpretation),
STRUCT('atm_count' AS column_name,'positive_when_flag_false' AS rule_id,COUNTIF((LOWER(TRIM(has_atms)) IN ('false','0','f','no','n')) AND SAFE_CAST(TRIM(atm_count) AS BIGNUMERIC)>0) AS affected_rows,'Consistency observation; policy pending' AS interpretation),
STRUCT('atm_count' AS column_name,'zero_when_flag_true' AS rule_id,COUNTIF((LOWER(TRIM(has_atms)) IN ('true','1','t','yes','y')) AND SAFE_CAST(TRIM(atm_count) AS BIGNUMERIC)=0) AS affected_rows,'Consistency observation; policy pending' AS interpretation),
STRUCT('atm_count' AS column_name,'missing_when_flag_true' AS rule_id,COUNTIF((LOWER(TRIM(has_atms)) IN ('true','1','t','yes','y')) AND NULLIF(TRIM(atm_count),'') IS NULL) AS affected_rows,'Optional count absent; do not infer zero' AS interpretation),
STRUCT('has_teller_windows' AS column_name,'unknown_boolean' AS rule_id,COUNTIF(NULLIF(TRIM(has_teller_windows),'') IS NOT NULL AND LOWER(TRIM(has_teller_windows)) NOT IN ('true','false','1','0','t','f','yes','no','y','n')) AS affected_rows,'Candidate boolean spellings' AS interpretation),
STRUCT('teller_window_count' AS column_name,'positive_when_flag_false' AS rule_id,COUNTIF((LOWER(TRIM(has_teller_windows)) IN ('false','0','f','no','n')) AND SAFE_CAST(TRIM(teller_window_count) AS BIGNUMERIC)>0) AS affected_rows,'Consistency observation; policy pending' AS interpretation),
STRUCT('teller_window_count' AS column_name,'zero_when_flag_true' AS rule_id,COUNTIF((LOWER(TRIM(has_teller_windows)) IN ('true','1','t','yes','y')) AND SAFE_CAST(TRIM(teller_window_count) AS BIGNUMERIC)=0) AS affected_rows,'Consistency observation; policy pending' AS interpretation),
STRUCT('teller_window_count' AS column_name,'missing_when_flag_true' AS rule_id,COUNTIF((LOWER(TRIM(has_teller_windows)) IN ('true','1','t','yes','y')) AND NULLIF(TRIM(teller_window_count),'') IS NULL) AS affected_rows,'Optional count absent; do not infer zero' AS interpretation),
STRUCT('branch_type' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(branch_type),'') IS NOT NULL AND TRIM(branch_type) NOT IN ('Main','Express','Premium','Corporate')) AS affected_rows,'Inspect translations before enforcing' AS interpretation),
STRUCT('geographic_zone' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(geographic_zone),'') IS NOT NULL AND TRIM(geographic_zone) NOT IN ('Urban','Suburban','Rural')) AS affected_rows,'Inspect translations before enforcing' AS interpretation),
STRUCT('branch_status' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(branch_status),'') IS NOT NULL AND TRIM(branch_status) NOT IN ('Active','Temporarily Closed','Closed')) AS affected_rows,'Inspect translations before enforcing' AS interpretation),
STRUCT('closing_time' AS column_name,'not_after_opening' AS rule_id,COUNTIF(SAFE_CAST(TRIM(closing_time) AS TIME)<=SAFE_CAST(TRIM(opening_time) AS TIME)) AS affected_rows,'Observation; overnight or 24-hour schedules possible' AS interpretation),
STRUCT('latitude' AS column_name,'incomplete_coordinate_pair' AS rule_id,COUNTIF((NULLIF(TRIM(latitude),'') IS NULL)!=(NULLIF(TRIM(longitude),'') IS NULL)) AS affected_rows,'Only one coordinate supplied' AS interpretation)
] AS metrics FROM profile_input),UNNEST(metrics) AS metric;

INSERT INTO measurements
SELECT 'branch_id','duplicate_key_excess_after_trim',COALESCE(SUM(n-1),0),'Excess rows per nonblank key; no winner selected'
FROM (SELECT TRIM(branch_id) AS normalized_key,COUNT(*) AS n FROM profile_input
WHERE NULLIF(TRIM(branch_id),'') IS NOT NULL GROUP BY normalized_key HAVING COUNT(*)>1);

INSERT INTO measurements
SELECT 'branch_code','duplicate_key_excess_after_trim',COALESCE(SUM(n-1),0),'Excess rows per nonblank key; no winner selected'
FROM (SELECT TRIM(branch_code) AS normalized_key,COUNT(*) AS n FROM profile_input
WHERE NULLIF(TRIM(branch_code),'') IS NOT NULL GROUP BY normalized_key HAVING COUNT(*)>1);

INSERT INTO measurements
SELECT '*','exact_duplicate_excess',COALESCE(SUM(n-1),0),'Identical business rows beyond first'
FROM (SELECT TO_JSON_STRING(STRUCT(branch_id,branch_code,branch_name,branch_type,address,city,state,country,postal_code,geographic_zone,phone,email,opening_time,closing_time,has_atms,atm_count,has_teller_windows,teller_window_count,latitude,longitude,branch_opening_date,branch_status)) AS row_content,COUNT(*) AS n
FROM profile_input GROUP BY row_content HAVING COUNT(*)>1);
CREATE TABLE IF NOT EXISTS `hackaton-509923.bank_ops.profile_domains` (
run_id STRING,recorded_at TIMESTAMP,source_table STRING,column_name STRING,value STRING,row_count INT64
) PARTITION BY DATE(recorded_at) OPTIONS(partition_expiration_days=30);
  -- Persist metrics and terminal success together; failed runs have no
  -- partially persisted metric set.
  BEGIN TRANSACTION;
  SET v_transaction_open = TRUE;
INSERT INTO `hackaton-509923.bank_ops.profile_domains`
SELECT v_run_id,v_started,'hackaton-509923.bank_raw.branches',d.column_name,d.value,COUNT(*)
FROM profile_input,UNNEST([
STRUCT('branch_type' AS column_name,TRIM(branch_type) AS value),
STRUCT('country' AS column_name,TRIM(country) AS value),
STRUCT('geographic_zone' AS column_name,TRIM(geographic_zone) AS value),
STRUCT('branch_status' AS column_name,TRIM(branch_status) AS value),
STRUCT('has_atms' AS column_name,TRIM(has_atms) AS value),
STRUCT('has_teller_windows' AS column_name,TRIM(has_teller_windows) AS value),
STRUCT('opening_time' AS column_name,TRIM(opening_time) AS value),
STRUCT('closing_time' AS column_name,TRIM(closing_time) AS value)]) d GROUP BY d.column_name,d.value;

  INSERT INTO `hackaton-509923.bank_ops.profile_results`
  SELECT v_run_id, v_started, 'hackaton-509923.bank_raw.branches',
    column_name, rule_id, affected_rows, v_rows,
    IF(rule_id = 'latest_version_conflicting_keys', NULL,
       ROUND(100.0 * SAFE_DIVIDE(affected_rows, v_rows), 4)),
    interpretation
  FROM measurements;

  UPDATE `hackaton-509923.bank_ops.profile_runs`
  SET status = 'SUCCEEDED', finished_at = CURRENT_TIMESTAMP(), input_rows = v_rows,
      note='Schedules and equipment consistency are observations; country domain pending; no curated changes'
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

SELECT column_name,value,row_count FROM `hackaton-509923.bank_ops.profile_domains`
WHERE run_id=v_run_id ORDER BY column_name,row_count DESC;
