"""The literature layer ships: scripts/vendor_literature.py, checkout.literature_module and the wheel.

The resolvers that read BRENDA live in `Tests/` as flat modules. The release
build copies exactly the modules the package can load, and the modules those
import (found with `ast`), into the git-ignored `caterva/_literature/`; the
wheel carries them; `caterva.checkout.literature_module` finds them there when
there is no `Tests/` beside the package. These tests hold each link.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vendor = _load("vendor_literature")


@pytest.fixture()
def target(tmp_path, monkeypatch):
    monkeypatch.setattr(vendor, "TARGET", tmp_path / "_literature")
    return vendor.TARGET


# --- what the closure is ----------------------------------------------------

def test_the_roots_are_what_the_package_asks_for():
    roots = set(vendor.roots())
    assert {"fallback_logic", "brenda_client", "enzyme_lookup", "citation",
            "parameterize", "model_compatibility", "assay_conditions", "enzyme_preparation"} <= roots
    # Not named by the package itself, but imported by modules that are (brenda_client).
    assert "http_retry" in vendor.closure()


def test_every_literature_module_the_package_names_is_in_the_closure():
    """Read independently of vendor_literature: a regex over the sources."""
    import re

    named = set()
    for path in (REPO / "caterva").rglob("*.py"):
        if "tests" in path.relative_to(REPO / "caterva").parts or "_literature" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        named.update(re.findall(r'literature_module\(\s*"(\w+)"', text))
        named.update(re.findall(r"from Tests\.(\w+) import", text))
    assert named and named <= set(vendor.closure())


def test_the_closure_follows_imports_into_other_modules_and_nests():
    closure = set(vendor.closure())
    # fallback_logic imports these; two of them import further modules.
    assert {"evidence_rank", "taxonomy", "form_mixture", "buffer_identity", "selection_tie"} <= closure


def test_no_test_module_or_debug_script_is_in_the_closure():
    closure = vendor.closure()
    assert not [m for m in closure if m.startswith("test_") or m.endswith(("_debug", "_test"))]
    assert not [m for m in closure if m.startswith(("big_test", "brenda_test", "pubmed_test"))]


def test_the_closure_is_closed_over_the_imports_of_every_member():
    available = vendor.tests_modules()
    closure = set(vendor.closure())
    for module in closure:
        tree = ast.parse((REPO / "Tests" / f"{module}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported = []
            if isinstance(node, ast.Import):
                imported = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported = [node.module.split(".")[0]]
            for name in imported:
                assert name not in available or name in closure, f"{module} imports {name}, which would not ship"


def test_a_non_literal_name_is_refused(tmp_path, monkeypatch):
    package = tmp_path / "caterva"
    package.mkdir()
    (package / "x.py").write_text("from caterva.checkout import literature_module\nliterature_module(name)\n")
    monkeypatch.setattr(vendor, "PACKAGE", package)
    with pytest.raises(SystemExit, match="not a string literal"):
        vendor.roots()


# --- what is written --------------------------------------------------------

def test_vendoring_copies_exactly_the_closure_byte_for_byte(target):
    names = vendor.vendor()
    modules = vendor.closure()
    assert names == sorted([*modules, *vendor.SCRIPT_ROOTS])
    written = {p.name for p in target.iterdir()}
    assert written == {f"{m}.py" for m in names} | {"README.txt"}
    for module in modules:
        assert (target / f"{module}.py").read_bytes() == (REPO / "Tests" / f"{module}.py").read_bytes()
    assert (target / "cite.py").read_bytes() == (REPO / "scripts" / "cite.py").read_bytes()
    assert (target / "report_lab.py").read_bytes() == (REPO / "scripts" / "report_lab.py").read_bytes()
    assert vendor.problems() == []


def test_no_fixture_or_data_file_is_copied(target):
    vendor.vendor()
    assert {p.suffix for p in target.iterdir()} <= {".py", ".txt"}


def test_vendoring_is_deterministic_and_mode_fixed(target):
    vendor.vendor()
    first = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), stat.S_IMODE(p.stat().st_mode)) for p in target.iterdir()}
    vendor.vendor()
    second = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), stat.S_IMODE(p.stat().st_mode)) for p in target.iterdir()}
    assert first == second
    assert {mode for _, mode in first.values()} == {0o644}


def test_a_stale_file_is_removed_and_a_changed_one_is_detected(target):
    vendor.vendor()
    (target / "zz_stale.py").write_text("x = 1\n")
    (target / "http_retry.py").write_text("# edited\n")
    problems = vendor.problems()
    assert "stale file zz_stale.py" in problems and "http_retry.py differs from its source" in problems
    vendor.vendor()
    assert not (target / "zz_stale.py").exists() and vendor.problems() == []


def test_a_missing_directory_is_a_problem(target):
    (problem,) = vendor.problems()
    assert problem.endswith("does not exist")


def test_the_vendored_directory_imports_with_nothing_else_on_the_path(target, tmp_path):
    """The flat `from http_retry import ...` imports must resolve from the
    copied directory alone, with the repository's Tests/ nowhere on the path."""
    vendor.vendor()
    modules = [p.stem for p in target.glob("*.py")]
    code = (
        "import sys\n"
        f"sys.path[:] = [p for p in sys.path if 'Tests' not in p]\n"
        f"sys.path.insert(0, {str(target)!r})\n"
        f"for name in {modules!r}:\n"
        "    __import__(name)\n"
        "import fallback_logic\n"
        "assert fallback_logic.__file__.startswith(sys.path[0])\n"
        "print('imported', len(" + repr(modules) + "))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.startswith("imported")


# --- how the package finds it -----------------------------------------------

@pytest.fixture()
def clean_imports():
    saved_path, saved_modules = list(sys.path), set(sys.modules)
    yield
    sys.path[:] = saved_path
    for name in set(sys.modules) - saved_modules:
        del sys.modules[name]


def test_checkout_uses_the_vendored_directory_when_there_is_no_tests_directory(tmp_path, monkeypatch, clean_imports):
    from caterva import checkout

    vendored = tmp_path / "_literature"
    vendored.mkdir()
    (vendored / "zz_vendored_probe.py").write_text("WHERE = 'vendored'\n")
    monkeypatch.setattr(checkout, "_TESTS_DIR", tmp_path / "no-such-Tests")
    monkeypatch.setattr(checkout, "_VENDORED_DIR", vendored)
    assert checkout.tests_directory() is None and checkout.literature_directory() == vendored
    assert checkout.literature_module("zz_vendored_probe").WHERE == "vendored"
    assert str(vendored) in sys.path


def test_checkout_prefers_tests_when_both_exist(tmp_path, monkeypatch, clean_imports):
    from caterva import checkout

    tests, vendored = tmp_path / "Tests", tmp_path / "_literature"
    for directory, where in ((tests, "tests"), (vendored, "vendored")):
        directory.mkdir()
        (directory / "zz_both_probe.py").write_text(f"WHERE = {where!r}\n")
    monkeypatch.setattr(checkout, "_TESTS_DIR", tests)
    monkeypatch.setattr(checkout, "_VENDORED_DIR", vendored)
    assert checkout.literature_directory() == tests
    assert checkout.literature_module("zz_both_probe").WHERE == "tests"


def test_checkout_says_what_is_missing_when_neither_exists(tmp_path, monkeypatch):
    from caterva import checkout

    monkeypatch.setattr(checkout, "_TESTS_DIR", tmp_path / "Tests")
    monkeypatch.setattr(checkout, "_VENDORED_DIR", tmp_path / "_literature")
    with pytest.raises(checkout.LiteratureLayerUnavailable) as caught:
        checkout.literature_module("zz_not_a_module")
    message = str(caught.value)
    assert "caterva/_literature/" in message and "scripts/vendor_literature.py" in message


# --- the wiring that puts it in the wheel -----------------------------------

def test_the_directory_is_ignored_by_git_and_declared_as_package_data():
    assert "caterva/_literature/" in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert '"_literature/*.py"' in pyproject and '"_literature/README.txt"' in pyproject
    manifest = (REPO / "MANIFEST.in").read_text(encoding="utf-8")
    assert "include caterva/_literature/*.py" in manifest
    tracked = subprocess.run(["git", "ls-files", "caterva/_literature"], cwd=REPO, capture_output=True, text=True).stdout
    assert tracked.strip() == ""


def test_the_release_check_refuses_a_wheel_without_the_literature_layer(tmp_path):
    release = _load("build_release")
    wheel = tmp_path / "caterva-0.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("caterva/__init__.py", "")
        zf.writestr("caterva-0.0.0.dist-info/licenses/LICENSE", "x")
        zf.writestr("caterva-0.0.0.dist-info/licenses/NOTICE", "x")
    problems = release._check_wheel(wheel)
    assert any("caterva/_literature/fallback_logic.py" in p for p in problems)


@pytest.mark.timeout(600)
def test_the_built_wheel_carries_exactly_the_closure_and_builds_the_same_twice(tmp_path):
    """The real build, twice, with one SOURCE_DATE_EPOCH."""
    env = {**os.environ, "SOURCE_DATE_EPOCH": "1700000000"}
    sums = []
    for name in ("one", "two"):
        out = tmp_path / name
        result = subprocess.run([sys.executable, str(REPO / "scripts" / "build_release.py"), "--out", str(out)],
                                cwd=REPO, env=env, capture_output=True, text=True, timeout=500)
        assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
        sums.append((out / "SHA256SUMS").read_text(encoding="utf-8"))
    assert sums[0] == sums[1], "the wheel and sdist must be byte-identical for one SOURCE_DATE_EPOCH"
    assert not (REPO / "caterva" / "_literature").exists(), (
        "build_release.py must remove the build-time copies once the sdist is built, or every scan of caterva/ sees each module twice")
    (wheel,) = (tmp_path / "one").glob("caterva-*.whl")
    with zipfile.ZipFile(wheel) as zf:
        shipped = {n.split("/", 2)[2] for n in zf.namelist() if n.startswith("caterva/_literature/")}
        expected = {f"{m}.py" for m in vendor.closure()} | {"cite.py", "report_lab.py", "README.txt"}
        assert shipped == expected
        assert not [n for n in zf.namelist() if "/fixtures/" in n or "Tests/" in n]
        assert zf.read("caterva/_literature/fallback_logic.py") == (REPO / "Tests" / "fallback_logic.py").read_bytes()
