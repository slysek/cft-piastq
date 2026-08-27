"""Logical direct-job partitioning, execution, and exact aggregation."""

from __future__ import annotations

import math
import operator
import threading
import time
import uuid
from _thread import LockType
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from copy import deepcopy
from dataclasses import dataclass, field
from numbers import Integral, Real
from typing import Any, Protocol

from qiskit.primitives import SamplerResult  # type: ignore[import-untyped]
from qiskit.result import QuasiDistribution  # type: ignore[import-untyped]

from .errors import DirectProviderError, PiastQTimeoutError
from .security import safe_error_message
from .status import normalize_job_status
from .types import JobStatus

DIRECT_SHOT_LIMIT = 200
_INTEGER_TOLERANCE = 1e-7
_LOGICAL_TIMEOUT_MESSAGE = "Timed out waiting for direct PCSS job to finish."
_CANCELLATION_MESSAGE = "Direct PCSS job was cancelled."


class _Progress(Protocol):
    def update(self, amount: int = 1) -> object: ...


class _ProgressContext(_Progress, AbstractContextManager[_Progress], Protocol):
    pass


ProgressFactory = Callable[..., _ProgressContext]
ErrorFormatter = Callable[[BaseException], str]


class _NoOpProgress:
    def update(self, amount: int = 1) -> None:
        del amount


def _default_progress_factory(**kwargs: Any) -> _ProgressContext:
    from tqdm.auto import tqdm  # type: ignore[import-untyped]

    return tqdm(**kwargs)  # type: ignore[no-any-return]


