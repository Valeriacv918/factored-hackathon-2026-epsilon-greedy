# MCP y sandbox bancario

Cómo usa el servidor MCP (`apps/mcp-server`) el sandbox de BigQuery para los
bloqueos de tarjeta, las disputas, las derivaciones y las notificaciones simuladas,
y por qué. Complementa la
[entrega de ingeniería de datos](sandbox-handoff.md), que describe las tablas,
los permisos y las consultas de origen.

## 1. Qué es un escenario

Un escenario es una fila de `bank_sandbox.scenarios`: una sesión de demo con nombre.
Guarda:

- `scenario_id`: el identificador, p. ej. `demo-20261004T120000Z-123`.
- `products_run_id` y `transactions_run_id`: la versión de los datos curados sobre la
  que se construyó.
- `scenario_clock`: el "hoy" simulado de la demo (los datos históricos terminan en
  junio de 2026).

Todas las tablas del sandbox (`card_blocks`, `disputes`, `handoffs`,
`notifications`) tienen `scenario_id STRING NOT NULL`, y las consultas de lectura y
verificación solo consideran filas del mismo escenario. Reiniciar la demo significa
crear un escenario nuevo; nunca se borran filas, que quedan como evidencia.

## 2. Configuración e identidad

1. Un administrador crea el escenario con `infra/bigquery/sandbox/create_scenario.sql`
   (`bank-mcp` solo puede leer `scenarios`).
2. Se configura `SANDBOX_SCENARIO_ID`: en `.env` en local y con
   `--set-env-vars SANDBOX_SCENARIO_ID=...` en Cloud Run. No es un secreto. Cambiarlo
   en Cloud Run crea una revisión nueva y reinicia los contadores en memoria
   (intentos de login, límite de peticiones).
3. `SCENARIO_NOW` del agente debe ser igual al `scenario_clock` del escenario.
4. El servidor ejecuta como `bank-mcp@hackaton-509923.iam.gserviceaccount.com`:
   - En local, mediante ADC con impersonación:
     `gcloud auth application-default login --impersonate-service-account=bank-mcp@hackaton-509923.iam.gserviceaccount.com`.
     Requiere el rol Token Creator sobre la cuenta. Para comprobarlo, ejecutar
     `SELECT SESSION_USER()` con esas credenciales; debe devolver la cuenta `bank-mcp`.
   - En Cloud Run, como cuenta de servicio adjunta (`--service-account`).
   - Nunca con claves JSON.

Sin `SANDBOX_SCENARIO_ID`, las herramientas de escritura y `dispute_context`
responden `Sandbox scenario not configured.` y las tarjetas muestran su estado
curado. Al arrancar, el servidor registra en el log en cuál de los dos modos está.

## 3. Qué lee y escribe cada herramienta

El LLM nunca consulta la base de datos. El código del agente llama a las
herramientas MCP; el modelo solo interpreta el mensaje del cliente y redacta el
resumen para el empleado a partir de hechos ya verificados.

| Herramienta | Fuente |
|---|---|
| `verify_identity` | Curado (`customers`, `products`) |
| `find_transactions` | Curado; con escenario usa `scenario_clock` como fecha de referencia |
| `list_cards`, `get_card` | Curado + bloqueos del escenario (estado efectivo) |
| `block_card` | Escribe en `bank_sandbox.card_blocks` |
| `read_block` | Sandbox, comprobado contra curado |
| `file_dispute` | Escribe en `bank_sandbox.disputes` |
| `read_dispute` | Sandbox, comprobado contra curado |
| `dispute_context` | Disputas del escenario + quejas curadas |
| `create_handoff` | Escribe en `bank_sandbox.handoffs`; comprueba las referencias contra curado y sandbox |
| `read_handoff` | Sandbox, comprobado contra `customers` curado |
| `notify_employee` | Escribe en `bank_sandbox.notifications` |
| `read_notification` | Sandbox, comprobado contra la derivación |

Estado efectivo: una tarjeta `Active` en curado con un bloqueo en el escenario se
devuelve como `Blocked`. Curado nunca cambia.

El cliente se identifica con su `document_number` (cédula, CURP, DNI); el token de
sesión lleva el `customer_id` interno, que es el que filtra todas las herramientas
del sandbox.

## 4. Por qué combinar curado y sandbox

**Ventajas**

- **Funcionan los controles de seguridad del agente.** Antes de bloquear, el agente
  lee la tarjeta y solo pide confirmación si no está `Blocked`; `dispute_context`
  evita disputar dos veces el mismo cargo. Sin leer el sandbox, el agente repetiría
  acciones.
- **Cada acción se verifica.** El agente solo informa de un bloqueo o caso después
  de que `read_block`/`read_dispute` lo encuentra persistido.
- **Curado no se toca.** `bank-mcp` no puede escribir en `bank_curated`; reiniciar es
  crear otro escenario.
- **Es auditable.** Cada cambio es una fila con identidad (`actor_service`) y hora.

**Inconvenientes**

- **Curado debe quedar congelado durante la demo.** Las filas del sandbox están
  ligadas a una versión curada. Si se vuelve a curar, cada escritura lo detecta y la
  rechaza (`Curated data changed...`); la solución es crear otro escenario.
- **Solo parte de los datos refleja las acciones.** Las tarjetas muestran el
  bloqueo, pero una transacción disputada sigue figurando como `Approved` en
  `find_transactions`.
- **Un escenario compartido.** Todas las conversaciones usan el mismo escenario: un
  bloqueo hecho en una se ve en otra si es el mismo cliente.
- **El aislamiento entre clientes depende solo del SQL.** IAM no separa filas por
  cliente; cada consulta filtra por el cliente del token de sesión.
