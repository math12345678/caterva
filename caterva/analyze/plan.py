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
with itself. Where two groups are both in contact with a third
(CONTACT_NM), the angle between them at the third is planned the same way,
with its crystal value.

Nothing here runs GROMACS. It reads a PDB file and returns selections.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
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

#: Two catalytic groups are in contact, and an angle with its vertex at one
#: of them is measured, when their functional-group centres are at most this
#: far apart in the starting structure. Derived, not picked: a hydrogen bond
#: or salt bridge between the groups puts two of their atoms at most 0.35 nm
#: apart (gmx hbond's donor-acceptor limit, the one caterva/analyze/hbonds.py
#: uses), and in a two-atom group (carboxylate, amide, imidazole nitrogens)
#: each atom sits about 0.11 nm from the group's centre: 0.104-0.116 nm over
#: every Asp, Glu, Asn, Gln and His of hen lysozyme (1AKI). 0.35 + 2 x 0.12
#: is 0.59, which this rounds up. An arginine's three nitrogens sit further
#: out (0.127-0.137 nm over 1AKI's eleven), and an arginine-carboxylate salt
#: bridge at 0.35 nm is still at most 0.35 + 0.137 + 0.111 = 0.598 nm
#: between centres.
CONTACT_NM = 0.6


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


@dataclass(frozen=True)
class Angle:
    """The angle a-v-b between three catalytic groups, at the vertex v."""
    a: Site
    v: Site
    b: Site
    crystal_deg: float

    @property
    def label(self) -> str:
        return f"{self.a.label}–{self.v.label}–{self.b.label}"

    def selection(self) -> str:
        """Three positions, vertex in the middle: what `gmx gangle -g1 angle`
        reads as one angle."""
        return f"{self.a.selection()} plus {self.v.selection()} plus {self.b.selection()}"


@dataclass
class Plan:
    sites: List[Site]
    pairs: List[Pair]
    pocket: List[int]  # residue numbers
    rest: List[int]
    notes: List[str]
    angles: List[Angle] = field(default_factory=list)


def _cog(atoms: Sequence[Atom]) -> Tuple[float, float, float]:
    n = len(atoms)
    return (sum(a.xyz[0] for a in atoms) / n, sum(a.xyz[1] for a in atoms) / n,
            sum(a.xyz[2] for a in atoms) / n)


def _angle_deg(pa: Sequence[float], pv: Sequence[float], pb: Sequence[float]) -> float:
    """a-v-b at v, in degrees, by atan2 as caterva/analyze/angles.py does
    for the frames; the crystal has no periodic box to take images in."""
    u = [pa[k] - pv[k] for k in range(3)]
    w = [pb[k] - pv[k] for k in range(3)]
    cross = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
    return math.degrees(math.atan2(math.sqrt(sum(c * c for c in cross)), sum(u[k] * w[k] for k in range(3))))


def contact_angles(sites: Sequence[Site], centres: Dict[int, Tuple[float, float, float]]) -> List[Angle]:
    """Every angle a-v-b whose arms v-a and v-b are both within CONTACT_NM
    in the starting structure, vertex by vertex in the order of `sites`.
    Only sites with their functional atoms take part: a CA stand-in tracks
    the backbone, and the contact the cutoff is derived from is between side
    chains' functional groups."""
    functional = [s for s in sites if s.functional and s.resnr in centres]
    out: List[Angle] = []
    for v in functional:
        near = [s for s in functional if s is not v
                and math.dist(centres[s.resnr], centres[v.resnr]) / 10.0 <= CONTACT_NM]
        for a, b in itertools.combinations(near, 2):
            out.append(Angle(a, v, b, _angle_deg(centres[a.resnr], centres[v.resnr], centres[b.resnr])))
    return out


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
    return Plan(sites, pairs, pocket, rest, notes, contact_angles(sites, centres))


__all__ = ["Atom", "Site", "Pair", "Angle", "Plan", "plan", "read_pdb", "contact_angles", "FUNCTIONAL_ATOMS",
           "POCKET_RADIUS", "CONTACT_NM"]
