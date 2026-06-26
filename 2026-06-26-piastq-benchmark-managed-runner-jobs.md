# Managed Runner Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the managed PiastQ runner counterpart in `piastq-benchmark`: protected job submission/cancel API, Postgres-backed logical jobs, in-process sequential worker, job history/detail UI, benchmark snapshot copies, and an Aer noise model endpoint.

**Architecture:** Keep `piastq-benchmark` as the FastAPI + Vite dashboard. Add a focused `backend/runner/` package with Pydantic contracts, storage adapters, runner service, worker, provider adapter, aggregation, benchmark snapshot, and noise model modules. Keep the frontend as a dashboard UI by splitting Jobs components and API client code out of the current monolithic `frontend/src/App.tsx`.

**Tech Stack:** FastAPI, Pydantic, Python `unittest`, PostgreSQL via `psycopg[binary,pool]`, Qiskit/QPY, qiskit-aqt-provider/AQTSampler, Vite, React, TypeScript, Tailwind CSS, Vitest, Playwright.

---

## Source Inputs

- Spec: `docs/superpowers/specs/2026-06-26-piastq-benchmark-managed-runner-jobs-design.md`
- Current backend entrypoint: `backend/app.py`
- Current backend helpers: `backend/benchmark_runs.py`, `backend/quantum_status.py`, `benchmarks/common/backend.py`
- Current frontend shell: `frontend/src/App.tsx`
- Current frontend client modules: `frontend/src/lib/backend-status.ts`, `frontend/src/lib/benchmark-runs.ts`, `frontend/src/lib/piastq-dashboard-data.ts`
- Current tests: `tests/test_backend_app.py`, `tests/test_benchmark_runs.py`, `frontend/src/App.test.tsx`

## Skill Review and Assignment

The useful available skills for this implementation are:

- `superpowers:using-superpowers`: requested explicitly; use before all task execution.
- `superpowers:using-git-worktrees`: use before implementation so each parallel agent works in an isolated worktree/branch.
- `superpowers:dispatching-parallel-agents`: use for the Wave 1 independent agent split below.
- `superpowers:subagent-driven-development`: preferred execution mode after this plan is accepted.
- `superpowers:test-driven-development`: use inside each implementation task.
- `superpowers:verification-before-completion`: use before any agent reports a task complete.
- `api-design`: use for `/api/runner/*`, `/api/jobs`, snapshot, and noise endpoints.
- `fastapi-patterns`: use for route modules, dependency injection, Pydantic schemas, and test overrides.
- `database-migrations`: use for immutable SQL migration files and migration safety.
- `postgres-patterns`: use for queue locking with `FOR UPDATE SKIP LOCKED`, indexes, JSONB storage, and status queries.
- `python-testing`: use for backend TDD and mocked provider tests.
- `security-review`: use for API key enforcement, PCSS token isolation, response redaction, and SQL parameterization.
- `frontend-patterns`: use for React component split, hooks, state, loading/error/empty states.
- `vite-patterns`: use only if `vite.config.ts` or dev proxy behavior is changed.
- `accessibility`: use for Jobs table, detail panel, tabs, lists, status updates, and keyboard navigation.
- `e2e-testing`: use for Playwright smoke tests after UI wiring.
- `docker-patterns` and `deployment-patterns`: use only for the deployment/README agent if Dockerfile or Railway env docs change.

Do not assign `design-taste-frontend` to this work. That skill states it is not for dashboards, data tables, or multi-step product UI. Jobs UI should instead follow the existing quiet technical dashboard style plus `frontend-patterns` and `accessibility`.

## Parallelization Rule

Parallel implementation should happen in separate worktrees. Do not run multiple implementation agents against the same checkout.

Recommended branches:

- `runner-contracts-base`
- `runner-storage-postgres`
- `runner-api-contract`
- `runner-worker-provider`
- `runner-snapshot-noise`
- `runner-jobs-ui`
- `runner-security-contract-tests`
- `runner-deploy-docs`

Wave 0 is sequential because it creates shared contracts. Wave 1 can run in parallel after Wave 0 is merged into each worktree. Wave 2 is integration and must be sequential.

