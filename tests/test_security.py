from __future__ import annotations


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
