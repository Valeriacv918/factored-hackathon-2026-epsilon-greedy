"""Emit BigQuery regression SQL using actual read queries and only TEMP fixtures."""
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding="utf-8")
root=Path(__file__).resolve().parent
print("""
CREATE TEMP TABLE scenarios AS
SELECT 's1' scenario_id,'p1' products_run_id
UNION ALL SELECT 's2','p1';
CREATE TEMP TABLE products AS
SELECT 'card1' product_id,'c1' customer_id,'Tarjeta Crédito' product_type,
 '11112222' product_number,'Active' product_status,'p1' _curation_run_id
UNION ALL SELECT 'card2','c1','Tarjeta Débito','33334444','Active','p1'
UNION ALL SELECT 'closed','c1','Tarjeta Débito','33334444','Closed','p1'
UNION ALL SELECT 'other','c2','Tarjeta Crédito','33334444','Active','p1'
UNION ALL SELECT 'loan','c1','Préstamo Personal','33334444','Active','p1'
UNION ALL SELECT 'stale','c1','Tarjeta Débito','33334444','Active','p0';
CREATE TEMP TABLE card_blocks AS
SELECT 'b1' block_id,'card1' card_id,'c1' customer_id,'s1' scenario_id,
 'p1' products_run_id,'SIMULATED' mode,'Blocked' status,'1.0.0' contract_version,
 TIMESTAMP '2026-06-17 12:00:00+00' created_at
UNION ALL SELECT 'b2','card2','c1','s2','p1','SIMULATED','Blocked','1.0.0',CURRENT_TIMESTAMP()
UNION ALL SELECT 'b3','closed','c1','s1','p1','SIMULATED','Blocked','1.0.0',CURRENT_TIMESTAMP();
""")
def query(name):
    sql=(root/name).read_text(encoding="utf-8-sig").strip().rstrip(";")
    for table in ("scenarios","card_blocks"):
        sql=sql.replace("`hackaton-509923.bank_sandbox."+table+"`",table)
    sql=sql.replace("`hackaton-509923.bank_curated.products`","products")
    for k,v in {"scenario_id":"s1","customer_id":"c1","card_id":"card1","block_id":"b1"}.items():
        sql=sql.replace("@"+k,"'"+v+"'")
    return sql
print("CREATE TEMP TABLE actual_cards AS\n"+query("cards_effective.sql")+";")
print("""
ASSERT (SELECT COUNT(*)=3 FROM actual_cards) AS 'Exclude other customer, non-card and stale run';
ASSERT (SELECT effective_status='Blocked' FROM actual_cards WHERE card_id='card1') AS 'Apply own block';
ASSERT (SELECT effective_status='Active' FROM actual_cards WHERE card_id='card2') AS 'Isolate scenario';
ASSERT (SELECT effective_status='Closed' FROM actual_cards WHERE card_id='closed') AS 'Preserve closed';
""")
print("CREATE TEMP TABLE verified AS\n"+query("read_block.sql")+";")
print("ASSERT (SELECT COUNT(*)=1 AND LOGICAL_AND(v.verified) FROM verified AS v) AS 'Verify receipt';")
print("INSERT INTO card_blocks SELECT * FROM card_blocks WHERE block_id='b1';")
print("CREATE TEMP TABLE duplicate_receipt AS\n"+query("read_block.sql")+";")
print("ASSERT (SELECT COUNT(*)=0 FROM duplicate_receipt) AS 'Reject duplicate receipt';")
print("SELECT 'PASSED' AS synthetic_read_tests;")
