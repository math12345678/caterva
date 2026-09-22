"""One executable for the downloadable app: `terrium <command>`.

WHY THIS EXISTS
---------------
The wheel installs two console scripts, `terium` (the simulation engine)
and `terium-compose` (the model builder). A frozen app bundle is one
folder with one executable, and a bundle built from two entry points
either doubles its size or depends on a multi-executable feature of the
freezer that cannot be exercised on this machine. So the bundle ships one
binary, `terrium`, and this module is what it runs: the first argument
picks the command and the rest is passed through unchanged.

    terrium compose "a toggle switch between two repressors"
    terrium sim wf --N 100 --generations 50
    terrium --version

`python -m Terium.app ...` runs the same code from a checkout or a wheel,
so the dispatch is tested where the bundle itself cannot be.

WHAT IT DOES NOT DO
-------------------
It does not re-implement or re-parse either command's options; every
argument after the first goes to the existing `main(argv)` unchanged, so
the two surfaces cannot drift. It does not change the two console scripts,
which the wheel still installs.
"""
from __future__ import annotations

import sys
from typing import Optional, Sequence

#: Command name -> (module path, human name). Resolved lazily, so `--help`
#: and an unknown command import nothing of the engine. (`--version` does:
#: `Terium/__init__.py` loads the engine, and with it roadrunner, antimony
#: and libsbml, at import. In the frozen folder that is also the cheapest
#: proof that the native libraries load.)
COMMANDS = {
    "compose": ("Terium.compose.__main__", "the model builder and its analyses"),
    "sim": ("Terium.cli", "the simulation engine: wf, kimura, ne, sweep, scenarios, ld, ssa"),
}

USAGE = """usage: terrium <command> [args...]

commands:
  compose   {compose}
  sim       {sim}

  terrium <command> --help   for that command's options
  terrium --version          print the version and exit
"""


def _usage() -> str:
    return USAGE.format(**{k: v[1] for k, v in COMMANDS.items()})


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(_usage(), end="")
        return 0 if args else 2
    if args[0] in ("-V", "--version"):
        from Terium import __version__

        print(f"terrium {__version__}")
        return 0
    command, rest = args[0], args[1:]
    if command not in COMMANDS:
        print(f"terrium: unknown command {command!r}\n", file=sys.stderr)
        print(_usage(), file=sys.stderr, end="")
        return 2
    import importlib

    module = importlib.import_module(COMMANDS[command][0])
    return int(module.main(rest) or 0)


if __name__ == "__main__":
    sys.exit(main())
