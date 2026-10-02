# Daily exchange rates curated v1
Compile with upload_workspace.py, then execute_compilation.py --table daily_exchange_rates.
After successful Dataform completion run verify_daily_exchange_rates.sql.

7 typed fields. Composite key date/source_currency/target_currency, after
DATE parsing and trimmed uppercase currency normalization. All duplicate-key
rows rejected, no arbitrary selection by provider. Any rejection blocks publication.
NUMERIC rates with enforced DECIMAL(12,6) bounds and scale; strictly positive
when present. Optional buy/sell/source NULL remains NULL. Currency format is
three ASCII uppercase letters, not a complete authoritative currency catalog.

Buy vs sell, principal rate outside interval, same-currency nonunit rate and
calendar gaps within each observed pair span are WARN observations.
Coverage is not enforced beyond observed bounds; absent pairs are not inferred.
No rounding, inversion, interpolation, forward-fill or synthetic records.
No cross-rate reciprocity or provider accuracy guarantee.

Transactional full replacement, clustered by source_currency,target_currency.
Small table not partitioned. Existing raw stays unchanged.
Expected profile: 13164 rows, 12 directed pairs, 1097 dates each,
2023-06-17 through 2026-06-17. Expected counts are not hardcoded.
Downstream consumers must handle missing date/pair explicitly; this package
only publishes reference data, not conversion or application fallback logic.

Audit and quarantine retention 30 days, staging 7 days; no concurrent runs.
Intermediate failures can leave RUNNING/VALIDATED; inspect Dataform as well.
Local generation tests do not replace compilation/execution in GCP.
