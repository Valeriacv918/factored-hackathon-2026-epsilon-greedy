# Agente 1 — Validación de identidad

## Estructura
```
nodes/validator_agent/
  language.py    # detección de idioma con lingua (es / pt)
  validator.py   # reglas de autenticación: 100% código, sin LLM
  agent.py       # agente LangChain (create_agent) que conversa y llama al validador
clients/identity.py   # IdentityChecker: McpIdentityChecker (real) + InMemoryIdentityChecker (tests)
config/settings.py    # políticas (intentos, bloqueo, TTL)
```

El agente no consulta BigQuery. La comparación de ID + fecha + producto la hace
el servidor MCP (`verify_identity`), que nunca devuelve la fecha de nacimiento y
responde con un token de sesión firmado. Ver apps/mcp-server/README.md.

## Esquema usado por el servidor (bank_curated)
- `customers`: `customer_id`, `date_of_birth` (DATE)
- `products`: `product_number`, `customer_id`  (1 cliente → N productos)

## Uso
```python
from bank_agent.clients.identity import McpIdentityChecker
from bank_agent.clients.mcp_services import mcp_client_from_env
from bank_agent.nodes.validator_agent.validator import IdentityValidator
from bank_agent.nodes.validator_agent.agent import ValidationAgent

validator = IdentityValidator(McpIdentityChecker(mcp_client_from_env()))   # compartido entre conversaciones
agent = ValidationAgent(validator)                                         # uno por conversación
print(agent.chat("Hola, quiero bloquear mi tarjeta"))
```
`chat()` devuelve `reply`, `language`, `status`, `authenticated`, `next_step`
(`ask_user` | `triage` | `handoff_human`) y `handoff` con el contexto para el asesor.

Los agentes 2–7 deben llamar `validator.can_access_product(session_id, producto)`
dentro de sus tools antes de leer o actuar sobre cualquier producto.

## Estados del validador
| Estado | Cuándo | Siguiente paso |
|---|---|---|
| VERIFIED | ID + fecha + un producto del cliente coinciden | triage |
| MISSING_FIELDS | falta algún dato | pedir dato |
| INVALID_FORMAT | fecha imposible, ID con caracteres inválidos | pedir corrección (no gasta intento) |
| FAILED | no coincide (mensaje genérico) | reintentar |
| LOCKED | 3 fallos (en esta conversación o en el servidor) → bloqueo 15 min | asesor humano |
| SERVICE_UNAVAILABLE | servidor MCP caído / timeout | asesor humano |

## Limitaciones conocidas
- Sesiones y bloqueos en memoria (aquí y en cada instancia del servidor MCP): en producción irían en Redis/Firestore (si no, se pierden al reiniciar y no escalan a varias instancias).
- Fechas `DD/MM/AAAA` se asumen formato latino; nunca `MM/DD`.
- ID + fecha + producto es conocimiento, no posesión: el reto lo acepta para prototipo, pero producción necesita OTP o sesión de la app.
- lingua es poco fiable en mensajes muy cortos; por eso se mantiene el idioma previo.
