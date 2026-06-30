# cft-piastq

`cft-piastq` is a Python package imported as `cft_piastq`. It will provide
Qiskit-compatible facades for PiastQ managed dashboard jobs, direct PCSS/AQT
execution, and local fake execution.

The managed path is available through the public `PiastQClient`,
`PiastQSampler`, and `PiastQJob` facades. Create a client, take its resolved
backend, pass that backend to `PiastQSampler`, and `sampler.run(...)` submits a
QPY payload to the dashboard runner.

## Installation

```powershell
python -m pip install -e .[dev]
```

Optional extras planned for later waves:

```powershell
python -m pip install -e .[direct]
python -m pip install -e .[fake]
```

## Modes

- `managed`: submit QPY payloads to a dashboard runner API.
- `direct`: run through local PCSS/AQT credentials and adapters.
- `fake`: run locally through an Aer-backed simulator adapter.
- `auto`: prefer managed mode when available and fall back only under explicit
  safe rules.

## Managed Sampler

Use `PiastQSampler` when you want jobs to go through the PiastQ dashboard. The
raw `qiskit_aqt_provider.primitives.AQTSampler` is a provider sampler and does
not know about the managed dashboard API.

```python
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
```

## Security Model

PCSS tokens and dashboard API keys are read from constructor arguments or
environment variables. The package must not send PCSS tokens to the dashboard,
persist secrets in SQLite, or expose raw secret values in public exceptions.
