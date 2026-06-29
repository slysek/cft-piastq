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


def _import_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to import example module {path.name}.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _python_code_blocks(markdown: str) -> list[str]:
    return re.findall(r"```python\n(.*?)```", markdown, flags=re.DOTALL)
