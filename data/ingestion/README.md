# Ingesta bancaria con contratos — primera versión

Preparado para `hackaton-509923` y `customers`. No se han creado recursos ni ejecutado cargas en GCP desde esta conversación.

## Qué hace

1. Bloquea cargas concurrentes a la misma tabla mediante una precondición de GCS.
2. Lee el contrato en GCS y guarda su contenido, hash y generación.
3. Enumera los archivos de entrada y fija sus generaciones, tamaños y CRC32C en un manifiesto.
4. Valida UTF-8, nombres/orden del encabezado, cantidad de campos y sintaxis CSV. No aplica todavía calidad de negocio.
5. Copia las mismas generaciones validadas a un bucket operativo privado. BigQuery carga esas copias, no un origen que podría haber cambiado.
6. Carga una tabla temporal con todas las columnas STRING/NULLABLE, sin admitir registros erróneos.
7. Compara su número de filas con el obtenido por el lector CSV.
8. Publica mediante una copia atómica que reemplaza `bank_raw.customers`. La tabla anterior se conserva si falla la validación o la carga temporal.
9. Guarda eventos en GCS y BigQuery, además de logs estructurados. El estado final incluye si se llegó a publicar.

## Archivos

- `main.py`: ejecutor parametrizado.
- `validation.py`: contrato y validación estructural.
- `audit.sql`: tabla de eventos y vistas de auditoría.
- `setup.sh`: creación de recursos y despliegue desde Cloud Shell, sin ejecutar la ingesta.
- `test_validation.py`: pruebas de contrato y CSV, sin acceso a GCP.

## Paso 1: subir el paquete a Cloud Shell

Descarga el ZIP, usa el menú de Cloud Shell para subirlo y ejecuta:

```bash
mkdir -p bank-ingestion
unzip bank-ingestion.zip -d bank-ingestion
cd bank-ingestion
python3 -m unittest -v
```

El ZIP contiene los archivos directamente, sin carpeta adicional. Si el nombre descargado cambia, ajusta el comando.

## Paso 2: revisar y desplegar

El contrato existente debe ser `gs://factoredia_hackaton/contracts/customers_v1.json`, con las 27 columnas y opciones que ya validaste.

Revisa `setup.sh` y ejecuta:

```bash
bash setup.sh
```

El script requiere permisos para habilitar APIs, crear cuentas de servicio, asignar IAM, crear datasets, construir imágenes y desplegar Cloud Run Jobs. No asigna Owner al ejecutor. Si un paso devuelve PermissionDenied, conserva el error exacto y corrige solo ese permiso; no continúes ignorando errores.

Cloud Build necesita permisos para ejecutar la construcción y escribir en Artifact Registry. La identidad de build depende de las políticas de tu proyecto; si falla la construcción, identifica esa cuenta en el error. El paquete no concede permisos amplios automáticamente a cuentas de build desconocidas.

Recursos creados:

- Bucket `hackaton-509923-ingestion-ops`, Standard en us-central1, privado. Contiene snapshots temporales y auditoría; no se modifica el bucket original.
- Cuenta `bank-ingestion@hackaton-509923.iam.gserviceaccount.com`.
- Datasets `bank_raw` y `bank_ops`, si no existen.
- Tabla particionada `bank_ops.pipeline_events` y vistas `pipeline_runs` y `quality_results`.
- Repositorio Artifact Registry `bank-pipeline` y job `bank-ingestion-customers`.

El script exige que el bucket original esté en us-central1. Si ya existen los datasets, confirma que también estén allí antes de ejecutar. No cambia su ubicación.

Permisos del ejecutor:

- Storage Object Viewer en el bucket original.
- Storage Object Admin exclusivamente en el bucket operativo.
- BigQuery Job User en el proyecto.
- BigQuery Data Editor únicamente en bank_raw y bank_ops.

## Paso 3: ejecutar una ingesta

Esto reemplaza únicamente `bank_raw.customers` después de validar y reconciliar:

```bash
gcloud run jobs execute bank-ingestion-customers \
  --project=hackaton-509923 --region=us-central1 --wait
```

No hay programación automática ni reintentos automáticos configurados: max-retries=0 facilita diagnosticar la primera ejecución y evita repetir trabajos inválidos. Repetir el job manualmente carga el snapshot seleccionado de nuevo sin añadir duplicados, porque publica con reemplazo. Dentro de una ejecución, los IDs de BigQuery evitan duplicar operaciones ante reintentos de API.

## Paso 4: auditoría

```sql
SELECT *
FROM `hackaton-509923.bank_ops.pipeline_runs`
ORDER BY started_at DESC
LIMIT 20;

SELECT *
FROM `hackaton-509923.bank_ops.quality_results`
ORDER BY event_time DESC
LIMIT 30;
```

