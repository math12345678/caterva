#!/usr/bin/env python3
"""No tracked file may name a person's home directory or a scratch folder.

WHY THIS EXISTS
---------------
A review of the Studio branch found a person's home directory
(`/Users/<name>/...`), a development worktree (`/tmp/claude-.../wt-...`) and
scratch folders from captures (`/private/tmp/...`) in documentation, test
fixtures and a fixtures README. A path like that is private information in a
public repository, it is a command nobody else can paste, and in a captured
fixture it is a statement about a machine that no reader can check.

WHAT IT CHECKS
--------------
Every tracked text file, line by line, for

    /Users/<name>/        a macOS home directory
    /tmp/claude-          a scratch or worktree folder of the development tooling
    /private/tmp/         macOS's spelling of /tmp, which a capture records

A hit fails unless the file is on ALLOWED below with a reason. The list is
short on purpose: a document that needs a path says `path/to/caterva`, and a
captured response has its scratch prefix rewritten to a neutral one (the
fixtures' README says so).

WHAT IT DOES NOT CHECK
----------------------
Untracked files (they are not in the repository), binary files, files over
2 MB, and other private-looking strings (a username in prose, an email
address): this is a path guard, not a privacy review.

Usage:
    python scripts/check_no_machine_paths.py             # exit 1 on a hit
    python scripts/check_no_machine_paths.py --selftest  # prove it matches
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Built from pieces so this file does not trip its own pattern when read as text.
_HOME = "/Us" + "ers/"
_SCRATCH = "/tmp/" + "claude-"
_PRIVATE_TMP = "/private" + "/tmp/"
PATTERN = re.compile(
    rf"(?:{re.escape(_HOME)}[A-Za-z0-9_.-]+/|{re.escape(_SCRATCH)}|{re.escape(_PRIVATE_TMP)})"
)

#: Tracked files allowed to contain a match, and why. Prefixes end in "/".
ALLOWED: dict[str, str] = {
    "scripts/check_no_machine_paths.py": "names the patterns it looks for",
    "caterva/tests/test_no_machine_paths.py": "the guard's own tests, which need a matching line to prove it matches",
    "caterva/tests/test_studio_workspace.py": (
        "an invented Windows APPDATA value (a drive-letter path under a user folder called u) "
        "that the default-data-folder test resolves; it is not a path on any real machine"
    ),
}

MAX_BYTES = 2_000_000


def tracked_files(root: Path = ROOT) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
    return [name for name in out.decode("utf-8", "surrogateescape").split("\0") if name]


def allowed(rel: str) -> bool:
    return any(rel == key or (key.endswith("/") and rel.startswith(key)) for key in ALLOWED)


def hits_in(text: str) -> list[tuple[int, str]]:
    return [(number, line.strip()[:160]) for number, line in enumerate(text.splitlines(), 1) if PATTERN.search(line)]


def findings(root: Path = ROOT, names: list[str] | None = None) -> list[str]:
    problems = []
    for rel in names if names is not None else tracked_files(root):
        if allowed(rel):
            continue
        path = root / rel
        try:
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue
        for number, line in hits_in(data.decode("utf-8", errors="replace")):
            problems.append(f"{rel}:{number}: {line}")
    return problems


def selftest() -> int:
    sample = "cd " + _HOME + "someone/code\nok line\nwork in " + _SCRATCH + "x/wt\nsaved to " + _PRIVATE_TMP + "x\n"
    got = hits_in(sample)
    if [n for n, _ in got] != [1, 3, 4]:
        print(f"selftest FAILED: expected hits on lines 1, 3 and 4, got {got}")
        return 1
    if hits_in("cd path/to/caterva\n/tmp/caterva-fixtures/run\nC:/Program Files/x\n"):
        print("selftest FAILED: a neutral path matched")
        return 1
    stale = [k for k in ALLOWED if not (ROOT / k).exists() and not k.endswith("/")]
    if stale:
        print(f"selftest FAILED: the allow-list names files that do not exist: {stale}")
        return 1
    print("selftest ok: matches a home directory, a scratch folder and /private/tmp; leaves neutral paths alone")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--selftest" in args:
        return selftest()
    names = tracked_files()
    if len(names) < 500:
        print(f"FAIL: git ls-files returned {len(names)} files; the listing is broken and nothing was checked")
        return 1
    problems = findings(names=names)
    if problems:
        print(f"FAIL: {len(problems)} line(s) name a machine-specific path:")
        for line in problems[:60]:
            print(f"  {line}")
        print("A document says `path/to/caterva`; a capture has its scratch prefix rewritten to a neutral one.")
        print("A file that must keep one goes on ALLOWED in scripts/check_no_machine_paths.py, with the reason.")
        return 1
    print(f"ok: {len(names)} tracked files, none names a home directory or a scratch folder "
          f"({len(ALLOWED)} files are allowed to, each with a reason)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
