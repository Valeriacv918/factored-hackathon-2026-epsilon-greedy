# Arquitectura

Flujo existente: GCS -> Cloud Run ingestion -> BigQuery raw -> Dataform -> curated.
Auditoria: bank_ops. Rechazos: bank_quarantine.
Flujo de aplicacion por implementar: agente LangGraph -> servidor MCP -> curated.
El agente no debe replicar contratos ni convertirse en un segundo motor ETL.
MCP debe exponer herramientas delimitadas, no SQL arbitrario al modelo.

Dataform tiene dependencias internas por tabla. Referencias a otras tablas usan
snapshots publicados, no disparan automaticamente su reconstruccion.
Workflows, CI y API todavia no estan implementados. Apps separadas permiten
identidades, dependencias y despliegues propios en un unico repositorio.
No hay frontend creado: se anadira apps/web cuando se decida esa interfaz.