Para la entrada de customers que validaste, el conteo de referencia es 150000. El pipeline calcula el conteo cada vez, no lo fija como una constante.

En Cloud Logging, filtra por recurso Cloud Run Job y `jsonPayload.run_id`. En GCS: `gs://hackaton-509923-ingestion-ops/audit/<run_id>/` contiene contrato, manifiesto, validación por archivo y eventos. Si BigQuery falla, los eventos ya escritos en GCS siguen disponibles. Los eventos no incluyen valores de clientes.

Los logs propios son sanitizados; los detalles de los jobs de BigQuery pueden incluir valores rechazados por el parser. Restringe el acceso de diagnóstico al equipo de ingeniería.

## Fallos y recuperación

- Contrato/CSV inválido: código de salida distinto de cero, evento FAILED y tabla raw anterior conservada.
- Auditoría indisponible antes de publicar: se bloquea el pipeline. Si el fallo sucede después de la copia final, GCS/logs registran `published: true`; comprueba el job de publicación antes de decidir un reintento.
- Cancelación, OOM o timeout: puede quedar un bloqueo bajo `locks/` y una ejecución sin evento final. Confirma en Cloud Run que ya no está activa, verifica los IDs de BigQuery y elimina SOLO ese objeto de bloqueo para reintentar. No se recupera automáticamente un bloqueo abandonado.
- No ejecutes cargas manuales sobre la misma tabla durante el job: el bloqueo coordina este pipeline, no herramientas externas.
- La tabla temporal expira a los dos días y se elimina al terminar. Si el proceso muere en el intervalo después de quitar la caducidad y antes del finally, limpia esa tabla stage manualmente.

## Reutilizar para products y transactions

Primero crea sus contratos a partir de sus diccionarios y encabezados; no se incluyen esquemas inventados.

La misma imagen permite jobs independientes con estas variables:

| Variable | customers | transactions (cuando exista contrato) |
|---|---|---|
| SOURCE_URI | gs://factoredia_hackaton/dataset_v1_raw/data/customers.csv | gs://factoredia_hackaton/dataset_v1_raw/data/transactions/ |
| CONTRACT_URI | gs://factoredia_hackaton/contracts/customers_v1.json | URI real de su contrato |
| DESTINATION_TABLE | hackaton-509923.bank_raw.customers | hackaton-509923.bank_raw.transactions |

Una URI terminada en `/` selecciona recursivamente TODOS los objetos de ese prefijo. Solo se admiten CSV sin comprimir y todos deben cumplir el mismo contrato. Cada archivo debe tener encabezado. Un archivo sin registros es admisible dentro de un lote, pero el lote completo debe tener al menos uno.

Esta versión procesa archivos secuencialmente con memoria acotada; las 1097 particiones pueden requerir ajustar el timeout tras medir. Cada campo CSV tiene un límite de validación de 10 MiB. Reutilizable no significa paralelismo ilimitado. Si el tiempo es insuficiente, separar validación por archivos y orquestar con Workflows/Cloud Run Tasks es el siguiente paso.

## Costo, retención y límites

- Usa cargas por lotes a BigQuery para datos y eventos, sin streaming.
- Cloud Run Jobs se ejecuta solo al invocarlo. Construcción, imágenes, almacenamiento y operaciones pueden generar consumo; no se garantiza costo cero.
- Los snapshots añaden temporalmente una copia de los archivos. Su eliminación por lifecycle comienza a partir de dos días y es asíncrona.
- Auditoría: 30 días en GCS y particiones BigQuery. Ajusta la retención si debe sobrevivir al hackatón. El bucket operativo tiene soft delete desactivado; los originales permanecen en el bucket original.
- No se configuran aún alertas, dashboards, Workflows, Dataform ni validación de negocio. Son la siguiente etapa; esta entrega resuelve la ingesta estructural.
- Reproducibilidad: se registran versiones de entrada y contrato, y se fijan versiones de librerías. La imagen base usa un tag; para despliegue estable conserva el digest de la imagen construida.

## Verificación local

Las pruebas cubren nulos permitidos, valores decimales conservados como texto, campos multilínea, encabezado desordenado, columnas faltantes/adicionales, comillas rotas, bytes NUL, archivos vacíos y contrato duplicado. También simulan los clientes cloud para comprobar publicación exitosa, bloqueo de publicación por contrato o conteo inválido, bloqueo de concurrencia y reutilización de jobs ante conflictos de API. Las pruebas no sustituyen la primera ejecución de integración en tu proyecto GCP.
