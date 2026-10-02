-- customers profiling v1.0.0. Run the whole script in us-central1.
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
VALUES(v_run_id, '1.0.0', 'hackaton-509923.bank_raw.customers',
  v_snapshot, v_started, NULL, 'RUNNING', NULL, NULL);

BEGIN
  -- Single stable input shared by all metrics, even if raw is replaced later.
  CREATE TEMP TABLE profile_input AS
  SELECT * FROM `hackaton-509923.bank_raw.customers`
  FOR SYSTEM_TIME AS OF v_snapshot;

  SET v_rows = (SELECT COUNT(*) FROM profile_input);
  ASSERT v_rows > 0 AS 'Profiling input has no records';

  CREATE TEMP TABLE measurements AS
  SELECT metric.* FROM (
    SELECT [
    STRUCT('customer_id' AS column_name, 'null' AS rule_id,
      COUNTIF(customer_id IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('customer_id' AS column_name, 'blank' AS rule_id,
      COUNTIF(customer_id IS NOT NULL AND TRIM(customer_id) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('customer_id' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(customer_id != TRIM(customer_id)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('customer_id' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(customer_id)) > 20) AS affected_rows, 'Dictionary maximum 20 characters after trim' AS interpretation),
    STRUCT('document_number' AS column_name, 'null' AS rule_id,
      COUNTIF(document_number IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('document_number' AS column_name, 'blank' AS rule_id,
      COUNTIF(document_number IS NOT NULL AND TRIM(document_number) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('document_number' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(document_number != TRIM(document_number)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('document_number' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(document_number)) > 20) AS affected_rows, 'Dictionary maximum 20 characters after trim' AS interpretation),
    STRUCT('document_type' AS column_name, 'null' AS rule_id,
      COUNTIF(document_type IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('document_type' AS column_name, 'blank' AS rule_id,
      COUNTIF(document_type IS NOT NULL AND TRIM(document_type) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('document_type' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(document_type != TRIM(document_type)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('document_type' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(document_type)) > 10) AS affected_rows, 'Dictionary maximum 10 characters after trim' AS interpretation),
    STRUCT('first_name' AS column_name, 'null' AS rule_id,
      COUNTIF(first_name IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('first_name' AS column_name, 'blank' AS rule_id,
      COUNTIF(first_name IS NOT NULL AND TRIM(first_name) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('first_name' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(first_name != TRIM(first_name)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('first_name' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(first_name)) > 100) AS affected_rows, 'Dictionary maximum 100 characters after trim' AS interpretation),
    STRUCT('last_name' AS column_name, 'null' AS rule_id,
      COUNTIF(last_name IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('last_name' AS column_name, 'blank' AS rule_id,
      COUNTIF(last_name IS NOT NULL AND TRIM(last_name) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('last_name' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(last_name != TRIM(last_name)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('last_name' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(last_name)) > 100) AS affected_rows, 'Dictionary maximum 100 characters after trim' AS interpretation),
    STRUCT('date_of_birth' AS column_name, 'null' AS rule_id,
      COUNTIF(date_of_birth IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('date_of_birth' AS column_name, 'blank' AS rule_id,
      COUNTIF(date_of_birth IS NOT NULL AND TRIM(date_of_birth) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('date_of_birth' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(date_of_birth != TRIM(date_of_birth)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('gender' AS column_name, 'null' AS rule_id,
      COUNTIF(gender IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('gender' AS column_name, 'blank' AS rule_id,
      COUNTIF(gender IS NOT NULL AND TRIM(gender) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('gender' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(gender != TRIM(gender)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('gender' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(gender)) > 1) AS affected_rows, 'Dictionary maximum 1 characters after trim' AS interpretation),
    STRUCT('email' AS column_name, 'null' AS rule_id,
      COUNTIF(email IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('email' AS column_name, 'blank' AS rule_id,
      COUNTIF(email IS NOT NULL AND TRIM(email) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('email' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(email != TRIM(email)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('email' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(email)) > 100) AS affected_rows, 'Dictionary maximum 100 characters after trim' AS interpretation),
    STRUCT('mobile_phone' AS column_name, 'null' AS rule_id,
      COUNTIF(mobile_phone IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('mobile_phone' AS column_name, 'blank' AS rule_id,
      COUNTIF(mobile_phone IS NOT NULL AND TRIM(mobile_phone) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('mobile_phone' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(mobile_phone != TRIM(mobile_phone)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('mobile_phone' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(mobile_phone)) > 20) AS affected_rows, 'Dictionary maximum 20 characters after trim' AS interpretation),
    STRUCT('landline_phone' AS column_name, 'null' AS rule_id,
      COUNTIF(landline_phone IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('landline_phone' AS column_name, 'blank' AS rule_id,
      COUNTIF(landline_phone IS NOT NULL AND TRIM(landline_phone) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('landline_phone' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(landline_phone != TRIM(landline_phone)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('landline_phone' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(landline_phone)) > 20) AS affected_rows, 'Dictionary maximum 20 characters after trim' AS interpretation),
    STRUCT('address' AS column_name, 'null' AS rule_id,
      COUNTIF(address IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('address' AS column_name, 'blank' AS rule_id,
      COUNTIF(address IS NOT NULL AND TRIM(address) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('address' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(address != TRIM(address)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('address' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(address)) > 200) AS affected_rows, 'Dictionary maximum 200 characters after trim' AS interpretation),
    STRUCT('city' AS column_name, 'null' AS rule_id,
      COUNTIF(city IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('city' AS column_name, 'blank' AS rule_id,
      COUNTIF(city IS NOT NULL AND TRIM(city) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('city' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(city != TRIM(city)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('city' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(city)) > 100) AS affected_rows, 'Dictionary maximum 100 characters after trim' AS interpretation),
    STRUCT('state' AS column_name, 'null' AS rule_id,
      COUNTIF(state IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('state' AS column_name, 'blank' AS rule_id,
      COUNTIF(state IS NOT NULL AND TRIM(state) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('state' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(state != TRIM(state)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('state' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(state)) > 100) AS affected_rows, 'Dictionary maximum 100 characters after trim' AS interpretation),
    STRUCT('country' AS column_name, 'null' AS rule_id,
      COUNTIF(country IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('country' AS column_name, 'blank' AS rule_id,
      COUNTIF(country IS NOT NULL AND TRIM(country) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('country' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(country != TRIM(country)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('country' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(country)) > 50) AS affected_rows, 'Dictionary maximum 50 characters after trim' AS interpretation),
    STRUCT('postal_code' AS column_name, 'null' AS rule_id,
      COUNTIF(postal_code IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('postal_code' AS column_name, 'blank' AS rule_id,
      COUNTIF(postal_code IS NOT NULL AND TRIM(postal_code) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('postal_code' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(postal_code != TRIM(postal_code)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('postal_code' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(postal_code)) > 10) AS affected_rows, 'Dictionary maximum 10 characters after trim' AS interpretation),
    STRUCT('detected_accent' AS column_name, 'null' AS rule_id,
      COUNTIF(detected_accent IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('detected_accent' AS column_name, 'blank' AS rule_id,
      COUNTIF(detected_accent IS NOT NULL AND TRIM(detected_accent) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('detected_accent' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(detected_accent != TRIM(detected_accent)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('detected_accent' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(detected_accent)) > 50) AS affected_rows, 'Dictionary maximum 50 characters after trim' AS interpretation),
    STRUCT('segment' AS column_name, 'null' AS rule_id,
      COUNTIF(segment IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('segment' AS column_name, 'blank' AS rule_id,
      COUNTIF(segment IS NOT NULL AND TRIM(segment) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('segment' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(segment != TRIM(segment)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('segment' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(segment)) > 50) AS affected_rows, 'Dictionary maximum 50 characters after trim' AS interpretation),
    STRUCT('credit_score' AS column_name, 'null' AS rule_id,
      COUNTIF(credit_score IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('credit_score' AS column_name, 'blank' AS rule_id,
      COUNTIF(credit_score IS NOT NULL AND TRIM(credit_score) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('credit_score' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(credit_score != TRIM(credit_score)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('estimated_monthly_income' AS column_name, 'null' AS rule_id,
      COUNTIF(estimated_monthly_income IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('estimated_monthly_income' AS column_name, 'blank' AS rule_id,
      COUNTIF(estimated_monthly_income IS NOT NULL AND TRIM(estimated_monthly_income) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('estimated_monthly_income' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(estimated_monthly_income != TRIM(estimated_monthly_income)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('occupation' AS column_name, 'null' AS rule_id,
      COUNTIF(occupation IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('occupation' AS column_name, 'blank' AS rule_id,
      COUNTIF(occupation IS NOT NULL AND TRIM(occupation) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('occupation' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(occupation != TRIM(occupation)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('occupation' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(occupation)) > 100) AS affected_rows, 'Dictionary maximum 100 characters after trim' AS interpretation),
    STRUCT('marital_status' AS column_name, 'null' AS rule_id,
      COUNTIF(marital_status IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('marital_status' AS column_name, 'blank' AS rule_id,
      COUNTIF(marital_status IS NOT NULL AND TRIM(marital_status) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('marital_status' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(marital_status != TRIM(marital_status)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('marital_status' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(marital_status)) > 20) AS affected_rows, 'Dictionary maximum 20 characters after trim' AS interpretation),
    STRUCT('education_level' AS column_name, 'null' AS rule_id,
      COUNTIF(education_level IS NULL) AS affected_rows, 'Original null; required=false' AS interpretation),
    STRUCT('education_level' AS column_name, 'blank' AS rule_id,
      COUNTIF(education_level IS NOT NULL AND TRIM(education_level) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('education_level' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(education_level != TRIM(education_level)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('education_level' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(education_level)) > 50) AS affected_rows, 'Dictionary maximum 50 characters after trim' AS interpretation),
    STRUCT('registration_date' AS column_name, 'null' AS rule_id,
      COUNTIF(registration_date IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('registration_date' AS column_name, 'blank' AS rule_id,
      COUNTIF(registration_date IS NOT NULL AND TRIM(registration_date) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('registration_date' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(registration_date != TRIM(registration_date)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('registration_branch_id' AS column_name, 'null' AS rule_id,
      COUNTIF(registration_branch_id IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('registration_branch_id' AS column_name, 'blank' AS rule_id,
      COUNTIF(registration_branch_id IS NOT NULL AND TRIM(registration_branch_id) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('registration_branch_id' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(registration_branch_id != TRIM(registration_branch_id)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('registration_branch_id' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(registration_branch_id)) > 20) AS affected_rows, 'Dictionary maximum 20 characters after trim' AS interpretation),
    STRUCT('customer_status' AS column_name, 'null' AS rule_id,
      COUNTIF(customer_status IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('customer_status' AS column_name, 'blank' AS rule_id,
      COUNTIF(customer_status IS NOT NULL AND TRIM(customer_status) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('customer_status' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(customer_status != TRIM(customer_status)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('customer_status' AS column_name, 'length_exceeded' AS rule_id,
      COUNTIF(CHAR_LENGTH(TRIM(customer_status)) > 20) AS affected_rows, 'Dictionary maximum 20 characters after trim' AS interpretation),
    STRUCT('last_updated' AS column_name, 'null' AS rule_id,
      COUNTIF(last_updated IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('last_updated' AS column_name, 'blank' AS rule_id,
      COUNTIF(last_updated IS NOT NULL AND TRIM(last_updated) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('last_updated' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(last_updated != TRIM(last_updated)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('accepts_marketing' AS column_name, 'null' AS rule_id,
      COUNTIF(accepts_marketing IS NULL) AS affected_rows, 'Original null; required=true' AS interpretation),
    STRUCT('accepts_marketing' AS column_name, 'blank' AS rule_id,
      COUNTIF(accepts_marketing IS NOT NULL AND TRIM(accepts_marketing) = '') AS affected_rows, 'Empty or whitespace; separate from original null' AS interpretation),
    STRUCT('accepts_marketing' AS column_name, 'surrounding_whitespace' AS rule_id,
      COUNTIF(accepts_marketing != TRIM(accepts_marketing)) AS affected_rows, 'Candidate for normalization; not automatically rejected' AS interpretation),
    STRUCT('date_of_birth' AS column_name, 'conversion_failed' AS rule_id,
      COUNTIF(NULLIF(TRIM(date_of_birth), '') IS NOT NULL AND SAFE_CAST(TRIM(date_of_birth) AS DATE) IS NULL) AS affected_rows, 'Default DATE parser; blanks excluded' AS interpretation),
    STRUCT('registration_date' AS column_name, 'conversion_failed' AS rule_id,
      COUNTIF(NULLIF(TRIM(registration_date), '') IS NOT NULL AND SAFE_CAST(TRIM(registration_date) AS TIMESTAMP) IS NULL) AS affected_rows, 'Default TIMESTAMP parser; blanks excluded' AS interpretation),
    STRUCT('last_updated' AS column_name, 'conversion_failed' AS rule_id,
      COUNTIF(NULLIF(TRIM(last_updated), '') IS NOT NULL AND SAFE_CAST(TRIM(last_updated) AS TIMESTAMP) IS NULL) AS affected_rows, 'Default TIMESTAMP parser; blanks excluded' AS interpretation),
    STRUCT('credit_score' AS column_name, 'conversion_failed' AS rule_id,
      COUNTIF(NULLIF(TRIM(credit_score), '') IS NOT NULL AND SAFE_CAST(TRIM(credit_score) AS BIGNUMERIC) IS NULL) AS affected_rows, 'Default BIGNUMERIC parser; blanks excluded' AS interpretation),
    STRUCT('estimated_monthly_income' AS column_name, 'conversion_failed' AS rule_id,
      COUNTIF(NULLIF(TRIM(estimated_monthly_income), '') IS NOT NULL AND SAFE_CAST(TRIM(estimated_monthly_income) AS BIGNUMERIC) IS NULL) AS affected_rows, 'Default BIGNUMERIC parser; blanks excluded' AS interpretation),
    STRUCT('gender' AS column_name, 'outside_dictionary_domain' AS rule_id,
      COUNTIF(NULLIF(TRIM(gender), '') IS NOT NULL AND TRIM(gender) NOT IN ('M', 'F', 'O')) AS affected_rows, 'Case-sensitive comparison after trim; profile before deciding normalization' AS interpretation),
    STRUCT('document_type' AS column_name, 'outside_dictionary_domain' AS rule_id,
      COUNTIF(NULLIF(TRIM(document_type), '') IS NOT NULL AND TRIM(document_type) NOT IN ('DNI', 'CURP', 'CC', 'CE', 'Passport')) AS affected_rows, 'Case-sensitive comparison after trim; profile before deciding normalization' AS interpretation),
    STRUCT('country' AS column_name, 'outside_dictionary_domain' AS rule_id,
      COUNTIF(NULLIF(TRIM(country), '') IS NOT NULL AND TRIM(country) NOT IN ('Mexico', 'Colombia', 'Argentina')) AS affected_rows, 'Case-sensitive comparison after trim; profile before deciding normalization' AS interpretation),
    STRUCT('segment' AS column_name, 'outside_dictionary_domain' AS rule_id,
      COUNTIF(NULLIF(TRIM(segment), '') IS NOT NULL AND TRIM(segment) NOT IN ('Premium', 'Plus', 'Basic', 'Student')) AS affected_rows, 'Case-sensitive comparison after trim; profile before deciding normalization' AS interpretation),
    STRUCT('detected_accent' AS column_name, 'outside_dictionary_domain' AS rule_id,
      COUNTIF(NULLIF(TRIM(detected_accent), '') IS NOT NULL AND TRIM(detected_accent) NOT IN ('mexican', 'colombian', 'argentine', 'neutral')) AS affected_rows, 'Case-sensitive comparison after trim; profile before deciding normalization' AS interpretation),
    STRUCT('customer_status' AS column_name, 'outside_dictionary_domain' AS rule_id,
      COUNTIF(NULLIF(TRIM(customer_status), '') IS NOT NULL AND TRIM(customer_status) NOT IN ('Active', 'Inactive', 'Suspended', 'Closed')) AS affected_rows, 'Case-sensitive comparison after trim; profile before deciding normalization' AS interpretation),
    STRUCT('accepts_marketing' AS column_name, 'unknown_boolean' AS rule_id,
      COUNTIF(NULLIF(TRIM(accepts_marketing), '') IS NOT NULL AND LOWER(TRIM(accepts_marketing)) NOT IN ('true','false','1','0','t','f','yes','no','y','n')) AS affected_rows, 'Candidate accepted spellings; conversion policy not yet published' AS interpretation),
    STRUCT('credit_score' AS column_name, 'fractional_value' AS rule_id,
      COUNTIF(SAFE_CAST(TRIM(credit_score) AS BIGNUMERIC) != TRUNC(SAFE_CAST(TRIM(credit_score) AS BIGNUMERIC))) AS affected_rows, 'Must not round to integer silently' AS interpretation),
    STRUCT('credit_score' AS column_name, 'outside_300_850' AS rule_id,
      COUNTIF(SAFE_CAST(TRIM(credit_score) AS BIGNUMERIC) < 300 OR SAFE_CAST(TRIM(credit_score) AS BIGNUMERIC) > 850) AS affected_rows, 'Numeric range check; conversion failures counted separately' AS interpretation),
    STRUCT('estimated_monthly_income' AS column_name, 'decimal_12_2_overflow' AS rule_id,
      COUNTIF(ABS(SAFE_CAST(TRIM(estimated_monthly_income) AS BIGNUMERIC)) >= 10000000000) AS affected_rows, 'DECIMAL(12,2) allows ten integer digits' AS interpretation),
    STRUCT('estimated_monthly_income' AS column_name, 'more_than_2_decimals' AS rule_id,
      COUNTIF(SAFE_CAST(TRIM(estimated_monthly_income) AS BIGNUMERIC) != TRUNC(SAFE_CAST(TRIM(estimated_monthly_income) AS BIGNUMERIC), 2)) AS affected_rows, 'Do not round without an explicit policy' AS interpretation),
    STRUCT('estimated_monthly_income' AS column_name, 'negative_value' AS rule_id,
      COUNTIF(SAFE_CAST(TRIM(estimated_monthly_income) AS BIGNUMERIC) < 0) AS affected_rows, 'Observation only; no rejection rule agreed' AS interpretation),
    STRUCT('date_of_birth' AS column_name, 'after_registration' AS rule_id,
      COUNTIF(SAFE_CAST(TRIM(date_of_birth) AS DATE) > DATE(SAFE_CAST(TRIM(registration_date) AS TIMESTAMP))) AS affected_rows, 'Uses UTC interpretation where timezone is absent; confirm source semantics' AS interpretation),
    STRUCT('last_updated' AS column_name, 'before_registration' AS rule_id,
      COUNTIF(SAFE_CAST(TRIM(last_updated) AS TIMESTAMP) < SAFE_CAST(TRIM(registration_date) AS TIMESTAMP)) AS affected_rows, 'Chronology observation; no automatic correction' AS interpretation)
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
  SELECT 'customer_id', 'duplicate_key_excess_after_trim', COALESCE(SUM(n - 1), 0),
    'Additional rows per nonblank trimmed key; overlaps with exact duplicates'
  FROM (
    SELECT TRIM(customer_id) AS key_value, COUNT(*) AS n
    FROM profile_input WHERE NULLIF(TRIM(customer_id), '') IS NOT NULL
    GROUP BY key_value HAVING COUNT(*) > 1
  );

  INSERT INTO measurements
  SELECT 'document_number', 'duplicate_key_excess_after_trim', COALESCE(SUM(n - 1), 0),
    'Additional rows per nonblank trimmed key; overlaps with exact duplicates'
  FROM (
    SELECT TRIM(document_number) AS key_value, COUNT(*) AS n
    FROM profile_input WHERE NULLIF(TRIM(document_number), '') IS NOT NULL
    GROUP BY key_value HAVING COUNT(*) > 1
  );

  -- Count distinct customer IDs with conflicting content at the latest
  -- parseable update timestamp. IDs without valid timestamps need separate review.
  INSERT INTO measurements
  WITH versioned AS (
    SELECT TRIM(customer_id) AS key_value,
      SAFE_CAST(TRIM(last_updated) AS TIMESTAMP) AS update_time,
      TO_JSON_STRING(r) AS row_content
    FROM profile_input AS r
    WHERE NULLIF(TRIM(customer_id), '') IS NOT NULL
  ), latest AS (
    SELECT * FROM versioned
    WHERE update_time IS NOT NULL
    QUALIFY update_time = MAX(update_time) OVER (PARTITION BY key_value)
  ), conflicts AS (
    SELECT key_value FROM latest GROUP BY key_value
    HAVING COUNT(DISTINCT row_content) > 1
  )
  SELECT 'customer_id', 'latest_version_conflicting_keys', COUNT(*),
    'Counts keys, not rows; raw-content differences at latest valid timestamp'
  FROM conflicts;

  -- Persist metrics and terminal success together; failed runs have no
  -- partially persisted metric set.
  BEGIN TRANSACTION;
  SET v_transaction_open = TRUE;
  INSERT INTO `hackaton-509923.bank_ops.profile_results`
  SELECT v_run_id, v_started, 'hackaton-509923.bank_raw.customers',
    column_name, rule_id, affected_rows, v_rows,
    IF(rule_id = 'latest_version_conflicting_keys', NULL,
       ROUND(100.0 * SAFE_DIVIDE(affected_rows, v_rows), 4)),
    interpretation
  FROM measurements;

  UPDATE `hackaton-509923.bank_ops.profile_runs`
  SET status = 'SUCCEEDED', finished_at = CURRENT_TIMESTAMP(), input_rows = v_rows
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
