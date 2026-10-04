# Sandbox bancario v1

Paquete de ingeniería de datos para `hackaton-509923`, región `us-central1`.
**Despliegue y bloqueo simulado validados mediante las salidas de Cloud Shell compartidas el 4 de octubre de 2026.**
Ver [entrega y alcance de la evidencia](../../../docs/sandbox-handoff.md).
Todas las gestiones son simuladas. Los agentes y el escritor MCP quedan a cargo
del equipo de aplicación.

## Archivos

- `001_schema.sql`: dataset y cinco tablas; no reemplaza tablas existentes.
- `verify_schema.sql`: compara columnas/tipos/required con el contrato.
- `create_scenario.sql`: registra escenario, reloj de evaluación y runs de referencia.
- `preflight.sql`: exige escenario único y curated sin cambio de run.
- `cards_effective.sql`: tarjetas y estado efectivo, acotados por escenario/cliente.
- `read_block.sql`, `read_dispute.sql`, `read_handoff.sql`, `read_notification.sql`: verificación persistida por recibo.
- `read_receipts.sql`: historial acotado; no certifica cada acción.
- `audit_contract.sql`, `audit_references.sql`: calidad y referencias.
- `run_audit.sh`: ejecuta controles, guarda evidencia JSON local y falla si hay infracciones.
- `test_reads.py`: emite pruebas BigQuery de lectura con datos sintéticos.

El contrato está en `data/contracts/sandbox/bank_sandbox_v1.json`.
Regenerar DDL/auditoría con `python scripts/verify/sandbox_contract.py`;
verificar consistencia con `python scripts/verify/sandbox_contract.py --check`.
Este paquete tiene despliegue independiente; la sincronización de Dataform no lo ejecuta.

NOT NULL sí se aplica en almacenamiento. Dominios, unicidad y referencias se
validan en el escritor y se auditan después. No declaramos claves no impuestas
que puedan inducir al optimizador a asumir una unicidad inexistente.
Los scripts no garantizan idempotencia concurrente del escritor.

## Primer despliegue: Cloud Shell

Desde el checkout que contenga estos cambios, con identidad de despliegue:

```bash
set -euo pipefail
python3 scripts/verify/sandbox_contract.py --check
bq query --project_id=hackaton-509923 --location=us-central1 \
  --use_legacy_sql=false --maximum_bytes_billed=1000000000 \
  < infra/bigquery/sandbox/001_schema.sql
bq query --project_id=hackaton-509923 --location=us-central1 \
  --use_legacy_sql=false --maximum_bytes_billed=1000000000 \
  < infra/bigquery/sandbox/verify_schema.sql
```

Esperado: jobs DONE, sin ASSERT fallido. Detenerse ante cualquier error.
IF NOT EXISTS no migra una tabla incompatible: diseñar una migración explícita,
sin borrarla para resolver la diferencia. No ejecutar el directorio entero por glob.

## Crear escenario y auditar

Ejecutar administrativamente, una sola creación a la vez. Elegir el reloj según
el caso y la cobertura histórica; la fecha siguiente es solo un ejemplo.

```bash
set -euo pipefail
export SCENARIO_ID="demo-$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}"
bq query --project_id=hackaton-509923 --location=us-central1 \
  --use_legacy_sql=false --maximum_bytes_billed=1000000000 \
  --parameter="scenario_id:STRING:$SCENARIO_ID" \
  --parameter="created_by:STRING:$(gcloud config get-value account)" \
  --parameter="scenario_clock:TIMESTAMP:2026-06-17 12:00:00+00" \
  < infra/bigquery/sandbox/create_scenario.sql
bash infra/bigquery/sandbox/run_audit.sh "$SCENARIO_ID"
```

El auditor escribe en `artifacts/sandbox/<timestamp-aleatorio>/`, ignorado por Git.
Un fallo guarda lo obtenido hasta ese momento y termina con código distinto de cero.
Son archivos locales: para retención compartida, subirlos a un destino de evidencia
con permisos acordados. No hay scheduler ni retención remota provisionados.
El límite de bytes es por trabajo, no un presupuesto acumulado; no elevarlo
automáticamente si una consulta lo supera.

Para probar lecturas sin datos bancarios ni cambios en tablas permanentes:

```bash
set -euo pipefail
python3 infra/bigquery/sandbox/test_reads.py > /tmp/sandbox-read-tests.sql
bq query --project_id=hackaton-509923 --location=us-central1 \
  --use_legacy_sql=false --maximum_bytes_billed=300000000 \
  < /tmp/sandbox-read-tests.sql
```

