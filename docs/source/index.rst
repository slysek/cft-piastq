cft-piastq
==========

``cft-piastq`` is a Qiskit-compatible client for PiastQ execution. Use it to
submit a circuit through a managed dashboard, run it directly with PCSS/AQT, or
simulate it locally with Qiskit Aer.

Install the package from PyPI:

.. code-block:: powershell

   python -m pip install cft-piastq

For a local smoke test, install the fake-execution extra:

.. code-block:: powershell

   python -m pip install "cft-piastq[fake]"

The package is imported as ``cft_piastq``.

.. toctree::
   :maxdepth: 2
   :caption: User guide

   getting-started
   execution-modes
   configuration
   managed-dashboard
   results
   deployment

.. toctree::
   :maxdepth: 2
   :caption: API reference

   api
