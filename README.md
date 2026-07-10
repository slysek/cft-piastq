# cft-piastq

`cft-piastq` is a Qiskit-compatible client for PiastQ execution. It gives the
same Python-facing workflow for managed dashboard jobs, direct PCSS/AQT jobs,
and local simulation.

Import the package as `cft_piastq`.

## Install

Install the base package from PyPI:

```powershell
python -m pip install cft-piastq
```

Install an extra when you need its execution mode:

```powershell
python -m pip install "cft-piastq[direct]"  # PCSS/AQT provider integration
python -m pip install "cft-piastq[fake]"    # local Qiskit Aer simulation
```

For development from a checkout:

```powershell
python -m pip install -e ".[dev]"
```

## Quick start

The fake mode is useful for a local smoke test. It requires the `fake` extra.

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
counts = job.counts()[0]
print(counts)
```

## Execution modes

| Mode | Use it when |
| --- | --- |
| `managed` | Jobs should be submitted through a PiastQ dashboard runner. |
| `direct` | You have a local PCSS token and want to submit directly to the provider. |
| `fake` | You want local Aer simulation for development or tests. |
| `auto` | You want managed execution when the dashboard is available, with direct execution as the only fallback. |

`auto` never falls back to fake mode. A dashboard authentication error is also
reported instead of silently switching to direct execution.

## Configuration and safety

Pass configuration to `PiastQClient` or provide it through environment
variables. Constructor arguments take precedence. Managed jobs require an
owner and a dashboard URL; direct jobs require a PCSS token.

Never put PCSS tokens or dashboard API keys in source code, notebooks, logs, or
screenshots. Load them from environment variables or a secret manager instead.

See the [full usage guide](docs/website-documentation.md) for configuration,
mode-specific examples, sampler options, job results, and security details.
