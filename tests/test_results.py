from __future__ import annotations

from qiskit.primitives import SamplerResult


def test_sampler_result_from_json_reconstructs_quasi_distributions() -> None:
    from cft_piastq.results import sampler_result_from_json

    payload = {
        "shots": 200,
        "quasi_dists": [
            {"0": 0.5, "3": 0.5},
            {1: 0.25, "2": 0.75},
        ],
        "metadata": [
            {"circuit_index": 0, "circuit_name": "bell"},
            {"circuit_index": 1, "shots": 123, "child_job_refs": ["provider-1"]},
        ],
    }

    result = sampler_result_from_json(payload)

    assert isinstance(result, SamplerResult)
    assert len(result.quasi_dists) == 2
    assert dict(result.quasi_dists[0]) == {0: 0.5, 3: 0.5}
    assert dict(result.quasi_dists[1]) == {1: 0.25, 2: 0.75}
    assert result.metadata == [
        {"circuit_index": 0, "circuit_name": "bell", "shots": 200},
        {"circuit_index": 1, "shots": 123, "child_job_refs": ["provider-1"]},
    ]


def test_sampler_result_from_json_creates_metadata_for_each_logical_circuit() -> None:
    from cft_piastq.results import sampler_result_from_json

    result = sampler_result_from_json(
        {"shots": 50, "quasi_dists": [{"0": 1.0}, {"1": 1.0}]}
    )

    assert len(result.quasi_dists) == 2
    assert result.metadata == [{"shots": 50}, {"shots": 50}]
