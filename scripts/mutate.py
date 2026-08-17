#!/usr/bin/env python3
"""
mutate.py

Run a mutation against the working tree and report, honestly, whether the
test suite caught it.

WHY THIS EXISTS
---------------
Every mutation in this project has been run by hand. That is how the
findings in ADR 0026 onwards were made, and it works -- but the harness has
now produced a wrong answer in three distinct ways, each of which cost real
time and one of which left a mutation sitting in the tree:

1. **The patch never applied.** A search string that spanned a source line
   break, or used four-space indentation against two-space source, matched
   nothing. The suite ran unmutated, passed, and the mutation was recorded
   as "not caught" -- a false accusation against a test that was fine.
   (ADR 0051, ADR 0056; two agents hit this independently on the same day.)

2. **The suite never ran.** A mutation that made a block unreachable broke
   the build, and jest printed `Tests: 0 total`. `0 total` is not
   `0 failed`: a suite that cannot compile has judged nothing. Reading it as
   "not caught" credits the tests with a verdict they never gave.
   (ADR 0065.)

3. **The restore silently failed.** `/tmp` was not writable, so every `cp`
   restore did nothing and five mutations accumulated in the tree. The tell
   was a run labelled "RESTORED" reporting 14 failures.

All three share a shape: **the harness reported a result it had not
established.** That is the same defect this codebase spends its time finding
in its own product, so it is worth fixing in the tooling with the same care.

WHAT THIS GUARANTEES
--------------------
Before reporting anything, it establishes:

- the baseline suite is GREEN (a mutation judged against a red baseline
  means nothing)
- the baseline suite actually RAN tests (a nonzero count)
- the search string occurs EXACTLY ONCE (zero = no-op, many = ambiguous)
- the file content CHANGED on disk
- the mutated suite actually RAN tests
- the restore put the file back BYTE-FOR-BYTE

If any of those cannot be established, the verdict is INDETERMINATE, never
"not caught". Three states, not two -- the same discipline the resolver uses
for `resolved` / `unresolvable` / `not_reported`.

USAGE
-----
    python3 scripts/mutate.py \\
        --file src/engine/parameter-sweep.ts \\
        --find 'finalValue: null,' \\
        --replace 'finalValue: 0,' \\
        --test 'npx jest src/engine/__tests__/parameter-sweep.test.ts'

Or a whole set, so an ADR's mutation table is reproducible:

    python3 scripts/mutate.py --set docs/mutations/adr-0058.json

Set file format:

    {
      "test": "npx jest src/engine/__tests__/parameter-sweep.test.ts",
      "mutations": [
        {"id": "M1", "description": "crash recorded as 0 again",
         "file": "src/engine/parameter-sweep.ts",
         "find": "finalValue: null,", "replace": "finalValue: 0,"}
      ]
    }

`--selftest` runs the harness against itself: it verifies that a mutation
which does not apply is reported INDETERMINATE rather than "not caught".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Where the pre-mutation content of the file currently under mutation is
#: parked, and the record pointing at it.
#:
#: WHY A JOURNAL AND NOT JUST `finally`
#: ------------------------------------
#: The first version of this harness restored in a `finally` block. It was
#: then run under `timeout`, exceeded the limit mid-mutation, and was killed
#: -- `finally` does not run on SIGKILL. The mutation stayed in the working
#: tree and a subsequent test run reported a failure that looked like a real
#: regression.
#:
#: That is the `/tmp`-not-writable incident again (five mutations left in the
#: tree by silently failing restores), reproduced by the very tool written to
#: prevent it. A cleanup path that may not run is not a guarantee.
#:
#: So the original bytes are written to disk BEFORE the mutation, and every
#: run checks for a leftover journal first. Recovery belongs to the next run,
#: which is the only participant guaranteed to still be alive.
JOURNAL_DIR = REPO_ROOT / ".mutate-journal"
JOURNAL_FILE = JOURNAL_DIR / "in-flight.json"
JOURNAL_CONTENT = JOURNAL_DIR / "original.bak"


def is_inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT)
        return True
    except (ValueError, OSError):
        return False


def pid_is_alive(pid: int) -> bool:
    """Whether a process still exists. Used to refuse clobbering a live run."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists, owned by somebody else. Alive for our purposes.
        return True
    except OSError:
        return False


