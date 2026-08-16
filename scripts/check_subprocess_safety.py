#!/usr/bin/env python3
"""User input must never reach a shell or a command line.

WHY THIS EXISTS
---------------
`SECURITY.md` carries a correction banner, written during an earlier audit,
which named two things its scope section had missed:

    The API server spawns Python subprocesses directly (`spawn(
    pythonExecutable, [SCRIPT_PATH], ...)`) and calls out to external LLM
    providers with an API key -- neither subprocess/command-injection risk
    nor LLM-API-key handling is mentioned anywhere in this scope section.

The LLM half was assessed and disclosed (see `check_llm_disclosure.py` and
`docs/PRIVACY.md`). This is the other half.

THE ASSESSMENT, WHICH CAME OUT CLEAN
-------------------------------------
Four things were checked, and all four are right:

  1. `spawn(pythonExecutable, [SCRIPT_PATH], {...})` -- the argv form. The
     command and its arguments are separate values, so nothing in them is
     parsed as shell syntax.
  2. **No `shell: true` anywhere in the server**, and no `execSync` or
     `child_process.exec`. Those are the constructs that turn an argument
     into a command.
  3. User data goes over **stdin as JSON**:
     `proc.stdin.write(JSON.stringify(payload))`. It never appears on a
     command line at all.
  4. `pythonExecutable` is resolved from `TERRIUM_PYTHON`, `VIRTUAL_ENV` and
     `PATH` -- operator-controlled environment, not request-controlled input.

So there is no command injection here. That is worth writing down: an
unassessed risk in a security document invites the next auditor to
re-litigate it from scratch, and the honest resolution of "we never checked"
is "we checked, here is what we found".

WHY IT IS GUARDED ANYWAY
------------------------
Because the property is one edit from being false, and the consequences are
not proportionate to the size of that edit. `shell: true` is twelve
characters. On a server that has **no authentication** and, until recently,
published itself to every network interface, that would be remote code
execution reachable by anyone who could open the port.

A correct thing nobody is watching is a coincidence, which is the same
reasoning behind `check_port_binding.py`.

WHAT IT CHECKS
--------------
Across the API server and `src/`:

  * no `shell: true` on a spawn/exec call
  * no `execSync` / `child_process.exec` (the string-command forms)
  * no template literal or concatenation inside a spawn's argv array

WHAT IT DOES NOT CHECK
----------------------
**That the Python side handles its stdin safely.** A payload arriving as
JSON can still be mishandled after parsing -- `eval`, an unsafe
deserialiser, a path built from a field. That is a different check on a
different language, and claiming this covers it would be exactly the
overreach this file is about.

It also does not check subprocesses spawned outside these roots.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parent.parent
SCAN_ROOTS = [
    REPO / "src",
    REPO / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src",
]
SKIP_PARTS = {"node_modules", "dist", "build", "__tests__", ".next"}

#: Constructs that hand a STRING to a shell for parsing.
FORBIDDEN: List[Tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\bshell\s*:\s*true\b"),
        "shell: true",
        "the argument list is parsed by a shell, so a value containing ; or "
        "$( becomes a command",
    ),
    (
        re.compile(r"\bexecSync\s*\("),
        "execSync(",
        "takes a command STRING, not an argv array -- there is no safe way "
        "to interpolate a value into it",
    ),
    (
        re.compile(r"child_process\.exec\s*\(|[^S]\bexec\s*\(\s*[`\"']"),
        "exec( with a string command",
        "same as execSync: a string command is shell-parsed. Use spawn() "
        "with an argv array",
    ),
]

#: A spawn whose argv array contains interpolation. Even without a shell,
#: an attacker-controlled argv entry can be a flag rather than a value.
SPAWN_ARGV_INTERP = re.compile(r"spawn\s*\([^,]+,\s*\[[^\]]*(\$\{|\s\+\s)", re.S)


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"^\s*//.*$", "", text, flags=re.M)


def offending(text: str) -> List[Tuple[int, str, str]]:
    """`(line number, what, why)` for each unsafe construct."""
    found: List[Tuple[int, str, str]] = []
    code = _strip_comments(text)
    for lineno, line in enumerate(code.splitlines(), start=1):
        for pattern, what, why in FORBIDDEN:
            if pattern.search(line):
                found.append((lineno, what, why))
    if SPAWN_ARGV_INTERP.search(code):
        found.append((0, "interpolation inside a spawn argv array",
                      "an attacker-controlled argv entry can be read as a "
                      "flag even without a shell"))
    return found


def selftest() -> int:
    """Prove each pattern fires, and that comments and safe forms do not.

    On a clean tree this reports zero findings forever. The `must_pass` half
    is the one that keeps the guard usable: a check that fires on the safe
    `spawn(exe, [SCRIPT])` form would be muted within a day.
    """
    failures: List[str] = []

    unsafe = [
        'const p = spawn(cmd, args, { shell: true });',
        'execSync(`python ${script}`);',
        'child_process.exec("ls " + dir);',
    ]
    safe = [
        'const proc = spawn(pythonExecutable, [SCRIPT_PATH], { cwd: REPO_ROOT });',
        'proc.stdin.write(JSON.stringify(payload));',
        '// never use shell: true here',
        '/* execSync was removed deliberately */',
        'const shell = detectShell();',
    ]
    for sample in unsafe:
        if not offending(sample):
            failures.append(f"unsafe construct not flagged: {sample!r}")
    for sample in safe:
        hits = offending(sample)
        if hits:
            failures.append(f"safe construct flagged as {hits[0][1]!r}: {sample!r}")

    # Interpolation inside an argv array must fire.
    interp = "spawn(exe, [`--query=${userInput}`], {})"
    if not offending(interp):
        failures.append("argv interpolation not flagged")

    if failures:
        print("SELFTEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"SELFTEST OK: {len(unsafe)} unsafe construct(s) flagged, "
        f"{len(safe)} safe form(s) — including comments about unsafe ones — "
        "left alone, and argv interpolation detected."
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    findings: List[str] = []
    scanned = 0
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.ts")):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, what, why in offending(text):
                where = f":{lineno}" if lineno else ""
                findings.append(
                    f"{path.relative_to(REPO)}{where}: {what}\n      {why}"
                )

    if scanned == 0:
        print(
            "FAIL: no TypeScript files scanned. The roots are wrong, not the "
            "code -- a scan\nthat reads nothing must not report safety."
        )
        return 1

    if findings:
        print(f"User input can reach a shell ({len(findings)}):\n")
        for finding in findings:
            print(f"  - {finding}")
        print(
            "\nThe server currently spawns Python with the argv form and "
            "passes user data over\nstdin as JSON, so nothing typed by a user "
            "reaches a command line. Keep it that way.\n"
            "\nThis matters more here than in most projects: the web server "
            "has NO\nauthentication (see SECURITY.md), so a shell injection "
            "would be reachable by\nanyone who can open the port."
        )
        return 1

    print(
        f"OK: {scanned} TypeScript file(s) scanned; no shell:true, no "
        "execSync, and no\n    interpolation inside a spawn argv array. User "
        "data reaches Python over stdin.\n"
        "\n    (This does not check how the Python side handles that stdin — "
        "see this script.)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
