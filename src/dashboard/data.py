"""Bounded, parameterized dashboard queries and freshness classification."""

from datetime import datetime, timedelta, timezone

from psycopg import sql

RESOURCES = ("orders", "products", "stocks", "advertising")


def freshness_status(completed_at: datetime | None, now: datetime, max_age: timedelta) -> str:
    if completed_at is None:
        return "missing"
    if completed_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("Freshness timestamps must be timezone-aware")
    if completed_at > now + timedelta(minutes=5):
        return "clock skew"
    return "stale" if now - completed_at > max_age else "fresh"


def relation(schema: str, name: str):
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(name))


def get_products(conn, schema: str):
    return conn.execute(
        sql.SQL("SELECT product_id, sku, product_name FROM {} ORDER BY product_id").format(
            relation(schema, "stg_products")
        )
    ).fetchall()


def date_bounds(conn, schema: str):
    return conn.execute(
        sql.SQL(
            "SELECT min(d), max(d) FROM (SELECT order_date_utc AS d FROM {} "
            "UNION ALL SELECT ad_date AS d FROM {}) x"
        ).format(relation(schema, "stg_orders"), relation(schema, "stg_advertising"))
    ).fetchone()


def query_metrics(conn, schema: str, start, end, product_ids: list[int] | None):
    sales = conn.execute(
        sql.SQL("""SELECT count(*), sum(order_total_rub),
            sum(order_total_rub) / nullif(count(*), 0)
            FROM {} WHERE order_date_utc BETWEEN %s AND %s
            AND (%s::bigint[] IS NULL OR product_id = ANY(%s::bigint[]))""").format(
            relation(schema, "stg_orders")
        ),
        (start, end, product_ids, product_ids),
    ).fetchone()
    ad = conn.execute(
        sql.SQL("""SELECT sum(advertising_spend_rub) FROM {}
            WHERE ad_date BETWEEN %s AND %s
            AND (%s::bigint[] IS NULL OR product_id = ANY(%s::bigint[]))""").format(
            relation(schema, "mart_ad_performance")
        ),
        (start, end, product_ids, product_ids),
    ).fetchone()
    inventory = conn.execute(
        sql.SQL("""SELECT product_id, sku, stock_quantity, stock_coverage_days,
            coverage_anchor_date_utc, latest_snapshot_date_utc FROM {}
            WHERE (%s::bigint[] IS NULL OR product_id = ANY(%s::bigint[]))
            ORDER BY product_id""").format(relation(schema, "mart_inventory_risk")),
        (product_ids, product_ids),
    ).fetchall()
    return sales, ad, inventory


def query_freshness(conn, max_age: timedelta, now: datetime | None = None):
    rows = conn.execute(
        "SELECT resource, completed_at, cursor_updated_at FROM raw.ingestion_state"
    ).fetchall()
    by_resource = {r[0]: (r[1], r[2]) for r in rows}
    now = now or datetime.now(timezone.utc)
    return [
        (
            name,
            *by_resource.get(name, (None, None)),
            freshness_status(by_resource.get(name, (None, None))[0], now, max_age),
        )
        for name in RESOURCES
    ]