def open_journal(file_path: Path, original_bytes: bytes) -> None:
    """Record the pre-mutation bytes, but only for files inside the repo.

    The self-test mutates files in a `TemporaryDirectory`, which needs no
    protection: if the process dies the directory goes with it. Journaling
    them was worse than pointless. The first cross-session run of this tool
    crashed on a journal left by ANOTHER AGENT's self-test, pointing at
    `/sessions/<their-sandbox>/tmp/.../subject.txt` -- a path this process
    cannot even stat. The harness died with a PermissionError traceback,
    which reads as "the tool is broken" rather than "there is a stale
    journal".

    That was self-inflicted twice over: `mutate.py --selftest` is wired into
    verify_build.py, so every agent running the build writes one of these.
    """
    if not is_inside_repo(file_path):
        return

    JOURNAL_DIR.mkdir(exist_ok=True)
    JOURNAL_CONTENT.write_bytes(original_bytes)
    JOURNAL_FILE.write_text(
        json.dumps({
            # RELATIVE to the repository root, because several agents mount
            # THE SAME repository at different absolute paths
            # (/sessions/<their-sandbox>/mnt/Terrium/...). An absolute path
            # is only meaningful in the sandbox that wrote it, so a journal
            # naming a real repo file looked "outside the repository" to
            # every other agent and was discarded -- with a message calling
            # it a temporary file, which it was not.
            #
            # Found when a journal from another sandbox named NOTICE. Their
            # run had restored it (the hashes matched), so nothing was lost
            # this time. Nothing about the design made that true.
            "relative": str(file_path.resolve().relative_to(REPO_ROOT))
                        if is_inside_repo(file_path) else None,
            "file": str(file_path),
            "sha256": hashlib.sha256(original_bytes).hexdigest(),
            # Several agents work in this repository at once. A journal that
            # does not say who wrote it cannot be distinguished from one
            # belonging to a run still in progress.
            "pid": os.getpid(),
        }),
        encoding="utf-8",
    )


def close_journal() -> None:
    for path in (JOURNAL_FILE, JOURNAL_CONTENT):
        if path.exists():
            path.unlink()


def recover_journal() -> bool:
    """Restore a file left mutated by a run that was killed.

    Returns True if a recovery happened, so the caller can report it rather
    than proceeding as if the tree were clean.
    """
    if not JOURNAL_FILE.exists() or not JOURNAL_CONTENT.exists():
        return False

    # Everything below is guarded. Recovery runs before any real work, so a
    # journal THIS process cannot read must not be able to stop the tool.
    #
    # The branch further down already handles "the directory is gone". It
    # does not handle "the directory cannot be read", which is what happens
    # in a repository several agents share: `mutate.py --selftest` is wired
    # into verify_build.py, so every agent running the build writes a journal
    # naming a temp file under THEIR sandbox. The first cross-session run
    # here died with
    #     PermissionError: '/sessions/<other-agent>/tmp/.../subject.txt'
    # raised from `target.parent.is_dir()` -- a traceback that reads as "the
    # tool is broken" rather than "there is a stale journal".
    try:
        record = json.loads(JOURNAL_FILE.read_text(encoding="utf-8"))
        target = Path(record["file"])
        original = JOURNAL_CONTENT.read_bytes()
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"NOTE: discarding an unreadable mutation journal ({exc}).", file=sys.stderr)
        close_journal()
        return False

    # A journal written in another sandbox names a path this one cannot
    # resolve. If it recorded a repo-relative path, re-anchor it here: the
    # file is genuinely ours, reached by a different mount.
    relative = record.get("relative")
    if relative and not is_inside_repo(target):
        target = REPO_ROOT / relative
        print(
            f"NOTE: re-anchoring a journal written in another sandbox onto\n"
            f"      {relative} in this checkout.",
            file=sys.stderr,
        )

    if not is_inside_repo(target):
        # In practice another sandbox's self-test temp directory. There is
        # nothing here to repair and nothing at risk.
        print(
            f"NOTE: discarding a mutation journal for {target}, which is outside\n"
            f"      this repository and records no repo-relative path (in practice\n"
            f"      another sandbox's temporary file).",
            file=sys.stderr,
        )
        close_journal()
        return False

    other_pid = record.get("pid")
    if other_pid and other_pid != os.getpid() and pid_is_alive(other_pid):
        # Restoring a file a LIVE run is mutating would corrupt its result
        # and leave the tree in a state neither process expects.
        print(
            f"REFUSING: a mutation run (pid {other_pid}) appears to be in progress\n"
            f"          on {target}. Two concurrent runs would clobber each other's\n"
            f"          journal. Wait for it, or clear .mutate-journal/ if you are\n"
            f"          certain that process is gone.",
            file=sys.stderr,
        )
        raise SystemExit(3)

    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == record["sha256"]:
        # Already clean -- a previous run restored it and died before
        # clearing the journal. Nothing to do beyond tidying up.
        close_journal()
        return False

    # The target can be gone entirely -- most often because the run that
    # wrote the journal was operating inside a TemporaryDirectory that has
    # since been removed, which is exactly what `--selftest` does.
    #
    # Before this branch, `write_bytes` raised FileNotFoundError and the
    # whole script died on startup, so the FIRST selftest run passed and
    # every run after it crashed. Recovery that cannot fail safely is worse
    # than no recovery: it turns a stale journal into a permanently unusable
    # tool, and the traceback points at the recovery rather than the cause.
    #
    # Nothing to restore is not an error. It is reported and cleared.
    if not target.parent.is_dir():
        close_journal()
        print(
            f"STALE JOURNAL: {target} no longer exists (its directory is\n"
            f"               gone), so there is nothing to restore. The\n"
            f"               journal has been cleared. This is normal after a\n"
            f"               run inside a temporary directory.\n",
            file=sys.stderr,
        )
        return False

    target.write_bytes(original)
    close_journal()
    print(
        f"RECOVERED: {target} was left mutated by a previous run that did not\n"
        f"           finish (killed, or the machine went away). It has been\n"
        f"           restored from the journal. Re-run whatever suite you were\n"
        f"           doubting -- the failure you saw was this, not your code.\n",
        file=sys.stderr,
    )
    return True


