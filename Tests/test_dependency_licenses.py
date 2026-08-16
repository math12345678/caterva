"""Every dependency must carry a recorded grant of permission.

Wraps `scripts/check_dependency_licenses.py` so something runs it unasked,
and exercises the branches that matter. The guard currently FAILS on
purpose -- four `@replit/*` packages ship no licence at all and their
manifest entries cannot be removed without a pnpm lockfile regeneration
(see docs/LICENSING.md). So the top-level assertion here is not "it
passes"; it is "it reports exactly the four we know about, and nothing
else has crept in".

That distinction is the point. A test asserting `main() == 0` would have to
be deleted or skipped today, and a deleted test does not come back.
"""
from __future__ import annotations

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_dependency_licenses import (  # noqa: E402
    NO_GRANT,
    PERMISSION,
    _JS_PERMISSIVE,
    js_deps,
    python_deps,
)

#: The four packages that declare no licence. Every one is a Replit editor
#: convenience; all four call sites have been removed, so nothing
#: unlicensed executes. What remains is the manifest entry.
KNOWN_UNLICENSED = {
    "@replit/connectors-sdk",
    "@replit/vite-plugin-cartographer",
    "@replit/vite-plugin-dev-banner",
    "@replit/vite-plugin-runtime-error-modal",
}


def test_no_new_dependency_lacks_a_recorded_grant() -> None:
    """Every declared dependency is either recorded or a known offender."""
    from check_dependency_licenses import installed_js_licence

    unrecorded = set()
    for dep in python_deps():
        if dep not in PERMISSION and dep not in NO_GRANT:
            unrecorded.add(dep)
    for dep in js_deps():
        if dep in PERMISSION or dep in NO_GRANT:
            continue
        lic = installed_js_licence(dep)
        # None means "not installed in this checkout", which is missing
        # evidence rather than a missing licence -- see the guard.
        if lic is not None and lic not in _JS_PERMISSIVE:
            unrecorded.add(dep)

    assert not unrecorded, (
        "dependenc(ies) with no recorded permission to use them: "
        f"{sorted(unrecorded)}. Read the licence text that ships with the "
        "package -- not a package-index summary -- and add it to PERMISSION, "
        "or add it to NO_GRANT and remove the dependency."
    )


def test_the_known_unlicensed_packages_are_still_the_only_ones() -> None:
    """Pins the outstanding item so it cannot silently grow.

    If this fails with a LARGER set, something unlicensed was added. If it
    fails with a SMALLER set, the pnpm removal finally happened and this
    list plus docs/LICENSING.md should shrink to match.
    """
    from check_dependency_licenses import installed_js_licence

    declared = set(js_deps())

    # Direction 1: nothing NEW declares no licence.
    undeclared_now = {
        dep for dep in declared
        if installed_js_licence(dep) == "DECLARES_NOTHING"
    }
    # Positive first: the detector must actually SEE the four we know
    # about. Only asserting "no new ones" is vacuously true when the
    # detector finds nothing -- a mutation reverting the three-state return
    # to a plain None passed all seven tests on exactly that hole.
    assert undeclared_now >= KNOWN_UNLICENSED & declared, (
        "the licence detector no longer reports the known unlicensed "
        f"packages: {sorted((KNOWN_UNLICENSED & declared) - undeclared_now)}. "
        "It is not distinguishing 'installed and declares nothing' from "
        "'not installed here', and those are different facts."
    )
    assert undeclared_now <= KNOWN_UNLICENSED, (
        "new dependenc(ies) ship no licence at all: "
        f"{sorted(undeclared_now - KNOWN_UNLICENSED)}. There is no grant of "
        "permission to use them."
    )

    # Direction 2: the known four are still there, so the list stays honest.
    # This FAILS once `pnpm remove` is finally run -- which is the point:
    # that is when KNOWN_UNLICENSED and docs/LICENSING.md should shrink.
    gone = KNOWN_UNLICENSED - declared
    assert not gone, (
        f"{sorted(gone)} no longer declared -- the pnpm removal happened. "
        "Remove them from KNOWN_UNLICENSED and from NO_GRANT, and update the "
        "outstanding-action section of docs/LICENSING.md."
    )

    for dep in KNOWN_UNLICENSED:
        assert dep in NO_GRANT, f"{dep} is declared but not recorded in NO_GRANT"