## Environment Contract

Add these server-side env vars:

- `DATABASE_URL`: Postgres connection string.
- `PCSS_TOKEN` or `PCSS_QAPI_TOKEN`: shared server-side PCSS token, never returned to clients.
- `DASHBOARD_API_KEY`: API key required by submit and cancel endpoints.
- `MANAGED_RUNNER_ENABLED`: defaults to `1`; set `0` to disable managed runner while keeping read APIs alive.
- `MAX_SHOTS_PER_PROVIDER_JOB`: defaults to `200`.
- `MAX_RESULT_JSON_BYTES`: defaults to `1048576`.
- `RUNNER_POLL_INTERVAL_SECONDS`: defaults to `2`.

## File Map

Backend files to create:

- `backend/runner/__init__.py`
- `backend/runner/config.py`
- `backend/runner/errors.py`
- `backend/runner/schemas.py`
- `backend/runner/auth.py`
- `backend/runner/store.py`
- `backend/runner/in_memory_store.py`
- `backend/runner/postgres_store.py`
- `backend/runner/migrations.py`
- `backend/runner/migrations/001_managed_runner_jobs.sql`
- `backend/runner/snapshots.py`
- `backend/runner/noise_model.py`
- `backend/runner/provider.py`
- `backend/runner/aggregation.py`
- `backend/runner/service.py`
- `backend/runner/worker.py`
- `backend/runner/routes.py`

Backend files to modify:

- `backend/app.py`: register runner routes, inject store/config, start worker in lifespan, run migrations when `DATABASE_URL` is present.
- `backend/requirements.txt`: add `psycopg[binary,pool]`; add `qiskit-aer` only if the noise model endpoint cannot serialize with currently installed Qiskit packages.
- `README.md`: document env vars and endpoints.
- `Dockerfile`: no change expected unless new runtime dependency needs a system package.

Backend tests to create:

- `tests/test_runner_schemas.py`
- `tests/test_runner_api.py`
- `tests/test_runner_store_in_memory.py`
- `tests/test_runner_worker.py`
- `tests/test_runner_aggregation.py`
- `tests/test_runner_snapshots_noise.py`
- `tests/test_runner_security.py`

Frontend files to create:

- `frontend/src/lib/runner-jobs.ts`
- `frontend/src/lib/runner-jobs.test.ts`
- `frontend/src/components/jobs/JobsTab.tsx`
- `frontend/src/components/jobs/JobsTab.test.tsx`
- `frontend/src/components/jobs/JobDetail.tsx`
- `frontend/src/components/jobs/JobDetail.test.tsx`
- `frontend/src/components/jobs/JobSnapshotMap.tsx`
- `frontend/src/components/jobs/JobResultPreview.tsx`
- `frontend/src/components/jobs/types.ts`

Frontend files to modify:

- `frontend/src/App.tsx`: introduce a dashboard tab switcher and render current benchmark view plus Jobs tab.
- `frontend/src/App.test.tsx`: cover the Jobs tab entry point without launching benchmark or runner jobs on page load.
- `frontend/src/styles.css`: add focused styles for table density, detail layout, status pills, timeline, and historical snapshot callouts.

Frontend E2E files to create if Playwright config exists or is added:

- `frontend/tests/e2e/jobs.spec.ts`
- `frontend/playwright.config.ts` if missing.

## Shared Contracts

Use these status literals everywhere:

```python
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "stale"]
ChildJobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
```

Use these API status codes:

- Missing API key: `401`
- Wrong API key: `403`
- Submit validation failure: `400`
- Job not found: `404`
- Result requested before success: `409`
- Result too large: job status `failed`, error code `result_too_large`
- Runner unavailable on health: `200` with `runner_available=false`

Use this error body shape for runner errors:

```json
{
  "error": {
    "code": "invalid_api_key",
    "message": "API key is invalid."
  }
}
```

Do not include `PCSS_TOKEN`, `PCSS_QAPI_TOKEN`, `DASHBOARD_API_KEY`, `Authorization`, or provider exception strings in API responses.

