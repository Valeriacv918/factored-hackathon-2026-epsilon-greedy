"""Fixed explanation persistence. Customer identity comes from the signed token."""
SAVE = """
MERGE {results} target
USING (
 SELECT @result_id result_id, @conversation_id conversation_id,
        customer_id, transaction_id, 'charge_error' agent_name,
        transaction_status observed_status, @rule_id rule_id,
        @explanation explanation, _curation_run_id transaction_run_id
 FROM {transactions}
 WHERE customer_id=@customer_id AND transaction_id=@transaction_id
   AND transaction_status=@observed_status
 QUALIFY COUNT(*) OVER () = 1
) source
ON target.result_id=source.result_id
WHEN NOT MATCHED THEN INSERT (
 result_id,conversation_id,customer_id,transaction_id,agent_name,observed_status,
 rule_id,explanation,transaction_run_id,created_at,mode
) VALUES (
 source.result_id,source.conversation_id,source.customer_id,source.transaction_id,
 source.agent_name,source.observed_status,source.rule_id,source.explanation,
 source.transaction_run_id,CURRENT_TIMESTAMP(),'SIMULATED'
)
"""
READ = """
SELECT result_id, transaction_id, observed_status, rule_id, explanation
FROM {results}
WHERE result_id=@result_id AND customer_id=@customer_id
 AND conversation_id=@conversation_id AND transaction_id=@transaction_id
 AND observed_status=@observed_status AND rule_id=@rule_id
 AND explanation=@explanation AND agent_name='charge_error' AND mode='SIMULATED'
"""
