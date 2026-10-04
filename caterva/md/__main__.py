"""`caterva md`: a GROMACS setup whose every number says where it came from.

    caterva md --pdb 1I10 --chain A --out ldha-md
    caterva md --pdb 1I10 --chain A --subject 1.1.1.27 --organism human \\
        --substrate pyruvate --out ldha-md

With --subject, --organism and --substrate, the literature is searched
first and the simulation runs at the temperature and pH the enzyme's Km was
MEASURED at, cited. Without them, 25 C is used and labelled a choice.
"""
from __future__ import annotations

import argparse
import math
import os
import secrets
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Sequence, TextIO, Tuple

from caterva.compose.organisms import normalise_organism
from caterva.md.setup import CHAIN_ID, PDB_ID, Conditions, MdSetup


def build_parser(prog: str = "caterva md") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Write a GROMACS setup (mdp files, a run script, PROVENANCE.md) for an "
            "enzyme structure. Each parameter is measured, chosen or cited; with "
            "--subject/--organism/--substrate the temperature and pH come from the "
            "assay behind the enzyme's cited Km."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            f"  {prog} --pdb 1I10 --chain A --out ldha-md\n"
            f"  {prog} --pdb 1I10 --chain A --subject 1.1.1.27 --organism human --substrate pyruvate --out ldha-md\n"
            f"  {prog} --summarise ldha-md          (after run.sh finishes)\n"
            "\nThen: bash ldha-md/run.sh   (needs GROMACS: gmx on PATH, or GMX=/path/to/gmx)\n"
            "Exit codes: 0 written, 2 malformed question, 3 refused and said why, 1 a crash."
        ),
    )
    p.add_argument("--pdb", help="PDB entry id (find one with `caterva structure`)")
    p.add_argument("--chain", help="simulate one chain (a monomer of an oligomer); default: all")
    p.add_argument("--out", help="directory to write the setup into")
    p.add_argument("--subject", help="EC number, to take temperature and pH from the kinetics")
    p.add_argument("--organism", help="organism of those kinetics (Latin or common name)")
    p.add_argument("--substrate", help="the substrate whose Km's assay conditions to use")
    p.add_argument("--temperature", type=float, help="override: kelvin")
    p.add_argument("--ph", type=float, help="override: the pH to record for protonation")
    p.add_argument("--ns", type=float, default=10.0, help="production length in ns (default 10)")
    p.add_argument("--ionic-strength", type=float, default=0.15, help="NaCl, molar (default 0.15)")
    p.add_argument("--seed", type=int, default=20260927,
                   help="velocity seed of replica 1; replica N uses seed+N-1 (default fixed)")
    p.add_argument("--replicas", type=int, default=3,
                   help="independent runs differing only in initial velocities (default 3; 1 is one sample)")
    p.add_argument("--summarise", metavar="DIR",
                   help="after run.sh: report each replica's backbone RMSD with block-averaged "
                        "errors and the spread across replicas, and say whether it converged")
    return p


def _from_kinetics(ec: str, organism: Optional[str], substrate: str) -> Tuple[Conditions, str]:
    """The assay conditions behind this enzyme's cited constants, or why there are none.

    Km, kcat and Ki are tried in that order and the FIRST one whose source
    states a temperature is used, and named: for human LDHA the Km's paper
    states no conditions, while the Ki's states pH 7.5 and 37 C. Conditions
    are never averaged across papers; one assay is one experiment.
    """
    from caterva.compose.__main__ import _search_the_literature
    from caterva.compose.pipeline import compose

    model = compose("Michaelis-Menten with a competitive inhibitor", subject=ec,
                    organism=organism, substrate=substrate)
    args = argparse.Namespace(subject=ec, organism=organism, substrate=substrate)
    model, note, refused = _search_the_literature(model, args)
    measured = getattr(model, "measured", None) or {}
    c = Conditions()
    if refused or not measured:
        return c, f"no measured constant to take conditions from ({note or 'nothing found'}); 25 C used, labelled a choice"
    for key, label in (("reaction_Km", "Km"), ("reaction_kcat", "kcat"), ("reaction_Ki", "Ki")):
        m = measured.get(key)
        if m is None or m.assay_temperature_c is None:
            continue
        cite = f"{m.citation}, the assay behind {label} = {m.value:g} {m.unit} ({m.organism})"
        c.temperature_k = m.assay_temperature_c + 273.15
        c.temperature_source = f"measured: {m.assay_temperature_c:g} C in {cite}"
        c.measured_temperature = True
        c.temperature_measurement = m
        if m.assay_ph is not None:
            c.ph = m.assay_ph
            c.ph_source = f"measured: pH {m.assay_ph:g} in {cite}"
            c.ph_measurement = m
        return c, f"conditions from {cite}"
    stated = ", ".join(f"{k.split('_')[1]} ({v.citation})" for k, v in measured.items())
    c.temperature_source = f"chosen: 25 C; none of the cited constants states a temperature: {stated}"
    return c, "no cited constant states its assay temperature; 25 C used, labelled a choice"


