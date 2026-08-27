Execution modes
===============

Choose a mode with ``PiastQClient(mode=...)``.

.. list-table::
   :header-rows: 1
   :widths: 12 25 40 23

   * - Mode
     - Requirements
     - Execution
     - Counts
   * - ``managed``
     - Dashboard URL, owner, and dashboard API access when required
     - One logical job submission through the dashboard API; splitting and
       aggregation belong to the separate runner/backend
     - Estimated when reconstructed from quasi-distributions
   * - ``direct``
     - PCSS token only and ``.[direct]``
     - Sequential PCSS/AQT child jobs
     - Exact combined counts
   * - ``fake``
     - ``.[fake]``
     - Local Qiskit Aer simulation
     - Estimated from quasi-distributions
   * - ``auto``
     - Dashboard configuration and/or PCSS token
     - Managed after a successful dashboard health check; otherwise direct
       when a token is available
     - Depends on the selected mode

``auto`` never selects fake mode. Dashboard authentication failures are
reported instead of silently falling back to direct execution.

Direct composite jobs
---------------------

Direct mode needs a PCSS token only. It does not need a dashboard URL or
dashboard API key. ``shots`` is the total logical count. Since every child is
limited to 200 shots, **2,000 shots** become **10 sequential PCSS jobs** of
**200 shots**. The library shows one logical progress bar when enabled. Set
``with_progress_bar=False`` in sampler or run options to hide it.

Integer counts from all children are summed before the final probabilities are
reconstructed. The public job returns one Qiskit-compatible aggregate and exact
combined counts, not an average of child results.

Direct composite state is process-local and cannot be recovered after the
Python process exits. Keep the process alive until ``result()`` completes.

Managed jobs
------------

Managed mode sends QPY circuit data and logical metadata through the dashboard
API. This library does not apply its direct 200-shot splitter to managed jobs.
Any managed split and aggregation is owned by the separately deployed PiastQ
runner/backend. ``PiastQClient.retrieve_job()`` supports managed jobs only.

Fake jobs
---------

Fake mode uses local Aer and makes no dashboard request by default. A
dashboard-provided noise snapshot can be selected explicitly for development;
it is not a calibrated hardware twin.
