"""Sampler facade for PiastQ execution modes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from qiskit import QuantumCircuit  # type: ignore[import-untyped]

from ._version import __version__
from .backend import DirectPiastQBackend, FakePiastQBackend, ManagedPiastQBackend
from .errors import DirectModeUnavailableError, ManagedJobError, PiastQError
from .job import FakeJobHandle, ManagedJobHandle, PiastQJob
from .options import PiastQSamplerOptions, split_cft_options
from .serialization import circuit_metadata, circuit_to_qpy_base64

DEFAULT_SHOTS = 1024
UNTITLED_JOB_NAME = "Untitled job"


class PiastQSampler:
    """Qiskit-style sampler facade for PiastQ backends."""

    def __init__(
        self,
        backend: ManagedPiastQBackend | DirectPiastQBackend | FakePiastQBackend,
        *,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        self.backend = backend
        self.options = PiastQSamplerOptions(options)

    def run(
        self,
        circuits: QuantumCircuit | Sequence[QuantumCircuit],
        parameter_values: object | None = None,
        shots: int | None = None,
        **run_options: Any,
    ) -> PiastQJob:
        """Submit circuits for execution and return a PiastQ job facade."""

        circuit_list = _normalize_circuits(circuits)
        sampler_options = self.options.as_dict()
        merged_options = dict(sampler_options)
        merged_options.update(run_options)
        cft_options, provider_options = split_cft_options(merged_options)
        sampler_cft_options, _ = split_cft_options(sampler_options)
        run_cft_options, _ = split_cft_options(run_options)
        resolved_shots = _resolve_shots(shots, provider_options)
        cft_job_name = _resolve_job_name(
            sampler_cft_options,
            run_cft_options,
            circuit_list,
        )

        if isinstance(self.backend, ManagedPiastQBackend):
            return self._run_managed(
                self.backend,
                circuit_list,
                parameter_values=parameter_values,
                shots=resolved_shots,
                cft_job_name=cft_job_name,
                cft_description=_optional_text(cft_options.get("cft_description")),
            )

        if isinstance(self.backend, DirectPiastQBackend):
            raise DirectModeUnavailableError(
                "Direct sampler execution is implemented in a later wave."
            )

        if isinstance(self.backend, FakePiastQBackend):
            return self._run_fake(
                self.backend,
                circuit_list,
                parameter_values=parameter_values,
                shots=resolved_shots,
                provider_options=provider_options,
                simulator_adapter=cft_options.get("cft_fake_simulator_adapter"),
            )

        raise PiastQError("Unsupported PiastQ backend handle.")

    def _run_managed(
        self,
        backend: ManagedPiastQBackend,
        circuits: list[QuantumCircuit],
        *,
        parameter_values: object | None,
        shots: int,
        cft_job_name: str,
        cft_description: str | None,
    ) -> PiastQJob:
        payload: dict[str, Any] = {
            "owner": _owner_text(backend.owner),
            "cft_job_name": cft_job_name,
            "cft_description": cft_description,
            "shots": shots,
            "circuits": [
                _managed_circuit_payload(circuit, index)
                for index, circuit in enumerate(circuits)
            ],
            "client_version": __version__,
        }
        if parameter_values is not None:
            payload["parameter_values"] = _jsonish(parameter_values)

        response = backend.dashboard_client.submit_job(
            cast(dict[str, object], payload)
        )
        server_job_id = _server_job_id_from_response(response)
        return PiastQJob(
            ManagedJobHandle(
                dashboard_client=backend.dashboard_client,
                server_job_id=server_job_id,
                shots=shots,
                num_bits=_result_num_bits(circuits),
            )
        )

    def _run_fake(
        self,
        backend: FakePiastQBackend,
        circuits: list[QuantumCircuit],
        *,
        parameter_values: object | None,
        shots: int,
        provider_options: Mapping[str, Any],
        simulator_adapter: object | None,
    ) -> PiastQJob:
        from .fake import FakeSamplerAdapter

        adapter = FakeSamplerAdapter(simulator_adapter=simulator_adapter)
        result = adapter.run(
            circuits,
            shots=shots,
            noise_model=backend.noise_model,
            parameter_values=parameter_values,
            provider_options=dict(provider_options),
        )
        return PiastQJob(
            FakeJobHandle(
                sampler_result=result,
                shots=shots,
                fake_job_id="fake-job",
                num_bits=_result_num_bits(circuits),
            )
        )


def _normalize_circuits(
    circuits: QuantumCircuit | Sequence[QuantumCircuit],
) -> list[QuantumCircuit]:
    if isinstance(circuits, QuantumCircuit):
        return [circuits]

    circuit_list = list(circuits)
    if not circuit_list:
        raise PiastQError("PiastQSampler.run requires at least one circuit.")
    for circuit in circuit_list:
        if not isinstance(circuit, QuantumCircuit):
            raise PiastQError(
                "PiastQSampler.run circuits must be QuantumCircuit objects."
            )
    return circuit_list


def _resolve_shots(shots: int | None, provider_options: dict[str, Any]) -> int:
    raw_shots = (
        shots if shots is not None else provider_options.pop("shots", DEFAULT_SHOTS)
    )
    provider_options.pop("shots", None)
    try:
        resolved_shots = int(raw_shots)
    except (TypeError, ValueError) as exc:
        raise PiastQError("shots must be a positive integer.") from exc
    if resolved_shots <= 0:
        raise PiastQError("shots must be a positive integer.")
    return resolved_shots


def _resolve_job_name(
    sampler_cft_options: Mapping[str, Any],
    run_cft_options: Mapping[str, Any],
    circuits: Sequence[QuantumCircuit],
) -> str:
    for cft_options in (sampler_cft_options, run_cft_options):
        configured_name = _optional_text(cft_options.get("cft_job_name"))
        if configured_name is not None:
            return configured_name

    if len(circuits) == 1:
        circuit_name = _optional_text(circuits[0].name)
        if circuit_name is not None:
            return circuit_name

    return UNTITLED_JOB_NAME


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _managed_circuit_payload(circuit: QuantumCircuit, index: int) -> dict[str, Any]:
    return {
        "circuit_index": index,
        "qpy_base64": circuit_to_qpy_base64(circuit),
        "metadata": circuit_metadata(circuit, index=index),
    }


def _server_job_id_from_response(response: object) -> str:
    if not isinstance(response, Mapping):
        raise ManagedJobError("Dashboard submit response must be a JSON object.")

    raw_job_id = response.get("server_job_id") or response.get("id")
    job_id = _optional_text(raw_job_id)
    if job_id is None:
        raise ManagedJobError(
            "Dashboard submit response did not include a server job identifier."
        )
    return job_id


def _owner_text(owner: object) -> str:
    owner_text = _optional_text(owner)
    return owner_text if owner_text is not None else "unknown"


def _result_num_bits(circuits: Sequence[QuantumCircuit]) -> int | None:
    if not circuits:
        return None
    return max(circuit.num_clbits or circuit.num_qubits for circuit in circuits)


def _jsonish(value: object) -> object:
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return tolist()
    if isinstance(value, tuple):
        return [_jsonish(item) for item in value]
    if isinstance(value, list):
        return [_jsonish(item) for item in value]
    return value
