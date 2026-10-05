import datetime as dt
from decimal import Decimal

from bank_mcp.services.mapping import iso_utc, to_card, to_search, to_transaction

UTC = dt.timezone.utc


def tx_row(**overrides):
    row = {"transaction_id": "TX1", "customer_id": "C1", "product_id": "P1", "product_type": "Tarjeta Crédito",
           "transaction_status": "Approved", "fraud_score": Decimal("12.5"), "amount": Decimal("40.00"),
           "amount_usd": Decimal("40.00"), "currency": "USD",
           "transaction_date": dt.datetime(2026, 6, 1, 12, tzinfo=UTC), "merchant_name": "Shop"}
    return row | overrides


def test_transaction_uses_agent_field_names():
    t = to_transaction(tx_row()).model_dump()
    assert t == {"id": "TX1", "customer_id": "C1", "card_id": "P1", "status": "Approved", "fraud_score": "12.5",
                 "amount": "40.00", "amount_usd": "40.00", "currency": "USD",
                 "date": "2026-06-01T12:00:00+00:00", "merchant": "Shop",
                 "local_date": None, "customer_timezone": None,
                 "amount_usd_original":"40.00", "amount_usd_source":"curated",
                 "fx_rate":None, "fx_date":None, "fx_run_id":None}


def test_non_card_product_has_no_card_id():
    assert to_transaction(tx_row(product_type="Cuenta Ahorro")).card_id is None
    assert to_transaction(tx_row(product_type=None)).card_id is None   # no matching owned product


def test_missing_values_stay_null_not_imputed():
    t = to_transaction(tx_row(fraud_score=None, amount_usd=None))
    assert t.fraud_score is None and t.amount_usd is None


def test_naive_timestamp_is_treated_as_utc():
    assert iso_utc(dt.datetime(2026, 1, 2, 3, 4)) == "2026-01-02T03:04:00+00:00"


def test_card_mapping():
    c = to_card({"product_id": "P1", "customer_id": "C1", "product_type": "Tarjeta Débito",
                 "product_status": "Blocked", "last4": "1234"}).model_dump()
    assert c == {"id": "P1", "customer_id": "C1", "last4": "1234", "status": "Blocked", "type": "Tarjeta Débito"}


def test_has_more_from_extra_row():
    rows = [tx_row(transaction_id=f"TX{i}") for i in range(4)]
    result = to_search(rows, limit=3)
    assert [t.id for t in result.transactions] == ["TX0", "TX1", "TX2"] and result.has_more
    assert not to_search(rows[:3], limit=3).has_more
