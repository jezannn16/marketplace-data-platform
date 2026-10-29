import socket
import subprocess
import sys
import time
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from api.data import generate_data
from api.main import app, paginate
from api.schemas import Advertising, Order, Page, Product, Stock

ENDPOINTS = {
    "orders": (1000, Order),
    "products": (100, Product),
    "stocks": (3000, Stock),
    "advertising": (3000, Advertising),
}


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_generation_is_reproducible_and_coherent():
    first = generate_data()
    assert first == generate_data()
    products, orders, stocks, advertising = first
    ids = {product.id for product in products}
    assert [len(records) for records in first] == [100, 1000, 3000, 3000]
    assert all(
        record.product_id in ids for group in (orders, stocks, advertising) for record in group
    )
    assert len({record.observed_at for record in stocks}) == 30
    assert len({record.date for record in advertising}) == 30


def test_paginate_inclusive_filter_and_tie_break():
    products = generate_data()[0]
    boundary = datetime(2025, 1, 2, tzinfo=UTC)
    result = paginate(products, 1, 3, boundary)
    assert [item.id for item in result.items] == [2, 32, 62]
    assert result.next_page == 2
    assert result.total == 96


@pytest.mark.parametrize("resource", ENDPOINTS)
def test_pagination_filter_and_contract(client, resource):
    total, model = ENDPOINTS[resource]
    path = f"/api/v1/{resource}"
    first = client.get(path, params={"page": 1, "page_size": 17}).json()
    second = client.get(path, params={"page": 2, "page_size": 17}).json()
    Page[model].model_validate(first)
    assert first["total"] == total
    assert first["next_page"] == 2
    assert len(first["items"]) == 17
    assert {item["id"] for item in first["items"]}.isdisjoint(
        item["id"] for item in second["items"]
    )
    assert first == client.get(path, params={"page": 1, "page_size": 17}).json()
    boundary = first["items"][0]["updated_at"]
    filtered = client.get(path, params={"updated_at": boundary}).json()
    assert filtered["items"][0] == first["items"][0]
    future = client.get(path, params={"updated_at": "2100-01-01T00:00:00Z"}).json()
    assert future["items"] == [] and future["total"] == 0 and future["next_page"] is None
    beyond = client.get(path, params={"page": 10000}).json()
    assert beyond["items"] == [] and beyond["total"] == total and beyond["next_page"] is None


@pytest.mark.parametrize("resource", ENDPOINTS)
def test_errors_and_validation(client, resource):
    path = f"/api/v1/{resource}"
    rate_limit = client.get(path, params={"scenario": "429"})
    assert rate_limit.status_code == 429
    assert rate_limit.headers["retry-after"] == "1"
    assert rate_limit.json() == {"detail": "Simulated rate limit"}
    server_error = client.get(path, params={"scenario": "500"})
    assert server_error.status_code == 500
    assert server_error.json() == {"detail": "Simulated server error"}
    empty = client.get(path, params={"scenario": "empty", "page": 3}).json()
    assert empty == {"items": [], "page": 3, "page_size": 50, "total": 0, "next_page": None}
    for params in (
        {"page": 0},
        {"page_size": 101},
        {"updated_at": "2025-01-01T00:00:00"},
        {"scenario": "unknown"},
    ):
        assert client.get(path, params=params).status_code == 422


def test_openapi_documents_endpoints_and_errors(client):
    schema = client.get("/openapi.json").json()
    for resource in ENDPOINTS:
        endpoint = schema["paths"][f"/api/v1/{resource}"]["get"]
        assert {"200", "429", "500", "422"} <= endpoint["responses"].keys()
        assert {"page", "page_size", "updated_at", "scenario"} <= {
            param["name"] for param in endpoint["parameters"]
        }


def test_timeout_over_real_http():
    # A real socket is needed: in-process ASGI transports do not enforce read timeouts.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                if httpx.get(f"{url}/health", timeout=0.5).status_code == 200:
                    break
            except httpx.RequestError:
                pass
            if time.monotonic() > deadline or process.poll() is not None:
                pytest.fail("Test server did not start")
            time.sleep(0.05)
        with pytest.raises(httpx.ReadTimeout):
            httpx.get(f"{url}/api/v1/orders", params={"scenario": "timeout"}, timeout=0.2)
    finally:
        process.terminate()
        try:
            process.wait(timeout=6)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@pytest.mark.parametrize("resource", ENDPOINTS)
def test_all_pages_are_ordered_and_complete(client, resource):
    path = f"/api/v1/{resource}"
    page = 1
    items = []
    while page is not None:
        result = client.get(path, params={"page": page, "page_size": 100}).json()
        items.extend(result["items"])
        page = result["next_page"]
    keys = [(item["updated_at"], item["id"]) for item in items]
    assert keys == sorted(keys)
    assert len({item["id"] for item in items}) == len(items) == ENDPOINTS[resource][0]
    boundary = items[len(items) // 2]["updated_at"]
    filtered = client.get(path, params={"updated_at": boundary, "page_size": 100}).json()
    expected = [item for item in items if item["updated_at"] >= boundary]
    assert filtered["total"] == len(expected)
    assert filtered["items"] == expected[:100]
