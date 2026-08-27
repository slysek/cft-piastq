from __future__ import annotations

import importlib
import json
import sqlite3
import sys
import traceback
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
RAW_PROVIDER_EXCEPTION = "raw-provider-exception-sentinel"
RAW_PROVIDER_PAYLOAD = "raw-provider-payload-sentinel"


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


def test_direct_client_returns_lazy_logical_job_and_aggregates_children(
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

    circuit = bell_circuit()
    from cft_piastq.serialization import circuit_to_qpy_base64

    qpy_payload = circuit_to_qpy_base64(circuit)
    job = sampler.run(
        circuit,
        parameter_values=[[0.0]],
        shots=321,
        cft_description="Display description",
        optimization_level=2,
    )

    assert job.job_id().startswith("direct-")
    assert job.status() == "queued"
    assert state["login_tokens"] == ["pcss-token-value"]
    assert len(state["providers"]) == 1
    assert state["providers"][0].direct_backend_requested is True
    assert len(state["samplers"]) == 1
    assert state["samplers"][0].backend.name == "pcss-direct-backend"
    assert state["samplers"][0].run_calls == []
    assert len(event_requests) == 2

    result = job.result()

    assert dict(result.quasi_dists[0]) == {0: 1.0}
    assert result.metadata[0]["shots"] == 321
    assert result.metadata[0]["cft_piastq_parts"] == 2
    assert state["samplers"][0].run_calls == [
        {
            "circuits": [state["submitted_circuit"]],
            "parameter_values": [[0.0]],
            "shots": 200,
            "options": {
                "optimization_level": 2,
                "with_progress_bar": False,
            },
        },
        {
            "circuits": [state["submitted_circuit"]],
            "parameter_values": [[0.0]],
            "shots": 121,
            "options": {
                "optimization_level": 2,
                "with_progress_bar": False,
            },
        },
    ]
    assert state["child_result_calls"] == [200, 121]
    assert job.counts() == [{"00": 321}]
    assert job.status() == "succeeded"
    assert job.result() is result
    assert job.counts() == [{"00": 321}]
    assert [call["shots"] for call in state["samplers"][0].run_calls] == [200, 121]

    registry = DirectJobRegistry(registry_path)
    registry_job = registry.get_job(job.job_id())
    assert registry_job is not None
    assert registry_job["provider_job_id"] == job.job_id()
    assert registry_job["status"] == "succeeded"
    assert registry_job["cft_job_name"] == "Display name"
    assert registry_job["cft_description"] == "Display description"
    metadata = json.loads(str(registry_job["metadata_json"]))
    assert metadata == {
        "completed_parts": 0,
        "total_parts": 2,
        "total_shots": 321,
    }

    events = registry.list_events(job.job_id())
    assert [event["event_type"] for event in events] == [
        "submitted",
        "status_update",
        "status_update",
        "result_ready",
        "status_update",
    ]
    assert all(event["error_message"] for event in events)
    submitted_payload = json.loads(str(events[0]["payload_json"]))
    assert submitted_payload == {
        "circuit_count": 1,
        "provider_job_id": "[REDACTED]",
        "shots": 321,
        "status": "queued",
        "total_parts": 2,
    }
    with sqlite3.connect(registry_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM direct_jobs").fetchone() == (1,)
    assert {event["local_job_id"] for event in registry.list_events()} == {
        job.job_id()
    }
    serialized_registry = json.dumps(
        {"job": registry_job, "events": events},
        sort_keys=True,
        default=str,
    )
    assert "pcss-token-value" not in serialized_registry
    assert qpy_payload not in serialized_registry
    assert "raw-direct-job-1" not in serialized_registry
    assert RAW_PROVIDER_EXCEPTION not in serialized_registry
    assert RAW_PROVIDER_PAYLOAD not in serialized_registry
    assert set(metadata) == {"completed_parts", "total_parts", "total_shots"}
    assert all(type(value) is int for value in metadata.values())


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
    formatted = "".join(traceback.format_exception(exc_info.value))
    assert "bad token" in message
    assert raw_token not in message
    assert "[REDACTED]" in message
    assert raw_token not in formatted
    assert "Unable to authenticate PCSS direct mode" in formatted
    assert exc_info.value.__cause__ is None


def test_direct_backend_setup_error_has_no_raw_exception_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_token = "pcss-token-value"
    install_fake_direct_modules(
        monkeypatch,
        backend_error=RuntimeError(f"PCSS_TOKEN={raw_token}"),
    )

    from cft_piastq.direct import DirectPcssAdapter

    adapter = DirectPcssAdapter(**{"to" + "ken": raw_token})

    with pytest.raises(DirectProviderError) as exc_info:
        adapter.run(circuits=[bell_circuit()], shots=10)

    formatted = "".join(traceback.format_exception(exc_info.value))
    assert raw_token not in formatted
    assert "Unable to create PCSS direct access backend" in formatted
    assert "[REDACTED]" in formatted
    assert exc_info.value.__cause__ is None


def test_direct_submit_error_redacts_configured_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_token = "pcss-token-value"
    install_fake_direct_modules(
        monkeypatch,
        run_error=RuntimeError(f"submit failed with token {raw_token}"),
    )

    from cft_piastq.direct import DirectPcssAdapter

    adapter = DirectPcssAdapter(**{"to" + "ken": raw_token})

    job = adapter.run(circuits=[bell_circuit()], shots=10)

    with pytest.raises(DirectProviderError) as exc_info:
        job.result()

    message = str(exc_info.value)
    formatted = "".join(traceback.format_exception(exc_info.value))
    assert "Direct PCSS part 1/1 failed" in message
    assert "submit failed" in message
    assert raw_token not in message
    assert "[REDACTED]" in message
    assert raw_token not in formatted
    assert "Direct PCSS part 1/1 failed" in formatted
    assert exc_info.value.__cause__ is None


def test_direct_adapter_rejects_missing_shots_before_dependency_setup() -> None:
    from cft_piastq.direct import DirectPcssAdapter

    adapter = DirectPcssAdapter(**{"to" + "ken": "unused-token"})

    with pytest.raises(DirectProviderError, match="positive integer"):
        adapter.run(circuits=[bell_circuit()], shots=None)


def test_direct_adapter_requires_boolean_progress_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnsafeProgressOption:
        def __bool__(self) -> bool:
            raise AssertionError("must not coerce custom provider option")

    install_fake_direct_modules(monkeypatch)

    from cft_piastq.direct import DirectPcssAdapter

    adapter = DirectPcssAdapter(**{"to" + "ken": "pcss-token-value"})

    with pytest.raises(
        DirectProviderError,
        match="with_progress_bar must be a boolean",
    ):
        adapter.run(
            circuits=[bell_circuit()],
            shots=10,
            provider_options={"with_progress_bar": UnsafeProgressOption()},
        )


@pytest.mark.parametrize(
    ("provider_options", "expected_show_progress"),
    [
        ({"optimization_level": 2}, True),
        ({"optimization_level": 2, "with_progress_bar": False}, False),
    ],
)
def test_direct_adapter_moves_progress_option_to_logical_job(
    monkeypatch: pytest.MonkeyPatch,
    provider_options: dict[str, object],
    expected_show_progress: bool,
) -> None:
    state = install_fake_direct_modules(monkeypatch)

    from cft_piastq.direct import DirectPcssAdapter

    adapter = DirectPcssAdapter(**{"to" + "ken": "pcss-token-value"})
    job = adapter.run(
        circuits=[bell_circuit()],
        shots=10,
        provider_options=provider_options,
    )

    assert job.show_progress is expected_show_progress
    assert job.provider_options == {"optimization_level": 2}
    assert state["samplers"][0].run_calls == []


def test_direct_adapter_snapshots_nested_inputs_before_lazy_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = install_fake_direct_modules(monkeypatch)

    from cft_piastq.direct import DirectPcssAdapter

    circuit = bell_circuit()
    parameter_values = [[0.0]]
    provider_config = {"levels": [1, 2]}
    provider_options = {
        "with_progress_bar": False,
        "provider_config": provider_config,
    }
    initial_instruction_count = len(circuit.data)
    adapter = DirectPcssAdapter(**{"to" + "ken": "pcss-token-value"})
    job = adapter.run(
        circuits=[circuit],
        parameter_values=parameter_values,
        shots=10,
        provider_options=provider_options,
    )

    circuit.x(0)
    parameter_values[0][0] = 9.0
    provider_config["levels"].append(3)
    job.result()

    call = state["samplers"][0].run_calls[0]
    submitted_circuit = call["circuits"][0]
    assert submitted_circuit is not circuit
    assert len(submitted_circuit.data) == initial_instruction_count
    assert call["parameter_values"] == [[0.0]]
    assert call["options"]["provider_config"] == {"levels": [1, 2]}


def test_direct_adapter_copy_failure_is_generic_and_token_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_token = "pcss-token-value"

    class UncopyableOption:
        def __deepcopy__(self, memo: dict[int, object]) -> object:
            del memo
            raise RuntimeError(f"PCSS_TOKEN={raw_token}")

    install_fake_direct_modules(monkeypatch)

    from cft_piastq.direct import DirectPcssAdapter

    adapter = DirectPcssAdapter(**{"to" + "ken": raw_token})

    with pytest.raises(DirectProviderError) as exc_info:
        adapter.run(
            circuits=[bell_circuit()],
            shots=10,
            provider_options={"provider_config": UncopyableOption()},
        )

    assert str(exc_info.value) == "Unable to snapshot direct job inputs."
    assert raw_token not in str(exc_info.value)


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
    def __init__(self, shots: int, child_result_calls: list[int]) -> None:
        self.shots = shots
        self.child_result_calls = child_result_calls

    def job_id(self) -> str:
        return "raw-direct-job-1"

    def status(self) -> str:
        return "RUNNING"

    def result(self) -> SamplerResult:
        self.child_result_calls.append(self.shots)
        return SamplerResult(
            [QuasiDistribution({0: 1.0})],
            metadata=[
                {
                    "shots": self.shots,
                    "provider_exception": RAW_PROVIDER_EXCEPTION,
                    "provider_payload": RAW_PROVIDER_PAYLOAD,
                }
            ],
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
    backend_error: Exception | None = None,
    run_error: Exception | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "login_tokens": [],
        "providers": [],
        "samplers": [],
        "submitted_circuit": None,
        "child_result_calls": [],
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

        def get_direct_access_backend(self) -> FakeDirectBackend:
            if backend_error is not None:
                raise backend_error
            return super().get_direct_access_backend()

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
            if run_error is not None:
                raise run_error
            assert shots is not None
            return RawProviderJob(shots, state["child_result_calls"])

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