def install_signal_handlers() -> None:
    """Turn SIGTERM/SIGINT into an exception so `finally` still runs.

    `timeout` sends SIGTERM first, so this covers the common case; the
    journal covers SIGKILL, which cannot be caught at all.
    """

    def raise_on_signal(signum, _frame):
        raise KeyboardInterrupt(f"received signal {signum}")

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, raise_on_signal)
        except (ValueError, OSError):
            pass  # not the main thread, or the platform disallows it

#: Test-count patterns for the runners this repository uses.
#:
#: A runner whose output matches none of these yields "unknown", which
#: becomes an INDETERMINATE verdict rather than a silent assumption that the
#: suite ran. Adding a runner means adding a pattern here, deliberately.
COUNT_PATTERNS = [
    # jest: "Tests:       23 passed, 23 total"
    re.compile(r"^Tests:\s+.*?(\d+)\s+total", re.MULTILINE),
    # vitest: "Tests  11 passed (11)"
    re.compile(r"^\s*Tests\s+.*?\((\d+)\)", re.MULTILINE),
    # pytest: "23 passed, 1 skipped in 4.2s" / "1 failed, 22 passed in 4.2s"
    re.compile(r"^=*\s*(?:\d+ \w+, )*(\d+) (?:passed|failed)", re.MULTILINE),
]

FAIL_PATTERNS = [
    re.compile(r"^Tests:\s+(\d+)\s+failed", re.MULTILINE),          # jest
    re.compile(r"^\s*Tests\s+(\d+)\s+failed", re.MULTILINE),        # vitest
    re.compile(r"^=*\s*(\d+) failed", re.MULTILINE),                # pytest
]


#: Colour escape sequences, stripped before any parsing.
#:
#: vitest writes `\x1b[2m      Tests \x1b[22m...35 passed...(35)`. The
#: patterns below anchor with `^\s*`, which does not match an escape byte,
#: so a colourised runner reported no test count at all and every verdict
#: became INDETERMINATE.
#:
#: The harness FAILED SAFE -- it refused the baseline and printed the runner
#: output rather than guessing -- which is the design working, and is why
#: this was a five-minute fix instead of a wrong mutation table. But a tool
#: that cannot read half the runners in the repository is not much use, and
#: the first use against vitest is what found it.
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@dataclass
class SuiteRun:
    """What actually happened when the suite was invoked."""

    exit_code: int
    raw_output: str

    @property
    def output(self) -> str:
        """Runner output with colour escapes removed."""
        return ANSI_RE.sub("", self.raw_output)

    @property
    def tests_run(self) -> int | None:
        """How many tests executed, or None if the output does not say.

        None is not zero. A suite that failed to compile prints no count at
        all, and treating that as "zero tests, none failed" is the exact
        misreading this harness exists to prevent.
        """
        for pattern in COUNT_PATTERNS:
            match = pattern.search(self.output)
            if match:
                return int(match.group(1))
        return None

    @property
    def failures(self) -> int:
        for pattern in FAIL_PATTERNS:
            match = pattern.search(self.output)
            if match:
                return int(match.group(1))
        return 0

    @property
    def ran(self) -> bool:
        count = self.tests_run
        return count is not None and count > 0


