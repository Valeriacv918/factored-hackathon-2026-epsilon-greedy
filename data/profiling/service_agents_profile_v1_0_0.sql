-- service_agents profiling v1.0.0. Run the whole script in us-central1.
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
VALUES(v_run_id, '1.0.0', 'hackaton-509923.bank_raw.service_agents',
  v_snapshot, v_started, NULL, 'RUNNING', NULL, NULL);

BEGIN
  -- Single stable input shared by all metrics, even if raw is replaced later.
  CREATE TEMP TABLE profile_input AS
  SELECT * FROM `hackaton-509923.bank_raw.service_agents`
  FOR SYSTEM_TIME AS OF v_snapshot;

  SET v_rows = (SELECT COUNT(*) FROM profile_input);
  ASSERT v_rows > 0 AS 'Profiling input has no records';

  CREATE TEMP TABLE measurements AS SELECT metric.* FROM (SELECT [
STRUCT('agent_id' AS column_name,'null' AS rule_id,COUNTIF(agent_id IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('agent_id' AS column_name,'blank' AS rule_id,COUNTIF(agent_id IS NOT NULL AND TRIM(agent_id)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('agent_id' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(agent_id!=TRIM(agent_id)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('agent_id' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(agent_id))>20) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('employee_code' AS column_name,'null' AS rule_id,COUNTIF(employee_code IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('employee_code' AS column_name,'blank' AS rule_id,COUNTIF(employee_code IS NOT NULL AND TRIM(employee_code)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('employee_code' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(employee_code!=TRIM(employee_code)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('employee_code' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(employee_code))>15) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('first_name' AS column_name,'null' AS rule_id,COUNTIF(first_name IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('first_name' AS column_name,'blank' AS rule_id,COUNTIF(first_name IS NOT NULL AND TRIM(first_name)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('first_name' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(first_name!=TRIM(first_name)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('first_name' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(first_name))>100) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('last_name' AS column_name,'null' AS rule_id,COUNTIF(last_name IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('last_name' AS column_name,'blank' AS rule_id,COUNTIF(last_name IS NOT NULL AND TRIM(last_name)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('last_name' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(last_name!=TRIM(last_name)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('last_name' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(last_name))>100) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('email' AS column_name,'null' AS rule_id,COUNTIF(email IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('email' AS column_name,'blank' AS rule_id,COUNTIF(email IS NOT NULL AND TRIM(email)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('email' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(email!=TRIM(email)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('email' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(email))>100) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('phone' AS column_name,'null' AS rule_id,COUNTIF(phone IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('phone' AS column_name,'blank' AS rule_id,COUNTIF(phone IS NOT NULL AND TRIM(phone)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('phone' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(phone!=TRIM(phone)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('phone' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(phone))>20) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('native_accent' AS column_name,'null' AS rule_id,COUNTIF(native_accent IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('native_accent' AS column_name,'blank' AS rule_id,COUNTIF(native_accent IS NOT NULL AND TRIM(native_accent)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('native_accent' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(native_accent!=TRIM(native_accent)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('native_accent' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(native_accent))>50) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('country_of_origin' AS column_name,'null' AS rule_id,COUNTIF(country_of_origin IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('country_of_origin' AS column_name,'blank' AS rule_id,COUNTIF(country_of_origin IS NOT NULL AND TRIM(country_of_origin)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('country_of_origin' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(country_of_origin!=TRIM(country_of_origin)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('country_of_origin' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(country_of_origin))>50) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('assigned_branch_id' AS column_name,'null' AS rule_id,COUNTIF(assigned_branch_id IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('assigned_branch_id' AS column_name,'blank' AS rule_id,COUNTIF(assigned_branch_id IS NOT NULL AND TRIM(assigned_branch_id)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('assigned_branch_id' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(assigned_branch_id!=TRIM(assigned_branch_id)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('assigned_branch_id' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(assigned_branch_id))>20) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('agent_type' AS column_name,'null' AS rule_id,COUNTIF(agent_type IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('agent_type' AS column_name,'blank' AS rule_id,COUNTIF(agent_type IS NOT NULL AND TRIM(agent_type)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('agent_type' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(agent_type!=TRIM(agent_type)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('agent_type' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(agent_type))>30) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('experience_level' AS column_name,'null' AS rule_id,COUNTIF(experience_level IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('experience_level' AS column_name,'blank' AS rule_id,COUNTIF(experience_level IS NOT NULL AND TRIM(experience_level)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('experience_level' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(experience_level!=TRIM(experience_level)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('experience_level' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(experience_level))>20) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('languages' AS column_name,'null' AS rule_id,COUNTIF(languages IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('languages' AS column_name,'blank' AS rule_id,COUNTIF(languages IS NOT NULL AND TRIM(languages)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('languages' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(languages!=TRIM(languages)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('languages' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(languages))>100) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('specialty' AS column_name,'null' AS rule_id,COUNTIF(specialty IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('specialty' AS column_name,'blank' AS rule_id,COUNTIF(specialty IS NOT NULL AND TRIM(specialty)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('specialty' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(specialty!=TRIM(specialty)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('specialty' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(specialty))>100) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('hire_date' AS column_name,'null' AS rule_id,COUNTIF(hire_date IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('hire_date' AS column_name,'blank' AS rule_id,COUNTIF(hire_date IS NOT NULL AND TRIM(hire_date)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('hire_date' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(hire_date!=TRIM(hire_date)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('avg_csat' AS column_name,'null' AS rule_id,COUNTIF(avg_csat IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('avg_csat' AS column_name,'blank' AS rule_id,COUNTIF(avg_csat IS NOT NULL AND TRIM(avg_csat)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('avg_csat' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(avg_csat!=TRIM(avg_csat)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('total_monthly_interactions' AS column_name,'null' AS rule_id,COUNTIF(total_monthly_interactions IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('total_monthly_interactions' AS column_name,'blank' AS rule_id,COUNTIF(total_monthly_interactions IS NOT NULL AND TRIM(total_monthly_interactions)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('total_monthly_interactions' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(total_monthly_interactions!=TRIM(total_monthly_interactions)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('agent_status' AS column_name,'null' AS rule_id,COUNTIF(agent_status IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('agent_status' AS column_name,'blank' AS rule_id,COUNTIF(agent_status IS NOT NULL AND TRIM(agent_status)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('agent_status' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(agent_status!=TRIM(agent_status)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('agent_status' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(agent_status))>20) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('work_shift' AS column_name,'null' AS rule_id,COUNTIF(work_shift IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('work_shift' AS column_name,'blank' AS rule_id,COUNTIF(work_shift IS NOT NULL AND TRIM(work_shift)='') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('work_shift' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(work_shift!=TRIM(work_shift)) AS affected_rows,'Normalization candidate' AS interpretation),
STRUCT('work_shift' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(work_shift))>20) AS affected_rows,'Dictionary limit after trim' AS interpretation),
STRUCT('hire_date' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(hire_date),'') IS NOT NULL AND SAFE_CAST(TRIM(hire_date) AS DATE) IS NULL) AS affected_rows,'DATE parser; excludes blanks' AS interpretation),
STRUCT('avg_csat' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(avg_csat),'') IS NOT NULL AND SAFE_CAST(TRIM(avg_csat) AS BIGNUMERIC) IS NULL) AS affected_rows,'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('total_monthly_interactions' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(total_monthly_interactions),'') IS NOT NULL AND SAFE_CAST(TRIM(total_monthly_interactions) AS BIGNUMERIC) IS NULL) AS affected_rows,'BIGNUMERIC parser; excludes blanks' AS interpretation),
STRUCT('avg_csat' AS column_name,'decimal_overflow' AS rule_id,COUNTIF(ABS(SAFE_CAST(TRIM(avg_csat) AS BIGNUMERIC))>=10) AS affected_rows,'DECIMAL(3,2) magnitude' AS interpretation),
STRUCT('avg_csat' AS column_name,'excess_scale' AS rule_id,COUNTIF(SAFE_CAST(TRIM(avg_csat) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(avg_csat) AS BIGNUMERIC),2)) AS affected_rows,'No silent rounding' AS interpretation),
STRUCT('avg_csat' AS column_name,'outside_1_5' AS rule_id,COUNTIF(SAFE_CAST(TRIM(avg_csat) AS BIGNUMERIC)<1 OR SAFE_CAST(TRIM(avg_csat) AS BIGNUMERIC)>5) AS affected_rows,'Dictionary range; excludes null' AS interpretation),
STRUCT('total_monthly_interactions' AS column_name,'fractional_value' AS rule_id,COUNTIF(SAFE_CAST(TRIM(total_monthly_interactions) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(total_monthly_interactions) AS BIGNUMERIC))) AS affected_rows,'Must be integral; no rounding' AS interpretation),
STRUCT('total_monthly_interactions' AS column_name,'int64_overflow' AS rule_id,COUNTIF(SAFE_CAST(TRIM(total_monthly_interactions) AS BIGNUMERIC) < -9223372036854775808 OR SAFE_CAST(TRIM(total_monthly_interactions) AS BIGNUMERIC)>9223372036854775807) AS affected_rows,'INT64 bounds' AS interpretation),
STRUCT('total_monthly_interactions' AS column_name,'negative_value' AS rule_id,COUNTIF(SAFE_CAST(TRIM(total_monthly_interactions) AS BIGNUMERIC)<0) AS affected_rows,'Negative interaction count' AS interpretation),
STRUCT('native_accent' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(native_accent),'') IS NOT NULL AND TRIM(native_accent) NOT IN ('mexican','colombian','argentine')) AS affected_rows,'Case sensitive; review translations before enforcing' AS interpretation),
STRUCT('agent_type' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(agent_type),'') IS NOT NULL AND TRIM(agent_type) NOT IN ('Phone','In-Person','Digital','Hybrid')) AS affected_rows,'Case sensitive; review translations before enforcing' AS interpretation),
STRUCT('experience_level' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(experience_level),'') IS NOT NULL AND TRIM(experience_level) NOT IN ('Junior','Mid-Senior','Senior','Specialist')) AS affected_rows,'Case sensitive; review translations before enforcing' AS interpretation),
STRUCT('agent_status' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(agent_status),'') IS NOT NULL AND TRIM(agent_status) NOT IN ('Active','Vacation','Leave','Inactive')) AS affected_rows,'Case sensitive; review translations before enforcing' AS interpretation),
STRUCT('work_shift' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(work_shift),'') IS NOT NULL AND TRIM(work_shift) NOT IN ('Morning','Afternoon','Night','Rotating')) AS affected_rows,'Case sensitive; review translations before enforcing' AS interpretation)
] AS metrics FROM profile_input),UNNEST(metrics) AS metric;

INSERT INTO measurements
SELECT 'agent_id','duplicate_key_excess_after_trim',COALESCE(SUM(n-1),0),'Excess rows per nonblank key; no winner chosen'
FROM (SELECT TRIM(agent_id) AS normalized_key,COUNT(*) AS n FROM profile_input
WHERE NULLIF(TRIM(agent_id),'') IS NOT NULL GROUP BY normalized_key HAVING COUNT(*)>1);

INSERT INTO measurements
SELECT 'employee_code','duplicate_key_excess_after_trim',COALESCE(SUM(n-1),0),'Excess rows per nonblank key; no winner chosen'
FROM (SELECT TRIM(employee_code) AS normalized_key,COUNT(*) AS n FROM profile_input
WHERE NULLIF(TRIM(employee_code),'') IS NOT NULL GROUP BY normalized_key HAVING COUNT(*)>1);

INSERT INTO measurements
SELECT '*','exact_duplicate_excess',COALESCE(SUM(n-1),0),'Identical business rows beyond first'
FROM (SELECT TO_JSON_STRING(STRUCT(agent_id,employee_code,first_name,last_name,email,phone,native_accent,country_of_origin,assigned_branch_id,agent_type,experience_level,languages,specialty,hire_date,avg_csat,total_monthly_interactions,agent_status,work_shift)) AS row_content,COUNT(*) AS n
FROM profile_input GROUP BY row_content HAVING COUNT(*)>1);
CREATE TEMP TABLE reference_branches AS
SELECT branch_id,branch_status,_curation_run_id
FROM `hackaton-509923.bank_curated.branches` FOR SYSTEM_TIME AS OF v_snapshot;
ASSERT (SELECT COUNT(*)>0 AND COUNT(*)=COUNT(DISTINCT branch_id) AND COUNT(DISTINCT _curation_run_id)=1 FROM reference_branches)
AS 'Publish nonempty unique branches from one run before profiling';
INSERT INTO measurements
SELECT 'assigned_branch_id','missing_curated_branch',COUNT(*),'Nonblank branch absent from curated at snapshot'
FROM profile_input a WHERE NULLIF(TRIM(a.assigned_branch_id),'') IS NOT NULL
AND NOT EXISTS(SELECT 1 FROM reference_branches b WHERE b.branch_id=TRIM(a.assigned_branch_id));
INSERT INTO measurements
SELECT 'assigned_branch_id','branch_not_active',COUNT(*),'Observation only; existing closed branch remains a valid reference'
FROM profile_input a JOIN reference_branches b ON b.branch_id=TRIM(a.assigned_branch_id)
WHERE b.branch_status!='Active';
CREATE TABLE IF NOT EXISTS `hackaton-509923.bank_ops.profile_domains` (
run_id STRING,recorded_at TIMESTAMP,source_table STRING,column_name STRING,value STRING,row_count INT64
) PARTITION BY DATE(recorded_at) OPTIONS(partition_expiration_days=30);
  -- Persist metrics and terminal success together; failed runs have no
  -- partially persisted metric set.
  BEGIN TRANSACTION;
  SET v_transaction_open = TRUE;
INSERT INTO `hackaton-509923.bank_ops.profile_domains`
SELECT v_run_id,v_started,'hackaton-509923.bank_raw.service_agents',d.column_name,d.value,COUNT(*)
FROM profile_input,UNNEST([
STRUCT('native_accent' AS column_name,TRIM(native_accent) AS value),
STRUCT('country_of_origin' AS column_name,TRIM(country_of_origin) AS value),
STRUCT('agent_type' AS column_name,TRIM(agent_type) AS value),
STRUCT('experience_level' AS column_name,TRIM(experience_level) AS value),
STRUCT('languages' AS column_name,TRIM(languages) AS value),
STRUCT('specialty' AS column_name,TRIM(specialty) AS value),
STRUCT('agent_status' AS column_name,TRIM(agent_status) AS value),
STRUCT('work_shift' AS column_name,TRIM(work_shift) AS value)]) d GROUP BY d.column_name,d.value;

  INSERT INTO `hackaton-509923.bank_ops.profile_results`
  SELECT v_run_id, v_started, 'hackaton-509923.bank_raw.service_agents',
    column_name, rule_id, affected_rows, v_rows,
    IF(rule_id = 'latest_version_conflicting_keys', NULL,
       ROUND(100.0 * SAFE_DIVIDE(affected_rows, v_rows), 4)),
    interpretation
  FROM measurements;

  UPDATE `hackaton-509923.bank_ops.profile_runs`
  SET status = 'SUCCEEDED', finished_at = CURRENT_TIMESTAMP(), input_rows = v_rows,
 note=CONCAT('Reference branches at source_snapshot_at; runs: ',
 (SELECT STRING_AGG(DISTINCT _curation_run_id,',') FROM reference_branches),
 '; languages preserved as text; country dictionary pending; no curated changes')
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
