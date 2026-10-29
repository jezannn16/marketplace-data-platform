.PHONY: setup up down test lint

setup:
	uv sync --locked

up:
	docker compose up --build -d

down:
	docker compose down

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
