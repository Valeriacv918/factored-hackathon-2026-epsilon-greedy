-- Read only. @scenario_id STRING. Freeze curated for the entire scenario.
ASSERT (SELECT COUNT(*)=1 FROM `hackaton-509923.bank_sandbox.scenarios`
        WHERE scenario_id=@scenario_id) AS 'Unknown or duplicate scenario';
ASSERT (SELECT COUNT(*)>0 AND COUNTIF(p._curation_run_id IS NULL OR p._curation_run_id!=s.products_run_id)=0
 FROM `hackaton-509923.bank_curated.products` p
 CROSS JOIN `hackaton-509923.bank_sandbox.scenarios` s
 WHERE s.scenario_id=@scenario_id) AS 'Products baseline changed';
ASSERT (SELECT COUNT(*)>0 AND COUNTIF(t._curation_run_id IS NULL OR t._curation_run_id!=s.transactions_run_id)=0
 FROM `hackaton-509923.bank_curated.transactions` t
 CROSS JOIN `hackaton-509923.bank_sandbox.scenarios` s
 WHERE s.scenario_id=@scenario_id) AS 'Transactions baseline changed';
