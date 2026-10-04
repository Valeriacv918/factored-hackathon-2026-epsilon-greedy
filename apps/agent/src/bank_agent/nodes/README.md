# Nodos

Una carpeta por componente: security_language, understanding, card_emergency_agent,
fraud_agent, charge_error y escalation. Cada una expone run(state, services, policy),
que es lo que graphs/disputes.py conecta al grafo.
common.py comparte confirmación, verificación e invocación de herramientas.
Las rutas las determina el código; los modelos no validan permisos.

card_emergency_agent y fraud_agent además exponen una API de clases
(CardEmergencyService, FraudAgent) con la misma lógica, usada únicamente por
scripts/chat_fraud_demo.py y sus propios tests fuera del grafo. El grafo real
solo llama a run().
