-- Grants reported applied in Cloud Shell. Requires existing bank-mcp service account.
-- Reviewed administrative deployment only; not part of the Dataform DAG.
GRANT `roles/bigquery.dataViewer` ON SCHEMA `hackaton-509923.bank_curated`
TO "serviceAccount:bank-mcp@hackaton-509923.iam.gserviceaccount.com";

GRANT `roles/bigquery.dataViewer` ON SCHEMA `hackaton-509923.bank_sandbox`
TO "serviceAccount:bank-mcp@hackaton-509923.iam.gserviceaccount.com";

GRANT `roles/bigquery.dataEditor` ON TABLE `hackaton-509923.bank_sandbox.card_blocks`
TO "serviceAccount:bank-mcp@hackaton-509923.iam.gserviceaccount.com";

GRANT `roles/bigquery.dataEditor` ON TABLE `hackaton-509923.bank_sandbox.disputes`
TO "serviceAccount:bank-mcp@hackaton-509923.iam.gserviceaccount.com";

GRANT `roles/bigquery.dataEditor` ON TABLE `hackaton-509923.bank_sandbox.handoffs`
TO "serviceAccount:bank-mcp@hackaton-509923.iam.gserviceaccount.com";

GRANT `roles/bigquery.dataEditor` ON TABLE `hackaton-509923.bank_sandbox.notifications`
TO "serviceAccount:bank-mcp@hackaton-509923.iam.gserviceaccount.com";
