# GCP read-only audit

Collector: scripts/verify/audit_gcp.py. Baseline: audit_baseline.json, generated
from the repository at preparation time. Regenerate hashes after source changes;
this baseline is not automatically refreshed.
Run in authenticated Cloud Shell alongside the baseline JSON. No external Python
dependencies. Only GET API calls; auth uses gcloud auth print-access-token.
No cloud writes, SQL queries, deployments or pipeline executions.

Collects workspace file hashes, directory inventory, recent invocation metadata,
ingestion job configuration (allowlisted environment values), storage settings,
structural contract fields, BigQuery schemas and metadata row counts.
Tokens are not written. Unknown env values and arbitrary contract fields excluded.
The downloaded contract export is structural fields only, not a byte-exact backup.
Missing/denied API resources produce PARTIAL, not a successful verification.

Limitations: collection is not atomic; effective IAM not checked; workspace parity
does not establish parity with each compiled/deployed execution. Remote-only nested
files need follow-up from directory inventory. No actual data quality rerun.
Result is local report.json plus structural contract exports inside a ZIP.
Do not commit exports by default. Review findings before changing deployed resources.

Official Dataform read endpoint:
https://docs.cloud.google.com/dataform/reference/rest/v1/projects.locations.repositories.workspaces/readFile
