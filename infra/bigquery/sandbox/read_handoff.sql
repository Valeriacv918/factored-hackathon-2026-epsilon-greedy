-- Parameters: scenario_id, customer_id, ticket_id STRING. Run preflight first.
SELECT h.ticket_id AS id,h.customer_id,h.scenario_id,h.mode,TRUE AS verified
FROM `hackaton-509923.bank_sandbox.handoffs` h
JOIN `hackaton-509923.bank_sandbox.scenarios` s ON s.scenario_id=h.scenario_id
JOIN `hackaton-509923.bank_curated.customers` c ON c.customer_id=h.customer_id
WHERE h.scenario_id=@scenario_id AND h.customer_id=@customer_id AND h.ticket_id=@ticket_id
 AND h.mode='SIMULATED' AND h.contract_version='1.0.0'
QUALIFY COUNT(*) OVER ()=1;
