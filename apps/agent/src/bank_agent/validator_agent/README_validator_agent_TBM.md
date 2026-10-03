# Agente 1 — Validación de identidad

## Estructura
```
validation_agent/
  config.py      # nombres de tablas/columnas de BigQuery y políticas (intentos, TTL...)
  language.py    # detección de idioma con lingua (es / pt / en)
  repository.py  # acceso a BigQuery (consultas parametrizadas) + repo de prueba en memoria
  validator.py   # reglas de autenticación: 100% código, sin LLM
  agent.py       # agente LangChain (create_agent) que conversa y llama al validador
tests/test_validation.py   # 22 tests con datos sintéticos
```

## Instalación
```bash
pip install -r requirements.txt
gcloud auth application-default login      # credenciales de Google Cloud

pytest tests -q
```

## Esquema esperado en BigQuery (ajustable con variables de entorno)
- `customers`: `customer_id`, `date_of_birth` (DATE)
- `products`: `product_number`, `customer_id`, `product_type`, `status`  (1 cliente → N productos)

## Uso
```python
from validation_agent.repository import BigQueryCustomerRepository
from validation_agent.validator import IdentityValidator
from validation_agent.agent_1validator import ValidationAgent

validator = IdentityValidator(BigQueryCustomerRepository())   # compartido entre conversaciones
agent = ValidationAgent(validator)                            # uno por conversación
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
| LOCKED | 3 fallos → bloqueo 15 min | asesor humano |
| SERVICE_UNAVAILABLE | BigQuery caído / timeout | asesor humano |

## Limitaciones conocidas
- Sesiones y bloqueos en memoria: en producción irían en Redis/Firestore (si no, se pierden al reiniciar y no escalan a varias instancias).
- Fechas `DD/MM/AAAA` se asumen formato latino; nunca `MM/DD`.
- ID + fecha + producto es conocimiento, no posesión: el reto lo acepta para prototipo, pero producción necesita OTP o sesión de la app.
- lingua es poco fiable en mensajes muy cortos; por eso se mantiene el idioma previo.
