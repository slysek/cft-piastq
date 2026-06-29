"""Backend handle objects returned by :class:`PiastQClient`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .http import DashboardClient
from .types import JSONDict


@dataclass(frozen=True)
class ManagedPiastQBackend:
    """Handle for managed dashboard execution."""

    mode: Literal["managed"]
    owner: object
    dashboard_client: DashboardClient


@dataclass(frozen=True)
class DirectPiastQBackend:
    """Handle for direct PCSS/AQT execution."""

    mode: Literal["direct"]
    owner: object
    token: str = field(repr=False)
    registry_path: Path
    provider: object | None = None


@dataclass(frozen=True)
class FakePiastQBackend:
    """Handle for local fake backend execution."""

    mode: Literal["fake"]
    owner: object
    use_backend_noise: bool = False
    dashboard_client: DashboardClient | None = None
    noise_model: object | None = None
