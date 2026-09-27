#!/usr/bin/env python3
"""Every published repository ships LICENSE and NOTICE, not just the umbrella.

WHY THIS EXISTS
---------------
Caterva is published as eighteen repositories under github.com/Terrium-sim.
`scripts/split_repos.sh` regenerates seventeen of them from the monorepo.

On 2026-08-16, `LICENSE` appeared exactly once in that 655-line script: in the
file list for the `main` umbrella repository. `NOTICE` appeared nowhere at all.

Seventeen published repositories therefore carried Apache-2.0 source code with
no licence file. This is not a missing formality. Under copyright a work
published with no stated licence is all-rights-reserved, and GitHub renders it
that way. Somebody who found `Terrium-sim/backend-main` from a search result
and wanted to contribute was looking at code they had no stated permission to
use, copy, or modify -- which defeats the entire purpose of publishing them.

Apache-2.0 is explicit about both halves:

  4(a) "You must give any other recipients of the Work or Derivative Works a
       copy of this License."
  4(d) requires the NOTICE file to travel with any distribution.

The monorepo satisfied neither for those seventeen.

HOW IT HAPPENED
---------------
`split_repos.sh` builds repositories by two paths that share no code:

    history repos   -> add_scaffold_commit()  (preserves git history)
    file-set repos  -> build_fileset()        (one initial commit)

`LICENSE` was passed as an argument to a single `build_fileset main ...` call.
It was never a property of *building a repository*, only a file that one
repository happened to list. So the other seventeen never got it, and the
second code path could not have got it even in principle.

That is the same shape this repository has now found nine times: a correct
action on too narrow a scope. `check_published_repo_readmes.py` names five
instances found on 2026-08-15 alone, and its own "WHAT IT DOES NOT CHECK"
section says it verifies README *sources* and not what the split actually
ships. This guard covers the gap that docstring left open.

WHAT IT CHECKS
--------------
1. LICENSE and NOTICE both exist at the monorepo root (nothing can be copied
   from a file that is not there).
2. `split_repos.sh` defines a helper that copies both.
3. **Every** repo-producing function in the script calls it. This is the check
   that matters: adding a third build path without the call is the way this
   defect returns.

WHAT IT DOES NOT CHECK
----------------------
That the eighteen repositories on GitHub right now contain the files. That
needs network access and for the split to have been re-run and pushed. This
guard checks what is knowable offline: that running the split *would* place
them. Re-running `scripts/split_repos.sh` and pushing is a separate,
deliberate act, and until it happens the published repositories keep whatever
they already have.

Run with --selftest to prove the matcher can fail.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPLIT_SCRIPT = REPO_ROOT / "scripts" / "split_repos.sh"

# The files Apache-2.0 requires travel with a distribution.
REQUIRED_AT_ROOT = ("LICENSE", "NOTICE")

# A repository is not published unless one of these produced it. If a third
# build path is ever added, add it here -- and the floor below makes a typo
# in one of these names loud instead of silent.
REPO_BUILDERS = ("add_scaffold_commit", "build_fileset")

# If the script stops defining this many builders, the guard is looking at a
# file it no longer understands and must say so rather than report success.
_MIN_BUILDERS = 2


def _function_body(script: str, name: str) -> str | None:
    """Return the body of shell function `name`, or None if it is not defined."""
    match = re.search(rf"^{re.escape(name)}\(\)\s*\{{", script, re.M)
    if match is None:
        return None
    start = match.end()
    depth = 1
    for i in range(start, len(script)):
        if script[i] == "{":
            depth += 1
        elif script[i] == "}":
            depth -= 1
            if depth == 0:
                return script[start:i]
    return script[start:]


def _copies(body: str, filename: str) -> bool:
    """True only if `body` actually copies `filename` somewhere.

    Deliberately not `filename in body`. The first version of this guard tested
    for the mention, and its own selftest caught it: a helper whose `cp` line
    had been deleted still contained `[ -f "$ROOT/NOTICE" ]` and so still
    "mentioned" NOTICE. It passed a script that shipped no NOTICE at all.
    A guard that accepts the defect it exists to catch is worse than none.
    """
    return re.search(rf"cp\s+\S*{re.escape(filename)}\S*\s+\S*{re.escape(filename)}", body) is not None


def _helper_name(script: str) -> str | None:
    """Find the helper that copies the legal files, by what it does."""
    for match in re.finditer(r"^(\w+)\(\)\s*\{", script, re.M):
        name = match.group(1)
        body = _function_body(script, name) or ""
        if all(_copies(body, f) for f in REQUIRED_AT_ROOT):
            return name
    return None


def check(script_text: str | None = None) -> list[str]:
    """Return a list of problems; empty means healthy."""
    problems: list[str] = []

    for filename in REQUIRED_AT_ROOT:
        path = REPO_ROOT / filename
        if not path.is_file():
            problems.append(f"{filename} is missing from the repository root")
        elif path.stat().st_size == 0:
            problems.append(f"{filename} exists but is empty")

    script = script_text if script_text is not None else SPLIT_SCRIPT.read_text()

    helper = _helper_name(script)
    if helper is None:
        problems.append(
            "split_repos.sh defines no helper that copies both LICENSE and "
            "NOTICE, so no split repository can receive them"
        )
        return problems

    defined = [b for b in REPO_BUILDERS if _function_body(script, b) is not None]
    if len(defined) < _MIN_BUILDERS:
        problems.append(
            f"expected at least {_MIN_BUILDERS} repo-building functions, found "
            f"{len(defined)} ({', '.join(defined) or 'none'}). The guard no "
            f"longer recognises this script; it is not reporting success."
        )
        return problems

    for builder in defined:
        body = _function_body(script, builder) or ""
        if not re.search(rf"\b{re.escape(helper)}\b", body):
            problems.append(
                f"{builder}() builds a published repository but never calls "
                f"{helper}(), so the repositories it produces ship without "
                f"LICENSE and NOTICE (Apache-2.0 4(a) and 4(d))"
            )

    # A shell function must be defined before the line that calls it runs.
    helper_def = re.search(rf"^{re.escape(helper)}\(\)\s*\{{", script, re.M)
    for builder in defined:
        call = re.search(rf"^\s*{re.escape(builder)}\s+\S", script, re.M)
        if helper_def and call and call.start() < helper_def.start():
            problems.append(
                f"{helper}() is defined at byte {helper_def.start()} but "
                f"{builder} is invoked at byte {call.start()}; at that point "
                f"the helper does not exist yet and the copy silently fails"
            )

    return problems


def _selftest() -> int:
    """Prove the matcher fails on a script that has the defect."""
    healthy = SPLIT_SCRIPT.read_text()
    failures = []

    if check(healthy):
        failures.append(f"the real script should be clean, got: {check(healthy)}")

    # Remove the call from build_fileset only -- the one-sided case.
    body = _function_body(healthy, "build_fileset") or ""
    mutated = healthy.replace(body, body.replace("add_legal_files", "true #"), 1)
    if not any("build_fileset" in p for p in check(mutated)):
        failures.append("removing the call from build_fileset was not detected")

    # A helper that copies LICENSE but forgets NOTICE is not a helper.
    no_notice = healthy.replace('cp "$ROOT/NOTICE" "$d/NOTICE"', "true")
    no_notice = no_notice.replace(
        "printf 'split_repos.sh: NOTICE missing from %s -- Apache-2.0 4(d)\\n' \"$ROOT\" >&2",
        "true",
    )
    if not check(no_notice):
        failures.append("a helper that never copies NOTICE was accepted")

    # No builders at all must trip the floor, not report success.
    stripped = re.sub(r"^(add_scaffold_commit|build_fileset)\(\)", r"x_\1()", healthy, flags=re.M)
    if not any("no longer recognises" in p for p in check(stripped)):
        failures.append("the builder floor did not fire when no builders were found")

    for f in failures:
        print(f"  selftest FAIL: {f}")
    if failures:
        return 1
    print("OK: selftest passed -- the matcher fails on all four defective scripts.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true", help="prove it can fail")
    args = parser.parse_args()

    if args.selftest:
        return _selftest()

    if not SPLIT_SCRIPT.is_file():
        print(f"FAIL: {SPLIT_SCRIPT} does not exist")
        return 1

    problems = check()
    if problems:
        print("FAIL: published repositories would ship without their licence")
        for p in problems:
            print(f"  - {p}")
        print(
            "\nApache-2.0 4(a) requires every recipient get a copy of the "
            "License; 4(d) requires NOTICE to travel with it."
        )
        return 1

    helper = _helper_name(SPLIT_SCRIPT.read_text())
    print(
        f"OK: LICENSE and NOTICE exist at the root, and all "
        f"{len(REPO_BUILDERS)} repo-building path(s) call {helper}()."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
