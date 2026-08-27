"""Lazy direct PCSS/AQT adapter."""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

from .direct_composite import DirectCompositeJob
from .errors import DirectModeUnavailableError, DirectProviderError
from .security import safe_error_message


class _DirectDependencies(NamedTuple):
    AuthorizationService: Any
    PCSS_AQTProvider: Any
    AQTSampler: Any


@dataclass
class DirectPcssAdapter:
    """Adapter that logs in to PCSS and builds the AQT sampler lazily."""

    token: str = field(repr=False)
    registry_path: str | Path | None = None
    owner: object = "unknown"
    dashboard_client: Any | None = None
    _dependencies: _DirectDependencies | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _logged_in: bool = field(default=False, init=False, repr=False)
    _direct_backend: Any | None = field(default=None, init=False, repr=False)
    _sampler: Any | None = field(default=None, init=False, repr=False)
    _registry: Any | None = field(default=None, init=False, repr=False)
    _event_reporter: Any | None = field(default=None, init=False, repr=False)

    def run(
        self,
        circuits: Sequence[Any],
        *,
        parameter_values: object | None = None,
        shots: int | None = None,
        provider_options: Mapping[str, Any] | None = None,
    ) -> Any:
        """Create one lazy logical job backed by partitioned AQT jobs."""

        if shots is None:
            raise DirectProviderError("Direct shots must be a positive integer.")

        try:
            options = dict(provider_options or {})
        except Exception:
            raise DirectProviderError(
                "Unable to snapshot direct job inputs."
            ) from None
        show_progress = options.pop("with_progress_bar", True)
        if not isinstance(show_progress, bool):
            raise DirectProviderError(
                "Direct provider option with_progress_bar must be a boolean."
            )

        try:
            circuit_snapshot, parameter_snapshot, option_snapshot = deepcopy(
                (list(circuits), parameter_values, options)
            )
        except Exception:
            raise DirectProviderError(
                "Unable to snapshot direct job inputs."
            ) from None

        sampler = self._sampler_or_create()
        return DirectCompositeJob(
            sampler=sampler,
            circuits=circuit_snapshot,
            parameter_values=parameter_snapshot,
            total_shots=shots,
            provider_options=option_snapshot,
            show_progress=show_progress,
            error_formatter=self._safe_provider_error,
        )

    @property
    def registry(self) -> Any | None:
        """Return the local direct-job registry, creating it lazily."""

        if self.registry_path is None:
            return None
        if self._registry is None:
            from .registry import DirectJobRegistry

            self._registry = DirectJobRegistry(self.registry_path)
        return self._registry

    @property
    def event_reporter(self) -> Any | None:
        """Return the direct-event reporter, creating it lazily."""

        registry = self.registry
        if registry is None:
            return None
        if self._event_reporter is None:
            from .registry import DashboardEventReporter

            self._event_reporter = DashboardEventReporter(
                registry=registry,
                dashboard_client=self.dashboard_client,
            )
        return self._event_reporter

    def _sampler_or_create(self) -> Any:
        self._login_if_needed()
        dependencies = self._load_dependencies()

        if self._direct_backend is None:
            try:
                provider = dependencies.PCSS_AQTProvider()
                self._direct_backend = provider.get_direct_access_backend()
            except Exception as exc:  # pragma: no cover - provider-specific
                raise DirectProviderError(
                    "Unable to create PCSS direct access backend: "
                    f"{self._safe_provider_error(exc)}"
                ) from None

        if self._sampler is None:
            try:
                self._sampler = dependencies.AQTSampler(self._direct_backend)
            except Exception as exc:  # pragma: no cover - provider-specific
                raise DirectProviderError(
                    f"Unable to create AQT sampler: {self._safe_provider_error(exc)}"
                ) from None

        return self._sampler

    def _login_if_needed(self) -> None:
        if self._logged_in:
            return

        dependencies = self._load_dependencies()
        try:
            dependencies.AuthorizationService.login(self.token)
        except Exception as exc:  # pragma: no cover - provider-specific
            raise DirectProviderError(
                "Unable to authenticate PCSS direct mode: "
                f"{self._safe_provider_error(exc)}"
            ) from None
        self._logged_in = True

    def _safe_provider_error(self, exc: BaseException) -> str:
        return safe_error_message(exc, secret_values=(self.token,))

    def _load_dependencies(self) -> _DirectDependencies:
        if self._dependencies is not None:
            return self._dependencies

        missing_packages: set[str] = set()
        modules: dict[str, Any] = {}
        for module_name, package_name in (
            ("pcss_qapi", "pcss-qapi"),
            ("pcss_qapi.aqt.provider", "pcss-qapi"),
            ("qiskit_aqt_provider.primitives", "qiskit-aqt-provider"),
        ):
            try:
                modules[module_name] = importlib.import_module(module_name)
            except ImportError:
                missing_packages.add(package_name)

        if missing_packages:
            packages = ", ".join(sorted(missing_packages))
            raise DirectModeUnavailableError(
                "Direct PCSS/AQT mode requires optional packages: "
                f"{packages}. Install cft-piastq[direct] to use direct mode."
            )

        self._dependencies = _DirectDependencies(
            AuthorizationService=modules["pcss_qapi"].AuthorizationService,
            PCSS_AQTProvider=modules["pcss_qapi.aqt.provider"].PCSS_AQTProvider,
            AQTSampler=modules["qiskit_aqt_provider.primitives"].AQTSampler,
        )
        return self._dependencies
