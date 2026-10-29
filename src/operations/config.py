"""Shared connection configuration; secrets come from the environment."""

import os

import psycopg


def connect_database():
    if url := os.getenv("DATABASE_URL"):
        return psycopg.connect(url)
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=5,
    )
