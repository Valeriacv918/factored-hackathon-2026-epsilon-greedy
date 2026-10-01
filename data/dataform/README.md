# customers curated con Dataform

Proyecto: hackaton-509923. Ubicación: us-central1. Estado de entrega: código preparado y pruebas locales del grafo; requiere compilación oficial y ejecución en GCP.

## Comportamiento

- Lee una versión fija de `bank_raw.customers` con time travel y la materializa en una tabla aislada por run_id.
- Conserva original, huella y fecha de la entrada en staging (7 días).
- Normaliza espacios, México → Mexico y Pasaporte → Passport. Vacíos normalizados → NULL.
- Convierte a DATE, TIMESTAMP, NUMERIC, INT64 y BOOL. Las conversiones fallidas son errores, no nulos aceptados.
- Valida obligatorios, longitudes, catálogos, credit_score entero 300–850 e ingreso DECIMAL(12,2), sin redondeo silencioso.
- Colapsa únicamente copias exactamente iguales. Claves con contenidos distintos se rechazan; todavía NO selecciona una versión por last_updated. Esa regla necesita validación semántica adicional.
- Registra observaciones de cronología como WARN. Interpreta timestamps sin zona como UTC de manera explícita, pendiente de confirmar con el origen.
- Escribe cuarentena y métricas ANTES de la assertion que bloquea publicación.
- Reconciliación: entrada = aceptados + rechazados + copias idénticas descartadas. Un registro rechazado puede tener varios motivos, pero cuenta una sola vez.
- Publica todos los registros válidos y actualiza el estado SUCCEEDED en una transacción BigQuery. Si falla, mantiene el contenido anterior. La primera ejecución puede dejar una tabla final vacía si falla después de crear su estructura.

## Política inicial

`maxRejectedRows: 0`: cualquier rechazo bloquea toda la publicación, aunque el candidato y la cuarentena se conservan. No se ha acordado una tasa tolerable. La cuarentena es para diagnosticar, no una autorización para omitir clientes silenciosamente.

Los nulos opcionales se aceptan. No se hacen imputaciones, enriquecimientos ni validaciones de email/teléfono inventadas.

La FK `registration_branch_id → branches` está PENDING y queda registrada en `curation_runs.pending_rules`. Esta versión NO certifica integridad referencial completa. Esta regla pendiente no bloquea el primer modelo: debe cerrarse antes de declarar cumplido el contrato bancario completo.

## DAG

customers_input → customers_typed → customers_classified → customers_candidate

checks → record_quality (auditoría + cuarentena) → publish_gate (assertion) → bank_curated.customers

Las tablas de trabajo y los nombres de acciones incluyen run_id. Cada compilación/ejecución necesita un run_id nuevo. El valor por defecto `preview` sirve para inspeccionar el grafo, pero está bloqueado para ejecutar.

## Preparación en GCP

No ejecutes los archivos JS como scripts sueltos: los ejecuta el compilador de Dataform.

Después de extraer el paquete, `bash prepare.sh` crea los datasets y la cuenta dedicada, asigna los permisos listados abajo y habilita Dataform. Requiere la identidad administradora que usaste para el setup de ingesta. No crea el repositorio ni ejecuta modelos. Si falla un comando, detente y conserva la salida; el script no ignora errores.

1. En BigQuery crea `bank_stage` y `bank_quarantine`, ubicación us-central1. Ya existen bank_raw y bank_ops; crea bank_curated si falta.
2. En Dataform crea el repositorio `bank-transformations` en us-central1.
3. Selecciona una identidad de ejecución dedicada (recomendado: `bank-curation@hackaton-509923.iam.gserviceaccount.com`). No reutilices permisos de escritura en raw.
4. Dale BigQuery Job User en el proyecto, BigQuery Data Viewer en bank_raw y BigQuery Data Editor en bank_stage, bank_quarantine, bank_ops y bank_curated.
5. Configura los permisos de impersonación que Dataform solicite: su agente de servicio necesita Service Account User y Service Account Token Creator SOBRE esa cuenta dedicada. El usuario que lanza la ejecución también necesita Service Account User sobre ella.
6. Crea el workspace `development`. Este paquete reemplaza los archivos del mismo nombre, por lo que debe usarse en ese workspace nuevo.

