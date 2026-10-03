"""Fixed SELECT statements over bank_curated, explicit columns only.

Placeholders {transactions}/{products} are fully qualified table names supplied by
the gateway, never user input. Every value goes through a query parameter, and
every statement filters by @customer_id: ownership is enforced here, not by the caller.
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

# The join also requires the same customer, so a transaction never exposes
# another customer's product as its card.
FIND_TRANSACTIONS = """
SELECT t.transaction_id, t.customer_id, t.product_id, p.product_type, t.transaction_status,
       t.fraud_score, t.amount, t.amount_usd, t.currency, t.transaction_date, t.merchant_name
FROM {transactions} AS t
LEFT JOIN {products} AS p ON p.product_id = t.product_id AND p.customer_id = t.customer_id
WHERE t.customer_id = @customer_id
  AND t.transaction_date >= @start_ts AND t.transaction_date < @end_ts
  {filters}
ORDER BY t.transaction_date DESC
LIMIT @lim
"""

FILTER_AMOUNT = "AND t.amount BETWEEN @amount_lo AND @amount_hi"
FILTER_MERCHANT = "AND STRPOS(LOWER(t.merchant_name), LOWER(@merchant)) > 0"
FILTER_CURRENCY = "AND t.currency = @currency"
