# MCP and the banking sandbox

How the MCP server (`apps/mcp-server`) uses the BigQuery sandbox for simulated card blocks,
disputes, handoffs and notifications, and why. Tables, permissions and deployment of the
sandbox itself: [infra/bigquery/sandbox](../infra/bigquery/sandbox/README.md).

## 1. What a scenario is

A scenario is one row of `bank_sandbox.scenarios`: a named demo session. It stores:

- `scenario_id`: the identifier, e.g. `demo-20261004T120000Z-123`.
- `products_run_id` and `transactions_run_id`: the curated data version it was built on.
- `scenario_clock`: the simulated "today" of the demo (the historical data ends in June 2026).

Every sandbox table (`card_blocks`, `disputes`, `handoffs`, `notifications`) has
`scenario_id STRING NOT NULL`, and read and verification queries only consider rows of the
same scenario. Resetting the demo means creating a new scenario; rows are never deleted and
stay as evidence.

## 2. Configuration and identity

1. An admin creates the scenario with `infra/bigquery/sandbox/create_scenario.sql`
   (`bank-mcp` can only read `scenarios`).
2. Set `SANDBOX_SCENARIO_ID`: in `.env` locally, with `--set-env-vars` on Cloud Run. It is
   not a secret. Changing it on Cloud Run creates a new revision and resets the in-memory
   counters (login attempts, rate limit).
3. The agent's `SCENARIO_NOW` must equal the scenario's `scenario_clock`.
4. The server runs as `bank-mcp@hackaton-509923.iam.gserviceaccount.com`:
   - Locally, through ADC with impersonation:
     `gcloud auth application-default login --impersonate-service-account=bank-mcp@hackaton-509923.iam.gserviceaccount.com`.
     Needs the Token Creator role on that account. Check with `SELECT SESSION_USER()`; it
     must return `bank-mcp`.
   - On Cloud Run, as the attached service account (`--service-account`).
   - Never with JSON keys.

Without `SANDBOX_SCENARIO_ID`, the write tools and `dispute_context` answer
`Sandbox scenario not configured.` and cards show their curated status. On start the
server logs which mode it is in.

## 3. What each tool reads and writes

The LLM never queries the database. The agent's code calls the MCP tools; the model only
interprets the customer's message and writes the employee summary from verified facts.

| Tool | Source |
|---|---|
| `verify_identity` | Curated (`customers`, `products`) |
| `find_transactions` | Curated; with a scenario, `scenario_clock` is the reference date |
| `list_cards`, `get_card` | Curated + the scenario's blocks (effective status) |
| `block_card` | Writes `bank_sandbox.card_blocks` |
| `read_block` | Sandbox, checked against curated |
| `file_dispute` | Writes `bank_sandbox.disputes` |
| `read_dispute` | Sandbox, checked against curated |
| `dispute_context` | Scenario disputes + curated complaints |
| `create_handoff` | Writes `bank_sandbox.handoffs`; checks references against curated and sandbox |
| `read_handoff` | Sandbox, checked against curated `customers` |
| `notify_employee` | Writes `bank_sandbox.notifications` |
| `read_notification` | Sandbox, checked against the handoff |
| `save_charge_explanation` | Writes `bank_sandbox.agent_results` (no scenario); see section 9 |

Effective status: a card `Active` in curated with a block in the scenario is returned as
`Blocked`. Curated never changes.

The customer identifies with their `document_number` (cédula, CURP, DNI); the session
token carries the internal `customer_id`, which filters every sandbox tool.

## 4. Why combine curated and sandbox

**Pros**

- **The agent's safety checks work.** Before blocking, the agent reads the card and only
  asks for confirmation if it is not `Blocked`; `dispute_context` prevents disputing the
  same charge twice. Without reading the sandbox the agent would repeat actions.
- **Every action is verified.** The agent reports a block or case only after
  `read_block`/`read_dispute` finds it persisted.
- **Curated is untouched.** `bank-mcp` cannot write `bank_curated`; resetting is creating
  another scenario.
- **Auditable.** Each change is a row with identity (`actor_service`) and time.

**Cons**

- **Curated must stay frozen during the demo.** Sandbox rows are tied to a curated version.
  If data is re-curated, every write detects it and refuses (`Curated data changed...`);
  the fix is a new scenario.
- **Only part of the data reflects actions.** Cards show the block, but a disputed
  transaction still shows as `Approved` in `find_transactions`.
- **One shared scenario.** All conversations use it: a block made in one is visible in
  another for the same customer.
- **Customer isolation relies on SQL only.** IAM does not separate rows by customer; every
  query filters by the session token's customer.
- **Latency.** One write is about four BigQuery jobs (scenario, insert, receipt, verify).
- **Simulated and real mix in the wording.** The summary says "card blocked" even though
  the block is `SIMULATED`.

## 5. Writes

- **Idempotency scope:** table + scenario + customer + `idempotency_key`. The agent uses
  `conversation:action:target` as the key.
- **`request_hash`:** lowercase hex SHA-256 of `{"action": ..., <arguments>}` serialized
  with sorted keys and no spaces (`services/sandbox.request_hash`). For example
  `block_card` on `PRD-1` hashes `{"action":"block_card","card_id":"PRD-1"}`.
