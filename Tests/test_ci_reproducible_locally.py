"""The contributor's pre-PR command must cover what CI will actually run.

CONTRIBUTING.md tells you to run `make test` before opening a PR. That runs
two commands. The `test` job in the workflow runs eleven. The nine in
between are guards, and until `make guards` existed there was no local way
to run them as a set -- so the instruction was followed correctly and CI
still failed.

`scripts/check_ci_reproducible_locally.py` compares the two. This wraps it
so something runs it unasked (the Stage 4 amendment), and pins the two
parsers against the real files.

The parser tests are the point. A hand-rolled reader of YAML and Make that
silently returns nothing makes the guard report "all clear" on a repository
it never looked at -- the failure mode that makes a check worse than no
check, because a green tick is trusted.
"""
from __future__ import annotations

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_ci_reproducible_locally import (  # noqa: E402
    CI_ONLY,
    classify,
    MAKEFILE,
    WORKFLOW,
    _normalise,
    _recipe_bodies,
    _run_steps,
    main,
)


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------

def test_every_ci_step_has_a_local_route_or_a_written_reason() -> None:
    assert main() == 0, (
        "CI runs a step that no `make` target runs and that CI_ONLY does not "
        "explain. A contributor cannot reproduce it before pushing. Run "
        "`python scripts/check_ci_reproducible_locally.py` for the list."
    )


def test_it_reports_a_step_with_no_local_route() -> None:
    """The guard must be able to FAIL, shown rather than assumed.

    The test above passes today because the repository is clean. It would
    go on passing if the guard were changed to count unclassified steps as
    reachable -- which is a mutation that was actually run, and which all
    eight of the original tests accepted. A guard whose failing branch is
    never exercised is a guard nobody has checked.
    """
    reachable, ci_only, unreachable = classify(
        ["python scripts/check_something_new.py"], {"python -m pytest"}
    )
    assert unreachable == ["python scripts/check_something_new.py"], (
        "a CI step that no recipe runs was not reported as unreachable"
    )
    assert reachable == [] and ci_only == []


def test_it_does_not_report_a_step_a_recipe_covers() -> None:
    """The other direction: crying wolf trains people to ignore it."""
    _, _, unreachable = classify(
        ["python scripts/check_env.py"], {'python scripts/check_env.py'}
    )
    assert unreachable == []


def test_an_exempted_step_is_not_counted_as_locally_runnable() -> None:
    """CI-only and reachable are different facts and must not merge.

    If an exemption counted as coverage, `make pr` could quietly stop
    running something while this guard still reported it handled.
    """
    marker = next(iter(CI_ONLY))
    reachable, ci_only, unreachable = classify([f"do {marker} now"], set())
    assert ci_only and not reachable and not unreachable


# ---------------------------------------------------------------------------
# The parsers, against the real files
# ---------------------------------------------------------------------------

def test_the_workflow_parser_finds_the_real_steps() -> None:
    """Pinned against the actual workflow, not a synthetic string.

    A test that builds its own YAML cannot verify the reader works on the
    file it will be pointed at.
    """
    steps = _run_steps(WORKFLOW.read_text())
    assert len(steps) >= 10, (
        f"parsed {len(steps)} run-step(s) from the real workflow; it has far "
        "more. The reader is broken, and a broken reader makes this guard "
        "pass on a repository it never examined."
    )
    joined = "\n".join(steps)
    # One inline step and one from a block scalar: both forms must survive.
    assert "python scripts/check_env.py" in joined, "inline `run:` steps lost"
    assert any("pip install -r requirements-dev.txt" in s for s in steps), (
        "block-scalar `run: |` steps lost"
    )


def test_the_makefile_parser_finds_the_real_recipes() -> None:
    recipes = _recipe_bodies(MAKEFILE.read_text())
    assert len(recipes) >= 8, f"parsed only {len(recipes)} recipes from the Makefile"
    for target in ("test", "guards", "pr", "check"):
        assert target in recipes, f"`make {target}` is documented but not parsed"
    assert any("verify_build.py" in line for line in recipes["guards"]), (
        "`make guards` is supposed to run the build guards and does not"
    )


def test_the_floors_fire_on_an_empty_parse() -> None:
    """The safety net, exercised rather than assumed."""
    assert _run_steps("") == []
    assert _recipe_bodies("") == {}


# ---------------------------------------------------------------------------
# Normalisation: loose enough to be useful, tight enough to still fail
# ---------------------------------------------------------------------------

def test_it_sees_through_the_two_spellings_of_the_same_command() -> None:
    assert _normalise('@"$(PY)" scripts/check_env.py') == _normalise(
        "python scripts/check_env.py"
    )
    assert _normalise("cd caterva && python3 -m pytest") == _normalise(
        "python -m pytest -v"
    )


def test_normalisation_does_not_collapse_different_commands() -> None:
    """The failure mode of a fuzzy matcher is matching everything.

    If these compared equal, the guard would report every CI step as
    covered by any recipe at all.
    """
    assert _normalise("python scripts/check_env.py") != _normalise(
        "python scripts/check_guard_wiring.py"
    )
    assert _normalise("python -m pytest") != _normalise("python -m build")


# ---------------------------------------------------------------------------
# The exemption list
# ---------------------------------------------------------------------------

def test_every_ci_only_exemption_carries_a_reason() -> None:
    """'CI only' with no reason is how an unreproducible step becomes permanent."""
    for marker, reason in CI_ONLY.items():
        assert reason and len(reason) > 40, (
            f"CI_ONLY[{marker!r}] has no real explanation. Say why it cannot "
            "run on a contributor's machine, or give it a make target."
        )


def test_every_ci_only_exemption_still_matches_a_real_step() -> None:
    """A stale exemption hides the step it used to cover.

    If CI drops a step, its entry here should go too -- otherwise the next
    step whose text happens to contain that substring is silently exempted.
    """
    steps = _run_steps(WORKFLOW.read_text())
    for marker in CI_ONLY:
        assert any(marker in s for s in steps), (
            f"CI_ONLY[{marker!r}] matches no step in the workflow any more. "
            "Remove it rather than leaving a blanket exemption behind."
        )
