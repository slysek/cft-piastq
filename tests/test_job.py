from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path

import pytest
from qiskit.primitives import SamplerResult
from qiskit.result import QuasiDistribution

from cft_piastq.errors import (
    DirectProviderError,
    ManagedJobError,
    PiastQError,
    PiastQTimeoutError,
)
from cft_piastq.job import DirectJobHandle, FakeJobHandle, ManagedJobHandle, PiastQJob


class SequencedDashboardClient:
    def __init__(
        self,
        statuses: list[dict[str, object]],
        *,
        result_payload: dict[str, object] | None = None,
    ) -> None:
        self.statuses = statuses
        self.result_payload = result_payload or {
            "server_job_id": "srv-managed-1",
            "status": "succeeded",
            "shots": 200,
            "quasi_dists": [{"0": 0.5, "3": 0.5}],
            "metadata": [{"circuit_index": 0}],
        }
        self.status_reads: list[str] = []
        self.result_reads: list[str] = []
        self.cancelled: list[str] = []

    def get_job(self, server_job_id: str) -> dict[str, object]:
        self.status_reads.append(server_job_id)
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        return self.statuses[0]

    def get_result(self, server_job_id: str) -> dict[str, object]:
        self.result_reads.append(server_job_id)
        return self.result_payload

    def cancel_job(self, server_job_id: str) -> dict[str, object]:
        self.cancelled.append(server_job_id)
        return {"server_job_id": server_job_id, "status": "cancelled"}


class ProviderJob:
    def __init__(self, result: SamplerResult) -> None:
        self.result_value = result
        self.result_timeouts: list[float | None] = []

    def job_id(self) -> str:
        return "provider-job-1"

    def status(self) -> str:
        return "RUNNING"

    def result(self, timeout: float | None = None) -> SamplerResult:
        self.result_timeouts.append(timeout)
        return self.result_value

    def cancel(self) -> str:
        return "CANCELLED"


class TypeErrorProviderJob:
    def __init__(self) -> None:
        self.result_calls = 0

    def result(self, timeout: float | None = None) -> object:
        del timeout
        self.result_calls += 1
        raise TypeError("provider result conversion failed")


class CompositeCountsStub:
    def __init__(self) -> None:
        self.count_widths: list[int | None] = []
        self.result_calls = 0

    def counts(self, num_bits: int | None = None) -> list[dict[str, int]]:
        self.count_widths.append(num_bits)
        return [{"00": 11, "01": 10}]

    def result(self, timeout: float | None = None) -> SamplerResult:
        del timeout
        self.result_calls += 1
        return SamplerResult(
            [QuasiDistribution({0: 0.9, 1: 0.1})],
            metadata=[{"shots": 21}],
        )


class HostileCountsJob(CompositeCountsStub):
    def counts(self, num_bits: int | None = None) -> list[dict[str, int]]:
        del num_bits
        raise RuntimeError("PCSS_TOKEN=raw-counts-secret")


class PublicErrorProviderJob:
    def __init__(self, error: PiastQError, *, provider_status: str = "UNKNOWN") -> None:
        self.error = error
        self.provider_status = provider_status

    def status(self) -> str:
        return self.provider_status

    def result(self, timeout: float | None = None) -> object:
        del timeout
        raise self.error

    def cancel(self) -> object:
        raise self.error


