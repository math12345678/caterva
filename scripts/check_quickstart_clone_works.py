#!/usr/bin/env python3
"""The first command a stranger runs actually works.

WHY THIS EXISTS
---------------
START_HERE.md opens with "You are in the right place whether you are an
intern joining the team or a stranger who found this on GitHub", and the
first command it gives is:

    git clone https://github.com/Terrium-sim/main.git

That repository is not readable anonymously. A stranger following the only
document they are asked to read gets a username prompt and stops, on line
one, having seen nothing. Behind that prompt sit 2,220 tests, 67 guards and
140 architecture decisions, none of which they will ever reach.

Every other guard in this directory protects a claim made *inside* the
product. This one protects the only claim that has to be true before any of
those matter: that the thing can be obtained.

HOW IT AVOIDS BEING THE BUG IT CHECKS FOR
-----------------------------------------
A network probe that reports "unreachable" cannot tell the difference
between "this repository is private" and "this machine has no network",
and reporting the first when it means the second would be the shape this
repository has now recorded seven times: a matcher narrower than the thing
it measures says "it is not there" when it means "I could not see".

So this guard probes **known-public controls first** -- repositories that
must be cloneable if anonymous GitHub access works at all. If a control
fails, the answer is NOT "the documented URL is broken". It is "this check
could not run", and the exit code is 3.

That is the same three-state discipline the rest of the project uses:
reachable / unreachable / could-not-check, never collapsing the third into
either of the first two.

WHAT IT CHECKS
--------------
Every `git clone <url>` in a contributor-facing document resolves for a user
with no credentials, tested exactly the way a stranger's shell would do it
(`git ls-remote`, `GIT_TERMINAL_PROMPT=0`, no interactive prompt possible).

WHAT IT DOES NOT CHECK
----------------------
That the clone then builds, or that the branch named exists in a usable
state. It answers one question -- "can a stranger get this at all" -- and
says so rather than implying it vouched for the quickstart.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Documents a newcomer is actually pointed at. Not every markdown file:
#: a clone URL inside a historical record in Business/build-stages/ is a
#: description of what was true then, and rewriting those is forbidden.
PUBLISHED_DOCS = ("README.md", "START_HERE.md", "CONTRIBUTING.md")
PUBLISHED_DIRS = ("docs/readmes",)

CLONE = re.compile(r"git\s+clone\s+(?:--\S+\s+)*(https://github\.com/[^\s`'\")]+)")

#: Must be cloneable by anyone. If these fail, the network is the problem.
#: Two, from different orgs, so one repository being renamed does not turn
#: this guard into a permanent "could not check".
CONTROLS = (
    "https://github.com/sys-bio/tellurium.git",
    "https://github.com/pnpm/pnpm.git",
)

#: Must NOT be cloneable. Proves the probe can return a negative at all --
#: without this, a probe that said CLONEABLE unconditionally would pass
#: every control and vouch for everything.
NEGATIVE_CONTROL = "https://github.com/sys-bio/this-repository-does-not-exist-9f3a.git"

TIMEOUT_S = 40


class Reference(NamedTuple):
    document: str
    url: str


def reachable_anonymously(url: str) -> bool | None:
    """True / False / None, where None means the probe itself failed.

    `GIT_TERMINAL_PROMPT=0` is what makes this honest: without it git blocks
    on a username prompt, and a guard that hangs is a guard that gets removed.
    """
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="", GCM_INTERACTIVE="never")
    try:
        done = subprocess.run(
            ["git", "ls-remote", url, "HEAD"],
            env=env,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        return None
    return done.returncode == 0


def documented_clone_urls() -> list[Reference]:
    refs: list[Reference] = []
    seen: set[tuple[str, str]] = set()
    paths = [REPO_ROOT / name for name in PUBLISHED_DOCS]
    for directory in PUBLISHED_DIRS:
        paths.extend(sorted((REPO_ROOT / directory).glob("*.md")))
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        for match in CLONE.finditer(text):
            url = match.group(1)
            if not url.endswith(".git"):
                url = url.rstrip("/") + ".git"
            if (rel, url) not in seen:
                seen.add((rel, url))
                refs.append(Reference(rel, url))
    return refs


def _selftest() -> int:
    """Prove the probe can say both yes and no.

    A probe that always answered one way would pass either the positive or
    the negative control and quietly vouch for everything else.
    """
    failures = 0

    for url in CONTROLS:
        got = reachable_anonymously(url)
        if got is True:
            print(f"  [ok] positive control cloneable: {url}")
        elif got is None:
            print(f"  [could not check] probe failed on {url} — network?")
            failures += 1
        else:
            print(f"  [SELFTEST FAILED] positive control NOT cloneable: {url}")
            failures += 1

    got = reachable_anonymously(NEGATIVE_CONTROL)
    if got is False:
        print("  [ok] negative control correctly reported unreachable")
    elif got is None:
        print("  [could not check] probe failed on the negative control")
        failures += 1
    else:
        print("  [SELFTEST FAILED] a repository that does not exist read as cloneable")
        failures += 1

    # The extractor, on text rather than on the tree, so a clean tree cannot
    # make this look like it passed by matching nothing.
    sample = "run `git clone https://github.com/o/r.git` then\n git clone https://github.com/a/b\n"
    found = {m.group(1) for m in CLONE.finditer(sample)}
    if len(found) == 2:
        print("  [ok] extractor found both clone URLs, with and without .git")
    else:
        print(f"  [SELFTEST FAILED] extractor found {len(found)} of 2 URLs: {found}")
        failures += 1

    if failures:
        print(f"\nSELFTEST FAILED: {failures} case(s).")
        return 1
    print("\nSelftest passed: the probe can return both answers.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()

    # Controls FIRST. Everything below is only meaningful if these pass.
    for url in CONTROLS:
        if reachable_anonymously(url) is not True:
            print("Could not check: a known-public repository was unreachable.")
            print(f"  control: {url}")
            print()
            print("  This is 'could not check', NOT 'the documented URL is fine'")
            print("  and NOT 'the documented URL is broken'. Exiting 3.")
            return 3

    refs = documented_clone_urls()
    if not refs:
        print("No `git clone` command found in any newcomer-facing document.")
        print("  Nothing checked — that is a finding of its own if the")
        print("  quickstart is supposed to have one. Exiting 3.")
        return 3

    broken = [r for r in refs if reachable_anonymously(r.url) is not True]

    print(f"Clone commands checked: {len(refs)} (controls passed)")
    if not broken:
        print("  every one resolves for a user with no credentials.")
        print()
        print("  NOT checked: whether the clone then builds. See the docstring.")
        return 0

    print(f"\nClone commands a stranger cannot run ({len(broken)}):\n")
    for ref in broken:
        print(f"  {ref.document}")
        print(f"      git clone {ref.url}")
        print("      -> prompts for a username and stops. Anyone without push")
        print("         access to this repository sees nothing at all.\n")
    print("  Fix: publish the repository, or point the quickstart at the")
    print("  location that is actually public. A quickstart whose first")
    print("  command fails is worse than no quickstart, because it is")
    print("  believed until it is run.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
