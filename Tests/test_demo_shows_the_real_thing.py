"""`make demo` shows the product, not a picture of the product.

WHY THIS FILE EXISTS
--------------------
A demo is the one thing in a repository that everybody looks at and nobody
tests. It is also the easiest place in a repository to put a lie: give it
its own rendering path and it keeps looking impressive for months after the
real command has rotted, and the discrepancy surfaces in front of the first
person who tries the thing it advertised.

That is this project's governing rule pointed at its own front door — a
check that cannot fail is worse than no check, because it is trusted — and a
demo that cannot fail is exactly that.

So these assert the two properties that make `make demo` honest:

1. It produces a **real** document, with a value carrying a real BRENDA
   reference, by driving `report_lab.py` — the same builder the CLI spawns.
2. It renders **nothing itself**. Not a heading, not a table row.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO = REPO_ROOT / "scripts" / "demo.py"
MAKEFILE = REPO_ROOT / "Makefile"
GITIGNORE = REPO_ROOT / ".gitignore"
OUT = REPO_ROOT / "demo-report.md"


def run_demo() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(DEMO)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300,
    )


def test_the_demo_produces_a_document_with_real_provenance():
    """The claim the demo makes, checked on its actual output.

    No skipif and no network marker. The whole point of the demo is that it
    runs without one; a test that skipped when offline would pass in exactly
    the environment the feature exists for.
    """
    done = run_demo()
    assert done.returncode == 0, f"make demo failed:\n{done.stdout[-800:]}\n{done.stderr[-800:]}"

    for heading in ("## Parameters", "## Result", "## What Terrium would not do"):
        assert heading in done.stdout, f"the demo output has no {heading!r}"

    # A literature value with a real reference — not a supplied number, not
    # a placeholder. This is the sentence the whole project is about.
    assert re.search(r"\| km \| [\d.]+ mM \| literature \| BRENDA ref \d+ \|", done.stdout), (
        "no literature-sourced km in the demo output; it is showing "
        "something other than what the front page promises"
    )


def test_the_demo_says_it_used_no_network():
    """Honest about what it did and did not prove.

    A demo that quietly reads a committed fixture while looking like a live
    lookup is a more flattering demo and a dishonest one.
    """
    done = run_demo()
    assert "No network was used" in done.stdout
    assert "Tests/fixtures/brenda_ldh_fixture.html" in done.stdout


def test_the_demo_writes_the_file_it_says_it_wrote():
    """`Written to demo-report.md` must be true when it is printed.

    "Says it did the thing" and "did the thing" are the two states this
    repository most often finds collapsed.
    """
    # Overwritten with a sentinel rather than deleted. `unlink` raised
    # PermissionError in the container this was written in, and a test that
    # cannot run everywhere is a test that gets marked skip and stops
    # meaning anything. Proving the file was REWRITTEN is the stronger
    # claim anyway: a demo that left a stale document in place would pass
    # an existence check.
    sentinel = "STALE OUTPUT FROM A PREVIOUS RUN — the demo did not rewrite this"
    OUT.write_text(sentinel, encoding="utf-8")

    done = run_demo()
    assert done.returncode == 0

    written = OUT.read_text(encoding="utf-8")
    assert sentinel not in written, "the demo printed a path it did not rewrite"
    assert "## Parameters" in written
    # And the file is the document it printed, not a different one.
    assert written.strip() in done.stdout


def test_the_demo_renders_nothing_of_its_own():
    """The property that stops it drifting from the product.

    If the demo ever grows its own heading or table row, it has started
    describing the tool rather than running it, and every assertion above
    can pass while the real command is broken.
    """
    source = DEMO.read_text(encoding="utf-8")
    # Its own docstring quotes the section name, so only string LITERALS
    # that would be emitted are of interest -- checked on the code, with the
    # module docstring removed.
    body = source.split('"""', 2)[-1]
    offenders = [
        line for line in body.splitlines()
        if re.search(r'["\'](#{1,4} |\| )', line)
    ]
    assert not offenders, (
        "the demo is rendering markdown itself:\n  " + "\n  ".join(offenders)
    )


def test_the_make_target_exists_and_runs_the_script():
    """A script nothing invokes is not a demo.

    `make demo` is what the README and `make help` tell a newcomer to run,
    so the target has to exist and has to call this file — the Stage 4
    amendment applied to something that is not a guard.
    """
    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert re.search(r"^demo:", makefile, re.MULTILINE), "no `demo` target"
    assert "scripts/demo.py" in makefile
    phony = next(l for l in makefile.splitlines() if l.startswith(".PHONY:"))
    assert " demo" in phony, (
        "demo is not in .PHONY, so a file named `demo` would silence it"
    )


def test_the_demos_output_is_not_committed():
    """A generated document in the tree is a document that goes stale.

    Committing `demo-report.md` would put a second, unwatched copy of the
    tool's output in the repository — the one-fact-two-copies defect this
    project has recorded most often. It is regenerated by one command.
    """
    assert "demo-report.md" in GITIGNORE.read_text(encoding="utf-8")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "demo-report.md"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert tracked.returncode != 0, "demo-report.md is committed; it should be generated"
