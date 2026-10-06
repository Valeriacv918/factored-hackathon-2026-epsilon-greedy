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
| Stats | `GET /api/metrics`: conversations of this process (from `conversation.summary`) and the latest offline triage evaluation (`evals/cases/results`, optional; shown as unavailable in a fresh checkout). |

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
gcloud run deploy bank-agent-web --source . --region us-central1 --service-account bank-mcp@hackaton-509923.iam.gserviceaccount.com --max-instances 1 --min-instances 0 --concurrency 8 --session-affinity --memory 1Gi --cpu 1 --timeout 300 --allow-unauthenticated --set-env-vars BQ_PROJECT=hackaton-509923,BQ_DATASET=bank_curated,BQ_LOCATION=us-central1,BQ_SANDBOX_DATASET=bank_sandbox,SANDBOX_SCENARIO_ID=<scenario>,SCENARIO_NOW=<scenario_clock>,LLM_MODEL=groq:openai/gpt-oss-120b --set-secrets GROQ_API_KEY=bank-web-groq-api-key:latest,SESSION_SIGNING_KEY=bank-web-session-signing-key:latest
```

The runtime service account needs `roles/secretmanager.secretAccessor` on both secrets, in
addition to the BigQuery permissions `bank-mcp` already has. Cloud Run uses its own identity
for BigQuery: no service-account JSON or personal ADC goes into the image.

`DEV_SESSIONS` is not set on Cloud Run: the web app always authenticates with the form.

Build context: Cloud Build uses `.gcloudignore` and Docker uses `.dockerignore`. Only the agent
and MCP projects are sent; no `.env`, virtual environments or local credentials. The container
does not read `.env` files. The MCP SDK does not inherit all environment variables, so the client
passes an explicit list (BigQuery, scenario, limits, session signing); the LLM key stays in the
agent process.

## Decisions and limits

- **`--max-instances 1`**: the checkpointer (`InMemorySaver`), the conversation registry and the
  live metrics are in memory. With more instances a reply could reach an instance without the
  conversation. To scale: a persistent checkpointer (Postgres/Firestore) and metrics from Cloud
  Logging or BigQuery.
- **Restarts and deploys** lose in-progress conversations and live metrics (session affinity is
  best effort). Blocks, disputes and tickets stay in the sandbox tables.
- **One service account**: agent and MCP share `bank-mcp` because they run in one container.
  Running MCP as its own service (`MCP_SERVER_URL`) would isolate permissions better.
- **Cost** is estimated with `LLM_PRICE_INPUT_PER_MTOK` and `LLM_PRICE_OUTPUT_PER_MTOK` (USD per
  million tokens; defaults 0.15 and 0.75). Check the model's current price before reporting it.
- **`--allow-unauthenticated`**: needed so the jury can open the URL. Customer identity comes from
  the form; actions are simulated in the sandbox.