@dataclass
class DirectCompositeJob:
    """One lazy logical direct job executed as ordered provider children."""

    sampler: Any
    circuits: Sequence[Any]
    parameter_values: Any
    total_shots: int
    provider_options: Mapping[str, Any]
    show_progress: bool = True
    progress_factory: ProgressFactory = _default_progress_factory
    error_formatter: ErrorFormatter = safe_error_message
    part_shots: tuple[int, ...] = field(init=False)
    _expected_circuit_count: int = field(init=False, repr=False)
    _job_id: str = field(init=False, repr=False)
    _status: JobStatus = field(default="queued", init=False, repr=False)
    _result: SamplerResult | None = field(default=None, init=False, repr=False)
    _exact_counts: list[dict[int, int]] | None = field(
        default=None, init=False, repr=False
    )
    _terminal_error: DirectProviderError | PiastQTimeoutError | None = field(
        default=None, init=False, repr=False
    )
    _terminal_interrupt: BaseException | None = field(
        default=None, init=False, repr=False
    )
    _logical_cancellation_error: DirectProviderError | None = field(
        default=None, init=False, repr=False
    )
    _active_child: Any | None = field(default=None, init=False, repr=False)
    _active_cancel_attempted: bool = field(default=False, init=False, repr=False)
    _cancel_requested: bool = field(default=False, init=False, repr=False)
    _state_lock: LockType = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    _execution_lock: LockType = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    _cancel_lock: LockType = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self.part_shots = partition_direct_shots(self.total_shots)
        try:
            self._expected_circuit_count = len(self.circuits)
        except Exception:
            raise DirectProviderError(
                "Direct circuits must expose a valid circuit count."
            ) from None
        self.provider_options = dict(self.provider_options)
        self._job_id = f"direct-{uuid.uuid4()}"

    def job_id(self) -> str:
        return self._job_id

    def status(self) -> JobStatus:
        with self._state_lock:
            return self._status

    def cancel(self) -> JobStatus:
        with self._cancel_lock:
            try:
                return self._cancel_once()
            finally:
                self._reset_cancel_attempt_if_inactive_locked()

    def _cancel_once(self) -> JobStatus:
        with self._state_lock:
            if (
                self._result is not None
                or self._terminal_error is not None
                or self._terminal_interrupt is not None
            ):
                return self._status

            self._cancel_requested = True
            child = self._active_child
            if child is None:
                if self._status == "queued":
                    self._status = "cancelled"
                else:
                    self._status = "cancel_requested"
                self._set_logical_cancellation_locked()
                return self._status

            self._status = "cancel_requested"

        try:
            provider_status = self._cancel_active_child_once_locked(child)
            normalized = _normalize_cancel_status(provider_status)
        except Exception as error:
            public_error = DirectProviderError(
                f"Direct PCSS cancellation failed: {self._format_error(error)}"
            )
            with self._state_lock:
                has_terminal_outcome = (
                    self._result is not None
                    or self._terminal_error is not None
                    or self._terminal_interrupt is not None
                    or self._status in {"succeeded", "failed", "cancelled"}
                )
                if not has_terminal_outcome:
                    self._terminal_error = public_error
                    self._status = "failed"
            raise public_error from None

        with self._state_lock:
            if (
                self._result is not None
                or self._terminal_interrupt is not None
                or self._status in {"succeeded", "failed", "cancelled"}
            ):
                return self._status
            if self._terminal_error is not None:
                if (
                    self._terminal_error is self._logical_cancellation_error
                    and self._status == "cancel_requested"
                    and normalized == "cancelled"
                ):
                    self._status = "cancelled"
                return self._status
            if normalized == "cancelled":
                self._status = "cancelled"
            elif self._status != "cancelled":
                self._status = "cancel_requested"
            if self._terminal_error is None:
                self._set_logical_cancellation_locked()
            return self._status

    def result(self, timeout: float | None = None) -> SamplerResult:
        cached_result = self._cached_result_or_raise()
        if cached_result is not None:
            return cached_result
        deadline = (
            None if timeout is None else time.monotonic() + max(0.0, timeout)
        )
        self._acquire_execution_lock(deadline)
        try:
            cached_result = self._check_deadline_after_acquire(deadline)
            if cached_result is not None:
                return cached_result
            with self._state_lock:
                if self._result is not None:
                    return self._result
                if self._terminal_error is not None:
                    raise self._terminal_error
                if self._terminal_interrupt is not None:
                    raise self._terminal_interrupt
                self._status = "running"

            completed_parts: list[tuple[Any, int]] = []

            try:
                with self._progress_context() as progress:
                    for part_number, shots in enumerate(self.part_shots, start=1):
                        self._raise_if_cancelled()
                        remaining = self._remaining(deadline)
                        child = self._submit_child(
                            shots=shots,
                            part_number=part_number,
                            query_timeout_seconds=remaining,
                        )
                        self._raise_if_cancelled_after_submit(child)

                        try:
                            child_result = child.result()
                            self._remaining(deadline)
                        except Exception as error:
                            self._raise_child_error(
                                error,
                                part_number=part_number,
                            )
                        finally:
                            self._clear_active_child(child)

                        self._validate_child_result(
                            child_result,
                            shots=shots,
                            part_number=part_number,
                        )
                        self._raise_if_cancelled()
                        completed_parts.append((child_result, shots))
                        progress.update(1)

                aggregate, exact_counts = aggregate_direct_results(completed_parts)
                self._remaining(deadline)
            except (DirectProviderError, PiastQTimeoutError) as error:
                self._cache_terminal(error, status="failed")
                raise self._cached_terminal_error() from None
            except Exception as error:
                public_error = DirectProviderError(
                    f"Direct PCSS execution failed: {self._format_error(error)}"
                )
                self._cache_terminal(public_error, status="failed")
                raise self._cached_terminal_error() from None
            except BaseException as interruption:
                with self._state_lock:
                    if (
                        self._terminal_error is None
                        and self._terminal_interrupt is None
                    ):
                        self._terminal_interrupt = interruption
                        self._status = "failed"
                    self._active_child = None
                raise

            with self._state_lock:
                if self._terminal_error is not None:
                    raise self._terminal_error
                if self._cancel_requested:
                    cancellation_error = self._set_logical_cancellation_locked()
                    if self._status not in {"cancelled", "cancel_requested"}:
                        self._status = "cancel_requested"
                    raise cancellation_error
                self._result = aggregate
                self._exact_counts = exact_counts
                self._status = "succeeded"
                return aggregate
        finally:
            self._execution_lock.release()

    def counts(self, num_bits: int | None = None) -> list[dict[str, int]]:
        self.result()
        with self._state_lock:
            exact_counts = self._exact_counts
            if exact_counts is None:  # pragma: no cover - result guarantees counts
                raise DirectProviderError("Direct PCSS result counts are unavailable.")
            snapshot = [dict(circuit_counts) for circuit_counts in exact_counts]

        width = num_bits
        if width is None:
            width = max(
                1,
                max(
                    (
                        state.bit_length()
                        for circuit_counts in snapshot
                        for state in circuit_counts
                    ),
                    default=1,
                ),
            )
        formatted: list[dict[str, int]] = []
        for circuit_counts in snapshot:
            formatted.append(
                {
                    _direct_state_bitstring(state, num_bits=width): count
                    for state, count in circuit_counts.items()
                }
            )
        return formatted

    def _progress_context(self) -> AbstractContextManager[_Progress]:
        if not self.show_progress or len(self.part_shots) <= 1:
            return nullcontext(_NoOpProgress())
        return self.progress_factory(
            total=len(self.part_shots),
            desc="Direct PCSS jobs",
            unit="job",
        )

    def _acquire_execution_lock(self, deadline: float | None) -> None:
        if self._execution_lock.acquire(blocking=False):
            return
        if deadline is None:
            self._execution_lock.acquire()
            return

        remaining = deadline - time.monotonic()
        if remaining <= 0 or not self._execution_lock.acquire(timeout=remaining):
            raise PiastQTimeoutError(_LOGICAL_TIMEOUT_MESSAGE)

    def _check_deadline_after_acquire(
        self,
        deadline: float | None,
    ) -> SamplerResult | None:
        cached_result = self._cached_result_or_raise()
        if cached_result is not None:
            return cached_result
        if deadline is None or deadline - time.monotonic() > 0:
            return None

        cached_result = self._cached_result_or_raise()
        if cached_result is not None:
            return cached_result
        error = PiastQTimeoutError(_LOGICAL_TIMEOUT_MESSAGE)
        self._cache_terminal(error, status="failed")
        raise error

    def _cached_result_or_raise(self) -> SamplerResult | None:
        with self._state_lock:
            if self._result is not None:
                return self._result
            if self._terminal_error is not None:
                raise self._terminal_error
            if self._terminal_interrupt is not None:
                raise self._terminal_interrupt
            return None

    def _remaining(self, deadline: float | None) -> float | None:
        if deadline is None:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            error = PiastQTimeoutError(_LOGICAL_TIMEOUT_MESSAGE)
            self._cache_terminal(error, status="failed")
            raise error
        return remaining

    def _submit_child(
        self,
        *,
        shots: int,
        part_number: int,
        query_timeout_seconds: float | None,
    ) -> Any:
        options = dict(self.provider_options)
        options["shots"] = shots
        options["with_progress_bar"] = False
        if query_timeout_seconds is not None:
            options["query_timeout_seconds"] = query_timeout_seconds
        if self.parameter_values is not None:
            options["parameter_values"] = self.parameter_values
        try:
            child = self.sampler.run(self.circuits, **options)
        except Exception as error:
            self._raise_child_error(error, part_number=part_number)
        with self._cancel_lock, self._state_lock:
            self._active_child = child
            self._active_cancel_attempted = False
        return child

    def _validate_child_result(
        self,
        child_result: Any,
        *,
        shots: int,
        part_number: int,
    ) -> None:
        try:
            child_counts = exact_counts_from_sampler_result(
                child_result,
                shots=shots,
            )
        except DirectProviderError as error:
            self._raise_child_validation_error(
                str(error),
                part_number=part_number,
            )
        if len(child_counts) != self._expected_circuit_count:
            self._raise_child_validation_error(
                "Direct sampler result circuit count must match submitted circuits.",
                part_number=part_number,
            )

    def _raise_child_validation_error(
        self,
        detail: str,
        *,
        part_number: int,
    ) -> None:
        public_error = DirectProviderError(
            f"Direct PCSS part {part_number}/{len(self.part_shots)} failed: {detail}"
        )
        self._cache_terminal(public_error, status="failed")
        raise public_error from None

    def _raise_if_cancelled_after_submit(self, child: Any) -> None:
        with self._state_lock:
            cancelled = self._cancel_requested or self._terminal_error is not None
        if not cancelled:
            return

        cancel_status: JobStatus = "unknown"
        cancel_error: DirectProviderError | None = None
        with self._cancel_lock:
            try:
                provider_status = self._cancel_active_child_once_locked(child)
                cancel_status = _normalize_cancel_status(provider_status)
            except Exception as error:
                cancel_error = DirectProviderError(
                    "Direct PCSS cancellation failed: "
                    f"{self._format_error(error)}"
                )

        with self._state_lock:
            provisional_cancellation = (
                self._terminal_error is self._logical_cancellation_error
            )
            if provisional_cancellation and cancel_error is not None:
                self._terminal_error = cancel_error
                self._status = "failed"
            elif provisional_cancellation and cancel_status == "cancelled":
                self._status = "cancelled"

        self._clear_active_child(child)
        self._raise_if_cancelled()

    def _clear_active_child(self, child: Any) -> None:
        cleared = False
        with self._state_lock:
            if self._active_child is child:
                self._active_child = None
                cleared = True
        if cleared and self._cancel_lock.acquire(blocking=False):
            try:
                self._reset_cancel_attempt_if_inactive_locked()
            finally:
                self._cancel_lock.release()

    def _raise_if_cancelled(self) -> None:
        with self._state_lock:
            if self._terminal_error is not None:
                raise self._terminal_error
            if not self._cancel_requested:
                return
            cancellation_error = self._set_logical_cancellation_locked()
            if self._status != "cancelled":
                self._status = "cancel_requested"
            raise cancellation_error

    def _cancel_active_child_once_locked(self, child: Any) -> object:
        with self._state_lock:
            if self._active_child is not child or self._active_cancel_attempted:
                return None
            self._active_cancel_attempted = True
        cancel_method = getattr(child, "cancel", None)
        return cancel_method() if callable(cancel_method) else None

    def _reset_cancel_attempt_if_inactive_locked(self) -> None:
        with self._state_lock:
            if self._active_child is None:
                self._active_cancel_attempted = False

    def _set_logical_cancellation_locked(self) -> DirectProviderError:
        error = DirectProviderError(_CANCELLATION_MESSAGE)
        self._logical_cancellation_error = error
        self._terminal_error = error
        return error

    def _raise_child_error(
        self,
        error: Exception,
        *,
        part_number: int,
    ) -> None:
        with self._state_lock:
            if self._terminal_error is not None:
                raise self._terminal_error

        if isinstance(error, PiastQTimeoutError):
            self._cache_terminal(error, status="failed")
            raise error
        if isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower():
            timeout_error = PiastQTimeoutError(_LOGICAL_TIMEOUT_MESSAGE)
            self._cache_terminal(timeout_error, status="failed")
            raise timeout_error from None

        public_error = DirectProviderError(
            f"Direct PCSS part {part_number}/{len(self.part_shots)} failed: "
            f"{self._format_error(error)}"
        )
        self._cache_terminal(public_error, status="failed")
        raise public_error from None

    def _format_error(self, error: BaseException) -> str:
        try:
            detail = self.error_formatter(error)
            return detail if isinstance(detail, str) and detail else "provider error"
        except Exception:
            return "provider error"

    def _cache_terminal(
        self,
        error: DirectProviderError | PiastQTimeoutError,
        *,
        status: JobStatus,
    ) -> None:
        with self._state_lock:
            if self._terminal_error is None:
                self._terminal_error = error
                self._status = status

    def _cached_terminal_error(self) -> DirectProviderError | PiastQTimeoutError:
        with self._state_lock:
            if self._terminal_error is None:  # pragma: no cover - caller caches first
                return DirectProviderError("Direct PCSS execution failed.")
            return self._terminal_error


