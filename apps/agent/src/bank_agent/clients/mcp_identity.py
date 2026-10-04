"""Trusted validation adapter: compare factors inside MCP, never fetch a DOB."""
from datetime import date
from bank_agent.clients.contracts import ServiceFailure
from bank_agent.clients.repository import CustomerRecord, Product, RepositoryUnavailable

class McpIdentityRepository:
    def __init__(self, client):
        self.client = client

    def verify_customer(self, customer_id: str, dob: date, product_number: str):
        try:
            result = self.client.call("verify_identity", {
                "customer_id": customer_id,
                "date_of_birth": dob.isoformat(),
                "product_number": product_number,
            })
            if result.get("verified") is not True:
                return None
            canonical = result["customer_id"]
            products = tuple(Product(**p) for p in result["products"])
            if not isinstance(canonical, str) or not canonical or not products:
                raise ValueError("Invalid verified identity")
            # DOB is the submitted value, already checked server-side; not a fetched record.
            return CustomerRecord(canonical, dob, products)
        except (ServiceFailure, KeyError, TypeError, ValueError) as exc:
            raise RepositoryUnavailable("Identity verification unavailable") from exc
