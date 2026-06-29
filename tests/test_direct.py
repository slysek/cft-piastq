from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pytest
from qiskit import QuantumCircuit
from qiskit.primitives import SamplerResult
from qiskit.result import QuasiDistribution

from cft_piastq.backend import DirectPiastQBackend
from cft_piastq.errors import DirectModeUnavailableError, DirectProviderError
from cft_piastq.job import DirectJobHandle, PiastQJob

OPTIONAL_MODULES = (
    "pcss_qapi",
    "pcss_qapi.aqt",
    "pcss_qapi.aqt.provider",
    "qiskit_aqt_provider",
    "qiskit_aqt_provider.primitives",
)


def bell_circuit() -> QuantumCircuit:
    circuit = QuantumCircuit(2, 2, name="bell")
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    return circuit


def test_importing_direct_module_does_not_import_optional_pcss_packages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for module_name in OPTIONAL_MODULES:
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    import cft_piastq.direct as direct_module

    importlib.reload(direct_module)

    for module_name in OPTIONAL_MODULES:
        assert module_name not in sys.modules


def test_direct_client_logs_in_lazily_and_delegates_to_aqt_sampler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state = install_fake_direct_modules(monkeypatch)
    event_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        event_requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/api/runner/direct-events"
        return httpx.Response(500, json={"detail": "event upload failed"})

    from cft_piastq import PiastQClient, PiastQSampler
    from cft_piastq.registry import DashboardEventReporter, DirectJobRegistry

    DashboardEventReporter._upload_disabled = False
    registry_path = tmp_path / "direct" / "jobs.sqlite3"
    client = PiastQClient(
        mode="direct",
        owner="local-user",
        **{"to" + "ken": "pcss-token-value"},
        dashboard_api_url="https://dashboard.example",
        registry_path=registry_path,
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )

    assert client.execution_mode == "direct"
    assert isinstance(client.backend, DirectPiastQBackend)
    assert state["login_tokens"] == []
    assert state["providers"] == []
    assert state["samplers"] == []

    sampler = PiastQSampler(
        client.backend,
        options={"cft_job_name": "Display name", "with_progress_bar": False},
    )

    job = sampler.run(
        bell_circuit(),
        parameter_values=[[0.0]],
        shots=321,
        cft_description="Display description",
        optimization_level=2,
    )

    assert job.job_id() == "raw-direct-job-1"
    assert job.status() == "running"
    assert state["login_tokens"] == ["pcss-token-value"]
    assert len(state["providers"]) == 1
    assert state["providers"][0].direct_backend_requested is True
    assert len(state["samplers"]) == 1
    assert state["samplers"][0].backend.name == "pcss-direct-backend"
    assert state["samplers"][0].run_calls == [
        {
            "circuits": [state["submitted_circuit"]],
            "parameter_values": [[0.0]],
            "shots": 321,
            "options": {
                "optimization_level": 2,
                "with_progress_bar": False,
            },
        }
    ]
    assert len(event_requests) == 2

    registry = DirectJobRegistry(registry_path)
    registry_job = registry.get_job(job.job_id())
    assert registry_job is not None
    assert registry_job["provider_job_id"] == "raw-direct-job-1"
    assert registry_job["status"] == "running"
    assert registry_job["cft_job_name"] == "Display name"
    assert registry_job["cft_description"] == "Display description"

    events = registry.list_events(job.job_id())
    assert [event["event_type"] for event in events] == ["submitted", "status_update"]
    assert all(event["error_message"] for event in events)


def test_direct_missing_optional_packages_raise_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_import(name: str, package: str | None = None) -> types.ModuleType:
        del package
        if name.startswith("pcss_qapi"):
            raise ModuleNotFoundError("No module named 'pcss_qapi'", name=name)
        if name.startswith("qiskit_aqt_provider"):
            raise ModuleNotFoundError(
                "No module named 'qiskit_aqt_provider'",
                name=name,
            )
        return importlib.import_module(name)

    monkeypatch.setattr(importlib, "import_module", missing_import)

    from cft_piastq.direct import DirectPcssAdapter

    adapter = DirectPcssAdapter(**{"to" + "ken": "pcss-token-that-must-not-leak"})

    with pytest.raises(DirectModeUnavailableError) as exc_info:
        adapter.run(circuits=[bell_circuit()], shots=10)

    message = str(exc_info.value)
    assert "pcss-qapi" in message
    assert "qiskit-aqt-provider" in message
    assert "pcss-token-that-must-not-leak" not in message


def test_direct_login_error_redacts_configured_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_token = "pcss-token-value"
    install_fake_direct_modules(
        monkeypatch,
        login_error=RuntimeError(f"bad token {raw_token}"),
    )

    from cft_piastq.direct import DirectPcssAdapter

    adapter = DirectPcssAdapter(**{"to" + "ken": raw_token})

    with pytest.raises(DirectProviderError) as exc_info:
        adapter.run(circuits=[bell_circuit()], shots=10)

    message = str(exc_info.value)
    assert "bad token" in message
    assert raw_token not in message
    assert "[REDACTED]" in message


