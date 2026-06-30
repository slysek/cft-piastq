cft-piastq
==========

``cft-piastq`` is a Python package imported as ``cft_piastq``. It provides
Qiskit-compatible facades for PiastQ managed dashboard jobs, direct PCSS/AQT
execution handles, and local fake execution handles.

The documentation is built with Sphinx and the Furo theme, matching the
documentation style used by the Qiskit AQT provider: a searchable content area,
left-hand navigation, right-hand page contents, automatic API pages, and
light/dark presentation.

.. toctree::
   :maxdepth: 2
   :caption: User guide

   getting-started
   execution-modes
   managed-dashboard
   configuration
   results
   deployment

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api

Project scope
-------------

The package keeps Qiskit as the source of circuits and primitive result types.
It adds the operational layer needed by PiastQ users:

* resolving the execution mode,
* submitting managed jobs through a dashboard runner,
* keeping local PCSS credentials out of managed dashboard submissions,
* serializing Qiskit circuits as QPY payloads,
* reconstructing ``qiskit.primitives.SamplerResult`` objects from dashboard
  JSON,
* exposing estimated counts for display and analysis.

Current API surface
-------------------

The stable public entry points are:

* ``PiastQClient`` for configuration and backend selection,
* ``PiastQSampler`` for managed dashboard submissions,
* ``PiastQJob`` for status, cancellation, result retrieval, and counts,
* ``DashboardClient`` for direct dashboard HTTP access,
* helpers for QPY serialization, status normalization, result reconstruction,
  and secret redaction.
