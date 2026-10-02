# Complaints curated v1

Aplicar sobre ~/bank-dataform con customers y products ya publicados.
python3 upload_workspace.py
# Despues de COMPILED:
python3 execute_compilation.py --table complaints
# Al terminar: ejecutar verify_complaints.sql en BigQuery us-central1.

Contrato: 27 campos, tipos, requeridos, longitudes, dominios indicados en diccionario,
precision monetaria, enteros y satisfaccion 1-5. No se fuerza un catalogo cerrado
para category/subcategory/currency. Describe y resolution preservan contenido
no vacio; blancos se vuelven NULL. Datos originales permanecen en raw.

Titularidad distinta es WARN, no rechazo. Columnas publicadas:
_product_owner_mismatch: TRUE difiere, FALSE coincide, NULL no evaluable.
_quality_warnings: lista de motivos por fila.
La relacion del reclamo con producto no acredita titularidad ni concede acceso.
No se cambia customer_id ni affected_product_id.

Cliente inexistente, producto informado ausente sin cuarentena, IDs repetidos
u otros errores bloquean la publicacion completa. Producto opcional vacio es valido.
Solo affected_product_id.quarantined_parent permite publicacion parcial.
Se usa exclusivamente cuarentena del run de products publicado al inicio.
No hay umbral numerico aprobado: cualquier cantidad de este motivo es WARN.

Fechas se preservan. Diferencia horaria es hipotesis no comprobada; parser UTC
si no hay zona. Cronologia, duracion calendario, negativos, moneda ausente con
importe y moneda distinta al producto son advertencias persistidas por fila y
agregadas en auditoria. No se recalcula SLA ni se imputan moneda o importes.

Pendientes: sucursal, agente e interaccion FK, catalogo de monedas, zona y SLA.
Auditoria/cuarentena 30 dias, staging 7 dias. Referencias en curation_references.
Reemplazo completo transaccional, particion process_date, cluster customer_id,
affected_product_id. No incremental; no ejecutar runs concurrentes.
Fallos intermedios pueden dejar RUNNING/VALIDATED: consultar tambien Dataform.

Esperado con perfil actual: 67095 entrada, 67094 publicadas, 1 cuarentena,
44569 con discrepancia, 22525 sin comparacion por producto vacio.
Las cifras son expectativas; nunca se fijan en las reglas.
Pruebas locales de generacion no sustituyen compilacion/ejecucion en GCP.
