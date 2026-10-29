"""Public Seller API contracts."""

from datetime import date
from typing import Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, Field


class Product(BaseModel):
    id: int
    sku: str
    name: str
    category: str
    price_minor: int = Field(ge=0, description="Price in minor currency units")
    currency: Literal["RUB"] = "RUB"
    updated_at: AwareDatetime


class Order(BaseModel):
    id: int
    product_id: int
    quantity: int = Field(ge=1)
    total_minor: int = Field(ge=0)
    currency: Literal["RUB"] = "RUB"
    status: Literal["created", "shipped", "delivered", "cancelled"]
    created_at: AwareDatetime
    updated_at: AwareDatetime


class Stock(BaseModel):
    id: int
    product_id: int
    warehouse: str
    quantity: int = Field(ge=0)
    observed_at: AwareDatetime
    updated_at: AwareDatetime


class Advertising(BaseModel):
    id: int
    product_id: int
    campaign_id: int
    date: date
    spend_minor: int = Field(ge=0)
    currency: Literal["RUB"] = "RUB"
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    updated_at: AwareDatetime


T = TypeVar("T", Product, Order, Stock, Advertising)


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    next_page: int | None


class ErrorResponse(BaseModel):
    detail: str
