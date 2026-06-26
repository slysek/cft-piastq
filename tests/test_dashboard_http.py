from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from cft_piastq.errors import (
    DashboardAuthError,
    DashboardUnavailableError,
    ManagedJobError,
    PiastQConfigurationError,
)
from cft_piastq.http import DashboardClient

BASE_URL = "https://dashboard.example"
DASHBOARD_KEY = "dashboard-key"
PCSS_TOKEN = "pcss-token-from-local-env"


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    api_key: str | None = DASHBOARD_KEY,
) -> DashboardClient:
    return DashboardClient(
        base_url=BASE_URL,
        api_key=api_key,
        transport=httpx.MockTransport(handler),
    )


def assert_dashboard_request_headers(request: httpx.Request) -> None:
    assert request.headers["x-dashboard-api-key"] == DASHBOARD_KEY
    assert "authorization" not in request.headers
    assert PCSS_TOKEN not in ";".join(request.headers.values())


def test_health_success_returns_dashboard_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.path == "/api/runner/health"
        return httpx.Response(200, json={"status": "ok"})

    client = make_client(handler)

    assert client.health() == {"status": "ok"}
    assert len(requests) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "ok", "runner_available": False},
        {"status": "ok", "managed_mode_enabled": False},
    ],
)
def test_health_raises_unavailable_when_dashboard_reports_runner_disabled(
    payload: dict[str, object],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/runner/health"
        return httpx.Response(200, json=payload)

    client = make_client(handler)

    with pytest.raises(DashboardUnavailableError, match="not available"):
        client.health()


def test_unavailable_health_raises_dashboard_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/runner/health"
        return httpx.Response(503, json={"detail": "maintenance window"})

    client = make_client(handler)

    with pytest.raises(DashboardUnavailableError, match="maintenance window"):
        client.health()


@pytest.mark.parametrize("status_code", [401, 403])
def test_auth_errors_raise_dashboard_auth_error(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/runner/health"
        return httpx.Response(status_code, json={"detail": "bad dashboard key"})

    client = make_client(handler)

    with pytest.raises(DashboardAuthError, match="bad dashboard key"):
        client.health()


def test_submit_job_posts_payload_and_returns_dashboard_job() -> None:
    payload = {"program": {"format": "qasm3", "source": "OPENQASM 3;"}, "shots": 10}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/runner/jobs"
        assert json.loads(request.content) == payload
        assert_dashboard_request_headers(request)
        return httpx.Response(201, json={"id": "server-job-1", "status": "queued"})

    client = make_client(handler)

    assert client.submit_job(payload) == {"id": "server-job-1", "status": "queued"}


def test_submit_job_failure_raises_sanitized_managed_job_error() -> None:
    leaked_dashboard_key = DASHBOARD_KEY
    leaked_pcss_token = "secret-local-pcss-token"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/runner/jobs"
        return httpx.Response(
            500,
            json={
                "detail": (
                    "runner failed with "
                    f"PCSS_TOKEN={leaked_pcss_token} "
                    f"CFT_PIASTQ_DASHBOARD_API_KEY={leaked_dashboard_key}"
                )
            },
        )

    client = make_client(handler)

    with pytest.raises(ManagedJobError) as exc_info:
        client.submit_job({"shots": 10})

    message = str(exc_info.value)
    assert "runner failed" in message
    assert leaked_pcss_token not in message
    assert leaked_dashboard_key not in message
    assert "[REDACTED]" in message


def test_submit_job_failure_recursively_sanitizes_object_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/runner/jobs"
        return httpx.Response(
            500,
            json={
                "detail": {
                    "PCSS_TOKEN": "short-secret",
                    "api_key": "short-key",
                    "context": "runner failed",
                }
            },
        )

    client = make_client(handler)

    with pytest.raises(ManagedJobError) as exc_info:
        client.submit_job({"shots": 10})

    message = str(exc_info.value)
    assert "short-secret" not in message
    assert "short-key" not in message
    assert "runner failed" in message
    assert "[REDACTED]" in message


def test_get_job_reads_fresh_status_on_every_call() -> None:
    responses = [
        {"id": "server-job-1", "status": "queued"},
        {"id": "server-job-1", "status": "running"},
    ]
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.path == "/api/runner/jobs/server-job-1"
        return httpx.Response(200, json=responses.pop(0))

    client = make_client(handler)

    assert client.get_job("server-job-1") == {"id": "server-job-1", "status": "queued"}
    assert client.get_job("server-job-1") == {
        "id": "server-job-1",
        "status": "running",
    }
    assert len(requests) == 2


def test_get_result_reads_dashboard_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/runner/jobs/server-job-1/result"
        return httpx.Response(200, json={"counts": {"0": 8, "1": 2}})

    client = make_client(handler)

    assert client.get_result("server-job-1") == {"counts": {"0": 8, "1": 2}}


def test_cancel_job_posts_cancel_request_with_dashboard_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/runner/jobs/server-job-1/cancel"
        assert_dashboard_request_headers(request)
        return httpx.Response(200, json={"id": "server-job-1", "status": "cancelled"})

    client = make_client(handler)

    assert client.cancel_job("server-job-1") == {
        "id": "server-job-1",
        "status": "cancelled",
    }


def test_cancel_job_requires_dashboard_api_key() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("cancel should fail before sending a dashboard request")

    client = make_client(handler, api_key=None)

    with pytest.raises(PiastQConfigurationError, match="dashboard API key"):
        client.cancel_job("server-job-1")


def test_get_noise_model_reads_latest_noise_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/noise-model/latest"
        return httpx.Response(200, json={"name": "latest-noise"})

    client = make_client(handler)

    assert client.get_noise_model() == {"name": "latest-noise"}
