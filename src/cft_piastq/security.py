"""Helpers for redacting secrets from public messages."""

from __future__ import annotations

import re

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
    r"(?<![A-Za-z0-9_-])(?:sk_[A-Za-z0-9_-]{8,}|[A-Za-z0-9][A-Za-z0-9_-]{23,})(?![A-Za-z0-9_-])"
)


def redact_secrets(message: object) -> str:
    """Return message text with token-like values replaced by a marker."""

    text = str(message)
    text = _AUTHORIZATION_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}Bearer {REDACTION}",
        text,
    )
    text = _NAMED_SECRET_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTION}",
        text,
    )
    return _LONG_KEY_RE.sub(REDACTION, text)


def safe_error_message(exc: BaseException) -> str:
    """Return a public exception message with secrets redacted."""

    message = str(exc) or exc.__class__.__name__
    return redact_secrets(message)
