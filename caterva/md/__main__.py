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
import stat
import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple

from caterva.compose.organisms import normalise_organism
from caterva.md.setup import Conditions, MdSetup


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
            "\nThen: bash ldha-md/run.sh   (needs GROMACS: gmx on PATH, or GMX=/path/to/gmx)\n"
            "Exit codes: 0 written, 2 malformed question, 3 refused and said why, 1 a crash."
        ),
    )
    p.add_argument("--pdb", required=True, help="PDB entry id (find one with `caterva structure`)")
    p.add_argument("--chain", help="simulate one chain (a monomer of an oligomer); default: all")
    p.add_argument("--out", required=True, help="directory to write the setup into")
    p.add_argument("--subject", help="EC number, to take temperature and pH from the kinetics")
    p.add_argument("--organism", help="organism of those kinetics (Latin or common name)")
    p.add_argument("--substrate", help="the substrate whose Km's assay conditions to use")
    p.add_argument("--temperature", type=float, help="override: kelvin")
    p.add_argument("--ph", type=float, help="override: the pH to record for protonation")
    p.add_argument("--ns", type=float, default=10.0, help="production length in ns (default 10)")
    p.add_argument("--ionic-strength", type=float, default=0.15, help="NaCl, molar (default 0.15)")
    p.add_argument("--seed", type=int, default=20260927, help="velocity seed (default fixed)")
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
        if m.assay_ph is not None:
            c.ph = m.assay_ph
            c.ph_source = f"measured: pH {m.assay_ph:g} in {cite}"
        return c, f"conditions from {cite}"
    stated = ", ".join(f"{k.split('_')[1]} ({v.citation})" for k, v in measured.items())
    c.temperature_source = f"chosen: 25 C; none of the cited constants states a temperature: {stated}"
    return c, "no cited constant states its assay temperature; 25 C used, labelled a choice"


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva md") -> int:
    args = build_parser(prog).parse_args(argv)
    pdb = args.pdb.strip().upper()
    if len(pdb) != 4 or not pdb[0].isdigit() or not pdb.isalnum():
        print(f"Refused: {args.pdb!r} is not a PDB id (four characters, starting with a digit, like 1I10).",
              file=sys.stderr)
        return 2
    exit_code = 0
    conditions, note = Conditions(), None
    if args.subject or args.substrate:
        if not (args.subject and args.substrate):
            print("Refused: taking conditions from the kinetics needs both --subject and --substrate.",
                  file=sys.stderr)
            return 2
        organism, organism_note = normalise_organism(args.organism)
        if organism_note:
            print(organism_note)
        conditions, note = _from_kinetics(args.subject, organism, args.substrate)
        if not conditions.measured_temperature:
            exit_code = 3  # asked for measured conditions and did not get them: say so in the exit code
    if args.temperature is not None:
        conditions.temperature_k = args.temperature
        conditions.temperature_source = f"chosen: {args.temperature:g} K, set with --temperature"
        conditions.measured_temperature = False
    if args.ph is not None:
        conditions.ph = args.ph
        conditions.ph_source = "chosen: set with --ph"

    setup = MdSetup(pdb_id=pdb, chain=args.chain, conditions=conditions, ns=args.ns,
                    ionic_strength_m=args.ionic_strength, seed=args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in setup.files().items():
        path = out / name
        path.write_text(text, encoding="utf-8")
        if name.endswith(".sh"):
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if note:
        print(note)
    print(f"Wrote {out}/: run.sh, em/nvt/npt/md.mdp, PROVENANCE.md "
          f"({conditions.temperature_k:.2f} K, {args.ns:g} ns).")
    for p in setup.parameters:
        if p.origin != "method":
            print(f"  {p.name:<20} {p.value:<38} {p.origin}")
    print(f"Run it: bash {out}/run.sh   (GROMACS needed; GMX=/path/to/gmx to choose one)")
    return exit_code


def console_main() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
