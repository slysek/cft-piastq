from __future__ import annotations

from qiskit.primitives import SamplerResult
from qiskit.result import QuasiDistribution


def test_estimated_counts_from_result_returns_list_for_single_distribution() -> None:
    from cft_piastq.counts import estimated_counts_from_result

    result = SamplerResult([QuasiDistribution({0: 0.5, 3: 0.5})], metadata=[{}])

    assert estimated_counts_from_result(result, shots=200, num_bits=2) == [
        {"00": 100, "11": 100}
    ]


def test_estimated_counts_from_result_floors_negative_quasi_probabilities() -> None:
    from cft_piastq.counts import estimated_counts_from_result

    result = SamplerResult([QuasiDistribution({0: -0.1, 1: 1.1})], metadata=[{}])

    assert estimated_counts_from_result(result, shots=100, num_bits=1) == [
        {"0": 0, "1": 110}
    ]
