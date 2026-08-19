#!/usr/bin/env python3
"""Every example in the domain catalogue is a command that actually runs.

WHY THIS EXISTS
---------------
`scientific domains` prints fifteen copy-pasteable commands. A student's
first act with this tool is to paste one, so an example that does not run is
not a cosmetic defect -- it is the first impression.

`domainCatalogue.test.ts` checks the examples LOOK like commands: they start
with `simulate` or `python -m Terium.cli`, they contain a digit, they carry
no `<PLACEHOLDER>`. Every one of those passed while

    python -m Terium.cli wf --n 100 --p0 0.5 --generations 200 --seed 1

was in the file, and `--n` and `--p0` are not flags. The real ones are
`--population-size` and `--starting-frequency`. A shape assertion cannot
tell the difference, which makes it the shape of a test that cannot fail.

THEN THE FIX BROKE A WORKING EXAMPLE
------------------------------------
Reading the true flag names with

    python3 -m Terium.cli ssa --help | grep -oE '\\-\\-[a-z-]+'

reported `--a` and `--b`. The character class has no digits, so `--a0`
arrived as `--a`, and a correct example was "corrected" into

    ssa --bimolecular --a 100 --b 100 ...
    error: ambiguous option: --b could match --bimolecular, --b0

Third time in one session that a matcher narrower than the thing it measures
produced a confident wrong answer (ADR 0102, ADR 0104, here) -- this time in
the tooling used to check the tooling.

The only thing that settles it is running the command, which is what this
does.

SCOPE, STATED
-------------
Only the `python -m Terium.cli` examples run here. The `simulate` ones need
the TypeScript CLI and a Node toolchain, cost ~15 s each through ts-node,
and would take this guard past the per-call ceiling several times over.
Those are covered by `documentedExamplesRun.test.ts` on the jest side.

That split is a real limitation and is written down rather than implied: a
`simulate` example CAN rot without this guard noticing.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOGUE = REPO_ROOT / "src" / "cli" / "domainCatalogue.ts"

#: `example: '...'` — single-quoted, which every entry uses.
EXAMPLE_RE = re.compile(r"example:\s*'((?:[^'\\]|\\.)*)'", re.MULTILINE)

PY_PREFIX = "python -m Terium.cli "


def examples() -> list[str]:
    if not CATALOGUE.exists():
        return []
    return [
        match.group(1).replace("\\'", "'")
        for match in EXAMPLE_RE.finditer(CATALOGUE.read_text(encoding="utf-8"))
    ]


def main() -> int:
    found = examples()
    if not found:
        # A guard that examined nothing must not print OK. If the catalogue
        # moves or its quoting changes, this must say so rather than pass.
        print(
            f"FAIL: no `example:` entries parsed out of {CATALOGUE.name}. "
            "Either the file moved or the matcher stopped matching; either way "
            "nothing was checked.",
            file=sys.stderr,
        )
        return 1

    runnable = [e for e in found if e.startswith(PY_PREFIX)]
    if not runnable:
        print(
            f"FAIL: parsed {len(found)} example(s) and none is a "
            f"`{PY_PREFIX.strip()}` command. This guard would be checking nothing.",
            file=sys.stderr,
        )
        return 1

    if shutil.which(sys.executable) is None:
        print("FAIL: no python executable to run examples with.", file=sys.stderr)
        return 1

    failures: list[tuple[str, str]] = []
    for example in runnable:
        # Everything after a `#` is a note to the reader, not part of the
        # command. Split before tokenising or argparse receives "#" as a
        # positional and the example fails for a reason that is not real.
        command = example.split("#", 1)[0].strip()
        args = command[len(PY_PREFIX):].split()
        proc = subprocess.run(
            [sys.executable, "-m", "Terium.cli", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            failures.append((command, (proc.stderr or proc.stdout).strip().splitlines()[-1]))

    print(f"Examples in the catalogue:      {len(found)}")
    print(f"  runnable here (engine CLI):   {len(runnable)}")
    print(f"  needing the TypeScript CLI:   {len(found) - len(runnable)}  "
          f"(see documentedExamplesRun.test.ts)")

    if failures:
        print(f"\nExamples that do NOT run ({len(failures)}):", file=sys.stderr)
        for command, why in failures:
            print(f"  $ {command}\n      {why}", file=sys.stderr)
        print(
            "\n`scientific domains` prints these for a student to paste. An\n"
            "example that does not run is the first impression the tool makes.",
            file=sys.stderr,
        )
        return 1

    print(f"\nOK: all {len(runnable)} engine examples run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
