"""Job facade and execution-handle adapters for PiastQ jobs."""

from __future__ import annotations

import threading
import time
from _thread import LockType
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

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

_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "stale"})
_STABLE_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
_DIRECT_LOGICAL_TIMEOUT_MESSAGE = "Timed out waiting for direct job to finish."


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
    shots: int | None
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
        result = self.result()
        shots = self.shots if self.shots is not None else _shots_from_result(result)
        if shots is None:
            raise ManagedJobError(
                f"Managed job {self.server_job_id} result does not include shots."
            )
        bit_count = self.num_bits if num_bits is None else num_bits
        return estimated_counts_from_result(
            result,
            shots=shots,
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
    _result_initialized: bool = field(default=False, init=False, repr=False)
    _success_recorded: bool = field(default=False, init=False, repr=False)
    _failure_recorded: bool = field(default=False, init=False, repr=False)
    _recorded_status: JobStatus | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _result_lock: LockType = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )
    _bookkeeping_lock: LockType = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

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
        status_method = getattr(self.provider_job, "status", None)
        try:
            raw_status = status_method() if callable(status_method) else None
            status = normalize_job_status(_provider_status_value(raw_status))
        except Exception:
            status = "unknown"

        return self._record_status(status)

    def cancel(self) -> JobStatus:
        self._mark_cancel_requested()
        self._record_cancel_status_best_effort("cancel_requested")
        cancel_method = getattr(self.provider_job, "cancel", None)
        if not callable(cancel_method):
            return "cancel_requested"

        try:
            raw_status = cancel_method()
        except PiastQError as exc:
            with suppress(BaseException):
                self._record_terminal_failure(
                    exc,
                    fallback_status="cancel_requested",
                    event_type="cancel_failed",
                )
            raise
        except Exception as exc:  # pragma: no cover - provider-specific failures
            public_error = DirectProviderError(
                f"Unable to cancel direct provider job: {safe_error_message(exc)}"
            )
            self._record_terminal_failure(
                public_error,
                fallback_status="cancel_requested",
                event_type="cancel_failed",
            )
            raise public_error from None

        status = normalize_job_status(_provider_status_value(raw_status))
        if status not in _TERMINAL_STATUSES and status != "cancel_requested":
            status = "cancel_requested"
        self._record_cancel_status_best_effort(status)
        return status

    def result(
        self,
        *,
        timeout: float | None = None,
        poll_interval: float = 5.0,
    ) -> Any:
        del poll_interval
        deadline = (
            None if timeout is None else time.monotonic() + max(0.0, timeout)
        )
        if self._result_initialized:
            return self._result

        self._acquire_result_lock(deadline)
        try:
            if self._result_initialized:
                return self._result

            result_method = getattr(self.provider_job, "result", None)
            if not callable(result_method):
                raise DirectProviderError(
                    "Direct provider job does not expose result()."
                )

            remaining = self._remaining_result_time(deadline)
            try:
                if remaining is None:
                    self._result = result_method()
                else:
                    self._result = result_method(timeout=remaining)
                self._result_initialized = True
            except PiastQError as exc:
                with suppress(BaseException):
                    self._record_terminal_failure(
                        exc,
                        fallback_status="failed",
                        event_type="result_failed",
                    )
                raise
            except Exception as exc:  # pragma: no cover - provider-specific failures
                public_error = DirectProviderError(
                    "Unable to read direct provider result: "
                    f"{safe_error_message(exc)}"
                )
                with suppress(BaseException):
                    self._record_terminal_failure(
                        public_error,
                        fallback_status="failed",
                        event_type="result_failed",
                    )
                raise public_error from None
            self._record_success_once()
            return self._result
        finally:
            self._result_lock.release()

    def counts(self, *, num_bits: int | None = None) -> list[dict[str, int]]:
        bit_count = self.num_bits if num_bits is None else num_bits
        counts_method = getattr(self.provider_job, "counts", None)
        if callable(counts_method):
            self.result()
            try:
                return cast(
                    list[dict[str, int]],
                    counts_method(num_bits=bit_count),
                )
            except PiastQError:
                raise
            except Exception as exc:
                raise DirectProviderError(
                    "Unable to read direct provider counts: "
                    f"{safe_error_message(exc)}"
                ) from None

        result = self.result()
        shots = self.shots if self.shots is not None else _shots_from_result(result)
        if shots is None:
            raise DirectProviderError("Shot count is required to estimate counts.")
        return estimated_counts_from_result(
            result,
            shots=shots,
            num_bits=bit_count,
        )

    def _record_status(
        self,
        status: JobStatus,
        *,
        cancel_requested: bool | None = None,
    ) -> JobStatus:
        with self._bookkeeping_lock:
            resolved_status, _ = self._write_status_locked(
                status,
                cancel_requested=cancel_requested,
                write_when_unchanged=True,
                emit_when_unchanged=True,
            )
            return resolved_status

    def _mark_cancel_requested(self) -> None:
        with self._bookkeeping_lock:
            self._cancel_requested = True

    def _cancel_requested_snapshot(self) -> bool:
        with self._bookkeeping_lock:
            return self._cancel_requested

    def _record_cancel_status_best_effort(self, status: JobStatus) -> None:
        with self._bookkeeping_lock:
            self._write_status_locked(status, cancel_requested=True)

    def _write_status_locked(
        self,
        candidate: JobStatus,
        *,
        error: str | None = None,
        cancel_requested: bool | None = None,
        write_when_unchanged: bool = False,
        emit_when_unchanged: bool = False,
    ) -> tuple[JobStatus, bool]:
        status = self._resolve_status_locked(candidate)
        changed = status != self._recorded_status
        self._recorded_status = status
        cancellation_flag = (
            self._cancel_requested
            or cancel_requested is True
            or status in {"cancel_requested", "cancelled"}
        )

        if (
            changed or write_when_unchanged or error is not None
        ) and self.registry is not None and self.local_job_id is not None:
            with suppress(BaseException):
                self.registry.update_status(
                    self.local_job_id,
                    status,
                    error=error,
                    cancel_requested=cancellation_flag,
                )
        if changed or emit_when_unchanged:
            payload: dict[str, object] = {"status": status}
            if error is not None:
                payload["error"] = error
            with suppress(BaseException):
                self._record_event("status_update", payload)
        return status, changed

    def _resolve_status_locked(self, candidate: JobStatus) -> JobStatus:
        current = self._recorded_status
        if current in _STABLE_TERMINAL_STATUSES:
            return current
        if current == "stale":
            if candidate in _STABLE_TERMINAL_STATUSES:
                return candidate
            return current
        if current == "cancel_requested" and candidate not in _TERMINAL_STATUSES:
            return current
        if self._cancel_requested and candidate not in _TERMINAL_STATUSES:
            return "cancel_requested"
        return candidate

    def _acquire_result_lock(self, deadline: float | None) -> None:
        if deadline is None:
            self._result_lock.acquire()
            return
        if self._result_lock.acquire(blocking=False):
            return

        remaining = deadline - time.monotonic()
        if remaining <= 0 or not self._result_lock.acquire(timeout=remaining):
            raise PiastQTimeoutError(_DIRECT_LOGICAL_TIMEOUT_MESSAGE)

    def _remaining_result_time(self, deadline: float | None) -> float | None:
        if deadline is None:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PiastQTimeoutError(_DIRECT_LOGICAL_TIMEOUT_MESSAGE)
        return remaining

    def _record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        if self.event_reporter is not None and self.local_job_id is not None:
            self.event_reporter.report(self.local_job_id, event_type, payload)

    def _record_terminal_failure(
        self,
        error: PiastQError,
        *,
        fallback_status: JobStatus,
        event_type: str,
    ) -> None:
        status = self._safe_terminal_status(fallback_status)
        detail = safe_error_message(error)
        with self._bookkeeping_lock:
            if self._success_recorded or self._failure_recorded:
                return
            self._failure_recorded = True
            resolved_status, _ = self._write_status_locked(
                status,
                error=detail,
            )
            payload = {"status": resolved_status, "error": detail}
            with suppress(BaseException):
                self._record_event(event_type, payload)

    def _record_success_once(self) -> None:
        with self._bookkeeping_lock:
            if self._success_recorded or self._failure_recorded:
                return
            self._success_recorded = True
            status, _ = self._write_status_locked("succeeded")
            with suppress(BaseException):
                self._record_event("result_ready", {"status": status})

    def _safe_terminal_status(self, fallback_status: JobStatus) -> JobStatus:
        try:
            status_method = getattr(self.provider_job, "status", None)
            raw_status = status_method() if callable(status_method) else None
            status = normalize_job_status(_provider_status_value(raw_status))
        except BaseException:
            status = "unknown"

        if status in _TERMINAL_STATUSES or status == "cancel_requested":
            return status
        if self._cancel_requested_snapshot():
            return "cancel_requested"
        return fallback_status


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
        """Return exact combined integer counts for direct jobs.

        Managed and fake jobs may be estimated from quasi-distributions.
        """

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
