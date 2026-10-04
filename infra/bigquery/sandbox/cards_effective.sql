-- Parameters: scenario_id, customer_id STRING. Authentication belongs to caller.
-- Run preflight first; an empty result is not a successful action verification.
WITH scenario AS (
 SELECT * FROM `hackaton-509923.bank_sandbox.scenarios` WHERE scenario_id=@scenario_id
 QUALIFY COUNT(*) OVER (PARTITION BY scenario_id)=1
), blocks AS (
 SELECT b.* FROM `hackaton-509923.bank_sandbox.card_blocks` b
 JOIN scenario s ON b.scenario_id=s.scenario_id AND b.products_run_id=s.products_run_id
 WHERE b.customer_id=@customer_id AND b.mode='SIMULATED'
 AND b.status='Blocked' AND b.contract_version='1.0.0'
 QUALIFY ROW_NUMBER() OVER (
 PARTITION BY b.scenario_id,b.customer_id,b.card_id ORDER BY b.created_at DESC,b.block_id DESC)=1
)
SELECT p.product_id AS card_id,p.customer_id,p.product_type,
 RIGHT(p.product_number,4) AS last4,p.product_status AS baseline_status,
 IF(b.block_id IS NOT NULL AND p.product_status='Active','Blocked',p.product_status) AS effective_status,
 b.block_id,b.created_at AS blocked_at,s.scenario_id,p._curation_run_id AS products_run_id,
 'SIMULATED' AS mode
FROM `hackaton-509923.bank_curated.products` p
JOIN scenario s ON p._curation_run_id=s.products_run_id
LEFT JOIN blocks b ON b.customer_id=p.customer_id AND b.card_id=p.product_id
WHERE p.customer_id=@customer_id AND p.product_type IN ('Tarjeta Crédito','Tarjeta Débito')
ORDER BY p.product_id;
