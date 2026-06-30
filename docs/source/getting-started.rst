Getting Started
===============

Installation
------------

Install the package in editable mode while developing:

.. code-block:: powershell

   python -m pip install -e .[dev]

Optional extras are separated by execution path:

.. code-block:: powershell

   python -m pip install -e .[direct]
   python -m pip install -e .[fake]

``direct`` installs the local PCSS/AQT dependencies. ``fake`` installs the local
simulation dependencies.

Managed sampler example
-----------------------

Use ``PiastQSampler`` when the job should go through the PiastQ dashboard
runner. The raw ``qiskit_aqt_provider.primitives.AQTSampler`` is an AQT
provider sampler and does not know about the PiastQ managed dashboard API.

.. code-block:: python

   from qiskit import QuantumCircuit

   from cft_piastq import PiastQClient, PiastQSampler

   circuit = QuantumCircuit(2, 2, name="bell")
   circuit.h(0)
   circuit.cx(0, 1)
   circuit.measure([0, 1], [0, 1])

   client = PiastQClient(
       owner="szymo",
       mode="managed",
       dashboard_api_url="https://piastq-dashboard.example",
       dashboard_api_key="dashboard-key",
       verbose=False,
   )

   sampler = PiastQSampler(
       client.backend,
       options={"cft_job_name": "Bell smoke test"},
   )

   job = sampler.run(circuits=[circuit], shots=200)
   result = job.result()
   counts = job.counts(num_bits=2)

The managed path serializes circuits as QPY, sends them to the dashboard runner,
waits for completion, and rebuilds a Qiskit ``SamplerResult`` from dashboard
JSON.

Sampler options
---------------

``PiastQSamplerOptions`` behaves like a mutable mapping and also supports
attribute-style assignment:

.. code-block:: python

   sampler = PiastQSampler(client.backend)
   sampler.options.cft_job_name = "Bell smoke test"
   sampler.options.cft_description = "2Q Bell state smoke test"

Options with the ``cft_`` prefix are interpreted by ``cft-piastq``. Provider
options can still be passed, but the current managed implementation only submits
the CFT-specific metadata to the dashboard.
