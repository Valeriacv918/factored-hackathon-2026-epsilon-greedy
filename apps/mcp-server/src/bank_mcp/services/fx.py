"""Demo convention: exchange_rate is target currency per unit of source.
Exact local-date rate only; no inverse rates, fallback dates, or floating point.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

def enrich_usd(rows, rates):
    index=defaultdict(list)
    for rate in rates:
        if rate.get("target_currency")=="USD":
            index[(str(rate["date"]),rate["source_currency"])].append(rate)
    output=[]
    for original in rows:
        row=dict(original)
        row["amount_usd_original"]=row.get("amount_usd")
        row["amount_usd_source"]="curated" if row.get("amount_usd") is not None else "unavailable"
        row["fx_rate"]=None;row["fx_date"]=None;row["fx_run_id"]=None
        if row.get("amount_usd") is None:
            try:
                amount=Decimal(str(row["amount"]))
                if not amount.is_finite() or amount<0: raise ValueError("Invalid amount")
                if row["currency"]=="USD":
                    row["amount_usd"]=amount
                    row["amount_usd_source"]="same_currency"
                else:
                    matches=index[(str(row.get("local_date")),row["currency"])]
                    if len(matches)!=1: raise ValueError("Missing or ambiguous rate")
                    rate=Decimal(str(matches[0]["exchange_rate"]))
                    if not rate.is_finite() or rate<=0: raise ValueError("Invalid rate")
                    row["amount_usd"]=(amount*rate).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
                    row.update(amount_usd_source="daily_exchange_rates",fx_rate=rate,
                               fx_date=str(matches[0]["date"]),fx_run_id=matches[0].get("_curation_run_id"))
            except (ValueError, InvalidOperation, KeyError):
                pass
        output.append(row)
    return output
