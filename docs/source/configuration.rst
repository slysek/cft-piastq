Configuration
=============

Constructor arguments have priority over environment variables. Empty strings
are treated as missing values.

Client arguments
----------------

.. code-block:: python

   client = PiastQClient(
       mode="auto",
       owner="szymo",
       token="local-pcss-token",
       dashboard_api_url="https://piastq-dashboard.example",
       dashboard_api_key="dashboard-key",
       registry_path="jobs.sqlite3",
       verbose=False,
       use_backend_noise=False,
   )

Environment variables
---------------------

.. list-table::
   :header-rows: 1

   * - Variable
     - Meaning
   * - ``CFT_PIASTQ_OWNER``
     - Dashboard job owner. Can also be passed as ``owner=``.
   * - ``CFT_PIASTQ_MODE``
     - ``auto``, ``managed``, ``direct``, or ``fake``. Defaults to ``auto``.
   * - ``PCSS_TOKEN``
     - Local PCSS token for ``direct`` mode.
   * - ``PCSS_QAPI_TOKEN``
     - Alternate local PCSS token variable.
   * - ``CFT_PIASTQ_DASHBOARD_API_URL``
     - Base dashboard API URL.
   * - ``CFT_PIASTQ_DASHBOARD_API_KEY``
     - Dashboard API key.
   * - ``CFT_PIASTQ_VERBOSE``
     - Boolean-like value, for example ``true``, ``false``, ``1``, or ``0``.
   * - ``CFT_PIASTQ_REGISTRY_PATH``
     - Local direct-mode job registry path.

Boolean values
--------------

The configuration parser accepts common environment-style boolean strings:

.. code-block:: python

   from cft_piastq.config import parse_bool

   assert parse_bool("true") is True
   assert parse_bool("0") is False

Invalid values raise ``PiastQConfigurationError``.
