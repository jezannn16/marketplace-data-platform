"""Replay-safe ingestion of the Seller API into PostgreSQL."""

import json
import logging
import random
import time
import uuid
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Callable

import httpx
import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from api.schemas import Advertising, Order, Page, Product, Stock

MODELS = {"orders": Order, "products": Product, "stocks": Stock, "advertising": Advertising}
logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """A source or ingestion operation failed without advancing its checkpoint."""


def _log(event: str, **values: object) -> None:
    logger.info(json.dumps({"event": event, **values}, default=str))


def initialize(conn: psycopg.Connection) -> None:
    with conn.transaction():
        conn.execute("CREATE SCHEMA IF NOT EXISTS raw")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS raw.ingestion_state (
                resource text PRIMARY KEY, cursor_updated_at timestamptz NOT NULL,
                completed_at timestamptz NOT NULL DEFAULT now()
            )"""
        )
        for resource in MODELS:
            conn.execute(
                sql.SQL("""CREATE TABLE IF NOT EXISTS raw.{} (
                    id bigint PRIMARY KEY, updated_at timestamptz NOT NULL,
                    payload jsonb NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now()
                )""").format(sql.Identifier(resource))
            )


def retry_after_seconds(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            return max(0.0, (date - datetime.now(date.tzinfo)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0.0


def fetch_page(
    client: httpx.Client,
    url: str,
    params: dict,
    *,
    max_attempts: int,
    base_delay: float,
    max_delay: float,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
    run_id: str = "",
    resource: str = "",
) -> dict:
    """Retry transport failures, 429 and 5xx with bounded exponential backoff and jitter."""
    reason = "unknown error"
    for attempt in range(1, max_attempts + 1):
        retry_after = 0.0
        try:
            response = client.get(url, params=params)
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                reason = f"HTTP {response.status_code}"
                retry_after = retry_after_seconds(response.headers.get("Retry-After"))
            elif response.is_error:
                raise IngestionError(f"Non-retryable HTTP {response.status_code}")
            else:
                try:
                    return response.json()
                except ValueError as exc:
                    raise IngestionError("API returned invalid JSON") from exc
        except httpx.TransportError as exc:
            reason = type(exc).__name__
        if attempt == max_attempts:
            raise IngestionError(f"API unavailable after {attempt} attempts: {reason}")
        delay = min(
            max_delay, max(retry_after, jitter(0, min(max_delay, base_delay * 2 ** (attempt - 1))))
        )
        logger.warning(
            json.dumps(
                {
                    "event": "api_retry",
                    "run_id": run_id,
                    "resource": resource,
                    "reason": reason,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "delay_seconds": delay,
                }
            )
        )
        sleep(delay)
    raise AssertionError("unreachable")


def ingest_resource(
    conn: psycopg.Connection,
    client: httpx.Client,
    base_url: str,
    resource: str,
    *,
    run_id: str,
    page_size: int = 100,
    max_attempts: int = 4,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
) -> int:
    if resource not in MODELS:
        raise ValueError(f"Unknown resource: {resource}")
    if not 1 <= page_size <= 100 or max_attempts < 1 or base_delay < 0 or max_delay < 0:
        raise ValueError("Invalid pagination or retry settings")
    start = time.monotonic()
    count = 0
    acquired = False
    try:
        # Session lock prevents concurrent runs from racing on this resource's checkpoint.
        acquired = conn.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
            (f"marketplace-ingestion:{resource}",),
        ).fetchone()[0]
        conn.commit()
        if not acquired:
            raise IngestionError(f"Resource {resource} is already being ingested")
        row = conn.execute(
            "SELECT cursor_updated_at FROM raw.ingestion_state WHERE resource = %s", (resource,)
        ).fetchone()
        checkpoint = row[0] if row else None
        conn.commit()
        page = 1
        max_seen = checkpoint
        last_key = None
        expected_total = None
        while True:
            params = {"page": page, "page_size": page_size}
            if checkpoint is not None:
                params["updated_at"] = checkpoint.isoformat()
            payload = fetch_page(
                client,
                f"{base_url.rstrip('/')}/api/v1/{resource}",
                params,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                run_id=run_id,
                resource=resource,
            )
            try:
                result = Page[MODELS[resource]].model_validate(payload)
            except (ValidationError, TypeError) as exc:
                raise IngestionError(f"Invalid API response for {resource} page {page}") from exc
            if result.page != page or result.page_size != page_size or result.total < 0:
                raise IngestionError(f"Inconsistent pagination metadata for {resource} page {page}")
            if expected_total is None:
                expected_total = result.total
            if result.total != expected_total or len(result.items) != min(
                page_size, max(0, expected_total - count)
            ):
                raise IngestionError(f"Inconsistent page size or total for {resource} page {page}")
            has_more = count + len(result.items) < expected_total
            if result.next_page != (page + 1 if has_more else None):
                raise IngestionError(f"Invalid next_page for {resource} page {page}")
            for item in result.items:
                key = (item.updated_at, item.id)
                if (last_key is not None and key <= last_key) or (
                    checkpoint and item.updated_at < checkpoint
                ):
                    raise IngestionError(f"Unstable ordering or cursor for {resource} page {page}")
                last_key = key
                max_seen = item.updated_at if max_seen is None else max(max_seen, item.updated_at)
            with conn.transaction():
                query = sql.SQL("""INSERT INTO raw.{} (id, updated_at, payload)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET updated_at = EXCLUDED.updated_at,
                        payload = EXCLUDED.payload, ingested_at = now()
                    WHERE EXCLUDED.updated_at >= {}.updated_at""").format(
                    sql.Identifier(resource), sql.Identifier(resource)
                )
                with conn.cursor() as cursor:
                    cursor.executemany(
                        query,
                        [
                            (item.id, item.updated_at, Jsonb(item.model_dump(mode="json")))
                            for item in result.items
                        ],
                    )
                # A checkpoint is committed only after every page has been validated and stored.
                if not has_more and max_seen is not None:
                    conn.execute(
                        """INSERT INTO raw.ingestion_state (resource, cursor_updated_at)
                           VALUES (%s, %s) ON CONFLICT (resource) DO UPDATE
                           SET cursor_updated_at = EXCLUDED.cursor_updated_at,
                               completed_at = now()""",
                        (resource, max_seen),
                    )
            count += len(result.items)
            if not has_more:
                break
            page += 1
        _log(
            "resource_completed",
            run_id=run_id,
            resource=resource,
            records=count,
            duration_seconds=round(time.monotonic() - start, 3),
            checkpoint=max_seen,
        )
        return count
    except Exception as exc:
        conn.rollback()
        _log(
            "resource_failed",
            run_id=run_id,
            resource=resource,
            records=count,
            duration_seconds=round(time.monotonic() - start, 3),
            error=type(exc).__name__,
        )
        raise
    finally:
        if acquired:
            conn.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                (f"marketplace-ingestion:{resource}",),
            )
            conn.commit()


def run(
    conn: psycopg.Connection, client: httpx.Client, base_url: str, resources: list[str], **options
) -> dict[str, int]:
    if conn.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("Ingestion requires a connection with no active transaction")
    run_id = str(uuid.uuid4())
    start = time.monotonic()
    counts = {}
    _log("run_started", run_id=run_id, resources=resources)
    try:
        initialize(conn)
        for resource in resources:
            counts[resource] = ingest_resource(
                conn, client, base_url, resource, run_id=run_id, **options
            )
    except Exception:
        _log(
            "run_failed",
            run_id=run_id,
            records=sum(counts.values()),
            duration_seconds=round(time.monotonic() - start, 3),
        )
        raise
    _log(
        "run_completed",
        run_id=run_id,
        records=sum(counts.values()),
        duration_seconds=round(time.monotonic() - start, 3),
    )
    return counts
