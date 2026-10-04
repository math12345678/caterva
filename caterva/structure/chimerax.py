"""A ChimeraX script that opens a structure the way the question needs it.

The script is plain ChimeraX command syntax (`.cxc`): run it with
`chimerax script.cxc`, or `open script.cxc` inside ChimeraX. It fetches the
entry from the PDB, shows the protein as cartoon and the chosen ligand as
sticks with the residues within 5 A of it, and hides crystallisation
additives so glycerol does not read as part of the chemistry. The header
cites the entry and ChimeraX itself.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from caterva.methods import METHODS
from caterva.structure.search import Protein, Structure, matches


_ID = re.compile(r"[A-Za-z0-9]+", re.ASCII)


def one_line(text: object) -> str:
    """`text` for a comment of the script: every control character (a
    newline, a carriage return, U+2028, a NUL) and every other line or
    paragraph separator becomes a space, so a name from the PDB or a
    request can never end the comment and begin a command."""
    cleaned = "".join(" " if (unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") or c in "\r\n") else c
                      for c in str(text))
    return " ".join(cleaned.split())


def identifier(text: object) -> str:
    """`text` as an identifier that may stand in a ChimeraX command (a PDB id,
    a component id): ASCII letters and digits only, everything else dropped."""
    return "".join(_ID.findall(str(text)))


def script(structure: Structure, protein: Protein, focus: Optional[str] = None,
           zone: float = 5.0) -> str:
    """The .cxc text for one structure. `focus` is a component id or name.

    Every field that came from the PDB, UniProt or the request is cleaned
    before it is written: free text into comments with `one_line`, and the
    ids that stand in commands with `identifier`."""
    pdb_id = identifier(structure.pdb_id)
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
        f"# Caterva: {one_line(protein.name)} ({one_line(protein.gene or '?')}, "
        f"UniProt {one_line(protein.accession)}), {one_line(protein.organism)}",
        f"# PDB {pdb_id}: {one_line(structure.title)}",
        f"# {one_line(structure.method).lower()}, {res}",
        f"# Structure: {one_line(structure.cite())}",
        f"# Database: {METHODS['pdb'].cite()}",
        f"# Viewer: {METHODS['chimerax'].cite()}",
    ]
    if focus and (chosen is None or not matches(chosen, focus)):
        lines.append(f"# NOTE: {one_line(focus)!r} is not bound in this entry; showing "
                     + (f"{identifier(chosen.component)} instead." if chosen else "the protein only."))
    lines += [
        f"open {pdb_id.lower()}",
        "hide atoms",
        "cartoon",
        "color bychain",
        "set bgColor white",
        "lighting soft",
        "graphics silhouettes true",
    ]
    if additives:
        lines.append("# crystallisation additives, not part of the chemistry")
        lines.append("hide :" + ",".join(identifier(b.component) for b in additives))
    if cofactors:
        spec = ":" + ",".join(identifier(b.component) for b in cofactors)
        lines += [f"show {spec}", f"style {spec} stick", f"color {spec} lightgray", f"color {spec} byhetero"]
    if chosen is not None:
        spec = f":{identifier(chosen.component)}"
        lines += [
            f"# {identifier(chosen.component)}: {one_line(chosen.name)}",
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


__all__ = ["identifier", "one_line", "script"]