#: Limits a request is held to (a script and mdp files are written from them).
MAX_REPLICAS = 50
MAX_NS = 10_000.0
MAX_SEED = 2**31 - 1


def check(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """The refusals argparse cannot express on its own, through `parser.error`
    (exit 2), so that anything driving this parser (the studio refuses a
    malformed request before a run exists) sees them as argparse's."""
    if args.summarise:
        return
    if not args.pdb or not args.out:
        parser.error("a setup needs --pdb and --out (or use --summarise DIR on a finished run)")
    if args.replicas < 1:
        parser.error("--replicas must be at least 1")
    if args.replicas > MAX_REPLICAS:
        parser.error(f"--replicas must be at most {MAX_REPLICAS}")
    if PDB_ID.fullmatch(args.pdb) is None:
        parser.error(f"{args.pdb!r} is not a PDB id (four ASCII characters, a digit then letters or digits, "
                     "like 1I10)")
    if args.chain is not None and CHAIN_ID.fullmatch(args.chain) is None:
        parser.error(f"{args.chain!r} is not a chain id (one to four ASCII letters or digits, like A)")
    for flag, value, low, high, nonzero in (("--ns", args.ns, 0.0, MAX_NS, True),
                                            ("--ionic-strength", args.ionic_strength, 0.0, 5.0, False),
                                            ("--temperature", args.temperature, 0.0, 1000.0, True),
                                            ("--ph", args.ph, 0.0, 14.0, False)):
        if value is None:
            continue
        if not math.isfinite(value) or not low <= value <= high or (nonzero and value == low):
            parser.error(f"{flag} must be a finite number up to {high:g}" + (" and above zero" if nonzero else
                                                                             f", from {low:g}"))
    if not 0 <= args.seed <= MAX_SEED:
        parser.error(f"--seed must be a whole number from 0 to {MAX_SEED}")
    if (args.subject or args.substrate) and not (args.subject and args.substrate):
        parser.error("taking conditions from the kinetics needs both --subject and --substrate")


@dataclass
class Planned:
    """A setup computed and not yet written: what `main` writes and prints."""

    setup: MdSetup
    #: Where the conditions came from, or why they are not measured.
    note: Optional[str]
    #: 3 when measured conditions were asked for and not found, else 0.
    exit_code: int


def plan(args: argparse.Namespace, out: Optional[TextIO] = None) -> Planned:
    """The setup a well-formed question asks for (after `check`): the
    literature searched when --subject and --substrate ask for measured
    conditions, the overrides applied, nothing written."""
    exit_code = 0
    conditions, note = Conditions(), None
    if args.subject or args.substrate:
        organism, organism_note = normalise_organism(args.organism)
        if organism_note:
            print(organism_note, file=out)
        conditions, note = _from_kinetics(args.subject, organism, args.substrate)
        if not conditions.measured_temperature:
            exit_code = 3  # asked for measured conditions and did not get them: say so in the exit code
    if args.temperature is not None:
        conditions.temperature_k = args.temperature
        conditions.temperature_source = f"chosen: {args.temperature:g} K, set with --temperature"
        conditions.measured_temperature = False
        conditions.temperature_measurement = None
    if args.ph is not None:
        conditions.ph = args.ph
        conditions.ph_source = "chosen: set with --ph"
        conditions.ph_measurement = None
    setup = MdSetup(pdb_id=args.pdb.upper(), chain=args.chain, conditions=conditions, ns=args.ns,
                    ionic_strength_m=args.ionic_strength, seed=args.seed, replicas=args.replicas)
    return Planned(setup, note, exit_code)


class UnsafeOutput(ValueError):
    """The output folder holds a link, so writing there could change a file
    elsewhere; nothing was written."""


def _links_inside(root: Path) -> List[Path]:
    """Every symbolic link anywhere under `root` (not followed)."""
    found: List[Path] = []
    for folder, names, files in os.walk(root, followlinks=False):
        for name in [*names, *files]:
            path = Path(folder) / name
            if path.is_symlink():
                found.append(path)
    return found


def write(setup: MdSetup, out: Path) -> List[str]:
    """Write the setup's files under `out`; their names, in the order written.

    A link inside an existing `out` (a run.sh that points at another file,
    say) would be written THROUGH, changing a file the setup has nothing to
    do with. So `out` is refused (UnsafeOutput, nothing written) when it holds
    a link anywhere; the files are first written into a new folder beside it
    (exclusive create, links not followed), and only then moved into place
    with a rename, which replaces a link rather than following it."""
    files = setup.files()
    if out.exists() and out.is_dir():
        links = _links_inside(out)
        if links:
            raise UnsafeOutput(f"{out} holds a symbolic link ({links[0].relative_to(out)}); remove it or choose "
                               "another folder: the setup does not write through links")
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = out.parent / f".caterva-md-{secrets.token_hex(6)}"
    os.mkdir(staging)
    try:
        names = []
        for name, text in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = 0o755 if name.endswith(".sh") else 0o644
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), mode)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            if name.endswith(".sh"):
                path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            names.append(name)
        if not out.exists():
            os.rename(staging, out)
            staging = None  # type: ignore[assignment]
        else:
            for name in names:
                target = out / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink():
                    raise UnsafeOutput(f"{target} became a link while the setup was written; nothing more was written")
                os.replace(staging / name, target)
        return names
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def written_lines(planned: Planned, out: Path, prog: str = "caterva md") -> List[str]:
    """What `main` prints once the files are written."""
    setup = planned.setup
    lines = [planned.note] if planned.note else []
    lines.append(f"Wrote {out}/: run.sh, em/npt/md.mdp, rep1..rep{setup.replicas}/nvt.mdp, PROVENANCE.md "
                 f"({setup.conditions.temperature_k:.2f} K, {setup.ns:g} ns, {setup.replicas} replica"
                 f"{'s' if setup.replicas > 1 else ''}).")
    if setup.replicas == 1:
        lines.append("  One replica is one sample: it has no spread, and nothing it shows can be told apart "
                     "from chance.")
    for p in setup.parameters:
        if p.origin != "method":
            lines.append(f"  {p.name:<20} {p.value:<38} {p.origin}")
    lines.append(f"Run it: bash {out}/run.sh   (GROMACS needed; GMX=/path/to/gmx to choose one)")
    lines.append(f"Then:   {prog} --summarise {out}")
    return lines


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva md") -> int:
    parser = build_parser(prog)
    args = parser.parse_args(argv)
    try:
        check(parser, args)
    except SystemExit as refused:  # parser.error printed the usage and the reason
        return int(refused.code or 2)
    if args.summarise:
        return summarise_run(Path(args.summarise)).code
    planned = plan(args)
    out = Path(args.out)
    try:
        write(planned.setup, out)
    except UnsafeOutput as refused:
        print(f"Refused: {refused}", file=sys.stderr)
        return 3
    for line in written_lines(planned, out, prog):
        print(line)
    return planned.exit_code


