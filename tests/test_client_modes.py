from __future__ import annotations

import sys
from collections.abc import Iterator

import httpx
import pytest

from cft_piastq.backend import (
    DirectPiastQBackend,
    FakePiastQBackend,
    ManagedPiastQBackend,
)
from cft_piastq.errors import (
    DashboardAuthError,
    DirectModeUnavailableError,
)


BASE_URL = "https://dashboard.example"
ENV_KEYS = (
    "PCSS_TOKEN",
    "PCSS_QAPI_TOKEN",
    "CFT_PIASTQ_DASHBOARD_API_URL",
    "CFT_PIASTQ_DASHBOARD_API_KEY",
    "CFT_PIASTQ_MODE",
    "CFT_PIASTQ_VERBOSE",
    "CFT_PIASTQ_REGISTRY_PATH",
)


@pytest.fixture(autouse=True)
def clean_piastq_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


def health_transport(
    status_code: int = 200,
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.path == "/api/runner/health"
        if status_code == 200:
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(status_code, json={"detail": "dashboard unavailable"})

    return httpx.MockTransport(handler), requests


def test_managed_mode_does_not_require_local_pcss_token() -> None:
    sys.modules.pop("pcss_qapi", None)
    sys.modules.pop("qiskit_aqt_provider", None)
    transport, requests = health_transport()

    from cft_piastq import PiastQClient

    client = PiastQClient(
        mode="managed",
        dashboard_api_url=BASE_URL,
        dashboard_api_key="dashboard-key",
        http_transport=transport,
        verbose=False,
    )

    assert client.execution_mode == "managed"
    assert isinstance(client.backend, ManagedPiastQBackend)
    assert "pcss_qapi" not in sys.modules
    assert "qiskit_aqt_provider" not in sys.modules
    assert len(requests) == 1
    assert "authorization" not in requests[0].headers


def test_direct_mode_requires_token() -> None:
    from cft_piastq import PiastQClient

    with pytest.raises(DirectModeUnavailableError, match="PCSS token"):
        PiastQClient(mode="direct", verbose=False)


def test_auto_mode_chooses_managed_when_health_succeeds() -> None:
    transport, _requests = health_transport()

    from cft_piastq import PiastQClient

    client = PiastQClient(
        mode="auto",
        token="local-direct-token",
        dashboard_api_url=BASE_URL,
        http_transport=transport,
        verbose=False,
    )

    assert client.execution_mode == "managed"
    assert isinstance(client.backend, ManagedPiastQBackend)


def test_auto_mode_falls_back_to_direct_when_health_unavailable() -> None:
    transport, _requests = health_transport(503)

    from cft_piastq import PiastQClient

    client = PiastQClient(
        mode="auto",
        token="local-direct-token",
        dashboard_api_url=BASE_URL,
        http_transport=transport,
        verbose=False,
    )

    assert client.execution_mode == "direct"
    assert isinstance(client.backend, DirectPiastQBackend)


def test_auto_mode_without_token_does_not_fallback_to_direct() -> None:
    transport, _requests = health_transport(503)

    from cft_piastq import PiastQClient

    with pytest.raises(DirectModeUnavailableError, match="PCSS token"):
        PiastQClient(
            mode="auto",
            dashboard_api_url=BASE_URL,
            http_transport=transport,
            verbose=False,
        )


@pytest.mark.parametrize("status_code", [401, 403])
def test_auto_mode_raises_dashboard_auth_error(status_code: int) -> None:
    transport, _requests = health_transport(status_code)

    from cft_piastq import PiastQClient

    with pytest.raises(DashboardAuthError):
        PiastQClient(
            mode="auto",
            token="local-direct-token",
            dashboard_api_url=BASE_URL,
            http_transport=transport,
            verbose=False,
        )


def test_constructor_arguments_override_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CFT_PIASTQ_MODE", "direct")
    monkeypatch.setenv("PCSS_TOKEN", "env-direct-token")
    monkeypatch.setenv("CFT_PIASTQ_DASHBOARD_API_URL", "https://env-dashboard.example")
    monkeypatch.setenv("CFT_PIASTQ_DASHBOARD_API_KEY", "env-dashboard-key")

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "ctor-dashboard.example"
        assert request.headers["x-dashboard-api-key"] == "ctor-dashboard-key"
        return httpx.Response(200, json={"status": "ok"})

    from cft_piastq import PiastQClient

    client = PiastQClient(
        mode="managed",
        dashboard_api_url="https://ctor-dashboard.example",
        dashboard_api_key="ctor-dashboard-key",
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )

    assert client.execution_mode == "managed"
    assert isinstance(client.backend, ManagedPiastQBackend)
    assert len(requests) == 1


def test_fake_mode_returns_fake_backend_without_importing_aer() -> None:
    sys.modules.pop("qiskit_aer", None)

    from cft_piastq import PiastQClient

    client = PiastQClient(mode="fake", verbose=False)

    assert client.execution_mode == "fake"
    assert isinstance(client.backend, FakePiastQBackend)
    assert "qiskit_aer" not in sys.modules