def test_recorded_outstanding_items_do_not_block_the_guard() -> None:
    """`make guards` must stay runnable.

    This guard was wired into the command CONTRIBUTING tells contributors
    to run before opening a PR, while exiting 1 over four `@replit/*`
    packages that are recorded, owner-assigned, and clearable only with a
    pnpm lockfile regeneration. Make stops at the first failure, so every
    contributor hit a red wall at step 38 of 45 over something they did not
    add and could not fix.

    A guard that blocks the suite on someone else's recorded item is not
    visibility, it is obstruction -- and it is how `make guards` stops
    being run at all.
    """
    from check_dependency_licenses import main

    assert main() == 0, (
        "the dependency-licence guard is blocking again. If that is a NEW "
        "unlicensed dependency, good -- fix it. If it is one of the recorded "
        "outstanding ones, the blocking/outstanding split has regressed."
    )


def test_a_new_unlicensed_dependency_still_blocks(monkeypatch) -> None:
    """The other half. Waving through the known four must not wave through a fifth."""
    from check_dependency_licenses import main
    import check_dependency_licenses as g

    monkeypatch.setattr(g, "python_deps", lambda: {"mystery-package": "requirements.txt"})
    assert main() == 1, "a dependency with no recorded grant did not fail the build"


def test_rule_7_stays_blocking(monkeypatch) -> None:
    """`tellurium` has no 'outstanding' version.

    Everything else in NO_GRANT is a removal someone has to schedule.
    Rule 7 is a prohibition, and a prohibition that only warns is a
    preference.
    """
    from check_dependency_licenses import main, BLOCKING
    import check_dependency_licenses as g

    assert "tellurium" in BLOCKING
    monkeypatch.setattr(g, "python_deps", lambda: {"tellurium": "requirements.txt"})
    assert main() == 1, "a declared tellurium dependency did not fail the build"


def test_no_unlicensed_package_is_imported_by_any_source_file() -> None:
    """The substantive check: is unlicensed code actually running?

    A manifest entry is a paperwork problem. An import is a use. This is
    the one that would matter in a dispute, and it is why the call sites
    were removed before the manifest entries could be.
    """
    import subprocess

    root = pathlib.Path(__file__).resolve().parents[1]
    tracked = subprocess.run(
        ["git", "ls-files", "*.ts", "*.tsx", "*.js", "*.jsx", "*.mts"],
        cwd=root, capture_output=True, text=True, check=False,
    ).stdout.split()
    assert len(tracked) > 20, (
        "found almost no source files to scan; the listing is broken and "
        "this test would pass vacuously"
    )

    offenders = []
    for rel in tracked:
        if "node_modules" in rel:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for dep in KNOWN_UNLICENSED:
            if dep in text:
                offenders.append(f"{rel} references {dep}")

    assert not offenders, (
        "unlicensed package(s) are referenced by source code:\n  "
        + "\n  ".join(offenders)
    )


def test_every_no_grant_entry_explains_itself() -> None:
    for dep, reason in NO_GRANT.items():
        assert reason and len(reason) > 60, (
            f"NO_GRANT[{dep!r}] does not say why. A prohibition nobody can "
            "evaluate gets removed by the next person who hits it."
        )


def test_every_permission_entry_records_a_licence_and_a_grant() -> None:
    for dep, value in PERMISSION.items():
        licence, grant = value
        assert licence.strip(), f"PERMISSION[{dep!r}] records no licence"
        assert len(grant) > 30, (
            f"PERMISSION[{dep!r}] names a licence but does not say what it "
            "permits. The licence name is not the grant."
        )


def test_the_engine_dependencies_are_recorded_as_permitted() -> None:
    """The ones the whole project rests on, named explicitly.

    If a future edit ever moved these into NO_GRANT, that would be a
    decision to delete the simulation engine, and it should not be possible
    to make it by accident.
    """
    for dep in ("libroadrunner", "antimony", "python-libsbml"):
        assert dep in PERMISSION, f"{dep} lost its recorded permission"
        assert dep not in NO_GRANT
    assert "Apache" in PERMISSION["libroadrunner"][0]
    assert "University of Washington" in PERMISSION["libroadrunner"][1], (
        "the libRoadRunner grant should name its copyright holder"
    )


def test_tellurium_is_forbidden_here_too() -> None:
    """Constitution Rule 7, restated where a licence reader will look."""
    assert "tellurium" in NO_GRANT
    assert "Rule 7" in NO_GRANT["tellurium"]
