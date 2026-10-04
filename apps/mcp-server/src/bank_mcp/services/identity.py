"""Minimal matched identity returned only to the trusted validator, not the LLM."""
from pydantic import BaseModel, Field

class VerifiedProduct(BaseModel):
    product_number: str
    product_type: str | None = None
    status: str | None = None

class IdentityVerification(BaseModel):
    verified: bool = False
    customer_id: str | None = None
    products: list[VerifiedProduct] = Field(default_factory=list)