class ExplodingBookkeeping:
    def update_status(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("bookkeeping failed")

    def report(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("event reporting failed")


class UnstringablePublicError(PiastQError):
    def __str__(self) -> str:
        raise RuntimeError("error formatting failed")


class ConcurrentCompositeStub(CompositeCountsStub):
    def __init__(self) -> None:
        super().__init__()
        self.first_result_started = threading.Event()
        self.second_result_started = threading.Event()
        self._call_lock = threading.Lock()

    def result(self, timeout: float | None = None) -> SamplerResult:
        del timeout
        with self._call_lock:
            self.result_calls += 1
            call_number = self.result_calls
        if call_number == 1:
            self.first_result_started.set()
            self.second_result_started.wait(timeout=0.25)
        else:
            self.second_result_started.set()
        return SamplerResult(
            [QuasiDistribution({0: 0.9, 1: 0.1})],
            metadata=[{"shots": 21}],
        )


class GatedResultStub:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.result_calls = 0
        self.result_timeouts: list[float | None] = []
        self.result_value = SamplerResult(
            [QuasiDistribution({0: 1.0})],
            metadata=[{"shots": 21}],
        )

    def result(self, timeout: float | None = None) -> SamplerResult:
        self.result_calls += 1
        self.result_timeouts.append(timeout)
        self.started.set()
        assert self.release.wait(timeout=2.0)
        return self.result_value

    def status(self) -> str:
        return "RUNNING"


class RawProviderFailureJob:
    def result(self, timeout: float | None = None) -> object:
        del timeout
        raise RuntimeError("PCSS_TOKEN=raw-handle-secret")

    def cancel(self) -> object:
        raise RuntimeError("PCSS_TOKEN=raw-handle-secret")

    def status(self) -> str:
        return "UNKNOWN"


class RawCountsFailureJob(CompositeCountsStub):
    def counts(self, num_bits: int | None = None) -> list[dict[str, int]]:
        del num_bits
        raise RuntimeError("PCSS_TOKEN=raw-handle-secret")


class SuccessfulCancelProvider:
    def __init__(
        self,
        *,
        cancel_status: object,
        provider_status: object,
        cancel_started: threading.Event | None = None,
        cancel_release: threading.Event | None = None,
    ) -> None:
        self.cancel_status = cancel_status
        self.provider_status = provider_status
        self.cancel_started = cancel_started
        self.cancel_release = cancel_release
        self.cancel_calls = 0

    def cancel(self) -> object:
        self.cancel_calls += 1
        if self.cancel_started is not None:
            self.cancel_started.set()
        if self.cancel_release is not None:
            assert self.cancel_release.wait(timeout=2.0)
        return self.cancel_status

    def status(self) -> object:
        return self.provider_status


class ConcurrentCancelProvider:
    def __init__(self) -> None:
        self.first_started = threading.Event()
        self.first_release = threading.Event()
        self._lock = threading.Lock()
        self.cancel_calls = 0

    def cancel(self) -> str:
        with self._lock:
            self.cancel_calls += 1
            call_number = self.cancel_calls
        if call_number == 1:
            self.first_started.set()
            assert self.first_release.wait(timeout=2.0)
            return "CANCEL_REQUESTED"
        return "CANCELLED"

    def status(self) -> str:
        return "RUNNING"


class LateCancelAfterSuccessProvider:
    def __init__(self) -> None:
        self.cancel_started = threading.Event()
        self.cancel_release = threading.Event()
        self.result_value = SamplerResult(
            [QuasiDistribution({0: 1.0})],
            metadata=[{"shots": 21}],
        )

    def cancel(self) -> str:
        self.cancel_started.set()
        assert self.cancel_release.wait(timeout=2.0)
        return "CANCELLED"

    def result(self, timeout: float | None = None) -> SamplerResult:
        del timeout
        return self.result_value

    def status(self) -> str:
        return "RUNNING"


def managed_job(client: SequencedDashboardClient) -> PiastQJob:
    return PiastQJob(
        ManagedJobHandle(
            dashboard_client=client,  # type: ignore[arg-type]
            server_job_id="srv-managed-1",
            shots=200,
            num_bits=2,
        )
    )


def test_managed_job_status_reads_dashboard_every_time() -> None:
    client = SequencedDashboardClient(
        [
            {"server_job_id": "srv-managed-1", "status": "queued"},
            {"server_job_id": "srv-managed-1", "status": "running"},
        ]
    )
    job = managed_job(client)

    assert job.job_id() == "srv-managed-1"
    assert job.status() == "queued"
    assert job.status() == "running"
    assert client.status_reads == ["srv-managed-1", "srv-managed-1"]


def test_managed_job_result_polls_until_success_and_returns_sampler_result() -> None:
    client = SequencedDashboardClient(
        [
            {"server_job_id": "srv-managed-1", "status": "queued"},
            {"server_job_id": "srv-managed-1", "status": "running"},
            {"server_job_id": "srv-managed-1", "status": "succeeded"},
        ]
    )
    job = managed_job(client)

    result = job.result(timeout=None, poll_interval=0.01)

    assert dict(result.quasi_dists[0]) == {0: 0.5, 3: 0.5}
    assert client.status_reads == [
        "srv-managed-1",
        "srv-managed-1",
        "srv-managed-1",
    ]
    assert client.result_reads == ["srv-managed-1"]
    assert job.counts() == [{"00": 100, "11": 100}]


@pytest.mark.parametrize("poll_interval", [0.0, -0.01])
def test_managed_job_result_rejects_nonpositive_poll_interval(
    poll_interval: float,
) -> None:
    client = SequencedDashboardClient(
        [
            {"server_job_id": "srv-managed-1", "status": "queued"},
            {"server_job_id": "srv-managed-1", "status": "succeeded"},
        ]
    )
    job = managed_job(client)

    with pytest.raises(
        PiastQError,
        match="poll_interval must be a positive number",
    ):
        job.result(timeout=None, poll_interval=poll_interval)

    assert client.status_reads == []


def test_managed_job_result_raises_when_polling_reaches_cancelled() -> None:
    client = SequencedDashboardClient(
        [
            {"server_job_id": "srv-managed-1", "status": "queued"},
            {"server_job_id": "srv-managed-1", "status": "cancelled"},
        ]
    )
    job = managed_job(client)

    with pytest.raises(ManagedJobError, match="cancelled"):
        job.result(timeout=1.0, poll_interval=0.001)

    assert client.status_reads == ["srv-managed-1", "srv-managed-1"]
    assert client.result_reads == []


def test_managed_job_cancel_delegates_to_dashboard() -> None:
    client = SequencedDashboardClient(
        [{"server_job_id": "srv-managed-1", "status": "running"}]
    )
    job = managed_job(client)

    assert job.cancel() == "cancelled"
    assert client.cancelled == ["srv-managed-1"]


def test_managed_job_result_raises_timeout_for_non_terminal_status() -> None:
    client = SequencedDashboardClient(
        [{"server_job_id": "srv-managed-1", "status": "running"}]
    )
    job = managed_job(client)

    with pytest.raises(PiastQTimeoutError, match="Timed out"):
        job.result(timeout=0.0, poll_interval=0.001)


def test_managed_job_result_raises_sanitized_failure_message() -> None:
    client = SequencedDashboardClient(
        [
            {
                "server_job_id": "srv-managed-1",
                "status": "failed",
                "error": "provider failed PCSS_TOKEN=secret",
            }
        ]
    )
    job = managed_job(client)

    with pytest.raises(ManagedJobError) as exc_info:
        job.result(timeout=1.0, poll_interval=0.001)

    message = str(exc_info.value)
    assert "provider failed" in message
    assert "secret" not in message


def test_piastq_job_facade_delegates_to_direct_job_handle() -> None:
    sampler_result = SamplerResult(
        [QuasiDistribution({0: 1.0})],
        metadata=[{"shots": 20}],
    )
    provider_job = ProviderJob(sampler_result)
    job = PiastQJob(DirectJobHandle(provider_job=provider_job, shots=20, num_bits=1))

    assert job.job_id() == "provider-job-1"
    assert job.status() == "running"
    assert job.result(timeout=2.0) is sampler_result
    assert len(provider_job.result_timeouts) == 1
    result_timeout = provider_job.result_timeouts[0]
    assert result_timeout is not None
    assert 0 < result_timeout <= 2.0
    assert job.counts() == [{"0": 20}]
    assert job.cancel() == "cancelled"


def test_direct_job_handle_does_not_mask_provider_type_errors() -> None:
    provider_job = TypeErrorProviderJob()
    job = PiastQJob(DirectJobHandle(provider_job=provider_job))

    with pytest.raises(DirectProviderError, match="provider result conversion failed"):
        job.result(timeout=2.0)

    assert provider_job.result_calls == 1


def test_direct_job_handle_delegates_exact_composite_counts() -> None:
    provider_job = CompositeCountsStub()
    job = PiastQJob(
        DirectJobHandle(provider_job=provider_job, shots=21, num_bits=2)
    )

    assert job.counts() == [{"00": 11, "01": 10}]
    assert provider_job.count_widths == [2]
    assert provider_job.result_calls == 1


def test_direct_job_handle_passes_explicit_width_to_composite_counts() -> None:
    provider_job = CompositeCountsStub()
    job = PiastQJob(
        DirectJobHandle(provider_job=provider_job, shots=21, num_bits=2)
    )

    assert job.counts(num_bits=3) == [{"00": 11, "01": 10}]
    assert provider_job.count_widths == [3]


def test_direct_counts_first_records_one_logical_success(tmp_path: Path) -> None:
    from cft_piastq.registry import DashboardEventReporter, DirectJobRegistry

    registry = DirectJobRegistry(Path(str(tmp_path)) / "jobs.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="direct-counts-first",
        status="queued",
        shots=21,
        circuit_count=1,
    )
    provider_job = CompositeCountsStub()
    job = PiastQJob(
        DirectJobHandle(
            provider_job=provider_job,
            shots=21,
            num_bits=2,
            registry=registry,
            local_job_id=local_job_id,
            event_reporter=DashboardEventReporter(registry=registry),
        )
    )

    assert job.counts() == [{"00": 11, "01": 10}]
    assert job.counts() == [{"00": 11, "01": 10}]
    assert provider_job.result_calls == 1

    registry_job = registry.get_job(local_job_id)
    assert registry_job is not None
    assert registry_job["status"] == "succeeded"
    events = registry.list_events(local_job_id)
    assert [event["event_type"] for event in events] == [
        "status_update",
        "result_ready",
    ]


def test_direct_exact_counts_wraps_and_redacts_nonpublic_error() -> None:
    job = PiastQJob(
        DirectJobHandle(provider_job=HostileCountsJob(), shots=21, num_bits=2)
    )

    with pytest.raises(DirectProviderError) as exc_info:
        job.counts()

    message = str(exc_info.value)
    assert "Unable to read direct provider counts" in message
    assert "raw-counts-secret" not in message
    assert "[REDACTED]" in message


@pytest.mark.parametrize(
    "error",
    [
        PiastQTimeoutError("logical timeout"),
        DirectProviderError("public provider error"),
        PiastQError("other public error"),
    ],
)
def test_direct_job_handle_preserves_public_result_errors(error: PiastQError) -> None:
    job = PiastQJob(DirectJobHandle(provider_job=PublicErrorProviderJob(error)))

    with pytest.raises(type(error)) as exc_info:
        job.result(timeout=2.0)

    assert exc_info.value is error


@pytest.mark.parametrize(
    "error",
    [
        DirectProviderError("public cancellation error"),
        PiastQError("other public cancellation error"),
    ],
)
def test_direct_job_handle_preserves_public_cancel_errors(error: PiastQError) -> None:
    job = PiastQJob(DirectJobHandle(provider_job=PublicErrorProviderJob(error)))

    with pytest.raises(type(error)) as exc_info:
        job.cancel()

    assert exc_info.value is error


@pytest.mark.parametrize(
    ("error", "provider_status", "expected_status", "expected_event"),
    [
        (
            PiastQTimeoutError("logical timeout"),
            "UNKNOWN",
            "failed",
            "result_failed",
        ),
        (
            DirectProviderError("PCSS_TOKEN=raw-result-secret"),
            "FAILED",
            "failed",
            "result_failed",
        ),
        (
            DirectProviderError("PCSS_TOKEN=raw-cancel-secret"),
            "UNKNOWN",
            "cancel_requested",
            "cancel_failed",
        ),
    ],
)
def test_direct_public_errors_synchronize_safe_registry_state(
    tmp_path: Path,
    error: PiastQError,
    provider_status: str,
    expected_status: str,
    expected_event: str,
) -> None:
    from cft_piastq.registry import DashboardEventReporter, DirectJobRegistry

    registry = DirectJobRegistry(Path(str(tmp_path)) / "errors.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="direct-public-error",
        status="running",
        shots=21,
        circuit_count=1,
    )
    provider_job = PublicErrorProviderJob(error, provider_status=provider_status)
    job = PiastQJob(
        DirectJobHandle(
            provider_job=provider_job,
            registry=registry,
            local_job_id=local_job_id,
            event_reporter=DashboardEventReporter(registry=registry),
        )
    )

    with pytest.raises(type(error)) as exc_info:
        if expected_event == "cancel_failed":
            job.cancel()
        else:
            job.result()

    assert exc_info.value is error
    with pytest.raises(type(error)) as repeated_exc_info:
        if expected_event == "cancel_failed":
            job.cancel()
        else:
            job.result()
    assert repeated_exc_info.value is error
    registry_job = registry.get_job(local_job_id)
    assert registry_job is not None
    assert registry_job["status"] == expected_status
    assert "raw-" not in str(registry_job["error_message"])
    events = registry.list_events(local_job_id)
    assert [event["event_type"] for event in events] == [
        "status_update",
        expected_event,
    ]
    assert "raw-" not in str(events)


def test_direct_public_error_identity_survives_bookkeeping_failure() -> None:
    error = DirectProviderError("original public error")
    bookkeeping = ExplodingBookkeeping()
    job = PiastQJob(
        DirectJobHandle(
            provider_job=PublicErrorProviderJob(error),
            registry=bookkeeping,
            local_job_id="direct-bookkeeping-failure",
            event_reporter=bookkeeping,
        )
    )

    with pytest.raises(DirectProviderError) as exc_info:
        job.result()

    assert exc_info.value is error


def test_direct_public_error_identity_survives_error_formatting_failure() -> None:
    error = UnstringablePublicError()
    job = PiastQJob(DirectJobHandle(provider_job=PublicErrorProviderJob(error)))

    with pytest.raises(UnstringablePublicError) as exc_info:
        job.result()

    assert exc_info.value is error


def test_direct_failed_provider_status_remains_terminal_after_cancel_error(
    tmp_path: Path,
) -> None:
    from cft_piastq.registry import DashboardEventReporter, DirectJobRegistry

    error = DirectProviderError("public cancellation error")
    registry = DirectJobRegistry(tmp_path / "terminal-status.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="direct-terminal-status",
        status="running",
    )
    job = PiastQJob(
        DirectJobHandle(
            provider_job=PublicErrorProviderJob(error, provider_status="FAILED"),
            registry=registry,
            local_job_id=local_job_id,
            event_reporter=DashboardEventReporter(registry=registry),
        )
    )

    with pytest.raises(DirectProviderError) as exc_info:
        job.cancel()
    assert exc_info.value is error

    assert job.status() == "failed"
    registry_job = registry.get_job(local_job_id)
    assert registry_job is not None
    assert registry_job["status"] == "failed"


def test_concurrent_direct_result_and_counts_record_success_once(
    tmp_path: Path,
) -> None:
    from cft_piastq.registry import DashboardEventReporter, DirectJobRegistry

    registry = DirectJobRegistry(tmp_path / "concurrent-success.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="direct-concurrent-success",
        status="queued",
    )
    provider_job = ConcurrentCompositeStub()
    job = PiastQJob(
        DirectJobHandle(
            provider_job=provider_job,
            shots=21,
            num_bits=2,
            registry=registry,
            local_job_id=local_job_id,
            event_reporter=DashboardEventReporter(registry=registry),
        )
    )
    results: list[object] = []
    errors: list[BaseException] = []

    def read_result() -> None:
        try:
            results.append(job.result())
        except BaseException as error:
            errors.append(error)

    def read_counts() -> None:
        try:
            results.append(job.counts())
        except BaseException as error:
            errors.append(error)

    result_thread = threading.Thread(target=read_result)
    counts_thread = threading.Thread(target=read_counts)
    result_thread.start()
    assert provider_job.first_result_started.wait(timeout=1.0)
    counts_thread.start()
    result_thread.join(timeout=2.0)
    counts_thread.join(timeout=2.0)

    assert not result_thread.is_alive()
    assert not counts_thread.is_alive()
    assert errors == []
    assert len(results) == 2
    assert provider_job.result_calls == 1
    events = registry.list_events(local_job_id)
    assert [event["event_type"] for event in events] == [
        "status_update",
        "result_ready",
    ]


def test_direct_result_lock_wait_timeout_does_not_mutate_active_job(
    tmp_path: Path,
) -> None:
    from cft_piastq.registry import DashboardEventReporter, DirectJobRegistry

    registry = DirectJobRegistry(tmp_path / "lock-timeout.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="direct-lock-timeout",
        status="queued",
    )
    provider_job = GatedResultStub()
    job = PiastQJob(
        DirectJobHandle(
            provider_job=provider_job,
            registry=registry,
            local_job_id=local_job_id,
            event_reporter=DashboardEventReporter(registry=registry),
        )
    )
    owner_results: list[object] = []
    owner_errors: list[BaseException] = []

    def read_owner_result() -> None:
        try:
            owner_results.append(job.result())
        except BaseException as error:
            owner_errors.append(error)

    owner_thread = threading.Thread(target=read_owner_result)
    owner_thread.start()
    assert provider_job.started.wait(timeout=1.0)

    started_at = time.monotonic()
    with pytest.raises(PiastQTimeoutError, match="Timed out waiting for direct job"):
        job.result(timeout=0.05)
    assert time.monotonic() - started_at < 1.0
    assert provider_job.result_calls == 1
    registry_job = registry.get_job(local_job_id)
    assert registry_job is not None
    assert registry_job["status"] == "queued"
    assert registry.list_events(local_job_id) == []

    provider_job.release.set()
    owner_thread.join(timeout=2.0)

    assert not owner_thread.is_alive()
    assert owner_errors == []
    assert owner_results == [provider_job.result_value]
    assert job.result(timeout=0.0) is provider_job.result_value
    assert provider_job.result_calls == 1
    assert provider_job.result_timeouts == [None]
    events = registry.list_events(local_job_id)
    assert [event["event_type"] for event in events] == [
        "status_update",
        "result_ready",
    ]


@pytest.mark.parametrize(
    ("operation", "expected_public_text"),
    [
        ("result", "Unable to read direct provider result"),
        ("cancel", "Unable to cancel direct provider job"),
        ("counts", "Unable to read direct provider counts"),
    ],
)
def test_direct_generic_wrappers_hide_raw_exception_traceback(
    operation: str,
    expected_public_text: str,
) -> None:
    provider_job: object
    if operation == "counts":
        provider_job = RawCountsFailureJob()
    else:
        provider_job = RawProviderFailureJob()
    job = PiastQJob(
        DirectJobHandle(provider_job=provider_job, shots=21, num_bits=2)
    )

    with pytest.raises(DirectProviderError) as exc_info:
        getattr(job, operation)()

    formatted = "".join(traceback.format_exception(exc_info.value))
    assert "raw-handle-secret" not in formatted
    assert expected_public_text in formatted
    assert "[REDACTED]" in formatted
    assert exc_info.value.__cause__ is None


@pytest.mark.parametrize(
    ("initial_status", "cancel_status", "expected_status"),
    [
        ("queued", "CANCELLED", "cancelled"),
        ("running", "CANCEL_REQUESTED", "cancel_requested"),
        ("running", "provider-specific-unknown", "cancel_requested"),
    ],
)
def test_direct_successful_cancel_records_requested_immediately(
    tmp_path: Path,
    initial_status: str,
    cancel_status: object,
    expected_status: str,
) -> None:
    from cft_piastq.registry import DirectJobRegistry

    registry = DirectJobRegistry(tmp_path / f"cancel-{initial_status}.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="direct-successful-cancel",
        status=initial_status,
    )
    provider_job = SuccessfulCancelProvider(
        cancel_status=cancel_status,
        provider_status=initial_status,
    )
    job = PiastQJob(
        DirectJobHandle(
            provider_job=provider_job,
            registry=registry,
            local_job_id=local_job_id,
        )
    )

    assert job.cancel() == expected_status
    registry_job = registry.get_job(local_job_id)
    assert registry_job is not None
    assert registry_job["status"] == expected_status
    assert registry_job["cancel_requested"] == 1


def test_direct_active_cancel_is_sticky_before_provider_returns(
    tmp_path: Path,
) -> None:
    from cft_piastq.registry import DirectJobRegistry

    cancel_started = threading.Event()
    cancel_release = threading.Event()
    provider_job = SuccessfulCancelProvider(
        cancel_status="CANCELLED",
        provider_status="RUNNING",
        cancel_started=cancel_started,
        cancel_release=cancel_release,
    )
    registry = DirectJobRegistry(tmp_path / "active-cancel.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="direct-active-cancel",
        status="running",
    )
    job = PiastQJob(
        DirectJobHandle(
            provider_job=provider_job,
            registry=registry,
            local_job_id=local_job_id,
        )
    )
    cancel_statuses: list[str] = []
    cancel_thread = threading.Thread(
        target=lambda: cancel_statuses.append(job.cancel())
    )

    cancel_thread.start()
    assert cancel_started.wait(timeout=1.0)
    pending_registry_job = registry.get_job(local_job_id)
    assert pending_registry_job is not None
    assert pending_registry_job["status"] == "cancel_requested"
    assert pending_registry_job["cancel_requested"] == 1
    cancel_release.set()
    cancel_thread.join(timeout=2.0)

    assert not cancel_thread.is_alive()
    assert cancel_statuses == ["cancelled"]
    registry_job = registry.get_job(local_job_id)
    assert registry_job is not None
    assert registry_job["status"] == "cancelled"
    assert registry_job["cancel_requested"] == 1
    assert provider_job.cancel_calls == 1


def test_direct_cancel_bookkeeping_failure_does_not_block_provider() -> None:
    bookkeeping = ExplodingBookkeeping()
    provider_job = SuccessfulCancelProvider(
        cancel_status="CANCELLED",
        provider_status="RUNNING",
    )
    job = PiastQJob(
        DirectJobHandle(
            provider_job=provider_job,
            registry=bookkeeping,
            local_job_id="direct-cancel-bookkeeping-failure",
            event_reporter=bookkeeping,
        )
    )

    assert job.cancel() == "cancelled"
    assert provider_job.cancel_calls == 1


def test_late_concurrent_cancel_response_does_not_downgrade_terminal_status(
    tmp_path: Path,
) -> None:
    from cft_piastq.registry import DirectJobRegistry

    provider_job = ConcurrentCancelProvider()
    registry = DirectJobRegistry(tmp_path / "concurrent-cancel.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="direct-concurrent-cancel",
        status="running",
    )
    job = PiastQJob(
        DirectJobHandle(
            provider_job=provider_job,
            registry=registry,
            local_job_id=local_job_id,
        )
    )
    statuses: list[str] = []
    first = threading.Thread(target=lambda: statuses.append(job.cancel()))
    second = threading.Thread(target=lambda: statuses.append(job.cancel()))

    first.start()
    assert provider_job.first_started.wait(timeout=1.0)
    second.start()
    second.join(timeout=2.0)
    assert not second.is_alive()
    provider_job.first_release.set()
    first.join(timeout=2.0)

    assert not first.is_alive()
    assert sorted(statuses) == ["cancel_requested", "cancelled"]
    registry_job = registry.get_job(local_job_id)
    assert registry_job is not None
    assert registry_job["status"] == "cancelled"
    assert registry_job["cancel_requested"] == 1


def test_stale_status_write_cannot_overwrite_concurrent_cancel_request(
    tmp_path: Path,
) -> None:
    from cft_piastq.registry import DirectJobRegistry

    cancel_started = threading.Event()
    cancel_release = threading.Event()
    provider_job = SuccessfulCancelProvider(
        cancel_status="CANCELLED",
        provider_status="RUNNING",
        cancel_started=cancel_started,
        cancel_release=cancel_release,
    )
    registry = DirectJobRegistry(tmp_path / "stale-status.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="direct-stale-status",
        status="running",
    )
    handle = DirectJobHandle(
        provider_job=provider_job,
        registry=registry,
        local_job_id=local_job_id,
    )
    job = PiastQJob(handle)
    stale_writer_entered = threading.Event()
    stale_writer_release = threading.Event()
    original_record_status = handle._record_status

    def gated_record_status(
        status: str,
        *,
        cancel_requested: bool | None = None,
    ) -> str:
        if status == "running":
            stale_writer_entered.set()
            assert stale_writer_release.wait(timeout=2.0)
        return original_record_status(  # type: ignore[arg-type,return-value]
            status,
            cancel_requested=cancel_requested,
        )

    handle._record_status = gated_record_status  # type: ignore[method-assign]
    status_results: list[str] = []
    cancel_results: list[str] = []
    status_thread = threading.Thread(target=lambda: status_results.append(job.status()))
    cancel_thread = threading.Thread(target=lambda: cancel_results.append(job.cancel()))

    status_thread.start()
    assert stale_writer_entered.wait(timeout=1.0)
    cancel_thread.start()
    assert cancel_started.wait(timeout=1.0)
    pending = registry.get_job(local_job_id)
    assert pending is not None
    assert pending["status"] == "cancel_requested"
    assert pending["cancel_requested"] == 1

    stale_writer_release.set()
    status_thread.join(timeout=2.0)
    after_stale = registry.get_job(local_job_id)
    assert after_stale is not None
    assert after_stale["status"] == "cancel_requested"

    cancel_release.set()
    cancel_thread.join(timeout=2.0)
    assert not status_thread.is_alive()
    assert not cancel_thread.is_alive()
    assert status_results == ["cancel_requested"]
    assert cancel_results == ["cancelled"]
    terminal = registry.get_job(local_job_id)
    assert terminal is not None
    assert terminal["status"] == "cancelled"


def test_late_cancel_terminal_cannot_overwrite_succeeded_result(
    tmp_path: Path,
) -> None:
    from cft_piastq.registry import DirectJobRegistry

    provider_job = LateCancelAfterSuccessProvider()
    registry = DirectJobRegistry(tmp_path / "late-cancel-success.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="direct-late-cancel-success",
        status="running",
    )
    job = PiastQJob(
        DirectJobHandle(
            provider_job=provider_job,
            registry=registry,
            local_job_id=local_job_id,
        )
    )
    cancel_results: list[str] = []
    cancel_thread = threading.Thread(target=lambda: cancel_results.append(job.cancel()))

    cancel_thread.start()
    assert provider_job.cancel_started.wait(timeout=1.0)
    assert job.result() is provider_job.result_value
    succeeded = registry.get_job(local_job_id)
    assert succeeded is not None
    assert succeeded["status"] == "succeeded"

    provider_job.cancel_release.set()
    cancel_thread.join(timeout=2.0)

    assert not cancel_thread.is_alive()
    assert cancel_results == ["cancelled"]
    terminal = registry.get_job(local_job_id)
    assert terminal is not None
    assert terminal["status"] == "succeeded"
    assert terminal["cancel_requested"] == 1


def test_piastq_job_facade_delegates_to_fake_job_handle() -> None:
    sampler_result = SamplerResult(
        [QuasiDistribution({1: 1.0})],
        metadata=[{}],
    )
    job = PiastQJob(
        FakeJobHandle(
            sampler_result=sampler_result,
            shots=12,
            fake_job_id="fake-job-1",
            num_bits=1,
        )
    )

    assert job.job_id() == "fake-job-1"
    assert job.status() == "succeeded"
    assert job.result() is sampler_result
    assert job.counts() == [{"1": 12}]
    assert job.cancel() == "cancelled"
    assert job.status() == "cancelled"
