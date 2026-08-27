import ast
import hashlib
import io
import json
import re
import tokenize
import tomllib
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REPOSITORY_URL = "https://github.com/slysek/cft-piastq"
PUBLIC_DOCUMENTATION = (
    REPOSITORY_ROOT / "README.md",
    REPOSITORY_ROOT / "docs" / "website-documentation.md",
    REPOSITORY_ROOT / "docs" / "source" / "index.rst",
    REPOSITORY_ROOT / "docs" / "source" / "getting-started.rst",
    REPOSITORY_ROOT / "docs" / "source" / "execution-modes.rst",
    REPOSITORY_ROOT / "docs" / "source" / "configuration.rst",
    REPOSITORY_ROOT / "docs" / "source" / "results.rst",
    REPOSITORY_ROOT / "docs" / "source" / "api-job.rst",
)
SCANNED_SUFFIXES = {
    ".env",
    ".ipynb",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
EXCLUDED_DIRECTORIES = {
    ".git",
    ".history-backup",
    ".history-tools",
    ".history-verification",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".worktrees",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "site",
}
_CREDENTIAL_FIELD = "|".join(
    (
        "api[_-]?key",
        "authorization",
        "dashboard[_-]?api[_-]?key",
        "pcss[_-]?token",
        "secret",
        "token",
    )
)
INLINE_CREDENTIAL = re.compile(
    rf"""
    (?<![\w])
    (?P<field_quote>["']?)(?:{_CREDENTIAL_FIELD})(?P=field_quote)
    \s*(?::|(?<![=!<>])=(?!=))\s*
    (?P<value_quote>["']?)(?:Bearer\s+)?
    (?P<value>[A-Za-z0-9_./+=-]{{24,}})(?P=value_quote)
    (?=$|[\s,;\}}\]\)])
    """,
    re.IGNORECASE | re.MULTILINE | re.VERBOSE,
)
EXPLICIT_PLACEHOLDER_DIGESTS = {
    "70863d54823fb7fdf43ea2f620f30015a208e27d3b0db79ac4403b0ff0ff4764",
}


def test_package_metadata_declares_supported_runtime_and_dependencies() -> None:
    metadata = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text("utf-8"))

    assert metadata["project"]["requires-python"] == ">=3.11"
    assert metadata["project"]["dependencies"] == [
        "qiskit>=1.4,<2",
        "httpx>=0.27,<1",
        "platformdirs>=4,<5",
    ]
    assert metadata["project"]["optional-dependencies"] == {
        "dev": [
            "mypy>=1.11,<2",
            "pytest>=8,<9",
            "pytest-cov>=5,<7",
            "pytest-httpx>=0.35,<0.36",
            "PyYAML>=6,<7",
            "ruff>=0.6,<1",
        ],
        "direct": [
            "pcss-qapi[aqt]>=0.2.2,<0.3",
            "qiskit-aqt-provider>=1.14,<1.15",
            "tqdm>=4.66,<5",
        ],
        "fake": ["qiskit-aer>=0.15,<1"],
    }
    assert "Programming Language :: Python :: 3.10" not in metadata["project"][
        "classifiers"
    ]
    assert metadata["tool"]["ruff"]["target-version"] == "py311"
    assert metadata["tool"]["mypy"]["python_version"] == "3.11"


def test_project_and_sphinx_use_the_canonical_repository_url() -> None:
    metadata = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text("utf-8"))
    conf_source = (
        REPOSITORY_ROOT / "docs" / "source" / "conf.py"
    ).read_text(encoding="utf-8")
    conf_tree = ast.parse(conf_source)
    theme_options_assignment = next(
        node
        for node in conf_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "html_theme_options"
            for target in node.targets
        )
    )
    theme_options = ast.literal_eval(theme_options_assignment.value)

    assert metadata["project"]["urls"]["Homepage"] == CANONICAL_REPOSITORY_URL
    assert theme_options["source_repository"] == f"{CANONICAL_REPOSITORY_URL}/"


def test_getting_started_links_to_the_local_direct_bell_notebook() -> None:
    getting_started = REPOSITORY_ROOT / "docs" / "source" / "getting-started.rst"
    content = getting_started.read_text(encoding="utf-8")
    link = re.search(
        r":download:`[^`]+ <(?P<target>[^>]+direct_bell\.ipynb)>`",
        content,
    )

    assert link is not None
    target = (getting_started.parent / link.group("target")).resolve()
    assert target == (REPOSITORY_ROOT / "examples" / "direct_bell.ipynb").resolve()
    assert target.is_file()


