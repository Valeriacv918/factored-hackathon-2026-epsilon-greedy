-- Read-only diagnostic tied to the successful profile snapshot.
DECLARE snapshot_at TIMESTAMP DEFAULT (
 SELECT source_snapshot_at FROM `hackaton-509923.bank_ops.profile_runs`
 WHERE run_id='a9d28bf3-fc55-49bd-80ac-7a8827bb41c5'
);
ASSERT snapshot_at IS NOT NULL AS 'Profile snapshot not found';
CREATE TEMP TABLE agents AS
SELECT agent_id,employee_code,assigned_branch_id
FROM `hackaton-509923.bank_raw.service_agents` FOR SYSTEM_TIME AS OF snapshot_at;
CREATE TEMP TABLE branches AS
SELECT branch_id,branch_code FROM `hackaton-509923.bank_curated.branches`
FOR SYSTEM_TIME AS OF snapshot_at;
CREATE TEMP TABLE raw_branches AS
SELECT branch_id FROM `hackaton-509923.bank_raw.branches`
FOR SYSTEM_TIME AS OF snapshot_at;

-- Hypotheses only: never remap an ID automatically to a code or similar ID.
SELECT COUNT(*) AS total_agents,
 COUNTIF(NULLIF(TRIM(a.assigned_branch_id),'') IS NULL) AS no_branch,
 COUNTIF(NULLIF(TRIM(a.assigned_branch_id),'') IS NOT NULL AND NOT EXISTS(
   SELECT 1 FROM branches b WHERE b.branch_id=TRIM(a.assigned_branch_id))) AS missing_curated,
 COUNTIF(NULLIF(TRIM(a.assigned_branch_id),'') IS NOT NULL AND NOT EXISTS(
   SELECT 1 FROM raw_branches b WHERE TRIM(b.branch_id)=TRIM(a.assigned_branch_id))) AS missing_raw,
 COUNTIF(NULLIF(TRIM(a.assigned_branch_id),'') IS NOT NULL AND NOT EXISTS(
   SELECT 1 FROM branches b WHERE b.branch_id=TRIM(a.assigned_branch_id)) AND EXISTS(
   SELECT 1 FROM branches b WHERE UPPER(b.branch_id)=UPPER(TRIM(a.assigned_branch_id)))) AS missing_but_matches_ignoring_case,
 COUNTIF(NULLIF(TRIM(a.assigned_branch_id),'') IS NOT NULL AND NOT EXISTS(
   SELECT 1 FROM branches b WHERE b.branch_id=TRIM(a.assigned_branch_id)) AND EXISTS(
   SELECT 1 FROM branches b WHERE b.branch_code=TRIM(a.assigned_branch_id))) AS missing_but_matches_branch_code
FROM agents a;

SELECT TRIM(a.assigned_branch_id) AS missing_branch_id,COUNT(*) AS affected_agents
FROM agents a WHERE NULLIF(TRIM(a.assigned_branch_id),'') IS NOT NULL
AND NOT EXISTS(SELECT 1 FROM branches b WHERE b.branch_id=TRIM(a.assigned_branch_id))
GROUP BY missing_branch_id ORDER BY affected_agents DESC,missing_branch_id LIMIT 20;
SELECT branch_id,branch_code FROM branches ORDER BY branch_id LIMIT 10;

CREATE TEMP TABLE duplicate_codes AS
SELECT TRIM(employee_code) AS normalized_code,COUNT(*) AS rows_in_group,
 COUNT(DISTINCT TRIM(agent_id)) AS distinct_agents
FROM agents WHERE NULLIF(TRIM(employee_code),'') IS NOT NULL
GROUP BY normalized_code HAVING COUNT(*)>1;
SELECT TO_HEX(SHA256(normalized_code)) AS employee_code_hash,rows_in_group,distinct_agents
FROM duplicate_codes ORDER BY rows_in_group DESC,employee_code_hash;
SELECT COUNT(*) AS duplicate_groups,COALESCE(SUM(rows_in_group),0) AS agents_in_duplicate_groups,
 COALESCE(SUM(rows_in_group-1),0) AS excess_rows FROM duplicate_codes;
SELECT COUNT(*) AS agents_with_both_issues FROM agents a
WHERE EXISTS(SELECT 1 FROM duplicate_codes d WHERE d.normalized_code=TRIM(a.employee_code))
AND NULLIF(TRIM(a.assigned_branch_id),'') IS NOT NULL
AND NOT EXISTS(SELECT 1 FROM branches b WHERE b.branch_id=TRIM(a.assigned_branch_id));
