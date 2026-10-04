"""Read-only verification of all three factors; no DOB or document returned."""
VERIFY_IDENTITY = r"""
WITH matched AS (
 SELECT c.customer_id
 FROM {customers} c
 WHERE (c.customer_id=@customer_id OR
        REGEXP_REPLACE(UPPER(c.document_number), r'[\s.\-]', '')=@customer_id)
   AND c.date_of_birth=@date_of_birth
   AND EXISTS (
     SELECT 1 FROM {products} owned
     WHERE owned.customer_id=c.customer_id
       AND REGEXP_REPLACE(UPPER(owned.product_number), r'[\s\-]', '')=@product_number
   )
 QUALIFY COUNT(*) OVER ()=1
)
SELECT c.customer_id,
 ARRAY_AGG(STRUCT(
   REGEXP_REPLACE(UPPER(p.product_number), r'[\s\-]', '') AS product_number,
   p.product_type AS product_type, p.product_status AS status
 ) ORDER BY p.product_id LIMIT 201) AS products
FROM matched c JOIN {products} p ON p.customer_id=c.customer_id
GROUP BY c.customer_id
"""
