# cft-piastq user guide

`cft-piastq` provides a Qiskit-compatible interface for PiastQ jobs. Use it to
submit circuits through a managed dashboard, run directly with a PCSS/AQT
provider, or simulate locally with Qiskit Aer. The package is imported as
`cft_piastq`.

## Installation

Install the base package from PyPI:

```powershell
python -m pip install cft-piastq
```

Install one of the optional extras when required:

```powershell
python -m pip install "cft-piastq[direct]"  # PCSS/AQT integration
python -m pip install "cft-piastq[fake]"    # Qiskit Aer simulation
```

Contributors working from a repository checkout can use:

```powershell
python -m pip install -e ".[dev]"
```

## Quick start

This local example uses fake mode and requires `cft-piastq[fake]`.

```python
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
```

`PiastQClient` resolves the execution mode and exposes a backend handle.
`PiastQSampler` submits circuits to that backend. `PiastQJob` exposes the job
identifier, state, result, estimated counts, and cancellation API.

## Configuration

Pass the values needed by your application directly to `PiastQClient`. The
examples use placeholders such as `YOUR_DASHBOARD_API_KEY`; replace them in your
application with the values issued for your PiastQ account.

## Choose an execution mode

| Mode | Requirements | Behavior |
| --- | --- | --- |
| `managed` | Dashboard URL and an owner | Checks the runner and submits QPY circuit data through the dashboard. |
| `direct` | PCSS token and the `direct` extra | Submits through the local PCSS/AQT provider integration. |
| `fake` | The `fake` extra | Runs locally with Qiskit Aer. |
| `auto` | Dashboard configuration, a PCSS token, or both | Uses managed mode when the runner is available; otherwise it may use direct mode. |

`auto` never selects fake mode. If the dashboard returns an authentication error,
`auto` surfaces that error rather than falling back to direct execution.

### Managed mode

Managed mode is the normal choice when your team uses a PiastQ dashboard.
Submission needs an owner and a dashboard URL. A dashboard API key is optional
for submission but may be required by protected operations such as cancellation.

```python
from qiskit import QuantumCircuit

from cft_piastq import PiastQClient, PiastQSampler

circuit = QuantumCircuit(2, 2, name="bell")
circuit.h(0)
circuit.cx(0, 1)
circuit.measure([0, 1], [0, 1])

client = PiastQClient(
    mode="managed",
    owner="YOUR_OWNER",
    dashboard_api_url="https://dashboard.example",
    dashboard_api_key="YOUR_DASHBOARD_API_KEY",
)
sampler = PiastQSampler(client.backend, options={"cft_job_name": "Bell test"})
job = sampler.run(circuit, shots=1024)

print(job.job_id())
print(job.result(timeout=120))
```

### Direct mode

Direct mode uses a local PCSS token. It does not need a dashboard, although a
configured dashboard can receive best-effort audit events. The token stays
local and is not sent in dashboard job payloads or stored in the local registry.

```python
from qiskit import QuantumCircuit

from cft_piastq import PiastQClient, PiastQSampler

circuit = QuantumCircuit(1, 1, name="direct-smoke-test")
circuit.h(0)
circuit.measure(0, 0)

client = PiastQClient(mode="direct", token="YOUR_PCSS_TOKEN")
job = PiastQSampler(client.backend).run(circuit, shots=200)

print(job.status())
```

### Fake mode

Fake mode runs locally and makes no dashboard calls by default.

```python
client = PiastQClient(mode="fake")
```

To simulate with a dashboard-provided noise snapshot, create a fake backend
explicitly. This is a development and demonstration aid, not a calibrated
digital twin of the hardware.

```python
from cft_piastq import PiastQClient

client = PiastQClient(
    mode="fake",
    dashboard_api_url="https://dashboard.example",
    dashboard_api_key="YOUR_DASHBOARD_API_KEY",
)
noisy_backend = client.fake_backend(use_backend_noise=True)
```

### Auto mode

Auto mode checks a configured dashboard first. When the runner is unavailable,
it can use direct mode only if a PCSS token is available.

```python
from cft_piastq import PiastQClient

client = PiastQClient(
    mode="auto",
    owner="YOUR_OWNER",
    token="YOUR_PCSS_TOKEN",
    dashboard_api_url="https://dashboard.example",
    dashboard_api_key="YOUR_DASHBOARD_API_KEY",
)

print(client.execution_mode)
```

## Sampler options and jobs

Pass options when creating a sampler or when calling `run()`. Keys beginning
with `cft_` are handled by this package; other options are retained for direct
or fake provider adapters.

| Option | Meaning |
| --- | --- |
| `cft_job_name` | Display name. A single circuit's name is used when this is omitted. |
| `cft_description` | Optional description for managed jobs and direct audit metadata. |
| `cft_fake_simulator_adapter` | Test hook for supplying a fake execution adapter. |

Pass `shots` explicitly to `run()` when possible. It takes precedence over a
`shots` value in provider options.

```python
sampler = PiastQSampler(
    client.backend,
    options={"cft_job_name": "Experiment 42"},
)
job = sampler.run(circuit, shots=4096, cft_description="Parameter sweep")
```

Jobs expose these methods:

```python
job_id = job.job_id()
status = job.status()
result = job.result(timeout=120)
counts = job.counts()
cancelled_status = job.cancel()
```

`result()` returns a Qiskit-compatible `SamplerResult`. `counts()` is a
convenience view: it converts quasi distributions to estimated integer counts
by multiplying probabilities by the shot count and rounding. Use `result()`
when you need the original quasi probabilities or metadata.

## Security

Treat PCSS tokens and dashboard API keys as secrets.

- Do not put them in source files, notebooks, screenshots, or issue reports.
- Do not print client configuration or raw HTTP headers in shared logs.
- Rotate a credential if it was accidentally exposed.

Managed payloads contain QPY circuit data and job metadata, but never PCSS
tokens. Direct-mode registry rows and public error messages redact token-like
values where possible; that does not replace safe secret handling by callers.