## Migration Shape

Create `backend/runner/migrations/001_managed_runner_jobs.sql` with these tables and indexes:

```sql
CREATE TABLE IF NOT EXISTS runner_jobs (
  server_job_id text PRIMARY KEY,
  owner text NOT NULL,
  name text NOT NULL,
  description text,
  mode text NOT NULL DEFAULT 'managed',
  status text NOT NULL,
  provider_status text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz,
  requested_shots_per_circuit integer NOT NULL,
  max_shots_per_provider_job integer NOT NULL,
  completed_child_jobs integer NOT NULL DEFAULT 0,
  total_child_jobs integer NOT NULL DEFAULT 0,
  client_version text,
  backend_name text,
  benchmark_snapshot_json jsonb NOT NULL,
  aggregated_result_json jsonb,
  error_message text,
  cancel_requested boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runner_circuits (
  server_job_id text NOT NULL REFERENCES runner_jobs(server_job_id) ON DELETE CASCADE,
  circuit_index integer NOT NULL,
  qpy_base64 text NOT NULL,
  circuit_name text,
  num_qubits integer,
  num_clbits integer,
  depth integer,
  operation_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
  used_qubits jsonb NOT NULL DEFAULT '[]'::jsonb,
  used_couplings jsonb NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (server_job_id, circuit_index)
);

CREATE TABLE IF NOT EXISTS runner_child_jobs (
  server_job_id text NOT NULL REFERENCES runner_jobs(server_job_id) ON DELETE CASCADE,
  child_job_id text NOT NULL,
  circuit_index integer NOT NULL,
  repetition_index integer NOT NULL,
  provider_job_id text,
  status text NOT NULL,
  provider_status text,
  shots integer NOT NULL,
  started_at timestamptz,
  finished_at timestamptz,
  result_json jsonb,
  error_message text,
  PRIMARY KEY (server_job_id, child_job_id)
);

CREATE INDEX IF NOT EXISTS idx_runner_jobs_status_created
  ON runner_jobs(status, created_at);

CREATE INDEX IF NOT EXISTS idx_runner_jobs_created_desc
  ON runner_jobs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_runner_child_jobs_server_circuit
  ON runner_child_jobs(server_job_id, circuit_index, repetition_index);
```

## Wave 0: Contract Agent

**Agent name:** Contract and shared types agent

**Run first:** yes, sequential.

**Skills:** `superpowers:test-driven-development`, `api-design`, `fastapi-patterns`, `python-testing`, `security-review`.

**Files:**

- Create: `backend/runner/__init__.py`
- Create: `backend/runner/config.py`
- Create: `backend/runner/errors.py`
- Create: `backend/runner/schemas.py`
- Create: `backend/runner/auth.py`
- Create: `backend/runner/store.py`
- Create: `backend/runner/in_memory_store.py`
- Create: `tests/test_runner_schemas.py`
- Create: `tests/test_runner_security.py`

**Steps:**

- [ ] Write tests that validate request/response schema normalization for `POST /api/runner/jobs`, status responses, result-not-ready responses, and no secret fields.
- [ ] Create Pydantic request models: `RunnerJobSubmitRequest`, `RunnerCircuitPayload`, `RunnerCircuitMetadata`.
- [ ] Create Pydantic response models: `RunnerHealthResponse`, `RunnerJobSubmitResponse`, `RunnerJobStatusResponse`, `RunnerJobResultResponse`, `RunnerJobListResponse`, `RunnerErrorResponse`.
- [ ] Create domain dataclasses or Pydantic models: `LogicalJobRecord`, `CircuitRecord`, `ChildJobRecord`, `JobSnapshot`.
- [ ] Implement `RunnerSettings.from_env()` with defaults listed in Environment Contract.
- [ ] Implement `require_dashboard_api_key()` dependency: missing key raises 401, wrong key raises 403, correct `X-Dashboard-Api-Key` passes.
- [ ] Implement `sanitize_runner_error(exc)` that maps provider/internal exceptions to stable messages and redacts token-like strings.
- [ ] Implement `RunnerStore` protocol with methods needed by API, worker, and tests.
- [ ] Implement `InMemoryRunnerStore` with deterministic ordering and thread lock for tests.
- [ ] Run: `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest tests.test_runner_schemas tests.test_runner_security -v`

