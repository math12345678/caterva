#!/usr/bin/env python3
"""Claim an ADR number without racing another agent for it.

THE PROBLEM, FROM THREE REAL INCIDENTS
--------------------------------------
`check_adr_index.py` states it exactly:

    Several agents write here at once, and each takes "the next free number"
    by looking at the directory -- so two looking at the same moment take
    the same one.

It detects the collision. The remedy it offers is manual: renumber the later
document, fix the index, fix every code comment citing it. That has now been
done three times in two days, twice by me, and each time it cost more than
the ADR was worth. ADR 0030 was written twice. ADR 0031 was taken mid-move.
ADR 0035 was taken four minutes apart.

WHY "PICK THE NEXT FREE NUMBER" CANNOT BE FIXED BY PICKING MORE CAREFULLY
------------------------------------------------------------------------
Two agents scanning the same directory at the same instant see the same
highest number and both compute the same successor. There is no amount of
care that separates them, because at the moment each looks, the other's file
does not exist. A lock file does not help: acquiring it is the same race.

WHAT DOES WORK: WRITE, THEN LOOK AGAIN, AND AGREE ON WHO MOVES
--------------------------------------------------------------
Optimistic concurrency. Claim a number by writing the file, wait for the
other writer's file to become visible, then look again. If two files hold the
number, both agents now see BOTH files -- and can apply the same rule to
decide which of them yields, without talking to each other.

The rule is a total order on filenames: **the lexicographically smaller
filename keeps the number.** Both agents compute it from the same two names
and reach opposite conclusions about themselves, so exactly one moves. The
loser picks the next free number and repeats. It terminates because each
round strictly reduces the number of contenders for any given integer.

That tiebreak is arbitrary, and that is the point -- it only has to be
*shared*. Anything derived from local state (who started first, whose pid is
lower) is not visible to the other agent and cannot be used.

WHAT THIS DOES NOT DO
---------------------
It does not make the claim atomic. There is a window between writing and
re-checking, and this widens it deliberately with a settle delay rather than
pretending it is closed. What it guarantees is CONVERGENCE: after the delay,
if a collision happened, exactly one agent moves.

It also cannot renumber citations inside prose someone already wrote. Claim
the number BEFORE writing the ADR body -- that is why this writes a stub.

Usage:
    python3 scripts/claim_adr.py "a-pool-that-mixes-enzyme-forms"
        -> prints the claimed path; writes a stub with a Status line

    python3 scripts/claim_adr.py --selftest
        -> simulates two agents racing and asserts exactly one moves
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = REPO_ROOT / "docs" / "adr"

#: How long to wait after writing before re-checking.
#:
#: Long enough that a competing write started at the same moment is visible;
#: short enough not to be annoying. Not a correctness parameter -- a longer
#: delay narrows the window, it does not close it, and the convergence rule
#: is what makes the outcome safe.
SETTLE_SECONDS = 2.0

#: Bound on renumber rounds. Reaching it means many agents are contending at
#: once, which is worth reporting rather than looping in.
MAX_ROUNDS = 8

_ADR_RE = re.compile(r"^(\d{4})-(.+)\.md$")


def existing() -> dict[int, list[str]]:
    """number -> filenames holding it. A list, because collisions are the
    thing this file exists to handle; a dict of single names would hide
    exactly the state that matters."""
    found: dict[int, list[str]] = {}
    for path in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")):
        match = _ADR_RE.match(path.name)
        if match:
            found.setdefault(int(match.group(1)), []).append(path.name)
    return found


def next_free(taken: dict[int, list[str]], above: int = 0) -> int:
    candidate = max([*taken, above], default=0) + 1
    while candidate in taken:
        candidate += 1
    return candidate


#: The index row a freshly claimed number needs.
#:
#: WHY THIS IS HERE AND NOT LEFT TO THE AUTHOR
#: -------------------------------------------
#: This tool wrote the stub and stopped, so **every** claimed number began
#: life failing `check_adr_index.py` -- "not linked from README.md" -- until
#: somebody noticed and added a row by hand.
#:
#: On 2026-08-15 four ADRs (0065, 0070, 0072, 0073) were sitting unindexed
#: at once, each reddening the build for everybody else while its author was
#: still writing. The failure is real and the guard is right; the cost was
#: being paid by whoever ran the build next rather than by the person who
#: created it.
#:
#: A tool that reserves a number should leave the tree in the state its own
#: guards expect. Claiming and indexing are one action, not two.
def _index_row(number: int, slug: str, title: str) -> str:
    return (
        f"| [{number:04d}]({number:04d}-{slug}.md) | **Claimed, not yet "
        f"written.** {title} |\n"
    )


def _add_to_index(number: int, slug: str, title: str) -> bool:
    """Append the row. Returns False if it was already there."""
    index = ADR_DIR / "README.md"
    if not index.exists():
        return False
    text = index.read_text(encoding="utf-8")
    if f"{number:04d}-{slug}.md" in text:
        return False
    index.write_text(text.rstrip("\n") + "\n" + _index_row(number, slug, title))
    return True


def stub(number: int, slug: str) -> str:
    title = slug.replace("-", " ").strip().capitalize()
    return (
        f"# ADR {number:04d}: {title}\n"
        "\n"
        "**Status:** Draft — claimed, not yet written.\n"
        "\n"
        "**Date:** " + time.strftime("%Y-%m-%d") + "\n"
        "\n"
        "A stub written by `scripts/claim_adr.py` to reserve this number\n"
        "before the body is drafted. Claiming first is what makes the number\n"
        "safe to cite while you write.\n"
        "\n"
        "Replace this text. A stub left in the tree is a decision record that\n"
        "records no decision, and `check_adr_index.py` counts it as real.\n"
        "\n"
        "---\n"
        "\n"
        "**If this record will present mutation results, it needs a set file.**\n"
        "\n"
        "```\n"
        "docs/mutations/adr-" + "NNNN" + "-<slug>.json\n"
        "python3 scripts/mutate.py --set docs/mutations/adr-NNNN-<slug>.json\n"
        "```\n"
        "\n"
        "`check_mutation_tables_reproducible.py` fails the build without one.\n"
        "The reason is ADR 0069: every mutation table written before that\n"
        "point came from a hand-run harness which had, by then, given a wrong\n"
        "answer three separate ways — a patch that never applied, a suite that\n"
        "never ran, and a restore that silently failed. A mutation table is\n"
        "the evidence a reader is asked to accept, so it should be something\n"
        "they can re-run rather than something they have to trust.\n"
        "\n"
        "One trap worth knowing before you hit it: the set's `test` command\n"
        "must run **every** suite this record cites, not the one that looks\n"
        "most relevant. A narrower command produces a confident NOT CAUGHT\n"
        "that reads exactly like a real gap.\n"
        "\n"
        "Delete this section along with the rest of the stub.\n"
    )


def claim(
    slug: str,
    settle: float = SETTLE_SECONDS,
    verbose: bool = True,
    _settle_hook=None,
) -> Path:
    """Claim a number for `slug`, yielding to a competing claim if needed."""
    slug = slug.strip().strip("/").removesuffix(".md")
    slug = re.sub(r"^\d{4}-", "", slug)

    number = next_free(existing())
    for round_index in range(MAX_ROUNDS):
        path = ADR_DIR / f"{number:04d}-{slug}.md"
        path.write_text(stub(number, slug))

        # The window. Widened on purpose rather than wished away.
        #
        # `_settle_hook` exists so a test can create the competing file
        # DURING this window, which is the only way to reproduce the race
        # faithfully. Pre-creating it instead just moves `next_free` along
        # and the contention never happens -- the first version of the
        # selftest did exactly that and passed for the wrong reason on one
        # case and failed for the wrong reason on the other.
        if _settle_hook is not None:
            _settle_hook(number)
        time.sleep(settle)

        holders = sorted(existing().get(number, []))
        if len(holders) <= 1:
            # Index it here, not on the contended path above: a claim that
            # loses the race deletes its file, and an index row pointing at
            # a deleted file is worse than a missing row -- it looks like
            # the decision is recorded.
            _add_to_index(number, slug, slug.replace("-", " ").strip().capitalize())
            if verbose:
                print(path)
            return path

        # Contended. Both agents see the same sorted list and apply the same
        # rule, so exactly one of them concludes it is not the winner.
        winner = holders[0]
        if path.name == winner:
            if verbose:
                print(
                    f"# contended {number:04d} with {len(holders) - 1} other(s); "
                    f"keeping it ({winner} sorts first)",
                    file=sys.stderr,
                )
                print(path)
            return path

        if verbose:
            print(
                f"# yielding {number:04d} to {winner}; renumbering",
                file=sys.stderr,
            )
        path.unlink(missing_ok=True)
        number = next_free(existing(), above=number)

    raise RuntimeError(
        f"could not settle on a number after {MAX_ROUNDS} rounds. That many "
        "simultaneous writers is worth investigating rather than retrying."
    )


def selftest() -> int:
    """Race two claims and assert exactly one keeps the number.

    Constructed, not hoped for: the second claim is forced onto the same
    number the first took, which is precisely the situation a live race
    produces and which cannot be reproduced by simply calling claim() twice.
    """
    import shutil
    import tempfile

    global ADR_DIR
    real = ADR_DIR
    failures: list[str] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ADR_DIR = Path(tmp)
            (ADR_DIR / "0001-existing.md").write_text("# ADR 0001: Existing\n")

            first = claim("alpha", settle=0.0, verbose=False)
            if first.name != "0002-alpha.md":
                failures.append(f"expected 0002-alpha.md, got {first.name}")

            first.unlink()

            fired: list[int] = []

            def earlier_rival_appears(number: int) -> None:
                # ONE-SHOT. A hook that fires every round manufactures a new
                # rival at each number and the claim never settles -- which
                # is what happened, and is how MAX_ROUNDS got exercised: it
                # raised instead of looping, which is the right behaviour and
                # is asserted separately below.
                if fired:
                    return
                fired.append(number)
                # Must sort BEFORE "alpha" for this agent to yield. The first
                # version used "beta", which sorts AFTER -- so alpha kept the
                # number, correctly, and the test called that a bug. The
                # implementation was right and the expectation was backwards.
                (ADR_DIR / f"{number:04d}-aardvark.md").write_text("# ADR: A\n")

            rival = ADR_DIR / "0002-aardvark.md"
            second = claim(
                "alpha", settle=0.0, verbose=False,
                _settle_hook=earlier_rival_appears,
            )
            if second.name == "0002-alpha.md":
                failures.append(
                    "alpha kept 0002 although beta sorts first; the tiebreak "
                    "did not fire and both agents would keep the number"
                )
            if not second.name.startswith("0003-"):
                failures.append(f"expected renumber to 0003, got {second.name}")
            if not rival.exists():
                failures.append("yielding clobbered the other agent's file")

            # The counterpart: the winner must NOT move. Without this the
            # tiebreak could pass by making every agent yield forever.
            for stale in ADR_DIR.glob("000[23]-*.md"):
                stale.unlink()

            def rival_appears_during_settle(number: int) -> None:
                # A competing agent writing a name that sorts AFTER ours.
                (ADR_DIR / f"{number:04d}-zulu.md").write_text("# ADR: Zulu\n")

            winner = claim(
                "alpha", settle=0.0, verbose=False,
                _settle_hook=rival_appears_during_settle,
            )
            if winner.name != "0002-alpha.md":
                failures.append(
                    f"alpha should have KEPT 0002 (sorts before zulu), got "
                    f"{winner.name}"
                )
            if not (ADR_DIR / "0002-zulu.md").exists():
                failures.append("keeping the number deleted the rival's file")

            # A contender that never yields must be reported, not looped on.
            for stale in ADR_DIR.glob("000[0-9]-*.md"):
                if stale.name != "0001-existing.md":
                    stale.unlink()

            def always_contends(number: int) -> None:
                (ADR_DIR / f"{number:04d}-aardvark.md").write_text("# ADR: A\n")

            try:
                claim("alpha", settle=0.0, verbose=False,
                      _settle_hook=always_contends)
                failures.append(
                    "an endlessly-contended claim returned instead of raising; "
                    "it would loop forever against a misbehaving writer"
                )
            except RuntimeError as exc:
                if "rounds" not in str(exc):
                    failures.append(f"unexpected error text: {exc}")
    finally:
        ADR_DIR = real

    # The bug this tool shipped with: a flag accepted as a slug.
    for flag in ("--help", "-h", "--selftest", "-x"):
        if not _looks_like_a_flag(flag):
            failures.append(
                f"{flag!r} not recognised as a flag; it would be claimed as a "
                "slug and written into docs/adr"
            )
    for real_slug in ("a-pool-that-mixes-enzyme-forms", "effectors-reach-the-api"):
        if _looks_like_a_flag(real_slug):
            failures.append(f"{real_slug!r} wrongly rejected as a flag")

    # The second instance of the same bug: a stringification artefact
    # accepted as a slug. `0065-object-object.md` is the evidence.
    for artefact in ("object-object", "undefined", "null", "NaN", "[object Object]"):
        sanitised = re.sub(r"[^a-z0-9]+", "-", artefact.lower()).strip("-")
        if not _looks_like_an_artefact(sanitised):
            failures.append(
                f"{artefact!r} (as {sanitised!r}) not recognised as an "
                "artefact; it would be written into docs/adr"
            )
    for real_slug in ("no-tellurium-umbrella-package", "the-file-that-leaves-the-building"):
        if _looks_like_an_artefact(real_slug):
            failures.append(f"{real_slug!r} wrongly rejected as an artefact")

    if failures:
        print("SELFTEST FAILED:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(
        "SELFTEST OK: on a contended number the later filename yields and the "
        "earlier one keeps it; both directions checked."
    )
    return 0


#: Slugs that are almost certainly a mistyped flag rather than a title.
#:
#: This exists because it happened: someone ran `claim_adr.py --help` and the
#: script cheerfully claimed a number with the slug "--help", creating
#: `0044---help.md` in the decision record. A tool whose failure mode is
#: writing a file into the directory it is supposed to keep tidy is worse
#: than no tool, and it took another agent minutes to hit.
def _looks_like_a_flag(text: str) -> bool:
    return text.startswith("-")


#: Slugs that are a stringification artefact rather than a title.
#:
#: Same shape as the flag check above, and it happened the same way:
#: `docs/adr/0065-object-object.md` exists because a caller passed a
#: JavaScript object where a string was wanted, and `[object Object]`
#: sanitised into a perfectly valid-looking slug.
#:
#: The flag guard was written after `0044---help.md`. This is the second
#: instance of the same lesson — **a tool whose failure mode is writing a
#: file into the directory it exists to keep tidy is worse than no tool** —
#: so the guard is widened rather than a third one being added later.
_ARTEFACT_SLUGS = frozenset({
    "object-object",     # [object Object]
    "undefined",
    "null",
    "nan",
    "none",
    "true",
    "false",
})


def _looks_like_an_artefact(text: str) -> bool:
    return text.strip().strip("-").lower() in _ARTEFACT_SLUGS


def main() -> int:
    argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    if not argv or "--help" in argv or "-h" in argv:
        print(__doc__.split("Usage:")[-1].strip())
        # Exit 0 for an explicit --help, 2 for no arguments at all: asking
        # for help is not an error, forgetting the slug is.
        return 0 if argv else 2

    if len(argv) != 1:
        print(
            f"Expected one slug, got {len(argv)} arguments: {argv}\n"
            "Quote it if the title contains spaces.",
            file=sys.stderr,
        )
        return 2
    if _looks_like_a_flag(argv[0]):
        print(
            f"{argv[0]!r} looks like a flag, not a slug. Refusing to claim a "
            "number for it.\n"
            "The only flags are --selftest and --help.",
            file=sys.stderr,
        )
        return 2
    if _looks_like_an_artefact(argv[0]):
        print(
            f"{argv[0]!r} is a stringification artefact, not a title. "
            "Refusing to claim a number for it.\n"
            "`docs/adr/0065-object-object.md` exists because this check did "
            "not. A caller passed an object where a string was wanted and "
            "`[object Object]` sanitised into a valid-looking slug.\n"
            "Pass the actual title, e.g. "
            "`claim_adr.py the-conditions-reach-the-student`.",
            file=sys.stderr,
        )
        return 2
    claim(argv[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
