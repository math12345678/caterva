#!/usr/bin/env python3
"""Everything that can be checked before publishing, in one command.

WHY THIS EXISTS
---------------
Publishing is the last thing standing between Terrium and anybody using it.
`check_quickstart_clone_works.py` has failed on every CI run since
2026-08-21 for exactly one reason: no documented `git clone` works for a
stranger, because the repositories are private (ADR 0143).

`docs/PUBLISHING.md` is a careful 140-line procedure, and that is the
problem. A one-off manual sequence with five sections is a thing people put
off, and the longer it is put off the more of this repository's work stays
behind a login.

So: everything that can be verified WITHOUT credentials is verified here, in
one command, and the output says either "the only thing left is the push" or
exactly what is not ready.

WHAT IT CANNOT DO, AND SAYS SO
------------------------------
It cannot push, create a repository, or check whether one exists — all three
need credentials this sandbox has never had. It does not pretend otherwise:
the last line of a passing run names the manual steps that remain rather
than implying the job is done.

That distinction is the whole point. A preflight that reported "ready to
publish" while unable to see GitHub would be a check that cannot fail, in
the one place where being wrong is most expensive.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Each entry: (script, args, what a failure would mean for publication).
#:
#: Every one of these already runs somewhere. Gathering them is not a new
#: check, it is a route through the existing ones aimed at one question --
#: and a route is what was missing.
CHECKS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "check_published_repo_readmes.py", (),
        "a split repository would land with no README, or one that states "
        "no licence and routes nobody to CONTRIBUTING. Fifteen of seventeen "
        "shipped that way once.",
    ),
    (
        "check_split_repo_legal_files.py", (),
        "a published repository would ship without LICENSE or NOTICE. "
        "Apache-2.0 4(a) and 4(d) require both to travel.",
    ),
    (
        "check_non_affiliation_notice.py", (),
        "a shipping surface would omit the Tellurium non-affiliation notice "
        "— the mistake that already caused one researcher to read a cold "
        "email as a false claim of credit.",
    ),
    (
        "check_data_source_attribution.py", (),
        "BRENDA's CC BY 4.0 attribution would be missing from something "
        "published.",
    ),
    (
        "check_dependency_licenses.py", (),
        "a dependency would ship without a recorded grant of permission.",
    ),
    (
        "check_no_fabricated_endorsements.py", (),
        "a public page would claim an endorsement that is not on record.",
    ),
    (
        "check_documented_counts.py", (),
        "a published document would state a test or guard count the "
        "repository does not have.",
    ),
    (
        "check_investor_claims.py", (),
        "an investor- or funder-facing document would carry a stale figure. "
        "This has happened four times, and every time it understated — "
        "which is luck, not policy.",
    ),
    (
        "check_doc_links.py", (),
        "a link in a contributor-facing document would 404 for the first "
        "person who follows it.",
    ),
    (
        "check_no_tellurium_integration_claims.py", (),
        "a published document would claim Terrium is built on Tellurium "
        "while NOTICE says it is not.",
    ),
)

#: Named, not run. Each needs something this script does not have.
CANNOT_CHECK: tuple[tuple[str, str], ...] = (
    (
        "Do the eighteen repositories exist under github.com/Terrium-sim?",
        "needs credentials. An anonymous probe cannot tell 'private' from "
        "'does not exist' — both answer 404 — so guessing would be the "
        "narrower-matcher mistake this project has recorded nine times.",
    ),
    (
        "Does the split push cleanly?",
        "`scripts/split_repos.sh` defaults to a dry run and is the right "
        "tool; it needs credentials to do the half that matters. Run it "
        "yourself: PUBLISHING.md sections 1 and 2.",
    ),
    (
        "Is the published tree what the split intended?",
        "nothing compares a pushed repository against the branch it came "
        "from. Worth building the day after publication, not before.",
    ),
)


def run(script: str, args: tuple[str, ...]) -> tuple[bool, str]:
    path = REPO_ROOT / "scripts" / script
    if not path.is_file():
        return False, f"{script} does not exist"
    done = subprocess.run(
        [sys.executable, str(path), *args],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=600,
    )
    if done.returncode == 0:
        return True, ""
    tail = [
        line for line in (done.stdout + done.stderr).splitlines()
        if line.strip()
    ][-6:]
    return False, "\n".join("      " + line for line in tail)


def main() -> int:
    print("Publication preflight — everything checkable without credentials\n")

    blocking: list[tuple[str, str, str]] = []
    for script, args, consequence in CHECKS:
        label = script.replace("check_", "").replace(".py", "").replace("_", " ")
        # No carriage-return progress line. It looks tidy in a terminal and
        # leaves half-overwritten duplicates in anything that captures the
        # output -- a log, a CI step, a paste into an issue. The place this
        # gets read is often not a terminal.
        passed, detail = run(script, args)
        print(f"  {'ok' if passed else 'XX'}  {label}", flush=True)
        if not passed:
            blocking.append((label, consequence, detail))

    print()
    if blocking:
        print(f"NOT READY: {len(blocking)} check(s) would ship something wrong.\n")
        for label, consequence, detail in blocking:
            print(f"  {label}")
            print(f"      If published as-is: {consequence}")
            if detail:
                print(detail)
            print()
        return 1

    print("Every offline check passes. Nothing in the tree would ship wrong.\n")
    print("WHAT THIS DID NOT CHECK, and cannot:\n")
    for question, why in CANNOT_CHECK:
        print(f"  {question}")
        print(f"      {why}\n")
    print("Remaining, in order — docs/PUBLISHING.md:")
    print("  1. ./scripts/split_repos.sh              (dry run, builds branches)")
    print("  2. ./scripts/split_repos.sh --push-https (needs credentials)")
    print("  3. make the repositories public")
    print()
    print("On step 3, two guards change state with no code edit:")
    print("  check_quickstart_clone_works              red  -> green")
    print("  check_availability_notice_matches_reality green -> RED,")
    print("      telling you to delete the 'Not public yet' notice it")
    print("      was written to make expire.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
