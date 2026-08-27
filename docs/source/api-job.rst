PiastQJob
=========

``PiastQJob`` is the common facade for managed, direct, and fake runs. It
normalizes job identifiers, status, cancellation, results, and counts.

Direct composite ``result()`` returns the Qiskit-compatible aggregate after all
child jobs complete. Its ``counts()`` returns exact summed integer counts.
Managed and fake ``counts()`` can be estimated from quasi-distributions.

Only managed jobs can be reconnected with ``PiastQClient.retrieve_job()``.
Direct composite handles cannot be recovered after the Python process exits.

.. automodule:: cft_piastq.job
   :members: PiastQJob
   :show-inheritance:
