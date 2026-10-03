# tests

Pruebas unitarias del servidor MCP, sin GCP ni red. Desde la raíz:

```bash
uv sync --project apps/mcp-server --extra test
uv run --project apps/mcp-server pytest apps/mcp-server
```

| Archivo | Qué cubre |
|---|---|
| `test_contracts.py` | `contracts/mcp/*.json` coincide con las firmas de las herramientas (regenerar con `scripts/export_contracts.py`) |
| `test_mapping.py` | Traducción de filas de BigQuery a los campos del agente (`services/mapping.py`) |
| `test_search.py` | Construcción parametrizada de la consulta de `find_transactions` (slots, ventana de fechas, tolerancia de monto) |

Las pruebas contra BigQuery real viven del lado del agente
(`apps/agent/tests/integration/`), que levanta este servidor como lo haría en producción.
Mismas convenciones que en `apps/agent/tests/README.md`: sin `__init__.py`, ayudas
en `conftest.py`, importar `bank_mcp...`.
