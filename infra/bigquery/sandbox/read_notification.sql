-- Parameters: scenario_id, customer_id, delivery_id STRING. Verifies SIMULATED record, not delivery.
SELECT n.delivery_id AS id,n.ticket_id,n.customer_id,n.scenario_id,n.mode,n.status,TRUE AS verified
FROM `hackaton-509923.bank_sandbox.notifications` n
JOIN `hackaton-509923.bank_sandbox.scenarios` s ON s.scenario_id=n.scenario_id
JOIN `hackaton-509923.bank_sandbox.handoffs` h
 ON h.scenario_id=n.scenario_id AND h.customer_id=n.customer_id AND h.ticket_id=n.ticket_id
WHERE n.scenario_id=@scenario_id AND n.customer_id=@customer_id AND n.delivery_id=@delivery_id
 AND n.mode='SIMULATED' AND n.status='SIMULATED' AND n.contract_version='1.0.0'
 AND h.mode='SIMULATED' AND h.contract_version='1.0.0'
QUALIFY COUNT(*) OVER ()=1;
