"""Deterministic, entirely synthetic marketplace data."""

from datetime import UTC, datetime, timedelta
from random import Random

from api.schemas import Advertising, Order, Product, Stock

SEED = 20261029
BASE_TIME = datetime(2025, 1, 1, tzinfo=UTC)


def generate_data() -> tuple[list[Product], list[Order], list[Stock], list[Advertising]]:
    """Create the same records on every call, without touching global random state."""
    rng = Random(SEED)
    categories = ("Tops", "Dresses", "Shoes", "Accessories")
    statuses = ("created", "shipped", "delivered", "cancelled")
    products = [
        Product(
            id=i,
            sku=f"SYN-{i:04d}",
            name=f"Synthetic {categories[(i - 1) % 4]} {i}",
            category=categories[(i - 1) % 4],
            price_minor=rng.randint(100_000, 1_000_000),
            updated_at=BASE_TIME + timedelta(days=(i - 1) % 30),
        )
        for i in range(1, 101)
    ]
    orders = []
    for i in range(1, 1001):
        product = products[rng.randrange(len(products))]
        quantity = rng.randint(1, 3)
        created = BASE_TIME + timedelta(minutes=i * 37)
        orders.append(
            Order(
                id=i,
                product_id=product.id,
                quantity=quantity,
                total_minor=product.price_minor * quantity,
                status=statuses[rng.randrange(len(statuses))],
                created_at=created,
                updated_at=created + timedelta(hours=rng.randrange(72)),
            )
        )
    stocks = []
    advertising = []
    for day in range(30):
        timestamp = BASE_TIME + timedelta(days=day)
        for product in products:
            record_id = day * len(products) + product.id
            stocks.append(
                Stock(
                    id=record_id,
                    product_id=product.id,
                    warehouse="SYN-WH-01",
                    quantity=rng.randint(0, 200),
                    observed_at=timestamp,
                    updated_at=timestamp,
                )
            )
            impressions = rng.randint(0, 5000)
            advertising.append(
                Advertising(
                    id=record_id,
                    product_id=product.id,
                    campaign_id=product.id,
                    date=timestamp.date(),
                    spend_minor=rng.randint(0, 100_000),
                    impressions=impressions,
                    clicks=rng.randint(0, impressions),
                    updated_at=timestamp,
                )
            )
    return products, orders, stocks, advertising


PRODUCTS, ORDERS, STOCKS, ADVERTISING = generate_data()
