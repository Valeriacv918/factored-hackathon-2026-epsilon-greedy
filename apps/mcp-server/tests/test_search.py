import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError

from bank_mcp.services.search import TransactionSlots, build_find_query, date_range

REF = dt.date(2026, 6, 18)


def build(slots, **kw):
    args = dict(slots=slots, customer_id="C1", reference_date=REF, limit=3, window_days=90,
                tolerance_pct=1.0, transactions="`p.d.transactions`", products="`p.d.products`")
    sql, params = build_find_query(**(args | kw))
    return sql, {p.name: p.value for p in params}


def test_default_window_ends_on_reference_date_inclusive():
    assert date_range(TransactionSlots(), REF, 90) == (dt.date(2026, 3, 20), dt.date(2026, 6, 19))


def test_exact_date_is_one_day():
    assert date_range(TransactionSlots(date="2026-05-01"), REF, 90) == (dt.date(2026, 5, 1), dt.date(2026, 5, 2))


def test_open_ended_range_uses_reference_and_window():
    assert date_range(TransactionSlots(date_from="2026-06-01"), REF, 90) == (dt.date(2026, 6, 1), dt.date(2026, 6, 19))
    assert date_range(TransactionSlots(date_to="2026-05-31"), REF, 30) == (dt.date(2026, 5, 1), dt.date(2026, 6, 1))


@pytest.mark.parametrize("slots", [{"date_from": "2026-06-10", "date_to": "2026-06-01"},
                                   {"date_from": "2024-01-01", "date_to": "2026-01-01"}])
def test_bad_ranges_rejected(slots):
    with pytest.raises(ValueError):
        date_range(TransactionSlots(**slots), REF, 90)


def test_no_slots_only_customer_and_window():
    sql, params = build(TransactionSlots())
    assert set(params) == {"customer_id", "start_ts", "end_ts", "lim"}
    assert params["lim"] == 4                       # limit + 1 for has_more
    assert "t.customer_id = @customer_id" in sql
    assert "@amount" not in sql and "@merchant" not in sql


def test_filters_are_parameters_not_sql_text():
    sql, params = build(TransactionSlots(amount="100", merchant="x' OR 1=1 --", currency="usd"))
    assert params["amount_lo"] == Decimal("99.00") and params["amount_hi"] == Decimal("101.00")
    assert params["merchant"] == "x' OR 1=1 --" and "OR 1=1" not in sql
    assert params["currency"] == "USD"


def test_unknown_slot_keys_ignored_and_bad_values_rejected():
    assert TransactionSlots(foo="bar").model_dump(exclude_none=True) == {}
    with pytest.raises(ValidationError):
        TransactionSlots(amount="-5")
    with pytest.raises(ValidationError):
        TransactionSlots(currency="dollars")
