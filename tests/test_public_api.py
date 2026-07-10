from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def test_public_facades_import_without_optional_provider_modules() -> None:
    sys.modules.pop("cft_piastq", None)
    sys.modules.pop("pcss_qapi", None)
    sys.modules.pop("qiskit_aer", None)

    from cft_piastq import PiastQClient, PiastQJob, PiastQSampler

    assert PiastQClient.__name__ == "PiastQClient"
    assert PiastQSampler.__name__ == "PiastQSampler"
    assert PiastQJob.__name__ == "PiastQJob"
    assert "pcss_qapi" not in sys.modules
    assert "qiskit_aer" not in sys.modules


def test_sampler_requires_an_explicit_backend() -> None:
    from cft_piastq import PiastQSampler

    with pytest.raises(TypeError):
        PiastQSampler()


def test_public_facades_export_real_implementations() -> None:
    from cft_piastq import PiastQJob, PiastQSampler
    from cft_piastq.job import PiastQJob as PiastQJobImplementation
    from cft_piastq.sampler import PiastQSampler as PiastQSamplerImplementation

    assert PiastQSampler is PiastQSamplerImplementation
    assert PiastQJob is PiastQJobImplementation


def test_public_exception_hierarchy_is_available() -> None:
    from cft_piastq import (
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

    for exc_type in (
        PiastQConfigurationError,
        DashboardUnavailableError,
        DashboardAuthError,
        ManagedJobError,
        DirectModeUnavailableError,
        DirectProviderError,
        FakeBackendError,
        PiastQTimeoutError,
    ):
        assert issubclass(exc_type, PiastQError)


@pytest.mark.parametrize(
    ("raw_status", "normalized"),
    [
        ("DONE", "succeeded"),
        ("finished", "succeeded"),
        ("SUCCESS", "succeeded"),
        ("ERROR", "failed"),
        ("CANCELLED", "cancelled"),
        ("queued", "queued"),
        ("RUNNING", "running"),
        ("stale", "stale"),
        ("cancel_requested", "cancel_requested"),
        ("something-new", "unknown"),
        (None, "unknown"),
    ],
)
def test_normalize_job_status_maps_provider_values(
    raw_status: object, normalized: str
) -> None:
    from cft_piastq.status import normalize_job_status

    assert normalize_job_status(raw_status) == normalized


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("YES", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("No", False),
        ("off", False),
        (True, True),
        (False, False),
        (None, True),
    ],
)
def test_config_parse_bool_accepts_notebook_friendly_values(
    raw_value: object, expected: bool
) -> None:
    from cft_piastq.config import parse_bool

    assert parse_bool(raw_value, default=True) is expected


def test_config_parse_bool_rejects_ambiguous_values() -> None:
    from cft_piastq.config import parse_bool
    from cft_piastq.errors import PiastQConfigurationError

    with pytest.raises(PiastQConfigurationError, match="boolean"):
        parse_bool("sometimes")


def test_default_registry_path_uses_platform_cache_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = importlib.import_module("cft_piastq.config")
    monkeypatch.setattr(config, "user_cache_path", lambda app_name: tmp_path / app_name)

    assert config.default_registry_path() == tmp_path / "cft_piastq" / "jobs.sqlite3"


def test_read_environment_uses_expected_variables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from cft_piastq.config import read_environment

    registry_path = tmp_path / "registry.sqlite3"
    monkeypatch.setenv("PCSS_QAPI_TOKEN", "pcss-from-env")
    monkeypatch.setenv("CFT_PIASTQ_OWNER", "szymo")
    monkeypatch.setenv("CFT_PIASTQ_DASHBOARD_API_URL", "https://dashboard.example")
    monkeypatch.setenv("CFT_PIASTQ_DASHBOARD_API_KEY", "dashboard-from-env")
    monkeypatch.setenv("CFT_PIASTQ_MODE", "managed")
    monkeypatch.setenv("CFT_PIASTQ_VERBOSE", "false")
    monkeypatch.setenv("CFT_PIASTQ_REGISTRY_PATH", str(registry_path))

    config = read_environment()

    assert config.owner == "szymo"
    assert config.token == "pcss-from-env"
    assert config.dashboard_api_url == "https://dashboard.example"
    assert config.dashboard_api_key == "dashboard-from-env"
    assert config.mode == "managed"
    assert config.verbose is False
    assert config.registry_path == registry_path
