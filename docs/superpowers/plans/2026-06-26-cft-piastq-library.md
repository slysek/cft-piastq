# cft-piastq Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `cft-piastq` as a standalone Python package imported as `cft_piastq`, with Qiskit-compatible managed, direct, and fake execution paths for PiastQ/AQT workflows.

**Architecture:** Use a small `src/cft_piastq/` package with stable public facades (`PiastQClient`, `PiastQSampler`, `PiastQJob`) and focused internal adapters for dashboard HTTP, QPY serialization, direct PCSS/AQT execution, fake Aer execution, local SQLite registry, result reconstruction, and count estimation. Keep PCSS and Aer dependencies lazy so managed-mode imports work in notebooks without local PCSS credentials or optional simulator packages.

**Tech Stack:** Python 3.10+, Qiskit primitives and QPY, optional `pcss_qapi`, optional `qiskit_aqt_provider`, optional `qiskit-aer`, `httpx`, `platformdirs`, SQLite via `sqlite3`, pytest, Ruff, mypy.

---

## Source Inputs

- Approved design: `2026-06-26-cft-piastq-library-design.md`
- Dashboard counterpart plan: `2026-06-26-piastq-benchmark-managed-runner-jobs.md`
- Current workspace state: this folder currently contains planning files only and is not a Git repository.

## Skill Review and Assignment

Use these skills during implementation:

- `superpowers:using-superpowers`: requested explicitly; use before task execution.
- `superpowers:using-git-worktrees`: use after the repository is initialized and before parallel implementation.
- `superpowers:subagent-driven-development`: preferred execution mode for this plan.
- `superpowers:executing-plans`: use if implementing inline in one session.
- `superpowers:test-driven-development`: use inside every implementation wave.
- `superpowers:verification-before-completion`: use before any task or wave is reported complete.
- `python-patterns`: use for package structure, lazy optional imports, dataclasses, protocols, and module boundaries.
- `python-testing`: use for pytest fixtures, monkeypatching provider adapters, and deterministic fake jobs.
- `api-design`: use for dashboard runner HTTP contracts and status/error mapping.
- `error-handling`: use for managed fallback rules, provider failures, timeout behavior, and result polling.
- `security-review`: use for token isolation, sanitized errors, QPY payload handling, and no-secret tests.
- `documentation-lookup`: use only if Qiskit/AQT API signatures differ from assumptions in the installed versions.

## Parallelization Rule

Parallel implementation should happen in separate worktrees after Wave 0 creates the package skeleton and shared contracts. Do not run multiple implementation agents against the same checkout.

Recommended branches:

- `cft-package-contracts`
- `cft-managed-http`
- `cft-sampler-job-results`
- `cft-direct-pcss`
- `cft-fake-aer`
- `cft-registry-security`
- `cft-docs-release`
- `cft-integration`

Wave 0 is sequential. Waves 1A through 1F can run in parallel after Wave 0 is merged into each worktree. Wave 2 is integration and must be sequential.

## Environment Contract

The library reads constructor arguments first and environment variables second.

- `PCSS_TOKEN` or `PCSS_QAPI_TOKEN`: optional local PCSS token for direct mode or `auto` fallback.
- `CFT_PIASTQ_DASHBOARD_API_URL`: optional dashboard API base URL.
- `CFT_PIASTQ_DASHBOARD_API_KEY`: optional dashboard API key for protected runner endpoints.
- `CFT_PIASTQ_MODE`: optional default execution mode; one of `auto`, `managed`, `direct`.
- `CFT_PIASTQ_VERBOSE`: optional boolean-like value; defaults to notebook-friendly messages enabled.
- `CFT_PIASTQ_REGISTRY_PATH`: optional path for direct-mode SQLite registry.

Constructor arguments override these environment variables:

```python
client = PiastQClient(
    owner="szymo",
    token=pcss_token,
    dashboard_api_url="https://piastq-dashboard.example",
    dashboard_api_key="dashboard-key",
    mode="auto",
)
```

## File Map

Package files to create:

