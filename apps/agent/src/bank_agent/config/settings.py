"""Configuración del agente de validación.

Todo lo que depende de TU base de datos está aquí. Ajusta los nombres
de tablas/columnas con variables de entorno, sin tocar el código.
"""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class BigQueryConfig:
    project: str = os.getenv("GCP_PROJECT_ID", "mi-proyecto")
    dataset: str = os.getenv("BQ_DATASET", "banco")
    customers_table: str = os.getenv("BQ_CUSTOMERS_TABLE", "customers")
    products_table: str = os.getenv("BQ_PRODUCTS_TABLE", "products")
    # Columnas
    col_customer_id: str = os.getenv("BQ_COL_CUSTOMER_ID", "customer_id")
    col_dob: str = os.getenv("BQ_COL_DOB", "date_of_birth")
    col_product_number: str = os.getenv("BQ_COL_PRODUCT_NUMBER", "product_number")
    col_product_type: str = os.getenv("BQ_COL_PRODUCT_TYPE", "product_type")
    col_product_status: str = os.getenv("BQ_COL_PRODUCT_STATUS", "status")
    query_timeout_s: float = float(os.getenv("BQ_TIMEOUT_S", "5"))


@dataclass(frozen=True)
class ValidationPolicy:
    max_attempts: int = 3                 # intentos fallidos antes de bloquear
    lockout_minutes: int = 15             # duración del bloqueo
    session_ttl_minutes: int = 15         # vida de la sesión autenticada
    supported_languages: tuple = ("es", "pt", "en")
    default_language: str = "es"
    min_lang_confidence: float = 0.60     # umbral de lingua
    min_chars_for_detection: int = 12     # textos más cortos no cambian el idioma


@dataclass(frozen=True)
class Settings:
    bq: BigQueryConfig = field(default_factory=BigQueryConfig)
    policy: ValidationPolicy = field(default_factory=ValidationPolicy)
    llm_model: str = os.getenv("LLM_MODEL", "groq:openai/gpt-oss-120b")


settings = Settings()