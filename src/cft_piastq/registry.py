"""SQLite registry and best-effort dashboard reporting for direct jobs."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .security import redact_secrets, safe_error_message
from .status import normalize_job_status

DIRECT_EVENT_ENDPOINT_PATH = "/api/runner/direct-events"
_REDACTION = "[REDACTED]"
_OMISSION = "[OMITTED]"
_SECRET_FIELD_NAMES = frozenset(
    {
        "authorization",
        "api_key",
        "dashboard_api_key",
        "pcss_qapi_token",
        "pcss_token",
        "token",
    }
)
_QPY_FIELD_NAMES = frozenset(
    {
        "circuit",
        "circuits",
        "qpy",
        "qpy_base64",
        "qpy_payload",
    }
)


class DirectJobRegistry:
    """Thread-safe SQLite audit/cache store for local direct jobs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._ensure_schema()

    def insert_job(
        self,
        *,
        provider_job_id: str | None = None,
        owner: object = "unknown",
        cft_job_name: object | None = None,
        cft_description: object | None = None,
        status: object = "queued",
        shots: int | None = None,
        circuit_count: int | None = None,
        provider_backend: object | None = None,
        metadata: Mapping[str, object] | None = None,
        local_job_id: str | None = None,
    ) -> str:
        """Insert a local direct job row and return its local identifier."""

        now = _utc_now()
        normalized_status = normalize_job_status(status)
        resolved_local_job_id = _safe_identifier(
            local_job_id or provider_job_id or f"direct-{uuid.uuid4().hex}"
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO direct_jobs (
                    local_job_id,
                    provider_job_id,
                    owner,
                    cft_job_name,
                    cft_description,
                    status,
                    shots,
                    circuit_count,
                    provider_backend,
                    metadata_json,
                    error_message,
                    cancel_requested,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    resolved_local_job_id,
                    _safe_identifier(provider_job_id),
                    _safe_text(owner),
                    _safe_text(cft_job_name),
                    _safe_text(cft_description),
                    normalized_status,
                    shots,
                    circuit_count,
                    _safe_text(provider_backend),
                    _safe_json_text(metadata or {}),
                    1 if normalized_status == "cancel_requested" else 0,
                    now,
                    now,
                ),
            )
        return resolved_local_job_id

    def update_status(
        self,
        local_job_id: str,
        status: object,
        *,
        error: object | None = None,
        cancel_requested: bool | None = None,
    ) -> None:
        """Update the local status and optional sanitized error detail."""

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE direct_jobs
                SET status = ?,
                    error_message = COALESCE(?, error_message),
                    cancel_requested = COALESCE(?, cancel_requested),
                    updated_at = ?
                WHERE local_job_id = ?
                """,
                (
                    normalize_job_status(status),
                    _safe_text(error),
                    None if cancel_requested is None else int(cancel_requested),
                    _utc_now(),
                    _safe_identifier(local_job_id),
                ),
            )

    def record_event(
        self,
        local_job_id: str,
        event_type: str,
        *,
        payload: Mapping[str, object] | None = None,
        error: object | None = None,
        uploaded: bool = True,
    ) -> None:
        """Record a direct event upload attempt or local-only event."""

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO direct_events (
                    local_job_id,
                    event_type,
                    payload_json,
                    error_message,
                    uploaded,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _safe_identifier(local_job_id),
                    _safe_text(event_type),
                    _safe_json_text(payload or {}),
                    _safe_text(error),
                    int(uploaded),
                    _utc_now(),
                ),
            )

    def record_event_failure(
        self,
        local_job_id: str,
        event_type: str,
        *,
        error: object,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        """Record a failed direct event upload attempt."""

        self.record_event(
            local_job_id,
            event_type,
            payload=payload,
            error=error,
            uploaded=False,
        )

    def get_job(self, local_job_id: str) -> dict[str, object] | None:
        """Return one direct job row as a dictionary."""

        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM direct_jobs WHERE local_job_id = ?",
                (_safe_identifier(local_job_id),),
            ).fetchone()
        return None if row is None else dict(row)

    def list_events(self, local_job_id: str | None = None) -> list[dict[str, object]]:
        """Return direct event rows ordered by insertion."""

        with self._lock, self._connect() as connection:
            if local_job_id is None:
                rows = connection.execute(
                    "SELECT * FROM direct_events ORDER BY event_id"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM direct_events
                    WHERE local_job_id = ?
                    ORDER BY event_id
                    """,
                    (_safe_identifier(local_job_id),),
                ).fetchall()
        return [dict(row) for row in rows]

    def _ensure_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS direct_jobs (
                    local_job_id TEXT PRIMARY KEY,
                    provider_job_id TEXT,
                    owner TEXT,
                    cft_job_name TEXT,
                    cft_description TEXT,
                    status TEXT NOT NULL,
                    shots INTEGER,
                    circuit_count INTEGER,
                    provider_backend TEXT,
                    metadata_json TEXT,
                    error_message TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS direct_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT,
                    error_message TEXT,
                    uploaded INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(local_job_id) REFERENCES direct_jobs(local_job_id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection


class DashboardEventReporter:
    """Best-effort uploader for direct job dashboard events."""

    _upload_disabled = False

    def __init__(
        self,
        *,
        registry: DirectJobRegistry,
        dashboard_client: Any | None = None,
        endpoint_path: str = DIRECT_EVENT_ENDPOINT_PATH,
    ) -> None:
        self.registry = registry
        self.dashboard_client = dashboard_client
        self.endpoint_path = endpoint_path

    def report(
        self,
        local_job_id: str,
        event_type: str,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        """Upload a dashboard event and always audit failures locally."""

        safe_payload = _sanitize_structured(payload or {})
        if self.dashboard_client is None:
            self._record_event(
                local_job_id,
                event_type,
                payload=safe_payload,
                uploaded=False,
            )
            return

        if type(self)._upload_disabled:
            self._record_event(
                local_job_id,
                event_type,
                payload=safe_payload,
                error="Direct dashboard event upload disabled.",
                uploaded=False,
            )
            return

        try:
            response = self._send({
                "local_job_id": _safe_identifier(local_job_id),
                "event_type": _safe_text(event_type),
                "payload": safe_payload,
            })
            if response.status_code == 404:
                type(self)._upload_disabled = True
            if response.status_code >= 400:
                raise RuntimeError(self._response_error_message(response))
        except Exception as exc:
            self._record_event(
                local_job_id,
                event_type,
                payload=safe_payload,
                error=exc,
                uploaded=False,
            )
            return

        self._record_event(
            local_job_id,
            event_type,
            payload=safe_payload,
            uploaded=True,
        )

    def _send(self, payload: Mapping[str, object]) -> Any:
        post_direct_event = getattr(self.dashboard_client, "post_direct_event", None)
        if callable(post_direct_event):
            return post_direct_event(payload)

        request_client = getattr(self.dashboard_client, "_client", None)
        url_builder = getattr(self.dashboard_client, "_url", None)
        if request_client is None or not callable(url_builder):
            raise RuntimeError("Dashboard client does not support direct events.")

        headers_builder = getattr(self.dashboard_client, "_headers", None)
        headers = headers_builder() if callable(headers_builder) else {}
        return request_client.request(
            "POST",
            url_builder(self.endpoint_path),
            json=payload,
            headers=headers,
        )

    def _response_error_message(self, response: Any) -> str:
        formatter = getattr(self.dashboard_client, "_response_error_message", None)
        if callable(formatter):
            return f"HTTP {response.status_code}: {formatter(response)}"
        return f"Dashboard direct event upload failed: HTTP {response.status_code}"

    def _record_event(
        self,
        local_job_id: str,
        event_type: str,
        *,
        payload: Mapping[str, object],
        error: object | None = None,
        uploaded: bool,
    ) -> None:
        try:
            self.registry.record_event(
                local_job_id,
                event_type,
                payload=payload,
                error=error,
                uploaded=uploaded,
            )
        except Exception:
            return


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_identifier(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _safe_text(value: object | None) -> str | None:
    if value is None:
        return None
    return redact_secrets(value)


def _safe_json_text(value: object) -> str:
    sanitized = _sanitize_structured(value)
    return json.dumps(sanitized, sort_keys=True, default=str)


def _sanitize_structured(value: object, *, key: str | None = None) -> object:
    if key is not None:
        normalized_key = _normalize_field_name(key)
        if _is_secret_field(normalized_key):
            return _REDACTION
        if _is_qpy_field(normalized_key):
            return _OMISSION

    if isinstance(value, Mapping):
        return {
            str(child_key): _sanitize_structured(
                child_value,
                key=str(child_key),
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_structured(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_structured(item) for item in value]
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, int | float | bool) or value is None:
        return value
    return safe_error_message(Exception(str(value)))


def _is_secret_field(normalized_key: str) -> bool:
    return (
        normalized_key in _SECRET_FIELD_NAMES
        or normalized_key.endswith("_token")
        or normalized_key.endswith("_api_key")
    )


def _is_qpy_field(normalized_key: str) -> bool:
    return normalized_key in _QPY_FIELD_NAMES or "qpy" in normalized_key


def _normalize_field_name(key: str) -> str:
    import re

    normalized = key.strip().replace("-", "_")
    normalized = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", normalized)
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", normalized)
    return normalized.lower()