def test_coverage_configuration_enforces_repository_quality_gate() -> None:
    metadata = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text("utf-8"))

    assert metadata["tool"]["coverage"]["run"] == {
        "source": ["cft_piastq"],
        "branch": True,
    }
    assert metadata["tool"]["coverage"]["report"] == {
        "fail_under": 80,
        "show_missing": True,
    }


def test_private_scratch_artifacts_are_not_distributed() -> None:
    forbidden_paths = (
        REPOSITORY_ROOT / "librarytest.py",
        REPOSITORY_ROOT / "libtest.ipynb",
    )

    assert not [path.name for path in forbidden_paths if path.exists()]


def test_direct_bell_notebook_is_safe_runnable_template() -> None:
    notebook_path = REPOSITORY_ROOT / "examples" / "direct_bell.ipynb"

    assert notebook_path.is_file()

    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    assert notebook["nbformat_minor"] == 5
    assert notebook["metadata"]["kernelspec"] == {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    assert notebook["metadata"]["language_info"]["name"] == "python"

    code_cells = [
        cell for cell in notebook["cells"] if cell["cell_type"] == "code"
    ]
    assert code_cells
    assert all(cell["execution_count"] is None for cell in code_cells)
    assert all(cell["outputs"] == [] for cell in code_cells)

    script = "\n\n".join(
        _notebook_source(cell["source"]) for cell in code_cells
    )
    ast.parse(script, filename="examples/direct_bell.ipynb")

    assert 'os.environ.get("PCSS_TOKEN")' in script
    assert "getpass.getpass(" in script
    assert 'mode="direct"' in script
    assert "verbose=False" in script
    assert '"cft_job_name"' in script
    assert "shots=2000" in script
    assert "job.result(timeout=1800)" in script
    assert "counts = job.counts()[0]" in script
    assert "sum(counts.values()) == 2000" in script

    serialized = notebook_path.read_text(encoding="utf-8")
    assert "CFT_PIASTQ_DASHBOARD_API_URL" not in serialized
    assert "dashboard_api_url" not in serialized
    assert "http://" not in serialized


def test_inline_credential_scan_reports_only_file_names(tmp_path: Path) -> None:
    credential = "AbCdEfGh" + "1234567890AbCdEfGh"
    leaked_file = tmp_path / "leaked.py"
    leaked_file.write_text(
        f'DASHBOARD_API_KEY = "{credential}"',
        encoding="utf-8",
    )

    assert _find_inline_credentials(tmp_path) == [Path("leaked.py")]


def test_inline_credential_scan_includes_dotenv_files(tmp_path: Path) -> None:
    credential = "GhIjKlMn" + "1234567890OpQrStUv"
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        f'PCSS_TOKEN="{credential}"',
        encoding="utf-8",
    )

    assert _find_inline_credentials(tmp_path) == [Path(".env")]


def test_inline_credential_scan_detects_alphabetic_only_values(
    tmp_path: Path,
) -> None:
    credential = "AbCdEfGh" * 3
    assignment = "api_key" + f'="{credential}"'
    (tmp_path / "client.py").write_text(
        f"Client({assignment})",
        encoding="utf-8",
    )

    assert _find_inline_credentials(tmp_path) == [Path("client.py")]


def test_inline_credential_scan_detects_arguments_not_comments_or_comparisons(
    tmp_path: Path,
) -> None:
    credential = "QrStUvWx" + "1234567890YzAbCdEf"
    assignment = "token" + f'="{credential}"'
    (tmp_path / "client.py").write_text(
        f"Client({assignment})",
        encoding="utf-8",
    )
    (tmp_path / "comment.py").write_text(
        f"# {assignment}",
        encoding="utf-8",
    )
    (tmp_path / "comparison.py").write_text(
        f'token == "{credential}"',
        encoding="utf-8",
    )

    assert _find_inline_credentials(tmp_path) == [Path("client.py")]


def test_inline_credential_scan_decodes_notebook_cell_sources(
    tmp_path: Path,
) -> None:
    credential = "EfGhIjKl" + "1234567890MnOpQrSt"
    assignment = "api_key" + f'="{credential}"'
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "metadata": {},
                "outputs": [],
                "source": [f"Client({assignment})"],
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (tmp_path / "example.ipynb").write_text(
        json.dumps(notebook),
        encoding="utf-8",
    )

    assert _find_inline_credentials(tmp_path) == [Path("example.ipynb")]


