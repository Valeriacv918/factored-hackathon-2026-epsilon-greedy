# Entrega de ingeniería de datos: sandbox bancario

Fecha de referencia: 4 de octubre de 2026 (America/Bogota).

## Estado y alcance

La ingeniería de datos entrega esquema, contratos, consultas de lectura,
auditorías y prueba de bloqueo simulado. No implementa agentes ni herramientas MCP.
La evidencia GCP descrita aquí procede de las salidas compartidas por el usuario
desde Cloud Shell; no se ha recuperado ni certificado un snapshot actual de GCP.

| Control | Resultado reportado |
|---|---|
| Creación y comprobación del esquema | Pasó |
| Seis comprobaciones de lecturas con fixtures temporales | Pasaron tras corregir alias y límite de bytes |
| IAM: lectura/escritura en 12 tablas | Coincide con lo esperado |
| Operaciones como bank-mcp | Lectura de products; UPDATE de cero filas permitido en las cuatro tablas de gestiones |
| Denegación operativa | UPDATE de cero filas rechazado en curated.products y sandbox.scenarios |
| Bloqueo simulado | Insertado, estado efectivo Blocked y recibo verificado después del commit |
| Conservación del producto original | Hash de la fila idéntico antes/después; estado Active |
| Auditoría posterior | PASSED, ejecutada por separado |

No se probó una escritura real de disputes, handoffs o notifications.
La prueba de bloqueo no certifica concurrencia, reintentos, autorización de usuarios
ni integración con un servicio MCP desplegado. IAM no aísla filas por cliente.

## Configuración para el responsable de MCP

Implementación en el servidor MCP (bloqueos y disputas): [mcp-sandbox.md](mcp-sandbox.md).

| Concepto | Valor |
|---|---|
| Proyecto / región | hackaton-509923 / us-central1 |
| Cuenta runtime | bank-mcp@hackaton-509923.iam.gserviceaccount.com |
| Lectura original | bank_curated |
| Gestiones simuladas | bank_sandbox |
| Contrato | [bank_sandbox_v1.json](../data/contracts/sandbox/bank_sandbox_v1.json), versión 1.0.0 |
| Guía operativa | [README sandbox](../infra/bigquery/sandbox/README.md) |
| DDL | [001_schema.sql](../infra/bigquery/sandbox/001_schema.sql) |
| Grants de datos | [002_grants.sql](../infra/bigquery/sandbox/002_grants.sql) |

Mantener configuración separada de curated y sandbox; no reemplazar el dataset
global del gateway actual. Adjuntar la cuenta runtime al servicio MCP cuando el
equipo lo despliegue. No distribuir claves JSON.
La cuenta también recibió roles/bigquery.jobUser en el proyecto.
El usuario operador recibió TokenCreator sobre esa cuenta para las pruebas;
no implica autorización para todos los compañeros. No hay que conceder ese
rol al servicio que ya ejecuta con su cuenta adjunta.

La cuenta tiene Viewer sobre ambos datasets y Editor en las cuatro tablas de
gestiones. Editor permite modificar y borrar; no es un registro inmutable.
El registro scenarios queda de solo lectura para runtime. Los grants no se
aplican simplemente al hacer push: requieren despliegue administrativo explícito.

## Tablas y operaciones

| Operación | Tabla | Identificador | Consulta para verificar |
|---|---|---|---|
| Bloquear tarjeta | card_blocks | block_id | read_block.sql |
| Registrar disputa | disputes | case_id | read_dispute.sql |
| Registrar derivación | handoffs | ticket_id | read_handoff.sql |
| Simular notificación | notifications | delivery_id | read_notification.sql |

Los archivos SQL están en infra/bigquery/sandbox; sus cabeceras enumeran parámetros.
cards_effective.sql recibe scenario_id/customer_id y devuelve tarjetas con
baseline_status y effective_status. read_receipts.sql es un historial acotado.

Las consultas read_* individuales devuelven id, contexto y verified.
Exigir exactamente una fila con verified=true y comprobar los identificadores.
Para notificaciones, verified acredita el registro SIMULATED, no entrega real.

El cliente y escenario proceden del contexto autenticado del servidor, no del
modelo. El escritor valida titularidad, confirmación, tipo tarjeta y estados.
Los campos comunes y tipos exactos están en el contrato. Insertar siempre con
lista explícita de columnas; no usar INSERT VALUES sin esa lista.

