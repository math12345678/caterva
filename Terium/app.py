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

USAGE = """terrium {version} -- mechanistic models whose every number says where it came from.

QUICK START, in the order that teaches the most

  terrium compose "a toggle switch between two repressors"
      Build a model from the shape of a mechanism and report on it. Read the
      VERDICT at the top: what the model supports, and the worst thing wrong
      with it. Then "Where the numbers come from": which constants are
      measurements and which are placeholders nobody measured.

  terrium compose --shapes
      The {shapes} mechanisms it can build, each in one line. Describe any of
      them in your own words.

  terrium compose "Michaelis-Menten with a competitive inhibitor" --design
      Which measurement to make next, and what it would newly pin down.

IT RECOGNISES A SHAPE, NEVER A SUBJECT

  "two genes repressing each other"  builds.  "glycolysis" does not, and says
  why: that needs a pathway database, and guessing one would be worse than
  refusing. Most refusals are this.

COMMANDS

  compose   {compose}
  sim       {sim}

  terrium <command> --help   every option, with examples
  terrium --version          the version and exit

REAL CONSTANTS, WITH REAL CITATIONS

  compose builds STRUCTURE: every constant is the motif library's
  illustrative placeholder, and the report says so on every page. Measured
  values with the paper that measured them come from the literature layer,
  which needs the source checkout, not this folder:

      make cite EC=1.1.1.27 SUBSTRATE=pyruvate ORGANISM="Homo sapiens"
      -> km = 0.03 mM, from BRENDA ref 286469

  See docs/USING_TERRIUM.md. Joining the two -- a composed mechanism whose
  constants are sourced -- is not wired yet; ADR 0178 says what it needs.

MORE

  Analyses to add to compose: --screen (which species matters), --robustness
  (does the conclusion survive not knowing the constants), --scale and
  --predictions (is it physically possible, in and out), --sweep (where it
  switches), --stochastic (single-molecule noise).
  Exports: --export methods | csv | sbml | antimony.
  Exit codes: 0 all good, 2 malformed question, 3 something refused and said
  why (the report still printed), 1 a crash.
  The full guide is docs/USING_TERRIUM.md in the repository.
"""


def _usage() -> str:
    from Terium import __version__

    # The shape count is read from the grammar rather than written here, so
    # this text cannot claim a number the builder does not have.
    try:
        from Terium.compose.grammar import shapes

        count = str(len(shapes()))
    except Exception:  # noqa: BLE001 - a usage message must never fail to print
        count = "many"
    return USAGE.format(
        version=__version__,
        shapes=count,
        **{k: v[1] for k, v in COMMANDS.items()},
    )


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
    # The command names itself the way the user typed it, so its --help and
    # examples show `terrium compose ...`, not a python invocation the folder
    # cannot run.
    return int(module.main(rest, prog=f"terrium {command}") or 0)


if __name__ == "__main__":
    sys.exit(main())
