from __future__ import annotations

import sys
from types import ModuleType

import httpx
import pytest
from qiskit import QuantumCircuit
from qiskit.primitives import SamplerResult
from qiskit.result import QuasiDistribution

from cft_piastq.backend import FakePiastQBackend
from cft_piastq.client import PiastQClient
from cft_piastq.errors import FakeBackendError
from cft_piastq.job import PiastQJob
from cft_piastq.sampler import PiastQSampler

BASE_URL = "https://dashboard.example"


class RecordingSimulatorAdapter:
    def __init__(self, result: SamplerResult | None = None) -> None:
        self.result = result or SamplerResult(
            [QuasiDistribution({0: 0.5, 3: 0.5})],
            metadata=[{"adapter": "recording"}],
        )
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        circuits: list[QuantumCircuit],
        *,
        shots: int,
        noise_model: object | None,
        parameter_values: object | None,
        provider_options: dict[str, object],
    ) -> SamplerResult:
        self.calls.append(
            {
                "circuits": list(circuits),
                "shots": shots,
                "noise_model": noise_model,
                "parameter_values": parameter_values,
                "provider_options": dict(provider_options),
            }
        )
        return self.result


class RejectingDashboardClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def submit_job(self, _payload: object) -> object:
        self.calls.append("submit_job")
        raise AssertionError("fake sampler must not submit dashboard jobs")

    def get_job(self, _server_job_id: str) -> object:
        self.calls.append("get_job")
        raise AssertionError("fake sampler must not poll dashboard jobs")

    def get_result(self, _server_job_id: str) -> object:
        self.calls.append("get_result")
        raise AssertionError("fake sampler must not read dashboard job results")

    def cancel_job(self, _server_job_id: str) -> object:
        self.calls.append("cancel_job")
        raise AssertionError("fake sampler must not cancel dashboard jobs")

    def get_noise_model(self) -> object:
        self.calls.append("get_noise_model")
        raise AssertionError("fake sampler must not fetch dashboard noise")

    def record_event(self, _event: object) -> object:
        self.calls.append("record_event")
        raise AssertionError("fake sampler must not emit direct-mode events")


def bell_circuit() -> QuantumCircuit:
    circuit = QuantumCircuit(2, 2, name="bell")
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    return circuit


def install_fake_aer_noise(monkeypatch: pytest.MonkeyPatch) -> type:
    aer_module = ModuleType("qiskit_aer")
    noise_module = ModuleType("qiskit_aer.noise")

    class NoiseModel:
        def __init__(self) -> None:
            self.source: dict[str, object] | None = None
            self.quantum_errors: list[tuple[object, ...]] = []
            self.readout_errors: list[tuple[object, ...]] = []

        @classmethod
        def from_dict(cls, payload: dict[str, object]) -> "NoiseModel":
            model = cls()
            model.source = dict(payload)
            return model

        def add_all_qubit_quantum_error(
            self, error: object, gates: str | list[str]
        ) -> None:
            self.quantum_errors.append(("all", _tupled(gates), None, error))

        def add_quantum_error(
            self,
            error: object,
            gates: str | list[str],
            qubits: list[int],
        ) -> None:
            self.quantum_errors.append(
                ("qubits", _tupled(gates), tuple(qubits), error)
            )

        def add_all_qubit_readout_error(self, error: object) -> None:
            self.readout_errors.append(("all", None, error))

        def add_readout_error(self, error: object, qubits: list[int]) -> None:
            self.readout_errors.append(("qubits", tuple(qubits), error))

    class ReadoutError:
        def __init__(self, probabilities: list[list[float]]) -> None:
            self.probabilities = probabilities

        def __eq__(self, other: object) -> bool:
            return (
                isinstance(other, ReadoutError)
                and self.probabilities == other.probabilities
            )

    def depolarizing_error(probability: float, num_qubits: int) -> tuple[str, float, int]:
        return ("depolarizing", probability, num_qubits)

    noise_module.NoiseModel = NoiseModel
    noise_module.ReadoutError = ReadoutError
    noise_module.depolarizing_error = depolarizing_error
    monkeypatch.setitem(sys.modules, "qiskit_aer", aer_module)
    monkeypatch.setitem(sys.modules, "qiskit_aer.noise", noise_module)
    return NoiseModel


