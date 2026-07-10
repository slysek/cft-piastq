Managed dashboard jobs
======================

Managed mode submits a Qiskit circuit to the PiastQ dashboard runner. It needs
an owner and a dashboard URL. The dashboard API key is optional for submission,
but protected operations such as cancellation may require it.

.. code-block:: python

   from qiskit import QuantumCircuit

   from cft_piastq import PiastQClient, PiastQSampler

   circuit = QuantumCircuit(2, 2, name="bell")
   circuit.h(0)
   circuit.cx(0, 1)
   circuit.measure([0, 1], [0, 1])

   client = PiastQClient(
       mode="managed",
       owner="YOUR_OWNER",
       dashboard_api_url="https://dashboard.example",
       dashboard_api_key="YOUR_DASHBOARD_API_KEY",
   )
   sampler = PiastQSampler(
       client.backend,
       options={"cft_job_name": "Bell test"},
   )
   job = sampler.run(circuit, shots=1024)

   result = job.result(timeout=120)
   counts = job.counts()

The payload contains QPY circuit data and job metadata. It never contains a
local PCSS token.

Working with a job
------------------

``PiastQJob`` exposes a small, consistent interface:

.. code-block:: python

   job_id = job.job_id()
   status = job.status()
   result = job.result(timeout=120)
   estimated_counts = job.counts()
   cancellation_status = job.cancel()

Use a positive ``poll_interval`` when waiting for a managed result. A failed or
cancelled managed job raises a public PiastQ exception when its result is read.