**Acceptance:**

- Schema tests pass.
- Security tests prove PCSS/API keys are not serialized.
- Other agents can depend on `backend.runner.schemas`, `backend.runner.store`, and `backend.runner.in_memory_store`.

## Wave 1A: Postgres Storage Agent

**Can run in parallel after Wave 0.**

**Skills:** `database-migrations`, `postgres-patterns`, `fastapi-patterns`, `python-testing`, `security-review`.

**Files:**

- Create: `backend/runner/migrations.py`
- Create: `backend/runner/migrations/001_managed_runner_jobs.sql`
- Create: `backend/runner/postgres_store.py`
- Create: `tests/test_runner_store_in_memory.py`
- Modify: `backend/requirements.txt`

**Steps:**

- [ ] Add `psycopg[binary,pool]` to `backend/requirements.txt`.
- [ ] Write migration SQL exactly matching Migration Shape.
- [ ] Implement `apply_runner_migrations(database_url)` that records applied migrations in `runner_schema_migrations(version text primary key, applied_at timestamptz not null default now())`.
- [ ] Implement `PostgresRunnerStore.claim_oldest_queued_job()` using `UPDATE ... WHERE server_job_id = (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING *`.
- [ ] Implement insert/read/list/update methods using parameterized SQL only.
- [ ] Implement list pagination with `limit` capped at 100 and `offset >= 0`.
- [ ] Add unit tests against `InMemoryRunnerStore` for logical job insert, circuit insert, child insert, progress update, cancellation flag, and listing order.
- [ ] Add optional Postgres integration test gated by `RUN_POSTGRES_TESTS=1` and `DATABASE_URL`.
- [ ] Run: `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest tests.test_runner_store_in_memory -v`

**Acceptance:**

- Queue claim is atomic.
- All SQL is parameterized.
- Migration is immutable and safe to run more than once.

## Wave 1B: Runner API Agent

**Can run in parallel after Wave 0.**

**Skills:** `api-design`, `fastapi-patterns`, `python-testing`, `security-review`.

**Files:**

- Create: `backend/runner/routes.py`
- Create: `backend/runner/service.py`
- Create: `tests/test_runner_api.py`
- Modify: `backend/app.py`

**Steps:**

- [ ] Write API tests using `TestClient(create_app(...))` with `InMemoryRunnerStore` and controlled `RunnerSettings`.
- [ ] Implement `GET /api/runner/health`.
- [ ] Implement `POST /api/runner/jobs` with API key requirement, QPY base64 validation, server-generated `server_job_id`, submit-time benchmark snapshot lookup, logical job creation, circuit creation, and child job planning.
- [ ] Implement `GET /api/runner/jobs/{server_job_id}`.
- [ ] Implement `GET /api/runner/jobs/{server_job_id}/result` returning `409` until `status == "succeeded"`.
- [ ] Implement `POST /api/runner/jobs/{server_job_id}/cancel` with API key requirement. Queued jobs become `cancelled`; running jobs set `cancel_requested=true`.
- [ ] Implement `GET /api/jobs` for the dashboard table, excluding fake backend jobs by only returning `mode == "managed"`.
- [ ] Register router in `create_app()` without breaking existing `/api/backend-status` and `/api/benchmarks` endpoints.
- [ ] Run: `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest tests.test_runner_api -v`

**Acceptance:**

- Submit and cancel require API key.
- Health returns unavailable when no server PCSS token or runner disabled.
- Read endpoints never expose token-bearing fields.
- Existing backend app tests still pass.

## Wave 1C: Worker and Provider Agent

**Can run in parallel after Wave 0.**

**Skills:** `backend-patterns`, `python-testing`, `error-handling`, `security-review`.

**Files:**

