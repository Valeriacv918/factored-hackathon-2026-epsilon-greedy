# Integration inventory

Integrated the prepared bank-platform source tree into this repository.
Existing profiling.ipynb, docs/policies.md, docs/findings_tables.txt,
pyproject.toml, uv.lock and .python-version were preserved byte for byte.
README and .gitignore were adapted to coexist with the existing analysis.
No datasets, credential files, node_modules or runtime compilation state copied.
No deployment, commit or push performed by this integration.

Included: ingestion engine, seven Dataform models and their contracts/tests,
profiling SQL, diagnostic SQL, three locally available raw contracts, and app
scaffolding/documentation. The app and infrastructure folders have no new runtime
implementation. Existing per-table instructions referencing ~/bank-dataform
should be interpreted as this repository's data/dataform directory.

Still pending: recover exact missing raw contracts from GCS, inventory live Cloud
Run Job settings, finish reference checks, and implement end-to-end orchestration.
Original deployment state was not refreshed from GCP as part of this integration.


Actualizacion 2026-10-01: contratos raw recuperados e inventario de jobs registrado.
Ver gcp-audit-2026-10-01.md; sustituye el pendiente de recuperacion/inventario
anterior. Permisos efectivos y despliegue automatico siguen sin verificar/configurar.
