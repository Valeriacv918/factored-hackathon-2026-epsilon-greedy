-- Parameters: scenario_id, customer_id, card_id, block_id STRING.
-- Exactly one returned row is required. No rows means NOT verified. Run preflight first.
SELECT b.block_id AS id,b.card_id,b.customer_id,b.scenario_id,b.mode,
 'Blocked' AS status,TRUE AS verified,b.created_at,b.products_run_id
FROM `hackaton-509923.bank_sandbox.card_blocks` b
JOIN `hackaton-509923.bank_sandbox.scenarios` s ON s.scenario_id=b.scenario_id
JOIN `hackaton-509923.bank_curated.products` p
 ON p.product_id=b.card_id AND p.customer_id=b.customer_id
 AND p._curation_run_id=s.products_run_id AND b.products_run_id=s.products_run_id
WHERE b.scenario_id=@scenario_id AND b.customer_id=@customer_id
 AND b.card_id=@card_id AND b.block_id=@block_id
 AND b.mode='SIMULATED' AND b.contract_version='1.0.0' AND b.status='Blocked'
 AND p.product_type IN ('Tarjeta Crédito','Tarjeta Débito') AND p.product_status='Active'
QUALIFY COUNT(*) OVER ()=1;
