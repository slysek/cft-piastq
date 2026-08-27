Managed dashboard jobs
======================

Managed mode submits a Qiskit circuit to the PiastQ dashboard runner. It needs
an owner and a dashboard URL. The dashboard API key is optional for submission,
but protected operations such as cancellation may require it.

.. code-block:: python

   import os

   from qiskit import QuantumCircuit

   from cft_piastq import PiastQClient, PiastQSampler

   circuit = QuantumCircuit(2, 2, name="bell")
   circuit.h(0)
   circuit.cx(0, 1)
   circuit.measure([0, 1], [0, 1])

   client = PiastQClient(
       mode="managed",
       owner=os.environ["CFT_PIASTQ_OWNER"],
       dashboard_api_url=os.environ["CFT_PIASTQ_DASHBOARD_API_URL"],
       dashboard_api_key=os.environ.get("CFT_PIASTQ_DASHBOARD_API_KEY"),
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

Reconnect by job ID
-------------------

Use ``retrieve_job()`` when the job was submitted in an earlier process or
notebook session. Retrieval immediately verifies that the managed job exists
and is accessible.

.. code-block:: python

   import os

   from cft_piastq import PiastQClient

   client = PiastQClient(
       mode="managed",
       owner=os.environ["CFT_PIASTQ_OWNER"],
       dashboard_api_url=os.environ["CFT_PIASTQ_DASHBOARD_API_URL"],
       dashboard_api_key=os.environ.get("CFT_PIASTQ_DASHBOARD_API_KEY"),
   )
   job = client.retrieve_job("YOUR_MANAGED_JOB_ID")

   status = job.status()
   result = job.result(timeout=120)

   # Protected cancellation requires the dashboard API key.
   cancellation_status = job.cancel()

Only managed dashboard jobs can be retrieved by identifier. Direct PCSS and
local fake jobs cannot be reconstructed with ``retrieve_job()``.
