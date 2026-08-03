"""Regression tests for the Rule 7/8 dependency guard.

`scripts/` is not an installed package, so it has to be put on `sys.path`
before the guard can be imported -- the same prelude every other guard
wrapper uses (see `test_citation_format.py`, `test_rng_convention.py`).
Without it the module raises ModuleNotFoundError at collection, which
pytest reports as a collection ERROR rather than a failure.
"""

import pathlib
import sys
from pathlib import Path

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_forbidden_packages import _requirement_names  # noqa: E402


def test_forbidden_packages_after_extra_specifier_are_scanned(
    tmp_path: Path,
) -> None:
    """A closing bracket inside an extra must not end the TOML array."""
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        """[project]
dependencies = [
    \"numpy[dev]\",
    \"tellurium==2.2.10\",
]
""",
        encoding="utf-8",
    )

    assert _requirement_names(manifest) == [
        (3, "numpy"),
        (4, "tellurium"),
    ]


def test_quoted_dependencies_key_and_markers_are_scanned(
    tmp_path: Path,
) -> None:
    """Quoted keys and # characters inside TOML strings remain valid data."""
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        """[ project ]
\"dependencies\" = [
    \"numpy; python_version >= '3.10'\", # inline comment
    \"tellurium==2.2.10\",
]
""",
        encoding="utf-8",
    )

    assert _requirement_names(manifest) == [
        (3, "numpy"),
        (4, "tellurium"),
    ]


def test_forbidden_packages_in_optional_dependencies_are_scanned(
    tmp_path: Path,
) -> None:
    """A forbidden package must not hide in a named optional dependency group."""
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        """[project]
authors = [
    \"tellurium is only a project name, not a dependency\",
]
dependencies = [\"numpy==1.26.4\"]

[project.optional-dependencies]
\"dev tools\" = [
    \"pytest==9.1.1\",
    \"tellurium==2.2.10\",
]

[tool.ruff.per-file-ignores]
\"Tellurium/tests/*.py\" = [\"S101\"]
""",
        encoding="utf-8",
    )

    assert _requirement_names(manifest) == [
        (5, "numpy"),
        (9, "pytest"),
        (10, "tellurium"),
    ]
