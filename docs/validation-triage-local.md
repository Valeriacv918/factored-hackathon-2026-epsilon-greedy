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
- MCP_SERVER_COMMAND=apps/mcp-server/.venv/Scripts/bank-mcp.exe (Windows, entornos ya preparados).
- SESSION_SIGNING_KEY: secreto local de al menos 32 caracteres compartido por las instancias MCP.
- DEV_SESSIONS vacío para esta prueba; las sesiones se crean al validar.
- ADC impersonando bank-mcp en Windows.
- SCENARIO_NOW sigue siendo el reloj de transacciones; autenticación y TTL usan
  la hora real, para no expirar sesiones según datos históricos.

DEV_SESSIONS no salta la validación de este flujo. El argumento --session se
conserva por compatibilidad con legacy; el validador crea una sesión aleatoria
independiente para cada conversación.

## Recorrido esperado

1. Saludar o describir el problema. Ese primer mensaje no se clasifica (puede traer
   datos de identidad). Aparece un FORMULARIO con tres campos: número de documento,
   fecha de nacimiento y número de un producto. No usar product_id PRD-... como número
   de producto: ese campo es products.product_number.
2. Los tres campos van directo a IdentityValidator, sin LLM: ningún modelo ve los
   datos de identidad. Su repositorio de confianza invoca la herramienta MCP
   verify_identity; el agente no abre BigQuery. Si no coinciden, el formulario vuelve
   con los intentos restantes, sin decir qué dato falló.
3. MCP compara los tres factores y la titularidad con parámetros de BigQuery.
   Usa exclusivamente document_number; customer_id se obtiene de la coincidencia.
   Una discordancia devuelve status=failed sin identificar qué factor falló.
4. El servidor emite un token firmado y expires_at. McpIdentityChecker entrega
   el resultado al validador. ValidatorSessions resuelve ese token para las
   consultas posteriores; el token no se pasa al LLM ni al estado del grafo.
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
La verificación ocurre después de la pausa del formulario: reanudar no repite un
intento de validación. La clasificación y su pausa están en nodos diferentes: reanudar
no repite una llamada al modelo ya realizada.

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

- Prueba real del 4 de octubre: documento + fecha + producto -> VERIFIED;
  'Me cobraron dos veces una compra.' -> charge_error / FIND_TRANSACTION /
  ready_for_transaction_search. Se comprobó list_cards con el token de esa sesión.
- El grafo general disputes.py aún falla al compilar por una referencia al nodo
  validator_agent inexistente; cuatro pruebas de test_mcp_services.py detectan esto.
- Las sesiones y conversaciones de ValidationAgent viven en memoria del proceso.
  Reiniciar el proceso obliga a validarse de nuevo. No reanudar checkpoints de
  otro proceso ni exponer esta CLI como un servidor concurrente de producción.
- Los factores entran en la conversación del validador y pueden existir en sus
  checkpoints en memoria. No habilitar trazas externas con datos personales sin
  definir redacción/retención. El debug final no imprime esos factores.
- El MCP se usa como proceso local de confianza. El servidor MCP limita intentos por documento en memoria; no es un control global contra intentos repartidos entre sesiones.
  El transporte HTTP aún necesita autenticación y control de intentos persistente.
- Los mensajes fijos del orquestador están en español; el validador y clasificador
  mantienen los módulos de idioma existentes.


## Prueba aislada de charge_error

Con los entornos y credenciales preparados, desde Git Bash en Windows:

```bash
apps/agent/.venv/Scripts/python.exe scripts/run_disputes.py --flow charge-error --debug
```

Este modo extiende el grafo separado; no ejecuta disputes.py. El modo
validation-triage mantiene su comportamiento anterior.

1. Identificarse con documento, fecha de nacimiento y número de producto.
2. Indicar el problema: "Me cobraron dos veces una compra".
3. Aportar fecha, monto y comercio si se solicitan. Las fechas relativas se
   interpretan contra SCENARIO_NOW.
4. Elegir el movimiento mostrado, incluso cuando solo hay una coincidencia.
5. Pending, Reversed y Declined aplican EXP-002/003/006. El nodo charge_save
   guarda el resultado con save_charge_explanation y solo termina en explained
   después de verificar su lectura. No se pide una confirmación adicional.
6. Approved termina directamente en approved, sin explicación ni escritura.
7. Un puntaje superior al umbral termina en ready_for_fraud; no ejecuta fraude.

## Persistencia de explicaciones

Migración: infra/bigquery/sandbox/003_agent_results.sql. Crea
bank_sandbox.agent_results y concede dataEditor sobre esa tabla a bank-mcp.
No modifica las tablas curated ni las otras tablas sandbox.