def _tupled(value: str | list[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def test_client_fake_backend_without_noise_does_not_call_dashboard_noise_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise AssertionError("fake_backend(use_backend_noise=False) must stay local")

    client = PiastQClient(
        mode="fake",
        dashboard_api_url=BASE_URL,
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )

    backend = client.fake_backend(use_backend_noise=False)

    assert isinstance(backend, FakePiastQBackend)
    assert backend.mode == "fake"
    assert backend.use_backend_noise is False
    assert backend.dashboard_client is None
    assert backend.noise_model is None
    assert requests == []


def test_fake_sampler_run_returns_job_and_stays_off_dashboard() -> None:
    dashboard_client = RejectingDashboardClient()
    simulator_adapter = RecordingSimulatorAdapter()
    backend = FakePiastQBackend(
        mode="fake",
        owner="szymo",
        dashboard_client=dashboard_client,  # type: ignore[arg-type]
    )
    sampler = PiastQSampler(backend)

    job = sampler.run(
        bell_circuit(),
        shots=200,
        seed_simulator=123,
        cft_fake_simulator_adapter=simulator_adapter,
    )

    assert isinstance(job, PiastQJob)
    assert job.status() == "succeeded"
    assert job.result() is simulator_adapter.result
    assert job.counts(num_bits=2) == [{"00": 100, "11": 100}]
    assert dashboard_client.calls == []
    assert len(simulator_adapter.calls) == 1
    assert simulator_adapter.calls[0]["shots"] == 200
    assert simulator_adapter.calls[0]["noise_model"] is None
    assert simulator_adapter.calls[0]["parameter_values"] is None
    assert simulator_adapter.calls[0]["provider_options"] == {"seed_simulator": 123}
    assert simulator_adapter.calls[0]["circuits"][0].name == "bell"  # type: ignore[index]


def test_fake_sampler_adapter_uses_injected_simulator_without_importing_aer() -> None:
    sys.modules.pop("qiskit_aer", None)
    sys.modules.pop("qiskit_aer.noise", None)

    from cft_piastq.fake import FakeSamplerAdapter

    simulator_adapter = RecordingSimulatorAdapter()
    adapter = FakeSamplerAdapter(simulator_adapter=simulator_adapter)

    result = adapter.run(
        [bell_circuit()],
        shots=50,
        noise_model=None,
        parameter_values=None,
        provider_options={},
    )

    assert result is simulator_adapter.result
    assert simulator_adapter.calls[0]["shots"] == 50
    assert "qiskit_aer" not in sys.modules


def test_client_fake_backend_with_noise_fetches_and_converts_latest_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    noise_model_type = install_fake_aer_noise(monkeypatch)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.path == "/api/noise-model/latest"
        return httpx.Response(200, json={"noise_model": {"errors": []}})

    client = PiastQClient(
        mode="fake",
        dashboard_api_url=BASE_URL,
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )

    backend = client.fake_backend(use_backend_noise=True)

    assert backend.use_backend_noise is True
    assert isinstance(backend.noise_model, noise_model_type)
    assert backend.noise_model.source == {"errors": []}  # type: ignore[union-attr]
    assert [request.url.path for request in requests] == ["/api/noise-model/latest"]


def test_noise_model_from_payload_supports_direct_aer_noise_model_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    noise_model_type = install_fake_aer_noise(monkeypatch)

    from cft_piastq.fake import noise_model_from_payload

    model = noise_model_from_payload({"noise_model": {"errors": []}})

    assert isinstance(model, noise_model_type)
    assert model.source == {"errors": []}


def test_noise_model_from_payload_supports_dashboard_cft_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_aer_noise(monkeypatch)

    from cft_piastq.fake import noise_model_from_payload

    model = noise_model_from_payload(
        {
            "one_qubit_errors": [
                {"gate": "x", "probability": 0.01},
            ],
            "two_qubit_errors": [
                {"gate": "cx", "qubits": [0, 1], "probability": 0.02},
            ],
            "readout_errors": [
                {
                    "qubits": [0],
                    "probabilities": [[0.98, 0.02], [0.03, 0.97]],
                },
            ],
            "rxx_errors": [
                {"qubits": [0, 1], "probability": 0.03},
            ],
        }
    )

    assert ("all", ("x",), None, ("depolarizing", 0.01, 1)) in model.quantum_errors
    assert (
        "qubits",
        ("cx",),
        (0, 1),
        ("depolarizing", 0.02, 2),
    ) in model.quantum_errors
    assert (
        "qubits",
        ("rxx",),
        (0, 1),
        ("depolarizing", 0.03, 2),
    ) in model.quantum_errors
    assert len(model.readout_errors) == 1
    readout_target, readout_qubits, readout_error = model.readout_errors[0]
    assert readout_target == "qubits"
    assert readout_qubits == (0,)
    assert readout_error.probabilities == [[0.98, 0.02], [0.03, 0.97]]


def test_noise_model_from_payload_rejects_unavailable_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_aer_noise(monkeypatch)

    from cft_piastq.fake import noise_model_from_payload

    with pytest.raises(FakeBackendError, match="No fake backend noise model"):
        noise_model_from_payload({})


def test_noise_model_from_payload_rejects_malformed_payload_without_leaking_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_aer_noise(monkeypatch)

    from cft_piastq.fake import noise_model_from_payload

    with pytest.raises(FakeBackendError) as exc_info:
        noise_model_from_payload(
            {"noise_model": "not an object", "debug": "internal-do-not-leak"}
        )

    message = str(exc_info.value)
    assert "noise_model" in message
    assert "internal-do-not-leak" not in message


def test_noise_model_from_payload_raises_clear_error_when_aer_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "qiskit_aer", None)
    monkeypatch.delitem(sys.modules, "qiskit_aer.noise", raising=False)

    from cft_piastq.fake import noise_model_from_payload

    with pytest.raises(FakeBackendError, match="qiskit-aer"):
        noise_model_from_payload({"noise_model": {"errors": []}})
