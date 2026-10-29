"""Uses a dedicated test database; the raw schema is dropped between tests."""

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from api.main import app
from ingestion.pipeline import IngestionError, initialize, run


@pytest.fixture
def db(test_database_url):
    with psycopg.connect(test_database_url) as conn:
        conn.execute("DROP SCHEMA IF EXISTS raw CASCADE")
        conn.commit()
        try:
            yield conn
        finally:
            conn.rollback()
            conn.execute("DROP SCHEMA IF EXISTS raw CASCADE")
            conn.commit()


@pytest.fixture
def api():
    with TestClient(app) as client:
        yield client


def count(conn, name):
    # Test-only fixed identifiers.
    assert name in {"orders", "products", "stocks", "advertising"}
    return conn.execute(f"SELECT count(*) FROM raw.{name}").fetchone()[0]


def test_idempotency_all_resources(db, api):
    expected = {"orders": 1000, "products": 100, "stocks": 3000, "advertising": 3000}
    assert run(db, api, "http://testserver", list(expected)) == expected
    before = {name: count(db, name) for name in expected}
    cursors = db.execute(
        "SELECT resource, cursor_updated_at FROM raw.ingestion_state ORDER BY resource"
    ).fetchall()
    db.commit()
    run(db, api, "http://testserver", list(expected))
    assert {name: count(db, name) for name in expected} == before == expected
    assert (
        db.execute(
            "SELECT resource, cursor_updated_at FROM raw.ingestion_state ORDER BY resource"
        ).fetchall()
        == cursors
    )


def test_failure_mid_pages_then_recovery(db, api):
    initialize(db)
    calls = []

    def fail_second_page(request):
        page = int(request.url.params["page"])
        calls.append(page)
        if page == 2:
            return httpx.Response(500, request=request)
        response = api.get(str(request.url))
        return httpx.Response(response.status_code, json=response.json(), request=request)

    with httpx.Client(transport=httpx.MockTransport(fail_second_page)) as flaky:
        with pytest.raises(IngestionError, match="after 2 attempts: HTTP 500"):
            run(
                db,
                flaky,
                "http://testserver",
                ["stocks"],
                page_size=20,
                max_attempts=2,
                base_delay=0,
                max_delay=0,
            )
    assert calls == [1, 2, 2]
    assert count(db, "stocks") == 20
    assert (
        db.execute("SELECT count(*) FROM raw.ingestion_state WHERE resource = 'stocks'").fetchone()[
            0
        ]
        == 0
    )
    db.commit()
    assert run(db, api, "http://testserver", ["stocks"], page_size=20) == {"stocks": 3000}
    assert count(db, "stocks") == 3000
    assert (
        db.execute("SELECT cursor_updated_at FROM raw.ingestion_state WHERE resource = 'stocks'")
        .fetchone()[0]
        .isoformat()
        .startswith("2025-01-30")
    )


def test_final_page_database_error_rolls_back_checkpoint(db, api):
    initialize(db)
    db.execute("""CREATE FUNCTION raw.fail_stock() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.id = 3000 THEN RAISE EXCEPTION 'simulated database failure'; END IF;
        RETURN NEW; END $$""")
    db.execute(
        "CREATE TRIGGER fail_stock BEFORE INSERT OR UPDATE ON raw.stocks "
        "FOR EACH ROW EXECUTE FUNCTION raw.fail_stock()"
    )
    db.commit()
    with pytest.raises(psycopg.Error):
        run(db, api, "http://testserver", ["stocks"], page_size=100)
    assert count(db, "stocks") == 2900
    assert (
        db.execute("SELECT count(*) FROM raw.ingestion_state WHERE resource = 'stocks'").fetchone()[
            0
        ]
        == 0
    )
    db.execute("DROP TRIGGER fail_stock ON raw.stocks")
    db.commit()
    run(db, api, "http://testserver", ["stocks"])
    assert count(db, "stocks") == 3000


def test_existing_checkpoint_and_equal_timestamps_after_failure(db, api):
    from api.data import PRODUCTS
    from api.main import paginate

    run(db, api, "http://testserver", ["products"], page_size=2)
    checkpoint = db.execute(
        "SELECT cursor_updated_at FROM raw.ingestion_state WHERE resource = 'products'"
    ).fetchone()[0]
    db.commit()
    # Add records at the exact stored watermark, with enough ties to span pages.
    added = [
        PRODUCTS[0].model_copy(update={"id": 101 + i, "sku": f"NEW-{i}", "updated_at": checkpoint})
        for i in range(5)
    ]
    records = PRODUCTS + added
    failing = True

    def source(request):
        params = request.url.params
        page = int(params["page"])
        if failing and page == 2:
            return httpx.Response(503, request=request)
        boundary = __import__("datetime").datetime.fromisoformat(params["updated_at"])
        payload = paginate(records, page, int(params["page_size"]), boundary).model_dump(
            mode="json"
        )
        return httpx.Response(200, json=payload, request=request)

    with httpx.Client(transport=httpx.MockTransport(source)) as client:
        with pytest.raises(IngestionError):
            run(db, client, "http://testserver", ["products"], page_size=2, max_attempts=1)
        assert (
            db.execute(
                "SELECT cursor_updated_at FROM raw.ingestion_state WHERE resource = 'products'"
            ).fetchone()[0]
            == checkpoint
        )
        db.commit()
        failing = False
        run(db, client, "http://testserver", ["products"], page_size=2)
    assert count(db, "products") == 105
