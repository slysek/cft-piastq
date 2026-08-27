# cft-piastq user guide

`cft-piastq` gives Qiskit programs one interface for managed PiastQ jobs,
direct PCSS/AQT jobs, and local Aer simulation. Import it as `cft_piastq`.

## Clone and install

Use Python 3.11 or 3.12. Clone this repository and install the execution extra
you need:

```powershell
git clone https://github.com/slysek/cft-piastq.git
cd cft-piastq
python -m pip install -e ".[direct]"
```

```powershell
python -m pip install -e ".[fake]"  # local Aer execution
python -m pip install -e ".[dev]"   # tests, lint, and types
```

Documentation dependencies are maintained separately:

```powershell
python -m pip install -r docs/requirements.txt
python -m sphinx -W -b html docs/source docs/_build/html
```

## Choose an execution mode

| Mode | Requirements | Behavior | Result counts |
| --- | --- | --- | --- |
| `managed` | Dashboard URL, owner, and dashboard API access when required | One logical job submission through the dashboard API; a separate runner/backend owns splitting and aggregation | Estimated when reconstructed from quasi-distributions |
| `direct` | PCSS token only and `.[direct]` | Sends sequential child jobs straight to PCSS/AQT | Exact combined counts |
| `fake` | `.[fake]` | Simulates locally with Qiskit Aer | Estimated from quasi-distributions |
| `auto` | Dashboard configuration and/or a PCSS token | Selects managed when dashboard health succeeds; otherwise direct when a token is available | Depends on the selected mode |

`auto` does not fall back to fake mode. Dashboard authentication and
authorization failures are reported instead of triggering a direct fallback.

## Direct mode: one logical job

Direct mode needs a PCSS token only; it does not need a dashboard URL or
dashboard API key. Pass the token at runtime:

```python
import os

from qiskit import QuantumCircuit

from cft_piastq import PiastQClient, PiastQSampler

bell = QuantumCircuit(2, 2, name="bell")
bell.h(0)
bell.cx(0, 1)
bell.measure([0, 1], [0, 1])

client = PiastQClient(mode="direct", token=os.environ["PCSS_TOKEN"])
sampler = PiastQSampler(
    client.backend,
    options={"cft_job_name": "direct-bell"},
)
job = sampler.run(bell, shots=2000)

result = job.result(timeout=1800)
counts = job.counts()[0]
assert sum(counts.values()) == 2000
```

Here, `shots=2000` means the total for one logical result. Because the PCSS
child limit is 200 shots, **2,000 shots become 10 sequential PCSS jobs of 200
shots**. When enabled, one logical progress bar tracks completed children.
Pass `with_progress_bar=False` in sampler options or `run()` options to hide it.

Child results are validated and converted back to integer counts. Those integer
counts are summed before probabilities are reconstructed, so `result()` returns
one Qiskit-compatible aggregate and `counts()` returns exact combined counts.
This is a sum, not an average of child results.

The composite and its provider handles exist in memory. A direct job cannot be
recovered after the Python process exits. Do not close the process before
`result()` completes. Managed jobs are the only jobs supported by
`PiastQClient.retrieve_job()`.

The output-free notebook [`examples/direct_bell.ipynb`](../examples/direct_bell.ipynb)
shows the same 2,000-shot Bell run. It reads `PCSS_TOKEN` or prompts securely and
does not store notebook output.

## Managed mode

Managed mode talks to the PiastQ dashboard API. Configuration can come from
environment variables, keeping credentials out of source:

```python
import os

from cft_piastq import PiastQClient

client = PiastQClient(
    mode="managed",
    owner=os.environ["CFT_PIASTQ_OWNER"],
    dashboard_api_url=os.environ["CFT_PIASTQ_DASHBOARD_API_URL"],
    dashboard_api_key=os.environ.get("CFT_PIASTQ_DASHBOARD_API_KEY"),
)
```

The library submits one logical job payload. It does not reuse the direct
200-shot splitter for managed mode: splitting and aggregation there belong to
the separately deployed runner/backend. `job.counts()` is an estimated view
when a managed response contains quasi-probabilities.

## Fake mode

Fake mode runs locally and makes no dashboard calls by default:

```python
from cft_piastq import PiastQClient

client = PiastQClient(mode="fake")
```

`job.counts()` is estimated from the fake sampler's quasi-distributions. A
dashboard-provided noise snapshot can be requested explicitly with
`client.fake_backend(use_backend_noise=True)` after dashboard configuration.
It is a development aid, not a calibrated hardware twin.

## Auto mode

Auto mode checks configured dashboard health first. A successful health check
selects managed mode. If the dashboard is unavailable, a configured PCSS token
selects direct mode. Without a usable dashboard or token, client construction
fails with a configuration error. An authentication error is not treated as
ordinary unavailability.

## Options, jobs, and results

Pass library options to `PiastQSampler(...)` or `run(...)`. A run-time option
overrides the sampler default.

| Option | Meaning |
| --- | --- |
| `cft_job_name` | Logical display name; a single circuit name is the default |
| `cft_description` | Optional managed description or direct audit metadata |
| `with_progress_bar` | Direct logical progress display; defaults to `True` |

Common job operations:

```python
job_id = job.job_id()
status = job.status()
result = job.result(timeout=1800)
counts = job.counts()
cancel_status = job.cancel()
```

`result()` is Qiskit-compatible. Direct composite counts are exact after
integer aggregation. Managed and fake counts are legacy estimates where only
quasi-distributions and total shots are available.

## Configuration and security

`PiastQClient` reads explicit arguments first, then these environment values:

| Variable | Purpose |
| --- | --- |
| `PCSS_TOKEN` or `PCSS_QAPI_TOKEN` | Direct PCSS authentication |
| `CFT_PIASTQ_MODE` | `auto`, `managed`, `direct`, or `fake` |
| `CFT_PIASTQ_OWNER` | Managed job owner |
| `CFT_PIASTQ_DASHBOARD_API_URL` | Managed dashboard base URL |
| `CFT_PIASTQ_DASHBOARD_API_KEY` | Protected dashboard operations |
| `CFT_PIASTQ_REGISTRY_PATH` | Local direct audit registry path |
| `CFT_PIASTQ_VERBOSE` | Client messages |

Treat PCSS tokens and dashboard API keys as secrets. Do not commit them or put
them in notebooks, logs, screenshots, issue reports, or example output. Rotate
an exposed credential. Direct payloads, registry rows, and public error messages
must not contain the PCSS token.
