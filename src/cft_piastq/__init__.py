"""Public package exports for cft-piastq."""

from __future__ import annotations

from ._version import __version__
from .client import PiastQClient
from .errors import (
    DashboardAuthError,
    DashboardUnavailableError,
    DirectModeUnavailableError,
    DirectProviderError,
    FakeBackendError,
    ManagedJobError,
    PiastQConfigurationError,
    PiastQError,
    PiastQTimeoutError,
)


class _Wave0FacadeGuard:
    """Temporary public facade until later implementation waves add behavior."""

    _facade_name = "PiastQ facade"

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise PiastQConfigurationError(
            f"{self._facade_name} is a Wave 0 import guard. "
            "Use it after a later implementation wave adds the real facade."
        )


class PiastQSampler(_Wave0FacadeGuard):
    """Importable placeholder for the sampler facade."""

    _facade_name = "PiastQSampler"


class PiastQJob(_Wave0FacadeGuard):
    """Importable placeholder for the job facade."""

    _facade_name = "PiastQJob"


__all__ = [
    "__version__",
    "DashboardAuthError",
    "DashboardUnavailableError",
    "DirectModeUnavailableError",
    "DirectProviderError",
    "FakeBackendError",
    "ManagedJobError",
    "PiastQClient",
    "PiastQConfigurationError",
    "PiastQError",
    "PiastQJob",
    "PiastQSampler",
    "PiastQTimeoutError",
]
