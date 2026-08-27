Configuration
=============

Pass values directly to ``PiastQClient`` or configure the process environment.
Explicit arguments take precedence over environment values.

Direct
------

Direct execution requires a PCSS token only:

.. code-block:: python

   import os

   from cft_piastq import PiastQClient

   direct_client = PiastQClient(
       mode="direct",
       token=os.environ["PCSS_TOKEN"],
   )

``PCSS_TOKEN`` and ``PCSS_QAPI_TOKEN`` are the supported token environment
variables. Direct mode does not require a dashboard URL, key, or owner.

Managed
-------

Managed execution requires an owner and dashboard URL. A dashboard API key can
be required for protected operations. Read secrets from the environment:

.. code-block:: python

   import os

   from cft_piastq import PiastQClient

   managed_client = PiastQClient(
       mode="managed",
       owner=os.environ["CFT_PIASTQ_OWNER"],
       dashboard_api_url=os.environ["CFT_PIASTQ_DASHBOARD_API_URL"],
       dashboard_api_key=os.environ.get("CFT_PIASTQ_DASHBOARD_API_KEY"),
   )

Environment reference
---------------------

``CFT_PIASTQ_MODE`` accepts ``auto``, ``managed``, ``direct``, or ``fake``.
Other settings are ``CFT_PIASTQ_OWNER``, ``CFT_PIASTQ_DASHBOARD_API_URL``,
``CFT_PIASTQ_DASHBOARD_API_KEY``, ``CFT_PIASTQ_REGISTRY_PATH``, and
``CFT_PIASTQ_VERBOSE``.

Secrets
-------

Never commit PCSS tokens or dashboard API keys. Do not include them in source,
notebooks, screenshots, logs, issue reports, or saved notebook output. Rotate
any credential that has been exposed.
