from __future__ import annotations

import base64

import pytest
from qiskit import QuantumCircuit


def bell_circuit() -> QuantumCircuit:
    circuit = QuantumCircuit(2, 2, name="bell")
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    return circuit


def assert_same_circuit_shape(
    original: QuantumCircuit, restored: QuantumCircuit
) -> None:
    assert restored.name == original.name
    assert restored.num_qubits == original.num_qubits
    assert restored.num_clbits == original.num_clbits
    assert dict(restored.count_ops()) == dict(original.count_ops())


def test_circuit_to_qpy_base64_round_trips_bell_circuit() -> None:
    from cft_piastq.serialization import circuit_to_qpy_base64, qpy_base64_to_circuit

    encoded = circuit_to_qpy_base64(bell_circuit())
    restored = qpy_base64_to_circuit(encoded)

    assert isinstance(encoded, str)
    assert_same_circuit_shape(bell_circuit(), restored)


def test_circuit_to_qpy_base64_supports_two_circuit_requests() -> None:
    from cft_piastq.serialization import (
        circuits_to_qpy_base64,
        qpy_base64_to_circuits,
    )

    bell = bell_circuit()
    parity = QuantumCircuit(3, 2, name="parity")
    parity.cx(0, 2)
    parity.cx(1, 2)
    parity.measure([0, 2], [0, 1])

    restored = qpy_base64_to_circuits(circuits_to_qpy_base64([bell, parity]))

    assert len(restored) == 2
    assert_same_circuit_shape(bell, restored[0])
    assert_same_circuit_shape(parity, restored[1])


def test_circuit_metadata_reports_json_safe_topology_fields() -> None:
    from cft_piastq.serialization import circuit_metadata

    circuit = QuantumCircuit(3, 2, name="metadata")
    circuit.h(0)
    circuit.cx(2, 0)
    circuit.cx(1, 2)
    circuit.measure([0, 2], [0, 1])

    metadata = circuit_metadata(circuit, index=0)

    assert metadata == {
        "circuit_index": 0,
        "circuit_name": "metadata",
        "num_qubits": 3,
        "num_clbits": 2,
        "depth": circuit.depth(),
        "operation_counts": dict(circuit.count_ops()),
        "used_qubits": [0, 1, 2],
        "used_couplings": [[0, 2], [1, 2]],
    }


def test_qpy_decode_rejects_invalid_base64_with_sanitized_error() -> None:
    from cft_piastq.errors import PiastQError
    from cft_piastq.serialization import qpy_base64_to_circuit

    with pytest.raises(PiastQError) as exc_info:
        qpy_base64_to_circuit("not base64 token=secret")

    message = str(exc_info.value)
    assert "invalid base64" in message.lower()
    assert "secret" not in message


def test_qpy_decode_rejects_invalid_qpy_with_sanitized_error() -> None:
    from cft_piastq.errors import PiastQError
    from cft_piastq.serialization import qpy_base64_to_circuit

    encoded = base64.b64encode(b"not a qpy payload token=secret").decode("ascii")

    with pytest.raises(PiastQError) as exc_info:
        qpy_base64_to_circuit(encoded)

    message = str(exc_info.value)
    assert "invalid qpy" in message.lower()
    assert "secret" not in message
