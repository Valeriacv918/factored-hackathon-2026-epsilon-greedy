from decimal import Decimal
from bank_mcp.services.fx import enrich_usd

def row(currency="MXN",usd=None):
 return dict(amount=Decimal("100"),amount_usd=usd,currency=currency,local_date="2026-05-15")
RATE=dict(date="2026-05-15",source_currency="MXN",target_currency="USD",
          exchange_rate=Decimal(".058436"),_curation_run_id="run")

def test_same_currency_needs_no_rate():
 r=enrich_usd([row("USD")],[])[0]
 assert r["amount_usd"]==100 and r["amount_usd_source"]=="same_currency"
 assert r["amount_usd_original"] is None

def test_exact_rate_and_provenance():
 r=enrich_usd([row()],[RATE])[0]
 assert r["amount_usd"]==Decimal("5.84") and r["fx_run_id"]=="run"
 assert r["fx_date"]=="2026-05-15" and r["amount_usd_source"]=="daily_exchange_rates"

def test_no_guess_when_missing_duplicate_bad_or_wrong_day():
 for rates in [[],[RATE,RATE],[{**RATE,"exchange_rate":0}],[{**RATE,"date":"2026-05-14"}]]:
  assert enrich_usd([row()],rates)[0]["amount_usd"] is None

def test_curated_value_preserved_even_when_invalid():
 for usd in [Decimal("6"),Decimal("-1")]:
  r=enrich_usd([row(usd=usd)],[RATE])[0]
  assert r["amount_usd"]==usd and r["amount_usd_source"]=="curated"
