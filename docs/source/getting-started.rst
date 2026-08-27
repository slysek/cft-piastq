Getting started
===============

Clone and install
-----------------

Use Python 3.11 or 3.12. Start from the GitHub checkout:

.. code-block:: powershell

   git clone https://github.com/slysek/cft-piastq.git
   cd cft-piastq
   python -m pip install -e ".[direct]"

Install a different extra when needed:

.. code-block:: powershell

   python -m pip install -e ".[fake]"
   python -m pip install -e ".[dev]"

Run a direct Bell circuit
-------------------------

Direct mode needs only a PCSS token. This example submits one logical run;
the library handles the provider's per-job shot limit.

.. code-block:: python

   import os

   from qiskit import QuantumCircuit

   from cft_piastq import PiastQClient, PiastQSampler

   bell = QuantumCircuit(2, 2, name="bell")
   bell.h(0)
   bell.cx(0, 1)
   bell.measure([0, 1], [0, 1])

   client = PiastQClient(mode="direct", token=os.environ["PCSS_TOKEN"])
   sampler = PiastQSampler(client.backend)
   job = sampler.run(bell, shots=2000)

   result = job.result(timeout=1800)
   counts = job.counts()[0]
   assert sum(counts.values()) == 2000

For a token-safe interactive version,
:download:`download the direct Bell notebook <../../examples/direct_bell.ipynb>`.
It reads ``PCSS_TOKEN`` or prompts without saving notebook output.

Object roles
------------

``PiastQClient`` selects a backend. ``PiastQSampler`` accepts one or more
``QuantumCircuit`` objects and returns ``PiastQJob``. The job exposes normalized
status, cancellation, a Qiskit-compatible result, and counts.