#: Runners whose module cache must be disabled for a mutation run.
#:
#: WHY THE MTIME BUMP WAS NOT ENOUGH
#: ---------------------------------
#: ADR 0083 recorded this harness giving two different verdicts for one
#: mutation, and fixed it by pushing the mutated file's mtime forward. That
#: was reasoned and it was WRONG -- or at least insufficient. Measured
#: afterwards, one mutation returned three different answers across runs:
#:
#:     run 1  NOT CAUGHT     (34 tests ran, all passed)
#:     run 2  INDETERMINATE  (0 tests ran)
#:     run 3  INDETERMINATE  (0 tests ran, with --no-cache)
#:
#: The mutation makes the file fail to compile, so INDETERMINATE is the
#: honest answer and run 1 was the lie: jest served a CACHED transform of
#: the pre-mutation source, ran the old code, and passed. A stale cache can
#: only ever manufacture a false NOT CAUGHT, which is the single most
#: damaging verdict this tool can produce -- it reads as a real gap in
#: somebody's tests.
#:
#: So the cache is disabled rather than out-manoeuvred. The flag is injected
#: and announced rather than left to the set file's author, because a
#: requirement that depends on everyone remembering it is not a requirement.
CACHE_FLAGS = {
    "jest": "--no-cache",
    "vitest": "--no-cache",
}


def without_cache(command: str) -> tuple[str, str | None]:
    """Return (command, note) with the runner's cache disabled."""
    for runner, flag in CACHE_FLAGS.items():
        if re.search(rf"\b{runner}\b", command) and flag not in command:
            return (
                re.sub(rf"\b({runner})\b", rf"\1 {flag}", command, count=1),
                f"{runner}: added {flag} (ADR 0083 -- a stale transform cache "
                f"manufactures false NOT CAUGHT verdicts)",
            )
    return command, None


