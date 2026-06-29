from __future__ import annotations

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

    with pytest.raises(PiastQError, match="poll_interval"):
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
    job = PiastQJob(
        DirectJobHandle(provider_job=provider_job, shots=20, num_bits=1)
    )

    assert job.job_id() == "provider-job-1"
    assert job.status() == "running"
    assert job.result(timeout=2.0) is sampler_result
    assert provider_job.result_timeouts == [2.0]
    assert job.counts() == [{"0": 20}]
    assert job.cancel() == "cancelled"


def test_direct_job_handle_does_not_mask_provider_type_errors() -> None:
    provider_job = TypeErrorProviderJob()
    job = PiastQJob(DirectJobHandle(provider_job=provider_job))

    with pytest.raises(DirectProviderError, match="provider result conversion failed"):
        job.result(timeout=2.0)

    assert provider_job.result_calls == 1


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