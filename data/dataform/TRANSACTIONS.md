# Transactions curated v1

Aplicar sobre ~/bank-dataform. Requiere customers y products publicados.

python3 upload_workspace.py
# Solo si devuelve COMPILED:
python3 execute_compilation.py --table transactions

Politica:
- Normaliza espacios y blancos; Mexico y México se publican como Mexico.
- Convierte tipos; valida requeridos, longitudes, dominios del diccionario,
  precision/escala monetaria y coordenadas, rangos de fraude y coordenadas.
- Rechaza todos los transaction_id repetidos y bloquea la publicacion.
- Publicacion parcial solo por product_id.quarantined_parent: producto ausente
  de curated, presente en cuarentena del run de products publicado al inicio.
- Cliente inexistente, producto sin explicacion, titular diferente y otros errores
  bloquean. No se elige un ganador ni se inventan referencias.
- No se comprueba titular contra productos en cuarentena: esas transacciones
  permanecen rechazadas y nunca llegan a curated.
- No hay limite numerico de rechazos aprobado. Los 130 del perfil son expectativa.
- Nulos opcionales se conservan; no se imputan importes ni coordenadas.
- Fechas se conservan. Diferencia horaria es hipotesis, no causa confirmada.
  No se cambia process_date ni se aplica offset a transaction_date.
  TIMESTAMP sin zona explicita usa interpretacion UTC del parser.
- Fecha de proceso anterior, coordenadas incompletas, importes negativos y moneda
  distinta a producto generan WARN. No bloquean ni corrigen datos.
- branch_id FK, diccionario de monedas y zona horaria siguen pendientes.

Publicacion: reemplazo completo transaccional, particion por process_date,
cluster product_id/customer_id. No es incremental. Consultar usando process_date
reduce particiones leidas; no se configura require_partition_filter.
No ejecutar runs concurrentes ni todas las etiquetas a la vez.
Este paquete no vuelve a ejecutar customers/products; congela su version publicada.

Auditoria: curation_runs, curation_results y curation_references (referencias y snapshot).
Cuarentena: transactions_rejected con fila original y motivos. Retencion 30 dias
para auditoria/cuarentena; staging 7 dias. Restringir acceso a raw_json segun permisos.
La puerta comprueba conteo persistido de cuarentena antes de publicar.
Fallos intermedios pueden dejar RUNNING; revisar tambien Dataform.

Esperado si raw/referencias no cambiaron: 4425008 entrada, 4424878 publicados,
130 rechazados, SUCCEEDED_WITH_REJECTIONS. Estos valores no estan codificados.

Pruebas locales validan generacion del grafo y reglas. No sustituyen compilacion
Dataform ni ejecucion SQL BigQuery. Ejecutar verify_transactions.sql al terminar.
