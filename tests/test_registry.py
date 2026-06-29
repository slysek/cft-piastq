from __future__ import annotations

import json
from pathlib import Path

import httpx


def test_registry_creates_schema_and_sanitizes_direct_job_storage(
    tmp_path: Path,
) -> None:
    from cft_piastq.registry import DirectJobRegistry

    registry_path = tmp_path / "nested" / "jobs.sqlite3"
    registry = DirectJobRegistry(registry_path)

    local_job_id = registry.insert_job(
        provider_job_id="provider-job-1",
        owner="owner token=owner-secret",
        cft_job_name="Bell job PCSS_TOKEN=name-secret",
        cft_description="Description Authorization: Bearer desc-secret",
        status="queued",
        shots=100,
        circuit_count=1,
        metadata={
            "token": "metadata-secret",
            "qpy_base64": "QPY-SHOULD-NOT-PERSIST",
            "safe": "value",
        },
    )
    registry.update_status(
        local_job_id,
        "failed",
        error="provider failed Authorization: Bearer status-secret",
    )
    registry.record_event_failure(
        local_job_id,
        "failed",
        error=RuntimeError("event failed PCSS_TOKEN=event-secret"),
        payload={
            "authorization": "Bearer payload-secret",
            "qpy_base64": "QPY-EVENT-SHOULD-NOT-PERSIST",
        },
    )

    assert registry_path.exists()
    assert registry_path.parent.exists()

    job = registry.get_job(local_job_id)
    assert job is not None
    assert job["local_job_id"] == local_job_id
    assert job["provider_job_id"] == "provider-job-1"
    assert job["status"] == "failed"
    assert "status-secret" not in str(job["error_message"])
    assert "[REDACTED]" in str(job["error_message"])

    events = registry.list_events(local_job_id)
    assert len(events) == 1
    assert events[0]["event_type"] == "failed"
    assert events[0]["uploaded"] == 0
    assert "event-secret" not in str(events[0]["error_message"])

    storage_text = registry_path.read_bytes().decode("latin1", errors="ignore")
    for forbidden in (
        "owner-secret",
        "name-secret",
        "desc-secret",
        "metadata-secret",
        "status-secret",
        "event-secret",
        "payload-secret",
        "QPY-SHOULD-NOT-PERSIST",
        "QPY-EVENT-SHOULD-NOT-PERSIST",
    ):
        assert forbidden not in storage_text


def test_dashboard_event_reporter_records_failures_and_disables_404_uploads(
    tmp_path: Path,
) -> None:
    from cft_piastq.http import DashboardClient
    from cft_piastq.registry import DashboardEventReporter, DirectJobRegistry

    DashboardEventReporter._upload_disabled = False
    registry = DirectJobRegistry(tmp_path / "jobs.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="provider-job-1",
        owner="local-user",
        status="queued",
        shots=100,
        circuit_count=1,
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/api/runner/direct-events"
        return httpx.Response(
            404,
            json={"detail": "missing endpoint token=server-secret"},
        )

    dashboard_client = DashboardClient(
        "https://dashboard.example",
        transport=httpx.MockTransport(handler),
    )
    reporter = DashboardEventReporter(
        registry=registry,
        dashboard_client=dashboard_client,
    )

    reporter.report(
        local_job_id,
        "submitted",
        {"provider_job_id": "provider-job-1", "token": "payload-secret"},
    )
    reporter.report(local_job_id, "status_update", {"status": "running"})

    assert len(requests) == 1
    events = registry.list_events(local_job_id)
    assert [event["event_type"] for event in events] == [
        "submitted",
        "status_update",
    ]
    assert events[0]["uploaded"] == 0
    assert "404" in str(events[0]["error_message"])

    serialized_events = json.dumps(events, sort_keys=True)
    assert "payload-secret" not in serialized_events
    assert "server-secret" not in serialized_events
