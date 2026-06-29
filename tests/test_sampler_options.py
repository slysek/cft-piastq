from __future__ import annotations

import json

import pytest
from qiskit import QuantumCircuit

import cft_piastq.client as client_module
from cft_piastq.backend import ManagedPiastQBackend
from cft_piastq.options import PiastQSamplerOptions, split_cft_options
from cft_piastq.sampler import PiastQSampler


class RecordingDashboardClient:
    def __init__(self) -> None:
        self.submitted_payloads: list[dict[str, object]] = []

    def health(self) -> dict[str, object]:
        return {"status": "ok"}

    def submit_job(self, payload: dict[str, object]) -> dict[str, object]:
        self.submitted_payloads.append(payload)
        return {"server_job_id": "srv-managed-1", "status": "queued"}


def bell_circuit() -> QuantumCircuit:
    circuit = QuantumCircuit(2, 2, name="bell")
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    return circuit


def test_sampler_options_support_attribute_and_dict_style_access() -> None:
    options = PiastQSamplerOptions({"shots": 100, "cft_job_name": "Constructor name"})

    options.cft_description = "Mutable description"
    options["optimization_level"] = 1

    assert options.cft_job_name == "Constructor name"
    assert options["cft_description"] == "Mutable description"
    assert options["optimization_level"] == 1
    assert options.as_dict() == {
        "shots": 100,
        "cft_job_name": "Constructor name",
        "cft_description": "Mutable description",
        "optimization_level": 1,
    }


def test_split_cft_options_returns_new_dicts_without_mutating_caller() -> None:
    raw_options = {
        "cft_job_name": "Bell job",
        "cft_description": "Bell description",
        "cft_internal_note": "dashboard only",
        "with_progress_bar": False,
    }

    cft_options, provider_options = split_cft_options(raw_options)

    assert cft_options == {
        "cft_job_name": "Bell job",
        "cft_description": "Bell description",
        "cft_internal_note": "dashboard only",
    }
    assert provider_options == {"with_progress_bar": False}
    assert raw_options == {
        "cft_job_name": "Bell job",
        "cft_description": "Bell description",
        "cft_internal_note": "dashboard only",
        "with_progress_bar": False,
    }


def test_managed_sampler_submits_qpy_payload_without_provider_options() -> None:
    dashboard_client = RecordingDashboardClient()
    backend = ManagedPiastQBackend(
        mode="managed",
        owner="szymo",
        dashboard_client=dashboard_client,  # type: ignore[arg-type]
    )
    sampler = PiastQSampler(
        backend,
        options={"with_progress_bar": False, "cft_job_name": "Constructor name"},
    )
    sampler.options.cft_description = "Mutable description"

    job = sampler.run(
        circuits=[bell_circuit()],
        shots=200,
        cft_job_name="Run name",
        optimization_level=1,
    )

    payload = dashboard_client.submitted_payloads[0]
    assert job.job_id() == "srv-managed-1"
    assert payload["owner"] == "szymo"
    assert payload["cft_job_name"] == "Constructor name"
    assert payload["cft_description"] == "Mutable description"
    assert payload["shots"] == 200
    assert payload["client_version"] == "0.1.0"
    assert "provider_options" not in payload
    assert payload["circuits"][0]["metadata"]["circuit_name"] == "bell"  # type: ignore[index]


def test_managed_sampler_uses_run_job_name_when_sampler_name_absent() -> None:
    dashboard_client = RecordingDashboardClient()
    backend = ManagedPiastQBackend(
        mode="managed",
        owner="szymo",
        dashboard_client=dashboard_client,  # type: ignore[arg-type]
    )
    sampler = PiastQSampler(backend)

    sampler.run(circuits=[bell_circuit()], shots=200, cft_job_name="Run name")

    payload = dashboard_client.submitted_payloads[0]
    assert payload["cft_job_name"] == "Run name"


def test_managed_sampler_uses_single_circuit_name_when_job_names_absent() -> None:
    dashboard_client = RecordingDashboardClient()
    backend = ManagedPiastQBackend(
        mode="managed",
        owner="szymo",
        dashboard_client=dashboard_client,  # type: ignore[arg-type]
    )
    sampler = PiastQSampler(backend)

    sampler.run(circuits=[bell_circuit()], shots=200)

    payload = dashboard_client.submitted_payloads[0]
    assert payload["cft_job_name"] == "bell"


