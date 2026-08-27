Results and counts
==================

``job.result()`` returns a Qiskit-compatible ``SamplerResult``. Its first quasi
distribution is available as ``result.quasi_dists[0]``.

.. code-block:: python

   result = job.result(timeout=1800)
   first_distribution = result.quasi_dists[0]
   first_counts = job.counts()[0]

Direct results
--------------

For a direct composite job, each child's result is converted back to validated
integer measurements. Those integer counts are summed before probabilities are
reconstructed. Consequently, ``result()`` is one logical aggregate and
``counts()`` returns exact combined counts. Child probabilities are never
averaged.

For example, a 2,000-shot logical run produces counts whose values sum exactly
to 2,000 after all ten 200-shot children complete.

Managed and fake results
------------------------

Managed and fake adapters can provide only quasi-distributions plus a logical
shot count. In those modes, ``counts()`` returns legacy estimated counts by
multiplying probabilities by shots and rounding. These are estimates, not raw
provider measurement memory.

QPY payloads
------------

Managed submission serializes Qiskit circuits as QPY data. Normal callers do
not need to handle that payload directly. Low-level helpers live in
``cft_piastq.serialization``.