def test_repository_has_no_long_inline_credentials() -> None:
    offenders = _find_inline_credentials(REPOSITORY_ROOT)

    assert not offenders, (
        "Long inline credentials found in: "
        + ", ".join(path.as_posix() for path in offenders)
    )


def test_public_documentation_is_github_clone_first() -> None:
    entry_points = (
        REPOSITORY_ROOT / "README.md",
        REPOSITORY_ROOT / "docs" / "website-documentation.md",
        REPOSITORY_ROOT / "docs" / "source" / "index.rst",
        REPOSITORY_ROOT / "docs" / "source" / "getting-started.rst",
    )

    for path in entry_points:
        content = path.read_text(encoding="utf-8")
        clone_position = content.index(
            "git clone https://github.com/slysek/cft-piastq.git"
        )
        pip_positions = [
            match.start()
            for match in re.finditer(
                r"(?:python\s+-m\s+)?pip\s+install\b",
                content,
                flags=re.IGNORECASE,
            )
        ]

        assert pip_positions, path
        assert clone_position < min(pip_positions), path
        assert "python -m pip install cft-piastq" not in content, path


def test_development_and_documentation_dependencies_are_separate() -> None:
    entry_points = (
        REPOSITORY_ROOT / "README.md",
        REPOSITORY_ROOT / "docs" / "website-documentation.md",
    )

    for path in entry_points:
        content = path.read_text(encoding="utf-8")
        dev_install_line = next(
            line
            for line in content.splitlines()
            if 'pip install -e ".[dev]"' in line
        )
        assert "documentation" not in dev_install_line.lower(), path
        assert "python -m pip install -r docs/requirements.txt" in content, path


def test_managed_dashboard_examples_read_credentials_from_environment() -> None:
    managed_dashboard = (
        REPOSITORY_ROOT / "docs" / "source" / "managed-dashboard.rst"
    ).read_text(encoding="utf-8")

    assert 'dashboard_api_key="' not in managed_dashboard
    assert 'dashboard_api_url="' not in managed_dashboard
    assert 'owner="' not in managed_dashboard
    assert managed_dashboard.count("import os") == 2
    assert managed_dashboard.count('os.environ["CFT_PIASTQ_OWNER"]') == 2
    assert (
        managed_dashboard.count('os.environ["CFT_PIASTQ_DASHBOARD_API_URL"]')
        == 2
    )
    assert (
        managed_dashboard.count(
            'os.environ.get("CFT_PIASTQ_DASHBOARD_API_KEY")'
        )
        == 2
    )


def test_public_documentation_describes_execution_modes_accurately() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    website = (REPOSITORY_ROOT / "docs" / "website-documentation.md").read_text(
        encoding="utf-8"
    )
    modes = (REPOSITORY_ROOT / "docs" / "source" / "execution-modes.rst").read_text(
        encoding="utf-8"
    )
    results = (REPOSITORY_ROOT / "docs" / "source" / "results.rst").read_text(
        encoding="utf-8"
    )

    for raw_content in (readme, website, modes):
        content = " ".join(raw_content.split())
        for mode in ("managed", "direct", "fake", "auto"):
            assert mode in content
        assert "2,000 shots" in content
        assert "10 sequential PCSS jobs" in content
        assert "200 shots" in content
        assert "one logical progress bar" in content
        assert "PCSS token only" in content
        assert "dashboard URL or dashboard API key" in content

    assert "integer counts are summed before probabilities" in results
    assert "exact combined counts" in results
    assert "estimated counts" in results
    assert "managed" in results.lower()
    assert "fake" in results.lower()


def test_public_documentation_uses_only_the_safe_token_placeholder() -> None:
    placeholder_pattern = re.compile(r"\bYOUR_[A-Z0-9_]+\b")

    for path in PUBLIC_DOCUMENTATION:
        placeholders = set(
            placeholder_pattern.findall(path.read_text(encoding="utf-8"))
        )
        assert placeholders <= {"YOUR_PCSS_TOKEN"}, (path, placeholders)


