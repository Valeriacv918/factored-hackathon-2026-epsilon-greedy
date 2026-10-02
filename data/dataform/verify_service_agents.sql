DECLARE latest_run STRING DEFAULT (
 SELECT run_id FROM `hackaton-509923.bank_ops.curation_runs`
 WHERE table_name='service_agents' ORDER BY started_at DESC LIMIT 1
);
SELECT run_id,status,input_rows,published_rows,pending_rules
FROM `hackaton-509923.bank_ops.curation_runs` WHERE run_id=latest_run AND table_name='service_agents';
SELECT rule_id,observed,expected,passed,severity
FROM `hackaton-509923.bank_ops.curation_results` WHERE run_id=latest_run ORDER BY severity,rule_id;
SELECT COALESCE(SUM(source_count),0) AS quarantined_rows
FROM `hackaton-509923.bank_quarantine.service_agents_rejected` WHERE run_id=latest_run;
SELECT * FROM `hackaton-509923.bank_ops.curation_references` WHERE run_id=latest_run;

SELECT _branch_reference_status,COUNT(*) AS published_agents
FROM `hackaton-509923.bank_curated.service_agents`
WHERE _curation_run_id=latest_run GROUP BY _branch_reference_status;
