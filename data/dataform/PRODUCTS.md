# Products: publicacion parcial con cuarentena

Aplicar esta actualizacion sobre ~/bank-dataform. Requiere customers ya publicado.

python3 upload_workspace.py
# Solo despues de COMPILED:
python3 execute_compilation.py --table products

No ejecutar customers y products en paralelo ni seleccionar todas las etiquetas.
Se usa la version de customers publicada al inicio: la consulta no vuelve a ejecutar customers.
El snapshot de referencia se conserva en bank_stage.products_customers_<run_id> durante 7 dias.

Politica: todos los registros de numeros repetidos van a cuarentena con
error duplicate_product_number. No se selecciona un ganador ni se borran en raw.
Solo ese motivo permite publicacion parcial; otros errores bloquean.
Los dominios de product_type conservan las ocho etiquetas en espanol observadas.
La validacion de opening_branch_id contra branches sigue pendiente.

Estado esperado con el perfil actual: SUCCEEDED_WITH_REJECTIONS,
400000 entrada, 399988 publicados y 12 en bank_quarantine.products_rejected.
Los conteos son expectativas, no limites codificados. Un aumento de duplicados
se registra como WARN y no bloquea por cantidad; falta definir un umbral de negocio.

Auditoria y cuarentena retienen 30 dias. Staging retiene 7 dias.
Los fallos intermedios pueden dejar RUNNING: revisar tambien la invocacion Dataform.
Ejecutar cada tabla con una compilacion y run_id nuevos, sin ejecuciones concurrentes.
Pruebas locales no sustituyen compilacion Dataform ni ejecucion BigQuery.
