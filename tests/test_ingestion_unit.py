import httpx
import pytest

from ingestion.pipeline import IngestionError, fetch_page


def test_retry_backoff_and_recovery():
    statuses = iter([429, 503, 200])
    delays = []

    def handler(request):
        status = next(statuses)
        return httpx.Response(
            status, headers={"Retry-After": "1"} if status == 429 else {}, json={"ok": True}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_page(
            client,
            "http://test/",
            {},
            max_attempts=3,
            base_delay=0.5,
            max_delay=5,
            sleep=delays.append,
            jitter=lambda low, high: high,
        )
    assert result == {"ok": True}
    assert delays == [1, 1]


def test_unavailable_and_non_retryable_errors():
    attempts = []

    def unavailable(request):
        attempts.append(1)
        raise httpx.ConnectError("offline", request=request)

    with httpx.Client(transport=httpx.MockTransport(unavailable)) as client:
        with pytest.raises(IngestionError, match="after 3 attempts: ConnectError"):
            fetch_page(
                client,
                "http://test/",
                {},
                max_attempts=3,
                base_delay=0,
                max_delay=0,
                sleep=lambda _: None,
            )
    assert len(attempts) == 3
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(400))) as client:
        with pytest.raises(IngestionError, match="Non-retryable HTTP 400"):
            fetch_page(client, "http://test/", {}, max_attempts=3, base_delay=0, max_delay=0)
