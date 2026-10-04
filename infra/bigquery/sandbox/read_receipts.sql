-- Parameters: scenario_id, customer_id STRING. History is not action verification.
SELECT * FROM (
 SELECT 'block_card' AS action,block_id AS receipt_id,card_id AS target_id,
 scenario_id,customer_id,status,mode,created_at FROM `hackaton-509923.bank_sandbox.card_blocks`
 WHERE scenario_id=@scenario_id AND customer_id=@customer_id
 UNION ALL
 SELECT 'file_dispute',case_id,transaction_id,scenario_id,customer_id,status,mode,created_at
 FROM `hackaton-509923.bank_sandbox.disputes` WHERE scenario_id=@scenario_id AND customer_id=@customer_id
 UNION ALL
 SELECT 'create_handoff',ticket_id,CAST(NULL AS STRING),scenario_id,customer_id,'RECORDED',mode,created_at
 FROM `hackaton-509923.bank_sandbox.handoffs` WHERE scenario_id=@scenario_id AND customer_id=@customer_id
 UNION ALL
 SELECT 'notify_employee',delivery_id,ticket_id,scenario_id,customer_id,status,mode,created_at
 FROM `hackaton-509923.bank_sandbox.notifications` WHERE scenario_id=@scenario_id AND customer_id=@customer_id
) ORDER BY created_at DESC,action,receipt_id LIMIT 100;
