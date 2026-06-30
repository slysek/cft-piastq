"""Mutable sampler options with CFT-specific keys kept explicit."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping

from .types import JSONValue


class PiastQSamplerOptions(MutableMapping[str, JSONValue]):
    """Dictionary-like sampler options with attribute access."""

    def __init__(self, values: Mapping[str, JSONValue] | None = None) -> None:
        self._values: dict[str, JSONValue] = dict(values or {})

    def __getitem__(self, key: str) -> JSONValue:
        return self._values[key]

    def __setitem__(self, key: str, value: JSONValue) -> None:
        self._values[key] = value

    def __delitem__(self, key: str) -> None:
        del self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __getattr__(self, name: str) -> JSONValue:
        try:
            return self._values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: JSONValue) -> None:
        if name == "_values":
            object.__setattr__(self, name, value)
            return
        self._values[name] = value

    def as_dict(self) -> dict[str, JSONValue]:
        """Return a shallow copy suitable for per-run merging."""

        return dict(self._values)
