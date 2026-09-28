"""What to measure in an enzyme trajectory, decided by the enzyme.

A generic analysis (RMSD, radius of gyration) asks the same questions of
every protein. The questions that matter for an enzyme are fixed by its
mechanism: do the catalytic residues stay where the chemistry needs them,
and is the active site more or less mobile than the rest of the protein?

The catalytic residues come from M-CSA via `caterva prepare`. For each
residue the *functional* atoms are taken -- the ones that do the chemistry
(a histidine's ring nitrogens, a carboxylate's oxygens) -- and each group is
reduced to its geometric centre, so a carboxylate that flips its two oxygens
is not reported as moving. Every pair of catalytic residues gives one
distance; its value in the starting structure is computed here, from the
same atoms, so the trajectory is compared with the crystal rather than
with itself.

Nothing here runs GROMACS. It reads a PDB file and returns selections.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

#: Side-chain atoms that carry each residue's chemistry. Residues not listed
#: (Gly, Ala, and the hydrophobics) act through the backbone or not at all;
#: they fall back to CA, and the report says so.
FUNCTIONAL_ATOMS: Dict[str, Tuple[str, ...]] = {
    "HIS": ("ND1", "NE2"), "ASP": ("OD1", "OD2"), "GLU": ("OE1", "OE2"),
    "ARG": ("NE", "NH1", "NH2"), "LYS": ("NZ",), "SER": ("OG",), "THR": ("OG1",),
    "TYR": ("OH",), "CYS": ("SG",), "ASN": ("OD1", "ND2"), "GLN": ("OE1", "NE2"),
    "TRP": ("NE1",), "MET": ("SD",),
}
# GROMACS renames protonation variants of histidine; the atoms are the same.
for _v in ("HID", "HIE", "HIP", "HSD", "HSE", "HSP"):
    FUNCTIONAL_ATOMS[_v] = FUNCTIONAL_ATOMS["HIS"]

#: Residues within this distance (any atom) of a catalytic residue form the
#: pocket for the flexibility comparison. A choice, and reported as one.
POCKET_RADIUS = 8.0


@dataclass(frozen=True)
class Atom:
    chain: str
    resnr: int
    resname: str
    name: str
    xyz: Tuple[float, float, float]


def read_pdb(text: str, chain: Optional[str] = None) -> List[Atom]:
    """ATOM records (first model only), optionally one chain."""
    out: List[Atom] = []
    for line in text.splitlines():
        if line.startswith("ENDMDL"):
            break
        if not line.startswith("ATOM"):
            continue
        ch = line[21].strip()
        if chain and ch != chain:
            continue
        alt = line[16]
        if alt not in (" ", "A"):
            continue  # keep the first conformer, as pdb2gmx does
        out.append(Atom(ch, int(line[22:26]), line[17:20].strip(), line[12:16].strip(),
                        (float(line[30:38]), float(line[38:46]), float(line[46:54]))))
    return out


@dataclass(frozen=True)
class Site:
    resnr: int
    resname: str
    atoms: Tuple[str, ...]
    functional: bool  # False when only CA was available

    @property
    def label(self) -> str:
        return f"{self.resname.title()}{self.resnr}"

    def selection(self) -> str:
        return f"cog of (resnr {self.resnr} and name {' '.join(self.atoms)})"


@dataclass(frozen=True)
class Pair:
    a: Site
    b: Site
    crystal_nm: Optional[float]  # None when an atom is missing from the start structure

    @property
    def label(self) -> str:
        return f"{self.a.label}–{self.b.label}"

    def selection(self) -> str:
        return f"{self.a.selection()} plus {self.b.selection()}"


@dataclass
class Plan:
    sites: List[Site]
    pairs: List[Pair]
    pocket: List[int]  # residue numbers
    rest: List[int]
    notes: List[str]


def _cog(atoms: Sequence[Atom]) -> Tuple[float, float, float]:
    n = len(atoms)
    return (sum(a.xyz[0] for a in atoms) / n, sum(a.xyz[1] for a in atoms) / n,
            sum(a.xyz[2] for a in atoms) / n)


def plan(atoms: Sequence[Atom], catalytic: Sequence[Tuple[int, str]]) -> Plan:
    """Sites, pairwise distances with crystal values, and the pocket.

    `catalytic` is (residue number, three-letter name) in the numbering of
    `atoms`, which is the numbering pdb2gmx keeps.
    """
    by_res: Dict[int, List[Atom]] = {}
    for a in atoms:
        by_res.setdefault(a.resnr, []).append(a)
    sites: List[Site] = []
    notes: List[str] = []
    centres: Dict[int, Optional[Tuple[float, float, float]]] = {}
    for resnr, name in catalytic:
        present = by_res.get(resnr, [])
        if not present:
            notes.append(f"{name.title()}{resnr} is not in the simulated structure; left out")
            continue
        resname = present[0].resname
        want = FUNCTIONAL_ATOMS.get(resname)
        got = [a for a in present if want and a.name in want]
        if want and got and len(got) == len(want):
            sites.append(Site(resnr, resname, want, True))
            centres[resnr] = _cog(got)
        else:
            ca = [a for a in present if a.name == "CA"]
            if not ca:
                notes.append(f"{resname.title()}{resnr} has neither its functional atoms nor CA; left out")
                continue
            sites.append(Site(resnr, resname, ("CA",), False))
            centres[resnr] = _cog(ca)
            notes.append(f"{resname.title()}{resnr}: "
                         + ("no functional atoms defined for this residue type"
                            if not want else "functional atoms missing from the structure")
                         + "; its CA is used, which tracks the backbone, not the chemistry")
    pairs = []
    for a, b in itertools.combinations(sites, 2):
        ca, cb = centres.get(a.resnr), centres.get(b.resnr)
        d = math.dist(ca, cb) / 10.0 if ca and cb else None  # A -> nm
        pairs.append(Pair(a, b, d))
    cat_atoms = [x for s in sites for x in by_res[s.resnr]]
    pocket = sorted({r for r, rs in by_res.items()
                     if any(math.dist(x.xyz, y.xyz) <= POCKET_RADIUS for x in rs for y in cat_atoms)})
    rest = sorted(set(by_res) - set(pocket))
    return Plan(sites, pairs, pocket, rest, notes)


__all__ = ["Atom", "Site", "Pair", "Plan", "plan", "read_pdb", "FUNCTIONAL_ATOMS", "POCKET_RADIUS"]