## Subir y compilar

Sube el ZIP a Cloud Shell y extrae:

```bash
mkdir -p bank-dataform
unzip bank-dataform.zip -d bank-dataform
cd bank-dataform
node tests/test.js
python3 upload_workspace.py
```

El script obtiene un token temporal de tu sesión de gcloud, sube cinco archivos de proyecto, instala las dependencias en el workspace y solicita una compilación con run_id único. No ejecuta consultas ni cambia tablas. Requiere Dataform API habilitada y permisos para editar el workspace, instalar dependencias y crear compilationResults.

Si la compilación dice que faltan dependencias, usa Install packages en el workspace y repite la compilación. El servicio puede requerir instalar @dataform/core antes de compilar el workspace.

## Ejecutar la compilación aprobada

Con la cuenta de ejecución configurada y solo después de revisar la compilación:

```bash
python3 execute_compilation.py
```

Este comando sí inicia el DAG y puede reemplazar bank_curated.customers si pasan los controles. No ejecuta otra vez una compilación marcada como ya enviada por este lanzador. Para otro lote o reintento crea una compilación nueva con upload_workspace.py.

Revisa el enlace de Dataform y el estado de las acciones. No lances dos publicaciones de customers simultáneas: el aislamiento de staging no implementa un bloqueo global de publicación. Conflictos concurrentes pueden abortar la transacción; tampoco hay protección contra que un snapshot anterior se publique después de uno más reciente.

## Verificación

```sql
SELECT run_id,status,input_rows,published_rows,contract_version,pending_rules
FROM `hackaton-509923.bank_ops.curation_runs`
ORDER BY started_at DESC LIMIT 10;

SELECT * FROM `hackaton-509923.bank_ops.curation_results`
WHERE run_id = 'EL_RUN_ID' ORDER BY severity,rule_id;

SELECT COUNT(*) AS rows, COUNT(DISTINCT customer_id) AS customers
FROM `hackaton-509923.bank_curated.customers`;
```

Para el snapshot perfilado esperamos 150000 filas, cero rechazos y cero copias idénticas, pero no se codifica ese número: se calcula a partir de la entrada. El nuevo snapshot puede haber cambiado.

## Auditoría y límites

- curation_runs: contrato completo serializado, versión, timestamp de entrada, estado y conteos.
- curation_results: checks de reconciliación, rechazo, claves y observaciones.
- bank_quarantine.customers_rejected: valores originales y códigos de error; restringir acceso. Retención 30 días; sin logs con datos de clientes.
- Aún no se enlaza autoritativamente con el run_id de ingesta; la versión de fuente está identificada por su timestamp BigQuery y la copia de staging.
- Errores técnicos en acciones intermedias pueden dejar RUNNING: el estado final de la invocación Dataform es la referencia de fallo. Hace falta el cierre de auditoría externo con Workflows para cubrir cancelaciones y cualquier fallo de infraestructura. No hay alertas automáticas todavía.
- Historial de auditoría y cuarentena: 30 días. Staging: 7 días. Ajustar retención si se necesita reproducir después.
- La publicación transaccional cubre customers, no múltiples tablas futuras. No se garantiza una transacción global para todo el DAG.
- Esta versión reconstruye customers por completo. Reutiliza helpers y patrón de acciones; products y transactions requieren sus propios contratos y decisiones de particionado.
- Las consultas y tablas intermedias consumen BigQuery. No se garantiza costo cero; respeta las cuotas del proyecto.

## Verificación local

`node tests/test.js` comprueba contrato, mapeos, errores requeridos, dependencias existentes, bloqueo de publicación después de auditar, aislamiento por ejecución y SQL transaccional. No valida la sintaxis SQL contra BigQuery ni sustituye la compilación de Dataform.
