# cft-piastq Library Design

Date: 2026-06-26
Status: approved brainstorming design

## Goal

Build `cft-piastq` as a separate Python library and repository. The package is imported as `cft_piastq` and acts as a Qiskit-compatible wrapper around `pcss_qapi`, `pcss_qapi.aqt.provider`, and `qiskit_aqt_provider.primitives.AQTSampler`.

The first version focuses on job handling, direct and managed execution, dashboard integration, result recovery, fake Aer backend support, and clean future extension points for mitigation techniques. It does not replace Qiskit circuit or result APIs.

## Non-Goals

- Do not create a custom circuit representation.
- Do not create a custom result type that replaces Qiskit's `SamplerResult`.
- Do not implement dynamical decoupling, Pauli twirling, or readout mitigation in V1.
- Do not couple the library to the local filesystem or Python modules of `piastq-benchmark`.
- Do not send the PCSS token to the dashboard frontend.
- Do not send fake backend jobs to the dashboard Jobs list.

## System Boundary

`cft-piastq` is a standalone Python package. It talks to `piastq-benchmark` only through HTTP APIs.

The library supports four execution modes:

- `auto`: default mode. `PiastQClient` runs a dashboard runner healthcheck during initialization. If the managed runner is available, execution uses the server. If the runner is unavailable, the client falls back to direct PCSS mode only when a local PCSS token was provided. A `401` or `403` response from the server is treated as a hard failure and does not fall back.
- `managed`: notebook sends QPY-serialized circuits to the dashboard runner. The server owns execution and result persistence.
- `direct`: notebook authenticates to PCSS locally and runs through `pcss_qapi` / `AQTSampler`. Dashboard events are best-effort and never block a direct quantum job.
- `fake`: user asks the client for a local Aer backend. Fake jobs stay local and are not sent to the dashboard.

## Public API

Typical managed or auto usage:

```python
from cft_piastq import PiastQClient, PiastQSampler

client = PiastQClient(
    owner="szymo",
    token=pcss_token,
    dashboard_api_url="https://piastq-dashboard.example",
    dashboard_api_key="dashboard-key",
)

backend = client.backend
sampler = PiastQSampler(
    backend,
    options={
        "with_progress_bar": False,
        "cft_job_name": "Bell smoke test",
        "cft_description": "2Q Bell test before RB run",
    },
)

job = sampler.run(circuits=[qc], shots=200)
result = job.result()
dist = result.quasi_dists[0]
counts = job.counts()
first_counts = counts[0]
```

The job metadata can also be set in the Qiskit-like options style before `run`:

```python
sampler = PiastQSampler(backend)
sampler.options.cft_job_name = "Bell smoke test"
sampler.options.cft_description = "2Q Bell test before RB run"

job = sampler.run(circuits=[qc], shots=200)
```

Fake backend usage:

```python
backend = client.fake_backend(use_backend_noise=False)
sampler = PiastQSampler(backend)
job = sampler.run(circuits=[qc], shots=200)
```

Noise-backed fake usage:

```python
backend = client.fake_backend(use_backend_noise=True)
sampler = PiastQSampler(backend)
job = sampler.run(circuits=[qc], shots=200)
```

## Main Components

### `PiastQClient`

Responsibilities:

- Store owner identity, dashboard URL, dashboard API key, local PCSS token, verbosity, and selected execution mode.
- In `auto`, perform a simple healthcheck at initialization.
- Print a short notebook-friendly message by default:
  - `cft-piastq: using managed runner at https://...`
  - `cft-piastq: managed runner unavailable, using direct PCSS mode`
- Expose `execution_mode`.
- Expose `backend`.
- Provide `fake_backend(use_backend_noise=False)`.
- Own a local SQLite registry for direct-mode audit/cache only.

Rules:

- In managed mode, a local PCSS token is not required because the server owns the PCSS credential.
- In direct mode, a local PCSS token is required.
- In auto mode, a local token is required only if managed runner is unavailable.
- If the dashboard returns `401` or `403`, the client raises an auth/permission error and does not fall back.

### `PiastQSampler`

Responsibilities:

- Preserve `AQTSampler.run(...)` calling style.
- Accept options in the constructor and expose mutable `sampler.options`.
- Split CFT-specific options from provider options.
- Never pass `cft_*` options to the real `AQTSampler`.
- Return a `PiastQJob`.

CFT options:

- `cft_job_name`: user-visible job name.
- `cft_description`: user-visible job description.

Name fallback order:

1. `sampler.options.cft_job_name`
2. `options["cft_job_name"]`
3. `circuit.name` when one circuit has a non-empty name
4. `"Untitled job"`

### `PiastQJob`

Responsibilities:

- Wrap the underlying direct provider job or managed server job.
- Expose `job_id()`.
- Expose `status()`.
- Expose `result(timeout=None, poll_interval=5)`.
- Expose `cancel()`.
- Expose `counts(num_bits=2)`.

Rules:

- `result()` returns a Qiskit/AQT-compatible `SamplerResult`.
- `result()` waits without a timeout by default. It stops when the job is succeeded, failed, or cancelled.
- Managed `status()` calls the server every time and does not cache status.
- `counts()` always returns a list of dictionaries, one per logical input circuit. For a single circuit, callers use `job.counts()[0]`.
- `counts()` is computed from `quasi_dists * shots`, so it is an estimated count view, not guaranteed raw provider counts.
- `cancel()` tries to cancel through the server or raw provider job when supported. If provider cancellation is unsupported, the job records a clear unsupported/cancel-requested state rather than pretending success.

## Logical Job Model

One `sampler.run(...)` call maps to one logical job.

For example:

```python
job = sampler.run(circuits=[qc1, qc2, qc3, qc4, qc5], shots=1000)
```

