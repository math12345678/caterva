#!/usr/bin/env python3
"""The front page's claim about its own availability is true, both ways.

WHY THIS EXISTS
---------------
`check_quickstart_clone_works.py` (ADR 0143) established that every
documented `git clone` fails for a user with no credentials, and wired
itself into CI red on purpose. That guard is correct and this one does not
replace it.

But look at who each one reaches. That guard prints into a CI log, which
only somebody with push access ever opens. The person actually harmed --
"a stranger who found this on GitHub", in START_HERE.md's own words -- never
sees it. They read the front page, run line one, get a username prompt, and
form the reasonable conclusion that they did something wrong.

So README.md and START_HERE.md now say plainly that the repositories are
private. That is the part CI cannot do: tell the reader.

WHY THAT NOTICE NEEDS A GUARD OF ITS OWN
----------------------------------------
A notice is a claim, and this one rots in a specific and predictable
direction. The day the repositories go public it stops being helpful and
becomes actively harmful -- a front page telling qualified visitors that the
thing they can plainly clone is unavailable to them. Nobody would notice,
because nothing goes red when a warning becomes false. The people who could
tell are exactly the people who have had access all along and never read the
notice, because it never applied to them.

This repository has a name for that shape: **computed and not delivered**,
inverted -- delivered and no longer computed (ADR 0027, 0038, 0039, 0047,
0113). A true sentence, written once, left standing after its subject
changed.

THE FOUR STATES
---------------
Reachability and the notice are two independent facts, so there are four
cases and each gets its own answer rather than being collapsed into a
boolean:

    clone reachable   notice present    verdict
    ----------------  ----------------  -------------------------------
    no                yes               OK -- today. The honest state.
    yes               no                OK -- published, notice removed.
    no                no                FAIL: private and undisclosed.
    yes               yes               FAIL: stale notice turning
                                        visitors away from a public repo.

There is a fifth state, and it is the one the collapsing would hide:
**the probe could not run.** No network, GitHub down. That exits 3 and
asserts nothing about the notice, because "I could not see" must never
become "it is fine" (the standing three-state rule; the eighth instance of a
matcher narrower than its subject is recorded in ADR 0143).

WHAT COUNTS AS A NOTICE
-----------------------
The sentinel below, AND a link to ADR 0143 in the same document. Requiring
both is deliberate: a bare marker string is a guard you satisfy by typing
the marker, whereas a marker that has to carry its reasoning with it makes
the cheapest way to pass also the correct one. It also means the notice and
the decision that produced it cannot drift apart.

WHAT IT DOES NOT CHECK
----------------------
That the prose around the sentinel is accurate, or that the clone then
builds. It answers one question -- does the front page's statement about
being obtainable match whether it is obtainable -- and says so rather than
implying it read the paragraph.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Reused, not reimplemented. A second copy of the probe would be a second
# thing to keep true about GitHub, and this project's most-repeated defect is
# one fact stored twice with nothing comparing them.
from check_quickstart_clone_works import (  # noqa: E402
    CONTROLS,
    documented_authenticated_clones,
    documented_clone_urls,
    reachable_anonymously,
)

#: Documents a newcomer is actually pointed at. START_HERE.md is named by
#: README.md's first line; README.md is what GitHub renders.
FRONT_DOORS = ("README.md", "START_HERE.md")

SENTINEL = "**Not public yet.**"
ADR_LINK = "0143-the-first-command-a-stranger-runs.md"


class Door(NamedTuple):
    document: str
    has_sentinel: bool
    has_adr_link: bool

    @property
    def has_notice(self) -> bool:
        return self.has_sentinel and self.has_adr_link


def read_doors() -> list[Door]:
    doors: list[Door] = []
    for name in FRONT_DOORS:
        path = REPO_ROOT / name
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        doors.append(Door(name, SENTINEL in text, ADR_LINK in text))
    return doors


def anything_reachable() -> bool | None:
    """True if a stranger can clone *any* documented URL; None if unknown.

    ANY rather than ALL on purpose. The notice says "the repositories are
    private". One of them becoming public makes that sentence false, and a
    visitor who can clone the thing in front of them is the case this guard
    exists to catch.
    """
    # Both forms, because the question is about the REPOSITORY and the
    # documents no longer name it the same way.
    #
    # ADR 0179 converted the quickstarts to `gh repo clone owner/repo`, and
    # this function read only `git clone https://...` -- so it found nothing
    # to probe and exited 3, "could not check". A guard that stops being able
    # to see is a guard that has stopped guarding, and it would have gone on
    # reporting could-not-check for as long as the repositories stayed
    # private, which is now indefinitely.
    #
    # The authenticated reference names `owner/repo`; the anonymous URL for
    # it is derivable, and that URL is exactly what a stranger would try.
    urls = [r.url for r in documented_clone_urls()]
    urls += [f"https://github.com/{r.repo}.git"
             for r in documented_authenticated_clones()]
    if not urls:
        return None
    seen_answer = False
    for url in dict.fromkeys(urls):
        got = reachable_anonymously(url)
        if got is None:
            continue
        seen_answer = True
        if got:
            return True
    return False if seen_answer else None


def _report(doors: list[Door], reachable: bool) -> int:
    missing = [d for d in doors if not d.has_notice]
    present = [d for d in doors if d.has_notice]

    if not reachable:
        if not missing:
            print("Private, and both front doors say so. Nothing to fix here.")
            print("  The quickstarts use `gh repo clone`, which is the command")
            print("  that works for a reader who has access (ADR 0179). This")
            print("  guard is the one that fires on publication: make them")
            print("  public and it demands this notice be deleted.")
            return 0
        print("The repositories are private and the front page does not say so.\n")
        for door in missing:
            print(f"  {door.document}")
            if not door.has_sentinel:
                print(f"      no {SENTINEL} notice")
            if not door.has_adr_link:
                print(f"      no link to ADR 0143 ({ADR_LINK})")
            print("      -> a visitor runs `git clone`, is asked for a username,")
            print("         and concludes they did something wrong.\n")
        return 1

    if present:
        print("A documented repository is now cloneable, and the notice is stale.\n")
        for door in present:
            print(f"  {door.document}")
            print(f"      still carries {SENTINEL}")
        print()
        print("  This is the good failure. Delete the notice from each document")
        print("  above; the quickstart is true again and does not need a caveat")
        print("  in front of it. Leaving it turns qualified visitors away from a")
        print("  repository they can plainly clone, and nothing else would say so.")
        return 1

    print("Cloneable by a stranger, and no notice claims otherwise.")
    return 0


def _selftest() -> int:
    """Prove the verdict actually depends on both inputs.

    A guard whose answer is fixed in one of the two dimensions would pass
    every case in that dimension while vouching for it -- which is precisely
    what a boolean collapse of these four states would do.
    """
    failures = 0
    cases = (
        (False, True, 0, "private + disclosed"),
        (False, False, 1, "private + undisclosed"),
        (True, True, 1, "public + stale notice"),
        (True, False, 0, "public + no notice"),
    )
    for reachable, has_notice, want, label in cases:
        doors = [Door(n, has_notice, has_notice) for n in FRONT_DOORS]
        got = _report(doors, reachable)
        if got == want:
            print(f"  [ok] {label} -> exit {got}")
        else:
            print(f"  [SELFTEST FAILED] {label} -> exit {got}, wanted {want}")
            failures += 1
        print()

    # Both halves of "a notice" must be load-bearing, or the ADR link is
    # decoration and the sentinel alone would pass.
    half = [Door(n, True, False) for n in FRONT_DOORS]
    if _report(half, False) == 1:
        print("  [ok] sentinel without the ADR link is not a notice")
    else:
        print("  [SELFTEST FAILED] sentinel alone was accepted as a notice")
        failures += 1

    if failures:
        print(f"\nSELFTEST FAILED: {failures} case(s).")
        return 1
    print("\nSelftest passed: all four states distinguished.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()

    # Controls first, for the same reason the sibling guard does it: an
    # outage must read as "could not check", never as an answer.
    for url in CONTROLS:
        if reachable_anonymously(url) is not True:
            print("Could not check: a known-public repository was unreachable.")
            print(f"  control: {url}")
            print("  This says nothing about the notice either way. Exiting 3.")
            return 3

    reachable = anything_reachable()
    if reachable is None:
        print("Could not check: no documented clone URL produced an answer.")
        print("  Exiting 3 rather than assuming either state.")
        return 3

    return _report(read_doors(), reachable)


if __name__ == "__main__":
    raise SystemExit(main())
