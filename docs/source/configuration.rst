Configuration
=============

Pass the values needed by your application directly to ``PiastQClient``. The
examples below use placeholders; replace them in your application with the
values issued for your PiastQ account.

.. code-block:: python

   from cft_piastq import PiastQClient

   client = PiastQClient(
       mode="managed",
       owner="YOUR_OWNER",
       dashboard_api_url="https://dashboard.example",
       dashboard_api_key="YOUR_DASHBOARD_API_KEY",
   )

For direct execution, pass a PCSS token explicitly:

.. code-block:: python

   direct_client = PiastQClient(
       mode="direct",
       token="YOUR_PCSS_TOKEN",
   )

Secrets
-------

Do not commit PCSS tokens or dashboard API keys. Do not include them in
notebooks, screenshots, or shared log output.