This is one logical job with:

- `circuit_count = 5`
- `requested_shots_per_circuit = 1000`
- `max_shots_per_provider_job = 200`
- `total_child_jobs = 25`

The library/server may split the request into child provider jobs. The main user-facing `job.result()` returns one aggregated `SamplerResult` with one `quasi_dist` per input circuit.

## Managed Mode Data Flow

1. User creates `PiastQClient` in `auto` or `managed`.
2. Client healthcheck confirms runner availability.
3. User creates `PiastQSampler(client.backend)`.
4. User calls `sampler.run(circuits=[...], shots=N)`.
5. Library serializes circuits to QPY and base64-encodes the payload.
6. Library posts the logical job request to `POST /api/runner/jobs`.
7. Server returns a `server_job_id`.
8. `PiastQJob.status()` calls `GET /api/runner/jobs/{server_job_id}`.
9. `PiastQJob.result()` polls status, then calls `GET /api/runner/jobs/{server_job_id}/result`.
10. Library reconstructs a `SamplerResult` from the JSON payload.

## Direct Mode Data Flow

1. User creates `PiastQClient` with local PCSS token or falls back to direct mode.
2. Client logs in through `AuthorizationService.login(token)`.
3. Client obtains the PCSS direct access backend from `PCSS_AQTProvider().get_direct_access_backend()`.
4. `PiastQSampler` delegates to `AQTSampler`.
5. Direct dashboard events are sent best-effort:
   - submitted
   - status update
   - result ready
   - failed
   - cancelled
6. Event upload errors are stored locally and do not fail the quantum job.

Direct mode does not guarantee recovery after notebook/process shutdown.

## Fake Backend

`client.fake_backend(use_backend_noise=False)` returns a local Aer backend without noise by default.

When `use_backend_noise=True`:

1. Client calls `GET /api/noise-model/latest`.
2. The dashboard returns a Qiskit Aer `NoiseModel` JSON payload.
3. The library rebuilds the Aer noise model locally.
4. The fake backend uses the noise model.

If `use_backend_noise=True` and the API or noise model is unavailable, the library raises a clear error. Fake jobs are local and are not sent to the dashboard Jobs list.

## Shared HTTP Contract

The library expects the dashboard to provide these endpoints:

```text
GET  /api/runner/health
POST /api/runner/jobs
GET  /api/runner/jobs/{server_job_id}
GET  /api/runner/jobs/{server_job_id}/result
POST /api/runner/jobs/{server_job_id}/cancel
GET  /api/jobs
GET  /api/benchmark-snapshot/latest
GET  /api/noise-model/latest
```

Healthcheck response shape:

```json
{
  "runner_available": true,
  "managed_mode_enabled": true,
  "max_shots_per_provider_job": 200
}
```

Submit request includes:

- `owner`
- `cft_job_name`
- `cft_description`
- `shots`
- QPY circuits as base64
- circuit metadata
- client/library version

Submit response includes:

- `server_job_id`
- `status`
- `created_at`
- `total_child_jobs`

Status response includes:

```json
{
  "server_job_id": "srv_abc123",
  "status": "running",
  "completed_child_jobs": 3,
  "total_child_jobs": 25,
  "provider_status": "RUNNING",
  "owner": "szymo",
  "name": "GHZ sweep"
}
```

Result response includes enough JSON data to reconstruct a Qiskit/AQT-compatible `SamplerResult`:

- `quasi_dists`
- `metadata`
- logical circuit count
- aggregated result metadata
- child job references

## Error Handling

- Managed unavailable in `auto`: fall back to direct only if local token exists.
- Managed `401` or `403`: raise and do not fall back.
- Managed submit failure: raise with sanitized server message.
- Managed result failure: raise with job status and sanitized failure detail.
- Direct dashboard event failure: record locally and continue.
- Direct PCSS provider failure: propagate as a normal job/provider error with token-safe messaging.
- Fake noise model fetch failure: raise if `use_backend_noise=True`.

## Security

- PCSS token is never sent to the dashboard frontend.
- In managed mode, local PCSS token is not sent to the dashboard API.
- Dashboard API key is sent only to protected dashboard endpoints.
- CFT metadata is treated as user-provided display text and must be escaped by dashboard consumers.
- QPY payloads are sent only to the trusted dashboard runner endpoint.

## Testing Strategy

- `PiastQClient(mode="auto")` chooses managed when healthcheck succeeds.
- `auto` falls back to direct only when runner is unavailable.
- `auto` does not fall back on `401` or `403`.
- `PiastQSampler` does not pass `cft_*` options to `AQTSampler`.
- QPY serialization/deserialization round-trip preserves representative `QuantumCircuit` objects.
- Managed `job.status()` calls the server every time.
- Managed `job.result()` polls until completion and reconstructs `SamplerResult`.
- `job.counts()` always returns a list.
- Shot splitting aggregates child results into one logical result.
- Multi-circuit jobs return one logical job and one `quasi_dist` per circuit.
- Fake backend works without noise by default.
- Fake backend with `use_backend_noise=True` fetches `NoiseModel` JSON.
- Fake jobs do not send dashboard events.

## Risks

- PCSS/AQT direct access may not expose stable child provider job IDs for every execution path. The implementation must verify what is available from `AQTSampler` and provider internals.
- Direct mode cannot reliably recover jobs after notebook shutdown if the provider lacks restore support.
- Aggregating `quasi_dists` across shot-split child jobs must preserve per-circuit ordering.
- Reconstructing `SamplerResult` from JSON must be tested across the installed Qiskit version used by the project.
- Aer noise model generation is owned by the dashboard; if the dashboard model is scientifically weak, the fake backend can give misleading confidence.
