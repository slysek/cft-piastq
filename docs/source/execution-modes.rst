Execution Modes
===============

``PiastQClient`` accepts four requested modes: ``auto``, ``managed``,
``direct``, and ``fake``. After initialization, ``client.execution_mode`` is one
of the resolved modes: ``managed``, ``direct``, or ``fake``.

Mode summary
------------

.. list-table::
   :header-rows: 1

   * - Mode
     - Behavior
   * - ``managed``
     - Requires a dashboard API URL. The client checks runner health and uses a
       managed dashboard backend.
   * - ``direct``
     - Requires a local PCSS token. The client returns a direct PCSS/AQT backend
       handle.
   * - ``fake``
     - Returns a local fake backend handle. It can optionally fetch a noise
       model from the dashboard.
   * - ``auto``
     - Prefers ``managed`` when a configured dashboard is healthy. If the
       dashboard is unavailable, it falls back to ``direct`` only when a local
       PCSS token is available.

Managed mode
------------

Use ``managed`` when jobs should be submitted through the dashboard runner:

.. code-block:: python

   client = PiastQClient(
       owner="szymo",
       mode="managed",
       dashboard_api_url="https://piastq-dashboard.example",
       dashboard_api_key="dashboard-key",
       verbose=False,
   )

The client calls ``GET /api/runner/health`` before the backend is considered
available. Dashboard authorization errors are treated as hard failures.

Direct mode
-----------

Use ``direct`` when local PCSS/AQT credentials should drive execution:

.. code-block:: python

   client = PiastQClient(
       owner="szymo",
       mode="direct",
       token="local-pcss-token",
       verbose=False,
   )

If no token is provided through the constructor or environment, the client raises
``DirectModeUnavailableError``.

Fake mode
---------

Use ``fake`` for tests, demos, and local flow validation:

.. code-block:: python

   client = PiastQClient(mode="fake", verbose=False)

To attach the latest dashboard-provided noise model:

.. code-block:: python

   client = PiastQClient(
       owner="szymo",
       mode="fake",
       use_backend_noise=True,
       dashboard_api_url="https://piastq-dashboard.example",
       dashboard_api_key="dashboard-key",
       verbose=False,
   )

The current public fake backend is a handle. Full fake sampler execution is a
future adapter layer.