def test_managed_documentation_describes_a_logical_submission_not_http_count() -> None:
    managed_summaries = (
        REPOSITORY_ROOT / "README.md",
        REPOSITORY_ROOT / "docs" / "website-documentation.md",
        REPOSITORY_ROOT / "docs" / "source" / "execution-modes.rst",
    )

    for path in managed_summaries:
        content = " ".join(path.read_text(encoding="utf-8").lower().split())
        assert "one logical job submission" in content, path
        assert "one dashboard request" not in content, path
        assert "one request to the piastq dashboard api" not in content, path
        assert "sends one logical request" not in content, path


def test_job_counts_docstring_distinguishes_exact_and_estimated_modes() -> None:
    source = (REPOSITORY_ROOT / "src" / "cft_piastq" / "job.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    piastq_job = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PiastQJob"
    )
    counts_method = next(
        node
        for node in piastq_job.body
        if isinstance(node, ast.FunctionDef) and node.name == "counts"
    )
    docstring = " ".join((ast.get_docstring(counts_method) or "").lower().split())

    assert "return exact combined integer counts for direct jobs" in docstring
    assert (
        "managed and fake jobs may be estimated from quasi-distributions"
        in docstring
    )


def test_repository_has_standard_mit_license() -> None:
    license_text = (REPOSITORY_ROOT / "LICENSE").read_text(encoding="utf-8")

    assert license_text == (
        "MIT License\n"
        "\n"
        "Copyright (c) 2026 CFT PiastQ contributors\n"
        "\n"
        "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
        "of this software and associated documentation files (the \"Software\"), "
        "to deal\n"
        "in the Software without restriction, including without limitation the rights\n"
        "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
        "copies of the Software, and to permit persons to whom the Software is\n"
        "furnished to do so, subject to the following conditions:\n"
        "\n"
        "The above copyright notice and this permission notice shall be included "
        "in all\n"
        "copies or substantial portions of the Software.\n"
        "\n"
        "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n"
        "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
        "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
        "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
        "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING "
        "FROM,\n"
        "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS "
        "IN THE\n"
        "SOFTWARE.\n"
    )


def test_security_policy_requires_private_reporting_and_rotation() -> None:
    policy = (REPOSITORY_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    normalized = " ".join(policy.lower().split())

    assert "do not open a public issue" in normalized
    for sensitive_item in (
        "credential",
        "token",
        "private endpoint",
        "circuit payload",
        "provider response",
    ):
        assert sensitive_item in normalized
    assert "report security issues privately" in normalized
    assert (
        "when enabled, or through an agreed private channel" in normalized
    )
    assert "revoke or rotate it immediately" in normalized
    assert "deleting a file or rewriting git history is not enough" in normalized
    for forbidden_location in (
        "source code",
        "notebooks",
        "outputs",
        "screenshots",
        "logs",
        "ci",
    ):
        assert forbidden_location in normalized


def test_sensitive_and_generated_artifacts_are_ignored() -> None:
    ignored_lines = (REPOSITORY_ROOT / ".gitignore").read_text(
        encoding="utf-8"
    ).splitlines()

    required_lines = (
        ".env",
        ".env.*",
        "!.env.example",
        ".ipynb_checkpoints/",
        ".coverage",
        "coverage.xml",
        "htmlcov/",
        ".venv-*/",
        ".history-tools/",
        ".history-backup/",
        ".history-verification/",
    )
    for required_line in required_lines:
        assert ignored_lines.count(required_line) == 1


def test_design_documents_are_kept_under_docs_design_without_content_changes() -> None:
    expected_digests = {
        "2026-06-26-cft-piastq-library-design.md": (
            "62119eae4451a5138437e36042d355118c1c6195b388643c31d586bada859777"
        ),
        "2026-06-26-piastq-benchmark-managed-runner-jobs.md": (
            "fbe34f53d650afb42af41160bd5b86e51c20fd79ffc4e074d38b6d800e5a6c00"
        ),
    }

    for file_name, expected_digest in expected_digests.items():
        assert not (REPOSITORY_ROOT / file_name).exists()
        destination = REPOSITORY_ROOT / "docs" / "design" / file_name
        assert destination.is_file()
        assert _canonical_text_digest(destination) == expected_digest


def test_canonical_text_digest_is_line_ending_independent(tmp_path: Path) -> None:
    lf_path = tmp_path / "lf.md"
    crlf_path = tmp_path / "crlf.md"
    lf_path.write_bytes(b"first\nsecond\n")
    crlf_path.write_bytes(b"first\r\nsecond\r\n")

    assert _canonical_text_digest(lf_path) == _canonical_text_digest(crlf_path)


def test_documentation_has_no_stale_root_design_document_references() -> None:
    design_file_names = (
        "2026-06-26-cft-piastq-library-design.md",
        "2026-06-26-piastq-benchmark-managed-runner-jobs.md",
    )

    for path in (REPOSITORY_ROOT / "docs").rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".rst"}:
            continue
        content = path.read_text(encoding="utf-8")
        for file_name in design_file_names:
            stale_reference = re.compile(rf"(?<!/){re.escape(file_name)}")
            assert stale_reference.search(content) is None, path


