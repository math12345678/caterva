#!/usr/bin/env python3
"""Every guard must refuse when its input is gone.

WHY THIS EXISTS
---------------
A guard that reports OK having examined nothing is this project's
most-recorded defect. ADR 0183 found one that read a JUnit report full of
failures and printed OK. ADR 0185 found three asserting a universal over an
empty set, and a follow-up found two more.

Those five were found by hand, by copying guards into an empty directory and
running them. The same procedure was run twice and produced **five false
positives against five real findings** -- a coin flip, where every real
finding survived only because it was checked individually afterwards. A
measurement that unreliable should not be a thing somebody remembers to do.

AND THEN THIS FILE WAS COMMITTED EMPTY
--------------------------------------
The first version of it shipped as **zero bytes**. A shell restore after a
sabotage run was `git checkout $G || gh api ... > $G`: the checkout failed
because the tree had no git metadata, and the fallback's redirect truncated
the file before the API call errored. CI went green, because an empty Python
file exits 0 -- so both CI steps "passed", the wiring guard saw a file that
existed, and the record said 73 guards were being starved while nothing was.

Hence `_MIN_SELF_BYTES` below. A guard has to be able to notice its own
absence, because everything else in the chain is satisfied by a file that
merely exists.

WHAT IT DOES
------------
For each `scripts/check_*.py`: build an empty directory, copy the guard into
`_starved/` -- a name no guard scans -- and run it there. Exiting 0 is a
failure of THIS guard, because there was nothing to be clean.

WHY THE SUBDIRECTORY IS NOT `scripts/`
--------------------------------------
The hand-run version copied guards into `scripts/`, which several of them
scan, so `check_package_spelling` reported reading 54 Python files (its own
siblings) and cleared its floor on them. Neither was starved at all.

WHAT "REFUSED" MEANS HERE, EXACTLY
----------------------------------
Any non-zero exit, including a guard that crashes on an import rather than
refusing in prose. That is weaker than a clean refusal and is counted
anyway, because the property under test is "does not report success on
nothing" and a traceback does not report success. Said so the pass is not
read as more than it is.

CONDITIONAL GUARDS ARE EXEMPTED, WITH REASONS
---------------------------------------------
Some guards are honestly conditional: "if the waitlist form exists, it must
not collect an email without a notice". On an empty tree the antecedent is
absent and passing is correct. Each is listed with the sentence it prints,
because an exemption whose justification is not written down is a hole
nobody can audit later.

The exemptions are checked in BOTH directions. A guard listed here that
starts refusing is reported too -- the listing has gone stale, and an
exemption that cannot expire is a rubber stamp.

Usage:
    python scripts/check_guards_refuse_on_empty.py [--selftest]
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"

#: Smallest this file can be and still be itself.
#:
#: It was committed at 0 bytes once (see the docstring). An empty Python file
#: exits 0, so every check around it was satisfied: CI ran it twice and went
#: green, `check_guard_wiring` saw a file that existed, and the ADR describing
#: it stayed true-looking. Nothing in the chain asks whether a guard contains
#: anything.
#:
#: Cheap, and it only has to catch truncation -- the failure that actually
#: happened -- not a subtly gutted implementation.
_MIN_SELF_BYTES = 2000

#: Guards that correctly pass on an empty tree, and the reason each gives.
#:
#: The reason is the guard's own sentence, not a summary: if the behaviour
#: changes the sentence changes, and the mismatch is visible to whoever reads
#: this next.
CONDITIONAL: dict[str, str] = {
    "check_llm_disclosure.py":
        "no module here can call an external LLM provider, so no disclosure "
        "is required",
    "check_port_binding.py":
        "no compose file found; nothing publishes a port here",
    "check_privacy_notice.py":
        "the waitlist form does not exist, so nothing here collects an email "
        "address",
    "check_release_artifacts.py":
        "no CI workflow publishes an artifact, so no LGPL/GPL conveyance "
        "obligation attaches",
    "check_guards_refuse_on_empty.py":
        "the meta-guard; with no guards to starve it reports that and exits 3",
}

#: A guard needing longer than this on an EMPTY tree is not refusing
#: promptly, which is its own finding -- there is nothing to be slow about.
TIMEOUT_S = 60


#: Top-level directories to create, empty, for the SHAPED probe.
#:
#: Derived from the repository rather than listed by hand, so a renamed or
#: added scan root is covered without anyone remembering to update this.
def _repo_top_level_dirs() -> list[str]:
    return sorted(
        p.name for p in REPO_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def starve(guard: Path, shaped: bool = False) -> tuple[int, str]:
    """Run one guard against an empty tree. Returns (exit code, first line).

    `shaped=True` creates every top-level directory of the real repository,
    all empty. That is a different kind of broken from an absent tree, and a
    sharper one: a guard can refuse because its scan root is missing while
    saying nothing when the root is present and its contents are gone -- a
    checkout that failed halfway, or a directory whose files moved.

    `check_python_bug_lints` was exactly this. It refuses with "none of
    ['Tests', 'scripts', 'Terium'] exist", and with those three present and
    empty it reported a clean lint over zero lines (ADR 0186).
    """
    with tempfile.TemporaryDirectory() as tmp:
        if shaped:
            for name in _repo_top_level_dirs():
                (Path(tmp) / name).mkdir(exist_ok=True)
        holder = Path(tmp) / "_starved"
        holder.mkdir(exist_ok=True)
        copy = holder / guard.name
        shutil.copy2(guard, copy)
        try:
            done = subprocess.run(
                [sys.executable, str(copy)],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return 124, "timed out"
        output = (done.stdout or done.stderr or "").strip().splitlines()
        return done.returncode, (output[0][:88] if output else "(no output)")


def main() -> int:
    own_size = Path(__file__).stat().st_size
    if own_size < _MIN_SELF_BYTES:
        print(
            f"FAIL: this guard is {own_size} bytes, below {_MIN_SELF_BYTES}. "
            "It has been truncated,\n"
            "      and an empty Python file exits 0 -- which is how a "
            "previous version of it\n"
            "      shipped as 0 bytes with CI green. Restore it from history.",
            file=sys.stderr,
        )
        return 1

    guards = sorted(
        p for p in SCRIPTS.glob("check_*.py") if p.name != Path(__file__).name
    )
    if not guards:
        # A meta-guard that found no guards has checked nothing, and saying
        # OK would be the exact defect it exists to catch.
        print("Could not check: no `scripts/check_*.py` found. Exiting 3.")
        return 3

    passed_on_nothing: list[tuple[str, str]] = []
    shaped_only: list[tuple[str, str]] = []
    stale_exemptions: list[str] = []
    empty_guards: list[tuple[str, int]] = []
    refused = 0
    conditional_ok = 0

    for guard in guards:
        size = guard.stat().st_size
        if size == 0:
            # Not starved, just gone. Reported separately because "passes on
            # nothing" would understate it: there is no guard here at all.
            empty_guards.append((guard.name, size))
            continue
        code, first = starve(guard)
        shaped_code, shaped_first = starve(guard, shaped=True)
        exempt = guard.name in CONDITIONAL
        if shaped_code == 0 and not exempt and code != 0:
            # Refused on an absent tree, passed on a present-but-empty one.
            # Reported separately because the guard is not simply missing a
            # floor -- it HAS a refusal and the refusal is too narrow.
            shaped_only.append((guard.name, shaped_first))
        if code == 0 and not exempt:
            passed_on_nothing.append((guard.name, first))
        elif code != 0 and exempt:
            stale_exemptions.append(guard.name)
        elif exempt:
            conditional_ok += 1
        else:
            refused += 1

    # The outcomes must add up to the number starved. An earlier version
    # folded exempt-and-passing into `refused` and printed "73 starved, 73
    # refused, 4 exempt" -- three true-looking numbers that cannot describe
    # the same 73 guards. Asserted rather than trusted, because a total that
    # does not reconcile is how a report starts lying quietly.
    accounted = (refused + conditional_ok + len(passed_on_nothing)
                 + len(stale_exemptions) + len(empty_guards))
    assert accounted == len(guards), (
        f"counted {accounted} outcomes for {len(guards)} guards"
    )

    print(f"Guards starved: {len(guards)}")
    print(f"  refused on an empty tree      : {refused}")
    print(f"  exempt, and still conditional : {conditional_ok}")
    print(f"  also refused a shaped-but-empty tree: "
          f"{refused - len(shaped_only)} of {refused}")

    problems = False

    if empty_guards:
        problems = True
        print(f"\nEmpty guard file(s) ({len(empty_guards)}):\n")
        for name, size in empty_guards:
            print(f"  {name} is {size} bytes")
        print(
            "\n  A zero-byte Python file exits 0, so every check around it\n"
            "  passes: CI runs it green, the wiring guard sees a file that\n"
            "  exists, and any record describing it stays true-looking."
        )

    if passed_on_nothing:
        problems = True
        print(f"\nReported success having examined nothing "
              f"({len(passed_on_nothing)}):\n")
        for name, line in passed_on_nothing:
            print(f"  {name}")
            print(f"      {line}\n")
        print(
            "  Over an empty set every universal is true, so this sentence\n"
            "  would also be printed by a renamed directory or a glob that\n"
            "  stopped matching. Give the guard a floor -- see ADR 0185, and\n"
            "  `check_public_images_reviewed` for the idiom -- or, if it is\n"
            "  honestly conditional, add it to CONDITIONAL with the sentence\n"
            "  it prints."
        )

    if shaped_only:
        problems = True
        print(f"\nRefused an ABSENT tree, passed a present-but-EMPTY one "
              f"({len(shaped_only)}):\n")
        for name, line in shaped_only:
            print(f"  {name}")
            print(f"      {line}\n")
        print(
            "  The refusal is too narrow. It covers a deleted scan root and\n"
            "  not a root whose contents are gone -- a checkout that failed\n"
            "  halfway, or files that moved. Count what was examined and put\n"
            "  a floor under it (ADR 0185)."
        )

    if stale_exemptions:
        problems = True
        print(f"\nExempted, but now refuses ({len(stale_exemptions)}):\n")
        for name in stale_exemptions:
            print(f"  {name}")
        print(
            "\n  The exemption is stale. It was recorded because the guard\n"
            "  passed correctly on nothing; it no longer does, so the entry\n"
            "  is protecting a case that cannot arise. Remove it."
        )

    if problems:
        return 1

    print("\nOK: every guard either refuses on an empty tree or is listed as\n"
          "    conditional with the sentence it prints.")
    return 0


def selftest() -> int:
    """Prove this can return both answers.

    Without this the guard passes on a clean tree forever and a broken
    starve() would look identical to a working one -- which is the shape
    this file exists to catch, and it is not exempt from itself.
    """
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        always_ok = Path(tmp) / "check_always_ok.py"
        # Wording matters even in a fixture. The first version of this line
        # printed a stock dismissal -- the phrase a page uses to tell a
        # reader there is nothing here worth examining -- and
        # `check_prompt_injection` flagged it as a trust-assertion,
        # correctly. A scanner cannot tell a test fixture from a real
        # reassurance and should not have to.
        #
        # The string is arbitrary, so it was changed rather than exempted: a
        # baseline entry for a phrase chosen carelessly is a suppression
        # nobody could justify later.
        #
        # Described rather than quoted. Repeating the phrase here made THIS
        # file trip the same rule on the next run -- the trap already
        # recorded three times in check_prompt_injection.py's own exemption
        # notes, and walked into anyway.
        always_ok.write_text("print('OK: 0 findings')\n", encoding="utf-8")
        code, _ = starve(always_ok)
        ok = code == 0
        failures += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] a guard that always passes is "
              f"seen to pass on nothing")

        always_fail = Path(tmp) / "check_always_fail.py"
        always_fail.write_text(
            "import sys\nprint('FAIL: nothing was checked')\nsys.exit(1)\n",
            encoding="utf-8",
        )
        code, first = starve(always_fail)
        ok = code == 1 and "nothing was checked" in first
        failures += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] a guard that refuses is seen to "
              f"refuse, and its reason is captured")

        # An EMPTY guard exits 0 and would otherwise read as "passes on
        # nothing", which understates it. This is the case that shipped.
        empty = Path(tmp) / "check_empty.py"
        empty.write_text("", encoding="utf-8")
        code, _ = starve(empty)
        ok = code == 0 and empty.stat().st_size == 0
        failures += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] an empty guard exits 0 -- which "
              f"is why size is checked before starving")

        # The starve must be real: a guard reading its own directory must
        # find only itself, never the repository it came from.
        counter = Path(tmp) / "check_counts.py"
        counter.write_text(
            "import pathlib\n"
            "root = pathlib.Path(__file__).resolve().parent.parent\n"
            "print('files:', sum(1 for p in root.rglob('*') if p.is_file()))\n",
            encoding="utf-8",
        )
        _, first = starve(counter)
        ok = first.strip() == "files: 1"
        failures += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] the tree really is empty "
              f"({first.strip()}); a guard cannot see the real repository")

    if failures:
        print(f"\nFAIL: {failures} selftest case(s) failed.")
        return 1
    print("\nSelftest passed: the starve is real and reports both outcomes.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    raise SystemExit(main())