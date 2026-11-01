"""Every file that names a licence must name the same one.

Wraps `scripts/check_license_consistency.py`. Until 2026-11-01 the guard
read only `package.json` and `*.cff`, and at f4ab5f7 the root `openapi.yaml`
-- the spec `GET /api/openapi.json` serves -- said `license: name: MIT`
while the guard printed OK. These tests plant an MIT licence in each kind
of file the guard now reads and assert that it fails, so that dropping a
source from the scan fails here rather than going quiet.

Each plant goes into a throwaway git repository rather than the real tree:
the guard reads `git ls-files`, so the planted file has to be tracked, and
the real tree is shared with other work in progress.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_license_consistency as guard  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[1]

APACHE_SPEC = """openapi: 3.0.3
info:
  title: Caterva API
  version: 1.0.0
  license:
    name: Apache-2.0
paths: {}
"""

#: The shape the root spec had at f4ab5f7, cut to the block that matters.
MIT_SPEC = APACHE_SPEC.replace("name: Apache-2.0", "name: MIT")

APACHE_PYPROJECT = """[project]
name = "caterva"
version = "0.6.0"
license = "Apache-2.0"

[tool.ruff]
line-length = 100
"""


def _repo(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """A git repository holding exactly `files`, all tracked."""
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def _wrong(root: pathlib.Path) -> list[tuple[str, str]]:
    return [
        (str(p.relative_to(root)), lic)
        for p, lic in guard.declared_licences(root)
        if lic != guard.EXPECTED
    ]


def test_the_real_tree_passes() -> None:
    assert guard.main() == 0


def test_the_real_tree_is_read_in_every_new_source_kind() -> None:
    """Passing because the new sources were not found would be worthless."""
    found = {str(p.relative_to(REPO)) for p, _ in guard.declared_licences()}
    assert "openapi.yaml" in found, "the root OpenAPI spec was not read"
    assert "pyproject.toml" in found, "pyproject.toml was not read"


def test_an_mit_licence_in_a_root_openapi_spec_fails(tmp_path) -> None:
    root = _repo(tmp_path, {"openapi.yaml": MIT_SPEC})
    assert _wrong(root) == [("openapi.yaml", "MIT")]


def test_an_mit_licence_in_a_nested_openapi_spec_fails(tmp_path) -> None:
    """Found by name anywhere in the tree, not from a fixed list of paths."""
    root = _repo(tmp_path, {"lib/api-spec/openapi.yml": MIT_SPEC})
    assert _wrong(root) == [("lib/api-spec/openapi.yml", "MIT")]


def test_an_mit_licence_in_a_json_openapi_spec_fails(tmp_path) -> None:
    root = _repo(tmp_path, {
        "openapi.json": '{"openapi": "3.1.0", "info": {"title": "x", '
                        '"version": "1", "license": {"name": "MIT"}}, "paths": {}}',
    })
    assert _wrong(root) == [("openapi.json", "MIT")]


def test_a_flow_style_yaml_licence_is_read(tmp_path) -> None:
    """The reason for PyYAML over a regex: `license: {name: MIT}` on one line."""
    root = _repo(tmp_path, {
        "openapi.yaml": APACHE_SPEC.replace(
            "  license:\n    name: Apache-2.0\n", "  license: {name: MIT}\n"),
    })
    assert _wrong(root) == [("openapi.yaml", "MIT")]


def test_an_identifier_that_contradicts_the_name_fails(tmp_path) -> None:
    root = _repo(tmp_path, {
        "openapi.yaml": APACHE_SPEC.replace(
            "    name: Apache-2.0\n", "    identifier: Apache-2.0\n    name: MIT\n"),
    })
    assert _wrong(root) == [("openapi.yaml", "MIT")]


def test_an_mit_licence_in_pyproject_fails(tmp_path) -> None:
    root = _repo(tmp_path, {
        "pyproject.toml": APACHE_PYPROJECT.replace('"Apache-2.0"', '"MIT"'),
    })
    assert _wrong(root) == [("pyproject.toml", "MIT")]


def test_an_mit_licence_in_the_old_pyproject_table_form_fails(tmp_path) -> None:
    root = _repo(tmp_path, {
        "pyproject.toml": APACHE_PYPROJECT.replace(
            'license = "Apache-2.0"', 'license = {text = "MIT"}'),
    })
    assert _wrong(root) == [("pyproject.toml", "MIT")]


@pytest.mark.parametrize("line, expected", [
    ('license = "MIT"', "MIT"),
    ('license = {text = "MIT"}', "MIT"),
    ('license = {file = "LICENSE"}', None),
])
def test_the_python_3_10_reader_agrees_with_tomllib(line, expected) -> None:
    """The regex fallback runs only on 3.10, so it is exercised directly here.

    A `license` key under `[tool.x]` must not be read as the project's.
    """
    text = APACHE_PYPROJECT.replace('license = "Apache-2.0"', line)
    text += '\n[tool.other]\nlicense = "GPL-3.0"\n'
    assert guard._pyproject_licence_by_regex(text) == expected


def test_a_published_spec_with_no_licence_fails(tmp_path) -> None:
    root = _repo(tmp_path, {
        "openapi.yaml": APACHE_SPEC.replace("  license:\n    name: Apache-2.0\n", ""),
        "pyproject.toml": APACHE_PYPROJECT,
    })
    problems = guard.missing_declarations(root)
    assert len(problems) == 1 and problems[0].startswith("openapi.yaml declares no")


def test_an_internal_spec_with_no_licence_passes(tmp_path) -> None:
    """Silence in an unpublished codegen spec is not a claim about the terms."""
    root = _repo(tmp_path, {
        "openapi.yaml": APACHE_SPEC,
        "pyproject.toml": APACHE_PYPROJECT,
        "lib/api-spec/openapi.yaml": APACHE_SPEC.replace(
            "  license:\n    name: Apache-2.0\n", ""),
    })
    assert guard.missing_declarations(root) == []
    assert _wrong(root) == []


def test_a_pyproject_with_no_licence_fails(tmp_path) -> None:
    root = _repo(tmp_path, {
        "openapi.yaml": APACHE_SPEC,
        "pyproject.toml": APACHE_PYPROJECT.replace('license = "Apache-2.0"\n', ""),
    })
    assert guard.missing_declarations(root) == [
        "pyproject.toml has no [project] license, so the published wheel's "
        "metadata says UNKNOWN."
    ]


def test_a_generator_config_is_not_read_as_a_spec(tmp_path) -> None:
    """`openapitools.json` is tracked and empty; parsing it would exit 3."""
    root = _repo(tmp_path, {"openapitools.json": "", "openapi.yaml": APACHE_SPEC})
    assert [p.name for p in guard.openapi_specs(root)] == ["openapi.yaml"]


def test_a_spec_that_cannot_be_parsed_is_could_not_check(tmp_path) -> None:
    root = _repo(tmp_path, {"openapi.yaml": "openapi: 3.0.3\ninfo: [unclosed\n"})
    with pytest.raises(guard.CouldNotCheckError):
        guard.declared_licences(root)


# --- main() end to end, on a planted tree ---------------------------------
#
# The tests above call the helpers. These run the whole guard, exit code
# included, so a helper that finds the problem but whose result main()
# drops (or reports with exit 0) fails here.

#: Files main() reads by fixed path. Copied from the real tree so the clean
#: planted tree passes for the same reasons the repository does.
_FIXED_FILES = ("LICENSE", "NOTICE", "docs/INBOUND_LICENSE.md", "CONTRIBUTING.md")


def _clean_files() -> dict[str, str]:
    files = {
        rel: (REPO / rel).read_text(encoding="utf-8") for rel in _FIXED_FILES
    }
    files["openapi.yaml"] = APACHE_SPEC
    files["pyproject.toml"] = APACHE_PYPROJECT
    files["CITATION.cff"] = "cff-version: 1.2.0\nlicense: Apache-2.0\n"
    return files


def test_main_passes_a_clean_planted_tree(tmp_path, capsys) -> None:
    """The baseline for the two failures below: without it, a planted tree
    that failed for some unrelated reason would make them pass vacuously."""
    assert guard.main(_repo(tmp_path, _clean_files())) == 0
    assert "OK: every declaration says Apache-2.0" in capsys.readouterr().out


def test_main_fails_a_planted_mit_licence(tmp_path, capsys) -> None:
    files = _clean_files()
    files["openapi.yaml"] = MIT_SPEC
    assert guard.main(_repo(tmp_path, files)) == 1
    assert "openapi.yaml declares license 'MIT'" in capsys.readouterr().out


def test_main_fails_when_the_published_spec_is_missing(tmp_path, capsys) -> None:
    """A renamed or moved published spec must not turn into a pass."""
    files = _clean_files()
    files["api/openapi-v2.yaml"] = files.pop("openapi.yaml")
    assert guard.main(_repo(tmp_path, files)) == 1
    out = capsys.readouterr().out
    assert "openapi.yaml is listed in PUBLISHED_SPECS but does not exist" in out
    assert "update PUBLISHED_SPECS" in out


def test_main_fails_when_the_published_pyproject_is_missing(tmp_path, capsys) -> None:
    files = _clean_files()
    del files["pyproject.toml"]
    assert guard.main(_repo(tmp_path, files)) == 1
    out = capsys.readouterr().out
    assert "pyproject.toml is PUBLISHED_PYPROJECT but does not exist" in out
    assert "update PUBLISHED_PYPROJECT" in out


def test_main_exits_3_on_a_spec_it_cannot_parse(tmp_path, capsys) -> None:
    files = _clean_files()
    files["openapi.yaml"] = "openapi: 3.0.3\ninfo: [unclosed\n"
    assert guard.main(_repo(tmp_path, files)) == 3
    assert "could not check" in capsys.readouterr().out
