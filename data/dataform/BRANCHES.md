# Branches curated v1
Compilar con upload_workspace.py; ejecutar execute_compilation.py --table branches.
Verificar con verify_branches.sql al terminar Dataform.
22 columnas tipadas. Mexico y Urban normalizados desde México y Urbana.
Horarios TIME sin zona. Conteos INT64 no negativos. Coordenadas NUMERIC con
escala maxima 7 y rangos geograficos. Sucursales cerradas se conservan.
PK y branch_code unicos; no se colapsan duplicados. Cualquier rechazo bloquea.
Coherencia equipo/indicador, horarios nocturnos y coordenadas incompletas: WARN.
Publicacion transaccional completa, sin particion por ser dimension pequena.
Esperado: 350 publicados y 0 rechazados; conteos no fijados en codigo.
Auditoria/cuarentena 30 dias, staging 7 dias. No ejecutar en paralelo.
Fallos intermedios pueden dejar RUNNING/VALIDATED: consultar Dataform.
Este paquete no activa aun FK de sucursales en otros contratos. Es siguiente paso.
Pruebas locales no sustituyen compilacion y ejecucion BigQuery.
