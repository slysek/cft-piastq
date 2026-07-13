from __future__ import annotations

import httpx
import pytest

from cft_piastq import (
    DashboardAuthError,
    ManagedJobError,
    PiastQClient,
    PiastQConfigurationError,
    PiastQJob,
)

BASE_URL = "https://dashboard.example"


def test_retrieve_job_validates_id_and_reads_fresh_result() -> None:
    job_reads = 0
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal job_reads
        requests.append(request)
        if request.url.path == "/api/runner/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/runner/jobs/srv managed/1":
            assert request.method == "GET"
            job_reads += 1
            statuses = ("queued", "running", "succeeded")
            return httpx.Response(
                200,
                json={
                    "server_job_id": "srv managed/1",
                    "status": statuses[min(job_reads - 1, 2)],
                    "shots": 200,
                },
            )
        if request.url.path == "/api/runner/jobs/srv managed/1/result":
            return httpx.Response(
                200,
                json={
                    "server_job_id": "srv managed/1",
                    "status": "succeeded",
                    "shots": 200,
                    "quasi_dists": [{"0": 0.5, "3": 0.5}],
                    "metadata": [{"circuit_index": 0}],
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = PiastQClient(
        mode="managed",
        dashboard_api_url=BASE_URL,
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )

    job = client.retrieve_job("srv managed/1")

    assert isinstance(job, PiastQJob)
    assert job.job_id() == "srv managed/1"
    assert job.status() == "running"
    result = job.result(timeout=1.0, poll_interval=0.001)
    assert dict(result.quasi_dists[0]) == {0: 0.5, 3: 0.5}
    job_request = requests[1]
    assert job_request.url.raw_path == b"/api/runner/jobs/srv%20managed%2F1"


def test_retrieved_job_can_be_cancelled() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/runner/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/runner/jobs/server-job-1":
            return httpx.Response(
                200,
                json={"server_job_id": "server-job-1", "status": "running"},
            )
        if request.url.path == "/api/runner/jobs/server-job-1/cancel":
            assert request.method == "POST"
            assert request.headers["x-dashboard-api-key"] == "dashboard-key"
            return httpx.Response(
                200,
                json={"server_job_id": "server-job-1", "status": "cancelled"},
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = PiastQClient(
        mode="managed",
        dashboard_api_url=BASE_URL,
        dashboard_api_key="dashboard-key",
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )

    job = client.retrieve_job("server-job-1")

    assert job.cancel() == "cancelled"
    assert [request.url.path for request in requests] == [
        "/api/runner/health",
        "/api/runner/jobs/server-job-1",
        "/api/runner/jobs/server-job-1/cancel",
    ]


@pytest.mark.parametrize("job_id", ["", "   ", None, 123])
def test_retrieve_job_rejects_invalid_ids_before_job_request(job_id: object) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/runner/health"
        return httpx.Response(200, json={"status": "ok"})

    client = PiastQClient(
        mode="managed",
        dashboard_api_url=BASE_URL,
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )

    with pytest.raises(PiastQConfigurationError, match="job_id"):
        client.retrieve_job(job_id)  # type: ignore[arg-type]

    assert [request.url.path for request in requests] == ["/api/runner/health"]


@pytest.mark.parametrize("mode", ["direct", "fake"])
def test_retrieve_job_requires_resolved_managed_mode(mode: str) -> None:
    kwargs: dict[str, object] = {"mode": mode, "verbose": False}
    if mode == "direct":
        kwargs["token"] = "local-direct-token"
    client = PiastQClient(**kwargs)  # type: ignore[arg-type]

    with pytest.raises(PiastQConfigurationError, match="managed"):
        client.retrieve_job("server-job-1")


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [(404, ManagedJobError), (403, DashboardAuthError)],
)
def test_retrieve_job_preserves_dashboard_errors(
    status_code: int,
    error_type: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/runner/health":
            return httpx.Response(200, json={"status": "ok"})
        assert request.url.path == "/api/runner/jobs/missing-job"
        return httpx.Response(status_code, json={"detail": "job is unavailable"})

    client = PiastQClient(
        mode="managed",
        dashboard_api_url=BASE_URL,
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )

    with pytest.raises(error_type, match="job is unavailable"):
        client.retrieve_job("missing-job")
