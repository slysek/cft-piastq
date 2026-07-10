Getting started
===============

Installation
------------

Install the base package from PyPI:

.. code-block:: powershell

   python -m pip install cft-piastq

Install an extra only when you need that execution path:

.. code-block:: powershell

   python -m pip install "cft-piastq[direct]"  # PCSS/AQT provider integration
   python -m pip install "cft-piastq[fake]"    # local Qiskit Aer simulation

For development from a repository checkout, use ``python -m pip install -e
".[dev]"``. End users installing from PyPI do not need an editable install.

Run a local circuit
-------------------

The smallest end-to-end example uses fake mode. It requires the ``fake`` extra
and does not contact a dashboard.

.. code-block:: python

   from qiskit import QuantumCircuit

   from cft_piastq import PiastQClient, PiastQSampler

   circuit = QuantumCircuit(2, 2, name="bell")
   circuit.h(0)
   circuit.cx(0, 1)
   circuit.measure([0, 1], [0, 1])

   client = PiastQClient(mode="fake")
   sampler = PiastQSampler(client.backend)
   job = sampler.run(circuit, shots=1024)

   print(job.status())
   print(job.counts()[0])

``PiastQClient`` chooses a backend. ``PiastQSampler`` submits one or more
``QuantumCircuit`` objects. ``PiastQJob`` gives access to status, results,
estimated counts, and cancellation.
