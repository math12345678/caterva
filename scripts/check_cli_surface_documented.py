#!/usr/bin/env python3
"""Every command and flag the CLI accepts must appear in `help`.

`check_commands_runnable.py` points at documented commands that cannot
run. This one points the other way: commands and flags that run and are
not documented. A capability nobody can find does not exist, which is the
same conclusion by a different route.

What it found when first run: `sweep` and `history` were whole working
commands absent from `help`, and `simulate --resolve` accepted seven flags
it did not list.

WHAT THIS GUARD LOOKED AT, precisely, so a pass is not read as more than
it earned:

  * ONE file, `src/cli/scientificCLI.ts`. It is the only argv parser; the
    command modules take typed options objects, not flags, so they cannot
    introduce a name this file does not first read.
  * COMMANDS are the `case '...'` labels of the top-level dispatch switch.
  * FLAGS READ are `flags['name']` and `booleans.has('name')`, plus names
    listed in the override-sweep exclusion arrays -- those are read as
    "not a parameter override", which is still being read.
  * DOCUMENTED is the name appearing anywhere inside `showHelp()`.

## The direction this guard deliberately does not rule on

"Documented but never read" is the more dangerous defect -- a user types
the flag, the CLI ignores it, and the run reports success on a request it
did not honour. This guard **cannot decide it**, and says so rather than
guessing.

The reason is structural. `simulate` and `sweep` iterate
`Object.entries(flags)` and read every remaining name as a parameter with
a unit. Under a catch-all like that, *every* flag is read by definition,
so a name-by-name comparison would clear a genuinely-ignored flag while
accusing six innocent ones -- which is what a first version of this guard
did to `--km`, `--vmax`, `--s0`, `--json`, `--verbose` and `--resolve`.

So the third outcome is reported by name: for each documented flag not
matched to an explicit read, the guard says it could not determine the
answer, and does not fail on it. A guard that turns "I cannot tell" into
"it is fine" is worse than no guard, because it is trusted.

Exit 0 clean, 1 on an undocumented command or flag, or if the file cannot
be read.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "src" / "cli" / "scientificCLI.ts"

# `help` is the command that prints the help; it need not describe itself
# in a `Commands:` entry to be findable.
COMMANDS_EXEMPT = {"help"}


def commands(source: str) -> set[str]:
    """Case labels of the top-level dispatch switch (four-space indented)."""
    return set(re.findall(r"^    case '([a-z][a-z0-9-]*)':", source, re.M))


def flags_read(source: str) -> tuple[set[str], set[str]]:
    """(read explicitly by name, consumed by an override-sweep exclusion)."""
    named = set(re.findall(r"flags\[\s*'([a-z0-9][a-z0-9-]*)'\s*\]", source))
    named |= set(re.findall(r"booleans\.has\(\s*'([a-z0-9][a-z0-9-]*)'\s*\)", source))

    # Anchored on the array literal itself, with no `[` or `]` inside it.
    # An `if\s*\(\[(.*?)\]\.includes\(k\)\)` form looks equivalent and is not:
    # non-greedy still starts at the EARLIEST `if ([` in the file, so an
    # unrelated `if ([...].includes(model))` hundreds of lines above swallows
    # everything between, and thirteen enum values -- 'competitive', 'kcat',
    # 'verify' -- get reported as undocumented flags. That was the first
    # version's output, and every one of the thirteen was a false accusation.
    swept: set[str] = set()
    for match in re.finditer(r"\[([^\[\]]*)\]\.includes\((?:k|key)\)", source, re.S):
        swept.update(re.findall(r"'([a-z0-9][a-z0-9-]*)'", match.group(1)))
    return named, swept


def help_body(source: str) -> str:
    start = source.find("function showHelp()")
    if start == -1:
        raise LookupError("showHelp() not found -- this guard is reading the wrong file")
    # Brace-balanced rather than "to the next line-start }": a nested object
    # literal would end a naive scan early and silently shrink the documented
    # set, which fails in the direction of false accusations.
    open_at = source.index("{", start)
    depth = 0
    for j in range(open_at, len(source)):
        if source[j] == "{":
            depth += 1
        elif source[j] == "}":
            depth -= 1
            if depth == 0:
                return source[open_at : j + 1]
    raise LookupError("showHelp() has unbalanced braces")


def main() -> int:
    if not CLI.exists():
        print(f"FAIL  {CLI.relative_to(REPO)} does not exist.")
        print("      This guard cannot say the CLI surface is documented; it can")
        print("      only say it did not look. Those are different facts.")
        return 1

    source = CLI.read_text(encoding="utf-8")
    try:
        body = help_body(source)
    except LookupError as exc:
        print(f"FAIL  {exc}")
        return 1

    found_commands = commands(source) - COMMANDS_EXEMPT
    named, swept = flags_read(source)
    read = named | swept
    documented_flags = set(re.findall(r"--([a-z0-9][a-z0-9-]*)", body))

    if not found_commands or not read:
        print("FAIL  Found no commands or no flag reads in the CLI parser.")
        print(f"      commands={len(found_commands)} flags={len(read)}")
        print("      Either the parser changed shape or these patterns stopped")
        print("      matching. Reporting a pass over an empty set is how a guard")
        print("      becomes decoration.")
        return 1

    # A command is documented if its name starts a line in the Commands
    # section. Substring matching would let the word "history" inside a
    # sentence count as documentation for the command.
    documented_commands = set(re.findall(r"^  ([a-z][a-z0-9-]*)[ \n]", body, re.M))

    missing_commands = sorted(found_commands - documented_commands)
    missing_flags = sorted(read - documented_flags)
    undecidable = sorted(documented_flags - read)

    print(f"Checked {CLI.relative_to(REPO)}")
    print(f"  {len(found_commands)} command(s) dispatched, {len(documented_commands & found_commands)} documented")
    print(f"  {len(read)} flag(s) read ({len(named)} by name, {len(swept - named)} only via an override sweep)")
    print(f"  {len(documented_flags)} flag(s) named in showHelp()")

    if undecidable:
        print(f"\nNOT DETERMINED  {len(undecidable)} documented flag(s) have no explicit read:")
        print("  " + ", ".join(f"--{f}" for f in undecidable))
        print("      `simulate` and `sweep` read every remaining flag as a")
        print("      parameter, so these may be honoured by that catch-all or")
        print("      may be ignored. This guard cannot tell which, and does not")
        print("      fail on them. See this file's docstring.")

    if not missing_commands and not missing_flags:
        print("\nOK  every dispatched command and every explicitly-read flag is in help.")
        return 0

    if missing_commands:
        print(f"\nFAIL  {len(missing_commands)} command(s) run but are not in help:")
        for name in missing_commands:
            print(f"  {name}")

    if missing_flags:
        print(f"\nFAIL  {len(missing_flags)} flag(s) read but not in help:")
        for name in missing_flags:
            print(f"  --{name}")

    print("\n      The capability exists and nobody can find it, which for a user")
    print("      is indistinguishable from it not existing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
