# Front web del agente: ejecución local y despliegue

El front es HTML, CSS y JS sin build, servido por la misma app Python que corre el grafo
(`apps/agent/src/bank_agent/web`). Hay un solo contenedor (`Dockerfile` en la raíz) con el
agente, el front y el servidor MCP como subproceso stdio, desplegado en Cloud Run como un solo servicio.

## Qué hace

| Parte | Cómo |
|---|---|
| Grafo | `graphs/validation_triage.build_graph` con las cuatro rutas, igual que `run_disputes.py --flow full`. |
| Conversaciones | `thread_id` generado por el servidor (`web-<uuid>`). Cada conversación pertenece al navegador que la creó (cookie HttpOnly); otro navegador recibe 404. |
| Interacciones | Cada `interrupt` se muestra como formulario, caja de texto o botones, y se continúa con `Command(resume=...)`. |
| Identidad | Formulario de documento, fecha de nacimiento (selector de fecha) y producto. Va directo al `resume` y a MCP `verify_identity`. No se escribe en el chat ni llega al LLM, y el formulario se borra al enviarlo. |
| Tarjetas y cargos | El navegador recibe `{index, label}` con los últimos cuatro dígitos (o fecha, monto y comercio). Responde con el índice y el servidor lo traduce al ID real. |
| Conexiones | El cliente MCP y el grafo compilado se crean una vez al arrancar (`lifespan`). |
| Secretos | Solo variables de entorno. El navegador no recibe configuración. CSP `default-src 'self'`. |
| Estadísticas | `GET /api/metrics`: conversaciones de este proceso (desde `conversation.summary`) y la última evaluación offline de triage (`evals/cases/results`). |

## Local

Requiere el `.env` de la raíz (ver `.env.example` y `docs/mcp-sandbox.md`), con
`SANDBOX_SCENARIO_ID`, `SCENARIO_NOW`, `SESSION_SIGNING_KEY` y `GROQ_API_KEY`.

```bash
uv run --project apps/agent bank-web
```

Abre http://localhost:8080. Los logs JSON salen por stdout, o a `LOG_FILE` si está definido.

## Cloud Run

1. Guarda los secretos en Secret Manager (una sola vez):

```bash
printf '%s' "$GROQ_API_KEY" | gcloud secrets create bank-web-groq-api-key --data-file=-
```

```bash
python -c "import secrets; print(secrets.token_urlsafe(48), end='')" | gcloud secrets create bank-web-session-signing-key --data-file=-
```

2. Despliega desde la raíz del repo (Cloud Build construye el `Dockerfile`):

```bash
gcloud run deploy bank-agent-web --source . --region us-central1 --service-account bank-mcp@hackaton-509923.iam.gserviceaccount.com --max-instances 1 --min-instances 0 --concurrency 8 --session-affinity --memory 1Gi --cpu 1 --timeout 300 --allow-unauthenticated --set-env-vars BQ_PROJECT=hackaton-509923,BQ_DATASET=bank_curated,BQ_LOCATION=us-central1,BQ_SANDBOX_DATASET=bank_sandbox,SANDBOX_SCENARIO_ID=<escenario>,SCENARIO_NOW=<scenario_clock>,LLM_MODEL=groq:openai/gpt-oss-120b --set-secrets GROQ_API_KEY=bank-web-groq-api-key:latest,SESSION_SIGNING_KEY=bank-web-session-signing-key:latest
```

La cuenta de servicio en tiempo de ejecución necesita `roles/secretmanager.secretAccessor`
sobre los dos secretos, además de los permisos de BigQuery que ya tiene `bank-mcp`.

`DEV_SESSIONS` no se configura en Cloud Run: la web siempre autentica con el formulario.

## Decisiones y límites

- **`--max-instances 1`**: el checkpointer (`InMemorySaver`), el registro de conversaciones y las
  métricas en vivo viven en memoria. Con más instancias, una respuesta podría llegar a otra
  instancia sin la conversación. Para escalar: checkpointer persistente (Postgres/Firestore) y
  métricas desde Cloud Logging o BigQuery.
- **Reinicios**: si Cloud Run reinicia el contenedor, se pierden las conversaciones en curso y las
  métricas en vivo. Los bloqueos, disputas y tickets sí quedan en las tablas del sandbox.
- **Una cuenta de servicio**: agente y MCP comparten `bank-mcp` porque corren en el mismo
  contenedor. Separarlos (MCP en su propio servicio con `MCP_SERVER_URL`) aísla mejor los permisos.
- **Costo**: se estima con `LLM_PRICE_INPUT_PER_MTOK` y `LLM_PRICE_OUTPUT_PER_MTOK` (USD por millón
  de tokens; por defecto 0.15 y 0.75). Confirmar la tarifa vigente del modelo antes de reportarla.
- **`--allow-unauthenticated`**: necesario para que el jurado abra la URL. La identidad del cliente
  la da el formulario; las acciones son simuladas en el sandbox.


## Preparación del contexto de build

Cloud Build utiliza `.gcloudignore` y Docker utiliza `.dockerignore`. Se incluyen
solo los proyectos de agente y MCP; no se envían `.env`, entornos virtuales ni
credenciales locales. Los resultados offline de evaluaciones son opcionales:
una copia limpia del repositorio no los contiene y el panel los muestra como
no disponibles. Las métricas de las conversaciones sí se recopilan en ejecución.

La cuenta de ejecución usa su identidad de Cloud Run para BigQuery; no se
incluyen archivos JSON de cuentas de servicio ni ADC personales en la imagen.
Los secretos de esta aplicación se llaman `bank-web-groq-api-key` y
`bank-web-session-signing-key`. Su acceso se concede a `bank-mcp` por secreto.

La configuración inicial limita a una instancia y ocho peticiones simultáneas.
La afinidad es de mejor esfuerzo: un reinicio o despliegue pierde las conversaciones
en memoria y requiere iniciar otra. No elimina los efectos ya escritos en sandbox.

### Configuración del subproceso MCP

El SDK MCP no hereda automáticamente todas las variables del proceso web.
El cliente transmite una lista explícita de configuración de BigQuery, escenario,
límites y firma de sesiones. La clave del LLM permanece en el proceso del agente.
El contenedor no depende de archivos .env.

La web inicializa la conexión MCP durante el arranque. Si falta configuración o
el subproceso no arranca, falla el inicio de la revisión en lugar de esperar al
primer formulario del usuario para descubrir el problema.

### Idioma de la conversación

El grafo completo llama al detector de validator_agent/language.py antes del
formulario. Si el detector no decide entre español y portugués, muestra botones
para elegir. La elección queda en el estado de la conversación y se transmite
a los formularios y botones de la web. Los factores de identidad no se usan
para detectar idioma ni se envían al modelo.

El idioma de conversación no traduce el panel estático de estadísticas.
