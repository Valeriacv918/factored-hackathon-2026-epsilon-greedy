"""find_transactions: turn extracted slots into one parameterized query.

Slots come from the agent's `understand` step (LLM extraction), so they are
validated here and unknown keys are ignored. The search window is anchored on
`reference_date`, not on the server clock: the demo data ends in 2026-06 and the
agent runs on a scenario clock (services.now()).
"""
import datetime as dt
from decimal import Decimal

from google.cloud import bigquery
from pydantic import BaseModel, ConfigDict, Field, field_validator

from bank_mcp.sql import queries

MAX_SPAN_DAYS = 366


class TransactionSlots(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: dt.date | None = Field(None, description="Exact transaction date (YYYY-MM-DD).")
    date_from: dt.date | None = Field(None, description="Start of a date range, inclusive.")
    date_to: dt.date | None = Field(None, description="End of a date range, inclusive.")
    amount: Decimal | None = Field(None, gt=0, description="Amount in the transaction currency, as a decimal string.")
    merchant: str | None = Field(None, min_length=1, max_length=100, description="Part of the merchant name.")
    currency: str | None = Field(None, pattern=r"^[A-Za-z]{3}$", description="ISO 4217 code.")

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


def date_range(slots: TransactionSlots, reference_date: dt.date, window_days: int) -> tuple[dt.date, dt.date]:
    """Return [start, end) in whole days."""
    if slots.date:
        return slots.date, slots.date + dt.timedelta(days=1)
    if slots.date_from or slots.date_to:
        end = slots.date_to or reference_date
        start = slots.date_from or end - dt.timedelta(days=window_days)
    else:
        end, start = reference_date, reference_date - dt.timedelta(days=window_days)
    if end < start:
        raise ValueError("date_to must be on or after date_from.")
    if (end - start).days > MAX_SPAN_DAYS:
        raise ValueError(f"Date range is limited to {MAX_SPAN_DAYS} days.")
    return start, end + dt.timedelta(days=1)


def _ts(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc)


def build_find_query(
    *, slots: TransactionSlots, customer_id: str, reference_date: dt.date, limit: int,
    window_days: int, tolerance_pct: float, transactions: str, products: str,
) -> tuple[str, list]:
    start, end = date_range(slots, reference_date, window_days)
    params = [
        bigquery.ScalarQueryParameter("customer_id", "STRING", customer_id),
        bigquery.ScalarQueryParameter("start_ts", "TIMESTAMP", _ts(start)),
        bigquery.ScalarQueryParameter("end_ts", "TIMESTAMP", _ts(end)),
        bigquery.ScalarQueryParameter("lim", "INT64", limit + 1),   # +1 detects has_more
    ]
    filters = []
    if slots.amount is not None:
        tolerance = slots.amount * Decimal(str(tolerance_pct)) / 100
        filters.append(queries.FILTER_AMOUNT)
        params += [bigquery.ScalarQueryParameter("amount_lo", "NUMERIC", slots.amount - tolerance),
                   bigquery.ScalarQueryParameter("amount_hi", "NUMERIC", slots.amount + tolerance)]
    if slots.merchant:
        filters.append(queries.FILTER_MERCHANT)
        params.append(bigquery.ScalarQueryParameter("merchant", "STRING", slots.merchant))
    if slots.currency:
        filters.append(queries.FILTER_CURRENCY)
        params.append(bigquery.ScalarQueryParameter("currency", "STRING", slots.currency))
    sql = queries.FIND_TRANSACTIONS.format(transactions=transactions, products=products,
                                           filters="\n  ".join(filters))
    return sql, params
