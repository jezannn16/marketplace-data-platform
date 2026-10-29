"""Start the demo locally on macOS when Docker Desktop is unavailable.

Requires an existing .env, .venv, and PostgreSQL binaries at LOCAL_PG_BIN.
The commands do not install software or start on login.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import psycopg
from dotenv import dotenv_values
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home() / ".local/share/marketplace-data-platform"
BIN = Path(os.environ.get("LOCAL_PG_BIN", str(STATE / "postgresql-16/bin")))
DATA = STATE / "postgres-data"
LOGS = STATE / "logs"
PIDS = STATE / "pids"
DAGSTER_HOME = STATE / "dagster"
RUNTIME = STATE / "runtime"
PYTHON_BIN = ROOT / ".venv/bin"
MARKERS = {
    "api": "api.main:app",
    "dagster": "operations.definitions",
    "dashboard": "src/dashboard/app.py",
}


def environment() -> dict[str, str]:
    values = dotenv_values(ROOT / ".env")
    env = {**os.environ, **{k: v for k, v in values.items() if v is not None}}
    if not all(env.get(k) for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")):
        raise RuntimeError("Set POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB in .env")
    port = int(env.get("LOCAL_POSTGRES_PORT", env.get("POSTGRES_PORT", "5432")))
    if not 1 <= port <= 65535:
        raise ValueError("Local PostgreSQL port must be between 1 and 65535")
    env.update(
        {
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": str(port),
            "DBT_HOST": "127.0.0.1",
            "DBT_PORT": str(port),
            "API_BASE_URL": f"http://127.0.0.1:{env.get('API_PORT', '8000')}",
            "DAGSTER_HOME": str(DAGSTER_HOME),
            "PATH": f"{PYTHON_BIN}{os.pathsep}{env.get('PATH', '')}",
            "TELEGRAM_ENABLED": "false",
        }
    )
    # Do not accidentally connect to an unrelated external database.
    env.pop("DATABASE_URL", None)
    return env


def command(args: list[str], env: dict[str, str], *, check: bool = True):
    return subprocess.run(args, env=env, cwd=ROOT, text=True, capture_output=True, check=check)


def port_busy(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def managed_pid(name: str) -> int | None:
    try:
        pid = int((PIDS / f"{name}.pid").read_text().strip())
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True
        )
        if result.returncode == 0 and MARKERS[name] in result.stdout and os.getpgid(pid) == pid:
            return pid
    except (OSError, ValueError):
        pass
    return None


def healthy(url: str) -> bool:
    try:
        with urlopen(url, timeout=2) as response:
            return response.status == 200
    except (URLError, TimeoutError, OSError):
        return False


def wait_http(url: str, process: subprocess.Popen | None = None) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if healthy(url):
            return
        if process is not None and process.poll() is not None:
            break
        time.sleep(0.25)
    raise RuntimeError(f"Service did not become ready: {url}; see {LOGS}")


def postgres(env: dict[str, str]) -> None:
    if not (BIN / "postgres").is_file():
        raise RuntimeError(f"PostgreSQL binaries not found in {BIN}")
    if not (DATA / "PG_VERSION").exists():
        if DATA.exists() and any(DATA.iterdir()):
            raise RuntimeError(f"Refusing to initialize nonempty directory {DATA}")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=STATE) as secret:
            secret.write(env["POSTGRES_PASSWORD"] + "\n")
            secret.flush()
            command(
                [
                    str(BIN / "initdb"),
                    "-D",
                    str(DATA),
                    "-U",
                    env["POSTGRES_USER"],
                    "--auth=scram-sha-256",
                    "--encoding=UTF8",
                    "--no-locale",
                    "--pwfile",
                    secret.name,
                ],
                env,
            )
    status = command([str(BIN / "pg_ctl"), "-D", str(DATA), "status"], env, check=False)
    if status.returncode != 0:
        if port_busy(int(env["POSTGRES_PORT"])):
            raise RuntimeError("Local PostgreSQL port is in use by another process")
        options = f"-h 127.0.0.1 -p {env['POSTGRES_PORT']} -k /tmp"
        command(
            [
                str(BIN / "pg_ctl"),
                "-D",
                str(DATA),
                "-l",
                str(LOGS / "postgres.log"),
                "-o",
                options,
                "-w",
                "start",
            ],
            env,
        )
    with psycopg.connect(
        host="127.0.0.1",
        port=env["POSTGRES_PORT"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
        dbname="postgres",
        autocommit=True,
    ) as conn:
        if not conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (env["POSTGRES_DB"],)
        ).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(env["POSTGRES_DB"])))


def start_service(name: str, args: list[str], url: str, port: int, env: dict[str, str]) -> None:
    if managed_pid(name):
        wait_http(url)
        print(f"{name}: already running")
        return
    if port_busy(port):
        raise RuntimeError(f"Port {port} is in use by an unmanaged process; not changing it")
    with (LOGS / f"{name}.log").open("a") as log:
        process = subprocess.Popen(
            args,
            cwd=RUNTIME if name == "dagster" else ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    (PIDS / f"{name}.pid").write_text(str(process.pid))
    wait_http(url, process)
    print(f"{name}: ready")


def start(env: dict[str, str]) -> None:
    if sys.platform != "darwin":
        raise RuntimeError("This local fallback is intended for macOS")
    for path in (STATE, LOGS, PIDS, DAGSTER_HOME, RUNTIME):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (RUNTIME / ".env").exists():
        raise RuntimeError("Remove .env from the local runtime directory before starting Dagster")
    config = DAGSTER_HOME / "dagster.yaml"
    if not config.exists():
        shutil.copyfile(ROOT / "config/dagster.yaml", config)
    postgres(env)
    print("postgres: ready")
    api_port, dagster_port, dashboard_port = (
        int(env.get(name, default))
        for name, default in (
            ("API_PORT", "8000"),
            ("DAGSTER_PORT", "3000"),
            ("DASHBOARD_PORT", "8501"),
        )
    )
    start_service(
        "api",
        [
            str(PYTHON_BIN / "uvicorn"),
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
        ],
        f"http://127.0.0.1:{api_port}/health",
        api_port,
        env,
    )
    start_service(
        "dagster",
        [
            str(PYTHON_BIN / "dagster"),
            "dev",
            "--host",
            "127.0.0.1",
            "--port",
            str(dagster_port),
            "--module-name",
            "operations.definitions",
        ],
        f"http://127.0.0.1:{dagster_port}/server_info",
        dagster_port,
        env,
    )
    print("Running ingestion and dbt build; this may take a moment...")
    with (LOGS / "job.log").open("a") as log:
        result = subprocess.run(
            [
                str(PYTHON_BIN / "dagster"),
                "job",
                "execute",
                "-m",
                "operations.definitions",
                "-j",
                "marketplace_job",
            ],
            cwd=RUNTIME,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    if result.returncode:
        raise RuntimeError(f"Dagster job failed; see {LOGS / 'job.log'}")
    start_service(
        "dashboard",
        [
            str(PYTHON_BIN / "streamlit"),
            "run",
            "src/dashboard/app.py",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(dashboard_port),
            "--server.headless",
            "true",
        ],
        f"http://127.0.0.1:{dashboard_port}/_stcore/health",
        dashboard_port,
        env,
    )
    print(
        f"Dashboard: http://127.0.0.1:{dashboard_port} | Dagster: http://127.0.0.1:{dagster_port}"
    )


def stop(env: dict[str, str]) -> None:
    for name in ("dashboard", "dagster", "api"):
        if pid := managed_pid(name):
            os.killpg(pid, signal.SIGTERM)
            print(f"{name}: stopping")
        (PIDS / f"{name}.pid").unlink(missing_ok=True)
    if (DATA / "PG_VERSION").exists():
        result = command(
            [str(BIN / "pg_ctl"), "-D", str(DATA), "-m", "fast", "-w", "stop"], env, check=False
        )
        if result.returncode == 0:
            print("postgres: stopped")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop"), nargs="?", default="start")
    args = parser.parse_args()
    try:
        env = environment()
        if args.action == "start":
            start(env)
        else:
            stop(env)
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError, psycopg.Error) as exc:
        print(f"Local startup failed: {type(exc).__name__}; check {LOGS}", file=sys.stderr)
        # Avoid printing subprocess command output, which may include secrets.
        if isinstance(exc, RuntimeError):
            print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
