# Reglas y excepciones vigentes

La fuente ejecutable es data/dataform/includes/*_contract.js y definitions/.

- customers: publicacion estricta; normalizacion Mexico/Passport.
- products: numeros repetidos en cuarentena; otros errores bloquean.
- transactions: padre en cuarentena permite rechazo parcial; cliente/producto
  inexistente sin explicacion o titular distinto bloquean.
- complaints: titular distinto es WARN con marca por fila, no prueba de propiedad.
- branches: claves unicas, dominio Urbana -> Urban, publicacion estricta.
- service_agents: codigo repetido en cuarentena; sucursal inexistente es excepcion
  WARN, se preserva ID y estado de resolucion.
- daily_exchange_rates: clave compuesta, tasas positivas y precision 12,6 estrictas;
  no rellenar ni invertir tasas. Cotizacion y cobertura requerida pendientes.

No interpretar fechas anteriores como error corregible automaticamente: diferencia
horaria es hipotesis sin confirmar. No imputar importes ni moneda. Relaciones con
sucursales, agentes e interacciones siguen pendientes donde el contrato lo indique.
Las herramientas MCP futuras deben respetar estos estados; no ignorar warnings
para atribuir titularidad o sucursal.
