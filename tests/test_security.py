from __future__ import annotations

from pathlib import Path

import httpx
import pytest

RAW_PCSS_SECRET = "pcss-secret-sentinel"
RAW_DASHBOARD_SECRET = "dashboard-secret-sentinel"
RAW_QPY_PAYLOAD = "qpy-payload-sentinel"


def test_redact_secrets_removes_token_like_values_and_keeps_context() -> None:
    from cft_piastq.security import redact_secrets

    redacted = redact_secrets(
        "owner=szymo token=abc PCSS_TOKEN=secret "
        "DASHBOARD_API_KEY=dashboard-key job=bell"
    )

    assert "szymo" in redacted
    assert "job=bell" in redacted
    assert "abc" not in redacted
    assert "secret" not in redacted
    assert "dashboard-key" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_secrets_removes_authorization_and_bearer_tokens() -> None:
    from cft_piastq.security import redact_secrets

    redacted = redact_secrets(
        "Authorization: Bearer sk_live_1234567890abcdef request failed"
    )

    assert "sk_live_1234567890abcdef" not in redacted
    assert "request failed" in redacted


def test_redact_secrets_removes_long_api_key_like_strings() -> None:
    from cft_piastq.security import redact_secrets

    redacted = redact_secrets("provider returned key abcdef1234567890abcdef123456")

    assert "abcdef1234567890abcdef123456" not in redacted
    assert "provider returned key" in redacted


def test_safe_error_message_redacts_exception_text() -> None:
    from cft_piastq.security import safe_error_message

    message = safe_error_message(
        RuntimeError("failed with PCSS_TOKEN=secret and owner=szymo")
    )

    assert "secret" not in message
    assert "owner=szymo" in message


def test_redact_secrets_recursively_redacts_mapping_and_list_values() -> None:
    from cft_piastq.security import redact_secrets

    redacted = redact_secrets(
        {
            "detail": {
                "PCSS_TOKEN": "short-secret",
                "api_key": "short-key",
                "context": "runner",
            },
            "errors": [
                {"dashboard_api_key": "nested-short-key"},
                {"message": "failed for owner=szymo"},
            ],
        }
    )

    assert "short-secret" not in redacted
    assert "short-key" not in redacted
    assert "nested-short-key" not in redacted
    assert "runner" in redacted
    assert "owner=szymo" in redacted
    assert "[REDACTED]" in redacted


def test_redact_secrets_recursively_redacts_camel_case_secret_fields() -> None:
    from cft_piastq.security import redact_secrets

    redacted = redact_secrets(
        {
            "detail": {
                "apiKey": "short-key",
                "dashboardApiKey": "dashboard-short-key",
                "pcssToken": "short-secret",
                "context": "runner",
            }
        }
    )

    assert "short-key" not in redacted
    assert "dashboard-short-key" not in redacted
    assert "short-secret" not in redacted
    assert "runner" in redacted
    assert "[REDACTED]" in redacted


def test_direct_event_dashboard_request_sanitizes_payload(
    tmp_path: Path,
) -> None:
    from cft_piastq.http import DashboardClient
    from cft_piastq.registry import DashboardEventReporter, DirectJobRegistry

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    registry = DirectJobRegistry(tmp_path / "jobs.sqlite3")
    local_job_id = registry.insert_job(provider_job_id="provider-job")
    client = DashboardClient(
        "https://dashboard.example",
        api_key=RAW_DASHBOARD_SECRET,
        transport=httpx.MockTransport(handler),
    )
    reporter = DashboardEventReporter(registry=registry, dashboard_client=client)

    reporter.report(
        local_job_id,
        "submitted",
        {
            "pcssToken": RAW_PCSS_SECRET,
            "dashboardApiKey": RAW_DASHBOARD_SECRET,
            "qpyPayload": RAW_QPY_PAYLOAD,
            "context": {"owner": "local-user"},
        },
    )

    assert len(requests) == 1
    request_public_surface = {
        "url": str(requests[0].url),
        "body": requests[0].content.decode(),
    }
    assert_no_raw_test_secrets(request_public_surface)


def test_direct_registry_sqlite_rows_do_not_store_raw_secrets(
    tmp_path: Path,
) -> None:
    from cft_piastq.registry import DirectJobRegistry

    registry_path = tmp_path / "jobs.sqlite3"
    registry = DirectJobRegistry(registry_path)
    local_job_id = registry.insert_job(
        provider_job_id="provider-job",
        metadata={
            "pcssToken": RAW_PCSS_SECRET,
            "dashboardApiKey": RAW_DASHBOARD_SECRET,
            "qpyPayload": RAW_QPY_PAYLOAD,
        },
    )
    registry.update_status(
        local_job_id,
        "failed",
        error=f"provider failed with PCSS_TOKEN={RAW_PCSS_SECRET}",
    )
    registry.record_event(
        local_job_id,
        "failed",
        payload={
            "token": RAW_PCSS_SECRET,
            "qpy": RAW_QPY_PAYLOAD,
        },
        error=f"dashboard key {RAW_DASHBOARD_SECRET}",
        uploaded=False,
    )

    assert_no_raw_test_secrets(registry.get_job(local_job_id))
    assert_no_raw_test_secrets(registry.list_events(local_job_id))
    assert_no_raw_test_secrets(
        registry_path.read_bytes().decode("latin1", errors="ignore")
    )


def test_dashboard_errors_do_not_expose_raw_secret_details() -> None:
    from cft_piastq.errors import ManagedJobError
    from cft_piastq.http import DashboardClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/runner/jobs"
        return httpx.Response(
            500,
            json={
                "detail": {
                    "PCSS_TOKEN": RAW_PCSS_SECRET,
                    "dashboardApiKey": RAW_DASHBOARD_SECRET,
                    "message": "runner failed",
                }
            },
        )

    client = DashboardClient(
        "https://dashboard.example",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ManagedJobError) as exc_info:
        client.submit_job({"shots": 10})

    assert_no_raw_test_secrets(str(exc_info.value))
    assert "runner failed" in str(exc_info.value)


def test_readme_and_examples_do_not_embed_raw_test_secrets() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [root / "README.md", *sorted((root / "examples").glob("*.py"))]

    assert paths
    for path in paths:
        assert_no_raw_test_secrets(path.read_text(encoding="utf-8"))


def assert_no_raw_test_secrets(value: object) -> None:
    text = str(value)
    assert RAW_PCSS_SECRET not in text
    assert RAW_DASHBOARD_SECRET not in text
    assert RAW_QPY_PAYLOAD not in text