def _normalize_cancel_status(value: object) -> JobStatus:
    if value is True:
        return "cancelled"
    try:
        if hasattr(value, "value"):
            value = value.value
        elif hasattr(value, "name"):
            value = value.name
    except Exception:
        return "unknown"
    return normalize_job_status(value)


def _direct_state_bitstring(state: int, *, num_bits: int | None) -> str:
    width = num_bits if num_bits is not None else max(1, state.bit_length())
    return format(state, f"0{width}b")


class _DirectResultValidationError(Exception):
    """Internal marker for static, trusted direct-result validation errors."""


def partition_direct_shots(total_shots: int) -> tuple[int, ...]:
    """Partition a positive logical shot total into direct-provider chunks."""
    try:
        invalid_total = (
            isinstance(total_shots, bool)
            or not isinstance(total_shots, int)
            or total_shots <= 0
        )
    except Exception:
        raise DirectProviderError("Direct shots must be a positive integer.") from None
    if invalid_total:
        raise DirectProviderError("Direct shots must be a positive integer.")

    full_chunks, remainder = divmod(total_shots, DIRECT_SHOT_LIMIT)
    chunks = (DIRECT_SHOT_LIMIT,) * full_chunks
    if remainder:
        chunks += (remainder,)
    return chunks


def exact_counts_from_sampler_result(
    result: Any,
    *,
    shots: int,
) -> list[dict[int, int]]:
    """Reconstruct exact non-negative counts from direct quasi probabilities."""
    try:
        invalid_shots = (
            isinstance(shots, bool)
            or not isinstance(shots, int)
            or shots <= 0
            or shots > DIRECT_SHOT_LIMIT
        )
    except Exception:
        raise DirectProviderError(
            "Direct child shots must be an integer between 1 and 200."
        ) from None
    if invalid_shots:
        raise DirectProviderError(
            "Direct child shots must be an integer between 1 and 200."
        )

    try:
        quasi_dists = result.quasi_dists
    except Exception:
        raise DirectProviderError(
            "Direct sampler result must contain a sequence of quasi distributions."
        ) from None

    try:
        valid_quasi_sequence = not isinstance(
            quasi_dists, (str, bytes)
        ) and isinstance(quasi_dists, Sequence)
    except Exception:
        raise DirectProviderError(
            "Direct sampler result must contain a sequence of quasi distributions."
        ) from None
    if not valid_quasi_sequence:
        raise DirectProviderError(
            "Direct sampler result must contain a sequence of quasi distributions."
        )
    try:
        distributions = list(quasi_dists)
    except Exception:
        raise DirectProviderError(
            "Direct sampler result must contain a sequence of quasi distributions."
        ) from None
    if not distributions:
        raise DirectProviderError(
            "Direct sampler result must contain at least one quasi distribution."
        )

    reconstructed: list[dict[int, int]] = []
    for distribution in distributions:
        try:
            is_mapping = isinstance(distribution, Mapping)
        except Exception:
            raise DirectProviderError(
                "Each direct quasi distribution must be a mapping."
            ) from None
        if not is_mapping:
            raise DirectProviderError(
                "Each direct quasi distribution must be a mapping."
            )

        circuit_counts: dict[int, int] = {}
        try:
            for raw_state, raw_probability in distribution.items():
                if (
                    isinstance(raw_state, bool)
                    or not isinstance(raw_state, Integral)
                ):
                    raise _DirectResultValidationError(
                        "Direct state keys must be non-negative integers."
                    )
                if isinstance(raw_probability, bool) or not isinstance(
                    raw_probability, Real
                ):
                    raise _DirectResultValidationError(
                        "Direct probabilities must be real numeric values "
                        "for integer counts."
                    )
                try:
                    state = operator.index(raw_state)
                except Exception:
                    raise _DirectResultValidationError(
                        "Direct state keys must be non-negative integers."
                    ) from None
                if state < 0:
                    raise _DirectResultValidationError(
                        "Direct state keys must be non-negative integers."
                    )
                try:
                    probability = float(raw_probability)
                except Exception:
                    raise _DirectResultValidationError(
                        "Direct probabilities must reconstruct integer counts."
                    ) from None
                if not math.isfinite(probability):
                    raise _DirectResultValidationError(
                        "Direct probabilities must be finite real values."
                    )
                if not 0.0 <= probability <= 1.0:
                    raise _DirectResultValidationError(
                        "Direct probabilities must be between 0 and 1 "
                        "for integer counts."
                    )
                scaled = probability * shots
                count = round(scaled)

                if not math.isclose(
                    scaled,
                    count,
                    rel_tol=0.0,
                    abs_tol=_INTEGER_TOLERANCE,
                ):
                    raise _DirectResultValidationError(
                        "Direct probabilities must reconstruct integer counts."
                    )
                if count:
                    circuit_counts[state] = circuit_counts.get(state, 0) + count
        except _DirectResultValidationError as exc:
            raise DirectProviderError(str(exc)) from None
        except Exception:
            raise DirectProviderError(
                "Direct probabilities must reconstruct integer counts."
            ) from None

        if sum(circuit_counts.values()) != shots:
            raise DirectProviderError(
                "Direct reconstructed integer counts must sum exactly to child shots."
            )
        reconstructed.append(circuit_counts)

    return reconstructed


