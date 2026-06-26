"""Helpers for redacting secrets from public messages."""

from __future__ import annotations

import re
from collections.abc import Mapping

REDACTION = "[REDACTED]"

_AUTHORIZATION_RE = re.compile(
    r"\b(authorization)(\s*[:=]\s*)bearer\s+[A-Za-z0-9._~+/=-]+",
    re.IGNORECASE,
)
_NAMED_SECRET_RE = re.compile(
    r"\b("
    r"PCSS_TOKEN|PCSS_QAPI_TOKEN|"
    r"CFT_PIASTQ_DASHBOARD_API_KEY|DASHBOARD_API_KEY|"
    r"Authorization|token|api[_-]?key"
    r")\b(\s*[:=]\s*)([^\s,;]+)",
    re.IGNORECASE,
)
_LONG_KEY_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?:sk_[A-Za-z0-9_-]{8,}|[A-Za-z0-9][A-Za-z0-9_-]{23,})"
    r"(?![A-Za-z0-9_-])"
)
_SECRET_FIELD_NAMES = frozenset(
    {
        "authorization",
        "api_key",
        "cft_piastq_dashboard_api_key",
        "dashboard_api_key",
        "pcss_qapi_token",
        "pcss_token",
        "token",
    }
)


def redact_secrets(message: object) -> str:
    """Return message text with token-like values replaced by a marker."""

    text = str(_redact_structured(message))
    return _redact_text(text)


def _redact_text(text: str) -> str:
    text = _AUTHORIZATION_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}Bearer {REDACTION}",
        text,
    )
    text = _NAMED_SECRET_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTION}",
        text,
    )
    return _LONG_KEY_RE.sub(REDACTION, text)


def _redact_structured(value: object, *, key: str | None = None) -> object:
    if key is not None and _is_secret_field_name(key):
        return REDACTION
    if isinstance(value, Mapping):
        return {
            str(child_key): _redact_structured(
                child_value,
                key=str(child_key),
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_structured(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_structured(item) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _is_secret_field_name(key: str) -> bool:
    normalized = _normalize_field_name(key)
    return (
        normalized in _SECRET_FIELD_NAMES
        or normalized.endswith("_token")
        or normalized.endswith("_api_key")
    )


def _normalize_field_name(key: str) -> str:
    normalized = key.strip().replace("-", "_")
    normalized = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", normalized)
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", normalized)
    return normalized.lower()


def safe_error_message(exc: BaseException) -> str:
    """Return a public exception message with secrets redacted."""

    message = str(exc) or exc.__class__.__name__
    return redact_secrets(message)
