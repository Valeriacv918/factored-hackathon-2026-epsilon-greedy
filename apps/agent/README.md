# Agente de disputas con LangGraph

Primera implementación ejecutable: seis componentes, transiciones en código y
confirmaciones mediante botones. Los servicios de pruebas son sintéticos; aún no
hay conexión a GCP, MCP o a un proveedor de modelos.

## Estructura

```text
src/bank_agent/
  graphs/state.py             Estado compartido e inicialización
  graphs/disputes.py          Grafo y controles comunes
  graphs/policy.py            Política de demostración configurable
  nodes/security_language/   1. Seguridad e idioma ES/PT/EN
  nodes/understanding/       2. Comprensión, aclaración y búsqueda
  nodes/lost_card/           3. Tarjeta perdida o robada
  nodes/fraud/               4. Señal de fraude
  nodes/charge_error/        5. Error en el cargo
  nodes/escalation/          6. Transferencia humana
  nodes/common.py            Confirmaciones, herramientas y verificación
  clients/contracts.py       Contrato de servicios futuros
```

```mermaid
flowchart TD
    START --> S[Seguridad e idioma]
    S -->|sesión válida| U[Comprensión]
    S -->|sesión inválida| END
    U -->|aclarar o buscar| U
    U -->|tarjeta perdida| C[Tarjeta perdida]
    U -->|cargo desconocido o riesgo| F[Señal de fraude]
    U -->|cargo reconocido con error| E[Error en el cargo]
    C -->|cargo desconocido| U
    F -->|otro cargo| U
    U --> H[Escalación]
    C --> H
    F --> H
    E --> H
    F --> END
    E --> END
    H --> END
```

Cada componente es un nodo con fases internas. Cada transición de fase crea un
checkpoint; una espera usa `interrupt()`. No hay escrituras antes de una espera
en la misma fase. Los adaptadores deben garantizar idempotencia ante reejecución.

## Pruebas (PowerShell, desde apps/agent)

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
.venv/Scripts/python.exe -m pytest -q
```

Python 3.12+ (probado con 3.12), independiente del entorno analítico raíz.
`requirements.lock.txt` fija versiones del entorno probado, sin hashes.
Para instalar el paquete: `pip install -e .`.

## Integrar

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from bank_agent.graphs.disputes import build_graph
from bank_agent.graphs.state import initial_state

# services implementa clients.contracts.Services.
graph = build_graph(services, checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "conversation-123"}, "recursion_limit": 100}
result = graph.invoke(initial_state("conversation-123", "trusted-session-ref", mensaje), config)
# Presentar result['__interrupt__'][0].value en la UI.
result = graph.invoke(Command(resume={"choice": "yes"}), config)
# Aclaración de transacción: Command(resume={"text": "fecha, monto o comercio"}).
```

La aplicación debe vincular `thread_id`, `conversation_id` y `session_ref` al
usuario autenticado. Nunca aceptar estado arbitrario del navegador ni exponer
`graph.invoke` directamente. No guardar tokens en checkpoints. La sesión se
revalida antes de nodos protegidos, al recibir confirmaciones y antes de herramientas.
Usar un checkpointer persistente y protegido al desplegar; `InMemorySaver` es local.

## Ejecutar contra el servidor MCP (datos reales)

`clients/mcp_services.py:McpServices` implementa `Services` sobre `apps/mcp-server`
(solo lectura: `find_transactions`, `list_cards`, `get_card`), un LLM para
`understand` y lingua para el idioma. Bloqueos, disputas, `dispute_context` y
derivaciones aún no existen: fallan con `ServiceFailure` y el grafo termina de forma
segura (escalación o "servicio no disponible"), nunca anunciando un éxito.
`customer_id` sale siempre de la sesión; `reference_date` del reloj de escenario.

```powershell
.venv/Scripts/python.exe -m pip install -e ".[live,test]"   # desde apps/agent
# .env en la raíz: SCENARIO_NOW, DEV_SESSIONS (solo desarrollo), LLM_MODEL, GROQ_API_KEY
# y el venv de apps/mcp-server instalado (ver su README). Desde la raíz:
apps/agent/.venv/Scripts/python.exe scripts/run_disputes.py --session dev --debug
```

`DEV_SESSIONS` asocia referencias fijas a clientes reales sin login; se reemplazará
por el validador cuando `normalize_id` conserve los guiones de los IDs reales.

## Decisiones y límites

- ES/PT/EN: detección y extracción inyectadas mediante `Services`.
- Política demo v4: 90 días, USD 500, score 30. No son políticas bancarias reales.
  Fecha de referencia: `services.now()`. Para históricos, inyectar un reloj de
  simulación explícito. Fechas futuras o sin zona escalan.
- `amount_usd` requiere conversión verificada por el servicio; datos monetarios
  o de riesgo ausentes escalan, no se imputan.
- Hasta 2 aclaraciones, 3 cargos desconocidos y 8 turnos, configurable. Calibrar
  el límite de turnos con las evaluaciones de recorridos largos.
- Bloqueos por tarjeta y disputas por transacción; claves de idempotencia para
  mutaciones. Verificación mediante lectura posterior independiente.
- Un reintento por herramienta. Si falla la derivación, termina sin anunciar
  una transferencia exitosa. El trace conserva nodos, fases y tiempos.
- Respuestas y resumen con plantillas. Pendientes: adaptadores reales, modelo
  narrativo, claim checker, métricas de tokens/costo y detector/clasificador real.
- Petición humana en botones autenticados y comprensión. Texto libre no confirma
  acciones. La futura UI necesita un canal para nuevas emergencias durante
  cualquier pausa; hoy se detectan en entrada y aclaración de transacciones.
- No hay frontend, endpoint, Dockerfile, alertas reales ni despliegue.

Referencia: [interrupciones de LangGraph](https://docs.langchain.com/oss/python/langgraph/interrupts).
