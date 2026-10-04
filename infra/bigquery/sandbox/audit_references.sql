-- @scenario_id STRING. Run after preflight. All violations must be zero.
SELECT 'card_blocks' AS table_name,'card_reference_or_state' AS rule_id,COUNT(*) AS violations
FROM `hackaton-509923.bank_sandbox.card_blocks` b
WHERE b.scenario_id=@scenario_id AND NOT EXISTS (
 SELECT 1 FROM `hackaton-509923.bank_curated.products` p
 JOIN `hackaton-509923.bank_sandbox.scenarios` s ON s.scenario_id=b.scenario_id
 WHERE p.product_id=b.card_id AND p.customer_id=b.customer_id
 AND p.product_type IN ('Tarjeta Crédito','Tarjeta Débito') AND p.product_status='Active'
 AND p._curation_run_id=b.products_run_id AND b.products_run_id=s.products_run_id)
UNION ALL
SELECT 'disputes','transaction_reference',COUNT(*)
FROM `hackaton-509923.bank_sandbox.disputes` d
WHERE d.scenario_id=@scenario_id AND NOT EXISTS (
 SELECT 1 FROM `hackaton-509923.bank_curated.transactions` t
 JOIN `hackaton-509923.bank_sandbox.scenarios` s ON s.scenario_id=d.scenario_id
 WHERE t.transaction_id=d.transaction_id AND t.customer_id=d.customer_id
 AND t._curation_run_id=d.transactions_run_id AND d.transactions_run_id=s.transactions_run_id)
UNION ALL
SELECT 'handoffs','customer_reference',COUNT(*)
FROM `hackaton-509923.bank_sandbox.handoffs` h
WHERE h.scenario_id=@scenario_id AND NOT EXISTS (
 SELECT 1 FROM `hackaton-509923.bank_curated.customers` c WHERE c.customer_id=h.customer_id)
UNION ALL
SELECT 'notifications','ticket_reference',COUNT(*)
FROM `hackaton-509923.bank_sandbox.notifications` n
WHERE n.scenario_id=@scenario_id AND NOT EXISTS (
 SELECT 1 FROM `hackaton-509923.bank_sandbox.handoffs` h
 WHERE h.scenario_id=n.scenario_id AND h.customer_id=n.customer_id AND h.ticket_id=n.ticket_id);