#: `--summarise` found the run is not (yet) a result.
EXIT_NOT_A_RESULT = 4


@dataclass
class Summarised:
    """What `--summarise DIR` read, decided and printed."""

    code: int
    summary: Optional[Any] = None
    #: The report, as printed and as written to CONVERGENCE.md.
    text: str = ""
    #: The refusal printed to stderr, for exit 3.
    refusal: Optional[str] = None
    written: Optional[Path] = None


def summarise_run(directory: Path, out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> Summarised:
    """Each replica's backbone RMSD, block-averaged and compared across
    replicas; the report printed and written to DIR/CONVERGENCE.md."""
    from caterva.md.convergence import collect, report, summarise

    series = collect(directory)
    if not series:
        refusal = f"Refused: no rep*/rmsd.xvg under {directory}. Run its run.sh first."
        print(refusal, file=sys.stderr if err is None else err)
        return Summarised(3, refusal=refusal)
    s = summarise(series, "backbone RMSD from the starting structure", "nm")
    text = "\n".join(report(s)) + "\n"
    print(text, end="", file=out)
    written = directory / "CONVERGENCE.md"
    written.write_text(text, encoding="utf-8")
    return Summarised(0 if s.verdict == "consistent" else EXIT_NOT_A_RESULT, s, text, None, written)


def console_main() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
