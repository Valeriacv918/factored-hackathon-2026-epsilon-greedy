# Pruebas del grafo

Desde apps/agent: `uv run pytest -q` (o desde la raíz: `uv run --project apps/agent pytest apps/agent -q`)

Servicios sintéticos en fakes.py; sin red, GCP ni modelos. Cubren ES/PT,
confirmaciones, aislamiento de clientes, sesiones, políticas, reintentos,
verificación, bloqueo, disputas y escalamiento. No sustituyen la evaluación
held-out del modelo ni pruebas de integración del futuro servidor MCP.
