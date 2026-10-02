DECLARE latest_run STRING DEFAULT (
 SELECT run_id FROM `hackaton-509923.bank_ops.curation_runs`
 WHERE table_name='daily_exchange_rates' ORDER BY started_at DESC LIMIT 1
);
SELECT run_id,status,input_rows,published_rows,pending_rules
FROM `hackaton-509923.bank_ops.curation_runs` WHERE run_id=latest_run AND table_name='daily_exchange_rates';
SELECT rule_id,observed,expected,passed,severity
FROM `hackaton-509923.bank_ops.curation_results` WHERE run_id=latest_run ORDER BY severity,rule_id;
SELECT COALESCE(SUM(source_count),0) AS quarantined_rows
FROM `hackaton-509923.bank_quarantine.daily_exchange_rates_rejected` WHERE run_id=latest_run;

SELECT source_currency,target_currency,COUNT(*) AS rows_in_pair,
 MIN(`date`) AS first_date,MAX(`date`) AS last_date,
 DATE_DIFF(MAX(`date`),MIN(`date`),DAY)+1-COUNT(DISTINCT `date`) AS missing_dates_within_span
FROM `hackaton-509923.bank_curated.daily_exchange_rates`
WHERE _curation_run_id=latest_run GROUP BY source_currency,target_currency
ORDER BY source_currency,target_currency;
