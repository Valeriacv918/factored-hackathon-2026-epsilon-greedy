"""Fixed statements over bank_curated (SELECT) and bank_sandbox (SELECT, INSERT), explicit columns only.

Placeholders {transactions}/{products}/{customers} are fully qualified table names
supplied by the gateway, never user input. Every value goes through a query parameter,
and every statement filters by @customer_id: ownership is enforced here, not by the caller.
"""

# Cards live in `products`; these are the card product types in bank_curated.
CARD_TYPES = ("Tarjeta Crédito", "Tarjeta Débito")

_CARD_COLUMNS = "product_id, customer_id, product_type, product_status, RIGHT(product_number, 4) AS last4"

LIST_CARDS = f"""
SELECT {_CARD_COLUMNS}
FROM {{products}}
WHERE customer_id = @customer_id AND product_type IN UNNEST(@card_types)
ORDER BY product_status, opening_date DESC
"""

GET_CARD = f"""
SELECT {_CARD_COLUMNS}
FROM {{products}}
WHERE customer_id = @customer_id AND product_id = @card_id AND product_type IN UNNEST(@card_types)
LIMIT 1
"""

# Product numbers are compared without spaces or dashes and uppercased, the same
# normalization the agent's validator applies to what the customer typed.
_PRODUCT_NUMBER = r"UPPER(REGEXP_REPLACE(p.product_number, r'[\s-]', ''))"
# Document numbers (cédula, CURP, DNI...) are compared without spaces, dots or dashes:
# "1.020.304.050" and "1020304050" are the same document.
_DOCUMENT_NUMBER = r"UPPER(REGEXP_REPLACE(c.document_number, r'[\s.-]', ''))"

# The customer identifies with the document they know (document_number); the row
# returns their internal customer_id. One row only if the date of birth matches AND
# one of the customer's products matches. A missing customer and a wrong answer both
# return no rows. The date of birth is never selected, so it never leaves the server.
VERIFY_IDENTITY = f"""
SELECT c.customer_id, ARRAY_AGG(DISTINCT {_PRODUCT_NUMBER} IGNORE NULLS) AS product_numbers
FROM {{customers}} AS c
JOIN {{products}} AS p ON p.customer_id = c.customer_id
WHERE {_DOCUMENT_NUMBER} = @document_number AND c.date_of_birth = @date_of_birth
GROUP BY c.customer_id
HAVING LOGICAL_OR({_PRODUCT_NUMBER} = @product_number)
"""

# The join also requires the same customer, so a transaction never exposes
# another customer's product as its card.
FIND_TRANSACTIONS = """
SELECT t.transaction_id, t.customer_id, t.product_id, p.product_type, t.transaction_status,
       t.fraud_score, t.amount, t.amount_usd, t.currency, t.transaction_date, t.merchant_name,
       DATE(t.transaction_date, @customer_timezone) AS local_date,
       @customer_timezone AS customer_timezone
FROM {transactions} AS t
LEFT JOIN {products} AS p ON p.product_id = t.product_id AND p.customer_id = t.customer_id
WHERE t.customer_id = @customer_id
  AND t.transaction_date >= TIMESTAMP(@start_date, @customer_timezone)
  AND t.transaction_date < TIMESTAMP(@end_date, @customer_timezone)
  {filters}
ORDER BY t.transaction_date DESC
LIMIT @lim
"""

FILTER_AMOUNT = "AND t.amount BETWEEN @amount_lo AND @amount_hi"
FILTER_MERCHANT = "AND STRPOS(LOWER(t.merchant_name), LOWER(@merchant)) > 0"
FILTER_CURRENCY = "AND t.currency = @currency"


# --- Sandbox (bank_sandbox): simulated card blocks and disputes -------------------
# Ported from infra/bigquery/sandbox/*.sql with table names as placeholders. Every
# statement filters by @scenario_id and @customer_id; the customer comes from the
# session token and the scenario from the server's configuration, never the caller.
# Rows must match data/contracts/sandbox/bank_sandbox_v1.json (contract 1.0.0).