- **Latencia.** Una escritura son unos cuatro trabajos de BigQuery (escenario,
  inserción, recibo, verificación).
- **Simulado y real se mezclan en el texto.** El resumen dice "tarjeta bloqueada"
  aunque el bloqueo sea `SIMULATED`.

## 5. Escrituras

- **Alcance de idempotencia:** tabla + escenario + cliente + `idempotency_key`. El
  agente usa como clave `conversación:acción:objetivo`.
- **`request_hash`:** SHA-256 hexadecimal en minúsculas de
  `{"action": ..., <argumentos>}` serializado con claves ordenadas y sin espacios
  (`services/sandbox.request_hash`). Por ejemplo, `block_card` sobre `PRD-1` hashea
  `{"action":"block_card","card_id":"PRD-1"}`.
- **Reintentos:** misma clave y mismo hash devuelven el recibo original; misma clave
  con otros argumentos es un error.
- **Elegibilidad:**
  - Bloqueo: tarjeta del cliente, de crédito o débito, `Active` en la versión del
    escenario. Una tarjeta ya bloqueada en el escenario devuelve ese bloqueo.
  - Disputa: transacción del cliente, `Approved`, en la versión del escenario. Una
    transacción con una disputa `OPEN` en el escenario devuelve ese caso.
  - Derivación: un ticket por clave; ver la sección 7.
  - Notificación: ticket del cliente en el escenario. Un ticket ya notificado
    devuelve esa notificación.
- **Errores genéricos:** `Card cannot be blocked.` / `Transaction cannot be disputed.` /
  `Ticket not found.` sin distinguir si no existe, es de otro cliente o no es elegible.
- **Verificación:** `read_*` exige exactamente una fila consistente con el escenario
  y la versión curada; si no, `Receipt not verified.`
- **Concurrencia:** la inserción condicional (`INSERT ... SELECT ... NOT EXISTS`) no
  garantiza unicidad ante llamadas simultáneas con la misma clave; BigQuery no
  impone claves únicas.

## 6. `dispute_context`

- `existing_case_id`: disputa `OPEN` del cliente sobre esa transacción en el
  escenario, si existe. Sale del sandbox porque las quejas curadas no tienen
  `transaction_id`.
- `recent_dispute_count`: solo quejas curadas (`bank_curated.complaints`) del cliente
  con `subcategory` en `Cargo no reconocido` o `Cobro indebido`, cualquier
  `case_type` y estado, y `creation_date` en los 90 días anteriores a
  `scenario_clock` (`DISPUTE_HISTORY_DAYS`).
- Consecuencia de esa decisión: las disputas registradas durante la demo no cuentan
  para la regla DSP-011 (dos o más disputas recientes escalan). Los duplicados sobre
  el mismo cargo siguen bloqueados por `existing_case_id`. Incluirlas sería sumar las
  disputas del escenario sin filtro de fecha (su `created_at` es la hora real, no la
  del escenario).
- Las fechas de las quejas tienen una diferencia horaria no confirmada (ver
  `data/dataform/COMPLAINTS.md`): una queja en el límite de la ventana puede caer de
  cualquiera de los dos lados.

## 7. Derivaciones y notificaciones

Una escalación del agente termina con dos escrituras, cada una verificada con su
lectura: `create_handoff` abre el ticket para un empleado y `notify_employee` avisa
de que está esperando. Solo después el cliente ve "Caso enviado a atención humana".

- **Paquete:** `create_handoff` recibe el paquete que arma el nodo de escalación
  (`reason`, `queue`, `priority`, `language`, `customer_quote`, ids de transacciones,
  casos y tarjetas, `not_done`, `next_steps`, `policy_version`, reglas, `narrative`,
  `narrative_source`, `claim_issues`). El esquema es estricto (`HandoffPacket` en
  `services/mapping.py`): un campo desconocido, un id mal formado o un texto
  demasiado largo (`customer_quote` 1000, `narrative` 2000 caracteres) se rechazan,
  así nunca se guardan tokens ni datos extra. Se guarda en `packet` (JSON).
- **Referencias:** cada transacción, caso y tarjeta citados debe ser del cliente del
  token (transacciones y tarjetas en la versión curada del escenario, casos en las
  disputas del escenario); si no, `Handoff cites items that are not the customer's.`
  sin escribir nada. Se comprueba la titularidad, no el estado: una tarjeta que ya
  estaba `Blocked` en curado no tiene bloqueo en el sandbox.
- **`suspended_accounts` siempre vacío:** no existe la suspensión de cuentas.
- **Idempotencia:** el `request_hash` cubre el paquete completo. El agente arma el
  paquete una vez y lo guarda en el checkpoint, así que un reintento envía el mismo.
- **Una notificación por ticket**, como un bloqueo por tarjeta.
- **Nadie recibe nada.** `status` es siempre `SIMULATED` y la tabla no tiene
  destinatario ni canal: el recibo prueba que el aviso quedó registrado, no que se
  entregó. Un destinatario real requiere cambiar el contrato de datos.

## 8. Relojes

`scenario_clock` es la referencia del servidor: ancla `find_transactions` y la
ventana de `recent_dispute_count`. El agente usa `SCENARIO_NOW` para su política
(antigüedad del cargo). Si difieren, el servidor registra un aviso y usa
`scenario_clock`; conviene que coincidan.

## 9. Fuera de alcance

- Suspensión de cuentas (`list_accounts`, `get_account`,
  `suspend_account_transactions`): no hay tabla ni permisos en el sandbox, y
  `find_transactions` no devuelve `account_id`, así que un fraude sobre una cuenta
  escala (`no_blockable_card`).
- Desbloqueo y cambios de estado de disputas: no existen en el contrato 1.0.0.
