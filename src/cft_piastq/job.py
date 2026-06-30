"""Job wrapper returned by :class:`cft_piastq.sampler.PiastQSampler`."""

from __future__ import annotations

import time

from qiskit.primitives import SamplerResult  # type: ignore[import-untyped]

from .backend import ManagedPiastQBackend
from .counts import estimated_counts_from_result
from .errors import ManagedJobError, PiastQConfigurationError, PiastQTimeoutError
from .results import sampler_result_from_json
from .status import normalize_job_status
from .types import JobStatus

DEFAULT_POLL_INTERVAL_SECONDS = 5.0
_TERMINAL_FAILURE_STATUSES = frozenset({"failed", "cancelled", "stale"})


class PiastQJob:
    """Managed dashboard job with Qiskit-compatible result access."""

    def __init__(
        self,
        *,
        backend: ManagedPiastQBackend,
        server_job_id: str,
        shots: int | None,
        initial_status: object = None,
    ) -> None:
        self._backend = backend
        self._server_job_id = server_job_id
        self._shots = shots
        self._last_status = normalize_job_status(initial_status)
        self._result: SamplerResult | None = None

    def job_id(self) -> str:
        """Return the dashboard job identifier."""

        return self._server_job_id

    def status(self) -> JobStatus:
        """Read fresh managed status from the dashboard."""

        payload = self._backend.dashboard_client.get_job(self._server_job_id)
        self._last_status = normalize_job_status(payload.get("status"))
        return self._last_status

    def result(
        self,
        timeout: float | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> SamplerResult:
        """Wait for completion and return a Qiskit ``SamplerResult``."""

        if self._result is not None:
            return self._result

        started_at = time.monotonic()
        while True:
            status = self.status()
            if status == "succeeded":
                break
            if status in _TERMINAL_FAILURE_STATUSES:
                raise ManagedJobError(
                    f"Managed job {self._server_job_id} finished with status "
                    f"{status}."
                )
            if timeout is not None and time.monotonic() - started_at >= timeout:
                raise PiastQTimeoutError(
                    f"Timed out waiting for managed job {self._server_job_id}."
                )
            if poll_interval > 0:
                time.sleep(poll_interval)

        payload = self._backend.dashboard_client.get_result(self._server_job_id)
        self._result = sampler_result_from_json(payload)
        return self._result

    def cancel(self) -> JobStatus:
        """Request cancellation and return the normalized dashboard status."""

        payload = self._backend.dashboard_client.cancel_job(self._server_job_id)
        self._last_status = normalize_job_status(payload.get("status"))
        return self._last_status

    def counts(self, *, num_bits: int | None = None) -> list[dict[str, int]]:
        """Return estimated counts for each logical circuit."""

        result = self._result if self._result is not None else self.result()
        return estimated_counts_from_result(
            result,
            shots=self._shots_from_result(result),
            num_bits=num_bits,
        )

    def _shots_from_result(self, result: SamplerResult) -> int:
        if self._shots is not None:
            return self._shots

        for metadata in result.metadata:
            shots = metadata.get("shots")
            if isinstance(shots, int):
                return shots

        raise PiastQConfigurationError(
            "Counts require shots from sampler.run() or result metadata."
        )
