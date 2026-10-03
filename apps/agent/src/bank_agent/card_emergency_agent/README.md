# card_emergency_agent

Implementa el diagrama "2. Card emergency" de `docs/STATE_MACHINE2.md`:
`SELECT_CARD -> CONFIRM_BLOCK -> BLOCK_AND_VERIFY -> ASK_CHARGE`.

```
service.py   # CardEmergencyService: 100% código, decide los estados
agent.py     # CardEmergencyAgent: LangChain create_agent, conversa con el cliente
```

## Por qué este agente SÍ usa LLM (a diferencia de `fraud_agent`)

Entender "me robaron la tarjeta" o "sí, bloquéala" es lenguaje libre del
cliente. El LLM solo conversa, pide el dato que falte y llama a la tool del
paso actual; **nunca decide el siguiente estado** — eso lo hace
`CardEmergencyService`, código puro, igual que `validator_agent/validator.py`
decide la identidad. Los pasos en sí son fijos y no los puede saltar ni
inventar (ver `prompts/card_emergency.py`).

`fraud_agent`, en cambio, no necesita conversar: solo recibe booleanos de
botones y un `transaction_id` ya resuelto, así que no lleva LLM.

## Requiere una sesión ya validada

Igual que `fraud_agent`: llama `validator.can_access_product(session_id,
producto)` antes de leer o actuar sobre cualquier tarjeta.
`CardEmergencyService.start()` falla con `PermissionError` si la sesión no
está autenticada.

## Entrega a `fraud_agent`

Cuando el cliente confirma que hay un cargo puntual (`ask_charge(True)` /
tool `report_charge(true)`), este agente termina en `next_step =
"find_transaction"` y su trabajo acaba ahí. El orquestador resuelve
FIND_TRANSACTION (fuera de alcance de ambos agentes) y continúa con
`fraud_agent.agent.FraudAgent.evaluate_transaction(session_id,
transaction_id)`. Ambos comparten el mismo `CardRepository`: si este agente
ya bloqueó la tarjeta, `fraud_agent` lo ve reflejado ahí y no vuelve a
preguntar.

## Uso

```python
from bank_agent.card_emergency_agent.service import CardEmergencyService
from bank_agent.card_emergency_agent.agent import CardEmergencyAgent

service = CardEmergencyService(validator, cards_repo)   # compartido entre conversaciones
agent = CardEmergencyAgent(service, session_id)         # uno por conversación
print(agent.chat("Me robaron la tarjeta"))
```