- **Retries:** same key and hash return the original receipt; same key with other
  arguments is an error.
- **Eligibility:**
  - Block: the customer's credit or debit card, `Active` in the scenario's version. A card
    already blocked in the scenario returns that block.
  - Dispute: the customer's transaction, `Approved`, in the scenario's version. A
    transaction with an `OPEN` dispute in the scenario returns that case.
  - Handoff: one ticket per key; see section 7.
  - Notification: the customer's ticket in the scenario. An already notified ticket returns
    that notification.
- **Generic errors:** `Card cannot be blocked.` / `Transaction cannot be disputed.` /
  `Ticket not found.`, without saying whether it does not exist, belongs to another
  customer or is not eligible.
- **Verification:** `read_*` requires exactly one row consistent with the scenario and the
  curated version; otherwise `Receipt not verified.`
- **Concurrency:** the conditional insert (`INSERT ... SELECT ... NOT EXISTS`) does not
  guarantee uniqueness under simultaneous calls with the same key; BigQuery has no unique
  constraints.

## 6. `dispute_context`

- `existing_case_id`: the customer's `OPEN` dispute on that transaction in the scenario,
  if any. It comes from the sandbox because curated complaints have no `transaction_id`.
- `recent_dispute_count`: curated complaints only (`bank_curated.complaints`) of the
  customer with `subcategory` in `Cargo no reconocido` or `Cobro indebido`, any
  `case_type` and status, and `creation_date` in the 90 days before `scenario_clock`
  (`DISPUTE_HISTORY_DAYS`).
- Consequence: disputes filed during the demo do not count toward DSP-011 (two or more
  recent disputes escalate). Duplicates on the same charge are still caught by
  `existing_case_id`.
- Complaint dates have an unconfirmed time offset (see the complaints section of
  [data/dataform](../data/dataform/README.md)): a complaint at the window edge can fall
  on either side.

## 7. Handoffs and notifications

An escalation ends with two writes, each verified by its read: `create_handoff` opens the
ticket for an employee and `notify_employee` signals it is waiting. Only then does the
customer see "Case sent to a human agent".

- **Packet:** `create_handoff` receives the packet built by the escalation node (`reason`,
  `queue`, `priority`, `language`, `customer_quote`, transaction/case/card ids, `not_done`,
  `next_steps`, `policy_version`, rules, `narrative`, `narrative_source`, `claim_issues`).
  The schema is strict (`HandoffPacket` in `services/mapping.py`): an unknown field, a
  malformed id or a too-long text (`customer_quote` 1000, `narrative` 2000 characters) is
  rejected, so tokens or extra data are never stored. It is saved in `packet` (JSON).
- **References:** every cited transaction, case and card must belong to the token's
  customer; otherwise `Handoff cites items that are not the customer's.` and nothing is
  written. Ownership is checked, not status.
- **`suspended_accounts` is always empty:** account suspension does not exist.
- **Idempotency:** `request_hash` covers the whole packet. The agent builds the packet once
  and keeps it in the checkpoint, so a retry sends the same one.
- **One notification per ticket**, like one block per card.
- **Nobody receives anything.** `status` is always `SIMULATED` and the table has no
  recipient or channel: the receipt proves the notice was recorded, not delivered.

## 8. Clocks

`scenario_clock` is the server's reference: it anchors `find_transactions` and the
`recent_dispute_count` window. The agent uses `SCENARIO_NOW` for its policy (charge age).
If they differ the server logs a warning and uses `scenario_clock`; keep them equal.
Authentication and token TTL use real time, so sessions do not expire against historical
dates.

## 9. Charge explanations (`agent_results`)

`save_charge_explanation` stores the fixed explanation (`EXP-002/003/006`) for a Pending,
Reversed or Declined transaction in `bank_sandbox.agent_results`
(`infra/bigquery/sandbox/003_agent_results.sql`, which also grants `dataEditor` on that
table to `bank-mcp`).

- `customer_id` comes from the signed token; ownership and status are checked in SQL. The
  rule and text are fixed by the server: no free text and no LLM-chosen customer.
- A stable `result_id` is derived from version, conversation, customer, transaction and
  status. A deterministic job id prevents two concurrent inserts of the same result; MERGE
  allows repeats after the job's retention. The read-back must return exactly one row.
- If the status changed before the first save, nothing incompatible is inserted. If the
  save cannot be verified, the flow does not report success.
- It does not need `SANDBOX_SCENARIO_ID` and is not scenario-scoped. Rows are `SIMULATED`:
  no refunds or open disputes.

## 10. Local dates in searches

`find_transactions` resolves the authenticated customer's country, state and city from
`bank_curated.customers`. `services/timezones.py` maps the 16 observed locations to IANA
zones; an unknown location is an explicit error. Exact dates and ranges are full local
days: BigQuery converts both local midnights to UTC (with historical DST) to filter
`transaction_date`. `local_date` (YYYY-MM-DD) is shown to the customer; `date` keeps the
original timestamp.

## 11. Out of scope

- Account suspension (`list_accounts`, `get_account`, `suspend_account_transactions`): no
  sandbox table or permissions, and `find_transactions` returns no `account_id`, so fraud
  on an account (not a card) escalates (`no_blockable_card`).
- Unblocking and dispute status changes: not in contract 1.0.0.
