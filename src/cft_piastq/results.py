"""Reconstruct Qiskit primitive results from dashboard JSON payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qiskit.primitives import SamplerResult
from qiskit.result import QuasiDistribution

from .errors import PiastQError
from .security import safe_error_message


def sampler_result_from_json(payload: Mapping[str, Any]) -> SamplerResult:
    """Return a Qiskit ``SamplerResult`` from a JSON-compatible payload."""

    raw_quasi_dists = payload.get("quasi_dists")
    if not isinstance(raw_quasi_dists, list):
        raise PiastQError("Sampler result payload must include a quasi_dists list.")

    quasi_dists = [
        _quasi_distribution_from_json(raw_dist) for raw_dist in raw_quasi_dists
    ]
    metadata = _metadata_from_json(
        payload.get("metadata"),
        count=len(quasi_dists),
        shots=payload.get("shots"),
    )
    return SamplerResult(quasi_dists=quasi_dists, metadata=metadata)


def _quasi_distribution_from_json(raw_dist: object) -> QuasiDistribution:
    if not isinstance(raw_dist, Mapping):
        raise PiastQError("Each quasi distribution must be a JSON object.")

    converted: dict[int, float] = {}
    for raw_key, raw_probability in raw_dist.items():
        try:
            key = _coerce_quasi_key(raw_key)
            converted[key] = float(raw_probability)
        except (TypeError, ValueError) as exc:
            raise PiastQError(
                f"Invalid quasi distribution entry: {safe_error_message(exc)}"
            ) from exc

    try:
        return QuasiDistribution(converted)
    except Exception as exc:  # pragma: no cover - qiskit owns validation details
        raise PiastQError(
            f"Invalid quasi distribution: {safe_error_message(exc)}"
        ) from exc


def _coerce_quasi_key(raw_key: object) -> int:
    if isinstance(raw_key, bool):
        raise ValueError("boolean quasi distribution keys are not supported")
    if isinstance(raw_key, int):
        return raw_key
    if isinstance(raw_key, str):
        return int(raw_key)
    raise TypeError(f"unsupported quasi distribution key type: {type(raw_key).__name__}")


def _metadata_from_json(
    raw_metadata: object, *, count: int, shots: object
) -> list[dict[str, Any]]:
    if raw_metadata is None:
        metadata = [{} for _ in range(count)]
    elif isinstance(raw_metadata, list):
        metadata = []
        for raw_item in raw_metadata:
            if not isinstance(raw_item, Mapping):
                raise PiastQError("Each sampler metadata entry must be a JSON object.")
            metadata.append(dict(raw_item))
    else:
        raise PiastQError("Sampler result metadata must be a list when provided.")

    if len(metadata) != count:
        raise PiastQError(
            "Sampler result metadata length must match quasi distribution count."
        )

    if shots is not None:
        for item in metadata:
            item.setdefault("shots", shots)

    return metadata
