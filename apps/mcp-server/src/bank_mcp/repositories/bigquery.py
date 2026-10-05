"""BigQuery access. Credentials only from ADC (gcloud locally, attached SA on Cloud Run).

Every query is parameterized, dry-run first against a byte cap, and time-limited.
Rows are returned raw (Decimal, datetime); services.mapping shapes them. The same
path runs the sandbox INSERT ... SELECT statements, which return no rows.
Every job logs one `bq.query` event (bank_mcp/observability.py), failures with their detail.
"""
import hashlib
import logging
from typing import Any

import google.auth
from google.api_core import exceptions as gexc
from google.cloud import bigquery

from bank_mcp.config.settings import Settings
from bank_mcp.observability import conversation_label, log_event

# Running query jobs needs the bigquery scope. What may be written is enforced by IAM
# (bank-mcp edits only the sandbox action tables) and by the server exposing only
# fixed statements: SELECTs over curated and sandbox, and INSERTs into card_blocks
# and disputes.
_SCOPES = ["https://www.googleapis.com/auth/bigquery"]

Param = bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter


class QueryError(RuntimeError):
    """A query failed for a reason that is safe to show the caller."""


class BigQueryGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        credentials, _ = google.auth.default(scopes=_SCOPES)
        self.client = bigquery.Client(project=settings.billing_project, credentials=credentials,
                                      location=settings.bq_location)

    def table(self, name: str) -> str:
        s = self.settings
        return f"`{s.bq_project}.{s.bq_dataset}.{name}`"

    def sandbox_table(self, name: str) -> str:
        s = self.settings
        return f"`{s.bq_project}.{s.bq_sandbox_dataset}.{name}`"

    def query(self, sql: str, params: list[Param], *, tool: str, job_id: str | None = None) -> list[dict[str, Any]]:
        s = self.settings
        sql_hash = hashlib.sha256(sql.encode()).hexdigest()[:12]
        labels = {"source": "bank-mcp", "tool": tool.replace("_", "-")}
        if conversation := conversation_label():
            labels["conversation"] = conversation   # bytes per conversation in INFORMATION_SCHEMA.JOBS
        base = dict(query_parameters=params, maximum_bytes_billed=s.max_bytes_billed,
                    use_legacy_sql=False, labels=labels)

        def failed(status: str, error: str, level: int = logging.WARNING) -> None:
            # The detail goes to the log only; the caller gets the QueryError text.
            log_event("bq.query", level=level, tool=tool, sql_hash=sql_hash, status=status, error=error)

        try:
            dry = self.client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, **base))
            estimated = dry.total_bytes_processed or 0
            if estimated > s.max_bytes_billed:
                raise QueryError(f"Query would scan {estimated:,} bytes, above the {s.max_bytes_billed:,} byte limit.")
            try:
                job = self.client.query(sql, job_config=bigquery.QueryJobConfig(use_query_cache=True, **base),
                                        **({"job_id": job_id, "job_retry": None} if job_id else {}))
            except gexc.Conflict:
                if not job_id:
                    raise
                job = self.client.get_job(job_id, location=s.bq_location)
            rows = [dict(r.items()) for r in job.result(timeout=s.query_timeout_s, max_results=s.max_rows)]
        except QueryError as e:
            failed("rejected_cost", str(e))
            raise
        except gexc.BadRequest as e:
            failed("bad_request", _first_error(e))
            raise QueryError(f"BigQuery rejected the query: {_first_error(e)}") from None
        except gexc.Forbidden as e:
            failed("forbidden", _first_error(e))
            raise QueryError("Access denied by BigQuery IAM.") from None
        except gexc.NotFound as e:
            failed("not_found", _first_error(e))
            raise QueryError(f"Not found: {_first_error(e)}") from None
        except TimeoutError:
            failed("timeout", f"over {s.query_timeout_s:.0f}s")
            raise QueryError(f"Query exceeded the {s.query_timeout_s:.0f}s timeout.") from None
        except gexc.GoogleAPICallError as e:   # 5xx, quota...: log it, do not pass it through
            failed("api_error", _first_error(e), logging.ERROR)
            raise QueryError("BigQuery is unavailable; try again.") from None
        log_event("bq.query", tool=tool, sql_hash=sql_hash, status="ok", rows=len(rows),
                  bytes=job.total_bytes_processed)
        return rows


def _first_error(e: gexc.GoogleAPICallError) -> str:
    errors = getattr(e, "errors", None) or []
    if errors and isinstance(errors[0], dict) and errors[0].get("message"):
        return str(errors[0]["message"])[:300]
    return str(e.message if hasattr(e, "message") else e)[:300]