def run_suite(command: str, timeout: int) -> SuiteRun:
    command, _note = without_cache(command)
    proc = subprocess.run(
        command,
        shell=True,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return SuiteRun(exit_code=proc.returncode, raw_output=(proc.stdout or "") + (proc.stderr or ""))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: Signs that a command died rather than reported a finding.
#:
#: WHY THIS EXISTS
#: ---------------
#: Many of this repository's checks are guard SCRIPTS, not test suites: one
#: process, one binary exit code, no test count. ADR 0045's whole mutation
#: table is of that shape -- the "suite" is
#: `check_findings_reach_a_surface.py` and the verdict is whether it exits
#: non-zero.
#:
#: Judging those by exit code alone would reintroduce the exact class of lie
#: ADR 0069 exists to remove. A mutation that makes a guard **crash** exits
#: non-zero and is indistinguishable from a guard that **caught** it. The
#: harness would report "caught" for a guard it had just broken, which is
#: worse than reporting nothing: it would certify a check that no longer
#: runs at all.
#:
#: So a crash is detected and reported INDETERMINATE.
CRASH_MARKERS = (
    "Traceback (most recent call last)",
    "SyntaxError:",
    "ImportError:",
    "ModuleNotFoundError:",
    "IndentationError:",
    "command not found",
    "No such file or directory",
)


def looks_like_a_crash(output: str) -> str | None:
    """The marker that says this command died, or None if it merely failed."""
    for marker in CRASH_MARKERS:
        if marker in output:
            return marker
    return None


@dataclass
class Verdict:
    id: str
    description: str
    state: str  # "caught" | "not_caught" | "indeterminate"
    detail: str
    failures: int = 0

    @property
    def symbol(self) -> str:
        return {"caught": "caught", "not_caught": "NOT CAUGHT", "indeterminate": "INDETERMINATE"}[self.state]


def apply_one(
    *,
    mutation_id: str,
    description: str,
    file_path: Path,
    find: str,
    replace: str,
    test_command: str,
    timeout: int,
    baseline: SuiteRun,
    verdict_mode: str = "test_count",
) -> Verdict:
    original_bytes = file_path.read_bytes()
    original_digest = hashlib.sha256(original_bytes).hexdigest()
    source = original_bytes.decode("utf-8")

    # 1. The patch must apply, exactly once.
    occurrences = source.count(find)
    if occurrences == 0:
        return Verdict(
            mutation_id, description, "indeterminate",
            "the search string does not occur in the file, so nothing was mutated. "
            "The suite would have run against unmutated source and passed, which is "
            "not evidence about the tests. Check indentation and line breaks.",
        )
    if occurrences > 1:
        return Verdict(
            mutation_id, description, "indeterminate",
            f"the search string occurs {occurrences} times, so which one was mutated "
            "is not defined. Extend it until it is unique.",
        )

    mutated = source.replace(find, replace, 1)
    if mutated == source:
        return Verdict(
            mutation_id, description, "indeterminate",
            "replacing the search string produced identical content, so the mutation "
            "is a no-op and the suite has nothing to catch.",
        )

    # 2. Write it, and confirm the bytes on disk actually changed.
    #    The journal is opened FIRST: if this process is killed between the
    #    write and the restore, the next run repairs the tree from it.
    open_journal(file_path, original_bytes)
    file_path.write_text(mutated, encoding="utf-8")

    # Push the modification time firmly forward.
    #
    # WHY: this harness reported the SAME mutation as NOT CAUGHT and then, a
    # few minutes later, as CAUGHT. Same set file, same command, same tree.
    # A harness that answers differently on two runs is worse than no
    # harness, because a false NOT CAUGHT reads as a real gap in the tests
    # -- the exact failure class ADR 0069 exists to remove, reappearing in
    # the tool written to remove it.
    #
    # The runs that disagreed were the third rapid mutation of one file
    # within a few seconds. Test runners cache transformed modules, and a
    # cache keyed on (path, mtime) rather than on content will serve the
    # PRE-MUTATION transform when two writes land inside the same mtime
    # tick. The suite then runs unmutated source and passes, which is
    # indistinguishable from a mutation nothing catches.
    #
    # Setting mtime to the future is cheap, needs no knowledge of which
    # runner is in use, and makes a stale cache entry impossible rather than
    # unlikely. The file is restored byte-for-byte afterwards either way.
    try:
        future = time.time() + 10
        os.utime(file_path, (future, future))
    except OSError:
        pass  # not fatal; the content check below still holds
    try:
        if digest(file_path) == original_digest:
            return Verdict(
                mutation_id, description, "indeterminate",
                "the file on disk is unchanged after writing the mutation.",
            )

        # 3. Run, and require that tests actually executed.
        run = run_suite(test_command, timeout)

        if verdict_mode == "exit_code":
            # For a guard script the verdict IS the exit code -- but only
            # once a crash has been ruled out. See CRASH_MARKERS.
            crash = looks_like_a_crash(run.output)
            if crash:
                return Verdict(
                    mutation_id, description, "indeterminate",
                    f"the command died rather than reporting a finding ({crash!r} in its "
                    "output). A crash exits non-zero exactly like a detection does, so "
                    "calling this 'caught' would certify a guard that no longer runs.",
                )
            if not run.output.strip():
                return Verdict(
                    mutation_id, description, "indeterminate",
                    "the command produced no output at all, so there is no evidence it "
                    "examined anything. A guard that prints nothing and exits 0 is the "
                    "check-that-cannot-fail shape.",
                )
            if run.exit_code != 0:
                return Verdict(
                    mutation_id, description, "caught",
                    f"the guard exited {run.exit_code} and reported a finding.",
                    failures=1,
                )
            return Verdict(
                mutation_id, description, "not_caught",
                "the guard exited 0 with the mutation applied.",
            )

        if not run.ran:
            count = run.tests_run
            reason = (
                "the runner reported no test count at all, which usually means the "
                "suite failed to compile or the command was wrong"
                if count is None
                else f"the runner reported {count} tests"
            )
            return Verdict(
                mutation_id, description, "indeterminate",
                f"the suite did not execute any tests -- {reason}. "
                "A suite that did not run has judged nothing; this is not 'not caught'.",
            )

        if run.failures > 0:
            return Verdict(
                mutation_id, description, "caught",
                f"{run.failures} test(s) failed of {run.tests_run} run.",
                failures=run.failures,
            )

        return Verdict(
            mutation_id, description, "not_caught",
            f"all {run.tests_run} tests passed with the mutation applied. "
            "Either the behaviour is untested, or the branch cannot fail.",
        )
    finally:
        # 4. Restore, and VERIFY the restore. A silent restore failure is
        #    how five mutations once accumulated in the tree.
        file_path.write_bytes(original_bytes)
        close_journal()
        if digest(file_path) != original_digest:
            print(
                f"\n  !! RESTORE FAILED for {file_path}. The mutation is STILL IN THE TREE.\n"
                f"     expected sha256 {original_digest}\n"
                f"     found    sha256 {digest(file_path)}",
                file=sys.stderr,
            )
            raise SystemExit(2)


def establish_baseline(test_command: str, timeout: int, verdict_mode: str = "test_count") -> SuiteRun:
    print("Baseline (unmutated)...", end=" ", flush=True)
    baseline = run_suite(test_command, timeout)

    if verdict_mode == "exit_code":
        crash = looks_like_a_crash(baseline.output)
        if crash or baseline.exit_code != 0 or not baseline.output.strip():
            print("FAILED")
            print(
                "\nThe baseline command did not succeed cleanly "
                f"(exit {baseline.exit_code}"
                + (f", {crash!r} in output" if crash else "")
                + "). Every verdict below would be meaningless, so nothing was mutated.",
                file=sys.stderr,
            )
            print("\n--- output (last 40 lines) ---\n"
                  + "\n".join(baseline.output.splitlines()[-40:]), file=sys.stderr)
            raise SystemExit(2)
        print("green (guard exits 0)")
        return baseline

    if not baseline.ran:
        print("FAILED")
        print(
            "\nThe baseline suite did not execute any tests. Every verdict below would\n"
            "be meaningless, so nothing was mutated. Check the --test command.",
            file=sys.stderr,
        )
        print(f"\n--- runner output (last 40 lines) ---\n" + "\n".join(baseline.output.splitlines()[-40:]),
              file=sys.stderr)
        raise SystemExit(2)

    if baseline.failures > 0:
        print("FAILED")
        print(
            f"\nThe baseline suite has {baseline.failures} failing test(s) before any\n"
            "mutation. A mutation judged against a red baseline says nothing: a test\n"
            "that was already failing 'catches' everything. Fix the baseline first.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    print(f"green ({baseline.tests_run} tests)")
    return baseline


def selftest() -> int:
    """Verify the harness reports INDETERMINATE where it used to lie."""
    print("Self-test: a mutation that does not apply must not read as 'not caught'.\n")

    with tempfile.TemporaryDirectory() as tmp:
        subject = Path(tmp) / "subject.txt"
        subject.write_text("value = 1\n", encoding="utf-8")

        # A test command that trivially passes and reports a count.
        passing = "python3 -c \"print('Tests:       3 passed, 3 total')\""
        baseline = run_suite(passing, timeout=30)

        cases = [
            (
                "search string absent",
                "no_such_string_anywhere",
                "x",
                "indeterminate",
            ),
            (
                "replacement identical to the original",
                "value = 1",
                "value = 1",
                "indeterminate",
            ),
        ]

        failures = 0
        for label, find, replace, expected in cases:
            verdict = apply_one(
                mutation_id="S", description=label, file_path=subject,
                find=find, replace=replace, test_command=passing,
                timeout=30, baseline=baseline,
            )
            ok = verdict.state == expected
            failures += 0 if ok else 1
            print(f"  [{'ok' if ok else 'FAIL'}] {label}: {verdict.symbol}")
            if not ok:
                print(f"        expected {expected}, got {verdict.state}")

        # A suite that reports no count at all must be INDETERMINATE, not
        # "not caught" -- the ADR 0065 lie.
        no_count = "python3 -c \"print('SyntaxError: unexpected token')\""
        verdict = apply_one(
            mutation_id="S", description="suite reports no test count",
            file_path=subject, find="value = 1", replace="value = 2",
            test_command=no_count, timeout=30, baseline=baseline,
        )
        ok = verdict.state == "indeterminate"
        failures += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] suite reports no test count: {verdict.symbol}")

        # And the restore must have worked.
        restored = subject.read_text(encoding="utf-8")
        ok = restored == "value = 1\n"
        failures += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] file restored after every case")

        # A genuinely uncaught mutation must still be reported as such --
        # otherwise this harness would be a check that cannot fail.
        verdict = apply_one(
            mutation_id="S", description="real mutation, passing suite",
            file_path=subject, find="value = 1", replace="value = 999",
            test_command=passing, timeout=30, baseline=baseline,
        )
        ok = verdict.state == "not_caught"
        failures += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] a real mutation against a passing suite: {verdict.symbol}")

    print()
    if failures:
        print(f"FAIL: {failures} self-test case(s) failed.", file=sys.stderr)
        return 1
    print("OK: the harness reports INDETERMINATE where it cannot establish a verdict.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument("--file")
    parser.add_argument("--find")
    parser.add_argument("--replace")
    parser.add_argument("--test", help="command that runs the suite")
    parser.add_argument("--set", dest="set_file", help="JSON file describing a mutation set")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--only", default=None,
                        help="comma-separated mutation ids, for running a set in parts. "
                             "A full set of N mutations costs N+1 suite runs, which can "
                             "exceed a per-call time limit; splitting the RUN is right, "
                             "splitting the set FILE would fragment the record.")
    parser.add_argument("--verdict", choices=["test_count", "exit_code"],
                        default="test_count",
                        help="exit_code: for guard scripts, where the verdict is the exit status")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    install_signal_handlers()
    recover_journal()

    if args.selftest:
        return selftest()

    if args.set_file:
        spec = json.loads(Path(args.set_file).read_text(encoding="utf-8"))
        test_command = spec["test"]
        mutations = spec["mutations"]
        verdict_mode = spec.get("verdict", "test_count")
    else:
        missing = [n for n in ("file", "find", "replace", "test") if not getattr(args, n)]
        if missing:
            parser.error(f"--{', --'.join(missing)} required (or use --set)")
        test_command = args.test
        verdict_mode = args.verdict
        mutations = [{
            "id": "M1", "description": args.find[:60],
            "file": args.file, "find": args.find, "replace": args.replace,
        }]

    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        known = {m.get("id") for m in mutations}
        unknown = wanted - known
        if unknown:
            # A typo'd id would silently run nothing and report
            # "0 caught, 0 not caught", which reads like a clean sweep.
            parser.error(f"--only names unknown mutation id(s): {sorted(unknown)}; "
                         f"this set has {sorted(i for i in known if i)}")
        mutations = [m for m in mutations if m.get("id") in wanted]

    baseline = establish_baseline(test_command, args.timeout, verdict_mode)
    print()

    verdicts: list[Verdict] = []
    for mutation in mutations:
        label = f"{mutation.get('id', '?')}: {mutation.get('description', '')}"
        print(f"{label} ...", end=" ", flush=True)
        verdict = apply_one(
            mutation_id=mutation.get("id", "?"),
            description=mutation.get("description", ""),
            file_path=REPO_ROOT / mutation["file"],
            find=mutation["find"],
            replace=mutation["replace"],
            test_command=test_command,
            timeout=args.timeout,
            baseline=baseline,
            verdict_mode=verdict_mode,
        )
        print(verdict.symbol)
        verdicts.append(verdict)

    print("\n" + "=" * 68)
    caught = [v for v in verdicts if v.state == "caught"]
    uncaught = [v for v in verdicts if v.state == "not_caught"]
    unknown = [v for v in verdicts if v.state == "indeterminate"]

    print(f"{len(caught)} caught, {len(uncaught)} not caught, {len(unknown)} indeterminate")

    for v in uncaught:
        print(f"\nNOT CAUGHT -- {v.id}: {v.description}\n  {v.detail}")
    for v in unknown:
        print(f"\nINDETERMINATE -- {v.id}: {v.description}\n  {v.detail}", file=sys.stderr)

    if unknown:
        print(
            "\nAn indeterminate result is not a passing test and not a failing one.\n"
            "It means the harness could not establish what happened. Fix the mutation\n"
            "spec and re-run; do not record it in an ADR as either outcome.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # SIGTERM/SIGINT is turned into this so `finally` restores the tree.
        # Letting it surface as a traceback undoes the point: ADR 0074 records
        # that a traceback reads as "the tool is broken" rather than "the run
        # was cut short", and this one appeared three times before being
        # tidied. The restore has already happened by the time we get here.
        print(
            "\nInterrupted (signal). The mutated file was restored before exit;\n"
            "if the process was SIGKILLed instead, the next run repairs the tree\n"
            "from .mutate-journal/ and says so.",
            file=sys.stderr,
        )
        sys.exit(130)
