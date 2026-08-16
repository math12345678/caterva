#!/usr/bin/env python3
"""Every published repository ships a README that says the legal basics.

WHY THIS EXISTS
---------------
Terrium is published as eighteen repositories under
github.com/Terrium-sim. The monorepo is where work happens; the other
seventeen are regenerated from it by `scripts/split_repos.sh`, each with a
README written from a source in `docs/readmes/`.

Those READMEs are what a stranger actually lands on. Somebody who finds
`Terrium-sim/backend-main` from a search result sees that file and nothing
else — not the umbrella README, not LICENSE, not NOTICE.

On 2026-08-15 an audit of the seventeen sources found:

    licence stated              2 of 17
    non-affiliation notice      3 of 17
    route to contributing       0 of 17

So fifteen separately-published repositories carried no statement of their
own terms, and none of the seventeen told a would-be contributor where to
go. A visitor who wanted to help had to guess that a repository called
`main` was the one to read.

The licence half is the more serious. `check_license_consistency.py` exists
because `package.json` said MIT while LICENSE said all-rights-reserved --
"three files, three answers, for months", as LICENSE puts it. Fifteen
published repositories saying nothing at all is the same defect at a larger
scale, and no guard was looking at them.

RELATION TO check_non_affiliation_notice.py
-------------------------------------------
That guard checks seven surfaces, all inside the monorepo: NOTICE,
README.md, CITATION.cff, pyproject.toml, package.json, the package docstring
and the landing page. All seven are correct and it works.

It does not look at `docs/readmes/`. Seventeen published front pages sat
outside a guard whose subject is "every shipping surface carries the
notice", because "shipping surface" had been enumerated once and the split
happened later.

That is the fifth instance of this shape found on 2026-08-15:
`check_documented_counts` on one document, `check_no_unsourced_ui_numbers`
on HTML only, `check_forbidden_packages` on three named manifests,
`check_dependency_licenses` on two, and this. **A correct check on too
narrow a scope, five times, by five different authors, in one day.**

WHAT IT CHECKS
--------------
1. Every repository listed in `docs/REPO_MAP.md` has a README source in
   `docs/readmes/`, or is named in `NOT_OURS` with a reason.
2. Each source states the licence, carries the non-affiliation notice, and
   routes a reader to START_HERE.

WHAT IT DOES NOT CHECK
----------------------
**That the published repositories actually match these sources.** That needs
network access and the split to have been run. This guard checks the inputs
to `split_repos.sh`, which is what is knowable offline — a README source
that is right cannot guarantee a push that happened.

Stated plainly because "every published repo has a licence" would be read as
more than this proves.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parent.parent
REPO_MAP = REPO / "docs" / "REPO_MAP.md"
READMES = REPO / "docs" / "readmes"

#: Repositories in the map that are not Terrium's to write a README for.
NOT_OURS = {
    "demo-repository": (
        "GitHub's own demo repository, left untouched. docs/PUBLISHING.md "
        "records the same. Writing a Terrium README into it would be "
        "editing somebody else's repository."
    ),
}

#: What every source must carry, and why that specific thing.
REQUIRED = [
    (
        re.compile(r"apache", re.I),
        "the licence",
        "A published repository that does not state its terms is one nobody "
        "may safely use. Apache-2.0 4(d) also makes NOTICE travel with "
        "redistribution, and a reader has to know to look for it.",
    ),
    (
        re.compile(r"not\s+tellurium", re.I),
        "the non-affiliation notice",
        "Terrium shares a field and nearly a name with the Sauro lab's "
        "Tellurium, and a researcher has already read an outreach email as "
        "a false claim of credit. A disclaimer on one surface out of "
        "eighteen is a disclaimer nobody sees.",
    ),
    (
        re.compile(r"START_HERE", re.I),
        "a route to contributing",
        "This is the file a stranger lands on. Without a next step they "
        "have to guess which of eighteen repositories to read.",
    ),
]


def repos_in_map() -> List[str]:
    if not REPO_MAP.exists():
        return []
    return re.findall(r"^\| `([a-z0-9-]+)` \|", REPO_MAP.read_text(encoding="utf-8"), re.M)


def selftest() -> int:
    """Prove the checks can fail.

    On a clean tree this reports zero findings forever, and a matcher that
    matched nothing would report zero too -- which is exactly how the
    seventeen split READMEs went unwatched while a guard named "every
    shipping surface" reported green.
    """
    failures: List[str] = []

    good = (
        "# backend-main\n\nApache-2.0. See LICENSE.\n\n"
        "**Terrium is not Tellurium.** Unaffiliated with the Sauro lab.\n\n"
        "Start at START_HERE.md.\n"
    )
    for pattern, what, _ in REQUIRED:
        if not pattern.search(good):
            failures.append(f"a complete README was reported as missing {what}")

    # Each requirement must be individually detectable as absent.
    for pattern, what, _ in REQUIRED:
        stripped = pattern.sub("", good)
        if pattern.search(stripped):
            failures.append(f"removing {what} did not make it undetectable")

    if not repos_in_map():
        failures.append(
            "no repositories parsed out of docs/REPO_MAP.md -- the row "
            "pattern no longer matches the table, so this guard would pass "
            "by checking nothing."
        )

    overlap = set(NOT_OURS) & {p.stem for p in READMES.glob("*.md")}
    if overlap:
        failures.append(
            f"{sorted(overlap)} is both excluded and has a README source; "
            "one of the two is wrong."
        )

    if failures:
        print("SELFTEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"SELFTEST OK: {len(REQUIRED)} requirement(s) detectable both present "
        f"and absent, {len(repos_in_map())} repo row(s) parsed from REPO_MAP, "
        "and the exclusion list does not overlap the sources."
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    problems: List[str] = []
    repos = repos_in_map()

    if not repos:
        print(
            "FAIL: no repositories parsed out of docs/REPO_MAP.md.\n"
            "Either the table changed shape or the file moved. A guard that "
            "checks nothing\nreports the same green as one that checks "
            "everything, so this is a failure."
        )
        return 1

    checked = 0
    for repo in repos:
        if repo in NOT_OURS:
            continue
        source = READMES / f"{repo}.md"
        if not source.exists():
            problems.append(
                f"{repo}: no README source at docs/readmes/{repo}.md.\n"
                f"      It is published from REPO_MAP, so it ships with "
                f"whatever GitHub renders for an empty repository.\n"
                f"      Write one, or add it to NOT_OURS with a reason."
            )
            continue

        checked += 1
        text = source.read_text(encoding="utf-8")
        for pattern, what, why in REQUIRED:
            if not pattern.search(text):
                problems.append(
                    f"docs/readmes/{repo}.md does not carry {what}.\n"
                    f"      {why}"
                )

    print(
        f"Checked {checked} published-repository README source(s) "
        f"({len(NOT_OURS)} excluded)."
    )

    if problems:
        print(f"\nProblems ({len(problems)}):\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nThese files are what a stranger arriving from a search result "
            "sees. They do\nnot get the umbrella README, LICENSE or NOTICE "
            "unless this file sends them.\n"
            "\n(This checks the SOURCES that split_repos.sh publishes from, "
            "not the published\nrepositories themselves -- see this script.)"
        )
        return 1

    print(
        "OK: every published repository has a README source stating the "
        "licence, the\n    non-affiliation notice, and a route to "
        "contributing."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
