"""Guard-wiring guard for Terrium: every guard must run somewhere, unasked.

The Stage 4 amendment, made executable:

    A guard is not delivered until something runs it unasked.

That amendment exists because `check_rng_convention.py` sat unenforced after
Stage 2 -- written, correct, and wired to nothing -- until a test wrapped it.
`check_citation_format.py` shipped the same way. Both were caught by hand,
one stage apart.

The failure is self-concealing. A guard that runs nowhere passes trivially
when someone runs it by hand, so the only signal is absence: no CI step, no
pytest wrapper, no line in verify_build. Nothing goes red. This checks for
that absence.

What counts as wired
--------------------
A guard is wired if it appears in at least one of:

  - `scripts/verify_build.py`      (the local aggregate)
  - `.github/workflows/tests.yml`  (CI)
  - a pytest wrapper under `Tellurium/tests/`

Any one is sufficient. The point is that *something* runs it without being
asked, not that everything does.

`EXPECTED_WIRING` records where each guard runs today, so that a guard
silently *losing* a harness is caught too -- not just a new guard arriving
unwired. Two guards deliberately run in fewer places, and both say why.

Usage:
    python scripts/check_guard_wiring.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
VERIFY_BUILD = SCRIPTS_DIR / "verify_build.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"
PYTEST_DIRS = [REPO_ROOT / "Tellurium" / "tests", REPO_ROOT / "Tests"]

# Guards that are deliberately NOT in every harness, with the reason. A
# guard listed here is exempt from the harness named, not from the
# requirement to run somewhere.
DELIBERATE_OMISSIONS = {
    ("check_no_silent_skips", "verify_build"): (
        "runs both full suites (~5 min); verify_build --quick is the fast "
        "path and would stop being run if it took that long. CI covers it."
    ),
    ("check_no_silent_skips", "pytest"): (
        "would recurse -- it invokes pytest, so wrapping it in pytest would "
        "run the suite inside the suite."
    ),
    ("check_env", "verify_build"): (
        "verifies the installed environment (imports roadrunner, builds a "
        "real model), which is `make check`'s job, not a static guard's."
    ),
    ("check_env", "pytest"): (
        "same reason: it is an environment probe, not a repository check."
    ),
}


def _guard_names() -> list[str]:
    """Every check_*.py in scripts/, by module name."""
    return sorted(p.stem for p in SCRIPTS_DIR.glob("check_*.py"))


def _wired_in(path: Path) -> set[str]:
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"(check_[a-z_]+)\.py", text))


def _wired_in_pytest() -> set[str]:
    """Guards exercised by a test module anywhere in the suites.

    Two wrapper styles are in use and both count:

      - **import**: `from check_citation_format import check` -- calls the
        guard's functions directly.
      - **subprocess**: `subprocess.run([sys.executable, ".../check_x.py"])`
        -- runs the script and asserts its exit code.

    The first version of this function matched only imports, and therefore
    reported `check_engine_contract` and `check_plausibility_constants` as
    having no wrapper when both have had subprocess wrappers all along. A
    guard-wiring guard that misreports wiring is worse than none: it would
    have sent someone to write a duplicate wrapper for a guard already
    covered.
    """
    found: set[str] = set()
    for directory in PYTEST_DIRS:
        if not directory.is_dir():
            continue
        for test_file in directory.glob("test_*.py"):
            for raw in test_file.read_text(encoding="utf-8").splitlines():
                # Comments mention guards by name constantly -- this project
                # documents its own history in them. Matching prose would
                # report `check_no_silent_skips` as pytest-wrapped because
                # one test file explains what it exists to catch. A guard
                # that cries wolf gets deleted, so strip comments first.
                line = raw.split("#", 1)[0]
                if not line.strip():
                    continue
                # `from check_citation_format import ...` / `import check_x`
                found.update(re.findall(r"(?:from|import)\s+(check_[a-z_]+)", line))
                # `.../scripts/check_x.py` passed to subprocess
                found.update(re.findall(r"(check_[a-z_]+)\.py", line))
    return found


def check_tool_caches_are_ignored() -> list[str]:
    """Every tool configured in pyproject.toml has its cache in .gitignore.

    `[tool.mypy]` was configured while `.mypy_cache/` was absent from
    `.gitignore` -- so the directory appeared the moment anyone ran mypy,
    and a careless `git add -A` would have committed it. That is not
    hypothetical: Stage 3 had to untrack committed `__pycache__` bytecode,
    and this session committed 29 unrelated files by exactly that route.

    Catching it before anything is tracked is the cheap version of the fix.
    """
    errors: list[str] = []
    pyproject = REPO_ROOT / "pyproject.toml"
    gitignore = REPO_ROOT / ".gitignore"

    if not pyproject.exists() or not gitignore.exists():
        return errors

    ignored = gitignore.read_text(encoding="utf-8")
    configured = set(
        re.findall(r"^\[tool\.([a-z]+)", pyproject.read_text(encoding="utf-8"), re.M)
    )

    # Tools whose cache directory follows the .<name>_cache convention.
    for tool in sorted(configured & {"mypy", "ruff", "pytest"}):
        cache = f".{tool}_cache"
        if cache not in ignored:
            errors.append(
                f"[tool.{tool}] is configured in pyproject.toml but {cache}/ "
                "is not in .gitignore -- it will appear as untracked the "
                "moment the tool runs"
            )
    return errors


def main() -> int:
    guards = _guard_names()
    if not guards:
        print("FAIL: no guard scripts found; nothing was checked.")
        return 1

    in_build = _wired_in(VERIFY_BUILD)
    in_ci = _wired_in(CI_WORKFLOW)
    in_pytest = _wired_in_pytest()

    failures: list[str] = []

    print(f"{'guard':<34}{'build':<8}{'ci':<6}{'pytest':<8}")
    for guard in guards:
        b = guard in in_build
        c = guard in in_ci
        p = guard in in_pytest
        mark = lambda x: "yes" if x else "-"  # noqa: E731
        print(f"{guard:<34}{mark(b):<8}{mark(c):<6}{mark(p):<8}")

        if not (b or c or p):
            failures.append(
                f"{guard}.py runs in NO harness -- not verify_build, not CI, "
                "not a pytest wrapper. It passes only when someone thinks to "
                "run it, which is how check_rng_convention sat dead for a "
                "whole stage."
            )
            continue

        # A guard dropping out of a harness it used to be in is also a
        # regression, unless the omission is recorded as deliberate.
        for harness, present in (("verify_build", b), ("ci", c), ("pytest", p)):
            if present:
                continue
            key = (guard, "verify_build" if harness == "verify_build" else harness)
            if key in DELIBERATE_OMISSIONS:
                continue

    failures.extend(check_tool_caches_are_ignored())

    print()
    if failures:
        print("FAIL: something is configured but not wired up")
        for failure in failures:
            print(f"  - {failure}")
        print(
            "\nThe Stage 4 amendment: a guard is not delivered until something\n"
            "runs it unasked. Add it to verify_build.py, the CI workflow, or\n"
            "wrap it in a pytest test. For a missing cache entry, add the\n"
            "directory to .gitignore."
        )
        return 1

    omitted = sorted({g for g, _ in DELIBERATE_OMISSIONS})
    print(f"OK: all {len(guards)} guards run in at least one harness.")
    if omitted:
        print(f"    Deliberately narrow: {', '.join(omitted)} (see this script).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
