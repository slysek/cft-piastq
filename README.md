# cft-piastq

`cft-piastq` is a Qiskit-compatible PiastQ client. It can submit through the
PiastQ dashboard, connect directly to PCSS/AQT, or simulate locally with Aer.
The Python package is imported as `cft_piastq`.

## Clone and install

Use Python 3.11 or 3.12, then install the checkout with the extra for the mode
you need:

```powershell
git clone https://github.com/slysek/cft-piastq.git
cd cft-piastq
python -m pip install -e ".[direct]"
```

Other supported extras:

```powershell
python -m pip install -e ".[fake]"  # local Qiskit Aer simulation
python -m pip install -e ".[dev]"   # tests, lint, and types
```

To build the Sphinx documentation, install its separate requirements:

```powershell
python -m pip install -r docs/requirements.txt
python -m sphinx -W -b html docs/source docs/_build/html
```

## Direct Bell example

Direct mode needs a PCSS token only. It does not need a dashboard URL or
dashboard API key.

```python
import os

from qiskit import QuantumCircuit

from cft_piastq import PiastQClient, PiastQSampler

bell = QuantumCircuit(2, 2, name="bell")
bell.h(0)
bell.cx(0, 1)
bell.measure([0, 1], [0, 1])

client = PiastQClient(mode="direct", token=os.environ["PCSS_TOKEN"])
sampler = PiastQSampler(client.backend)
job = sampler.run(bell, shots=2000)

result = job.result(timeout=1800)
counts = job.counts()[0]
print(result)
print(counts)
```

For a token-safe, output-free walkthrough, open
[`examples/direct_bell.ipynb`](examples/direct_bell.ipynb). It reads
`PCSS_TOKEN` or prompts with `getpass` instead of saving a token.

## Execution modes

| Mode | Credentials/dependency | Execution | Counts |
| --- | --- | --- | --- |
| `managed` | Dashboard URL, owner, and dashboard API access when required | One logical job submission through the PiastQ dashboard API; splitting and aggregation belong to the separate runner/backend | Estimated from the returned quasi-distributions |
| `direct` | PCSS token only and `.[direct]` | Sequential jobs sent directly to PCSS/AQT | Exact combined counts |
| `fake` | `.[fake]` | Local Qiskit Aer simulation | Estimated from the returned quasi-distributions |
| `auto` | Dashboard configuration and/or PCSS token | Managed when dashboard health succeeds; otherwise direct when a token is available | Depends on the selected mode |

`auto` never selects fake mode. A dashboard authentication error is surfaced;
it does not silently switch to direct mode.

## Automatic direct-job splitting

`shots` is the total logical shot count. Each direct child job is limited to
200 shots, so **2,000 shots become 10 sequential PCSS jobs of 200 shots**. The
library displays one logical progress bar when progress is enabled, not one bar
per child. Disable it with `with_progress_bar=False` in sampler or run options.

After every child completes, its integer counts are summed before probabilities
are reconstructed. `job.result()` therefore returns one Qiskit-compatible
aggregate, while `job.counts()` returns exact combined counts whose total is the
requested logical shot count.

A direct composite job lives in the current process and cannot be recovered
after the Python process exits. Keep that process running until `result()`
finishes. `PiastQClient.retrieve_job()` is for managed dashboard jobs only.

## Managed, fake, and configuration

Managed mode uses the dashboard API. The client submits one logical job payload;
any managed splitting and aggregation is performed by the separate PiastQ
runner/backend, not by the direct-mode splitter in this package. Fake mode runs
locally with Aer. Managed and fake `counts()` remain estimated where their
results provide quasi-probabilities rather than direct integer counts.

Configuration may be passed to `PiastQClient` or read from these environment
variables:

- `PCSS_TOKEN` or `PCSS_QAPI_TOKEN`
- `CFT_PIASTQ_MODE`
- `CFT_PIASTQ_OWNER`
- `CFT_PIASTQ_DASHBOARD_API_URL`
- `CFT_PIASTQ_DASHBOARD_API_KEY`
- `CFT_PIASTQ_REGISTRY_PATH`
- `CFT_PIASTQ_VERBOSE`

Never commit PCSS tokens or dashboard API keys. Do not place them in notebooks,
logs, screenshots, or issue reports. Rotate an exposed credential.

See the [full usage guide](docs/website-documentation.md) and the
[Sphinx documentation](docs/source/index.rst) for configuration, results, and
API details.
