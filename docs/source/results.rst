Results and counts
==================

``job.result()`` returns a Qiskit-compatible ``SamplerResult``. Use it when you
need quasi probabilities or result metadata.

.. code-block:: python

   result = job.result(timeout=120)
   first_distribution = result.quasi_dists[0]

``job.counts()`` is a convenience view for display and simple analysis. It
multiplies quasi probabilities by the requested shot count and rounds to
estimated integer counts.

.. code-block:: python

   counts = job.counts()
   first_counts = counts[0]

The returned counts are estimates, not raw provider measurement memory. Negative
quasi probabilities are treated as zero before the estimate is calculated.

QPY payloads
------------

The package serializes Qiskit circuits as QPY data before a managed submission.
This is an implementation detail for normal use. If you need to inspect or
transport QPY yourself, use the helpers in ``cft_piastq.serialization`` from the
module reference.
