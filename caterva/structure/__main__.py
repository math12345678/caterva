"""`caterva structure`: the experimental structures of an enzyme, cited.

    caterva structure --subject 1.1.1.27 --organism human --gene LDHA
    caterva structure --subject hexokinase --organism human
    caterva structure --subject 1.1.1.27 --organism human --gene LDHA \\
        --ligand oxamate --chimerax ldha.cxc

Exit codes follow the rest of Caterva: 0 produced what was asked, 2 a
malformed question, 3 refused and said why (an enzyme name that is several
enzymes, an EC number that is several proteins, no structure, no network, a
ChimeraX script for a protein with no entry to open), 1 a crash.

`--subject` takes an EC number or an enzyme name. The name is read by
caterva.enzymes.policy, the same function `caterva compose` uses, so a name
that is several enzymes is refused here with each candidate named.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, TextIO

from caterva.compose.organisms import normalise_organism
from caterva.enzymes.policy import NameNotResolved, literature_uniprot_lookup, refusal_view, resolve_enzyme_name
from caterva.methods import METHODS
from caterva.structure.search import Structure, StructureSearch, StructureSearchError, find_structures

ROLES = ("ligand", "cofactor", "metal", "additive")

#: What reads as an EC number (complete, partial or preliminary, "3.2.1.n3").
#: Anything else is a name, which may need the literature layer's UniProt
#: fallback; the policy itself reads both.
EC_LIKE = re.compile(r"\s*\d+(\.(\d+|n\d*|-)){0,3}\.?\s*")


@dataclass
class Subject:
    """What `--subject` named: the EC number searched, or why there is none.

    `notes` are the sentences the policy wants read (a name read as an EC
    number, a transferred number); `refusal` is the policy's refusal as the
    command prints it and `view` the same refusal as data, each candidate
    named (`caterva.enzymes.policy.refusal_view`)."""

    ec: Optional[str]
    name: Optional[str] = None
    refusal: Optional[str] = None
    view: Optional[dict] = None
    notes: List[str] = field(default_factory=list)


def subject_ec(subject: str, organism: Optional[str] = None) -> Subject:
    """The EC number to search for `--subject`, by the one policy every
    command uses to read an enzyme name."""
    text = subject.strip()
    try:
        resolution = resolve_enzyme_name(
            text, organism, uniprot=literature_uniprot_lookup(), allow_unlisted_ec=True)
    except NameNotResolved as exc:
        return Subject(None, text, f"Refused: {exc}", refusal_view(exc))
    return Subject(resolution.ec, None if EC_LIKE.fullmatch(text) else text, notes=resolution.notes(text))


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


@dataclass
class StructureRun:
    """What one `caterva structure` question found, printed and decided.

    `main` prints it and exits with `code`; the studio's adapter
    (caterva/studio/adapters/structure.py) reads the same object, so the
    page and the terminal are drawn from one search rather than two.
    """

    code: int
    organism: Optional[str]
    organism_note: Optional[str]
    search: Optional[StructureSearch]
    #: The refusal exactly as printed ("Refused: ..."), for exit 3.
    refusal: Optional[str] = None
    #: The top entry and the ChimeraX script written for it, when asked.
    best: Optional[Structure] = None
    chimerax: Optional[str] = None
    #: What --subject named, and the EC number it was resolved to.
    subject: Optional[Subject] = None


def run(args: argparse.Namespace, out: Optional[TextIO] = None, err: Optional[TextIO] = None,
        write: bool = True) -> StructureRun:
    """Search, print the report to `out` and any refusal to `err`, and
    write the ChimeraX script (unless `write` is False: the studio stores
    the script itself, as a run artifact at the same path).

    `--chimerax` with no entry to open used to index `ranked()[0]` of an
    empty ranking (a chosen protein with no structure) and crash; it is a
    refusal with a reason now, exit 3, after the table that shows why.
    """
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    organism, organism_note = normalise_organism(args.organism)
    subject = subject_ec(args.subject, organism)
    if subject.ec is None:
        print(subject.refusal, file=err)
        return StructureRun(3, organism, organism_note, None, subject.refusal, subject=subject)
    for line in subject.notes:
        print(line + "\n", file=out)
    try:
        search = find_structures(subject.ec, organism=organism, gene=args.gene,
                                 uniprot=args.uniprot, ligand=args.ligand)
    except StructureSearchError as exc:
        refusal = f"Refused: {exc}"
        print(refusal, file=err)
        return StructureRun(3, organism, organism_note, None, refusal, subject=subject)
    if organism_note:
        print(organism_note + "\n", file=out)
    print("\n".join(_report(search, args.top)), file=out)
    if search.undecided:
        refusal = f"Refused: {search.undecided}"
        print(f"\n{refusal}", file=out)
        return StructureRun(3, organism, organism_note, search, refusal, subject=subject)
    if args.chimerax:
        from caterva.structure.chimerax import script

        ranked = search.ranked()
        if not ranked:
            chosen = search.chosen
            refusal = (f"Refused: {chosen.gene or chosen.accession} ({chosen.accession}) has no entry in the "
                       "PDB, so there is no structure to write a ChimeraX script for.")
            print(refusal, file=err)
            return StructureRun(3, organism, organism_note, search, refusal, subject=subject)
        best = ranked[0]
        text = script(best, search.chosen, focus=args.ligand)
        if write:
            Path(args.chimerax).write_text(text, encoding="utf-8")
        print(f"\nWrote {args.chimerax}: PDB {best.pdb_id}. Run it with `chimerax {args.chimerax}`.", file=out)
        return StructureRun(0, organism, organism_note, search, None, best, text, subject)
    return StructureRun(0, organism, organism_note, search, subject=subject)


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva structure") -> int:
    args = build_parser(prog).parse_args(argv)
    return run(args).code


def console_main() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
