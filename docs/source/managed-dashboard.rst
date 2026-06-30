Managed Dashboard
=================

Managed execution uses the dashboard runner API. The local package is
responsible for Qiskit-facing ergonomics, circuit serialization, status
normalization, result reconstruction, and secret-safe error handling.

Dashboard client
----------------

The lower-level HTTP wrapper is ``DashboardClient``:

.. code-block:: python

   from cft_piastq.http import DashboardClient

   dashboard = DashboardClient(
       "https://piastq-dashboard.example",
       api_key="dashboard-key",
   )

   health = dashboard.health()
   job = dashboard.submit_job({"shots": 200})
   fresh_status = dashboard.get_job(job["id"])
   result = dashboard.get_result(job["id"])
   dashboard.cancel_job(job["id"])
   dashboard.close()

Endpoints
---------

.. list-table::
   :header-rows: 1

   * - Method
     - Path
     - Python method
   * - ``GET``
     - ``/api/runner/health``
     - ``health()``
   * - ``POST``
     - ``/api/runner/jobs``
     - ``submit_job(payload)``
   * - ``GET``
     - ``/api/runner/jobs/{id}``
     - ``get_job(server_job_id)``
   * - ``GET``
     - ``/api/runner/jobs/{id}/result``
     - ``get_result(server_job_id)``
   * - ``POST``
     - ``/api/runner/jobs/{id}/cancel``
     - ``cancel_job(server_job_id)``
   * - ``GET``
     - ``/api/noise-model/latest``
     - ``get_noise_model()``

Job lifecycle
-------------

``PiastQSampler.run()`` submits circuits and returns ``PiastQJob``. A job can
read status, request cancellation, wait for a result, and derive estimated
counts:

.. code-block:: python

   job = sampler.run(circuits=[circuit], shots=200)

   job_id = job.job_id()
   status = job.status()
   result = job.result(timeout=120, poll_interval=2)
   counts = job.counts(num_bits=2)

``result()`` polls until the normalized status is ``succeeded``. ``failed``,
``cancelled``, and ``stale`` are terminal failure statuses.

Security boundary
-----------------

Managed submissions must not send local PCSS tokens to the dashboard. Dashboard
operations use ``CFT_PIASTQ_DASHBOARD_API_KEY`` or the explicit
``dashboard_api_key`` constructor argument when authentication is required.

HTTP errors and public exception messages are passed through secret redaction so
that logs remain useful without exposing credentials.
