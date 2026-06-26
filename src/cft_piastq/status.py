"""Shared job status literals and normalization."""

from __future__ import annotations

from typing import cast

from .types import JobStatus

_STATUS_MAP: dict[str, JobStatus] = {
    "queued": "queued",
    "queue": "queued",
    "pending": "queued",
    "submitted": "queued",
    "running": "running",
    "run": "running",
    "in_progress": "running",
    "done": "succeeded",
    "finished": "succeeded",
    "finish": "succeeded",
    "success": "succeeded",
    "successful": "succeeded",
    "succeeded": "succeeded",
    "complete": "succeeded",
    "completed": "succeeded",
    "error": "failed",
    "failed": "failed",
    "failure": "failed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "cancelled_by_user": "cancelled",
    "canceled_by_user": "cancelled",
    "stale": "stale",
    "cancel_requested": "cancel_requested",
    "cancellation_requested": "cancel_requested",
    "unknown": "unknown",
}


def normalize_job_status(value: object) -> JobStatus:
    """Normalize provider and dashboard status values to shared literals."""

    if value is None:
        return "unknown"

    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        return "unknown"

    return cast(JobStatus, _STATUS_MAP.get(normalized, "unknown"))
