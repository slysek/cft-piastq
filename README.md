# cft-piastq

`cft-piastq` is imported as `cft_piastq`. It provides a small
Qiskit-compatible facade for PiastQ managed dashboard jobs, local direct
PCSS/AQT execution, and local fake execution for development workflows.

The main public types are:

- `PiastQClient`: resolves the execution mode and holds the backend handle.
- `PiastQSampler`: accepts Qiskit `QuantumCircuit` objects and submits or runs
  them through the selected backend.
- `PiastQJob`: exposes `job_id()`, `status()`, `result()`, `counts()`, and
  `cancel()` across managed, direct, and fake jobs.

## Installation

Editable development install:

```powershell
python -m pip install -e .[dev]
```

Runtime install:

```powershell
python -m pip install cft-piastq
```

Optional execution extras:

```powershell
python -m pip install "cft-piastq[direct]"
python -m pip install "cft-piastq[fake]"
```

`direct` installs PCSS/AQT provider packages. `fake` installs Qiskit Aer.

## Managed Mode

Managed mode submits QPY payloads to the PiastQ dashboard runner API. The
dashboard URL is required; the dashboard API key is optional for submission but
required by endpoints that need authorization, such as cancellation.

```python
from qiskit import QuantumCircuit

from cft_piastq import PiastQClient, PiastQSampler

circuit = QuantumCircuit(2, 2, name="bell")
circuit.h(0)
circuit.cx(0, 1)
circuit.measure([0, 1], [0, 1])

client = PiastQClient(
    mode="managed",
    owner="local-user",
    dashboard_api_url="https://dashboard.example",
    dashboard_api_key=None,
)
sampler = PiastQSampler(
    client.backend,
    options={"cft_job_name": "managed-bell"},
)

job = sampler.run(circuit, shots=1024)
counts = job.counts()[0]
```

## Auto Mode

Auto mode prefers managed execution when a dashboard URL is configured and the
runner health check succeeds. If the dashboard is unavailable, auto mode falls
back to direct execution only when a PCSS token is available. Authentication
errors from the dashboard do not fall back to direct mode. Auto mode never falls
back to fake execution.

```python
import os

from cft_piastq import PiastQClient

client = PiastQClient(
    mode="auto",
    owner="local-user",
    token=os.environ.get("PCSS_TOKEN"),
    dashboard_api_url=os.environ.get("CFT_PIASTQ_DASHBOARD_API_URL"),
    dashboard_api_key=os.environ.get("CFT_PIASTQ_DASHBOARD_API_KEY"),
)
resolved_mode = client.execution_mode
```

## Direct Mode

Direct mode uses the local PCSS token and lazy-loads the optional PCSS/AQT
packages. It does not require a dashboard. When a dashboard URL is also
configured, direct mode can report best-effort audit events, but PCSS tokens are
not sent to the dashboard and are not persisted in the SQLite registry.

```python
import os

from qiskit import QuantumCircuit

from cft_piastq import PiastQClient, PiastQSampler

circuit = QuantumCircuit(2, 2, name="bell")
circuit.h(0)
circuit.cx(0, 1)
circuit.measure([0, 1], [0, 1])

client = PiastQClient(
    mode="direct",
    owner="local-user",
    token=os.environ["PCSS_TOKEN"],
)
sampler = PiastQSampler(
    client.backend,
    options={"cft_job_name": "direct-bell"},
)

job = sampler.run(circuit, shots=1024)
counts = job.counts()[0]
```

The default direct registry path is under the platform user cache directory.
Set `CFT_PIASTQ_REGISTRY_PATH` or pass `registry_path=` to choose another
SQLite file.

## Fake Mode

Fake mode runs locally through Qiskit Aer. By default it makes no dashboard
calls and uses no dashboard noise data.

