"""A ChimeraX script that opens a structure the way the question needs it.

The script is plain ChimeraX command syntax (`.cxc`): run it with
`chimerax script.cxc`, or `open script.cxc` inside ChimeraX. It fetches the
entry from the PDB, shows the protein as cartoon and the chosen ligand as
sticks with the residues within 5 A of it, and hides crystallisation
additives so glycerol does not read as part of the chemistry. The header
cites the entry and ChimeraX itself.
"""
from __future__ import annotations

from typing import Optional

from caterva.methods import METHODS
from caterva.structure.search import Protein, Structure, matches


def script(structure: Structure, protein: Protein, focus: Optional[str] = None,
           zone: float = 5.0) -> str:
    """The .cxc text for one structure. `focus` is a component id or name."""
    ligands = structure.with_role("ligand")
    cofactors = structure.with_role("cofactor")
    additives = structure.with_role("additive")

    chosen = None
    if focus:
        chosen = next((b for b in structure.bound
                       if b.role != "additive" and matches(b, focus)), None)
    if chosen is None and ligands:
        chosen = ligands[0]

    res = f"{structure.resolution:.2f} A" if structure.resolution else "resolution not stated"
    lines = [
        f"# Caterva: {protein.name} ({protein.gene or '?'}, UniProt {protein.accession}), {protein.organism}",
        f"# PDB {structure.pdb_id}: {structure.title}",
        f"# {structure.method.lower()}, {res}",
        f"# Structure: {structure.cite()}",
        f"# Database: {METHODS['pdb'].cite()}",
        f"# Viewer: {METHODS['chimerax'].cite()}",
    ]
    if focus and (chosen is None or not matches(chosen, focus)):
        lines.append(f"# NOTE: {focus!r} is not bound in this entry; showing "
                     + (f"{chosen.component} instead." if chosen else "the protein only."))
    lines += [
        f"open {structure.pdb_id.lower()}",
        "hide atoms",
        "cartoon",
        "color bychain",
        "set bgColor white",
        "lighting soft",
        "graphics silhouettes true",
    ]
    if additives:
        lines.append("# crystallisation additives, not part of the chemistry")
        lines.append("hide :" + ",".join(b.component for b in additives))
    if cofactors:
        spec = ":" + ",".join(b.component for b in cofactors)
        lines += [f"show {spec}", f"style {spec} stick", f"color {spec} lightgray", f"color {spec} byhetero"]
    if chosen is not None:
        spec = f":{chosen.component}"
        lines += [
            f"# {chosen.component}: {chosen.name}",
            f"show {spec}",
            f"style {spec} stick",
            f"color {spec} orange",
            f"color {spec} byhetero",
            f"# residues within {zone:g} A of it",
            f"show ({spec} :<{zone:g}) & protein",
            f"label ({spec} :<{zone:g}) & protein residues",
            f"view {spec}",
        ]
    else:
        lines.append("view")
    return "\n".join(lines) + "\n"


__all__ = ["script"]
