# Operacion

1. Revisar proyecto, cuotas y datos de origen.
2. Ejecutar el Cloud Run Job de ingesta correspondiente y esperar su resultado.
3. Ejecutar perfiles si cambio la fuente o el contrato requiere diagnostico.
4. En data/dataform: upload_workspace.py, esperar COMPILED y ejecutar
   execute_compilation.py --table <tabla>. Cada envio usa compilacion/run_id nuevos.
5. Esperar Dataform y consultar verify_*.sql donde exista.

Orden compatible con referencias actuales: branches antes de service_agents;
customers antes de products; customers y products antes de transactions/complaints.
Daily exchange rates es independiente. Algunas FK de sucursal/agente aun pendientes.

VALIDATED no significa publicado. SUCCEEDED_WITH_REJECTIONS es exito parcial
aprobado, revisar WARN y cuarentena. No volver a enviar la misma compilacion.
No concurrencia por tabla curated. Publicaciones completas, no incrementales.
Fallos intermedios pueden dejar auditoria RUNNING/VALIDATED: consultar Dataform.
Staging 7 dias, auditoria/cuarentena curated 30 dias; reproduccion historica limitada.

Inventario pendiente: recuperar contratos raw faltantes y describir en GCP la
configuracion vigente de todos los Cloud Run Jobs. La copia local no prueba su
estado desplegado actual. Los documentos por tabla conservan nombres antiguos
de ZIP y ~/bank-dataform como referencia; usar data/dataform en este monorepo.


Actualizacion 2026-10-01: contratos raw recuperados e inventario de jobs registrado.
Ver gcp-audit-2026-10-01.md; sustituye el pendiente de recuperacion/inventario
anterior. Permisos efectivos y despliegue automatico siguen sin verificar/configurar.
