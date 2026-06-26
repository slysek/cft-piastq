"""HTTP client for PiastQ managed dashboard endpoints."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from .errors import (
    DashboardAuthError,
    DashboardUnavailableError,
    FakeBackendError,
    ManagedJobError,
    PiastQConfigurationError,
    PiastQError,
)
from .security import redact_secrets, safe_error_message
from .types import JSONDict

DEFAULT_TIMEOUT_SECONDS = 10.0


class DashboardClient:
    """Small HTTP wrapper for the managed dashboard API."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> None:
        normalized_base_url = base_url.rstrip("/")
        if not normalized_base_url:
            raise PiastQConfigurationError("Dashboard API URL is required.")
        if client is not None and transport is not None:
            raise PiastQConfigurationError(
                "Pass either an httpx client or a transport, not both."
            )

        self.base_url = normalized_base_url
        self.api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
            transport=transport,
        )

    def close(self) -> None:
        """Close the owned HTTP client."""

        if self._owns_client:
            self._client.close()

    def health(self) -> JSONDict:
        """Return managed runner health information."""

        return self._request(
            "GET",
            "/api/runner/health",
            error_type=DashboardUnavailableError,
        )

    def submit_job(self, payload: JSONDict) -> JSONDict:
        """Submit a job to the managed runner."""

        return self._request(
            "POST",
            "/api/runner/jobs",
            json=payload,
            error_type=ManagedJobError,
        )

    def get_job(self, server_job_id: str) -> JSONDict:
        """Read fresh managed job status."""

        return self._request(
            "GET",
            f"/api/runner/jobs/{_path_token(server_job_id)}",
            error_type=ManagedJobError,
        )

    def get_result(self, server_job_id: str) -> JSONDict:
        """Fetch a completed managed job result."""

        return self._request(
            "GET",
            f"/api/runner/jobs/{_path_token(server_job_id)}/result",
            error_type=ManagedJobError,
        )

    def cancel_job(self, server_job_id: str) -> JSONDict:
        """Request managed job cancellation."""

        return self._request(
            "POST",
            f"/api/runner/jobs/{_path_token(server_job_id)}/cancel",
            error_type=ManagedJobError,
            require_api_key=True,
        )

    def get_noise_model(self) -> JSONDict:
        """Fetch the dashboard-provided fake-backend noise model."""

        return self._request(
            "GET",
            "/api/noise-model/latest",
            error_type=FakeBackendError,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: JSONDict | None = None,
        error_type: type[PiastQError],
        require_api_key: bool = False,
    ) -> JSONDict:
        headers = self._headers(require_api_key=require_api_key)
        try:
            response = self._client.request(
                method,
                self._url(path),
                json=json,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise DashboardUnavailableError(safe_error_message(exc)) from exc

        if response.status_code in (401, 403):
            raise DashboardAuthError(self._response_error_message(response))
        if response.status_code >= 400:
            raise error_type(self._response_error_message(response))

        return self._response_json(response, error_type=error_type)

    def _headers(self, *, require_api_key: bool = False) -> Mapping[str, str]:
        if require_api_key and not self.api_key:
            raise PiastQConfigurationError(
                "A dashboard API key is required for this dashboard operation."
            )
        if not self.api_key:
            return {}
        return {"X-Dashboard-Api-Key": self.api_key}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _response_json(
        self,
        response: httpx.Response,
        *,
        error_type: type[PiastQError],
    ) -> JSONDict:
        if not response.content:
            return {}

        try:
            data = response.json()
        except ValueError as exc:
            message = self._response_error_message(response)
            raise error_type(message) from exc

        if not isinstance(data, dict):
            raise error_type(
                f"Dashboard returned a non-object JSON response from "
                f"{response.request.url.path}."
            )
        return data

    def _response_error_message(self, response: httpx.Response) -> str:
        detail: Any | None = None
        if response.content:
            try:
                data = response.json()
            except ValueError:
                detail = response.text
            else:
                if isinstance(data, dict):
                    detail = (
                        data.get("detail")
                        or data.get("error")
                        or data.get("message")
                        or data
                    )
                else:
                    detail = data

        if detail is None:
            detail = response.reason_phrase or f"HTTP {response.status_code}"

        return redact_secrets(f"Dashboard request failed: {detail}")


def _path_token(value: str) -> str:
    return quote(value, safe="")