def test_ci_workflow_enforces_quality_gates_on_supported_python_versions() -> None:
    workflow = _load_workflow("ci.yml")

    assert workflow["permissions"] == {"contents": "read"}
    assert _workflow_triggers(workflow) == {"push": None, "pull_request": None}

    test_job = workflow["jobs"]["test"]
    assert test_job["runs-on"] == "ubuntu-latest"
    assert test_job["strategy"] == {
        "fail-fast": False,
        "matrix": {"python-version": ["3.11", "3.12"]},
    }
    test_steps = test_job["steps"]
    assert _uses(test_steps, "actions/checkout@v7")
    setup_python = _step_using(test_steps, "actions/setup-python@v7")
    assert setup_python["with"] == {
        "python-version": "${{ matrix.python-version }}",
        "cache": "pip",
    }
    test_commands = _workflow_commands(test_steps)
    assert "python -m pip install --upgrade pip" in test_commands
    assert 'python -m pip install -e ".[dev,direct]"' in test_commands
    assert (
        "python -m pytest --cov=cft_piastq --cov-report=term-missing "
        "--cov-report=xml" in test_commands
    )
    assert "python -m ruff check src tests examples" in test_commands
    assert "python -m mypy src/cft_piastq" in test_commands
    assert (
        "python -c \"from cft_piastq import PiastQClient, PiastQSampler; "
        "print('import ok')\"" in test_commands
    )

    docs_job = workflow["jobs"]["docs"]
    assert docs_job["runs-on"] == "ubuntu-latest"
    docs_steps = docs_job["steps"]
    assert _uses(docs_steps, "actions/checkout@v7")
    docs_python = _step_using(docs_steps, "actions/setup-python@v7")
    assert docs_python["with"] == {"python-version": "3.12", "cache": "pip"}
    docs_commands = _workflow_commands(docs_steps)
    assert "python -m pip install --upgrade pip" in docs_commands
    assert 'python -m pip install -e ".[dev]"' in docs_commands
    assert "python -m pip install -r docs/requirements.txt" in docs_commands
    assert (
        "python -m sphinx -W -b html docs/source docs/_build/html"
        in docs_commands
    )


def test_pages_workflow_builds_strict_docs_with_cached_dependencies() -> None:
    workflow = _load_workflow("docs.yml")

    assert workflow["permissions"] == {"contents": "read"}
    assert _workflow_triggers(workflow) == {
        "push": {"branches": ["main"]},
        "workflow_dispatch": None,
    }
    build_steps = workflow["jobs"]["build"]["steps"]
    assert _uses(build_steps, "actions/checkout@v7")
    setup_python = _step_using(build_steps, "actions/setup-python@v7")
    assert setup_python["with"] == {"python-version": "3.12", "cache": "pip"}
    commands = _workflow_commands(build_steps)
    assert 'python -m pip install -e ".[dev]"' in commands
    assert "python -m sphinx -W -b html docs/source docs/_build/html" in commands
    assert _uses(build_steps, "actions/upload-pages-artifact@v5")

    deploy_job = workflow["jobs"]["deploy"]
    assert deploy_job["permissions"] == {
        "pages": "write",
        "id-token": "write",
    }
    assert _uses(deploy_job["steps"], "actions/deploy-pages@v5")


def _canonical_text_digest(path: Path) -> str:
    canonical_text = path.read_text(encoding="utf-8")
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()


def _load_workflow(file_name: str) -> dict[object, object]:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / file_name
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    return workflow


def _workflow_triggers(workflow: dict[object, object]) -> object:
    # PyYAML follows YAML 1.1 and may parse the unquoted key ``on`` as ``True``.
    return workflow.get("on", workflow.get(True))


def _uses(steps: list[dict[str, object]], action: str) -> bool:
    return any(step.get("uses") == action for step in steps)


