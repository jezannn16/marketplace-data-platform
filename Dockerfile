FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY dbt ./dbt
COPY .streamlit ./.streamlit
RUN uv sync --locked --no-dev --no-cache \
    && useradd --create-home --user-group --uid 10001 app \
    && mkdir -p /app/dagster_home \
    && chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000 3000 8501
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
