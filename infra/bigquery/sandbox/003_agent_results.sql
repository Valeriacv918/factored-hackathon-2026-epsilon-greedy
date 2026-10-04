-- Additive schema. Does not alter curated or existing sandbox tables.
CREATE TABLE IF NOT EXISTS `hackaton-509923.bank_sandbox.agent_results` (
 result_id STRING NOT NULL,
 conversation_id STRING NOT NULL,
 customer_id STRING NOT NULL,
 transaction_id STRING NOT NULL,
 agent_name STRING NOT NULL,
 observed_status STRING NOT NULL,
 rule_id STRING NOT NULL,
 explanation STRING NOT NULL,
 transaction_run_id STRING NOT NULL,
 created_at TIMESTAMP NOT NULL,
 mode STRING NOT NULL
)
CLUSTER BY customer_id, conversation_id;
GRANT `roles/bigquery.dataEditor`
ON TABLE `hackaton-509923.bank_sandbox.agent_results`
TO "serviceAccount:bank-mcp@hackaton-509923.iam.gserviceaccount.com";
