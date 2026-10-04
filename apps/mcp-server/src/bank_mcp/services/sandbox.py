"""Helpers for the simulated writes in bank_sandbox (docs/mcp-sandbox.md).

The scenario and the customer always come from the server (configuration and session
token); these helpers only shape what the fixed statements in sql/queries.py need.
"""
import datetime as dt
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from google.cloud import bigquery

# Complaint subcategories that count as a past dispute for recent_dispute_count.
DISPUTE_SUBCATEGORIES = ("Cargo no reconocido", "Cobro indebido")


@dataclass(frozen=True)
class Scenario:
    """A row of bank_sandbox.scenarios: fixed for the scenario's whole life."""
    scenario_id: str
    clock: dt.datetime
    products_run_id: str
    transactions_run_id: str


def request_hash(action: str, **arguments: str) -> str:
    """SHA-256 (lowercase hex) of the canonical request: sorted keys, no spaces.

    Example: block_card + card_id=PRD-1 hashes '{"action":"block_card","card_id":"PRD-1"}'.
    Scenario and customer are not included: they are already part of the lookup scope.
    """
    canonical = json.dumps({"action": action, **arguments}, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def params(**values: Any) -> list:
    """BigQuery parameters from Python values, so each statement gets exactly the ones it uses."""
    out = []
    for name, value in values.items():
        if isinstance(value, (tuple, list)):
            out.append(bigquery.ArrayQueryParameter(name, "STRING", list(value)))
        elif isinstance(value, dt.datetime):
            out.append(bigquery.ScalarQueryParameter(name, "TIMESTAMP", value))
        elif isinstance(value, int) and not isinstance(value, bool):
            out.append(bigquery.ScalarQueryParameter(name, "INT64", value))
        else:
            out.append(bigquery.ScalarQueryParameter(name, "STRING", value))
    return out
