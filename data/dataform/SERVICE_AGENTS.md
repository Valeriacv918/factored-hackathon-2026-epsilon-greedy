# Service agents curated v1

Apply over ~/bank-dataform. Run upload_workspace.py, then after COMPILED:
python3 execute_compilation.py --table service_agents
After completion execute verify_service_agents.sql in BigQuery us-central1.

Approved exception: missing assigned branch is WARN, source ID preserved.
_branch_reference_status: NOT_PROVIDED, UNRESOLVED, RESOLVED.
_quality_warnings stores row warnings. Resolved closed branches are WARN only.
Branch warnings are counted across all input rows in curation_results;
published counts exclude rejected agents, so 831 input vs 811 published is expected.

Every row with a duplicated employee_code is quarantined. No arbitrary winner.
Only employee_code.not_unique permits partial publication. All other errors block.
Repeated agent_id blocks. Counts are computed; no hardcoded rejection threshold.
Optional NULLs remain NULL. languages stays text; no splitting or inference.
CSAT numeric scale 2, range 1-5; interaction count integral and nonnegative.
Domain checks use supplied dictionary and observed countries.

Expected: 1200 input, 1174 published, 26 quarantined, 811 published unresolved.
Other published agents have missing or resolved branches; actual counts verified.

Reference branch snapshot and run ID recorded in curation_references.
Transactional full replacement; no partition for this small dimension.
Audit/quarantine retention 30 days, staging 7 days. No concurrent runs.
Intermediate failures can leave RUNNING/VALIDATED; check Dataform status too.
Other tables are not modified; downstream agent FK validation remains pending.
Local tests verify generated rules and graph, not BigQuery execution.