- Create: `backend/runner/provider.py`
- Create: `backend/runner/aggregation.py`
- Create: `backend/runner/worker.py`
- Create: `tests/test_runner_worker.py`
- Create: `tests/test_runner_aggregation.py`
- Modify: `backend/app.py`

**Steps:**

- [ ] Write worker tests with fake provider that records submitted circuits, shots, provider job IDs, statuses, and results.
- [ ] Implement QPY decode from base64 to Qiskit circuits in `provider.py`.
- [ ] Implement `PcssSamplerProvider` that loads PCSS backend from server env and runs `AQTSampler(backend).run(circuits=[circuit], shots=shots)`.
- [ ] Implement fake provider class for tests with deterministic quasi distributions.
- [ ] Implement `aggregate_child_results(children, circuit_count, requested_shots)` preserving input circuit order and returning one `quasi_dist` per input circuit.
- [ ] Enforce `MAX_RESULT_JSON_BYTES` before storing aggregated JSON; mark job failed with code/message `result_too_large` if exceeded.
- [ ] Implement `RunnerWorker.run_once()` that claims one queued job, creates/runs child jobs sequentially, records provider IDs when available, updates progress after each child, checks cancellation between child jobs, stores aggregation, and marks final status.
- [ ] Implement stale recovery at startup: running jobs without provider restore path become `stale`.
- [ ] Wire optional background worker in FastAPI lifespan when `runner_available` is true.
- [ ] Run: `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest tests.test_runner_worker tests.test_runner_aggregation -v`

**Acceptance:**

- Only one logical job runs at a time per worker.
- Progress fields compute `completed_child_jobs / total_child_jobs`.
- Child provider job IDs are stored when the provider exposes them.
- Provider errors are sanitized before persistence and API response.

## Wave 1D: Snapshot and Noise Model Agent

**Can run in parallel after Wave 0.**

**Skills:** `api-design`, `fastapi-patterns`, `python-testing`, `security-review`.

**Files:**

- Create: `backend/runner/snapshots.py`
- Create: `backend/runner/noise_model.py`
- Create: `tests/test_runner_snapshots_noise.py`
- Modify: `backend/runner/routes.py`

**Steps:**

- [ ] Write tests that load `benchmarks/devices/piastq/example.json` and return normalized snapshot data.
- [ ] Implement `load_latest_benchmark_snapshot()` that reads the repository benchmark fixture and preserves raw provenance: device, benchmarkRun, backend name, measuredAt, and source.
- [ ] Implement `snapshot_for_submit()` that returns a server-owned copy for job records.
- [ ] Implement `GET /api/benchmark-snapshot/latest`.
- [ ] Implement `build_noise_model_payload(snapshot)` returning JSON with `schema`, `backend_name`, `provenance`, `basis_gates`, and error entries derived from one-qubit, two-qubit, readout when present, and RXX metrics when present.
- [ ] Implement `GET /api/noise-model/latest`.
- [ ] Add a clear `provenance.warning` value: `Derived from benchmark snapshot; not a calibrated digital twin.`
- [ ] Run: `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest tests.test_runner_snapshots_noise -v`

**Acceptance:**

- Submit-time snapshots are server-generated, not trusted from client request.
- Noise payload is valid JSON and includes provenance metadata.
- Missing benchmark fields produce omitted entries, not crashes.

## Wave 1E: Jobs UI Agent

**Can run in parallel after Wave 0.**

**Skills:** `frontend-patterns`, `accessibility`, `vite-patterns`, `e2e-testing`.

**Files:**

- Create: `frontend/src/lib/runner-jobs.ts`
- Create: `frontend/src/lib/runner-jobs.test.ts`
- Create: `frontend/src/components/jobs/types.ts`
- Create: `frontend/src/components/jobs/JobsTab.tsx`
- Create: `frontend/src/components/jobs/JobsTab.test.tsx`
- Create: `frontend/src/components/jobs/JobDetail.tsx`
- Create: `frontend/src/components/jobs/JobDetail.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/styles.css`

**Steps:**

