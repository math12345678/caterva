"""One executable for the downloadable app: `caterva <command>`.

WHY THIS EXISTS
---------------
The wheel installs two console scripts, `caterva` (the simulation engine)
and `caterva-compose` (the model builder). A frozen app bundle is one
folder with one executable, and a bundle built from two entry points
either doubles its size or depends on a multi-executable feature of the
freezer that cannot be exercised on this machine. So the bundle ships one
binary, `caterva`, and this module is what it runs: the first argument
picks the command and the rest is passed through unchanged.

    caterva compose "a toggle switch between two repressors"
    caterva sim wf --population-size 100 --generations 50
    caterva --version

`python -m caterva.app ...` runs the same code from a checkout or a wheel,
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
#: `caterva/__init__.py` loads the engine, and with it roadrunner, antimony
#: and libsbml, at import. In the frozen folder that is also the cheapest
#: proof that the native libraries load.)
COMMANDS = {
    "compose": ("caterva.compose.__main__", "the model builder and its analyses"),
    "rates": ("caterva.rates.__main__", "fit your own initial rates: constants, mechanism, and the cited values"),
    "structure": ("caterva.structure.__main__", "an enzyme's PDB structures, cited, and a ChimeraX script"),
    "md": ("caterva.md.__main__", "a GROMACS setup whose every parameter is measured, chosen or cited"),
    "analyze": ("caterva.analyze.__main__", "catalytic geometry and active-site flexibility across replicas"),
    "bind": ("caterva.bind.__main__", "the measured binding free energy a simulation is held to, from cited Ki"),
    "complex": ("caterva.fep.complex", "a PDB entry and your ligand topology, posed and equilibrated for caterva fep"),
    "fep": ("caterva.fep.__main__", "an absolute binding free energy, run at and judged against a cited Ki"),
    "prepare": ("caterva.prepare.__main__", "audit a PDB entry before simulating it, defects ranked by distance to the active site"),
    "sim": ("caterva.cli", "exact stochastic chemical kinetics (Gillespie SSA)"),
}

USAGE = """caterva {version} -- mechanistic models whose every number says where it came from.

QUICK START, in the order that teaches the most

  caterva compose "a toggle switch between two repressors"
      Build a model from the shape of a mechanism and report on it. Read the
      VERDICT at the top: what the model supports, and the worst thing wrong
      with it. Then "Where the numbers come from": which constants are
      measurements and which are placeholders nobody measured.

  caterva compose --shapes
      The {shapes} mechanisms it can build, each in one line. Describe any of
      them in your own words.

  caterva compose "Michaelis Menten" --subject 2.7.1.1 --organism human --substrate glucose
      The same, with real measured constants from BRENDA, each cited.

  caterva compose "Michaelis-Menten with a competitive inhibitor" --design
      Which measurement to make next, and what it would newly pin down.

IT RECOGNISES A SHAPE, NEVER A SUBJECT

  "two genes repressing each other"  builds.  "glycolysis" does not, and says
  why: that needs a pathway database, and guessing one would be worse than
  refusing. Most refusals are this.

COMMANDS

{commands}

  caterva <command> --help   every option, with examples
  caterva --version          the version and exit

REAL CONSTANTS, WITH REAL CITATIONS

  Name the enzyme (its EC number), the organism and the substrate, and
  compose searches BRENDA and puts the measured values in the model, each
  with the reference it came from:

      caterva compose "Michaelis Menten" --subject 1.1.1.27 --organism human --substrate pyruvate
      -> Km 0.03 mM (BRENDA ref 286469), from the paper that measured it

  A value nobody measured stays a labelled placeholder, and the report says
  why: most often it exists in another organism, which it names. Find an
  EC number by searching the enzyme on https://www.brenda-enzymes.org.
  The search needs the source checkout (git clone, then make setup); the
  downloaded app folder builds and simulates but cannot search, and says so.

MORE

  Analyses to add to compose: --screen (which species matters), --robustness
  (does the conclusion survive not knowing the constants), --scale and
  --predictions (is it physically possible, in and out), --sweep (where it
  switches), --stochastic (single-molecule noise).
  Exports: --export methods | csv | sbml | antimony.
  Exit codes: 0 all good, 2 malformed question, 3 something refused and said
  why (the report still printed), 1 a crash.
  The full guide is docs/USING_CATERVA.md in the repository.
"""


def _usage() -> str:
    from caterva import __version__

    # The shape count is read from the grammar rather than written here, so
    # this text cannot claim a number the builder does not have.
    try:
        from caterva.compose.grammar import shapes

        count = str(len(shapes()))
    except Exception:  # noqa: BLE001 - a usage message must never fail to print
        count = "many"
    return USAGE.format(
        version=__version__,
        shapes=count,
        commands="\n".join(f"  {k:<9} {v[1]}" for k, v in COMMANDS.items()),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(_usage(), end="")
        return 0 if args else 2
    if args[0] in ("-V", "--version"):
        from caterva import __version__

        print(f"caterva {__version__}")
        return 0
    command, rest = args[0], args[1:]
    if command not in COMMANDS:
        print(f"caterva: unknown command {command!r}\n", file=sys.stderr)
        print(_usage(), file=sys.stderr, end="")
        return 2
    import importlib

    module = importlib.import_module(COMMANDS[command][0])
    # The command names itself the way the user typed it, so its --help and
    # examples show `caterva compose ...`, not a python invocation the folder
    # cannot run.
    return int(module.main(rest, prog=f"caterva {command}") or 0)


if __name__ == "__main__":
    sys.exit(main())
