# tests

Pruebas del servidor MCP. Desde la raíz:

```bash
uv sync --project apps/mcp-server
uv run --project apps/mcp-server pytest apps/mcp-server                 # unitarias: sin GCP ni red (CI)
uv run --project apps/mcp-server pytest apps/mcp-server -m integration  # dry run en BigQuery (opcional)
```

| Archivo | Qué cubre |
|---|---|
| `conftest.py` | `FakeGateway` (responde por nombre de herramienta y registra cada consulta), clave de firma conocida, estado del servidor limpio; fixtures `gateway`, `token`, `signing_key` |
| `test_contracts.py` | `contracts/mcp/*.json` coincide con las firmas de las herramientas (regenerar con `scripts/export_contracts.py`) |
| `test_identity.py` | `verify_identity`: parámetros normalizados, token firmado, intentos y bloqueo |
| `test_session.py` | Tokens de sesión (firma, expiración, manipulación) y `LoginThrottle` |
| `test_mapping.py` | Traducción de filas de BigQuery a los campos del agente (`services/mapping.py`) |
| `test_search.py` | Construcción parametrizada de la consulta de `find_transactions` (slots, ventana de fechas, tolerancia de monto) |
| `test_sandbox.py` | Herramientas del sandbox: escenario, cliente del token, hashes, recibos, rechazos, esquema del paquete de derivación |
| `test_sql_dry_run.py` | `integration`: compila cada sentencia de `sql/queries.py` en BigQuery con dry run (no lee ni escribe datos) |

**Qué no prueban las unitarias.** `FakeGateway` devuelve las filas que el test le da,
así que comprueban lo que decide y envía Python, no el SQL: titularidad,
elegibilidad y deduplicación viven en las consultas. El dry run detecta errores de
compilación y de permisos; el comportamiento de las consultas se comprueba en vivo
(ver `docs/mcp-sandbox.md`). Para comprobar los permisos de despliegue, ejecutar el
dry run impersonando a `bank-mcp`.

Las pruebas en vivo del agente contra este servidor están en
`apps/agent/tests/integration/`. Mismas convenciones que en `apps/agent/tests/README.md`:
sin `__init__.py`, ayudas como fixtures en `conftest.py`, importar `bank_mcp...`.
