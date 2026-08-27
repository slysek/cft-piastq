from __future__ import annotations

import ast
import importlib.util
import re
import textwrap
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "examples"
README = ROOT / "README.md"


def test_example_modules_import_without_running_live_calls(
    monkeypatch,
) -> None:
    for key in (
        "CFT_PIASTQ_DASHBOARD_API_URL",
        "CFT_PIASTQ_DASHBOARD_API_KEY",
        "PCSS_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)

    example_paths = sorted(EXAMPLES_DIR.glob("*.py"))
    assert example_paths

    for path in example_paths:
        module = _import_module(path)
        assert callable(module.main)
        circuit = module.build_bell_circuit()
        assert circuit.name == "bell"
        assert circuit.num_qubits == 2
        assert circuit.num_clbits == 2


def test_readme_python_snippets_are_syntactically_valid() -> None:
    blocks = _python_code_blocks(README.read_text(encoding="utf-8"))

    assert blocks
    for index, block in enumerate(blocks):
        ast.parse(textwrap.dedent(block), filename=f"README.md python block {index}")


def test_readme_starts_with_github_clone_installation() -> None:
    readme = README.read_text(encoding="utf-8")
    clone_position = readme.index(
        "git clone https://github.com/slysek/cft-piastq.git"
    )
    pip_positions = [
        match.start()
        for match in re.finditer(
            r"(?:python\s+-m\s+)?pip\s+install\b",
            readme,
            flags=re.IGNORECASE,
        )
    ]

    assert "https://github.com/slysek/cft-piastq.git" in readme
    assert pip_positions
    assert clone_position < min(pip_positions)
    assert "cd cft-piastq" in readme
    assert 'python -m pip install -e ".[direct]"' in readme
    assert 'python -m pip install -e ".[fake]"' in readme
    assert 'python -m pip install -e ".[dev]"' in readme
    assert "python -m pip install -r docs/requirements.txt" in readme
    dev_install_line = next(
        line for line in readme.splitlines() if 'pip install -e ".[dev]"' in line
    )
    assert "documentation" not in dev_install_line.lower()
    assert "Python 3.11 or 3.12" in readme
    assert "python -m pip install cft-piastq" not in readme


def test_readme_documents_direct_composite_result_contract() -> None:
    readme = " ".join(README.read_text(encoding="utf-8").split())

    for statement in (
        "2,000 shots become 10 sequential PCSS jobs of 200 shots",
        "one logical progress bar",
        "integer counts are summed before probabilities are reconstructed",
        "exact combined counts",
        "examples/direct_bell.ipynb",
        "cannot be recovered after the Python process exits",
    ):
        assert statement in readme


def _import_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to import example module {path.name}.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _python_code_blocks(markdown: str) -> list[str]:
    return re.findall(r"```python\n(.*?)```", markdown, flags=re.DOTALL)
