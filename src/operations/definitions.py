"""Dagster assets for the actual ingestion pipeline and dbt project."""

import os
import subprocess
from pathlib import Path

import httpx
from dagster import (
    AssetExecutionContext,
    DefaultSensorStatus,
    Definitions,
    MaterializeResult,
    RunFailureSensorContext,
    asset,
    define_asset_job,
    run_failure_sensor,
)

from ingestion.pipeline import MODELS, run
from operations.config import connect_database
from operations.notifications import notify_failure

PROJECT_DIR = Path(__file__).resolve().parents[2] / "dbt"


@asset
def marketplace_raw(context: AssetExecutionContext) -> MaterializeResult:
    scenario = os.getenv("SELLER_API_SCENARIO", "normal")
    if scenario not in {"normal", "429", "500", "timeout"}:
        raise ValueError("SELLER_API_SCENARIO must be normal, 429, 500 or timeout")
    with (
        connect_database() as conn,
        httpx.Client(
            timeout=float(os.getenv("SELLER_API_TIMEOUT_SECONDS", "5")),
            params={"scenario": scenario},
        ) as client,
    ):
        counts = run(conn, client, os.getenv("API_BASE_URL", "http://localhost:8000"), list(MODELS))
    context.log.info("Ingestion completed: %s", counts)
    return MaterializeResult(metadata={"records_read": sum(counts.values()), **counts})


@asset(deps=[marketplace_raw])
def marketplace_dbt(context: AssetExecutionContext) -> MaterializeResult:
    command = [
        "dbt",
        "build",
        "--project-dir",
        str(PROJECT_DIR),
        "--profiles-dir",
        str(PROJECT_DIR),
        "--no-use-colors",
    ]
    result = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
    )
    context.log.info("dbt build output:\n%s", result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"dbt build failed with exit code {result.returncode}")
    return MaterializeResult(metadata={"dbt_exit_code": result.returncode})


marketplace_job = define_asset_job("marketplace_job", selection=[marketplace_raw, marketplace_dbt])


@run_failure_sensor(
    name="marketplace_failure_notifications",
    monitor_all_code_locations=True,
    default_status=DefaultSensorStatus.RUNNING,
)
def marketplace_failure_notifications(context: RunFailureSensorContext):
    if context.dagster_run.job_name != "marketplace_job":
        return
    sent = notify_failure(context.dagster_run.run_id, context.dagster_run.job_name)
    context.log.info("Failure notification sent: %s", sent)


defs = Definitions(
    assets=[marketplace_raw, marketplace_dbt],
    jobs=[marketplace_job],
    sensors=[marketplace_failure_notifications],
)
