# Pruebas del agente

Se ejecutan en el entorno propio del agente (`apps/agent/.venv`), nunca en el
entorno raíz. Desde la raíz del repositorio:

```bash
uv sync --project apps/agent                                 # una vez
uv run --project apps/agent pytest apps/agent                # unitarias (por defecto, y en CI)
uv run --project apps/agent pytest apps/agent -m integration # integración en vivo (opcional)
```

Desde `apps/agent` basta `uv run pytest` (o `uv run pytest -m integration`).

## Organización

| Archivo | Qué cubre |
|---|---|
| `conftest.py` | `FakeServices` y la fixture `fake_services`: servicios sintéticos en memoria |
| `test_graph.py` | Grafo de disputas: ES/PT, confirmaciones, aislamiento de clientes, sesiones, políticas, reintentos, verificación, bloqueo, disputas y escalamiento |
| `test_mcp_services.py` | `McpServices` con un cliente MCP falso; detector de idioma real (lingua) |
| `test_mcp_client.py` | `McpToolClient` por stdio contra `mcp_echo_server.py` (errores, timeouts) |
| `test_understanding.py` | Extracción con LLM simulado; slots alineados con `contracts/mcp` |
| `test_triage_schemas.py` | Contrato del Triage |
| `test_validator_validation.py` | Validador de identidad e idioma, con datos sintéticos |
| `test_validator_agent_flow.py` | Agente validador completo con LLM simulado |
| `integration/test_live_mcp.py` | En vivo: servidor MCP real y BigQuery (ver abajo) |

**Unitarias:** sin red, GCP ni modelos.

**Integración** (`integration/`, marcador `integration`): levantan el servidor MCP
real con `uv run --project apps/mcp-server bank-mcp`, en su propio entorno, y
consultan `bank_curated` con tus credenciales ADC (ver `apps/mcp-server/README.md`).
Solo lectura. Usan el cliente de la entrada `dev` de `DEV_SESSIONS`, el mismo de
`run_disputes.py --session dev`. Si falta, se omiten (*skipped*).

## Cómo leer el resultado

- `N passed, M deselected`: ejecución por defecto; las M son las de integración.
  `addopts = "-m 'not integration'"` (en `pyproject.toml`) las deja fuera a propósito.
- Con `-m integration` es al revés: corren esas y las unitarias quedan *deselected*.
- *skipped* significa que una prueba seleccionada no pudo correr (p. ej., falta
  `DEV_SESSIONS` o `uv`), no que haya fallado.

## Convenciones

- **Sin `__init__.py` en `tests/`.** Hacía que pytest alterara `sys.path` y
  rompía importaciones.
- **Ayudas compartidas como fixtures en `conftest.py`**, no módulos importados por
  nombre (`from fakes import ...`).
- **Importar siempre `bank_agent...`**, nunca `src.bank_agent...`: el paquete
  está instalado, y `src.` carga una segunda copia (dos `settings`, `isinstance`
  que falla).
- Una prueba nueva que necesite GCP, red o un modelo real va en `integration/`
  con el marcador; todo lo demás debe correr sin conexión.

La calidad del LLM (p. ej., el set del Triage) se mide en `evals/`, no aquí: son
métricas, no pruebas de pasa/falla.
