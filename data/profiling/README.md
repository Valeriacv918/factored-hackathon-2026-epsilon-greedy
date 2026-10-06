# Profiles

SQL profiles and diagnostics to run in BigQuery (`us-central1`). They write observations to audit
tables; they do not publish curated data. Check permissions and the raw table before running them.
Diagnostics may pin a historical snapshot: check Time Travel availability before reusing them.
They are not automatic steps of any pipeline.