def _step_using(
    steps: list[dict[str, object]], action: str
) -> dict[str, object]:
    return next(step for step in steps if step.get("uses") == action)


def _workflow_commands(steps: list[dict[str, object]]) -> str:
    return "\n".join(str(step["run"]) for step in steps if "run" in step)


def _find_inline_credentials(root: Path) -> list[Path]:
    offenders: list[Path] = []
    for path in sorted(root.rglob("*")):
        relative_path = path.relative_to(root)
        if any(part in EXCLUDED_DIRECTORIES for part in relative_path.parts):
            continue
        is_dotenv = path.name == ".env" or path.name.startswith(".env.")
        if not path.is_file() or (
            not is_dotenv and path.suffix.lower() not in SCANNED_SUFFIXES
        ):
            continue

        content = _read_scannable_content(path)
        if _contains_inline_credential(path, content):
            offenders.append(relative_path)

    return offenders


def _read_scannable_content(path: Path) -> str:
    content = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".ipynb":
        content = _decode_notebook_sources(content)
    return _strip_comments(path, content)


def _contains_inline_credential(path: Path, content: str) -> bool:
    if path.suffix.lower() == ".py":
        try:
            return _python_contains_inline_credential(content)
        except SyntaxError:
            pass
    return any(
        _is_long_credential_value(match.group("value"))
        for match in INLINE_CREDENTIAL.finditer(content)
    )


def _python_contains_inline_credential(content: str) -> bool:
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword):
            if _is_credential_field(node.arg) and _node_has_long_value(node.value):
                return True
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_is_credential_target(target) for target in targets) and (
                _node_has_long_value(node.value)
            ):
                return True
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and _is_credential_field(key.value)
                    and _node_has_long_value(value)
                ):
                    return True
    return False


def _is_credential_target(target: ast.expr) -> bool:
    if isinstance(target, ast.Name):
        return _is_credential_field(target.id)
    if isinstance(target, ast.Attribute):
        return _is_credential_field(target.attr)
    if isinstance(target, ast.Subscript):
        key = target.slice
        return (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and _is_credential_field(key.value)
        )
    return False


def _is_credential_field(field: str | None) -> bool:
    if field is None:
        return False
    normalized = field.lower().replace("-", "_")
    return normalized in {
        "api_key",
        "authorization",
        "dashboard_api_key",
        "pcss_token",
        "secret",
        "token",
    }


def _node_has_long_value(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _is_long_credential_value(node.value)
    )


def _is_long_credential_value(value: str) -> bool:
    if value.lower().startswith("bearer "):
        value = value[7:]
    normalized = value.lower()
    explicit_placeholder_markers = (
        "dummy",
        "example",
        "fake-",
        "placeholder",
        "replace-me",
        "sentinel",
        "test",
        "your-",
    )
    digest = hashlib.sha256(value.encode()).hexdigest()
    return (
        len(value) >= 24
        and re.fullmatch(r"[A-Za-z0-9_./+=-]+", value) is not None
        and not any(marker in normalized for marker in explicit_placeholder_markers)
        and digest not in EXPLICIT_PLACEHOLDER_DIGESTS
    )


def _decode_notebook_sources(content: str) -> str:
    try:
        notebook = json.loads(content)
    except json.JSONDecodeError:
        return content
    if not isinstance(notebook, dict) or not isinstance(
        notebook.get("cells"), list
    ):
        return content

    sources: list[str] = []
    for cell in notebook["cells"]:
        if not isinstance(cell, dict):
            continue
        source = cell.get("source")
        if isinstance(source, str):
            sources.append(source)
        elif isinstance(source, list):
            sources.append("".join(part for part in source if isinstance(part, str)))
    return "\n".join(sources)


def _notebook_source(source: str | list[str]) -> str:
    if isinstance(source, str):
        return source
    return "".join(source)


def _strip_comments(path: Path, content: str) -> str:
    if path.suffix.lower() == ".py":
        try:
            tokens = tokenize.generate_tokens(io.StringIO(content).readline)
            return tokenize.untokenize(
                token._replace(string="")
                if token.type == tokenize.COMMENT
                else token
                for token in tokens
            )
        except (IndentationError, tokenize.TokenError):
            pass

    return "\n".join(
        "" if line.lstrip().startswith(("#", "//")) else line
        for line in content.splitlines()
    )