## Permisos aplicados y reportados por IAM

| Recurso | Rol runtime |
|---|---|
| Proyecto | roles/bigquery.jobUser |
| bank_curated | roles/bigquery.dataViewer |
| bank_sandbox | roles/bigquery.dataViewer |
| Cada tabla card_blocks/disputes/handoffs/notifications | roles/bigquery.dataEditor a nivel tabla |
| scenarios | Solo lectura heredada del dataset |

Identidad runtime separada de despliegue y bank-curation. No conceder Editor
en el proyecto. Revisar permisos heredados y comprobar que runtime no puede
escribir curated ni scenarios. Identidad configurada: 
`bank-mcp@hackaton-509923.iam.gserviceaccount.com`. Los grants aplicados
se versionan en `002_grants.sql`; no se ejecutan automáticamente.
No probar permisos con un borrado real.

Data Editor permite modificar/borrar datos y tablas: **no garantiza append-only**.
El servidor debe exponer acciones cerradas. Una exigencia de inmutabilidad
requiere controles adicionales. No compartir claves JSON; usar identidad
adjunta al servicio o impersonación autorizada.

## Entrega al equipo MCP

Enviar columnas explícitas. `customer_id`, `scenario_id`, `actor_service` y
`created_at` proceden del contexto confiable del servidor. El filtro SQL no
autentica al usuario. El escritor implementa sesión, titularidad, confirmación,
estados, idempotencia y recuperación de timeout; no están implementados aquí.

La identidad de idempotencia incluye tabla/acción + escenario + cliente + clave.
`request_hash` es SHA-256 hexadecimal minúsculo sobre argumentos canónicos;
acordar serialización con MCP. Misma clave y otro hash significa conflicto.
MERGE no garantiza unicidad concurrente: debe probarse con el escritor.

`card_id` corresponde a products.product_id, exclusivamente para Tarjeta Crédito
o Tarjeta Débito. Un bloqueo nuevo requiere baseline Active. Una tarjeta ya
Blocked no necesita evento nuevo; Closed/Suspended se rechazan en v1.
No hay desbloqueo ni transiciones posteriores de disputas en este contrato.
Notificaciones solo admite SIMULATED: un recibo no acredita entrega.
`handoffs.packet` es JSON mínimo sin tokens; MCP define y valida su esquema de negocio.

Las consultas requieren parámetros BigQuery (ver cabecera de cada archivo).
`read_block` exige exactamente una fila válida; resultado vacío no verifica nada.
Las consultas read_dispute/read_handoff/read_notification verifican recibo, contexto y referencias; `read_receipts` es únicamente un historial.

Mantener curated congelado durante la demo. Los run IDs no son snapshots físicos;
preflight detecta cambio de run, no mutaciones manuales dentro del mismo run.
Las consultas filtran versiones discordantes. Si se necesita recurar durante
una demo, usar snapshots dedicados y revisar el contrato. Handoffs comprueba
clientes contra la versión actual: congelar también customers.
Reiniciar significa otro escenario, nunca TRUNCATE. Retención/limpieza quedan
como operación administrativa posterior.

## Validación

Local: contrato y SQL generado consistentes. Según salidas de Cloud Shell
compartidas: DDL y esquema, seis pruebas sintéticas, diagnóstico IAM, prueba
operativa de permisos, bloqueo persistido y auditoría posterior pasaron.
La prueba operativa de denegación cubrió products y scenarios; el resto de
curated se revisó mediante IAM. No equivale a probar las otras tres gestiones.
Pendientes: pruebas de escrituras de disputes/handoffs/notifications y del
escritor MCP (concurrencia, autenticación, reintentos y timeout).

Ejecutar una nueva prueba completa de bloqueo desde el repo:

```bash
bash infra/bigquery/sandbox/smoke_block.sh
```

Crea un escenario nuevo y conserva el bloqueo simulado como evidencia.
Si falla, revisar sus logs; no repetir sin conocer si alcanzó el COMMIT.
El límite de 300 MB para las pruebas sintéticas corrige el agotamiento del
tope anterior de 100 MB por mínimos de facturación de varias sentencias.
El límite es por trabajo y no representa un consumo obligatorio.

Fuentes: [constraints](https://docs.cloud.google.com/bigquery/docs/primary-foreign-keys),
[DML](https://docs.cloud.google.com/bigquery/docs/data-manipulation-language),
[roles](https://docs.cloud.google.com/iam/docs/roles-permissions/bigquery).
