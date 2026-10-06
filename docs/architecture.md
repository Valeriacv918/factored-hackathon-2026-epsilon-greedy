# Architecture

> The LLM understands and writes. Deterministic code decides, acts and verifies.

## Data flow

```text
GCS (raw CSV) → Cloud Run ingestion jobs → BigQuery bank_raw → Dataform → bank_curated
```

- Audit events go to `bank_ops`; rejected rows to `bank_quarantine`.
- Dataform has dependencies inside each table pipeline. Cross-table references use the
  *published* snapshot of the other table; they do not trigger its rebuild.
- Details: [data platform](data-platform.md), [data/dataform](../data/dataform/README.md),
  [data/ingestion](../data/ingestion/README.md).

## Application flow

```text
Browser → web app (Starlette, apps/agent/web) → LangGraph graph → MCP server (stdio) → BigQuery
                                                                       ├─ bank_curated (read only)
                                                                       └─ bank_sandbox (simulated writes)
```

- **Web app + agent + MCP server** run in one Cloud Run container (`Dockerfile`); the agent
  starts the MCP server as a subprocess. See [deploy-web](deploy-web.md).
- **Agent** (`apps/agent`): the conversation is a LangGraph state machine
  ([state machine](state-machine.md)). Code chooses every next state from verified data.
  The LLM only classifies and extracts slots from the customer's words, and writes
  replies and the employee summary from facts the code gives it.
- **MCP server** (`apps/mcp-server`): bounded tools only, never arbitrary SQL. It decides who
  the customer is from a signed session token, never from a tool argument. Card blocks,
  disputes, handoffs and notifications are simulated rows in `bank_sandbox`; curated data
  is never modified. See [MCP and sandbox](mcp-sandbox.md).
- **Logs**: JSON lines from both processes; see [observability](observability.md).

## Principles

- The agent never queries BigQuery and never replicates data contracts: all data comes
  through MCP tools.
- Identity factors (document, date of birth, product number) go straight to the MCP
  `verify_identity` tool; no LLM sees them.
- Every action (block, dispute, handoff, notification) is confirmed by the customer with a
  button and verified by an independent read before the agent reports it.
- Data-quality flags and unresolved references are handled explicitly. A complaint linked
  to a product does not prove ownership or authorize access.

## Monorepo

One repository with separately deployable components (`apps/agent`, `apps/mcp-server`,
`data/*`), each with its own dependencies and identity. Reason: coordinate data, MCP tools
and agent changes during the hackathon. No shared library until real shared code exists.
MCP contracts (`contracts/mcp`) and data contracts (`data/contracts`) serve different purposes.
