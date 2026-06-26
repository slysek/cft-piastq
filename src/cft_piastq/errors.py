"""Public exception hierarchy for cft-piastq."""

from __future__ import annotations


class PiastQError(Exception):
    """Base class for all public cft-piastq exceptions."""


class PiastQConfigurationError(PiastQError):
    """Raised when client configuration is invalid or incomplete."""


class DashboardUnavailableError(PiastQError):
    """Raised when the managed dashboard cannot be reached or is unhealthy."""


class DashboardAuthError(PiastQError):
    """Raised when dashboard authentication or authorization fails."""


class ManagedJobError(PiastQError):
    """Raised when a managed dashboard job fails."""


class DirectModeUnavailableError(PiastQError):
    """Raised when direct PCSS/AQT mode cannot be used locally."""


class DirectProviderError(PiastQError):
    """Raised when a direct provider operation fails."""


class FakeBackendError(PiastQError):
    """Raised when local fake backend execution cannot proceed."""


class PiastQTimeoutError(PiastQError):
    """Raised when waiting for a job exceeds the configured timeout."""
