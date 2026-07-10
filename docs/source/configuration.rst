Configuration
=============

Pass configuration directly to ``PiastQClient`` or set environment variables.
Constructor arguments take precedence over environment values.

.. list-table::
   :header-rows: 1

   * - Variable
     - Purpose
   * - ``CFT_PIASTQ_MODE``
     - Requested mode: ``auto``, ``managed``, ``direct``, or ``fake``.
   * - ``CFT_PIASTQ_OWNER``
     - Owner recorded for managed job submissions.
   * - ``PCSS_TOKEN``
     - PCSS token for direct execution.
   * - ``PCSS_QAPI_TOKEN``
     - Alternative PCSS token variable.
   * - ``CFT_PIASTQ_DASHBOARD_API_URL``
     - Base URL of the dashboard API.
   * - ``CFT_PIASTQ_DASHBOARD_API_KEY``
     - API key for protected dashboard operations.
   * - ``CFT_PIASTQ_REGISTRY_PATH``
     - Local SQLite registry location for direct jobs.
   * - ``CFT_PIASTQ_VERBOSE``
     - Boolean-like value controlling the resolved-mode message.

For example, configure a managed process without placing secrets in code:

.. code-block:: powershell

   $env:CFT_PIASTQ_MODE = "managed"
   $env:CFT_PIASTQ_OWNER = "researcher"
   $env:CFT_PIASTQ_DASHBOARD_API_URL = "https://dashboard.example"

Secrets
-------

Do not commit PCSS tokens or dashboard API keys. Read them from environment
variables or a secret manager. Do not include them in notebooks, screenshots, or
shared log output.
