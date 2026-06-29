"""Job facade and execution-handle adapters for PiastQ jobs."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from .counts import estimated_counts_from_result
from .errors import (
    DirectProviderError,
    FakeBackendError,
    ManagedJobError,
    PiastQError,
    PiastQTimeoutError,
)
from .results import sampler_result_from_json
from .security import redact_secrets, safe_error_message
from .status import normalize_job_status
from .types import JobStatus

_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


class _JobHandle(Protocol):
    def job_id(self) -> str:
        """Return the public job identifier."""

        ...

    def status(self) -> JobStatus:
        """Return the current normalized job status."""

        ...

    def cancel(self) -> JobStatus:
        """Request job cancellation and return the normalized status."""

        ...

    def result(
        self,
        *,
        timeout: float | None = None,
        poll_interval: float = 5.0,
    ) -> Any:
        """Return a Qiskit-compatible result object."""

        ...

    def counts(self, *, num_bits: int | None = None) -> list[dict[str, int]]:
        """Return estimated counts for the job result."""

        ...


@dataclass
class ManagedJobHandle:
    """Handle for a managed dashboard job."""

    dashboard_client: Any
    server_job_id: str
    shots: int
    num_bits: int | None = None
    _result: Any | None = field(default=None, init=False, repr=False)

    def job_id(self) -> str:
        return self.server_job_id

    def status(self) -> JobStatus:
        return _status_from_payload(self._read_status_payload())

    def cancel(self) -> JobStatus:
        payload = self.dashboard_client.cancel_job(self.server_job_id)
        return _status_from_payload(payload)

    def result(
        self,
        *,
        timeout: float | None = None,
        poll_interval: float = 5.0,
    ) -> Any:
        if self._result is not None:
            return self._result

        if poll_interval <= 0:
            raise PiastQError("poll_interval must be a positive number.")

        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        sleep_interval = poll_interval

        while True:
            status_payload = self._read_status_payload()
            status = _status_from_payload(status_payload)

            if status == "succeeded":
                self._result = sampler_result_from_json(
                    self.dashboard_client.get_result(self.server_job_id)
                )
                return self._result

            if status == "failed":
                raise ManagedJobError(
                    _managed_failure_message(self.server_job_id, status_payload)
                )

            if status == "cancelled":
                raise ManagedJobError(
                    f"Managed job {self.server_job_id} was cancelled."
                )

            if status in _TERMINAL_STATUSES:
                raise ManagedJobError(
                    f"Managed job {self.server_job_id} ended with status {status}."
                )

            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PiastQTimeoutError(
                        "Timed out waiting for managed job "
                        f"{self.server_job_id} to finish."
                    )
                sleep_for = min(sleep_interval, remaining)
            else:
                sleep_for = sleep_interval

            if sleep_for > 0:
                time.sleep(sleep_for)

    def counts(self, *, num_bits: int | None = None) -> list[dict[str, int]]:
        bit_count = self.num_bits if num_bits is None else num_bits
        return estimated_counts_from_result(
            self.result(),
            shots=self.shots,
            num_bits=bit_count,
        )

    def _read_status_payload(self) -> Mapping[str, object]:
        payload = self.dashboard_client.get_job(self.server_job_id)
        if not isinstance(payload, Mapping):
            raise ManagedJobError(
                "Dashboard job status response must be a JSON object."
            )
        return payload


@dataclass
class DirectJobHandle:
    """Thin adapter around a direct provider job object."""

    provider_job: Any
    shots: int | None = None
    num_bits: int | None = None
    registry: Any | None = None
    local_job_id: str | None = None
    event_reporter: Any | None = None
    _cancel_requested: bool = field(default=False, init=False, repr=False)
    _result: Any | None = field(default=None, init=False, repr=False)

    def job_id(self) -> str:
        job_id_method = getattr(self.provider_job, "job_id", None)
        if callable(job_id_method):
            return str(job_id_method())

        job_id_value = getattr(self.provider_job, "job_id", None)
        if job_id_value is None:
            job_id_value = getattr(self.provider_job, "id", None)
        if job_id_value is not None:
            return str(job_id_value)
        return self.local_job_id or "direct-job"

    def status(self) -> JobStatus:
        if self._cancel_requested:
            self._record_status("cancel_requested", cancel_requested=True)
            return "cancel_requested"

        status_method = getattr(self.provider_job, "status", None)
        if callable(status_method):
            status = normalize_job_status(_provider_status_value(status_method()))
        else:
            status = "unknown"
        self._record_status(status)
        return status

    def cancel(self) -> JobStatus:
        cancel_method = getattr(self.provider_job, "cancel", None)
        if not callable(cancel_method):
            self._cancel_requested = True
            self._record_status("cancel_requested", cancel_requested=True)
            return "cancel_requested"

        try:
            raw_status = cancel_method()
        except Exception as exc:  # pragma: no cover - provider-specific failures
            raise DirectProviderError(
                f"Unable to cancel direct provider job: {safe_error_message(exc)}"
            ) from exc

        status = normalize_job_status(_provider_status_value(raw_status))
        if status == "unknown":
            status = self.status()
        else:
            self._record_status(status)
        return status

    def result(
        self,
        *,
        timeout: float | None = None,
        poll_interval: float = 5.0,
    ) -> Any:
        del poll_interval
        if self._result is not None:
            return self._result

        result_method = getattr(self.provider_job, "result", None)
        if not callable(result_method):
            raise DirectProviderError("Direct provider job does not expose result().")

        try:
            if timeout is None:
                self._result = result_method()
            else:
                self._result = result_method(timeout=timeout)
        except Exception as exc:  # pragma: no cover - provider-specific failures
            raise DirectProviderError(
                f"Unable to read direct provider result: {safe_error_message(exc)}"
            ) from exc
        self._record_status("succeeded")
        self._record_event("result_ready", {"status": "succeeded"})
        return self._result

    def counts(self, *, num_bits: int | None = None) -> list[dict[str, int]]:
        result = self.result()
        shots = self.shots if self.shots is not None else _shots_from_result(result)
        if shots is None:
            raise DirectProviderError("Shot count is required to estimate counts.")
        return estimated_counts_from_result(
            result,
            shots=shots,
            num_bits=self.num_bits if num_bits is None else num_bits,
        )

    def _record_status(
        self,
        status: JobStatus,
        *,
        cancel_requested: bool | None = None,
    ) -> None:
        if self.registry is not None and self.local_job_id is not None:
            self.registry.update_status(
                self.local_job_id,
                status,
                cancel_requested=cancel_requested,
            )
        self._record_event("status_update", {"status": status})

    def _record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        if self.event_reporter is not None and self.local_job_id is not None:
            self.event_reporter.report(self.local_job_id, event_type, payload)


@dataclass
class FakeJobHandle:
    """Handle for an already-computed local fake-backend sampler result."""

    sampler_result: Any
    shots: int
    fake_job_id: str = "fake-job"
    num_bits: int | None = None
    _cancelled: bool = field(default=False, init=False, repr=False)

    def job_id(self) -> str:
        return self.fake_job_id

    def status(self) -> JobStatus:
        return "cancelled" if self._cancelled else "succeeded"

    def cancel(self) -> JobStatus:
        self._cancelled = True
        return "cancelled"

    def result(
        self,
        *,
        timeout: float | None = None,
        poll_interval: float = 5.0,
    ) -> Any:
        del timeout, poll_interval
        if self._cancelled:
            raise FakeBackendError(f"Fake job {self.fake_job_id} was cancelled.")
        return self.sampler_result

    def counts(self, *, num_bits: int | None = None) -> list[dict[str, int]]:
        return estimated_counts_from_result(
            self.result(),
            shots=self.shots,
            num_bits=self.num_bits if num_bits is None else num_bits,
        )


class PiastQJob:
    """User-facing job facade for managed, direct, and fake execution."""

    def __init__(self, handle: _JobHandle) -> None:
        self._handle = handle

    def job_id(self) -> str:
        """Return the job identifier."""

        return self._handle.job_id()

    def status(self) -> JobStatus:
        """Return the latest normalized job status."""

        return self._handle.status()

    def cancel(self) -> JobStatus:
        """Request cancellation and return the normalized status."""

        return self._handle.cancel()

    def result(
        self,
        timeout: float | None = None,
        poll_interval: float = 5.0,
    ) -> Any:
        """Return the Qiskit-compatible sampler result."""

        return self._handle.result(timeout=timeout, poll_interval=poll_interval)

    def counts(self, num_bits: int | None = None) -> list[dict[str, int]]:
        """Return estimated counts derived from the sampler result."""

        return self._handle.counts(num_bits=num_bits)


def _status_from_payload(payload: object) -> JobStatus:
    if not isinstance(payload, Mapping):
        return "unknown"
    return normalize_job_status(payload.get("status"))


def _managed_failure_message(
    server_job_id: str,
    payload: Mapping[str, object],
) -> str:
    raw_detail = payload.get("error") or payload.get("detail") or payload.get("message")
    if raw_detail is None:
        return f"Managed job {server_job_id} failed."
    return f"Managed job {server_job_id} failed: {redact_secrets(raw_detail)}"


def _provider_status_value(raw_status: object) -> object:
    if hasattr(raw_status, "value"):
        return raw_status.value
    if hasattr(raw_status, "name"):
        return raw_status.name
    return raw_status


def _shots_from_result(result: Any) -> int | None:
    metadata = getattr(result, "metadata", None)
    if not isinstance(metadata, list) or not metadata:
        return None
    first_metadata = metadata[0]
    if not isinstance(first_metadata, Mapping):
        return None
    raw_shots = first_metadata.get("shots")
    if raw_shots is None:
        return None
    try:
        return int(raw_shots)
    except (TypeError, ValueError):
        return None