- [ ] Write `normalizeRunnerJobList`, `normalizeRunnerJobDetail`, and `normalizeRunnerJobResult` tests for valid, partial, and invalid payloads.
- [ ] Implement `fetchRunnerJobs()`, `fetchRunnerJobDetail(serverJobId)`, and `fetchRunnerJobResult(serverJobId)` with no API key in browser code.
- [ ] Add a tab control in `App.tsx` with two tabs: benchmark map and Jobs.
- [ ] Implement Jobs table columns: timestamp, owner, name, status/progress, job ID.
- [ ] Implement row click/keyboard activation to load logical job detail.
- [ ] Implement detail panels: metadata, timeline, provider IDs, circuit list, child provider jobs, error message, aggregated result preview, estimated counts preview.
- [ ] Implement loading, empty, and error states.
- [ ] Ensure table and detail controls have accessible names, focus rings, and keyboard support.
- [ ] Run: `npm --workspace frontend run test -- src/lib/runner-jobs.test.ts src/components/jobs/JobsTab.test.tsx src/components/jobs/JobDetail.test.tsx src/App.test.tsx`

**Acceptance:**

- The Jobs tab does not submit or cancel jobs.
- The UI renders `running 3/25` from `status`, `completed_child_jobs`, and `total_child_jobs`.
- PCSS/API keys are absent from all frontend code and test fixtures.

## Wave 1F: Job Snapshot Map and Result Preview Agent

**Can run in parallel after Wave 1E creates `components/jobs/types.ts`, or can work in a separate worktree with a copied type contract from Wave 0.**

**Skills:** `frontend-patterns`, `accessibility`, `e2e-testing`.

**Files:**

- Create: `frontend/src/components/jobs/JobSnapshotMap.tsx`
- Create: `frontend/src/components/jobs/JobResultPreview.tsx`
- Create: `frontend/src/components/jobs/JobSnapshotMap.test.tsx`
- Create: `frontend/src/components/jobs/JobResultPreview.test.tsx`
- Modify: `frontend/src/components/jobs/JobDetail.tsx`
- Modify: `frontend/src/styles.css`

**Steps:**

- [ ] Write tests for metric selector labels: `1Q EPC`, `2Q EPC`, `Readout`, `RXX EPC`.
- [ ] Implement job-scoped used-qubit/coupling map from stored job snapshot, `used_qubits`, and `used_couplings`.
- [ ] Add a visible label that colors come from the historical submit-time snapshot.
- [ ] Implement result preview that shows one quasi distribution per input circuit.
- [ ] Implement estimated counts preview by multiplying quasi probabilities by requested shots and rounding for display only.
- [ ] Keep canonical API payload as `SamplerResult`-compatible JSON; do not mutate it in UI code.
- [ ] Run: `npm --workspace frontend run test -- src/components/jobs/JobSnapshotMap.test.tsx src/components/jobs/JobResultPreview.test.tsx`

**Acceptance:**

- Historical snapshot labeling is visible in the detail view.
- Metric selection changes colors without changing layout size.
- Long IDs and JSON previews wrap without overlapping adjacent content.

## Wave 1G: Security and Contract Test Agent

**Can run in parallel after Wave 0; final assertions run after Waves 1A-1D are integrated.**

**Skills:** `security-review`, `api-design`, `python-testing`, `e2e-testing`.

**Files:**

- Create: `tests/test_runner_contract_endpoints.py`
- Create: `tests/test_runner_no_secret_leaks.py`
- Modify: `tests/test_backend_app.py` only if app factory parameters need extension.

**Steps:**

- [ ] Write tests proving `POST /api/runner/jobs` returns `401` without key and `403` with wrong key.
- [ ] Write tests proving `POST /api/runner/jobs/{id}/cancel` returns `401` without key and `403` with wrong key.
- [ ] Write tests proving `GET /api/runner/jobs/{id}` and `GET /api/jobs` do not include token-like fields.
- [ ] Write tests proving provider exceptions containing token-looking strings are sanitized.
- [ ] Write tests proving `401` and `403` are not converted into fallback-friendly success bodies.
- [ ] Add a test that recursively scans all JSON responses from runner endpoints for `PCSS_TOKEN`, `PCSS_QAPI_TOKEN`, `DASHBOARD_API_KEY`, and raw configured secret values.
- [ ] Run: `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest tests.test_runner_contract_endpoints tests.test_runner_no_secret_leaks -v`