# Single-SELECT form of preflight.sql: the scenario exists and curated products and
# transactions are still on the runs it was created from.
SCENARIO_STATE = """
WITH p AS (
  SELECT COUNT(*) AS n, COUNTIF(_curation_run_id IS NULL) AS missing,
         COUNT(DISTINCT _curation_run_id) AS runs, MIN(_curation_run_id) AS run
  FROM {products}
), t AS (
  SELECT COUNT(*) AS n, COUNTIF(_curation_run_id IS NULL) AS missing,
         COUNT(DISTINCT _curation_run_id) AS runs, MIN(_curation_run_id) AS run
  FROM {transactions}
)
SELECT s.scenario_clock, s.products_run_id, s.transactions_run_id,
       p.n > 0 AND p.missing = 0 AND p.runs = 1 AND p.run = s.products_run_id AS products_ok,
       t.n > 0 AND t.missing = 0 AND t.runs = 1 AND t.run = s.transactions_run_id AS transactions_ok
FROM {scenarios} AS s CROSS JOIN p CROSS JOIN t
WHERE s.scenario_id = @scenario_id
"""

# cards_effective.sql with the LIST_CARDS/GET_CARD columns: a block recorded in this
# scenario turns an Active card into Blocked; curated itself never changes.
_EFFECTIVE_CARDS = """
WITH blocks AS (
  SELECT DISTINCT card_id
  FROM {card_blocks}
  WHERE scenario_id = @scenario_id AND customer_id = @customer_id AND products_run_id = @products_run_id
    AND mode = 'SIMULATED' AND status = 'Blocked' AND contract_version = '1.0.0'
)
SELECT p.product_id, p.customer_id, p.product_type,
       IF(b.card_id IS NOT NULL AND p.product_status = 'Active', 'Blocked', p.product_status) AS product_status,
       RIGHT(p.product_number, 4) AS last4
FROM {products} AS p
LEFT JOIN blocks AS b ON b.card_id = p.product_id
WHERE p.customer_id = @customer_id AND p.product_type IN UNNEST(@card_types)
  AND p._curation_run_id = @products_run_id
"""

LIST_CARDS_EFFECTIVE = _EFFECTIVE_CARDS + "ORDER BY p.product_status, p.opening_date DESC\n"

GET_CARD_EFFECTIVE = _EFFECTIVE_CARDS + "  AND p.product_id = @card_id\nLIMIT 1\n"

# Inserts one row only if the card is the customer's, Active in the scenario's run,
# and neither this key nor a block on this card exists yet. Zero rows inserted is
# not an error by itself: FIND_BLOCK_RECEIPT decides what happened.
INSERT_BLOCK = """
INSERT INTO {card_blocks}
  (block_id, scenario_id, customer_id, idempotency_key, request_hash, created_at, actor_service,
   correlation_id, mode, contract_version, card_id, products_run_id, status)
SELECT @block_id, s.scenario_id, p.customer_id, @idempotency_key, @request_hash, CURRENT_TIMESTAMP(),
       SESSION_USER(), @idempotency_key, 'SIMULATED', '1.0.0', p.product_id, s.products_run_id, 'Blocked'
FROM {scenarios} AS s
JOIN {products} AS p ON p._curation_run_id = s.products_run_id
WHERE s.scenario_id = @scenario_id
  AND p.customer_id = @customer_id AND p.product_id = @card_id
  AND p.product_type IN UNNEST(@card_types) AND p.product_status = 'Active'
  AND NOT EXISTS (
    SELECT 1 FROM {card_blocks} AS b
    WHERE b.scenario_id = @scenario_id AND b.customer_id = @customer_id
      AND (b.idempotency_key = @idempotency_key OR (b.card_id = @card_id AND b.status = 'Blocked')))
"""

# The row for this key if any (same_key = TRUE: compare its hash), else an earlier
# block on the same card: a card that is already blocked needs no second event.
FIND_BLOCK_RECEIPT = """
SELECT block_id AS id, request_hash, idempotency_key = @idempotency_key AS same_key
FROM {card_blocks}
WHERE scenario_id = @scenario_id AND customer_id = @customer_id
  AND (idempotency_key = @idempotency_key
       OR (card_id = @card_id AND status = 'Blocked' AND products_run_id = @products_run_id))
ORDER BY same_key DESC, created_at
LIMIT 1
"""