- `pyproject.toml`: package metadata, dependencies, optional extras, test/lint/type config.
- `README.md`: install, quickstart, modes, security model, dashboard contract.
- `src/cft_piastq/__init__.py`: public exports.
- `src/cft_piastq/_version.py`: package version fallback.
- `src/cft_piastq/backend.py`: lightweight backend handles for managed, direct, and fake modes.
- `src/cft_piastq/client.py`: `PiastQClient`, mode selection, healthcheck, backend factories.
- `src/cft_piastq/config.py`: env loading, boolean parsing, path defaults.
- `src/cft_piastq/counts.py`: quasi distribution to estimated counts conversion.
- `src/cft_piastq/direct.py`: lazy PCSS/AQT login, backend creation, direct sampler adapter.
- `src/cft_piastq/errors.py`: public exception hierarchy and sanitized messages.
- `src/cft_piastq/fake.py`: Aer simulator backend and dashboard noise model loading.
- `src/cft_piastq/http.py`: dashboard HTTP client, auth headers, error mapping.
- `src/cft_piastq/job.py`: `PiastQJob`, managed/direct/fake job wrappers, polling/cancel/counts.
- `src/cft_piastq/options.py`: mutable sampler options with `cft_*` split.
- `src/cft_piastq/registry.py`: direct-mode SQLite registry and event audit records.
- `src/cft_piastq/results.py`: `SamplerResult` JSON reconstruction and serialization helpers.
- `src/cft_piastq/sampler.py`: `PiastQSampler` facade and mode dispatch.
- `src/cft_piastq/security.py`: token redaction and safe display messages.
- `src/cft_piastq/serialization.py`: QPY base64 encode/decode and circuit metadata extraction.
- `src/cft_piastq/status.py`: status literals and normalization.
- `src/cft_piastq/types.py`: typed payload aliases and protocols.

Tests to create:

- `tests/conftest.py`
- `tests/test_public_api.py`
- `tests/test_client_modes.py`
- `tests/test_dashboard_http.py`
- `tests/test_sampler_options.py`
- `tests/test_serialization.py`
- `tests/test_results.py`
- `tests/test_job.py`
- `tests/test_counts.py`
- `tests/test_direct.py`
- `tests/test_registry.py`
- `tests/test_fake_backend.py`
- `tests/test_security.py`
- `tests/test_readme_examples.py`

Example files to create:

- `examples/managed_bell.py`
- `examples/direct_bell.py`
- `examples/fake_bell.py`

## Shared Contracts

Use these execution mode literals internally and in tests:

```python
ExecutionMode = Literal["auto", "managed", "direct", "fake"]
ResolvedExecutionMode = Literal["managed", "direct", "fake"]
```

Use these job status literals internally:

```python
JobStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "stale",
    "cancel_requested",
    "unknown",
]
```

Use this public exception hierarchy:

```python
class PiastQError(Exception): ...
class PiastQConfigurationError(PiastQError): ...
class DashboardUnavailableError(PiastQError): ...
class DashboardAuthError(PiastQError): ...
class ManagedJobError(PiastQError): ...
class DirectModeUnavailableError(PiastQError): ...
class DirectProviderError(PiastQError): ...
class FakeBackendError(PiastQError): ...
class PiastQTimeoutError(PiastQError): ...
```

Use this managed submit payload shape:

```json
{
  "owner": "szymo",
  "cft_job_name": "Bell smoke test",
  "cft_description": "2Q Bell test before RB run",
  "shots": 200,
  "circuits": [
    {
      "circuit_index": 0,
      "qpy_base64": "base64-qpy",
      "metadata": {
        "circuit_name": "bell",
        "num_qubits": 2,
        "num_clbits": 2,
        "depth": 2,
        "operation_counts": {"h": 1, "cx": 1, "measure": 2},
        "used_qubits": [0, 1],
        "used_couplings": [[0, 1]]
      }
    }
  ],
  "client_version": "0.1.0"
}
```

Use this managed result payload shape from the dashboard:

```json
{
  "server_job_id": "srv_abc123",
  "status": "succeeded",
  "shots": 200,
  "quasi_dists": [{"0": 0.5, "3": 0.5}],
  "metadata": [{"shots": 200, "circuit_index": 0}],
  "child_job_refs": [{"circuit_index": 0, "provider_job_id": "provider-1"}]
}
```

HTTP behavior:

- `GET /api/runner/health` resolves managed availability.
- `POST /api/runner/jobs` submits managed jobs and sends `X-Dashboard-Api-Key` when configured.
- `GET /api/runner/jobs/{server_job_id}` reads fresh managed status on every call.
- `GET /api/runner/jobs/{server_job_id}/result` fetches the result after success.
- `POST /api/runner/jobs/{server_job_id}/cancel` sends cancellation and requires the dashboard API key.
- `GET /api/noise-model/latest` fetches fake-backend noise only when `use_backend_noise=True`.
- A `401` or `403` from any managed runner endpoint raises `DashboardAuthError` and never falls back to direct mode.

