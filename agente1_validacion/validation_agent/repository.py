"""Acceso a datos de clientes.

Capa de repositorio: el agente NUNCA consulta BigQuery directamente ni ve
los registros. Solo el validador usa este repositorio.

- BigQueryCustomerRepository: producción. Consultas PARAMETRIZADAS
  (evita SQL injection, incluido el que venga de prompt injection).
- InMemoryCustomerRepository: datos de prueba sintéticos para tests y demos.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Protocol

from .config import BigQueryConfig, settings


@dataclass(frozen=True)
class Product:
    product_number: str
    product_type: Optional[str] = None
    status: Optional[str] = None


@dataclass(frozen=True)
class CustomerRecord:
    customer_id: str
    date_of_birth: Optional[date]
    products: tuple = field(default_factory=tuple)   # tuple[Product, ...]


class CustomerRepository(Protocol):
    def get_customer(self, customer_id: str) -> Optional[CustomerRecord]: ...


class RepositoryUnavailable(Exception):
    """BigQuery caído, timeout o credenciales inválidas."""


class BigQueryCustomerRepository:
    def __init__(self, cfg: BigQueryConfig = settings.bq, client=None):
        from google.cloud import bigquery  # import perezoso
        self._bq = bigquery
        self.cfg = cfg
        self.client = client or bigquery.Client(project=cfg.project)

    def _query(self) -> str:
        c = self.cfg
        cust = f"`{c.project}.{c.dataset}.{c.customers_table}`"
        prod = f"`{c.project}.{c.dataset}.{c.products_table}`"
        # Un cliente puede tener VARIOS productos → ARRAY_AGG en una sola consulta
        return f"""
            SELECT
              CAST(c.{c.col_customer_id} AS STRING) AS customer_id,
              c.{c.col_dob} AS date_of_birth,
              ARRAY_AGG(
                IF(p.{c.col_product_number} IS NULL, NULL,
                   STRUCT(CAST(p.{c.col_product_number} AS STRING) AS product_number,
                          CAST(p.{c.col_product_type} AS STRING) AS product_type,
                          CAST(p.{c.col_product_status} AS STRING) AS status))
                IGNORE NULLS) AS products
            FROM {cust} c
            LEFT JOIN {prod} p
              ON CAST(p.{c.col_customer_id} AS STRING) = CAST(c.{c.col_customer_id} AS STRING)
            WHERE CAST(c.{c.col_customer_id} AS STRING) = @customer_id
            GROUP BY 1, 2
        """

    def get_customer(self, customer_id: str) -> Optional[CustomerRecord]:
        job_config = self._bq.QueryJobConfig(
            query_parameters=[self._bq.ScalarQueryParameter("customer_id", "STRING", customer_id)]
        )
        try:
            rows = list(
                self.client.query(self._query(), job_config=job_config)
                .result(timeout=self.cfg.query_timeout_s)
            )
        except Exception as exc:  # red, permisos, timeout
            raise RepositoryUnavailable(str(exc)) from exc

        if not rows:
            return None
        if len(rows) > 1:
            # Contrato de datos: customer_id debe ser único. Si no, no autenticamos.
            raise RepositoryUnavailable("customer_id duplicado en la tabla de clientes")

        r = rows[0]
        products = tuple(
            Product(p["product_number"], p.get("product_type"), p.get("status"))
            for p in (r["products"] or [])
        )
        return CustomerRecord(r["customer_id"], r["date_of_birth"], products)


class InMemoryCustomerRepository:
    """Datos SINTÉTICOS para pruebas. Nunca usar datos reales aquí."""

    def __init__(self, records: dict[str, CustomerRecord], fail: bool = False):
        self.records = records
        self.fail = fail
        self.calls = 0

    def get_customer(self, customer_id: str) -> Optional[CustomerRecord]:
        self.calls += 1
        if self.fail:
            raise RepositoryUnavailable("simulated outage")
        return self.records.get(customer_id)
