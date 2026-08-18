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
  - a pytest wrapper under `Terium/tests/`

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
PYTEST_DIRS = [REPO_ROOT / "Terium" / "tests", REPO_ROOT / "Tests"]

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
    ("check_codegen_loads", "verify_build"): (
        "runs orval against a real node_modules; verify_build --quick is the "
        "fast path and would stop being run if it shelled out to codegen. "
        "CI has the toolchain and covers it."
    ),
    ("check_identifier_patterns_fresh", "verify_build"): (
        "consults the live identifiers.org registry; verify_build --quick is "
        "the offline fast path. Its comparison logic IS exercised offline by "
        "Tests/test_identifier_pattern_freshness.py, which drives all three "
        "verdicts with a stubbed fetch -- this sandbox can only ever produce "
        "'unreachable', so the other two branches would otherwise never run."
    ),
    ("check_codegen_loads", "pytest"): (
        "same reason: it needs an installed Node toolchain, which a Python "
        "test run cannot assume."
    ),
}

#: Where each guard runs TODAY. A snapshot of fact, not an aspiration.
#:
#: This dict is what the docstring above has always claimed existed. It did
#: not. The loop meant to enforce it computed a key, tested it against
#: DELIBERATE_OMISSIONS, and then fell off the end without appending
#: anything -- an empty body under a docstring promising enforcement. So a
#: guard dropping out of CI while staying in verify_build was reported as
#: "all 19 guards run in at least one harness", which is the weaker claim
#: the code actually made.
#:
#: That is the third appearance of this exact shape in the repository:
#: `check_constant_usage` had a loop with two `continue`s and no
#: `errors.append` (Part 12), and `check_citation_format` printed OK on a
#: zero parse (Part 20). A loop that cannot append is a check that cannot
#: fail.
#:
#: MAINTAINING IT: adding a harness to a guard is an improvement, and is
#: accepted silently -- this records a FLOOR, not an exact match. Removing
#: one fails, and the fix is either to put it back or to move the pair into
#: DELIBERATE_OMISSIONS with a written reason. A new guard needs an entry
#: here; the guard-wiring check will tell you so.
EXPECTED_WIRING: dict[str, tuple[str, ...]] = {
    "check_citation_format": ("verify_build", "ci", "pytest"),
    # Wired 2026-08-15. `make guards` is a fourth harness this script does
    # not model -- it reads verify_build, CI and pytest. The pytest wrapper
    # is what makes it enforcing; the make target is what makes it usable.
    "check_ci_reproducible_locally": ("pytest",),
    "check_doc_paths_resolve": ("pytest",),
    "check_dependency_licenses": ("ci", "pytest", "verify_build"),
    "check_non_affiliation_notice": ("ci", "pytest", "verify_build"),
    "check_no_fabricated_endorsements": ("ci", "pytest", "verify_build"),
    "check_public_images_reviewed": ("pytest",),
    "check_public_claims": ("pytest",),
    "check_investor_claims": ("pytest", "verify_build"),
    # Wired 2026-08-15. Markdown links, as distinct from the backticked
    # prose paths check_doc_paths_resolve covers -- verified by appending a
    # broken `[text](target)` to START_HERE.md and confirming that guard
    # passed it while this one failed it. Both harnesses on purpose: CI is
    # what gates a contributor's PR, verify_build is what a maintainer runs.
    "check_doc_links": ("verify_build", "ci"),
    # Wired 2026-08-15. Both harnesses on purpose: this one watches a fact
    # the licence position depends on (that nothing publishes), and losing
    # it from CI would remove the check from the place a contributor's PR
    # is actually gated.
    "check_release_artifacts": ("verify_build", "ci"),
    # Wired 2026-08-15, same pass that widened its manifest scan.
    # Wired 2026-08-15, same pass as check_dependency_licenses.
    "check_data_source_attribution": ("verify_build", "ci"),
    "check_model_citations_cite_models": ("verify_build", "ci"),
    # Wired 2026-08-15. Both harnesses: CI gates the PR, verify_build is
    # what a maintainer runs locally.
    "check_package_spelling": ("verify_build", "ci"),
    # Wired 2026-08-15, alongside check_package_spelling.
    # Wired 2026-08-15. Covers the seventeen published front pages that
    # check_non_affiliation_notice's seven monorepo surfaces do not.
    "check_published_repo_readmes": ("verify_build", "ci"),
    # Wired 2026-08-16. The sibling above checks what the seventeen split
    # READMEs say; this checks that their repositories carry LICENSE and
    # NOTICE at all. Unconditional: there is no state in which publishing
    # Apache-2.0 source with no licence file is acceptable.
    "check_split_repo_legal_files": ("verify_build", "ci"),
    # Wired 2026-08-16, CI only. check_non_affiliation_notice checks that
    # surfaces CARRY the disclaimer; this checks that no document CONTRADICTS
    # it, which is a different question and the one nothing was asking. CI
    # alone on purpose for now: verify_build.py and the Makefile both hold
    # uncommitted work, and one harness is what "runs unasked" requires.
    "check_no_tellurium_integration_claims": ("ci",),
    # Wired 2026-08-15. Conditional guard: it stops demanding the
    # warning if authentication is ever added to src/web/server.ts.
    "check_deployment_warning": ("ci", "verify_build"),
    # Wired 2026-08-15. Conditional, and paired with
    # check_deployment_warning: both read the same auth signal from the
    # same file so they cannot disagree about whether auth exists.
    "check_port_binding": ("ci", "verify_build"),
    # Wired 2026-08-15. Conditional on collection actually happening,
    # like the two guards above are conditional on auth.
    "check_privacy_notice": ("ci", "verify_build"),
    # Wired 2026-08-15. Third of the conditional privacy/security trio:
    # auth, collection, third-party disclosure. Each goes quiet when the
    # thing it watches for stops being true.
    "check_llm_disclosure": ("ci", "verify_build"),
    # Wired 2026-08-15. Unconditional, unlike its three neighbours:
    # there is no state in which user input reaching a shell is fine.
    "check_subprocess_safety": ("ci", "verify_build"),
    # Wired 2026-08-15, same pass.
    # Wired 2026-08-15, same pass.
    "check_dependencies_declared": ("verify_build", "pytest"),
    "check_documented_counts": ("verify_build", "ci"),
    "check_domain_parity": ("verify_build", "pytest"),
    "check_engine_contract": ("verify_build", "pytest"),
    "check_runner_boundary": ("verify_build",),
    "check_generated_client_loads": ("verify_build",),
    "check_golden_freshness": ("pytest",),
    "check_example_endpoints": ("verify_build",),
    "check_env": ("ci",),
    "check_forbidden_packages": ("verify_build", "ci", "pytest"),
    "check_guard_wiring": ("verify_build", "ci"),
    "check_literature_inventory": ("verify_build",),
    "check_license_consistency": ("verify_build",),
    "check_no_disabled_tests": ("verify_build",),
    "check_no_generated_files_tracked": ("verify_build",),
    "check_no_orphan_modules": ("verify_build",),
    "check_no_silent_skips": ("ci",),
    "check_no_vacuous_tests": ("verify_build",),
    "check_plausibility_constants": ("verify_build", "pytest"),
    "check_prompt_injection": ("verify_build",),
    "check_python_support_claim": ("verify_build", "ci"),
    "check_rng_convention": ("verify_build", "pytest"),
    "check_scripts_reachable": ("verify_build",),
    "check_static_assets": ("verify_build",),
    "check_typescript_compiles": ("verify_build",),
    "check_typescript_suites_discovered": ("verify_build",),
    # Wired 2026-08-14. All seven ran in NO harness until this date --
    # written, correct, and invisible. check_guard_wiring named them
    # together on one run, which is the Stage 4 amendment catching its own
    # failure mode seven times over rather than once.
    "check_adr_index": ("verify_build",),
    "check_cli_surface_documented": ("verify_build",),
    "check_codegen_loads": ("ci",),
    "check_commands_runnable": ("verify_build",),
    "check_commentary_coverage": ("verify_build",),
    "check_findings_reach_a_surface": ("verify_build",),
    "check_citation_cff": ("verify_build", "pytest"),
    "check_identifier_patterns_fresh": ("ci", "pytest"),
    "check_no_hardcoded_assay_conditions": ("verify_build",),
    "check_no_unsourced_ui_numbers": ("verify_build",),
    "check_thrown_values_are_errors": ("verify_build",),
    "check_exports_reach_a_caller": ("verify_build",),
    "check_python_bug_lints": ("verify_build",),
    "check_third_party_requests_disclosed": ("verify_build",),
    "check_mutation_tables_reproducible": ("verify_build",),
    "mutate": ("verify_build",),
    #: The two-front-end guard. verify_build only: it runs the real
    #: runner subprocess to see what is emitted, which CI has no
    #: Python environment for and a pytest wrapper would nest.
    "check_both_front_ends_read_it": ("verify_build",),
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


def _duplicate_expected_wiring_keys() -> list[str]:
    """Keys written more than once in EXPECTED_WIRING.

    A Python dict literal silently keeps the LAST value for a repeated key,
    so `{"x": ("pytest",), ... "x": ("ci",)}` loses the pytest expectation
    entirely -- and losing the pytest wrapper would then not be caught,
    which is the one thing this table exists to catch.

    It happened. On 2026-08-15 five keys were written twice, by agents
    working in parallel who each added an entry without seeing the other's:
    check_dependency_licenses, check_non_affiliation_notice,
    check_no_fabricated_endorsements, check_license_consistency and
    check_scripts_reachable. Fifty-five entries written, fifty surviving.

    The dict cannot report this about itself once parsed, so the source is
    read with `ast`. A ratchet that can silently drop a notch is not a
    ratchet.
    """
    import ast
    import collections

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        is_table = (
            isinstance(node, ast.AnnAssign)
            and getattr(node.target, "id", "") == "EXPECTED_WIRING"
        )
        if is_table and isinstance(node.value, ast.Dict):
            keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
            return sorted(k for k, n in collections.Counter(keys).items() if n > 1)
    return []


def main() -> int:
    guards = _guard_names()
    if not guards:
        print("FAIL: no guard scripts found; nothing was checked.")
        return 1

    in_build = _wired_in(VERIFY_BUILD)
    in_ci = _wired_in(CI_WORKFLOW)
    in_pytest = _wired_in_pytest()

    failures: list[str] = []

    # The table's own integrity, before it is trusted to judge anything.
    for duplicate in _duplicate_expected_wiring_keys():
        failures.append(
            f"EXPECTED_WIRING names {duplicate!r} more than once. Python keeps "
            "only the last value,\n      so the earlier expectation is gone "
            "and losing that harness would not be caught.\n"
            "      Merge them into one entry with the union of harnesses."
        )

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
        expected = EXPECTED_WIRING.get(guard)
        if expected is None:
            failures.append(
                f"{guard}.py has no entry in EXPECTED_WIRING. Add one naming "
                "the harnesses it runs in today, so that losing one later is "
                "caught rather than silently accepted."
            )
            continue

        present_in = {
            name
            for name, yes in (("verify_build", b), ("ci", c), ("pytest", p))
            if yes
        }
        for harness in expected:
            if harness in present_in:
                continue
            if (guard, harness) in DELIBERATE_OMISSIONS:
                continue
            failures.append(
                f"{guard}.py used to run in {harness} and no longer does. "
                "It still runs somewhere, so the 'runs in at least one "
                "harness' rule does not catch this -- which is exactly why "
                "EXPECTED_WIRING exists. Put it back, or move the pair into "
                "DELIBERATE_OMISSIONS with a written reason."
            )

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
    print(
        f"OK: all {len(guards)} guards run in at least one harness, and none "
        "has lost one it used to run in."
    )
    if omitted:
        print(f"    Deliberately narrow: {', '.join(omitted)} (see this script).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
