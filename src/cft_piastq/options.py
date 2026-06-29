"""Sampler option helpers for CFT metadata and provider options."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from typing import Any

CFT_OPTION_PREFIX = "cft_"
CFT_OPTION_KEYS = frozenset({"cft_job_name", "cft_description"})


class PiastQSamplerOptions(MutableMapping[str, Any]):
    """Mutable sampler options with Qiskit-like attribute access."""

    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        object.__setattr__(self, "_values", dict(values or {}))

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._values[key] = value

    def __delitem__(self, key: str) -> None:
        del self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        self._values[name] = value

    def as_dict(self) -> dict[str, Any]:
        """Return a shallow copy of current option values."""

        return dict(self._values)


def split_cft_options(
    options: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split CFT display metadata from provider options without mutation."""

    cft_options = {
        key: value for key, value in options.items() if _is_cft_option_key(key)
    }
    provider_options = {
        key: value for key, value in options.items() if not _is_cft_option_key(key)
    }
    return cft_options, provider_options


def _is_cft_option_key(key: str) -> bool:
    return key.startswith(CFT_OPTION_PREFIX)