card_id corresponde a products.product_id, de tipo Tarjeta Crédito/Tarjeta Débito.
Un bloqueo nuevo requiere baseline Active. Una tarjeta ya Blocked no requiere
otro evento; Closed/Suspended no se convierten a Blocked.
No hay desbloqueo ni transiciones posteriores de disputas en v1.

Idempotencia: ámbito tabla/acción + escenario + cliente + clave. Reutilizar una
clave con argumentos distintos es conflicto. request_hash es SHA-256 hexadecimal
minúsculo de argumentos canónicos. El servidor MCP ya fijó la serialización:
`{"action": ..., <argumentos>}` con claves ordenadas y sin espacios
(`services/sandbox.request_hash`, ver [mcp-sandbox.md](mcp-sandbox.md)).
El hash usado por el smoke test identifica exclusivamente esa prueba; no impone
un algoritmo de serialización de producción. MERGE no garantiza unicidad concurrente.

## Escenarios y versiones de referencia

El administrador crea escenarios con create_scenario.sql. El runtime los consulta.
Ejecutar preflight antes de habilitar uno. Mantener products, transactions y
customers sin recurar durante la demo. Los run IDs guardados detectan cambios de
versión de products/transactions; no conservan snapshots ni detectan una edición
manual dentro del mismo run. Si cambia la referencia, iniciar otro escenario.

El reloj 2026-06-17 12:00:00+00 fue el ejemplo del smoke test. Ajustar el reloj
de un caso de negocio a su cobertura histórica. La hora real created_at es del
servidor. Reiniciar significa otro escenario, nunca borrar la evidencia compartida.

## Evidencia recibida

- Escenario: smoke-d2f3f3a1195a4fd696b283126c745039
- Bloqueo: smoke-eba070dd-50b4-440b-ab68-fd9f65fd89ae
- Producto: PRD-000F8NZ1NOK4
- Resultado: PASSED; curated Active; efectivo Blocked; SIMULATED.
- Auditoría final, ruta en Cloud Shell:

```text
/home/jtautivace/bank-sandbox-setup.dAZXkx/bank-sandbox-v1/artifacts/sandbox/20261004T050101Z-27656
```

Los JSON originales siguen en Cloud Shell; no forman parte del repo.
La primera ejecución mostró el bloqueo exitoso pero no el mensaje final de
auditoría. No se conoce la causa de esa ausencia. Se ejecutó solo la auditoría
sobre el mismo escenario y devolvió PASSED. No se insertó otro bloqueo.

## Reproducir y conservar evidencia

Desde un checkout con estas modificaciones:

```bash
python3 scripts/verify/sandbox_contract.py --check
bash infra/bigquery/sandbox/smoke_block.sh
```

El smoke crea un escenario nuevo y conserva el evento. Usa identidad
administrativa para crear el escenario y bank-mcp para el bloqueo.
El operador necesita impersonación. Reutiliza las consultas de lectura del repo.
Máximo por trabajo: 1 GB; no es presupuesto acumulado ni gasto garantizado.
Para pruebas sintéticas, seguir README: límite corregido a 300 MB.

Para reauditar el escenario existente sin insertar otra gestión:

```bash
bash infra/bigquery/sandbox/run_audit.sh smoke-d2f3f3a1195a4fd696b283126c745039
```

El auditor guarda JSON/logs bajo artifacts/sandbox (ignorado por Git).
La versión local ahora imprime la ruta antes de ejecutar y muestra errores de
BigQuery si algún paso falla. Esta mejora diagnóstica y la adaptación del smoke
a rutas del repo se validan localmente; aún no se han vuelto a ejecutar en GCP.

## Pendientes y responsabilidades

- Ingeniería de datos: retención compartida de evidencia, política de limpieza
  y pruebas equivalentes de las otras tres gestiones.
- Equipo MCP: hecho para bloqueos, disputas, derivaciones y notificaciones
  ([mcp-sandbox.md](mcp-sandbox.md)): consultas y escrituras conectadas, cliente y
  escenario desde el contexto del servidor, estados permitidos, esquema del paquete
  de derivación e idempotencia por clave, con prueba real y auditoría PASSED
  (escenario `demo-20261004T211122Z-10525`). Pendiente: recuperación de timeout más allá de reintentar
  con la misma clave, y unicidad ante llamadas concurrentes. Las confirmaciones
  al cliente las hace el agente antes de llamar a la herramienta.
- Validación conjunta: dos clientes/escenarios concurrentes, claves repetidas y
  conflictos, fallos de red y tratamiento de ausencia de resultados.
- Publicación: integrado en `main` (PR #13). No confundir este paquete con despliegue
  automático de Dataform o de la aplicación.
