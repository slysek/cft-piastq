"""Environment configuration helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from platformdirs import user_cache_path

from .errors import PiastQConfigurationError
from .types import ExecutionMode

_TRUE_VALUES = frozenset({"1", "true", "t", "yes", "y", "on"})
_FALSE_VALUES = frozenset({"0", "false", "f", "no", "n", "off"})
_EXECUTION_MODES = frozenset({"auto", "managed", "direct", "fake"})


@dataclass(frozen=True)
class PiastQEnvironmentConfig:
    """Configuration values read from the process environment."""

    owner: str | None
    token: str | None
    dashboard_api_url: str | None
    dashboard_api_key: str | None
    mode: ExecutionMode
    verbose: bool
    registry_path: Path


def parse_bool(value: object, *, default: bool = False) -> bool:
    """Parse environment-style boolean values."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False

    raise PiastQConfigurationError(f"Expected a boolean-like value, got {value!r}.")


def default_registry_path() -> Path:
    """Return the default direct-mode SQLite registry path."""

    return user_cache_path("cft_piastq") / "jobs.sqlite3"


def read_environment(
    environ: Mapping[str, str] | None = None,
) -> PiastQEnvironmentConfig:
    """Read cft-piastq configuration from environment variables."""

    source = os.environ if environ is None else environ
    mode = _read_execution_mode(source.get("CFT_PIASTQ_MODE", "auto"))
    registry_path = Path(
        source.get("CFT_PIASTQ_REGISTRY_PATH") or default_registry_path()
    )

    return PiastQEnvironmentConfig(
        owner=source.get("CFT_PIASTQ_OWNER"),
        token=source.get("PCSS_TOKEN") or source.get("PCSS_QAPI_TOKEN"),
        dashboard_api_url=source.get("CFT_PIASTQ_DASHBOARD_API_URL"),
        dashboard_api_key=source.get("CFT_PIASTQ_DASHBOARD_API_KEY"),
        mode=mode,
        verbose=parse_bool(source.get("CFT_PIASTQ_VERBOSE"), default=True),
        registry_path=registry_path,
    )


def _read_execution_mode(value: str) -> ExecutionMode:
    normalized = value.strip().lower()
    if normalized not in _EXECUTION_MODES:
        raise PiastQConfigurationError(
            "CFT_PIASTQ_MODE must be one of auto, managed, direct, or fake."
        )
    return cast(ExecutionMode, normalized)
