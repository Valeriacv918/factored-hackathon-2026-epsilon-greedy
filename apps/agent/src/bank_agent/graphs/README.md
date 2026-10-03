# Grafo de disputas

`disputes.build_graph(services, checkpointer=..., policy=...)` compila seis nodos.
`state.initial_state` crea una conversación desde la capa autenticada.
`policy.Policy` contiene reglas de demostración configurables.

route lo escribe el código; phase identifica el paso interno. Seis componentes
no implican seis llamadas al modelo. Ver apps/agent/README.md para integración,
diagrama y límites actuales.
