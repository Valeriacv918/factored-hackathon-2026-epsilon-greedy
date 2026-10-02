-- complaints profiling v1.0.0. Run the whole script in us-central1.
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
VALUES(v_run_id, '1.0.0', 'hackaton-509923.bank_raw.complaints',
  v_snapshot, v_started, NULL, 'RUNNING', NULL, NULL);

BEGIN
  -- Single stable input shared by all metrics, even if raw is replaced later.
  CREATE TEMP TABLE profile_input AS
  SELECT * FROM `hackaton-509923.bank_raw.complaints`
  FOR SYSTEM_TIME AS OF v_snapshot;

  SET v_rows = (SELECT COUNT(*) FROM profile_input);
  ASSERT v_rows > 0 AS 'Profiling input has no records';

  CREATE TEMP TABLE measurements AS SELECT metric.* FROM (SELECT [
STRUCT('complaint_id' AS column_name,'null' AS rule_id,COUNTIF(complaint_id IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('complaint_id' AS column_name,'blank' AS rule_id,COUNTIF(complaint_id IS NOT NULL AND TRIM(complaint_id) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('complaint_id' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(complaint_id!=TRIM(complaint_id)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('complaint_id' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(complaint_id))>30) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('creation_date' AS column_name,'null' AS rule_id,COUNTIF(creation_date IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('creation_date' AS column_name,'blank' AS rule_id,COUNTIF(creation_date IS NOT NULL AND TRIM(creation_date) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('creation_date' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(creation_date!=TRIM(creation_date)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('process_date' AS column_name,'null' AS rule_id,COUNTIF(process_date IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('process_date' AS column_name,'blank' AS rule_id,COUNTIF(process_date IS NOT NULL AND TRIM(process_date) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('process_date' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(process_date!=TRIM(process_date)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('customer_id' AS column_name,'null' AS rule_id,COUNTIF(customer_id IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('customer_id' AS column_name,'blank' AS rule_id,COUNTIF(customer_id IS NOT NULL AND TRIM(customer_id) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('customer_id' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(customer_id!=TRIM(customer_id)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('customer_id' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(customer_id))>20) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('case_type' AS column_name,'null' AS rule_id,COUNTIF(case_type IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('case_type' AS column_name,'blank' AS rule_id,COUNTIF(case_type IS NOT NULL AND TRIM(case_type) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('case_type' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(case_type!=TRIM(case_type)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('case_type' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(case_type))>30) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('category' AS column_name,'null' AS rule_id,COUNTIF(category IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('category' AS column_name,'blank' AS rule_id,COUNTIF(category IS NOT NULL AND TRIM(category) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('category' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(category!=TRIM(category)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('category' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(category))>100) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('subcategory' AS column_name,'null' AS rule_id,COUNTIF(subcategory IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('subcategory' AS column_name,'blank' AS rule_id,COUNTIF(subcategory IS NOT NULL AND TRIM(subcategory) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('subcategory' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(subcategory!=TRIM(subcategory)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('subcategory' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(subcategory))>100) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('reception_channel' AS column_name,'null' AS rule_id,COUNTIF(reception_channel IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('reception_channel' AS column_name,'blank' AS rule_id,COUNTIF(reception_channel IS NOT NULL AND TRIM(reception_channel) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('reception_channel' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(reception_channel!=TRIM(reception_channel)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('reception_channel' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(reception_channel))>30) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('affected_product_id' AS column_name,'null' AS rule_id,COUNTIF(affected_product_id IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('affected_product_id' AS column_name,'blank' AS rule_id,COUNTIF(affected_product_id IS NOT NULL AND TRIM(affected_product_id) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('affected_product_id' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(affected_product_id!=TRIM(affected_product_id)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('affected_product_id' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(affected_product_id))>20) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('related_branch_id' AS column_name,'null' AS rule_id,COUNTIF(related_branch_id IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('related_branch_id' AS column_name,'blank' AS rule_id,COUNTIF(related_branch_id IS NOT NULL AND TRIM(related_branch_id) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('related_branch_id' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(related_branch_id!=TRIM(related_branch_id)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('related_branch_id' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(related_branch_id))>20) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('origin_interaction_id' AS column_name,'null' AS rule_id,COUNTIF(origin_interaction_id IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('origin_interaction_id' AS column_name,'blank' AS rule_id,COUNTIF(origin_interaction_id IS NOT NULL AND TRIM(origin_interaction_id) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('origin_interaction_id' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(origin_interaction_id!=TRIM(origin_interaction_id)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('origin_interaction_id' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(origin_interaction_id))>30) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('description' AS column_name,'null' AS rule_id,COUNTIF(description IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('description' AS column_name,'blank' AS rule_id,COUNTIF(description IS NOT NULL AND TRIM(description) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('description' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(description!=TRIM(description)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('claimed_amount' AS column_name,'null' AS rule_id,COUNTIF(claimed_amount IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('claimed_amount' AS column_name,'blank' AS rule_id,COUNTIF(claimed_amount IS NOT NULL AND TRIM(claimed_amount) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('claimed_amount' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(claimed_amount!=TRIM(claimed_amount)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('currency' AS column_name,'null' AS rule_id,COUNTIF(currency IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('currency' AS column_name,'blank' AS rule_id,COUNTIF(currency IS NOT NULL AND TRIM(currency) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('currency' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(currency!=TRIM(currency)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('currency' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(currency))>3) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('priority' AS column_name,'null' AS rule_id,COUNTIF(priority IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('priority' AS column_name,'blank' AS rule_id,COUNTIF(priority IS NOT NULL AND TRIM(priority) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('priority' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(priority!=TRIM(priority)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('priority' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(priority))>20) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('status' AS column_name,'null' AS rule_id,COUNTIF(status IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('status' AS column_name,'blank' AS rule_id,COUNTIF(status IS NOT NULL AND TRIM(status) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('status' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(status!=TRIM(status)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('status' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(status))>30) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('assigned_agent_id' AS column_name,'null' AS rule_id,COUNTIF(assigned_agent_id IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('assigned_agent_id' AS column_name,'blank' AS rule_id,COUNTIF(assigned_agent_id IS NOT NULL AND TRIM(assigned_agent_id) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('assigned_agent_id' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(assigned_agent_id!=TRIM(assigned_agent_id)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('assigned_agent_id' AS column_name,'length_exceeded' AS rule_id,COUNTIF(CHAR_LENGTH(TRIM(assigned_agent_id))>20) AS affected_rows,'Dictionary length after trim' AS interpretation),
STRUCT('assignment_date' AS column_name,'null' AS rule_id,COUNTIF(assignment_date IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('assignment_date' AS column_name,'blank' AS rule_id,COUNTIF(assignment_date IS NOT NULL AND TRIM(assignment_date) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('assignment_date' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(assignment_date!=TRIM(assignment_date)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('first_response_date' AS column_name,'null' AS rule_id,COUNTIF(first_response_date IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('first_response_date' AS column_name,'blank' AS rule_id,COUNTIF(first_response_date IS NOT NULL AND TRIM(first_response_date) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('first_response_date' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(first_response_date!=TRIM(first_response_date)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('resolution_date' AS column_name,'null' AS rule_id,COUNTIF(resolution_date IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('resolution_date' AS column_name,'blank' AS rule_id,COUNTIF(resolution_date IS NOT NULL AND TRIM(resolution_date) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('resolution_date' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(resolution_date!=TRIM(resolution_date)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('closing_date' AS column_name,'null' AS rule_id,COUNTIF(closing_date IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('closing_date' AS column_name,'blank' AS rule_id,COUNTIF(closing_date IS NOT NULL AND TRIM(closing_date) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('closing_date' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(closing_date!=TRIM(closing_date)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('sla_breached' AS column_name,'null' AS rule_id,COUNTIF(sla_breached IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('sla_breached' AS column_name,'blank' AS rule_id,COUNTIF(sla_breached IS NOT NULL AND TRIM(sla_breached) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('sla_breached' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(sla_breached!=TRIM(sla_breached)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('resolution_days' AS column_name,'null' AS rule_id,COUNTIF(resolution_days IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('resolution_days' AS column_name,'blank' AS rule_id,COUNTIF(resolution_days IS NOT NULL AND TRIM(resolution_days) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('resolution_days' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(resolution_days!=TRIM(resolution_days)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('resolution' AS column_name,'null' AS rule_id,COUNTIF(resolution IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('resolution' AS column_name,'blank' AS rule_id,COUNTIF(resolution IS NOT NULL AND TRIM(resolution) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('resolution' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(resolution!=TRIM(resolution)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('compensation_granted' AS column_name,'null' AS rule_id,COUNTIF(compensation_granted IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('compensation_granted' AS column_name,'blank' AS rule_id,COUNTIF(compensation_granted IS NOT NULL AND TRIM(compensation_granted) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('compensation_granted' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(compensation_granted!=TRIM(compensation_granted)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('resolution_satisfaction' AS column_name,'null' AS rule_id,COUNTIF(resolution_satisfaction IS NULL) AS affected_rows,'Original null; required=false' AS interpretation),
STRUCT('resolution_satisfaction' AS column_name,'blank' AS rule_id,COUNTIF(resolution_satisfaction IS NOT NULL AND TRIM(resolution_satisfaction) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('resolution_satisfaction' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(resolution_satisfaction!=TRIM(resolution_satisfaction)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('is_repeat_complainer' AS column_name,'null' AS rule_id,COUNTIF(is_repeat_complainer IS NULL) AS affected_rows,'Original null; required=true' AS interpretation),
STRUCT('is_repeat_complainer' AS column_name,'blank' AS rule_id,COUNTIF(is_repeat_complainer IS NOT NULL AND TRIM(is_repeat_complainer) = '') AS affected_rows,'Blank; separate from null' AS interpretation),
STRUCT('is_repeat_complainer' AS column_name,'surrounding_whitespace' AS rule_id,COUNTIF(is_repeat_complainer!=TRIM(is_repeat_complainer)) AS affected_rows,'Observation; preserve original narrative in raw' AS interpretation),
STRUCT('creation_date' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(creation_date),'') IS NOT NULL AND SAFE_CAST(TRIM(creation_date) AS TIMESTAMP) IS NULL) AS affected_rows,'Blanks excluded from conversion failures' AS interpretation),
STRUCT('assignment_date' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(assignment_date),'') IS NOT NULL AND SAFE_CAST(TRIM(assignment_date) AS TIMESTAMP) IS NULL) AS affected_rows,'Blanks excluded from conversion failures' AS interpretation),
STRUCT('first_response_date' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(first_response_date),'') IS NOT NULL AND SAFE_CAST(TRIM(first_response_date) AS TIMESTAMP) IS NULL) AS affected_rows,'Blanks excluded from conversion failures' AS interpretation),
STRUCT('resolution_date' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(resolution_date),'') IS NOT NULL AND SAFE_CAST(TRIM(resolution_date) AS TIMESTAMP) IS NULL) AS affected_rows,'Blanks excluded from conversion failures' AS interpretation),
STRUCT('closing_date' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(closing_date),'') IS NOT NULL AND SAFE_CAST(TRIM(closing_date) AS TIMESTAMP) IS NULL) AS affected_rows,'Blanks excluded from conversion failures' AS interpretation),
STRUCT('process_date' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(process_date),'') IS NOT NULL AND SAFE_CAST(TRIM(process_date) AS DATE) IS NULL) AS affected_rows,'Blanks excluded from conversion failures' AS interpretation),
STRUCT('claimed_amount' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(claimed_amount),'') IS NOT NULL AND SAFE_CAST(TRIM(claimed_amount) AS BIGNUMERIC) IS NULL) AS affected_rows,'Blanks excluded from conversion failures' AS interpretation),
STRUCT('compensation_granted' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(compensation_granted),'') IS NOT NULL AND SAFE_CAST(TRIM(compensation_granted) AS BIGNUMERIC) IS NULL) AS affected_rows,'Blanks excluded from conversion failures' AS interpretation),
STRUCT('resolution_days' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(resolution_days),'') IS NOT NULL AND SAFE_CAST(TRIM(resolution_days) AS BIGNUMERIC) IS NULL) AS affected_rows,'Blanks excluded from conversion failures' AS interpretation),
STRUCT('resolution_satisfaction' AS column_name,'conversion_failed' AS rule_id,COUNTIF(NULLIF(TRIM(resolution_satisfaction),'') IS NOT NULL AND SAFE_CAST(TRIM(resolution_satisfaction) AS BIGNUMERIC) IS NULL) AS affected_rows,'Blanks excluded from conversion failures' AS interpretation),
STRUCT('claimed_amount' AS column_name,'decimal_overflow' AS rule_id,COUNTIF(ABS(SAFE_CAST(TRIM(claimed_amount) AS BIGNUMERIC))>=10000000000000) AS affected_rows,'DECIMAL(15,2) magnitude' AS interpretation),
STRUCT('claimed_amount' AS column_name,'excess_scale' AS rule_id,COUNTIF(SAFE_CAST(TRIM(claimed_amount) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(claimed_amount) AS BIGNUMERIC),2)) AS affected_rows,'No silent rounding' AS interpretation),
STRUCT('claimed_amount' AS column_name,'negative_value' AS rule_id,COUNTIF(SAFE_CAST(TRIM(claimed_amount) AS BIGNUMERIC)<0) AS affected_rows,'Observation; business policy pending' AS interpretation),
STRUCT('compensation_granted' AS column_name,'decimal_overflow' AS rule_id,COUNTIF(ABS(SAFE_CAST(TRIM(compensation_granted) AS BIGNUMERIC))>=10000000000000) AS affected_rows,'DECIMAL(15,2) magnitude' AS interpretation),
STRUCT('compensation_granted' AS column_name,'excess_scale' AS rule_id,COUNTIF(SAFE_CAST(TRIM(compensation_granted) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(compensation_granted) AS BIGNUMERIC),2)) AS affected_rows,'No silent rounding' AS interpretation),
STRUCT('compensation_granted' AS column_name,'negative_value' AS rule_id,COUNTIF(SAFE_CAST(TRIM(compensation_granted) AS BIGNUMERIC)<0) AS affected_rows,'Observation; business policy pending' AS interpretation),
STRUCT('resolution_days' AS column_name,'fractional_value' AS rule_id,COUNTIF(SAFE_CAST(TRIM(resolution_days) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(resolution_days) AS BIGNUMERIC))) AS affected_rows,'Must be integral' AS interpretation),
STRUCT('resolution_days' AS column_name,'int64_overflow' AS rule_id,COUNTIF(SAFE_CAST(TRIM(resolution_days) AS BIGNUMERIC) < -9223372036854775808 OR SAFE_CAST(TRIM(resolution_days) AS BIGNUMERIC)>9223372036854775807) AS affected_rows,'INT64 bounds' AS interpretation),
STRUCT('resolution_satisfaction' AS column_name,'fractional_value' AS rule_id,COUNTIF(SAFE_CAST(TRIM(resolution_satisfaction) AS BIGNUMERIC)!=TRUNC(SAFE_CAST(TRIM(resolution_satisfaction) AS BIGNUMERIC))) AS affected_rows,'Must be integral' AS interpretation),
STRUCT('resolution_satisfaction' AS column_name,'int64_overflow' AS rule_id,COUNTIF(SAFE_CAST(TRIM(resolution_satisfaction) AS BIGNUMERIC) < -9223372036854775808 OR SAFE_CAST(TRIM(resolution_satisfaction) AS BIGNUMERIC)>9223372036854775807) AS affected_rows,'INT64 bounds' AS interpretation),
STRUCT('resolution_satisfaction' AS column_name,'outside_1_5' AS rule_id,COUNTIF(SAFE_CAST(TRIM(resolution_satisfaction) AS BIGNUMERIC)<1 OR SAFE_CAST(TRIM(resolution_satisfaction) AS BIGNUMERIC)>5) AS affected_rows,'Dictionary range' AS interpretation),
STRUCT('resolution_days' AS column_name,'negative_value' AS rule_id,COUNTIF(SAFE_CAST(TRIM(resolution_days) AS BIGNUMERIC)<0) AS affected_rows,'Observation; duration semantics pending' AS interpretation),
STRUCT('sla_breached' AS column_name,'unknown_boolean' AS rule_id,COUNTIF(NULLIF(TRIM(sla_breached),'') IS NOT NULL AND LOWER(TRIM(sla_breached)) NOT IN ('true','false','1','0','t','f','yes','no','y','n')) AS affected_rows,'Candidate boolean spellings' AS interpretation),
STRUCT('is_repeat_complainer' AS column_name,'unknown_boolean' AS rule_id,COUNTIF(NULLIF(TRIM(is_repeat_complainer),'') IS NOT NULL AND LOWER(TRIM(is_repeat_complainer)) NOT IN ('true','false','1','0','t','f','yes','no','y','n')) AS affected_rows,'Candidate boolean spellings' AS interpretation),
STRUCT('case_type' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(case_type),'') IS NOT NULL AND TRIM(case_type) NOT IN ('Complaint','Claim','Request','Suggestion')) AS affected_rows,'Inspect translations before enforcing' AS interpretation),
STRUCT('reception_channel' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(reception_channel),'') IS NOT NULL AND TRIM(reception_channel) NOT IN ('Call Center','Email','Web','App','Branch','Regulator')) AS affected_rows,'Inspect translations before enforcing' AS interpretation),
STRUCT('priority' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(priority),'') IS NOT NULL AND TRIM(priority) NOT IN ('Low','Medium','High','Critical')) AS affected_rows,'Inspect translations before enforcing' AS interpretation),
STRUCT('status' AS column_name,'outside_dictionary_domain' AS rule_id,COUNTIF(NULLIF(TRIM(status),'') IS NOT NULL AND TRIM(status) NOT IN ('Open','In Process','Escalated','Resolved','Closed','Rejected')) AS affected_rows,'Inspect translations before enforcing' AS interpretation),
STRUCT('assignment_date' AS column_name,'before_creation' AS rule_id,COUNTIF(SAFE_CAST(TRIM(assignment_date) AS TIMESTAMP)<SAFE_CAST(TRIM(creation_date) AS TIMESTAMP)) AS affected_rows,'Observation; timezone and business semantics unconfirmed' AS interpretation),
STRUCT('first_response_date' AS column_name,'before_creation' AS rule_id,COUNTIF(SAFE_CAST(TRIM(first_response_date) AS TIMESTAMP)<SAFE_CAST(TRIM(creation_date) AS TIMESTAMP)) AS affected_rows,'Observation; timezone and business semantics unconfirmed' AS interpretation),
STRUCT('resolution_date' AS column_name,'before_creation' AS rule_id,COUNTIF(SAFE_CAST(TRIM(resolution_date) AS TIMESTAMP)<SAFE_CAST(TRIM(creation_date) AS TIMESTAMP)) AS affected_rows,'Observation; timezone and business semantics unconfirmed' AS interpretation),
STRUCT('closing_date' AS column_name,'before_creation' AS rule_id,COUNTIF(SAFE_CAST(TRIM(closing_date) AS TIMESTAMP)<SAFE_CAST(TRIM(creation_date) AS TIMESTAMP)) AS affected_rows,'Observation; timezone and business semantics unconfirmed' AS interpretation),
STRUCT('process_date' AS column_name,'before_creation_date' AS rule_id,COUNTIF(SAFE_CAST(TRIM(process_date) AS DATE)<DATE(SAFE_CAST(TRIM(creation_date) AS TIMESTAMP))) AS affected_rows,'Observation; timezone difference is a hypothesis; no correction' AS interpretation),
STRUCT('closing_date' AS column_name,'before_resolution' AS rule_id,COUNTIF(SAFE_CAST(TRIM(closing_date) AS TIMESTAMP)<SAFE_CAST(TRIM(resolution_date) AS TIMESTAMP)) AS affected_rows,'Chronology observation' AS interpretation),
STRUCT('resolution_days' AS column_name,'differs_from_calendar_days' AS rule_id,COUNTIF(SAFE_CAST(TRIM(resolution_days) AS BIGNUMERIC)!=DATE_DIFF(DATE(SAFE_CAST(TRIM(resolution_date) AS TIMESTAMP)),DATE(SAFE_CAST(TRIM(creation_date) AS TIMESTAMP)),DAY)) AS affected_rows,'Observation; calendar days may differ from SLA business days' AS interpretation),
STRUCT('currency' AS column_name,'missing_with_amount' AS rule_id,COUNTIF((NULLIF(TRIM(claimed_amount),'') IS NOT NULL OR NULLIF(TRIM(compensation_granted),'') IS NOT NULL) AND NULLIF(TRIM(currency),'') IS NULL) AS affected_rows,'Observation; currency dependency not yet approved' AS interpretation)
] AS metrics FROM profile_input),UNNEST(metrics) AS metric;

INSERT INTO measurements
SELECT 'complaint_id','duplicate_key_excess_after_trim',COALESCE(SUM(n-1),0),'Excess rows; no arbitrary winner'
FROM (SELECT TRIM(complaint_id) AS normalized_id,COUNT(*) AS n FROM profile_input
WHERE NULLIF(TRIM(complaint_id),'') IS NOT NULL GROUP BY normalized_id HAVING COUNT(*)>1);
INSERT INTO measurements
SELECT '*','exact_duplicate_excess',COALESCE(SUM(n-1),0),'Identical business rows beyond first'
FROM (SELECT TO_JSON_STRING(STRUCT(complaint_id,creation_date,process_date,customer_id,case_type,category,subcategory,reception_channel,affected_product_id,related_branch_id,origin_interaction_id,description,claimed_amount,currency,priority,status,assigned_agent_id,assignment_date,first_response_date,resolution_date,closing_date,sla_breached,resolution_days,resolution,compensation_granted,resolution_satisfaction,is_repeat_complainer)) AS row_content,COUNT(*) AS n
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
  SELECT 'affected_product_id','missing_curated_product',COUNT(*),'Includes products found in quarantine; metrics overlap'
  FROM profile_input AS t
  WHERE NULLIF(TRIM(t.affected_product_id),'') IS NOT NULL
    AND NOT EXISTS(SELECT 1 FROM reference_products p WHERE p.product_id=TRIM(t.affected_product_id));

  INSERT INTO measurements
  SELECT 'affected_product_id','missing_product_found_in_quarantine',COUNT(*),'Subset of missing curated products; current published run only'
  FROM profile_input AS t
  WHERE NULLIF(TRIM(t.affected_product_id),'') IS NOT NULL
    AND NOT EXISTS(SELECT 1 FROM reference_products p WHERE p.product_id=TRIM(t.affected_product_id))
    AND EXISTS(SELECT 1 FROM quarantined_products q WHERE q.product_id=TRIM(t.affected_product_id));

  INSERT INTO measurements
  SELECT 'affected_product_id','missing_product_not_in_quarantine',COUNT(*),'Absent from curated and retained quarantine for current run'
  FROM profile_input AS t
  WHERE NULLIF(TRIM(t.affected_product_id),'') IS NOT NULL
    AND NOT EXISTS(SELECT 1 FROM reference_products p WHERE p.product_id=TRIM(t.affected_product_id))
    AND NOT EXISTS(SELECT 1 FROM quarantined_products q WHERE q.product_id=TRIM(t.affected_product_id));

  INSERT INTO measurements
  SELECT 'customer_id','product_owner_mismatch',COUNT(*),'Nonblank customer differs from published product owner'
  FROM profile_input t JOIN reference_products p ON p.product_id=TRIM(t.affected_product_id)
  WHERE NULLIF(TRIM(t.customer_id),'') IS NOT NULL AND TRIM(t.customer_id)!=p.customer_id;

  INSERT INTO measurements
  SELECT 'currency','differs_from_product_currency',COUNT(*),'Observation only; claim currency may differ'
  FROM profile_input t JOIN reference_products p ON p.product_id=TRIM(t.affected_product_id)
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
  SELECT v_run_id,v_started,'hackaton-509923.bank_raw.complaints',d.column_name,d.value,COUNT(*)
  FROM profile_input,UNNEST([
STRUCT('case_type' AS column_name,TRIM(case_type) AS value),
STRUCT('category' AS column_name,TRIM(category) AS value),
STRUCT('subcategory' AS column_name,TRIM(subcategory) AS value),
STRUCT('reception_channel' AS column_name,TRIM(reception_channel) AS value),
STRUCT('currency' AS column_name,TRIM(currency) AS value),
STRUCT('priority' AS column_name,TRIM(priority) AS value),
STRUCT('status' AS column_name,TRIM(status) AS value),
STRUCT('sla_breached' AS column_name,TRIM(sla_breached) AS value),
STRUCT('is_repeat_complainer' AS column_name,TRIM(is_repeat_complainer) AS value)
  ]) d GROUP BY d.column_name,d.value;

  INSERT INTO `hackaton-509923.bank_ops.profile_results`
  SELECT v_run_id, v_started, 'hackaton-509923.bank_raw.complaints',
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
      '; branch, agent and interaction FK, currency dictionary, timezone and SLA definitions pending; observations are not publication rules')
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