**Acceptance:**

- Security behavior is specified as executable tests.
- Sanitization tests fail if raw provider exception text leaks.

## Wave 1H: Deployment and Docs Agent

**Can run in parallel after Wave 0; final README updates should wait until endpoint names are stable.**

**Skills:** `docker-patterns`, `deployment-patterns`, `security-review`.

**Files:**

- Modify: `README.md`
- Modify: `Dockerfile` only if dependency installation requires it.
- Modify: `railway.json` only if startup command changes.

**Steps:**

- [ ] Document all Environment Contract variables.
- [ ] Document that `PCSS_TOKEN`/`PCSS_QAPI_TOKEN` and `DASHBOARD_API_KEY` are Railway server variables only.
- [ ] Document that browser code never receives the PCSS token.
- [ ] Document the V1 worker limitation: one in-process sequential worker, not horizontally scalable.
- [ ] Document that PiastQ submissions may take about 4 minutes and benchmark jobs should not be treated as stalled before that window.
- [ ] Document endpoint contract from the spec.
- [ ] Run: `npm run validate`

**Acceptance:**

- Deployment docs match implemented env var names.
- Docs do not instruct users to put secrets into `VITE_` env vars.

## Wave 2: Integration Agent

**Run sequentially after Wave 1 branches are merged.**

**Skills:** `superpowers:subagent-driven-development`, `superpowers:verification-before-completion`, `api-design`, `fastapi-patterns`, `python-testing`, `frontend-patterns`, `security-review`.

**Files:**

- Modify as needed across backend, frontend, tests, docs.

**Steps:**

- [ ] Merge Wave 1 branches in this order: contracts, storage, snapshot/noise, API, worker, frontend jobs UI, snapshot map/result preview, security tests, deployment docs.
- [ ] Resolve import and route registration conflicts in `backend/app.py`.
- [ ] Verify `create_app()` accepts injectable `runner_store`, `runner_settings`, `runner_provider`, and `enable_runner_worker` for tests.
- [ ] Verify existing endpoints still work: `/api/backend-status`, `/api/backend-status/check`, `/api/health`, `/api/benchmarks`, `/api/benchmarks/{benchmark}/run`.
- [ ] Run backend runner tests: `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest tests.test_runner_schemas tests.test_runner_api tests.test_runner_store_in_memory tests.test_runner_worker tests.test_runner_aggregation tests.test_runner_snapshots_noise tests.test_runner_security tests.test_runner_contract_endpoints tests.test_runner_no_secret_leaks -v`
- [ ] Run all backend tests: `$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest discover -s tests -v`
- [ ] Run frontend tests: `npm --workspace frontend run test`
- [ ] Run build: `npm run build`
- [ ] Run schema validation: `npm run validate`
- [ ] If Playwright config exists or was added, run: `npm --workspace frontend run test:e2e`

**Acceptance:**

- All fresh verification commands pass.
- The runner can submit a logical job using fake provider tests.
- The UI can list and inspect a logical job from mocked API responses.
- No API response leaks secrets.
- Existing benchmark dashboard behavior is preserved.

## Recommended Agent Dispatch Prompts

Use these prompts as the starting point for parallel agents. Each agent should work in its own worktree and return: files changed, tests run, test output summary, and blockers.

### Agent 0 Prompt: Contracts Base

Use skills: `superpowers:test-driven-development`, `api-design`, `fastapi-patterns`, `python-testing`, `security-review`.

Implement Wave 0 from `docs/superpowers/plans/2026-06-26-piastq-benchmark-managed-runner-jobs.md`. Do not touch frontend files. Do not add Postgres code. Return the exact schema/model names created and the unittest command output.

### Agent 1 Prompt: Postgres Storage

Use skills: `database-migrations`, `postgres-patterns`, `fastapi-patterns`, `python-testing`, `security-review`.

