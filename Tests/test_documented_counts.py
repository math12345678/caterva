"""The counts in the README, and the command that corrects them.

WHAT THIS COMES FROM
--------------------
`check_documented_counts.py` grew an ADR-count matcher after
`docs/INTERN_ONBOARDING.md` was found claiming 23 decision records when
there were 56. The matcher was applied to every present-tense contributor
document except one:

    if relative == "README.md":
        continue  # already checked above, in more detail

The detailed check above covered test counts, domain counts and guard
counts. It never covered ADRs. So `README.md:449` said "23 decision
records" while `docs/adr/` held **93** — in the one file every newcomer
opens, and the one file the exemption was written for.

The matcher was never broken. `--selftest` asserts it catches
"`docs/adr/` — 23 decision records", verbatim, and had been passing the
whole time. The guard proved it could find that sentence and was never
pointed at the file containing it.

THE SECOND HALF
---------------
Five counts drifted in one hour of concurrent agent work, and the failure
message said "Update README.md" — a hand-edit across six lines, for
numbers a script already knows. `--write` corrects what it derives.

What it must NOT touch is the point of most of these tests: a `--write`
that rewrites a judgment call, an example, or a deliberately approximate
figure would be worse than the drift it fixes, because the result looks
verified.
"""
from __future__ import annotations

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_documented_counts as guard  # noqa: E402

_ACTUAL = {"make_test": 100, "engine": 60, "literature": 40}


def test_the_readme_is_held_to_the_adr_rule() -> None:
    """The exemption, replayed with the verbatim historical line."""
    stale = "│   └── adr/                    23 decision records (and counting)\n"
    problems = guard.adr_failures("README", stale, 93)
    assert problems, (
        "README's ADR count is exempt again. That exemption is how "
        "'23 decision records' survived while docs/adr/ held 93."
    )
    assert "93" in problems[0] and "23" in problems[0]


