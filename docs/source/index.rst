cft-piastq
==========

``cft-piastq`` is a Qiskit-compatible client for managed PiastQ execution,
direct PCSS/AQT access, and local Aer simulation. The package is imported as
``cft_piastq``.

Clone the repository and install an execution extra with Python 3.11 or 3.12:

.. code-block:: powershell

   git clone https://github.com/slysek/cft-piastq.git
   cd cft-piastq
   python -m pip install -e ".[direct]"

Use ``.[fake]`` for local simulation or ``.[dev]`` for development tools.

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
