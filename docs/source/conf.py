from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

project = "cft-piastq"
author = "CFT PiastQ contributors"
copyright = "2026, CFT PiastQ contributors"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

autosummary_generate = True
autodoc_typehints = "description"
autodoc_member_order = "bysource"
napoleon_google_docstring = True
napoleon_numpy_docstring = True

templates_path = ["_templates"]
exclude_patterns: list[str] = []

html_theme = "furo"
html_title = "cft-piastq"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "source_repository": "https://github.com/cft-piastq/cft-piastq/",
    "source_branch": "main",
    "source_directory": "docs/source/",
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
}

pygments_style = "sphinx"
pygments_dark_style = "monokai"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", {}),
    "qiskit": ("https://quantum.cloud.ibm.com/docs/api/qiskit", {}),
}
