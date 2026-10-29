"""Command-line entry point for the ingestion pipeline."""

import argparse
import logging
import os
import sys

import httpx
import psycopg

from ingestion.pipeline import MODELS, run


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Seller API records into PostgreSQL")
    parser.add_argument(
        "--resource",
        action="append",
        choices=MODELS,
        help="Repeat to select resources; default: all",
    )
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout in seconds")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    api_url = os.environ.get("API_BASE_URL", "http://localhost:8000")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required; see README.md", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("--timeout must be positive", file=sys.stderr)
        return 2
    try:
        with psycopg.connect(database_url) as conn, httpx.Client(timeout=args.timeout) as client:
            run(
                conn,
                client,
                api_url,
                args.resource or list(MODELS),
                page_size=args.page_size,
                max_attempts=args.max_attempts,
            )
    except (psycopg.Error, httpx.HTTPError, ValueError, RuntimeError) as exc:
        print(f"Ingestion failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Ingestion failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
