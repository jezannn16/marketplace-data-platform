"""Requires a dedicated PostgreSQL database; drops raw and analytics schemas."""

from datetime import date, timedelta

import psycopg
from fastapi.testclient import TestClient

from api.main import app
from dashboard.data import date_bounds, get_products, query_freshness, query_metrics
from ingestion.pipeline import run


def test_dashboard_filters_and_freshness_on_postgres(test_database_url):
    with psycopg.connect(test_database_url) as conn:
        conn.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
        conn.execute("DROP SCHEMA IF EXISTS raw CASCADE")
        conn.commit()
        try:
            with TestClient(app) as client:
                run(
                    conn,
                    client,
                    "http://testserver",
                    ["orders", "products", "stocks", "advertising"],
                )
            conn.execute("CREATE SCHEMA analytics")
            conn.execute("""CREATE VIEW analytics.stg_products AS SELECT id AS product_id,
                payload->>'sku' AS sku, payload->>'name' AS product_name FROM raw.products""")
            conn.execute("""CREATE VIEW analytics.stg_orders AS SELECT id AS order_id,
                (payload->>'product_id')::bigint AS product_id,
                ((payload->>'created_at')::timestamptz AT TIME ZONE 'UTC')::date AS order_date_utc,
                (payload->>'total_minor')::numeric/100 AS order_total_rub FROM raw.orders""")
            conn.execute("""CREATE VIEW analytics.stg_advertising AS SELECT
                (payload->>'date')::date AS ad_date FROM raw.advertising""")
            conn.execute("""CREATE VIEW analytics.mart_ad_performance AS SELECT
                (payload->>'product_id')::bigint AS product_id, (payload->>'date')::date AS ad_date,
                (payload->>'spend_minor')::numeric/100 AS advertising_spend_rub
                FROM raw.advertising""")
            conn.execute("""CREATE VIEW analytics.mart_inventory_risk AS SELECT
                id AS product_id, payload->>'sku' AS sku, NULL::integer AS stock_quantity,
                NULL::numeric AS stock_coverage_days, NULL::date AS coverage_anchor_date_utc,
                NULL::date AS latest_snapshot_date_utc FROM raw.products""")
            conn.commit()
            assert len(get_products(conn, "analytics")) == 100
            assert date_bounds(conn, "analytics") == (date(2025, 1, 1), date(2025, 1, 30))
            sales, ads, stocks = query_metrics(
                conn, "analytics", date(2025, 1, 1), date(2025, 1, 30), [1]
            )
            assert sales[0] > 0 and sales[1] > 0 and ads[0] > 0
            assert len(stocks) == 1 and stocks[0][0] == 1
            expected = conn.execute(
                "SELECT count(*) FROM analytics.stg_orders "
                "WHERE product_id = 1 AND order_date_utc = %s",
                (date(2025, 1, 1),),
            ).fetchone()[0]
            assert (
                query_metrics(conn, "analytics", date(2025, 1, 1), date(2025, 1, 1), [1])[0][0]
                == expected
            )
            assert all(row[3] == "fresh" for row in query_freshness(conn, timedelta(hours=24)))
        finally:
            conn.rollback()
            conn.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
            conn.execute("DROP SCHEMA IF EXISTS raw CASCADE")
            conn.commit()
