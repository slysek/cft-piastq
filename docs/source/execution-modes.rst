Execution modes
===============

Choose a mode with ``PiastQClient(mode=...)``. The mode describes where the
circuit runs, not how the circuit is written.

.. list-table::
   :header-rows: 1

   * - Mode
     - Requirements
     - What it does
   * - ``managed``
     - Dashboard URL and job owner
     - Submits QPY circuit data to the PiastQ dashboard runner.
   * - ``direct``
     - PCSS token and the ``direct`` extra
     - Runs through the local PCSS/AQT provider integration.
   * - ``fake``
     - The ``fake`` extra
     - Runs a local Qiskit Aer simulation.
   * - ``auto``
     - Dashboard configuration, a PCSS token, or both
     - Uses managed mode when available; otherwise it may use direct mode.

``auto`` never falls back to fake mode. A dashboard authentication error is
reported instead of silently changing to direct execution.

Managed
-------

Use managed mode for work submitted through the dashboard:

.. code-block:: python

   import os

   from cft_piastq import PiastQClient

   client = PiastQClient(
       mode="managed",
       owner=os.environ["CFT_PIASTQ_OWNER"],
       dashboard_api_url=os.environ["CFT_PIASTQ_DASHBOARD_API_URL"],
       dashboard_api_key=os.environ.get("CFT_PIASTQ_DASHBOARD_API_KEY"),
   )

Direct
------

Use direct mode when a local PCSS token should be used:

.. code-block:: python

   import os

   from cft_piastq import PiastQClient

   client = PiastQClient(mode="direct", token=os.environ["PCSS_TOKEN"])

Fake
----

Use fake mode for local development and tests:

.. code-block:: python

   from cft_piastq import PiastQClient

   client = PiastQClient(mode="fake")

To use a dashboard-provided noise snapshot, call
``client.fake_backend(use_backend_noise=True)`` with a dashboard URL configured.
This is useful for simulation, not hardware calibration.
