# Contratos de servicios

`contracts.Services` se inyecta al construir el grafo. No hay adaptador real aún.
Todas las herramientas reciben `session_ref`, `customer_id` y `arguments`.
El servidor debe comprobar autorización y validar estrictamente sus respuestas.
Errores operativos o respuestas inválidas: `ServiceFailure`; sesión vencida:
`SessionExpired`. No incluir datos sensibles en mensajes de error.

| Operación | Argumentos | Respuesta |
|---|---|---|
| find_transactions | slots, limit | transactions, has_more |
| list_cards | ninguno | cards |
| get_card | card_id | id, customer_id, status |
| dispute_context | transaction_id | existing_case_id opcional, recent_dispute_count |
| block_card | card_id, idempotency_key | id de recibo |
| read_block | id | id, verified, card_id, status |
| file_dispute | transaction_id, idempotency_key | id de caso |
| read_dispute | id | id, verified, customer_id, transaction_id |
| create_handoff | packet, idempotency_key | id de ticket |
| read_handoff | id | id, verified, customer_id |
| notify_employee | ticket_id, idempotency_key | id de entrega |
| read_notification | id | id, verified, ticket_id |

Transacción: `id`, `customer_id`, `card_id` opcional, `status`, `fraud_score`
opcional, `amount`, `amount_usd` opcional, `currency`, `date` ISO con zona.
Tarjeta: `id`, `customer_id`, `last4`, `status`.
Importes como strings decimales, evitando float.

`understand`: intent (not_me/charge_error/card_emergency/other), confidence,
slots (objeto), wants_human opcional. El modelo nunca devuelve rutas ejecutables
ni una identidad autorizada. El adaptador valida el esquema y rechaza salidas
inválidas. `detect_language` devuelve es/pt/en o None si no hay confianza suficiente.

Buscar exclusivamente en productos autorizados y devolver has_more cuando la
lista es parcial. Implementar la tolerancia de monto y filtros de fechas/comercio
en el adaptador. recent_dispute_count cubre los 90 días anteriores al reloj del
escenario, no todas las quejas. existing_case_id pertenece al cliente y transacción.

Mutaciones: deduplicación atómica por idempotency_key y comprobación actual de
permisos, titularidad, estado y política. Un timeout puede ocurrir después de
escribir: la misma clave recupera el recibo original. Cada read_* consulta el
estado persistido y verified solo es verdadero cuando comprobó el efecto.
No hacer eco de la solicitud como prueba de ejecución.

Publicar esquemas MCP equivalentes en contracts/mcp al conectar el servidor.
