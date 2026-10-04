# card_emergency_agent

Implementa el diagrama "2. Card emergency" de `../../../../../../docs/STATE_MACHINE2.md`:
`SELECT_CARD -> CONFIRM_BLOCK -> BLOCK_AND_VERIFY -> ASK_CHARGE`.

```
service.py   # CardEmergencyService: 100% código, decide los estados
__init__.py  # run(state, services, policy): el nodo que conecta graphs/disputes.py
```

Dos interfaces para la misma lógica: `run()` es lo que el grafo real llama;
`CardEmergencyService` (clases) es lo mismo pero para
`scripts/chat_fraud_demo.py` y sus propios tests, fuera del grafo.

## 100% código, sin LLM (igual que `fraud_agent`)

Las confirmaciones del cliente llegan como booleanos de botones
(`select_card(product_number)`, `confirm_block(confirmed: bool)`,
`ask_charge(has_charge: bool)`) — nunca como texto libre interpretado por un
modelo. `CardEmergencyService` decide el siguiente estado; ningún LLM
participa en esa decisión, igual que `validator_agent/validator.py` (en
`nodes/validator_agent/`) decide la identidad sin que el LLM intervenga.

## Requiere una sesión ya validada

Igual que `fraud_agent`: llama `validator.can_access_product(session_id,
producto)` antes de leer o actuar sobre cualquier tarjeta.
`CardEmergencyService.start()` falla con `PermissionError` si la sesión no
está autenticada.

## Entrega a `fraud_agent`

Cuando el cliente confirma que hay un cargo puntual (`ask_charge(True)`),
este agente termina en `next_step = "find_transaction"` y su trabajo acaba
ahí. El orquestador resuelve FIND_TRANSACTION (fuera de alcance de ambos
agentes) y continúa con
`fraud_agent.agent.FraudAgent.evaluate_transaction(session_id,
transaction_id)`. Ambos comparten el mismo `CardRepository`: si este agente
ya bloqueó la tarjeta, `fraud_agent` lo ve reflejado ahí y no vuelve a
preguntar.

## Uso

```python
from bank_agent.nodes.card_emergency_agent.service import CardEmergencyService

service = CardEmergencyService(validator, cards_repo)   # compartido entre conversaciones
result = service.start(session_id)                      # -> select_card | confirm_block | ask_charge
result = service.confirm_block(session_id, True)
result = service.ask_charge(session_id, True)            # -> find_transaction
```
