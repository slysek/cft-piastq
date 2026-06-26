"""QPY serialization and circuit metadata helpers."""

from __future__ import annotations

import base64
import binascii
import io
from collections.abc import Sequence
from typing import cast

from qiskit import QuantumCircuit, qpy  # type: ignore[import-untyped]

from .errors import PiastQError
from .security import safe_error_message
from .types import JSONDict


def circuit_to_qpy_base64(circuit: QuantumCircuit) -> str:
    """Return a base64-encoded QPY payload containing one circuit."""

    return circuits_to_qpy_base64([circuit])


def circuits_to_qpy_base64(circuits: Sequence[QuantumCircuit]) -> str:
    """Return a base64-encoded QPY payload containing one or more circuits."""

    circuit_list = list(circuits)
    if not circuit_list:
        raise PiastQError("Cannot serialize an empty QPY circuit payload.")

    buffer = io.BytesIO()
    try:
        qpy.dump(circuit_list, buffer)
    except Exception as exc:  # pragma: no cover - qiskit owns concrete failures
        raise PiastQError(
            f"Unable to serialize QPY circuit payload: {safe_error_message(exc)}"
        ) from exc

    return base64.b64encode(buffer.getvalue()).decode("ascii")


def qpy_base64_to_circuit(qpy_base64: str) -> QuantumCircuit:
    """Decode a base64 QPY payload that contains exactly one circuit."""

    circuits = qpy_base64_to_circuits(qpy_base64)
    if len(circuits) != 1:
        raise PiastQError(
            f"Expected exactly one circuit in QPY payload, found {len(circuits)}."
        )
    return circuits[0]


def qpy_base64_to_circuits(qpy_base64: str) -> list[QuantumCircuit]:
    """Decode a base64 QPY payload into the contained circuits."""

    qpy_bytes = _decode_base64(qpy_base64)
    buffer = io.BytesIO(qpy_bytes)
    try:
        return list(qpy.load(buffer))
    except Exception as exc:
        raise PiastQError(f"Invalid QPY payload: {safe_error_message(exc)}") from exc


def circuit_metadata(circuit: QuantumCircuit, *, index: int) -> JSONDict:
    """Return JSON-safe metadata used when submitting a circuit."""

    return cast(
        JSONDict,
        {
            "circuit_index": index,
            "circuit_name": circuit.name,
            "num_qubits": circuit.num_qubits,
            "num_clbits": circuit.num_clbits,
            "depth": circuit.depth(),
            "operation_counts": dict(circuit.count_ops()),
            "used_qubits": _used_qubits(circuit),
            "used_couplings": _used_couplings(circuit),
        },
    )


def _decode_base64(qpy_base64: str) -> bytes:
    try:
        return base64.b64decode(qpy_base64.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise PiastQError(
            f"Invalid base64 QPY payload: {safe_error_message(exc)}"
        ) from exc


def _used_qubits(circuit: QuantumCircuit) -> list[int]:
    used: set[int] = set()
    for instruction in circuit.data:
        for qubit in instruction.qubits:
            used.add(circuit.find_bit(qubit).index)
    return sorted(used)


def _used_couplings(circuit: QuantumCircuit) -> list[list[int]]:
    couplings: set[tuple[int, int]] = set()
    for instruction in circuit.data:
        if len(instruction.qubits) != 2:
            continue
        qubit_indices = sorted(
            circuit.find_bit(qubit).index for qubit in instruction.qubits
        )
        couplings.add((qubit_indices[0], qubit_indices[1]))
    return [list(pair) for pair in sorted(couplings)]