def test_managed_sampler_uses_untitled_job_name_for_multiple_circuits() -> None:
    dashboard_client = RecordingDashboardClient()
    backend = ManagedPiastQBackend(
        mode="managed",
        owner="szymo",
        dashboard_client=dashboard_client,  # type: ignore[arg-type]
    )
    sampler = PiastQSampler(backend)

    sampler.run(circuits=[bell_circuit(), bell_circuit()], shots=200)

    payload = dashboard_client.submitted_payloads[0]
    assert payload["cft_job_name"] == "Untitled job"


def test_managed_sampler_uses_untitled_job_name_for_blank_circuit_name() -> None:
    dashboard_client = RecordingDashboardClient()
    backend = ManagedPiastQBackend(
        mode="managed",
        owner="szymo",
        dashboard_client=dashboard_client,  # type: ignore[arg-type]
    )
    sampler = PiastQSampler(backend)
    circuit = bell_circuit()
    circuit.name = ""

    sampler.run(circuits=[circuit], shots=200)

    payload = dashboard_client.submitted_payloads[0]
    assert payload["cft_job_name"] == "Untitled job"


def test_managed_sampler_uses_mutable_option_job_name_when_run_name_absent() -> None:
    dashboard_client = RecordingDashboardClient()
    backend = ManagedPiastQBackend(
        mode="managed",
        owner="szymo",
        dashboard_client=dashboard_client,  # type: ignore[arg-type]
    )
    sampler = PiastQSampler(backend)
    sampler.options.cft_job_name = "Mutable name"

    sampler.run(circuits=[bell_circuit()], shots=200)

    payload = dashboard_client.submitted_payloads[0]
    assert payload["cft_job_name"] == "Mutable name"


def test_managed_sampler_never_serializes_provider_or_secret_options() -> None:
    dashboard_client = RecordingDashboardClient()
    pcss_token_key = "PCSS_" + "TOKEN"
    run_token_key = "to" + "ken"
    dashboard_key = "CFT_PIASTQ_DASHBOARD_" + "API_KEY"
    backend = ManagedPiastQBackend(
        mode="managed",
        owner="szymo",
        dashboard_client=dashboard_client,  # type: ignore[arg-type]
    )
    sampler = PiastQSampler(
        backend,
        options={
            pcss_token_key: "pcss-placeholder",
            "authorization": "Bearer local-secret",
            "provider_config": {"opaque": "provider-secret"},
        },
    )
    run_options = {
        run_token_key: "run-token-placeholder",
        dashboard_key: "dashboard-placeholder",
        "arbitrary_provider_config": "must-not-serialize",
    }

    sampler.run(
        circuits=[bell_circuit()],
        shots=200,
        **run_options,
    )

    payload = dashboard_client.submitted_payloads[0]
    serialized_payload = json.dumps(payload, sort_keys=True)
    assert "provider_options" not in payload
    for forbidden in (
        pcss_token_key,
        "pcss-placeholder",
        "authorization",
        "local-secret",
        "provider_config",
        "provider-secret",
        run_token_key,
        "run-token-placeholder",
        dashboard_key,
        "dashboard-placeholder",
        "arbitrary_provider_config",
        "must-not-serialize",
    ):
        assert forbidden not in serialized_payload


def test_managed_sampler_submits_payload_from_client_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dashboard_client = RecordingDashboardClient()
    monkeypatch.setattr(
        client_module,
        "DashboardClient",
        lambda *_args, **_kwargs: dashboard_client,
    )
    client = client_module.PiastQClient(
        mode="managed",
        owner="szymo",
        dashboard_api_url="https://dashboard.example",
        verbose=False,
    )
    sampler = PiastQSampler(client.backend)

    job = sampler.run(circuits=[bell_circuit()], shots=200)

    payload = dashboard_client.submitted_payloads[0]
    assert job.job_id() == "srv-managed-1"
    assert payload["owner"] == "szymo"
    assert payload["shots"] == 200
    assert payload["circuits"][0]["metadata"]["circuit_name"] == "bell"  # type: ignore[index]
