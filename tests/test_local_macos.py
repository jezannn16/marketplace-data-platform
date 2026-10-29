import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "local_macos", Path(__file__).resolve().parents[1] / "scripts/local_macos.py"
)
local_macos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local_macos)


def test_local_environment_does_not_use_external_database_or_enable_telegram(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "POSTGRES_USER=demo\nPOSTGRES_PASSWORD=fake\nPOSTGRES_DB=demo\n"
        "POSTGRES_PORT=5432\nLOCAL_POSTGRES_PORT=55433\n"
        "DATABASE_URL=postgresql://example.com/remote\nTELEGRAM_ENABLED=true\n"
    )
    monkeypatch.setattr(local_macos, "ROOT", tmp_path)
    env = local_macos.environment()
    assert "DATABASE_URL" not in env
    assert env["POSTGRES_HOST"] == "127.0.0.1"
    assert env["POSTGRES_PORT"] == env["DBT_PORT"] == "55433"
    assert env["TELEGRAM_ENABLED"] == "false"


def test_local_environment_rejects_invalid_port(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "POSTGRES_USER=demo\nPOSTGRES_PASSWORD=fake\nPOSTGRES_DB=demo\n"
        "LOCAL_POSTGRES_PORT=1;invalid\n"
    )
    monkeypatch.setattr(local_macos, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        local_macos.environment()
