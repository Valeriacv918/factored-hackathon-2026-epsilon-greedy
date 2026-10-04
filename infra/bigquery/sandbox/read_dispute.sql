-- Parameters: scenario_id, customer_id, case_id STRING. Run preflight first.
SELECT d.case_id AS id,d.customer_id,d.transaction_id,d.scenario_id,d.status,d.mode,TRUE AS verified
FROM `hackaton-509923.bank_sandbox.disputes` d
JOIN `hackaton-509923.bank_sandbox.scenarios` s ON s.scenario_id=d.scenario_id
JOIN `hackaton-509923.bank_curated.transactions` t
 ON t.transaction_id=d.transaction_id AND t.customer_id=d.customer_id
 AND t._curation_run_id=s.transactions_run_id AND d.transactions_run_id=s.transactions_run_id
WHERE d.scenario_id=@scenario_id AND d.customer_id=@customer_id AND d.case_id=@case_id
 AND d.mode='SIMULATED' AND d.status='OPEN' AND d.contract_version='1.0.0'
QUALIFY COUNT(*) OVER ()=1;
