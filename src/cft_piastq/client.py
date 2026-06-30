"""Public PiastQ client facade and execution mode selection."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import httpx

from .backend import DirectPiastQBackend, FakePiastQBackend, ManagedPiastQBackend
from .config import parse_bool, read_environment
from .errors import (
    DashboardAuthError,
    DashboardUnavailableError,
    DirectModeUnavailableError,
    PiastQConfigurationError,
)
from .http import DashboardClient
from .types import ExecutionMode, ResolvedExecutionMode

_EXECUTION_MODES = frozenset({"auto", "managed", "direct", "fake"})


class PiastQClient:
    """Select and hold the execution backend for PiastQ jobs."""

    def __init__(
        self,
        *,
        owner: str | None = None,
        mode: ExecutionMode | str | None = None,
        token: str | None = None,
        dashboard_api_url: str | None = None,
        dashboard_api_key: str | None = None,
        registry_path: str | Path | None = None,
        verbose: bool | str | None = None,
        http_client: httpx.Client | None = None,
        http_transport: httpx.BaseTransport | None = None,
        timeout: float | httpx.Timeout | None = None,
        use_backend_noise: bool | str = False,
    ) -> None:
        env = read_environment()

        self._owner = _optional_non_empty(owner if owner is not None else env.owner)
        self._requested_mode = _normalize_mode(mode if mode is not None else env.mode)
        self._token = _optional_non_empty(token if token is not None else env.token)
        self._dashboard_api_url = _optional_non_empty(
            dashboard_api_url
            if dashboard_api_url is not None
            else env.dashboard_api_url
        )
        self._dashboard_api_key = _optional_non_empty(
            dashboard_api_key
            if dashboard_api_key is not None
            else env.dashboard_api_key
        )
        self._registry_path = (
            Path(registry_path) if registry_path is not None else env.registry_path
        )
        self._verbose = (
            parse_bool(verbose, default=env.verbose)
            if verbose is not None
            else env.verbose
        )
        self._use_backend_noise = parse_bool(use_backend_noise, default=False)
        self._http_client = http_client
        self._http_transport = http_transport
        self._timeout = timeout
        self._dashboard_client: DashboardClient | None = None

        self._resolved_mode, self._backend = self._resolve_backend()
        self._notify(f"Using {self._resolved_mode} execution mode.")

    @property
    def backend(
        self,
    ) -> ManagedPiastQBackend | DirectPiastQBackend | FakePiastQBackend:
        """Return the resolved backend handle."""

        return self._backend

    @property
    def execution_mode(self) -> ResolvedExecutionMode:
        """Return the resolved execution mode."""

        return self._resolved_mode

    @property
    def dashboard_client(self) -> DashboardClient | None:
        """Return the dashboard client when this client uses one."""

        return self._dashboard_client

    @property
    def owner(self) -> str | None:
        """Return the configured dashboard owner."""

        return self._owner

    def _resolve_backend(
        self,
    ) -> tuple[
        ResolvedExecutionMode,
        ManagedPiastQBackend | DirectPiastQBackend | FakePiastQBackend,
    ]:
        if self._requested_mode == "managed":
            dashboard_client = self._require_dashboard_client()
            dashboard_client.health()
            return "managed", ManagedPiastQBackend(
                mode="managed",
                owner=self,
                dashboard_client=dashboard_client,
            )

        if self._requested_mode == "direct":
            return "direct", self._direct_backend()

        if self._requested_mode == "fake":
            return "fake", self._fake_backend()

        return self._resolve_auto_backend()

    def _resolve_auto_backend(
        self,
    ) -> tuple[ResolvedExecutionMode, ManagedPiastQBackend | DirectPiastQBackend]:
        dashboard_error: DashboardUnavailableError | None = None
        if self._dashboard_api_url:
            dashboard_client = self._dashboard_client_or_create()
            try:
                dashboard_client.health()
            except DashboardAuthError:
                raise
            except DashboardUnavailableError as exc:
                dashboard_error = exc
            else:
                return "managed", ManagedPiastQBackend(
                    mode="managed",
                    owner=self,
                    dashboard_client=dashboard_client,
                )

        try:
            return "direct", self._direct_backend()
        except DirectModeUnavailableError as exc:
            if dashboard_error is not None:
                raise DirectModeUnavailableError(
                    "Managed dashboard is unavailable and direct mode requires "
                    "a PCSS token."
                ) from exc
            raise

    def _direct_backend(self) -> DirectPiastQBackend:
        if not self._token:
            raise DirectModeUnavailableError("Direct mode requires a PCSS token.")
        return DirectPiastQBackend(
            mode="direct",
            owner=self,
            token=self._token,
            registry_path=self._registry_path,
        )

    def _fake_backend(self) -> FakePiastQBackend:
        dashboard_client: DashboardClient | None = None
        noise_model = None
        if self._use_backend_noise:
            dashboard_client = self._require_dashboard_client()
            noise_model = dashboard_client.get_noise_model()

        return FakePiastQBackend(
            mode="fake",
            owner=self,
            use_backend_noise=self._use_backend_noise,
            dashboard_client=dashboard_client,
            noise_model=noise_model,
        )

    def _require_dashboard_client(self) -> DashboardClient:
        if not self._dashboard_api_url:
            raise PiastQConfigurationError(
                "Dashboard API URL is required for managed dashboard mode."
            )
        return self._dashboard_client_or_create()

    def _dashboard_client_or_create(self) -> DashboardClient:
        if self._dashboard_client is None:
            self._dashboard_client = DashboardClient(
                self._dashboard_api_url or "",
                api_key=self._dashboard_api_key,
                client=self._http_client,
                transport=self._http_transport,
                timeout=self._timeout,
            )
        return self._dashboard_client

    def _notify(self, message: str) -> None:
        if self._verbose:
            print(f"cft-piastq: {message}")


def _normalize_mode(value: ExecutionMode | str) -> ExecutionMode:
    normalized = value.strip().lower()
    if normalized not in _EXECUTION_MODES:
        raise PiastQConfigurationError(
            "Execution mode must be one of auto, managed, direct, or fake."
        )
    return cast(ExecutionMode, normalized)


def _optional_non_empty(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
