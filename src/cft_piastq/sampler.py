"""Qiskit-like sampler facade for PiastQ backends."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeAlias, cast

from qiskit import QuantumCircuit  # type: ignore[import-untyped]

from ._version import __version__
from .backend import DirectPiastQBackend, FakePiastQBackend, ManagedPiastQBackend
from .errors import ManagedJobError, PiastQConfigurationError
from .job import PiastQJob
from .options import PiastQSamplerOptions
from .serialization import circuit_to_qpy_base64
from .types import JSONDict, JSONValue

PiastQBackend: TypeAlias = (
    ManagedPiastQBackend | DirectPiastQBackend | FakePiastQBackend
)


class PiastQSampler:
    """Sampler facade that routes managed jobs through the PiastQ dashboard."""

    def __init__(
        self,
        backend: PiastQBackend,
        *,
        options: Mapping[str, JSONValue] | None = None,
    ) -> None:
        self._backend = backend
        self.options = PiastQSamplerOptions(options)

    def run(
        self,
        circuits: QuantumCircuit | Sequence[QuantumCircuit],
        parameter_values: JSONValue | None = None,
        shots: int | None = None,
        **run_options: JSONValue,
    ) -> PiastQJob:
        """Submit circuits for execution and return a PiastQ job wrapper."""

        if not isinstance(self._backend, ManagedPiastQBackend):
            raise PiastQConfigurationError(
                "PiastQSampler currently supports managed dashboard backends."
            )

        circuit_list = _normalize_circuits(circuits)
        payload = _managed_payload(
            circuit_list,
            owner=_owner_from_backend(self._backend),
            parameter_values=parameter_values,
            shots=shots,
            sampler_options=self.options.as_dict(),
            run_options=run_options,
        )
        response = self._backend.dashboard_client.submit_job(payload)
        return PiastQJob(
            backend=self._backend,
            server_job_id=_server_job_id(response),
            shots=shots,
            initial_status=response.get("status"),
        )


def _normalize_circuits(
    circuits: QuantumCircuit | Sequence[QuantumCircuit],
) -> list[QuantumCircuit]:
    if isinstance(circuits, QuantumCircuit):
        return [circuits]

    circuit_list = list(circuits)
    if not circuit_list:
        raise PiastQConfigurationError("Sampler run requires at least one circuit.")
    return circuit_list


def _managed_payload(
    circuits: Sequence[QuantumCircuit],
    *,
    owner: str,
    parameter_values: JSONValue | None,
    shots: int | None,
    sampler_options: Mapping[str, JSONValue],
    run_options: Mapping[str, JSONValue],
) -> JSONDict:
    merged_options = dict(sampler_options)
    merged_options.update(run_options)
    cft_options, _provider_options = _split_options(merged_options)

    payload = cast(
        JSONDict,
        {
            "owner": owner,
            "circuits": [
                {"qpy_base64": circuit_to_qpy_base64(circuit)}
                for circuit in circuits
            ],
            "shots": shots,
            "client_version": __version__,
        },
    )
    if parameter_values is not None:
        payload["parameter_values"] = parameter_values

    payload.update(_dashboard_cft_options(cft_options))
    payload["cft_job_name"] = _job_name(cft_options, circuits)
    return payload


def _split_options(
    options: Mapping[str, JSONValue],
) -> tuple[JSONDict, JSONDict]:
    cft_options: JSONDict = {}
    provider_options: JSONDict = {}
    for key, value in options.items():
        if key.startswith("cft_"):
            cft_options[key] = value
            continue
        provider_options[key] = value
    return cft_options, provider_options


def _dashboard_cft_options(options: Mapping[str, JSONValue]) -> JSONDict:
    dashboard_options: JSONDict = {}
    for key in ("cft_description",):
        value = options.get(key)
        if value is not None:
            dashboard_options[key] = value
    return dashboard_options


def _job_name(
    cft_options: Mapping[str, JSONValue],
    circuits: Sequence[QuantumCircuit],
) -> str:
    configured_name = cft_options.get("cft_job_name")
    if isinstance(configured_name, str) and configured_name.strip():
        return configured_name

    if len(circuits) == 1:
        circuit_name = circuits[0].name
        if isinstance(circuit_name, str) and circuit_name:
            return circuit_name

    return "Untitled job"


def _server_job_id(payload: Mapping[str, JSONValue]) -> str:
    raw_job_id = payload.get("server_job_id") or payload.get("id")
    if isinstance(raw_job_id, str) and raw_job_id.strip():
        return raw_job_id

    raise ManagedJobError("Dashboard submit response did not include a job id.")


def _owner_from_backend(backend: ManagedPiastQBackend) -> str:
    owner = getattr(backend.owner, "owner", None)
    if isinstance(owner, str) and owner.strip():
        return owner
    raise PiastQConfigurationError(
        "Managed dashboard jobs require an owner. "
        "Pass owner='your-name' to PiastQClient."
    )
