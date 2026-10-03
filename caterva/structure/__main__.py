"""`caterva structure`: the experimental structures of an enzyme, cited.

    caterva structure --subject 1.1.1.27 --organism human --gene LDHA
    caterva structure --subject 1.1.1.27 --organism human --gene LDHA \\
        --ligand oxamate --chimerax ldha.cxc

Exit codes follow the rest of Caterva: 0 produced what was asked, 2 a
malformed question, 3 refused and said why (an enzyme name that is several
enzymes, an EC number that is several proteins, no structure, no network),
1 a crash.

`--subject` takes an EC number or an enzyme name. The name is read by
caterva.enzymes.policy, the same function `caterva compose` uses, so a name
that is several enzymes is refused here with each candidate named.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from caterva.compose.organisms import normalise_organism
from caterva.enzymes.policy import NameNotResolved, literature_uniprot_lookup, resolve_enzyme_name
from caterva.methods import METHODS
from caterva.structure.search import StructureSearchError, find_structures

ROLES = ("ligand", "cofactor", "metal", "additive")


def build_parser(prog: str = "caterva structure") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Find the experimental structures of an enzyme in the PDB, grouped by "
            "protein, each with its method, resolution, primary citation and what "
            "is bound in it -- ligands, cofactors and metals kept apart from "
            "crystallisation additives. Optionally write a ChimeraX script."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            f"  {prog} --subject 1.1.1.27 --organism human\n"
            f"  {prog} --subject 1.1.1.27 --organism human --gene LDHA --ligand oxamate --chimerax ldha.cxc\n"
            f"  {prog} --subject 3.1.1.7 --organism 'Torpedo californica' --top 3\n"
            "\nExit codes: 0 produced, 2 malformed question, 3 refused and said why, 1 a crash."
        ),
    )
    p.add_argument("--subject", required=True,
                   help="the enzyme, as an EC number (1.1.1.27) or a name (pyruvate kinase); a name that is "
                        "several enzymes is refused with each one named")
    p.add_argument("--organism", help="Latin or common name (human, mouse, E. coli)")
    p.add_argument("--gene", help="which protein, by gene name (LDHA), when the EC number is several")
    p.add_argument("--uniprot", help="which protein, by UniProt accession (P00338)")
    p.add_argument("--ligand", help="prefer entries with this molecule bound (id like OXM, or a name)")
    p.add_argument("--top", type=int, default=10, help="how many entries to list (default 10)")
    p.add_argument("--chimerax", metavar="FILE", help="write a ChimeraX script for the top entry")
    return p


def _report(search, top: int) -> List[str]:
    lines = [f"# Structures for EC {search.ec}" + (f" in {search.organism}" if search.organism else ""), ""]
    lines.append("| protein | gene | UniProt | entries |")
    lines.append("|---|---|---|---|")
    for p in search.proteins:
        mark = " **(chosen)**" if search.chosen and p.accession == search.chosen.accession else ""
        lines.append(f"| {p.name}{mark} | {p.gene or '?'} | {p.accession} | {len(p.structures)} |")
    lines.append("")
    ranked = search.ranked()
    if not ranked:
        return lines
    shown = ranked[:top]
    lines.append(f"## {search.chosen.gene or search.chosen.accession}: {len(ranked)} entries, best evidence first")
    lines.append("")
    if search.ligand:
        n = sum(1 for s in ranked if s.binds(search.ligand))
        lines.append(f"{n} of {len(ranked)} entries have {search.ligand!r} bound; those are listed first.")
        lines.append("")
    lines.append("| PDB | method | resolution | ligands | cofactors | additives | primary citation |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in shown:
        def names(role: str) -> str:
            return ", ".join(b.component for b in s.with_role(role)) or "none"
        res = f"{s.resolution:.2f} A" if s.resolution is not None else "n/a"
        lines.append(
            f"| [{s.pdb_id}](https://www.rcsb.org/structure/{s.pdb_id}) | {s.method.lower()} | {res} "
            f"| {names('ligand')} | {names('cofactor')}{'; metals ' + names('metal') if s.with_role('metal') else ''} "
            f"| {names('additive')} | {s.cite()} |"
        )
    if len(ranked) > top:
        lines.append(f"\n{len(ranked) - top} more; raise --top to see them.")
    lines += [
        "",
        "Ordering is by the ligand asked for, then experimental method, then "
        "resolution: numbers a reader can check, not a judgement of quality. "
        "Additives are there because of how the crystal was grown.",
        "",
        f"Sources: {METHODS['pdb'].cite()}; UniProt for the protein grouping.",
    ]
    return lines


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva structure") -> int:
    args = build_parser(prog).parse_args(argv)
    organism, organism_note = normalise_organism(args.organism)
    try:
        # The same function every command uses to read an enzyme name; an EC
        # number passes through it, a name is looked up in the nomenclature.
        resolution = resolve_enzyme_name(
            args.subject, organism, uniprot=literature_uniprot_lookup(), allow_unlisted_ec=True)
    except NameNotResolved as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 3
    for line in resolution.notes(args.subject):
        print(line + "\n")
    try:
        search = find_structures(resolution.ec, organism=organism, gene=args.gene,
                                 uniprot=args.uniprot, ligand=args.ligand)
    except StructureSearchError as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 3
    if organism_note:
        print(organism_note + "\n")
    print("\n".join(_report(search, args.top)))
    if search.undecided:
        print(f"\nRefused: {search.undecided}")
        return 3
    if args.chimerax:
        from caterva.structure.chimerax import script

        best = search.ranked()[0]
        Path(args.chimerax).write_text(script(best, search.chosen, focus=args.ligand), encoding="utf-8")
        print(f"\nWrote {args.chimerax}: PDB {best.pdb_id}. Run it with `chimerax {args.chimerax}`.")
    return 0


def console_main() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