Implement Wave 1A. Own only `backend/runner/migrations.py`, `backend/runner/migrations/001_managed_runner_jobs.sql`, `backend/runner/postgres_store.py`, `tests/test_runner_store_in_memory.py`, and `backend/requirements.txt`. Use parameterized SQL. Return any API expected from the shared `RunnerStore` protocol that was missing.

### Agent 2 Prompt: Runner API

Use skills: `api-design`, `fastapi-patterns`, `python-testing`, `security-review`.

Implement Wave 1B using `InMemoryRunnerStore` for tests. Own only route/service API files, API tests, and minimal `backend/app.py` router registration. Do not implement real provider execution. Return endpoint list with status codes verified by tests.

### Agent 3 Prompt: Worker and Provider

Use skills: `backend-patterns`, `python-testing`, `error-handling`, `security-review`.

Implement Wave 1C with a fake provider test double and production `PcssSamplerProvider`. Own worker/provider/aggregation files and tests. Do not modify UI. Ensure job execution is sequential and child progress updates after each child result.

### Agent 4 Prompt: Snapshot and Noise

Use skills: `api-design`, `fastapi-patterns`, `python-testing`, `security-review`.

Implement Wave 1D. Own snapshot/noise modules, tests, and route additions. Use `benchmarks/devices/piastq/example.json` as the deterministic test fixture. Include provenance warning in the noise payload.

### Agent 5 Prompt: Jobs UI

Use skills: `frontend-patterns`, `accessibility`, `vite-patterns`, `e2e-testing`.

Implement Wave 1E. Own runner job API client, Jobs table/detail components, component tests, and minimal `App.tsx` tab integration. Do not add browser-side API keys or submit/cancel controls. Keep the existing dashboard style and density.

### Agent 6 Prompt: Snapshot Map and Result Preview UI

Use skills: `frontend-patterns`, `accessibility`, `e2e-testing`.

Implement Wave 1F. Own job snapshot map and result preview components/tests. The map must label colors as historical submit-time snapshot colors. The result preview computes estimated counts for display only.

### Agent 7 Prompt: Security Contract Tests

Use skills: `security-review`, `api-design`, `python-testing`, `e2e-testing`.

Implement Wave 1G. Own only security/contract tests unless a failing test proves a small backend fix is needed. Prioritize missing/wrong API key behavior, no token leaks, and sanitized provider errors.

### Agent 8 Prompt: Deployment Docs

Use skills: `docker-patterns`, `deployment-patterns`, `security-review`.

Implement Wave 1H. Own README/deployment docs and Dockerfile only if necessary. Make sure no docs suggest `VITE_` secrets. Include the 4-minute PiastQ submission note from `AGENTS.md`.

## Risk Controls

- The real PCSS provider may not expose provider job IDs. Store `null` when unavailable and keep the child job otherwise valid.
- The in-process worker is intentionally single-process V1. Do not add distributed locks beyond Postgres `SKIP LOCKED` claim logic.
- QPY and result JSON can be large. Enforce `MAX_RESULT_JSON_BYTES` before storing aggregated results.
- Do not trust benchmark snapshots from clients. All snapshots must be loaded server-side.
- Read-only job endpoints are public by default for the private dashboard deployment. If deployment policy requires protection, add a separate follow-up auth plan rather than mixing it into V1.

## Final Verification Checklist

- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] `npm --workspace frontend run test` passes.
- [ ] `npm run build` passes.
- [ ] `npm run validate` passes.
- [ ] Runner submit/cancel require API key.
- [ ] `GET /api/runner/health` reports unavailable without token.
- [ ] `GET /api/runner/jobs/{id}/result` returns not-ready before success.
- [ ] One logical job can contain multiple circuits.
- [ ] `shots > 200` creates multiple child jobs per circuit by default.
- [ ] Worker runs child jobs sequentially.
- [ ] Aggregated result contains one `quasi_dist` per input circuit.
- [ ] Jobs UI renders table, details, progress, child jobs, circuit metadata, historical snapshot map, and result previews.
- [ ] No response or frontend fixture includes server token values.
- [ ] README documents Railway env vars and V1 limitations.
