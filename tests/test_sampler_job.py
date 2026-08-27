from __future__ import annotations

import json

import httpx
import pytest
from qiskit import QuantumCircuit
from qiskit.primitives import SamplerResult

from cft_piastq import PiastQClient, PiastQJob, PiastQSampler, __version__
from cft_piastq.serialization import qpy_base64_to_circuits

BASE_URL = "https://dashboard.example"


def bell_circuit() -> QuantumCircuit:
    circuit = QuantumCircuit(2, 2, name="bell")
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    return circuit


def test_managed_sampler_run_posts_qpy_job_and_returns_piastq_job() -> None:
    submitted_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/runner/health":
            return httpx.Response(
                200,
                json={"runner_available": True, "managed_mode_enabled": True},
            )

        if request.method == "POST" and request.url.path == "/api/runner/jobs":
            payload = json.loads(request.content)
            submitted_payloads.append(payload)
            restored = qpy_base64_to_circuits(payload["circuits"][0]["qpy_base64"])

            assert "program" not in payload
            assert "options" not in payload
            assert payload["owner"] == "szymo"
            assert len(restored) == 1
            assert restored[0].name == "bell"
            assert set(payload["circuits"][0]) == {"qpy_base64"}
            assert payload["shots"] == 200
            assert payload["cft_job_name"] == "Bell smoke test"
            assert payload["cft_description"] == "2Q Bell test before RB run"
            assert payload["client_version"] == __version__
            return httpx.Response(
                201,
                json={"server_job_id": "server-job-1", "status": "queued"},
            )

        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    client = PiastQClient(
        owner="szymo",
        mode="managed",
        dashboard_api_url=BASE_URL,
        dashboard_api_key="dashboard-key",
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )
    sampler = PiastQSampler(
        client.backend,
        options={
            "with_progress_bar": False,
            "cft_job_name": "Bell smoke test",
            "cft_description": "2Q Bell test before RB run",
        },
    )

    job = sampler.run(circuits=[bell_circuit()], shots=200)

    assert isinstance(job, PiastQJob)
    assert job.job_id() == "server-job-1"
    assert len(submitted_payloads) == 1


def test_sampler_options_split_cft_keys_from_provider_options() -> None:
    submitted_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/runner/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/runner/jobs":
            payload = json.loads(request.content)
            submitted_payloads.append(payload)
            return httpx.Response(201, json={"id": "server-job-2"})
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    client = PiastQClient(
        owner="szymo",
        mode="managed",
        dashboard_api_url=BASE_URL,
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )
    sampler = PiastQSampler(
        client.backend,
        options={"cft_job_name": "Constructor name", "with_progress_bar": True},
    )
    sampler.options.cft_job_name = "Mutated name"
    sampler.options["provider_seed"] = 123

    sampler.run(
        circuits=bell_circuit(),
        shots=10,
        cft_description="Run description",
        cft_priority="not provider data",
    )

    assert sampler.options["cft_job_name"] == "Mutated name"
    assert submitted_payloads[0]["owner"] == "szymo"
    assert submitted_payloads[0]["cft_job_name"] == "Mutated name"
    assert submitted_payloads[0]["cft_description"] == "Run description"
    assert "cft_priority" not in submitted_payloads[0]
    assert "options" not in submitted_payloads[0]


def test_managed_job_reads_fresh_status_result_counts_and_cancel() -> None:
    status_payloads = [
        {"server_job_id": "server-job-3", "status": "queued"},
        {"server_job_id": "server-job-3", "status": "running"},
        {"server_job_id": "server-job-3", "status": "succeeded"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/runner/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.method == "POST" and request.url.path == "/api/runner/jobs":
            return httpx.Response(201, json={"server_job_id": "server-job-3"})
        if (
            request.method == "GET"
            and request.url.path == "/api/runner/jobs/server-job-3"
        ):
            return httpx.Response(200, json=status_payloads.pop(0))
        if (
            request.method == "GET"
            and request.url.path == "/api/runner/jobs/server-job-3/result"
        ):
            return httpx.Response(
                200,
                json={
                    "shots": 200,
                    "quasi_dists": [{"0": 0.5, "3": 0.5}],
                    "metadata": [{"circuit_name": "bell"}],
                },
            )
        if (
            request.method == "POST"
            and request.url.path == "/api/runner/jobs/server-job-3/cancel"
        ):
            return httpx.Response(
                200,
                json={"server_job_id": "server-job-3", "status": "cancelled"},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    client = PiastQClient(
        owner="szymo",
        mode="managed",
        dashboard_api_url=BASE_URL,
        dashboard_api_key="dashboard-key",
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )
    job = PiastQSampler(client.backend).run(circuits=[bell_circuit()], shots=200)

    assert job.status() == "queued"
    result = job.result(timeout=1, poll_interval=0.001)

    assert isinstance(result, SamplerResult)
    assert result.metadata[0]["shots"] == 200
    assert job.counts(num_bits=2) == [{"00": 100, "11": 100}]
    assert job.cancel() == "cancelled"


def test_managed_sampler_requires_owner_before_submit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/runner/health":
            return httpx.Response(200, json={"status": "ok"})
        raise AssertionError("submit should fail before sending a dashboard request")

    client = PiastQClient(
        mode="managed",
        dashboard_api_url=BASE_URL,
        http_transport=httpx.MockTransport(handler),
        verbose=False,
    )

    from cft_piastq import PiastQConfigurationError

    with pytest.raises(PiastQConfigurationError, match="owner"):
        PiastQSampler(client.backend).run(circuits=bell_circuit(), shots=10)
