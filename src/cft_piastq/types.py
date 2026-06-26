"""Shared typing contracts."""

from __future__ import annotations

from typing import Literal, Protocol, TypeAlias

ExecutionMode: TypeAlias = Literal["auto", "managed", "direct", "fake"]
ResolvedExecutionMode: TypeAlias = Literal["managed", "direct", "fake"]
JobStatus: TypeAlias = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "stale",
    "cancel_requested",
    "unknown",
]

JSONValue: TypeAlias = (
    dict[str, "JSONValue"] | list["JSONValue"] | str | int | float | bool | None
)
JSONDict: TypeAlias = dict[str, JSONValue]


class SupportsJobId(Protocol):
    """Protocol for provider job objects exposing a job identifier."""

    def job_id(self) -> str:
        """Return a provider job identifier."""
