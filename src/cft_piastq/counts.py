"""Estimated count views derived from Qiskit quasi distributions."""

from __future__ import annotations

from typing import Any


def estimated_counts_from_result(
    result: Any, *, shots: int, num_bits: int | None = None
) -> list[dict[str, int]]:
    """Return estimated counts for each quasi distribution in a sampler result.

    The returned dictionaries are computed from quasi probabilities and the
    requested shot count. They are display/count-view estimates, not raw
    provider counts.
    """

    counts: list[dict[str, int]] = []
    for quasi_dist in result.quasi_dists:
        probabilities = quasi_dist.binary_probabilities(num_bits=num_bits)
        counts.append(
            {
                bitstring: max(0, round(probability * shots))
                for bitstring, probability in probabilities.items()
            }
        )
    return counts
