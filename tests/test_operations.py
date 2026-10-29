from datetime import UTC, datetime, timedelta

import httpx
import pytest

from dashboard.data import freshness_status
from operations.notifications import notify_failure


def test_freshness_states():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert freshness_status(None, now, timedelta(hours=24)) == "missing"
    assert freshness_status(now - timedelta(hours=24), now, timedelta(hours=24)) == "fresh"
    assert freshness_status(now - timedelta(hours=25), now, timedelta(hours=24)) == "stale"
    assert freshness_status(now + timedelta(hours=1), now, timedelta(hours=24)) == "clock skew"
    with pytest.raises(ValueError):
        freshness_status(datetime(2026, 1, 1), now, timedelta(hours=24))


def test_notification_disabled_and_missing_credentials_never_send():
    def forbidden(request):
        raise AssertionError("a request should not have been sent")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        assert not notify_failure("run", "job", env={}, client=client)
        assert not notify_failure("run", "job", env={"TELEGRAM_ENABLED": "true"}, client=client)
        assert not notify_failure(
            "run",
            "job",
            env={
                "TELEGRAM_ENABLED": "false",
                "TELEGRAM_BOT_TOKEN": "fake",
                "TELEGRAM_CHAT_ID": "fake",
            },
            client=client,
        )


def test_notification_enabled_uses_mock_transport_and_hides_errors(caplog):
    requests = []

    def responder(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    env = {
        "TELEGRAM_ENABLED": "true",
        "TELEGRAM_BOT_TOKEN": "fake-token",
        "TELEGRAM_CHAT_ID": "123",
    }
    with httpx.Client(transport=httpx.MockTransport(responder)) as client:
        assert notify_failure("run-1", "marketplace_job", env=env, client=client)
    assert len(requests) == 1
    assert b"run-1" in requests[0].content
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(500))) as client:
        assert not notify_failure("run-1", "job", env=env, client=client)
    assert "fake-token" not in caplog.text


def test_dagster_assets_dependency_and_job_resolution():
    from operations.definitions import defs

    repo = defs.get_repository_def()
    job = repo.get_job("marketplace_job")
    assert set(job.graph.node_names()) >= {
        "marketplace_raw",
        "marketplace_dbt",
    }
    graph = defs.resolve_asset_graph()
    from dagster import AssetKey

    assert AssetKey("marketplace_raw") in graph.get(AssetKey("marketplace_dbt")).parent_keys