Security behavior:

- Never send a PCSS token to the dashboard API.
- Never persist PCSS tokens, dashboard API keys, or authorization headers in SQLite.
- Never include raw provider exception strings in public errors if they contain token-like values.
- Fake backend jobs stay local and never call the dashboard Jobs API.

## Package Bootstrap

Run this once before Wave 0 if the folder is still not a Git repository:

```powershell
git init
git add 2026-06-26-cft-piastq-library-design.md 2026-06-26-piastq-benchmark-managed-runner-jobs.md docs/superpowers/plans/2026-06-26-cft-piastq-library.md
git commit -m "docs: add cft-piastq implementation plan"
```

If implementation happens in a different newly created repository, copy this plan into `docs/superpowers/plans/2026-06-26-cft-piastq-library.md` there before starting Wave 0.

## Wave 0: Package Skeleton and Shared Contracts

**Agent name:** Package contracts agent

**Run first:** yes, sequential.

**Skills:** `superpowers:test-driven-development`, `python-patterns`, `python-testing`, `security-review`.

**Files:**

- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/cft_piastq/__init__.py`
- Create: `src/cft_piastq/_version.py`
- Create: `src/cft_piastq/errors.py`
- Create: `src/cft_piastq/status.py`
- Create: `src/cft_piastq/security.py`
- Create: `src/cft_piastq/types.py`
- Create: `src/cft_piastq/config.py`
- Create: `tests/conftest.py`
- Create: `tests/test_public_api.py`
- Create: `tests/test_security.py`

**Steps:**

- [ ] Create `pyproject.toml` with `setuptools`, `src` layout, package name `cft-piastq`, import package `cft_piastq`, Python `>=3.10`, base dependencies `qiskit`, `httpx`, and `platformdirs`, dev dependencies `pytest`, `pytest-cov`, `ruff`, and `mypy`, optional extras `direct` for PCSS/AQT packages and `fake` for `qiskit-aer`.
- [ ] Write `tests/test_public_api.py` proving `from cft_piastq import PiastQClient, PiastQSampler, PiastQJob` succeeds without importing `pcss_qapi` or `qiskit_aer`.
- [ ] Write `tests/test_security.py` proving `redact_secrets("token=abc PCSS_TOKEN=secret dashboard-key")` removes token-like values and keeps non-secret context.
- [ ] Implement `errors.py` with the public exception hierarchy listed in Shared Contracts.
- [ ] Implement `status.py` with `normalize_job_status(value)` mapping provider/server values such as `DONE`, `finished`, `SUCCESS`, `ERROR`, and `CANCELLED` to the shared status literals.
- [ ] Implement `security.py` with `redact_secrets(message)` and `safe_error_message(exc)`; redact `PCSS_TOKEN`, `PCSS_QAPI_TOKEN`, `DASHBOARD_API_KEY`, `Authorization`, bearer tokens, and long API-key-looking strings.
- [ ] Implement `config.py` with env readers, boolean parsing, and default registry path using `platformdirs.user_cache_path("cft_piastq") / "jobs.sqlite3"`.
- [ ] Implement `__init__.py` exports for exceptions and public classes after their modules exist; during Wave 0, expose lightweight import guards that raise clear messages if the facade classes are used before their modules are added.
- [ ] Run: `.\.venv\Scripts\python -m pytest tests/test_public_api.py tests/test_security.py -q`
- [ ] Run: `.\.venv\Scripts\python -m ruff check src tests`
- [ ] Commit: `git add pyproject.toml README.md src tests && git commit -m "feat: add package skeleton and shared contracts"`

**Acceptance:**

- Top-level import works without optional PCSS or Aer packages.
- Secret redaction tests pass.
- Shared exception and status modules are available for every later wave.

## Wave 1A: Dashboard HTTP Client and Mode Selection

**Can run in parallel after Wave 0.**

**Skills:** `api-design`, `python-patterns`, `python-testing`, `error-handling`, `security-review`.

**Files:**

- Create: `src/cft_piastq/http.py`
- Create: `src/cft_piastq/backend.py`
- Create: `src/cft_piastq/client.py`
- Create: `tests/test_dashboard_http.py`
- Create: `tests/test_client_modes.py`
- Modify: `src/cft_piastq/__init__.py`

**Steps:**

- [ ] Write `tests/test_dashboard_http.py` using `httpx.MockTransport` for health success, unavailable health, `401`, `403`, submit success, submit failure with sanitized error, status read, result read, and cancel.
- [ ] Write `tests/test_client_modes.py` proving `mode="managed"` does not require a local PCSS token, `mode="direct"` requires a token, `mode="auto"` chooses managed when health succeeds, `mode="auto"` falls back to direct only when health is unavailable and a token exists, and `mode="auto"` raises `DashboardAuthError` on `401` or `403`.
- [ ] Implement `DashboardClient` with `base_url`, optional `api_key`, injectable `httpx.Client` or transport, timeout defaults, protected endpoint headers, JSON helpers, and error mapping.
- [ ] Implement `DashboardClient.health()`, `submit_job(payload)`, `get_job(server_job_id)`, `get_result(server_job_id)`, `cancel_job(server_job_id)`, and `get_noise_model()`.
- [ ] Implement backend handle dataclasses: `ManagedPiastQBackend`, `DirectPiastQBackend`, and `FakePiastQBackend`; each stores `mode`, `owner`, and adapter dependencies needed by `PiastQSampler`.
- [ ] Implement `PiastQClient.__init__` with constructor/env merging, verbose notebook messages, mode resolution, and no PCSS login in managed mode.
- [ ] Implement `PiastQClient.backend` returning a managed or direct backend handle based on resolved mode.
- [ ] Implement `PiastQClient.execution_mode` as the resolved mode string.
- [ ] Run: `.\.venv\Scripts\python -m pytest tests/test_dashboard_http.py tests/test_client_modes.py -q`
- [ ] Commit: `git add src/cft_piastq/http.py src/cft_piastq/backend.py src/cft_piastq/client.py src/cft_piastq/__init__.py tests/test_dashboard_http.py tests/test_client_modes.py && git commit -m "feat: add dashboard client and execution mode selection"`

**Acceptance:**

- Managed-mode health and auth behavior matches the design.
- PCSS token is not sent in any dashboard request fixture.
- Constructor arguments override environment values.

## Wave 1B: QPY Serialization and Result Reconstruction

**Can run in parallel after Wave 0.**

**Skills:** `python-patterns`, `python-testing`, `error-handling`.

**Files:**

- Create: `src/cft_piastq/serialization.py`
- Create: `src/cft_piastq/results.py`
- Create: `src/cft_piastq/counts.py`
- Create: `tests/test_serialization.py`
- Create: `tests/test_results.py`
- Create: `tests/test_counts.py`

**Steps:**

- [ ] Write `tests/test_serialization.py` with Bell and two-circuit fixtures proving `circuit_to_qpy_base64()` round-trips through `qpy_base64_to_circuit()` and preserves circuit name, qubits, clbits, and operation counts.
- [ ] Write metadata tests proving `circuit_metadata(qc, index=0)` returns `circuit_index`, `circuit_name`, `num_qubits`, `num_clbits`, `depth`, `operation_counts`, `used_qubits`, and `used_couplings`.
- [ ] Implement QPY encode/decode through `io.BytesIO`, `qiskit.qpy.dump`, and `qiskit.qpy.load`; raise `PiastQError` with sanitized context for invalid base64 or invalid QPY.
- [ ] Implement conservative used-coupling extraction by scanning two-qubit instructions and returning sorted pairs of integer qubit indices.
- [ ] Write `tests/test_results.py` proving `sampler_result_from_json()` reconstructs a Qiskit-compatible `SamplerResult` with one quasi distribution per logical input circuit and metadata preserved.
- [ ] Implement `sampler_result_from_json(payload)` accepting integer-key and string-key quasi distributions, preserving payload metadata, and adding `shots` metadata when the server returns top-level `shots`.
- [ ] Write `tests/test_counts.py` proving `estimated_counts_from_result(result, shots=200, num_bits=2)` returns `[{"00": 100, "11": 100}]` for `{0: 0.5, 3: 0.5}` and always returns a list.
- [ ] Implement count conversion with `QuasiDistribution.binary_probabilities(num_bits)`, `round(probability * shots)`, and zero floor for negative quasi probabilities.
- [ ] Run: `.\.venv\Scripts\python -m pytest tests/test_serialization.py tests/test_results.py tests/test_counts.py -q`
- [ ] Commit: `git add src/cft_piastq/serialization.py src/cft_piastq/results.py src/cft_piastq/counts.py tests/test_serialization.py tests/test_results.py tests/test_counts.py && git commit -m "feat: add qpy serialization and sampler result helpers"`

**Acceptance:**

- QPY helpers support single and multi-circuit requests.
- Result reconstruction uses Qiskit's `SamplerResult` rather than a custom result replacement.
- Count views are documented and tested as estimated counts derived from quasi distributions.

## Wave 1C: PiastQSampler and Managed Jobs

**Can run in parallel after Waves 1A and 1B are available.**

**Skills:** `python-patterns`, `python-testing`, `api-design`, `error-handling`.

**Files:**

- Create: `src/cft_piastq/options.py`
- Create: `src/cft_piastq/sampler.py`
- Create: `src/cft_piastq/job.py`
- Create: `tests/test_sampler_options.py`
- Create: `tests/test_job.py`
- Modify: `src/cft_piastq/__init__.py`

**Steps:**

- [ ] Write `tests/test_sampler_options.py` proving constructor options and mutable `sampler.options.cft_job_name` work, and `cft_*` options are stripped before provider adapter calls.
- [ ] Implement `PiastQSamplerOptions` with attribute and dict-style access for `cft_job_name`, `cft_description`, and provider options; preserve unknown provider options for direct/fake adapters.
- [ ] Implement `split_cft_options(options)` returning CFT metadata and provider options without mutating the caller's dict.
- [ ] Write managed sampler tests with a fake `DashboardClient` proving `PiastQSampler(client.backend).run(circuits=[qc], shots=200)` posts the managed payload and returns `PiastQJob`.
- [ ] Implement `PiastQSampler.run(circuits, parameter_values=None, shots=None, **run_options)` with list normalization, job name fallback order, CFT option extraction, QPY payload creation, and managed dispatch.
- [ ] Write managed job tests proving `job.job_id()`, `job.status()`, `job.cancel()`, `job.result(timeout=None, poll_interval=0.01)`, timeout behavior, failure behavior, and `job.counts()` work from fake dashboard responses.
- [ ] Implement `PiastQJob` as a facade over `ManagedJobHandle`, `DirectJobHandle`, and `FakeJobHandle`.
- [ ] Implement managed status polling so `status()` calls the dashboard every time and `result()` polls until `succeeded`, `failed`, or `cancelled`.
- [ ] Implement `PiastQTimeoutError` when a finite timeout elapses before terminal status.
- [ ] Run: `.\.venv\Scripts\python -m pytest tests/test_sampler_options.py tests/test_job.py -q`
- [ ] Commit: `git add src/cft_piastq/options.py src/cft_piastq/sampler.py src/cft_piastq/job.py src/cft_piastq/__init__.py tests/test_sampler_options.py tests/test_job.py && git commit -m "feat: add sampler facade and managed job handling"`

**Acceptance:**

- User-facing API from the design works for managed mode.
- `cft_*` options never reach provider adapters.
- Managed `status()` is never cached.
- `result()` returns Qiskit's `SamplerResult`.

## Wave 1D: Direct PCSS/AQT Mode and Local Registry

**Can run in parallel after Waves 1A and 1C are available.**

**Skills:** `python-patterns`, `python-testing`, `error-handling`, `security-review`.

**Files:**

- Create: `src/cft_piastq/direct.py`
- Create: `src/cft_piastq/registry.py`
- Create: `tests/test_direct.py`
- Create: `tests/test_registry.py`
- Modify: `src/cft_piastq/client.py`
- Modify: `src/cft_piastq/sampler.py`
- Modify: `src/cft_piastq/job.py`

**Steps:**

- [ ] Write `tests/test_direct.py` using fake authorization, provider, backend, sampler, and raw job objects; prove direct mode logs in lazily, obtains the direct access backend, delegates to an AQTSampler-compatible adapter, and wraps the returned raw job.
- [ ] Implement `DirectPcssAdapter` with lazy imports of `pcss_qapi.AuthorizationService`, `pcss_qapi.aqt.provider.PCSS_AQTProvider`, and `qiskit_aqt_provider.primitives.AQTSampler`.
- [ ] Implement direct mode so missing optional packages raise `DirectModeUnavailableError` with package names and no token values.
- [ ] Implement direct sampler dispatch with provider options passed through after `cft_*` filtering.
- [ ] Write `tests/test_registry.py` proving SQLite schema creation, direct job insert, status update, sanitized error storage, event failure storage, and no secret persistence.
- [ ] Implement `DirectJobRegistry` with tables `direct_jobs` and `direct_events`, path creation, thread lock, parameterized SQL, and no QPY/token persistence.
- [ ] Implement best-effort `DashboardEventReporter` for direct jobs; default endpoint path is `/api/runner/direct-events`, `404` disables network event upload for the process, and every upload failure is stored in SQLite without failing the quantum job.
- [ ] Implement direct `PiastQJob.status()`, `result()`, `cancel()`, and `counts()` by delegating to raw provider job methods where available.
- [ ] If provider cancellation is unsupported, record `cancel_requested` locally and return that status without pretending provider cancellation succeeded.
- [ ] Run: `.\.venv\Scripts\python -m pytest tests/test_direct.py tests/test_registry.py -q`
- [ ] Commit: `git add src/cft_piastq/direct.py src/cft_piastq/registry.py src/cft_piastq/client.py src/cft_piastq/sampler.py src/cft_piastq/job.py tests/test_direct.py tests/test_registry.py && git commit -m "feat: add direct pcss mode and local registry"`

**Acceptance:**

- Direct mode never imports optional PCSS packages at top-level import time.
- Direct dashboard event failures never fail a quantum job.
- SQLite registry stores audit/cache data without secrets.

## Wave 1E: Fake Aer Backend and Noise Model Support

**Can run in parallel after Waves 1A, 1B, and 1C are available.**

**Skills:** `python-patterns`, `python-testing`, `error-handling`, `security-review`.

**Files:**

- Create: `src/cft_piastq/fake.py`
- Create: `tests/test_fake_backend.py`
- Modify: `src/cft_piastq/client.py`
- Modify: `src/cft_piastq/sampler.py`
- Modify: `src/cft_piastq/job.py`

**Steps:**

- [ ] Write fake backend tests proving `client.fake_backend(use_backend_noise=False)` returns a backend handle without calling dashboard noise endpoints.
- [ ] Write fake sampler tests proving a Bell circuit run returns a `PiastQJob`, `result()` returns a `SamplerResult`, and fake jobs do not send dashboard job submissions or direct events.
- [ ] Implement `FakePiastQBackend` construction in `PiastQClient.fake_backend(use_backend_noise=False)`.
- [ ] Implement `FakeSamplerAdapter` with lazy `qiskit_aer` imports and deterministic tests through an injectable simulator adapter.
- [ ] Write noise tests proving `use_backend_noise=True` calls `GET /api/noise-model/latest`, converts supported payloads into an Aer `NoiseModel`, and raises `FakeBackendError` when the payload is unavailable or malformed.
- [ ] Implement `noise_model_from_payload(payload)` supporting a direct Qiskit Aer noise model dict under `noise_model` and the dashboard-derived CFT schema with one-qubit, two-qubit, readout, and RXX error entries.
- [ ] Document in code and README that the dashboard-derived noise model is a simulation convenience, not a calibrated digital twin.
- [ ] Run: `.\.venv\Scripts\python -m pytest tests/test_fake_backend.py -q`
- [ ] Commit: `git add src/cft_piastq/fake.py src/cft_piastq/client.py src/cft_piastq/sampler.py src/cft_piastq/job.py tests/test_fake_backend.py && git commit -m "feat: add fake aer backend support"`

**Acceptance:**

- Fake backend works without dashboard calls by default.
- Noise-backed fake mode fails clearly when no noise model is available.
- Fake jobs are absent from dashboard job submission/event tests.

## Wave 1F: Security, Examples, and Documentation

**Can run in parallel after public APIs from Waves 1A through 1E are stable.**

**Skills:** `security-review`, `python-testing`, `documentation-lookup`.

**Files:**

- Modify: `README.md`
- Create: `examples/managed_bell.py`
- Create: `examples/direct_bell.py`
- Create: `examples/fake_bell.py`
- Create: `tests/test_readme_examples.py`
- Modify: `tests/test_security.py`

**Steps:**

- [ ] Write `tests/test_readme_examples.py` that imports every example module with provider calls guarded behind `if __name__ == "__main__"` and verifies public snippets stay syntactically valid.
- [ ] Extend `tests/test_security.py` to recursively inspect fake dashboard requests, SQLite rows, raised errors, and README examples for raw secret values used in tests.
- [ ] Write README sections: installation, optional extras, managed mode quickstart, auto mode fallback, direct mode quickstart, fake mode quickstart, options, counts semantics, dashboard endpoint contract, security model, and known V1 limitations.
- [ ] Add `examples/managed_bell.py` using `PiastQClient`, `PiastQSampler`, `cft_job_name`, and `job.counts()[0]`.
- [ ] Add `examples/direct_bell.py` using local `PCSS_TOKEN`, direct mode, and no dashboard dependency.
- [ ] Add `examples/fake_bell.py` using `client.fake_backend(use_backend_noise=False)`.
- [ ] Run: `.\.venv\Scripts\python -m pytest tests/test_readme_examples.py tests/test_security.py -q`
- [ ] Run: `.\.venv\Scripts\python -m ruff check README.md examples src tests`
- [ ] Commit: `git add README.md examples tests/test_readme_examples.py tests/test_security.py && git commit -m "docs: add examples and security guidance"`

**Acceptance:**

- README matches the implemented constructor names and mode behavior.
- Examples do not run live PCSS or dashboard calls during import.
- Documentation never instructs users to expose PCSS tokens in frontend or browser contexts.

## Wave 2: Integration and Release Readiness

**Run sequentially after Wave 1 branches are merged.**

**Skills:** `superpowers:subagent-driven-development`, `superpowers:verification-before-completion`, `python-patterns`, `python-testing`, `error-handling`, `security-review`.

**Files:**

- Modify as needed across `src/cft_piastq/`, `tests/`, `README.md`, `examples/`, and `pyproject.toml`.

**Steps:**

- [ ] Merge Wave 1 branches in this order: package contracts, QPY/results, dashboard HTTP, sampler/job, direct PCSS, fake Aer, docs/security.
- [ ] Resolve import cycles by keeping adapters below public facades: `client.py` and `sampler.py` may import adapters; adapter modules must not import public facade classes.
- [ ] Verify `from cft_piastq import PiastQClient, PiastQSampler, PiastQJob` succeeds in a clean interpreter.
- [ ] Verify managed mode request payload matches the dashboard counterpart plan's `RunnerJobSubmitRequest` shape.
- [ ] Verify `auto` mode does not fall back after managed `401` or `403`.
- [ ] Verify direct mode works with fake adapter tests and does not require real PCSS network access in unit tests.
- [ ] Verify fake mode tests pass with and without noise payload.
- [ ] Run all tests: `.\.venv\Scripts\python -m pytest -q`
- [ ] Run coverage: `.\.venv\Scripts\python -m pytest --cov=cft_piastq --cov-report=term-missing`
- [ ] Run lint: `.\.venv\Scripts\python -m ruff check src tests examples`
- [ ] Run format check: `.\.venv\Scripts\python -m ruff format --check src tests examples`
- [ ] Run type check: `.\.venv\Scripts\python -m mypy src/cft_piastq`
- [ ] Build wheel and sdist: `.\.venv\Scripts\python -m build`
- [ ] Inspect package contents: `.\.venv\Scripts\python -m twine check dist/*`
- [ ] Commit: `git add . && git commit -m "chore: integrate cft-piastq library"`

**Acceptance:**

- Tests, lint, format check, type check, and package build pass.
- The package can be installed with `pip install -e .[dev,fake]`.
- Managed, direct, and fake paths are covered by deterministic tests.
- Optional PCSS/Aer imports remain lazy.
- No tests, docs, or fixtures leak secrets.

## Recommended Agent Dispatch Prompts

Use these prompts as the starting point for parallel agents. Each agent should work in its own worktree and return: files changed, tests run, test output summary, and blockers.

### Agent 0 Prompt: Package Contracts

Use skills: `superpowers:test-driven-development`, `python-patterns`, `python-testing`, `security-review`.

Implement Wave 0 from `docs/superpowers/plans/2026-06-26-cft-piastq-library.md`. Own package metadata, public import contract, exception/status modules, config helpers, and secret redaction tests. Return the exact optional imports that remain lazy.

### Agent 1 Prompt: Dashboard HTTP and Client Modes

Use skills: `api-design`, `python-patterns`, `python-testing`, `error-handling`, `security-review`.

Implement Wave 1A. Own `http.py`, `backend.py`, `client.py`, and mode tests. Prove `auto` fallback behavior and `401`/`403` hard failure behavior with `httpx.MockTransport`. Do not implement sampler or job result polling.

### Agent 2 Prompt: Serialization and Results

Use skills: `python-patterns`, `python-testing`, `error-handling`.

Implement Wave 1B. Own QPY serialization, circuit metadata extraction, `SamplerResult` reconstruction, and estimated counts. Use real Qiskit Bell-circuit fixtures. Do not add PCSS or dashboard calls.

### Agent 3 Prompt: Sampler and Managed Job

Use skills: `python-patterns`, `python-testing`, `api-design`, `error-handling`.

Implement Wave 1C. Own options splitting, `PiastQSampler`, and managed `PiastQJob`. Use fake dashboard clients and result payloads. Ensure `cft_*` options never reach provider option dictionaries.

### Agent 4 Prompt: Direct PCSS and Registry

Use skills: `python-patterns`, `python-testing`, `error-handling`, `security-review`.

Implement Wave 1D. Own direct adapter, SQLite registry, direct event reporter, and direct job wrapper behavior. Use fake PCSS/AQT modules or injectable adapter doubles in tests. Do not require live PCSS credentials.

### Agent 5 Prompt: Fake Aer Backend

Use skills: `python-patterns`, `python-testing`, `error-handling`, `security-review`.

Implement Wave 1E. Own fake backend creation, Aer lazy imports, simulator adapter, and noise model payload conversion. Prove fake jobs do not call dashboard job submission or direct event endpoints.

### Agent 6 Prompt: Docs and Security Examples

Use skills: `security-review`, `python-testing`, `documentation-lookup`.

Implement Wave 1F. Own README, examples, example import tests, and secret-leak tests. Keep examples executable but guarded from live calls during import.

### Agent 7 Prompt: Integration

Use skills: `superpowers:subagent-driven-development`, `superpowers:verification-before-completion`, `python-patterns`, `python-testing`, `error-handling`, `security-review`.

Implement Wave 2 after other branches merge. Resolve import cycles, run full verification, build package artifacts, and report exact command results.

## Risk Controls

- PCSS and AQT packages may not be available on public PyPI. Keep them optional and lazily imported so managed and fake modes remain usable.
- Qiskit primitive APIs can differ across installed versions. Hide version differences in `results.py`, `fake.py`, and adapter classes, and update tests against the installed version before changing public APIs.
- Direct provider jobs may not expose provider IDs or cancellation. Store missing provider IDs as `None`, and represent unsupported cancellation as `cancel_requested`.
- Managed server result payloads can evolve. Keep JSON reconstruction isolated in `results.py` and test both integer and string quasi distribution keys.
- Local SQLite is an audit/cache helper only. Do not promise direct job recovery after notebook shutdown unless provider restore support is proven.
- Dashboard direct-event upload is best-effort. A missing event endpoint must not affect direct PCSS execution.
- Noise-backed fake mode can mislead users if presented as calibration quality. README and payload provenance must state that it is derived from benchmark snapshots.

## Final Verification Checklist

- [ ] `.\.venv\Scripts\python -m pytest -q` passes.
- [ ] `.\.venv\Scripts\python -m pytest --cov=cft_piastq --cov-report=term-missing` passes with meaningful coverage for managed, direct, and fake modes.
- [ ] `.\.venv\Scripts\python -m ruff check src tests examples` passes.
- [ ] `.\.venv\Scripts\python -m ruff format --check src tests examples` passes.
- [ ] `.\.venv\Scripts\python -m mypy src/cft_piastq` passes.
- [ ] `.\.venv\Scripts\python -m build` creates wheel and sdist.
- [ ] `.\.venv\Scripts\python -m twine check dist/*` passes.
- [ ] Top-level import works without `pcss_qapi` installed.
- [ ] Top-level import works without `qiskit_aer` installed.
- [ ] `PiastQClient(mode="managed")` does not require a local PCSS token.
- [ ] `PiastQClient(mode="direct")` requires a local PCSS token.
- [ ] `PiastQClient(mode="auto")` uses managed mode when health succeeds.
- [ ] `auto` falls back to direct only when managed is unavailable and a local token exists.
- [ ] `auto` does not fall back after dashboard `401` or `403`.
- [ ] Managed submit sends QPY base64 and circuit metadata.
- [ ] Managed submit never sends the PCSS token.
- [ ] `PiastQSampler` supports constructor options and mutable `sampler.options`.
- [ ] `cft_job_name` fallback order matches the design.
- [ ] `PiastQJob.status()` calls managed server every time.
- [ ] `PiastQJob.result()` returns a Qiskit-compatible `SamplerResult`.
- [ ] `PiastQJob.counts()` always returns a list of dictionaries.
- [ ] Multi-circuit managed result returns one quasi distribution per input circuit.
- [ ] Direct dashboard event failures are recorded locally and do not fail the provider job.
- [ ] Fake backend works without dashboard noise by default.
- [ ] Fake backend with `use_backend_noise=True` fetches and validates the noise payload.
- [ ] Fake jobs are never submitted to the dashboard Jobs list.
- [ ] README examples match implemented APIs.
- [ ] No response, exception, SQLite row, fixture, or README snippet leaks configured test secrets.
