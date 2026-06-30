Results and Serialization
=========================

QPY circuit payloads
--------------------

The package uses QPY as the portable format for Qiskit circuits. Payloads are
base64 encoded so they can be carried in dashboard JSON.

.. code-block:: python

   from qiskit import QuantumCircuit

   from cft_piastq.serialization import (
       circuit_metadata,
       circuit_to_qpy_base64,
       qpy_base64_to_circuit,
   )

   circuit = QuantumCircuit(2, 2, name="bell")
   circuit.h(0)
   circuit.cx(0, 1)
   circuit.measure([0, 1], [0, 1])

   payload = circuit_to_qpy_base64(circuit)
   restored = qpy_base64_to_circuit(payload)
   metadata = circuit_metadata(circuit, index=0)

``circuit_metadata()`` returns JSON-safe details used by the dashboard, including
circuit name, qubit and classical bit counts, depth, operation counts, used
qubits, and used two-qubit couplings.

Sampler results
---------------

Dashboard JSON can be reconstructed as a Qiskit ``SamplerResult``:

.. code-block:: python

   from cft_piastq.results import sampler_result_from_json

   payload = {
       "shots": 200,
       "quasi_dists": [{"0": 0.5, "3": 0.5}],
       "metadata": [{"circuit_index": 0, "circuit_name": "bell"}],
   }

   result = sampler_result_from_json(payload)

Estimated counts
----------------

``estimated_counts_from_result()`` converts quasi distributions to display-ready
count estimates:

.. code-block:: python

   from cft_piastq.counts import estimated_counts_from_result

   counts = estimated_counts_from_result(result, shots=200, num_bits=2)

The returned values are estimates derived from quasi probabilities. They are not
raw provider counts.

Status normalization
--------------------

Provider and dashboard status names are normalized to a shared literal set:

.. code-block:: python

   from cft_piastq.status import normalize_job_status

   assert normalize_job_status("DONE") == "succeeded"
   assert normalize_job_status("in-progress") == "running"
   assert normalize_job_status("something-new") == "unknown"
