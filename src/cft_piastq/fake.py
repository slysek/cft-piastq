"""Local fake-backend simulation and dashboard noise conversion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from qiskit import QuantumCircuit, transpile  # type: ignore[import-untyped]
from qiskit.primitives import SamplerResult  # type: ignore[import-untyped]
from qiskit.result import QuasiDistribution  # type: ignore[import-untyped]

from .errors import FakeBackendError
from .security import safe_error_message

_PARAMETER_VALUES_LENGTH_ERROR = (
    "Fake backend parameter_values length does not match circuit parameters."
)

DEFAULT_FAKE_SEED = 12345


class SimulatorAdapter(Protocol):
    """Protocol for the simulator boundary used by fake sampler tests."""

    def run(
        self,
        circuits: list[QuantumCircuit],
        *,
        shots: int,
        noise_model: object | None,
        parameter_values: object | None,
        provider_options: dict[str, object],
    ) -> SamplerResult:
        """Run circuits locally and return a Qiskit sampler result."""


class FakeSamplerAdapter:
    """Qiskit-style fake sampler adapter with injectable simulation backend."""

    def __init__(self, simulator_adapter: SimulatorAdapter | None = None) -> None:
        self._simulator_adapter = simulator_adapter or AerSimulatorAdapter()

    def run(
        self,
        circuits: list[QuantumCircuit],
        *,
        shots: int,
        noise_model: object | None,
        parameter_values: object | None,
        provider_options: dict[str, object],
    ) -> SamplerResult:
        try:
            result = self._simulator_adapter.run(
                list(circuits),
                shots=shots,
                noise_model=noise_model,
                parameter_values=parameter_values,
                provider_options=dict(provider_options),
            )
        except FakeBackendError:
            raise
        except Exception as exc:
            raise FakeBackendError(
                f"Fake backend simulation failed: {safe_error_message(exc)}"
            ) from exc

        if not isinstance(result, SamplerResult):
            raise FakeBackendError("Fake simulator adapter must return SamplerResult.")
        return result


class AerSimulatorAdapter:
    """Adapter around qiskit-aer, imported only when simulation executes."""

    def run(
        self,
        circuits: list[QuantumCircuit],
        *,
        shots: int,
        noise_model: object | None,
        parameter_values: object | None,
        provider_options: dict[str, object],
    ) -> SamplerResult:
        try:
            from qiskit_aer import (  # type: ignore[import-not-found,import-untyped]
                AerSimulator,
            )
        except ImportError as exc:
            raise _missing_aer_error() from exc

        options = dict(provider_options)
        seed_simulator = options.pop("seed_simulator", options.pop("seed", None))
        simulator_kwargs: dict[str, object] = {
            "seed_simulator": (
                DEFAULT_FAKE_SEED if seed_simulator is None else seed_simulator
            )
        }
        if noise_model is not None:
            simulator_kwargs["noise_model"] = noise_model

        simulator = AerSimulator(**simulator_kwargs)
        bound_circuits = _bind_parameter_values(circuits, parameter_values)
        compiled_circuits = transpile(bound_circuits, simulator)
        raw_result = simulator.run(
            compiled_circuits,
            shots=shots,
            **options,
        ).result()

        quasi_dists: list[QuasiDistribution] = []
        metadata: list[dict[str, object]] = []
        for index, _circuit in enumerate(bound_circuits):
            counts = raw_result.get_counts(index)
            quasi_dists.append(_counts_to_quasi_distribution(counts, shots=shots))
            metadata.append({"shots": shots, "simulator": "aer"})

        return SamplerResult(quasi_dists=quasi_dists, metadata=metadata)


def noise_model_from_payload(payload: object) -> object:
    """Convert a dashboard noise payload into an Aer ``NoiseModel``.

    Dashboard-derived payloads are a simulation convenience for local fake runs,
    not a calibrated digital twin of the PiastQ backend.
    """

    if not isinstance(payload, Mapping):
        raise FakeBackendError("Fake backend noise payload must be a JSON object.")

    if "noise_model" in payload:
        return _direct_noise_model_from_payload(payload["noise_model"])

    one_qubit_errors = _entries(
        payload,
        "one_qubit_errors",
        "one_qubit",
        "one-qubit",
        "oneQubitErrors",
    )
    two_qubit_errors = _entries(
        payload,
        "two_qubit_errors",
        "two_qubit",
        "two-qubit",
        "twoQubitErrors",
    )
    readout_errors = _entries(
        payload,
        "readout_errors",
        "readout",
        "readoutErrors",
    )
    rxx_errors = _entries(payload, "rxx_errors", "rxx", "rxxErrors")
    if not any((one_qubit_errors, two_qubit_errors, readout_errors, rxx_errors)):
        raise FakeBackendError("No fake backend noise model is available.")

    noise_api = _import_aer_noise()
    model = noise_api.NoiseModel()
    for entry in one_qubit_errors:
        _add_depolarizing_error(
            model,
            noise_api,
            entry,
            num_qubits=1,
            default_gate=None,
        )
    for entry in two_qubit_errors:
        _add_depolarizing_error(
            model,
            noise_api,
            entry,
            num_qubits=2,
            default_gate=None,
        )
    for entry in rxx_errors:
        _add_depolarizing_error(
            model,
            noise_api,
            entry,
            num_qubits=2,
            default_gate="rxx",
        )
    for entry in readout_errors:
        _add_readout_error(model, noise_api, entry)
    return model


def _direct_noise_model_from_payload(raw_noise_model: object) -> object:
    if raw_noise_model is None:
        raise FakeBackendError("No fake backend noise model is available.")
    if not isinstance(raw_noise_model, Mapping):
        raise FakeBackendError("Fake backend noise_model must be a JSON object.")

    noise_api = _import_aer_noise()
    try:
        return noise_api.NoiseModel.from_dict(dict(raw_noise_model))
    except Exception as exc:  # pragma: no cover - qiskit-aer owns validation details
        raise FakeBackendError(
            f"Unable to load qiskit-aer noise_model: {safe_error_message(exc)}"
        ) from exc


def _import_aer_noise() -> Any:
    try:
        from qiskit_aer.noise import (  # type: ignore[import-not-found,import-untyped]
            NoiseModel,
            ReadoutError,
            depolarizing_error,
        )
    except ImportError as exc:
        raise _missing_aer_error() from exc

    return _AerNoiseApi(
        NoiseModel=NoiseModel,
        ReadoutError=ReadoutError,
        depolarizing_error=depolarizing_error,
    )


class _AerNoiseApi:
    def __init__(
        self,
        *,
        NoiseModel: Any,
        ReadoutError: Any,
        depolarizing_error: Any,
    ) -> None:
        self.NoiseModel = NoiseModel
        self.ReadoutError = ReadoutError
        self.depolarizing_error = depolarizing_error


def _missing_aer_error() -> FakeBackendError:
    return FakeBackendError(
        "qiskit-aer is required for fake backend simulation with Aer. "
        "Install cft-piastq[fake] or qiskit-aer."
    )


def _entries(
    payload: Mapping[object, object],
    *candidate_keys: str,
) -> list[Mapping[object, object]]:
    raw_entries = None
    for key in candidate_keys:
        if key in payload:
            raw_entries = payload[key]
            break
    if raw_entries is None:
        return []
    if not isinstance(raw_entries, list):
        raise FakeBackendError("Fake backend CFT noise entries must be lists.")

    entries: list[Mapping[object, object]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, Mapping):
            raise FakeBackendError("Fake backend CFT noise entries must be objects.")
        entries.append(raw_entry)
    return entries


def _add_depolarizing_error(
    model: Any,
    noise_api: Any,
    entry: Mapping[object, object],
    *,
    num_qubits: int,
    default_gate: str | None,
) -> None:
    probability = _probability(entry)
    gates = _gate_names(entry, default=default_gate)
    qubits = _qubits(entry, expected_count=num_qubits)
    error = noise_api.depolarizing_error(probability, num_qubits)
    if qubits is None:
        model.add_all_qubit_quantum_error(error, gates)
    else:
        model.add_quantum_error(error, gates, qubits)


def _add_readout_error(
    model: Any,
    noise_api: Any,
    entry: Mapping[object, object],
) -> None:
    matrix = _readout_matrix(entry)
    error = noise_api.ReadoutError(matrix)
    qubits = _qubits(entry, expected_count=1)
    if qubits is None:
        model.add_all_qubit_readout_error(error)
    else:
        model.add_readout_error(error, qubits)


def _probability(entry: Mapping[object, object]) -> float:
    raw_probability = _first_present(entry, "probability", "p", "error_probability")
    if raw_probability is None:
        raise FakeBackendError("Fake backend quantum error probability is required.")
    probability = _coerce_float(
        raw_probability,
        "Fake backend quantum error probability must be numeric.",
    )
    if probability < 0 or probability > 1:
        raise FakeBackendError(
            "Fake backend quantum error probability must be between 0 and 1."
        )
    return probability


def _gate_names(
    entry: Mapping[object, object],
    *,
    default: str | None,
) -> list[str]:
    raw_gates = _first_present(entry, "gates", "gate", "instruction")
    if raw_gates is None:
        raw_gates = default
    if isinstance(raw_gates, str):
        gates = [raw_gates]
    elif isinstance(raw_gates, list) and all(
        isinstance(gate, str) for gate in raw_gates
    ):
        gates = raw_gates
    else:
        raise FakeBackendError("Fake backend quantum error gate is required.")

    cleaned = [gate.strip() for gate in gates if gate.strip()]
    if not cleaned:
        raise FakeBackendError("Fake backend quantum error gate is required.")
    return cleaned


def _qubits(
    entry: Mapping[object, object],
    *,
    expected_count: int,
) -> list[int] | None:
    raw_qubits = entry.get("qubits")
    if raw_qubits is None:
        return None
    if not isinstance(raw_qubits, list):
        raise FakeBackendError("Fake backend noise qubits must be a list.")

    qubits: list[int] = []
    for raw_qubit in raw_qubits:
        if isinstance(raw_qubit, bool):
            raise FakeBackendError("Fake backend noise qubits must be integers.")
        try:
            qubits.append(int(raw_qubit))
        except (TypeError, ValueError) as exc:
            raise FakeBackendError(
                "Fake backend noise qubits must be integers."
            ) from exc

    if len(qubits) != expected_count:
        raise FakeBackendError(
            "Fake backend noise qubits do not match the error arity."
        )
    return qubits


def _readout_matrix(entry: Mapping[object, object]) -> list[list[float]]:
    raw_matrix = _first_present(entry, "probabilities", "matrix", "readout_error")
    if raw_matrix is None:
        raise FakeBackendError("Fake backend readout probabilities are required.")
    if not isinstance(raw_matrix, list) or len(raw_matrix) != 2:
        raise FakeBackendError("Fake backend readout probabilities must be 2x2.")

    matrix: list[list[float]] = []
    for raw_row in raw_matrix:
        if not isinstance(raw_row, list) or len(raw_row) != 2:
            raise FakeBackendError("Fake backend readout probabilities must be 2x2.")
        row: list[float] = []
        for raw_probability in raw_row:
            probability = _coerce_float(
                raw_probability,
                "Fake backend readout probabilities must be numeric.",
            )
            if probability < 0 or probability > 1:
                raise FakeBackendError(
                    "Fake backend readout probabilities must be between 0 and 1."
                )
            row.append(probability)
        if abs(sum(row) - 1.0) > 1e-9:
            raise FakeBackendError(
                "Fake backend readout probabilities rows must sum to 1."
            )
        matrix.append(row)
    return matrix


def _first_present(
    entry: Mapping[object, object],
    *keys: str,
) -> object | None:
    for key in keys:
        if key in entry:
            return entry[key]
    return None


def _bind_parameter_values(
    circuits: list[QuantumCircuit],
    parameter_values: object | None,
) -> list[QuantumCircuit]:
    if parameter_values is None:
        return list(circuits)

    if not isinstance(parameter_values, list | tuple):
        values_by_circuit: list[object] = [parameter_values]
    else:
        values_by_circuit = list(parameter_values)

    if (
        len(circuits) == 1
        and values_by_circuit
        and not isinstance(values_by_circuit[0], list | tuple | Mapping)
    ):
        values_by_circuit = [values_by_circuit]

    if len(values_by_circuit) != len(circuits):
        raise FakeBackendError(
            "Fake backend parameter_values must match the circuit count."
        )

    bound_circuits: list[QuantumCircuit] = []
    for circuit, raw_values in zip(circuits, values_by_circuit, strict=True):
        parameters = list(circuit.parameters)
        if not parameters:
            bound_circuits.append(circuit)
            continue
        if isinstance(raw_values, Mapping):
            bindings = dict(raw_values)
        elif isinstance(raw_values, list | tuple):
            if len(raw_values) != len(parameters):
                raise FakeBackendError(_PARAMETER_VALUES_LENGTH_ERROR)
            bindings = dict(zip(parameters, raw_values, strict=True))
        else:
            if len(parameters) != 1:
                raise FakeBackendError(_PARAMETER_VALUES_LENGTH_ERROR)
            bindings = {parameters[0]: raw_values}
        try:
            bound_circuits.append(circuit.assign_parameters(bindings, inplace=False))
        except Exception as exc:
            message = safe_error_message(exc)
            raise FakeBackendError(
                f"Unable to bind fake backend parameter_values: {message}"
            ) from exc
    return bound_circuits


def _counts_to_quasi_distribution(
    counts: Mapping[object, object],
    *,
    shots: int,
) -> QuasiDistribution:
    quasi: dict[int, float] = {}
    for raw_key, raw_count in counts.items():
        try:
            key = _count_key_to_int(raw_key)
            quasi[key] = _coerce_float(raw_count, "count must be numeric") / shots
        except (FakeBackendError, TypeError, ValueError) as exc:
            raise FakeBackendError(
                f"Unable to convert fake backend counts: {safe_error_message(exc)}"
            ) from exc
    return QuasiDistribution(quasi)


def _coerce_float(value: object, error_message: str) -> float:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise FakeBackendError(error_message)
    try:
        return float(value)
    except ValueError as exc:
        raise FakeBackendError(error_message) from exc


def _count_key_to_int(raw_key: object) -> int:
    if isinstance(raw_key, bool):
        raise TypeError("boolean count keys are not supported")
    if isinstance(raw_key, int):
        return raw_key
    if not isinstance(raw_key, str):
        raise TypeError(f"unsupported count key type: {type(raw_key).__name__}")

    bitstring = raw_key.replace(" ", "")
    if bitstring.startswith("0x"):
        return int(bitstring, 16)
    return int(bitstring or "0", 2)