MCP toma customer_id del token firmado, verifica titularidad y estado de la
transacción en SQL y guarda la regla/texto fijo del servidor. No acepta un texto
libre ni un cliente elegido por el LLM. El resultado incluye el run de curated.
La clave estable se deriva de versión, conversación, cliente, transacción y
estado. Un job_id determinista evita ejecutar dos inserciones concurrentes del
mismo resultado; MERGE permite repetir después de la retención del job. La
lectura posterior debe devolver exactamente una fila coincidente.

Si el estado cambió antes del primer guardado, no se inserta una explicación
incompatible. Si el guardado no puede verificarse, el flujo no reporta éxito.
Los registros son SIMULATED; no representan reembolsos ni disputas abiertas.

Pruebas: test_charge_test_graph.py y test_charge_results.py cubren rutas,
titularidad, sesión, recibos y reintentos.

## Fechas locales en búsquedas MCP

find_transactions resuelve país, estado y ciudad del cliente autenticado desde
bank_curated.customers. services/timezones.py mantiene las 16 ubicaciones
observadas y su zona IANA; una ubicación desconocida produce error explícito.

La fecha exacta y los rangos se interpretan como días locales completos. BigQuery
convierte ambas medianoches locales a UTC para filtrar transaction_date, teniendo
en cuenta el horario histórico. local_date contiene solo YYYY-MM-DD y se muestra
en la selección. date conserva el timestamp original para trazabilidad.

Verificación real: la búsqueda 2024-11-19, 416.73 encontró una coincidencia
sin comercio para el cliente de prueba, en America/Mexico_City.

## Ruta de fraude en el grafo separado

Ejecutar desde la raíz:

```bash
apps/agent/.venv/Scripts/python.exe scripts/run_disputes.py --flow fraud --debug
```

Incluye validación, triage, la búsqueda compartida, charge_error y la entrada
fraud_agent.run de nodes/fraud_agent. No modifica disputes.py ni usa una copia
del agente. La clase independiente FraudAgent conserva su API de repositorios.

- not_me lleva a fraude, incluso sin fraud_score. charge_error con score alto
  también lleva a fraude. El resto conserva la ruta de explicación probada.
- La selección de un movimiento no confirma un bloqueo ni una disputa.
- Cada acción pide su confirmación y se verifica con read_block/read_dispute.
- "Otro cargo" vuelve a la búsqueda; conserva recibos y limpia producto/filtros
  anteriores. Se aplican los límites del agente de fraude.
- Una solicitud de escalamiento termina en human_required con reason/queue/priority;
  no se invoca todavía al agente de escalamiento ni se crea un ticket.
- Las cuentas sin tarjeta no pueden suspenderse con las herramientas MCP actuales:
  esta limitación produce revisión humana, nunca un bloqueo ficticio.

Se requiere SANDBOX_SCENARIO_ID configurado y vigente, alineado con SCENARIO_NOW.
La CLI avisa que las acciones son SIMULATED. .env permanece fuera de Git.
Las pruebas sin red están en test_fraud_test_graph.py y test_fraud_agent.py.


## Recorrido completo (grafo separado)

Desde Git Bash en la raíz del repositorio, con los entornos y ADC ya configurados:

```bash
apps/agent/.venv/Scripts/python.exe scripts/run_disputes.py --flow full --debug
```

El modo `full` conecta validación por documento, triage, emergencia, búsqueda de
transacciones, error de cargo, fraude y escalamiento. Los modos anteriores siguen
disponibles para pruebas aisladas; el modo predeterminado sigue siendo
`validation-triage`.

- Emergencia: selección y confirmación de tarjeta, bloqueo verificado y búsqueda
  de cargos no reconocidos. Si no hay cargos, deriva para reposición.
- Error de cargo: Pending, Reversed o Declined guarda la explicación en sandbox
  y termina; Approved termina sin guardar una explicación.
- Fraude: conserva las confirmaciones, las reglas y los recibos del agente.
- Atención humana: crea y verifica el ticket y la notificación simulada.
- La CLI muestra solo los últimos cuatro dígitos de las tarjetas. El número de
  opción distingue tarjetas con la misma terminación. Si falta last4, muestra
  “Tarjeta sin terminación disponible”; nunca usa el ID como alternativa.
- El resumen de depuración muestra la cantidad de tarjetas bloqueadas. Los IDs
  internos permanecen en el estado del grafo y en las llamadas MCP para operar
  sobre el producto correcto; este cambio no anonimiza el estado interno.

Los bloqueos, disputas y notificaciones son SIMULATED en sandbox. Un bloqueo de
una prueba previa permanece efectivo dentro del escenario: usar /new reinicia
la conversación, no borra los efectos persistidos. Las pruebas locales usan
servicios simulados; el recorrido con LLM y MCP reales se verifica con el comando
anterior.
