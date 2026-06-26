# cft-piastq

`cft-piastq` is a Python package imported as `cft_piastq`. It will provide
Qiskit-compatible facades for PiastQ managed dashboard jobs, direct PCSS/AQT
execution, and local fake execution.

Wave 0 contains the package skeleton and shared contracts only. The public
facade names are importable so notebooks and later modules can depend on a
stable API surface, but constructing `PiastQClient`, `PiastQSampler`, or
`PiastQJob` raises a clear configuration error until later implementation
waves add the real classes.

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
- `auto`: prefer managed mode when available and fall back only under the
  explicit rules implemented by later waves.

## Security Model

PCSS tokens and dashboard API keys are read from constructor arguments or
environment variables. The package must not send PCSS tokens to the dashboard,
persist secrets in SQLite, or expose raw secret values in public exceptions.
Wave 0 includes shared redaction helpers for later adapters.