def test_direct_job_unsupported_cancel_records_cancel_requested(
    tmp_path: Path,
) -> None:
    from cft_piastq.registry import DirectJobRegistry

    registry = DirectJobRegistry(tmp_path / "jobs.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="provider-no-cancel",
        owner="local-user",
        status="running",
        shots=20,
        circuit_count=1,
    )
    provider_job = ProviderJobWithoutCancel()
    job = PiastQJob(
        DirectJobHandle(
            provider_job=provider_job,
            shots=20,
            num_bits=1,
            registry=registry,
            local_job_id=local_job_id,
        )
    )

    assert job.cancel() == "cancel_requested"
    assert job.status() == "cancel_requested"

    registry_job = registry.get_job(local_job_id)
    assert registry_job is not None
    assert registry_job["status"] == "cancel_requested"
    assert registry_job["cancel_requested"] == 1


def test_direct_job_result_marks_registry_succeeded(tmp_path: Path) -> None:
    from cft_piastq.registry import DirectJobRegistry

    registry = DirectJobRegistry(tmp_path / "jobs.sqlite3")
    local_job_id = registry.insert_job(
        provider_job_id="provider-result-ready",
        owner="local-user",
        status="running",
        shots=20,
        circuit_count=1,
    )
    job = PiastQJob(
        DirectJobHandle(
            provider_job=ProviderJobWithoutCancel(),
            shots=20,
            num_bits=1,
            registry=registry,
            local_job_id=local_job_id,
        )
    )

    assert job.result() is not None

    registry_job = registry.get_job(local_job_id)
    assert registry_job is not None
    assert registry_job["status"] == "succeeded"


class FakeDirectBackend:
    name = "pcss-direct-backend"


class FakeProvider:
    def __init__(self) -> None:
        self.direct_backend_requested = False

    def get_direct_access_backend(self) -> FakeDirectBackend:
        self.direct_backend_requested = True
        return FakeDirectBackend()


class RawProviderJob:
    def job_id(self) -> str:
        return "raw-direct-job-1"

    def status(self) -> str:
        return "RUNNING"

    def result(self, timeout: float | None = None) -> SamplerResult:
        del timeout
        return SamplerResult(
            [QuasiDistribution({0: 1.0})],
            metadata=[{"shots": 321}],
        )

    def cancel(self) -> str:
        return "CANCELLED"


class ProviderJobWithoutCancel:
    def job_id(self) -> str:
        return "provider-no-cancel"

    def status(self) -> str:
        return "RUNNING"

    def result(self, timeout: float | None = None) -> SamplerResult:
        del timeout
        return SamplerResult(
            [QuasiDistribution({0: 1.0})],
            metadata=[{"shots": 20}],
        )


def install_fake_direct_modules(
    monkeypatch: pytest.MonkeyPatch,
    *,
    login_error: Exception | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "login_tokens": [],
        "providers": [],
        "samplers": [],
        "submitted_circuit": None,
    }

    class FakeAuthorizationService:
        @classmethod
        def login(cls, token: str) -> None:
            if login_error is not None:
                raise login_error
            state["login_tokens"].append(token)

    class RecordingProvider(FakeProvider):
        def __init__(self) -> None:
            super().__init__()
            state["providers"].append(self)

    class RecordingAQTSampler:
        def __init__(self, backend: FakeDirectBackend) -> None:
            self.backend = backend
            self.run_calls: list[dict[str, Any]] = []
            state["samplers"].append(self)

        def run(
            self,
            circuits: list[QuantumCircuit],
            parameter_values: object | None = None,
            shots: int | None = None,
            **options: object,
        ) -> RawProviderJob:
            state["submitted_circuit"] = circuits[0]
            self.run_calls.append(
                {
                    "circuits": circuits,
                    "parameter_values": parameter_values,
                    "shots": shots,
                    "options": dict(sorted(options.items())),
                }
            )
            return RawProviderJob()

    install_module(
        monkeypatch,
        "pcss_qapi",
        {"AuthorizationService": FakeAuthorizationService},
    )
    install_module(monkeypatch, "pcss_qapi.aqt", {})
    install_module(
        monkeypatch,
        "pcss_qapi.aqt.provider",
        {"PCSS_AQTProvider": RecordingProvider},
    )
    install_module(monkeypatch, "qiskit_aqt_provider", {})
    install_module(
        monkeypatch,
        "qiskit_aqt_provider.primitives",
        {"AQTSampler": RecordingAQTSampler},
    )
    return state


def install_module(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    attributes: dict[str, object],
) -> None:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