# read_block.sql keyed by the receipt id. Exactly one row means verified.
READ_BLOCK = """
SELECT b.block_id AS id, b.card_id, b.customer_id, b.status, TRUE AS verified
FROM {card_blocks} AS b
JOIN {scenarios} AS s ON s.scenario_id = b.scenario_id
JOIN {products} AS p
  ON p.product_id = b.card_id AND p.customer_id = b.customer_id
 AND p._curation_run_id = s.products_run_id AND b.products_run_id = s.products_run_id
WHERE b.scenario_id = @scenario_id AND b.customer_id = @customer_id AND b.block_id = @id
  AND b.mode = 'SIMULATED' AND b.contract_version = '1.0.0' AND b.status = 'Blocked'
  AND p.product_type IN UNNEST(@card_types) AND p.product_status = 'Active'
QUALIFY COUNT(*) OVER () = 1
"""

# Same pattern for disputes: the transaction is the customer's, Approved, in the
# scenario's run, and has no OPEN dispute in this scenario yet.
INSERT_DISPUTE = """
INSERT INTO {disputes}
  (case_id, scenario_id, customer_id, idempotency_key, request_hash, created_at, actor_service,
   correlation_id, mode, contract_version, transaction_id, transactions_run_id, status)
SELECT @case_id, s.scenario_id, t.customer_id, @idempotency_key, @request_hash, CURRENT_TIMESTAMP(),
       SESSION_USER(), @idempotency_key, 'SIMULATED', '1.0.0', t.transaction_id, s.transactions_run_id, 'OPEN'
FROM {scenarios} AS s
JOIN {transactions} AS t ON t._curation_run_id = s.transactions_run_id
WHERE s.scenario_id = @scenario_id
  AND t.customer_id = @customer_id AND t.transaction_id = @transaction_id
  AND t.transaction_status = 'Approved'
  AND NOT EXISTS (
    SELECT 1 FROM {disputes} AS d
    WHERE d.scenario_id = @scenario_id AND d.customer_id = @customer_id
      AND (d.idempotency_key = @idempotency_key OR (d.transaction_id = @transaction_id AND d.status = 'OPEN')))
"""

FIND_DISPUTE_RECEIPT = """
SELECT case_id AS id, request_hash, idempotency_key = @idempotency_key AS same_key
FROM {disputes}
WHERE scenario_id = @scenario_id AND customer_id = @customer_id
  AND (idempotency_key = @idempotency_key
       OR (transaction_id = @transaction_id AND status = 'OPEN' AND transactions_run_id = @transactions_run_id))
ORDER BY same_key DESC, created_at
LIMIT 1
"""

# read_dispute.sql keyed by the receipt id.
READ_DISPUTE = """
SELECT d.case_id AS id, d.customer_id, d.transaction_id, d.status, TRUE AS verified
FROM {disputes} AS d
JOIN {scenarios} AS s ON s.scenario_id = d.scenario_id
JOIN {transactions} AS t
  ON t.transaction_id = d.transaction_id AND t.customer_id = d.customer_id
 AND t._curation_run_id = s.transactions_run_id AND d.transactions_run_id = s.transactions_run_id
WHERE d.scenario_id = @scenario_id AND d.customer_id = @customer_id AND d.case_id = @id
  AND d.mode = 'SIMULATED' AND d.status = 'OPEN' AND d.contract_version = '1.0.0'
QUALIFY COUNT(*) OVER () = 1
"""

# One job for dispute_context. owned = 0 means "not this customer's transaction".
# existing_case_id comes from the sandbox (complaints carry no transaction_id);
# recent_dispute_count comes from curated complaints only (docs/mcp-sandbox.md).
DISPUTE_CONTEXT = """
SELECT
  (SELECT COUNT(*) FROM {transactions}
   WHERE customer_id = @customer_id AND transaction_id = @transaction_id
     AND _curation_run_id = @transactions_run_id) AS owned,
  (SELECT ARRAY_AGG(case_id ORDER BY created_at LIMIT 1)[SAFE_OFFSET(0)] FROM {disputes}
   WHERE scenario_id = @scenario_id AND customer_id = @customer_id AND transaction_id = @transaction_id
     AND status = 'OPEN' AND mode = 'SIMULATED' AND transactions_run_id = @transactions_run_id) AS existing_case_id,
  (SELECT COUNT(*) FROM {complaints}
   WHERE customer_id = @customer_id AND subcategory IN UNNEST(@subcategories)
     AND creation_date >= @history_start AND creation_date < @history_end) AS recent_dispute_count
"""
