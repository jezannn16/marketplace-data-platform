"""Deterministic Seller API simulator."""

import asyncio
from datetime import datetime
from typing import Annotated, Literal, TypeVar

from fastapi import FastAPI, HTTPException, Query
from pydantic import AwareDatetime

from api.data import ADVERTISING, ORDERS, PRODUCTS, STOCKS
from api.schemas import Advertising, ErrorResponse, Order, Page, Product, Stock

app = FastAPI(
    title="Marketplace Seller API Simulator",
    version="0.2.0",
    description="Synthetic data only. Error scenarios are enabled per request.",
)
Scenario = Literal["normal", "429", "500", "timeout", "empty"]
ScenarioQuery = Annotated[
    Scenario,
    Query(description="Deterministic simulation: timeout delays the response by 3 seconds."),
]
PageNumber = Annotated[int, Query(ge=1, description="1-based page number")]
PageSize = Annotated[int, Query(ge=1, le=100, description="Records per page")]
UpdatedAt = Annotated[
    AwareDatetime | None,
    Query(description="Inclusive lower bound; ISO 8601 timestamp with timezone required"),
]
T = TypeVar("T", Product, Order, Stock, Advertising)
ERRORS = {
    429: {"model": ErrorResponse, "description": "Simulated rate limit"},
    500: {"model": ErrorResponse, "description": "Simulated server error"},
}


def paginate(records: list[T], page: int, page_size: int, updated_at: datetime | None) -> Page[T]:
    """Filter inclusively, sort by timestamp then ID, and slice the requested page."""
    ordered = sorted(
        (record for record in records if updated_at is None or record.updated_at >= updated_at),
        key=lambda record: (record.updated_at, record.id),
    )
    start = (page - 1) * page_size
    return Page[T](
        items=ordered[start : start + page_size],
        page=page,
        page_size=page_size,
        total=len(ordered),
        next_page=page + 1 if start + page_size < len(ordered) else None,
    )


async def respond(
    records: list[T], page: int, page_size: int, updated_at: datetime | None, scenario: Scenario
) -> Page[T]:
    if scenario == "429":
        raise HTTPException(
            status_code=429, detail="Simulated rate limit", headers={"Retry-After": "1"}
        )
    if scenario == "500":
        raise HTTPException(status_code=500, detail="Simulated server error")
    if scenario == "timeout":
        await asyncio.sleep(3)
    if scenario == "empty":
        return paginate([], page, page_size, updated_at)
    return paginate(records, page, page_size, updated_at)


@app.get("/health")
def health() -> dict[str, str]:
    """Report API process availability, independent of PostgreSQL."""
    return {"status": "ok"}


@app.get("/api/v1/orders", response_model=Page[Order], responses=ERRORS)
async def orders(
    page: PageNumber = 1,
    page_size: PageSize = 50,
    updated_at: UpdatedAt = None,
    scenario: ScenarioQuery = "normal",
) -> Page[Order]:
    """List synthetic orders."""
    return await respond(ORDERS, page, page_size, updated_at, scenario)


@app.get("/api/v1/products", response_model=Page[Product], responses=ERRORS)
async def products(
    page: PageNumber = 1,
    page_size: PageSize = 50,
    updated_at: UpdatedAt = None,
    scenario: ScenarioQuery = "normal",
) -> Page[Product]:
    """List synthetic products."""
    return await respond(PRODUCTS, page, page_size, updated_at, scenario)


@app.get("/api/v1/stocks", response_model=Page[Stock], responses=ERRORS)
async def stocks(
    page: PageNumber = 1,
    page_size: PageSize = 50,
    updated_at: UpdatedAt = None,
    scenario: ScenarioQuery = "normal",
) -> Page[Stock]:
    """List synthetic daily stock snapshots."""
    return await respond(STOCKS, page, page_size, updated_at, scenario)


@app.get("/api/v1/advertising", response_model=Page[Advertising], responses=ERRORS)
async def advertising(
    page: PageNumber = 1,
    page_size: PageSize = 50,
    updated_at: UpdatedAt = None,
    scenario: ScenarioQuery = "normal",
) -> Page[Advertising]:
    """List synthetic daily advertising observations."""
    return await respond(ADVERTISING, page, page_size, updated_at, scenario)
