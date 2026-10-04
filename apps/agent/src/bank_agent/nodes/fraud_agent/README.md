# fraud_agent

Implementa el diagrama "3. Fraud path" de `../../../../../../docs/STATE_MACHINE2.md`. 100%
código: ninguno de sus estados está marcado con LLM en la tabla de ese
documento, así que `agent.py` no llama a ningún modelo — solo recibe
booleanos de botones y un `transaction_id` ya resuelto.

```
policy.py   # DSP-004 (duplicado), DSP-005 (ventana), DSP-013 (umbral de riesgo)
agent.py    # FraudAgent: máquina de estados CONFIRM_BLOCK..DONE/ESCALATED
__init__.py # run(state, services, policy): el nodo que conecta graphs/disputes.py
```

Dos interfaces para la misma lógica: `run()` es lo que el grafo real llama;
`FraudAgent` (clases, en `agent.py`) es lo mismo pero para
`scripts/chat_fraud_demo.py` y sus propios tests, fuera del grafo.

### Umbrales (DSP-005/DSP-012/DSP-013): una sola fuente

Los números (`fraud_score=30`, `high_amount_usd=500`, `window_days=90`,
`max_charges=3`) viven en `graphs/policy.py:Policy` — es la fuente única.
`config/settings.py:FraudPolicy` los deriva de ahí (`_POLICY = Policy()`), y
tanto `agent.py` (vía `settings.fraud_policy`) como el `run()` del grafo (vía
`policy` que le pasa `graphs/disputes.py`) acaban leyendo los mismos valores.
Cambiar un umbral en `graphs/policy.py` alcanza para los dos.

El diagrama "2. Card emergency" (perder/que roben la tarjeta) vive aparte,
en `card_emergency_agent`, porque **ese sí necesita un LLM** para entender
lenguaje libre ("me robaron la tarjeta"). Este agente no conversa.

## Requiere una sesión ya validada

Como indica `validator_agent/README_validator_agent_TBM.md` (en `nodes/validator_agent/`): este agente
llama `validator.can_access_product(session_id, producto)` antes de leer o
actuar sobre cualquier producto o transacción.

## La disputa no es solo de tarjetas

Un cliente puede tener la transacción en cualquier producto: tarjeta, cuenta
de ahorros, cuenta corriente. Antes de seguir con la disputa, el agente
"protege" el producto, y eso significa algo distinto según el tipo
(`FraudAgent._protection_lookup` busca primero en `CardRepository`, luego en
`AccountRepository`):

| Tipo de producto | Acción de protección | Repositorio |
|---|---|---|
| Tarjeta | Se bloquea la tarjeta completa | `CardRepository.block_card` |
| Cuenta (savings/checking) | Se suspende solo su capacidad de hacer transacciones; el producto en sí no se bloquea | `AccountRepository.suspend_transactions` |

## Relación con `card_emergency_agent`

- Si el caso llegó por una emergencia de tarjeta, `card_emergency_agent` ya
  bloqueó la tarjeta y el orquestador resolvió `FIND_TRANSACTION`; se entra
  aquí por `evaluate_transaction(session_id, transaction_id)` y la protección
  se salta (se ve reflejada en el repositorio compartido).
- Si el caso llegó directo desde ROUTE (p. ej. "no reconozco este cargo de
  $900", sin mención de pérdida/robo), el producto puede no estar protegido
  todavía: este agente tiene su propio `confirm_block`, que bloquea o
  suspende según el tipo, sin preguntar primero por lenguaje natural (el
  producto ya se identificó por la transacción).

## Fuera de alcance (lo resuelve otro agente / el orquestador)

- **SELECT_CARD / CONFIRM_BLOCK como emergencia** ("2. Card emergency"):
  vive en `card_emergency_agent`, exclusivo de tarjetas (solo una tarjeta
  física se puede perder o robar).
- **FIND_TRANSACTION**: compartido con el path de "charge error"; este agente
  recibe `transaction_id` ya resuelto.
- **BUILD_HANDOFF / WRITE_NARRATIVE / CREATE_TICKET**: la redacción del
  resumen para el empleado sí usa LLM y vive en el flujo de escalamiento.
  Este agente solo devuelve un `EscalationRequest` (cola, prioridad, motivo,
  contexto verificado) cuando corresponde.

## Uso

```python
from bank_agent.nodes.fraud_agent import FraudAgent

fraud = FraudAgent(validator, cards_repo, accounts_repo, transactions_repo, disputes_repo)
result = fraud.evaluate_transaction(session_id, "TX-1")  # -> confirm_block | confirm_dispute | escalate
result = fraud.confirm_block(session_id, True)  # solo si hacía falta; bloquea o suspende según el tipo
result = fraud.confirm_dispute(session_id, True)
result = fraud.ask_more_charges(session_id, False)  # -> done, o escalate si DSP-013
```
