-- Admin only; execute sequentially. Parameters: scenario_id, created_by STRING; scenario_clock TIMESTAMP.
DECLARE products_run STRING;
DECLARE transactions_run STRING;
ASSERT LENGTH(TRIM(@scenario_id))>0 AS 'scenario_id required';
ASSERT LENGTH(TRIM(@created_by))>0 AS 'created_by required';
ASSERT @scenario_clock IS NOT NULL AS 'scenario_clock required';
ASSERT (SELECT COUNT(*)=0 FROM `hackaton-509923.bank_sandbox.scenarios`
        WHERE scenario_id=@scenario_id) AS 'Scenario already exists';
ASSERT (SELECT COUNT(*)>0 AND COUNTIF(_curation_run_id IS NULL)=0
        AND COUNT(DISTINCT _curation_run_id)=1 FROM `hackaton-509923.bank_curated.products`)
        AS 'Products must contain one published run';
ASSERT (SELECT COUNT(*)>0 AND COUNTIF(_curation_run_id IS NULL)=0
        AND COUNT(DISTINCT _curation_run_id)=1 FROM `hackaton-509923.bank_curated.transactions`)
        AS 'Transactions must contain one published run';
SET products_run=(SELECT MIN(_curation_run_id) FROM `hackaton-509923.bank_curated.products`);
SET transactions_run=(SELECT MIN(_curation_run_id) FROM `hackaton-509923.bank_curated.transactions`);
INSERT INTO `hackaton-509923.bank_sandbox.scenarios`
(scenario_id,created_at,created_by,scenario_clock,products_run_id,transactions_run_id)
VALUES (@scenario_id,CURRENT_TIMESTAMP(),@created_by,@scenario_clock,products_run,transactions_run);
