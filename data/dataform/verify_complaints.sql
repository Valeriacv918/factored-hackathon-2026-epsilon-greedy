DECLARE latest_run STRING DEFAULT (
 SELECT run_id FROM `hackaton-509923.bank_ops.curation_runs`
 WHERE table_name='complaints' ORDER BY started_at DESC LIMIT 1
);
SELECT run_id,status,input_rows,published_rows,pending_rules
FROM `hackaton-509923.bank_ops.curation_runs` WHERE run_id=latest_run AND table_name='complaints';
SELECT rule_id,observed,expected,passed,severity
FROM `hackaton-509923.bank_ops.curation_results` WHERE run_id=latest_run ORDER BY severity,rule_id;
SELECT COALESCE(SUM(source_count),0) AS quarantined_rows
FROM `hackaton-509923.bank_quarantine.complaints_rejected` WHERE run_id=latest_run;
SELECT * FROM `hackaton-509923.bank_ops.curation_references` WHERE run_id=latest_run;

SELECT COUNT(*) AS published_rows,
  COUNTIF(_product_owner_mismatch) AS owner_mismatch,
  COUNTIF(_product_owner_mismatch IS NULL) AS owner_not_evaluated
FROM `hackaton-509923.bank_curated.complaints`
WHERE _curation_run_id=latest_run;