```python
from qiskit import QuantumCircuit

from cft_piastq import PiastQClient, PiastQSampler

circuit = QuantumCircuit(2, 2, name="bell")
circuit.h(0)
circuit.cx(0, 1)
circuit.measure([0, 1], [0, 1])

client = PiastQClient(mode="fake", owner="local-user")
backend = client.fake_backend(use_backend_noise=False)
sampler = PiastQSampler(
    backend,
    options={"cft_job_name": "fake-bell"},
)

job = sampler.run(circuit, shots=1024)
counts = job.counts()[0]
```

`client.fake_backend(use_backend_noise=True)` reads
`GET /api/noise-model/latest` from the dashboard and converts supported payloads
into an Aer noise model. Dashboard-derived noise is a simulation convenience for
development and demonstrations; it is not a calibrated digital twin of the
hardware.

## Options

`PiastQSampler` accepts constructor options and run options. Keys beginning with
`cft_` are consumed by the package and are not passed to provider adapters.
Other keys are preserved for direct or fake provider adapters.

Common CFT options:

- `cft_job_name`: display name. If omitted, a single circuit's name is used,
  otherwise `Untitled job`.
- `cft_description`: optional job description for managed and direct audit
  metadata.
- `cft_fake_simulator_adapter`: test hook for fake execution adapters.

`shots` can be passed either as `sampler.run(..., shots=1024)` or in provider
options. The explicit `shots=` argument wins.

## Counts Semantics

`job.result()` returns Qiskit's `SamplerResult`. `job.counts()` converts quasi
distributions into estimated integer counts by multiplying probabilities by the
shot count and rounding. Negative quasi probabilities are floored at zero.

The count view is convenient for notebook display and simple examples. Use the
raw `SamplerResult` when downstream code needs quasi probabilities or metadata.

## Dashboard Endpoint Contract

The managed dashboard client uses these endpoints relative to
`dashboard_api_url`:

- `GET /api/runner/health`: runner availability check.
- `POST /api/runner/jobs`: submit managed QPY job payload.
- `GET /api/runner/jobs/{server_job_id}`: read fresh job status.
- `GET /api/runner/jobs/{server_job_id}/result`: fetch completed result.
- `POST /api/runner/jobs/{server_job_id}/cancel`: request cancellation.
- `GET /api/noise-model/latest`: optional fake-backend noise snapshot.
- `POST /api/runner/direct-events`: best-effort direct-mode audit events.

Dashboard API keys are sent as `X-Dashboard-Api-Key` when configured. PCSS
tokens are local direct-mode credentials and are never part of dashboard job
payloads or direct-event payloads.

## Environment Variables

- `CFT_PIASTQ_MODE`: `auto`, `managed`, `direct`, or `fake`.
- `PCSS_TOKEN` or `PCSS_QAPI_TOKEN`: local direct-mode PCSS token.
- `CFT_PIASTQ_DASHBOARD_API_URL`: dashboard base URL.
- `CFT_PIASTQ_DASHBOARD_API_KEY`: dashboard API key.
- `CFT_PIASTQ_REGISTRY_PATH`: direct-mode SQLite registry path.
- `CFT_PIASTQ_VERBOSE`: print resolved execution mode when truthy.

Constructor arguments override environment variables.

## Security Model

Do not expose PCSS tokens or dashboard API keys in browser, frontend, notebook
output, logs, screenshots, or shared examples. Load them from environment
variables or a secret manager in the process that runs the job.

The package redacts token-like values from public exception messages and direct
registry rows. Direct-mode SQLite rows store job metadata, status, sanitized
errors, and sanitized event payloads. They intentionally omit QPY payloads and
secret fields.

Managed dashboard payloads contain QPY circuit data and metadata, but not PCSS
tokens. Direct event uploads contain local job identifiers, event type, status,
shot counts, and sanitized metadata.

## Known V1 Limitations

- Direct mode depends on optional PCSS/AQT packages and the provider API
  surface available in the local environment.
- Fake mode requires Qiskit Aer at runtime.
- Fake mode with dashboard noise uses a best-effort snapshot conversion for
  simulation convenience, not calibration-grade hardware modeling.
- Auto mode chooses managed or direct only; it never falls back to fake mode.
- `counts()` is an estimate derived from quasi distributions, not raw hardware
  measurement memory.
