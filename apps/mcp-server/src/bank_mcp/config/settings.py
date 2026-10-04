"""Settings from environment variables / .env. BigQuery auth is ADC, never a key file.

The one secret here is SESSION_SIGNING_KEY, which signs session tokens."""
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ROOT = Path(__file__).resolve().parents[3]   # apps/mcp-server
REPO_ROOT = APP_ROOT.parents[1]


class Settings(BaseSettings):
    # Later files win: the app's own .env overrides the repository one.
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", APP_ROOT / ".env"), extra="ignore")

    # Accept the names from the repository .env.example as well as BQ_*.
    bq_project: str = Field("hackaton-509923", min_length=1,
                            validation_alias=AliasChoices("BQ_PROJECT", "GCP_PROJECT_ID"))
    bq_dataset: str = Field("bank_curated", pattern=r"^[A-Za-z0-9_]+$",
                            validation_alias=AliasChoices("BQ_DATASET", "BIGQUERY_CURATED_DATASET"))
    bq_location: str = Field("us-central1", validation_alias=AliasChoices("BQ_LOCATION", "GCP_REGION"))
    bq_billing_project: str | None = Field(None, validation_alias="BQ_BILLING_PROJECT")

    max_bytes_billed: int = Field(default=1_000_000_000, gt=0)
    max_rows: int = Field(default=200, gt=0, le=10_000)
    query_timeout_s: float = Field(default=30, gt=0)
    rate_limit_per_min: int = Field(default=60, gt=0)

    # find_transactions matching. The search window is the agent's policy and
    # arrives as a tool argument (window_days), capped by search.MAX_SPAN_DAYS.
    amount_tolerance_pct: float = Field(default=10.0, ge=0, le=50)

    # Session tokens (services/session.py). The key signs every token: keep it secret,
    # e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
    session_signing_key: SecretStr = Field(min_length=32)
    session_ttl_minutes: int = Field(default=15, gt=0, le=24 * 60)
    identity_max_attempts: int = Field(default=3, gt=0)
    identity_lockout_minutes: int = Field(default=15, gt=0)

    @property
    def billing_project(self) -> str:
        return self.bq_billing_project or self.bq_project


@lru_cache
def get_settings() -> Settings:
    return Settings()
