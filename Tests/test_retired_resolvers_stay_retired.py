"""The guards that named the retired resolvers name only files that exist.

On 2026-11-01 the epidemiology and population-genetics resolvers, their
tests and `requirements-popgen.txt` moved to `archive/legacy_domains/`
after the SIR, SEIR and Wright-Fisher domains they served (those were
archived on 2026-09-27, after v0.4.0, the last release that runs them;
v0.6.0 is the last release that ships the resolvers). Six guards and set-up
checks named those paths, and the way each one would have reacted to the
move is the reason this file exists:

* `verify_citations_live.py` raises on a missing DOI source file, so a
  stale entry stops the whole citation check -- loud, but only when
  someone runs it with network access.
* `check_forbidden_packages.py` SKIPS a listed manifest that does not
  exist, and `check_pins_resolve.py` reads it as having no pins. Both would
  have gone on counting `requirements-popgen.txt` as covered while reading
  nothing -- the "correct check, too narrow a scope" shape, turned inside
  out: a scope that names something that is not there.
* `check_no_silent_skips.py` fails on an allowance whose skip stopped
  happening, but only after running both suites for minutes.
* `check_env.py` and `doctor.py` told contributors to install stdpopsim,
  and on linux/arm64 a C toolchain and GSL, for a resolver nothing calls.

These tests state the same facts statically, in seconds, so the next file
that moves out from under a guard list is caught by `pytest` rather than by
whichever guard happens to run.
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    # A private module name, so this copy never shadows, and is never
    # shadowed by, a `doctor` or `check_env` another test in the same
    # session imports under its bare name. It is still registered in
    # sys.modules because dataclasses resolve their module from there.
    private = f"_retired_resolvers_{name}"
    spec = importlib.util.spec_from_file_location(
        private, SCRIPTS / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[private] = module
    spec.loader.exec_module(module)
    return module


def _missing(paths) -> list[str]:
    return [str(Path(p).relative_to(ROOT)) for p in paths if not Path(p).is_file()]


def test_every_doi_source_file_the_citation_check_reads_exists() -> None:
    verify = _load("verify_citations_live")
    assert not _missing(verify.DOI_SOURCE_FILES), (
        "verify_citations_live.DOI_SOURCE_FILES names files that do not "
        "exist; discovered_dois() raises on the first one, so no citation "
        "after it is checked."
    )


def test_every_manifest_the_forbidden_package_check_lists_exists() -> None:
    guard = _load("check_forbidden_packages")
    assert not _missing(guard.MANIFESTS), (
        "check_forbidden_packages.MANIFESTS names a file that does not "
        "exist. main() skips it silently, so the list claims coverage of a "
        "manifest nobody reads."
    )


def test_every_requirements_file_the_pin_check_lists_exists() -> None:
    guard = _load("check_pins_resolve")
    assert not _missing(guard.REQUIREMENTS), (
        "check_pins_resolve.REQUIREMENTS names a file that does not exist. "
        "pins() returns nothing for it, which reads the same as a file "
        "whose pins all resolved."
    )


def _defined_test_names() -> set[str]:
    """Every test function name and test module stem in the two live suites."""
    names: set[str] = set()
    for suite in (ROOT / "Tests", ROOT / "caterva" / "tests"):
        for path in suite.rglob("test_*.py"):
            names.add(path.stem)
            for match in re.finditer(r"^\s*(?:async\s+)?def (test_\w+)",
                                     path.read_text(encoding="utf-8"), re.M):
                names.add(match.group(1))
    return names


def test_every_unconditional_skip_allowance_names_a_live_test() -> None:
    guard = _load("check_no_silent_skips")
    defined = _defined_test_names()
    unconditional = set(guard.ALLOWED_SKIPS) - set(guard.CONDITIONAL_ON_ENVIRONMENT)
    # A parametrised id carries its parameter in brackets; the function is
    # what has to exist.
    orphaned = sorted(k for k in unconditional if k.split("[", 1)[0] not in defined)
    assert not orphaned, (
        f"ALLOWED_SKIPS allows skips for {orphaned}, which no longer exist "
        "in Tests/ or caterva/tests/. The guard would report them stale "
        "only after running both suites; delete the entries."
    )


def test_the_setup_checks_no_longer_send_people_after_stdpopsim() -> None:
    doctor = _load("doctor")
    check_env = _load("check_env")
    assert not hasattr(doctor, "check_stdpopsim")
    assert not hasattr(check_env, "check_resolver_deps")


def test_nothing_live_imports_what_was_archived() -> None:
    """The archive stays an archive: no live module imports the resolvers
    or stdpopsim, and pytest in Tests/ cannot collect their tests."""
    archived = {"popgen_resolver", "epidemiology_resolver", "stdpopsim"}
    offenders: list[str] = []
    for top in ("Tests", "caterva", "scripts"):
        for path in (ROOT / top).rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    roots = [node.module.split(".")[0]]
                else:
                    continue
                for name in roots:
                    if name in archived:
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} {name}")
    assert not offenders, offenders

    for stem in ("popgen_resolver", "epidemiology_resolver",
                 "test_popgen_resolver", "test_epidemiology_resolver"):
        assert not (ROOT / "Tests" / f"{stem}.py").exists(), stem
        assert any((ROOT / "archive" / "legacy_domains").rglob(f"{stem}.py")), stem
    assert not (ROOT / "requirements-popgen.txt").exists()
