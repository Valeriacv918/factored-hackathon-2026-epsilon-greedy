# Validación y triage en el grafo local

Alcance: integración de los módulos actuales de validación y triage. No se
ejecutan emergency ni fraud. El grafo anterior se conserva en disputes.py;
el flujo acotado está en graphs/validation_triage.py.

## Ejecutar en la rama actual

Desde la raíz del repo, con los dos entornos ya sincronizados:

```bash
py -m uv run --project apps/agent --locked scripts/run_disputes.py --flow validation-triage --debug
```

La CLI usa este flujo por defecto. `--flow legacy` selecciona el grafo anterior,
que aún contiene nodos placeholder; no usarlo como prueba de una gestión exitosa.
No es necesario hacer merge ni cambiar de rama.

Configuración local:
- GROQ_API_KEY y LLM_MODEL: proveedor real ya configurado.
- MCP_SERVER_URL vacío para ejecutar el MCP local por stdio.
- MCP_SERVER_COMMAND=py -m uv run --project apps/mcp-server --locked bank-mcp
- ADC impersonando bank-mcp en Windows.
- SCENARIO_NOW sigue siendo el reloj de transacciones; autenticación y TTL usan
  la hora real, para no expirar sesiones según datos históricos.

DEV_SESSIONS no salta la validación de este flujo. El argumento --session se
conserva por compatibilidad con legacy; el validador crea una sesión aleatoria
independiente para cada conversación.

## Recorrido esperado

1. Saludar o describir el problema. ValidationAgent pide ID/documento, fecha de
   nacimiento y número de un producto. No usar product_id PRD-... como número
   de producto: ese campo es products.product_number.
2. La tool del agente llama a IdentityValidator. Su repositorio de confianza
   invoca la herramienta MCP verify_identity; el agente no abre BigQuery.
3. MCP compara los tres factores y la titularidad con parámetros de BigQuery.
   Admite customer_id CLI-... o document_number normalizado. No devuelve fecha
   de nacimiento ni documento, y una discordancia devuelve verified=false,
   customer_id=null, products=[].
4. Tras verificar, el repositorio entrega el ID canónico y los productos al
   validador, que crea la sesión con TTL. El LLM solo recibe estado/intentos y
   cantidad de productos; nunca el registro completo.
5. El grafo solicita el motivo de atención en un nuevo turno. Se hace así para
   no enviar al clasificador el mensaje que contiene los factores de identidad.
6. Triage clasifica con LLMClassifier y aplica decide en código. No consulta
   BigQuery ni MCP: esta etapa solo determina intención y destino.
7. Las rutas siguientes quedan preparadas, sin ejecutar acciones:
   - EMERGENCY -> ready_for_card_emergency.
   - FIND_TRANSACTION -> ready_for_transaction_search.
   - ESCALATION -> human_requested (no ticket creado).
   - OUT_OF_SCOPE -> out_of_scope.
   - CLARIFY_INTENT -> botones de aclaración; después clasifica sin otra llamada LLM.

La sesión se revalida antes de triage y después de la pausa de aclaración.
Los errores terminan en service_unavailable, sin resultado de negocio inventado.
La llamada del agente y la pausa están en nodos diferentes: reanudar no repite
un intento de validación ni una llamada al modelo ya realizada.

## Pruebas locales sin red

```bash
py -m uv run --project apps/agent --locked pytest apps/agent/tests/test_validation_triage_graph.py apps/agent/tests/test_mcp_identity.py apps/agent/tests/test_validator_validation.py apps/agent/tests/test_validator_agent_flow.py apps/agent/tests/test_triage_classifier.py apps/agent/tests/test_triage_router.py -q
py -m uv run --project apps/mcp-server --locked pytest apps/mcp-server/tests -q
```

Cubren pausas/reanudación, sesión vencida, afirmación falsa de autenticación,
aislamiento de conversaciones, destinos pendientes, ID CLI con guion,
normalización de documento, factores MCP, errores y contratos publicados.
La suite histórica test_graph.py sigue apuntando a disputes.py y ya fallaba antes
de este cambio; no se ha ocultado ni marcado como correcta.

## Límites de esta integración local

- No se ha ejecutado aquí una validación exitosa con factores reales y Groq.
  La consulta nueva de identidad requiere su comprobación en GCP.
- El repositorio BigQuery directo anterior sigue disponible para otros scripts,
  pero no interviene en este flujo.
- Las sesiones y conversaciones de ValidationAgent viven en memoria del proceso.
  Reiniciar el proceso obliga a validarse de nuevo. No reanudar checkpoints de
  otro proceso ni exponer esta CLI como un servidor concurrente de producción.
- Los factores entran en la conversación del validador y pueden existir en sus
  checkpoints en memoria. No habilitar trazas externas con datos personales sin
  definir redacción/retención. El debug final no imprime esos factores.
- El MCP se usa como proceso local de confianza. IdentityValidator limita intentos
  por sesión; no es un control global contra intentos repartidos entre sesiones.
  El transporte HTTP aún necesita autenticación y control de intentos persistente.
- Los mensajes fijos del orquestador están en español; el validador y clasificador
  mantienen los módulos de idioma existentes.