def test_the_live_readme_agrees_with_docs_adr() -> None:
    readme = (guard.REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert guard.adr_failures("README", readme, guard.count_adrs()) == []


def test_a_correct_count_is_not_flagged() -> None:
    """Crying wolf is how a guard gets ignored."""
    assert guard.adr_failures("x.md", "93 decision records here", 93) == []


def test_the_drafted_public_readmes_are_checked() -> None:
    """`docs/readmes/` is the front page of every repo the split would make.

    Nothing checked it, because it is not live *yet* — which is backwards:
    a stale number in an internal document costs a contributor an hour, and
    a stale number in a published README is the first paragraph a stranger
    reads. `main.md` advertised "1,291 tests (1,014 engine + 277
    literature)" against real figures of 1,997 / 1,142 / 855, and 23 ADRs
    against 94.
    """
    listed = set(guard.PRESENT_TENSE_DOCS)
    on_disk = {
        str(p.relative_to(guard.REPO_ROOT))
        for p in (guard.REPO_ROOT / "docs" / "readmes").glob("*.md")
    }
    assert on_disk, "docs/readmes/ is empty; if it moved, update this guard"
    assert on_disk <= listed, f"unchecked drafted READMEs: {sorted(on_disk - listed)}"


def test_a_test_count_no_suite_has_is_reported() -> None:
    """The figure is stale whatever suite it was about."""
    problems = guard.test_count_failures(
        "docs/readmes/caterva.md", "1,014 tests.\n", _ACTUAL
    )
    assert problems and "1,014" in problems[0]


def test_a_current_test_count_is_accepted() -> None:
    """Any real suite size passes; the guard does not guess which is meant.

    `1,014 tests.` has no antecedent on the line. Requiring it to match a
    *specific* suite would mean inventing an attribution, so the rule is
    that it must match one of them.
    """
    for value in (100, 60, 40):
        assert guard.test_count_failures("x.md", f"{value} tests\n", _ACTUAL) == []


def test_a_report_of_tests_failing_is_not_a_count_of_tests() -> None:
    """`docs/readmes/business.md` describes a real incident.

    "a guard that printed 'every collected test ran' while 275 tests
    failed" is a record of what happened. Rewriting it to a current figure
    would falsify the record to make a build go green — the failure this
    project exists to find, performed by a tool.
    """
    historical = "a guard printed success while 275 tests failed\n"
    assert guard.documented_test_counts(historical) == []
    assert guard.test_count_failures("business.md", historical, _ACTUAL) == []


def test_a_quoted_stale_count_is_an_example_not_a_claim() -> None:
    """`docs/FIRST_TASKS.md` cites the defect it is warning about.

    It said three documents claimed 1,291 tests when the real figure was
    1,684 — and the new matcher flagged the warning. The project already
    has a convention for this, used by `is_quoted`: write a count plainly
    to assert it, quote it to cite it.
    """
    cited = 'documents claiming "22 guards and 1,291 tests" were wrong\n'
    assert guard.documented_test_counts(cited) == []


def test_an_uncollected_suite_produces_no_test_count_findings() -> None:
    """No baseline means no verdict, rather than a verdict against nothing.

    With `actual` empty, every claim would differ from every real figure,
    so a naive implementation reports the whole repository as stale the
    moment pytest cannot run.
    """
    assert guard.test_count_failures("x.md", "1,014 tests\n", {}) == []


def test_write_corrects_the_counts_it_derives() -> None:
    text = (
        "make test      # runs all 1 tests (2 engine + 3 literature)\n"
        "│   └── tests/                4 tests\n"
        "│   └── ...                   5 tests\n"
        "├── scripts/                    6 guard scripts\n"
        "│   └── adr/                    7 decision records\n"
    )
    out, changed = guard.rewrite(text, _ACTUAL, guards=62, adrs=93)
    assert "runs all 100 tests (60 engine + 40 literature)" in out
    assert "tests/                60 tests" in out
    assert "...                   40 tests" in out
    assert "62 guard scripts" in out
    assert "93 decision records" in out
    assert len(changed) == 7, changed


def test_write_leaves_the_domain_count_alone() -> None:
    """The one count the guard refuses to derive, and must refuse to write.

    `DISPATCH` includes a run-mode and a generic ingest path that are not
    teaching domains, so any automatic figure would encode a judgment call.
    The guard checks the two claims agree with *each other* and leaves the
    number to a person. A `--write` that picked one would bury that
    decision inside a script.
    """
    text = "Caterva ships 15 simulation domains.\n"
    out, changed = guard.rewrite(text, _ACTUAL, guards=62, adrs=93)
    assert out == text and changed == []


def test_write_leaves_quoted_examples_alone() -> None:
    """A quoted count is an example. Rewriting it corrupts the explanation.

    `docs/README.md` explains the historical-document exclusion by quoting
    a stale figure. A `--write` that "corrected" the quotation would edit
    the evidence to match the claim.
    """
    text = 'the README once said `23 decision records`, wrongly\n'
    out, changed = guard.rewrite(text, _ACTUAL, guards=62, adrs=93)
    assert out == text and changed == []


def test_write_respects_the_approximate_tolerance() -> None:
    """`~` is a claim about magnitude, not a number to be sharpened.

    Rewriting `~60 guard scripts` to `~62` converts a deliberately loose
    statement into a false-precise one and teaches writers that hedging
    buys nothing.
    """
    inside = "about ~60 guard scripts run on every build\n"
    out, changed = guard.rewrite(inside, _ACTUAL, guards=62, adrs=93)
    assert out == inside and changed == []

    outside = "about ~20 guard scripts run on every build\n"
    out, changed = guard.rewrite(outside, _ACTUAL, guards=62, adrs=93)
    assert "~62 guard scripts" in out and len(changed) == 1


def test_write_is_idempotent() -> None:
    """A second run must find nothing. Otherwise it is oscillating."""
    text = "├── scripts/                    6 guard scripts\n"
    once, _ = guard.rewrite(text, _ACTUAL, guards=62, adrs=93)
    twice, changed = guard.rewrite(once, _ACTUAL, guards=62, adrs=93)
    assert twice == once and changed == []


def test_write_preserves_thousands_separators() -> None:
    """The README's tree diagram is aligned. Reformatting it is a diff nobody asked for."""
    text = "make test      # runs all 1,998 tests (1,179 engine + 819 literature)\n"
    out, _ = guard.rewrite(text, {"make_test": 1967, "engine": 1141, "literature": 826},
                           guards=62, adrs=93)
    assert "1,967" in out and "1,141" in out
    # `literature` had no separator to preserve and must not gain one.
    assert "826" in out and "0,826" not in out


def test_an_uncollectable_suite_never_becomes_a_written_number() -> None:
    """The rule that matters, asserted where it is enforced.

    A partial collection means the test counts are unknown. Writing them
    anyway replaces a stale number with an invented one — and an invented
    number a tool has just written reads as freshly verified, which is
    strictly worse than the drift.

    This is checked on `rewrite` rather than through `main`, because that
    is where the rule lives. The first version tested it through `main` by
    stubbing `collect_count` to return None, and the test failed for a
    reason worth keeping: with no test counts to compare, there were no
    failures at all, so `--write` was never entered and the branch was
    unreachable. The wholesale refusal it was testing has been removed —
    guard and ADR counts come from file globs and have nothing to do with
    whether pytest can collect, so blocking those would leave a
    contributor unable to fix the thing they actually broke.
    """
    text = (
        "make test      # runs all 1 tests (2 engine + 3 literature)\n"
        "├── scripts/                    6 guard scripts\n"
    )
    partial = {"engine": 60}  # literature never collected

    out, changed = guard.rewrite(text, partial, guards=62, adrs=93)

    assert "runs all 1 tests (2 engine + 3 literature)" in out, (
        "a test count was written from an incomplete collection"
    )
    assert "62 guard scripts" in out, (
        "the guard count comes from a file glob and should still be fixed"
    )
    assert changed == ["line 2: guard scripts 6 -> 62"]


def test_main_with_write_never_touches_the_real_readme(monkeypatch, tmp_path) -> None:
    """`--write` is pointed at a copy here, and that is not fussiness.

    The first version of this test called `main()` with `--write` in argv
    against the live tree. Under mutation testing it wrote to the real
    `README.md`: `scripts/mutate.py` keeps its backup beside the file it is
    mutating, so `scripts/check_*.py` briefly globbed to 63, and `--write`
    dutifully recorded 63 guard scripts. The harness restored the script it
    had mutated and had no reason to restore the README, so the edit
    survived the run.

    A test that writes to the working tree is a test that can leave the
    repository wrong when it fails — and this one would have left behind a
    plausible number nobody typed.
    """
    readme = tmp_path / "README.md"
    original = (
        "make test      # runs all 1 tests (2 engine + 3 literature)\n"
        "├── scripts/                    6 guard scripts\n"
        "Caterva ships 15 simulation domains.\n"
    )
    readme.write_text(original, encoding="utf-8")
    monkeypatch.setattr(guard, "README", readme)
    monkeypatch.setattr(guard, "collect_count", lambda path: None)
    monkeypatch.setattr(sys, "argv", ["check_documented_counts.py", "--write"])

    guard.main()

    written = readme.read_text(encoding="utf-8")
    assert "runs all 1 tests (2 engine + 3 literature)" in written, (
        "a test count was written from an incomplete collection"
    )
    assert "15 simulation domains" in written, "the domain count was rewritten"
