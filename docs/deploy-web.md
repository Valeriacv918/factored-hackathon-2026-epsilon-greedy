# Web front and deployment

The front is plain HTML, CSS and JS with no build step, served by the same Python app that
runs the graph (`apps/agent/src/bank_agent/web`). One container (root `Dockerfile`) holds the
agent, the front and the MCP server as a stdio subprocess, deployed on Cloud Run as a single
service.

To run it locally, see the [Quickstart](../README.md#quickstart-run-locally).

## What it does

| Part | How |
|---|---|
| Graph | `graphs/validation_triage.build_graph` with all four routes, same as `run_disputes.py --flow full`. |
| Conversations | Server-generated `thread_id` (`web-<uuid>`). Each conversation belongs to the browser that created it (HttpOnly cookie); another browser gets 404. |
| Interactions | Each `interrupt` is shown as a form, text box or buttons, and resumed with `Command(resume=...)`. |
| Identity | Form with document, date of birth (date picker) and product. Goes straight to `resume` and MCP `verify_identity`. Never written to the chat or sent to the LLM; the form is cleared on submit. |
| Cards and charges | The browser receives `{index, label}` with the last four digits (or date, amount and merchant). It answers with the index and the server maps it to the real ID. |
| Connections | The MCP client and the compiled graph are created once at startup (`lifespan`). If configuration is missing or the subprocess fails, the revision fails to start instead of failing on the first form. |
| Secrets | Environment variables only. The browser receives no configuration. CSP `default-src 'self'`. |
| Language | The language detector runs before the form; if it cannot choose between Spanish and Portuguese, the customer picks with buttons (also an es/pt toggle in the UI). The choice is kept in the conversation state and used by forms, buttons and replies. The stats panel is not translated. |
| Stats | `GET /api/metrics`: conversations of this process (from `conversation.summary`) and the latest offline triage evaluation shipped in `evals/cases/results`. |

## Cloud Run

1. Store the secrets in Secret Manager (once):

```bash
printf '%s' "$GROQ_API_KEY" | gcloud secrets create bank-web-groq-api-key --data-file=-
```

```bash
python -c "import secrets; print(secrets.token_urlsafe(48), end='')" | gcloud secrets create bank-web-session-signing-key --data-file=-
```

2. Deploy from the repo root (Cloud Build builds the `Dockerfile`):

```bash
gcloud run deploy bank-agent-demo --source . --region us-east4 --service-account bank-mcp@hackaton-509923.iam.gserviceaccount.com --max-instances 1 --min-instances 0 --concurrency 8 --session-affinity --memory 1Gi --cpu 1 --timeout 300 --allow-unauthenticated --set-env-vars BQ_PROJECT=hackaton-509923,BQ_DATASET=bank_curated,BQ_LOCATION=us-central1,BQ_SANDBOX_DATASET=bank_sandbox,SANDBOX_SCENARIO_ID=<escenario>,SCENARIO_NOW=<scenario_clock>,LLM_MODEL=groq:openai/gpt-oss-120b --set-secrets GROQ_API_KEY=bank-web-groq-api-key:latest,SESSION_SIGNING_KEY=bank-web-session-signing-key:latest
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
los proyectos de agente y MCP y los resultados offline versionados en
`evals/cases/results`; el set fuente `evals/cases/triage_messages.csv` se conserva
en el repositorio, pero no se copia a la imagen. No se envían `.env`, entornos
virtuales ni credenciales locales. El panel muestra la corrida offline incluida
y las métricas de conversaciones recopiladas en ejecución.

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
a los formularios, botones, ayudas y respuestas finales de la web. Los factores
de identidad no se usan para detectar idioma ni se envían al modelo.

El idioma de conversación no traduce el panel estático de estadísticas.


## Despliegue verificado: 5 de octubre de 2026 (Bogotá)

- URL: https://bank-agent-demo-676773032351.us-east4.run.app
- Revisión: bank-agent-demo-00001-98s.
- Código de jonathan integrado con main: 768e23d3b4627eeab529bad285ff765f00af791f.
- Imagen: us-central1-docker.pkg.dev/hackaton-509923/cloud-run-source-deploy/bank-agent-demo@sha256:2e40d850198202a3cc1e1105d754c0aa78ee37372ef9e58ac3c8419092ab1b9f.
- La imagen añade USER 10001:10001 sobre la compilación de ese commit; el Dockerfile local incorpora el mismo cambio.
- Cloud Run en us-east4; BigQuery permanece en us-central1.
- SANDBOX_SCENARIO_ID=jury-20261005-99546af8bf.
- SCENARIO_NOW=2026-06-19T12:00:00+00:00.
- Secret Manager: versión 2 de bank-web-groq-api-key y bank-web-session-signing-key.
- Instancias: mínimo 0, máximo 1; concurrencia 8; memoria 1 GiB.

La prueba pública confirmó HTML, formulario y validación real con MCP/BigQuery
en español y portugués. En español también llegó a seleccionar una transacción
mediante el LLM real. No se confirmaron bloqueos ni disputas durante esta prueba.

La prueba de clasificación posterior encontró el límite diario de tokens de
Groq para openai/gpt-oss-120b. La clasificación en portugués queda pendiente de
repetirse cuando exista cuota. No confundir ese 429 del proveedor con el 429 de
Cloud Run observado antes de trasladar el servicio.

Las revisiones en us-central1 y us-east1 no quedaron verificadas para atender
tráfico. La prueba en us-east4 sí respondió. El mínimo temporal de una instancia
en us-central1 se restauró a cero. Para la demo usar la URL de us-east4.