def aggregate_direct_results(
    parts: Sequence[tuple[Any, int]],
) -> tuple[SamplerResult, list[dict[int, int]]]:
    """Sum exact child counts and derive aggregate quasi probabilities."""
    try:
        valid_parts_sequence = not isinstance(parts, (str, bytes)) and isinstance(
            parts, Sequence
        )
    except Exception:
        raise DirectProviderError(
            "Direct result parts must be a non-empty sequence."
        ) from None
    if not valid_parts_sequence:
        raise DirectProviderError("Direct result parts must be a non-empty sequence.")
    try:
        parts_snapshot = list(parts)
    except Exception:
        raise DirectProviderError(
            "Direct result parts must be a valid sequence."
        ) from None
    if not parts_snapshot:
        raise DirectProviderError("Direct result parts must be a non-empty sequence.")

    aggregate_counts: list[dict[int, int]] | None = None
    first_result: Any = None
    total_shots = 0

    for part in parts_snapshot:
        try:
            child_result, child_shots = part
        except Exception:
            raise DirectProviderError(
                "Each direct result part must contain a result and child shots."
            ) from None

        child_counts = exact_counts_from_sampler_result(
            child_result,
            shots=child_shots,
        )
        if aggregate_counts is None:
            aggregate_counts = [dict(counts) for counts in child_counts]
            first_result = child_result
        elif len(child_counts) != len(aggregate_counts):
            raise DirectProviderError(
                "Direct result parts must have the same circuit count."
            )
        else:
            for circuit_index, counts in enumerate(child_counts):
                combined = aggregate_counts[circuit_index]
                for state, count in counts.items():
                    combined[state] = combined.get(state, 0) + count

        total_shots += child_shots

    if aggregate_counts is None:  # pragma: no cover - guarded by non-empty check
        raise DirectProviderError("Direct result parts must be a non-empty sequence.")

    metadata = _first_child_metadata(first_result, count=len(aggregate_counts))
    for item in metadata:
        item["shots"] = total_shots
        item["cft_piastq_parts"] = len(parts_snapshot)

    quasi_dists = [
        QuasiDistribution(
            {state: count / total_shots for state, count in circuit_counts.items()}
        )
        for circuit_counts in aggregate_counts
    ]
    return (
        SamplerResult(quasi_dists=quasi_dists, metadata=metadata),
        aggregate_counts,
    )


def _first_child_metadata(result: Any, *, count: int) -> list[dict[str, Any]]:
    try:
        raw_metadata = result.metadata
        if (
            isinstance(raw_metadata, Sequence)
            and not isinstance(raw_metadata, (str, bytes))
            and len(raw_metadata) == count
        ):
            return [
                deepcopy(dict(item)) if isinstance(item, Mapping) else {}
                for item in raw_metadata
            ]
    except Exception:
        pass
    return [{} for _ in range(count)]
