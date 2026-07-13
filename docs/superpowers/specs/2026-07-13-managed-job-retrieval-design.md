# Managed job retrieval by job ID

## Goal

Allow a user to reconnect to an existing managed dashboard job using only its
public job identifier. The retrieved job must support the same status, result,
and cancellation operations as a managed job returned by
`PiastQSampler.run()`.

## Public API

`PiastQClient` gains one method:

```python
job = client.retrieve_job("server-job-id")

status = job.status()
result = job.result(timeout=120)
cancellation_status = job.cancel()
```

The method returns the existing `PiastQJob` facade. It is available only when
the client's resolved execution mode is `managed`. Calling it on a client
resolved to `direct` or `fake` raises a public PiastQ configuration error.

`job_id` must be a non-empty string after trimming whitespace. An invalid
value is rejected before an HTTP request is sent.

## Retrieval and data flow

`retrieve_job(job_id)` immediately calls
`GET /api/runner/jobs/{job_id}` through the configured `DashboardClient`. This
eager read verifies that the job exists and is accessible. A successful
response is validated as a JSON object and used to create a `ManagedJobHandle`
with the requested identifier and existing dashboard client.

The eager response does not make later state stale. Every explicit `status()`
call reads the current job state from the dashboard. `result()` keeps the
existing managed-job behavior: it polls the job endpoint until the job reaches
a terminal state and, after success, fetches
`GET /api/runner/jobs/{job_id}/result` and converts the payload to the existing
Qiskit-compatible `SamplerResult`.

`cancel()` keeps the existing behavior and calls
`POST /api/runner/jobs/{job_id}/cancel`. The dashboard API key remains required
for this protected operation.

## Compatibility and scope

The existing `PiastQJob.counts()` method remains unchanged. This feature does
not add special handling for a dashboard `counts` field and does not remove or
alter the current counts API.

Managed jobs created by `PiastQSampler.run()` continue to work unchanged.
Direct and fake job handles are not retrievable by identifier in this feature.
No provider-job reconstruction or local registry lookup is introduced.

## Error handling

- An empty or non-string `job_id` raises `PiastQConfigurationError` without an
  HTTP request.
- Dashboard authentication failures continue to raise `DashboardAuthError`.
- Missing jobs, other dashboard failures, and malformed job responses raise
  `ManagedJobError` with the existing secret-redaction behavior.
- Failed, cancelled, stale, and timed-out result polling retains the current
  `ManagedJobHandle` behavior and public exceptions.

## Testing

Tests will prove that:

- a managed client eagerly retrieves a job and returns `PiastQJob`;
- the exact requested identifier is URL-escaped and sent to the job endpoint;
- the retrieved job can read fresh status, wait for and return a result, and
  request cancellation;
- an already completed job can return its result;
- invalid identifiers fail before network access;
- missing and unauthorized jobs preserve the public dashboard exceptions;
- direct and fake clients reject `retrieve_job()`;
- existing managed submission and `counts()` tests continue to pass unchanged.

The managed-dashboard documentation will include a reconnect example using
`retrieve_job(job_id)` followed by `status()`, `result()`, and `cancel()`.
