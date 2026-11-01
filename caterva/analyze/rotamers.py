"""Side-chain rotamers of the catalytic residues: chi1, frame by frame.

A catalytic residue can keep every distance to its partners within a few
tenths of a nanometre and still turn its side chain over: a serine's
hydroxyl pointing away from the substrate is a different active site. The
distances `caterva analyze` reports are measured between functional-group
centres and cannot see that, so the first side-chain dihedral is measured
too, and put in one of the three staggered wells it lives in.

chi1 is the dihedral N-CA-CB-XG, with XG the gamma atom IUPAC names for the
residue (OG for serine, OG1 for threonine, SG for cysteine, CG1 for valine
and isoleucine, CG otherwise). The angle convention is IUPAC's and
GROMACS's: a right-handed rotation about CA-CB, in (-180, 180]. Checked
against `gmx angle -type dihedral` on six catalytic residues of hen
lysozyme over 21 frames, to the 0.001 degree that tool prints.

The wells are named by their angle, +60, 180 and -60, rather than by
gauche+/gauche-/trans, because the literature uses the two gauche names in
both senses. A frame is in the well its chi1 is nearest to: [0, 120) is
+60, [-120, 0) is -60, and the rest is 180.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

#: The gamma atom of chi1, by residue name, where it is not CG. Protonation
#: variants GROMACS names (HID, HIE, HIP, ASH, GLH, LYN, CYX) share their
#: parent's atoms.
GAMMA = {"SER": "OG", "THR": "OG1", "CYS": "SG", "CYX": "SG", "VAL": "CG1", "ILE": "CG1"}
#: No chi1: no side chain beyond CB, or none at all.
NO_CHI1 = {"GLY", "ALA"}

WELLS = ("+60", "180", "-60")


def dihedral(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, p3: np.ndarray,
             box: Optional[np.ndarray] = None) -> float:
    """The dihedral p0-p1-p2-p3 in degrees, (-180, 180]. Bond vectors are
    taken to their nearest periodic image when a box is given, so a side
    chain split across the boundary still reads correctly."""
    b = [p1 - p0, p2 - p1, p3 - p2]
    if box is not None:
        from caterva.md.xtc import nearest_image
        b = [nearest_image(v[None, :], box)[0] for v in b]
    b0, b1, b2 = b
    n1, n2 = np.cross(b0, b1), np.cross(b1, b2)
    m1 = np.cross(n1, b1 / np.linalg.norm(b1))
    x, y = float(np.dot(n1, n2)), float(np.dot(m1, n2))
    angle = -math.degrees(math.atan2(y, x))
    return 180.0 if angle == -180.0 else angle


def well(chi: float) -> str:
    if 0.0 <= chi < 120.0:
        return "+60"
    if -120.0 <= chi < 0.0:
        return "-60"
    return "180"


def chi1_atoms(atoms: Sequence[Tuple[int, str, str, np.ndarray]], resnr: int) -> Optional[Tuple[int, int, int, int]]:
    """0-based indices of N, CA, CB and the gamma atom of residue `resnr`, or
    None when it has no chi1 (glycine, alanine) or the atoms are missing.
    `atoms` is (resnr, resname, name, xyz) for the whole system, in order."""
    mine = {a[2]: i for i, a in enumerate(atoms) if a[0] == resnr}
    names = [a[1] for a in atoms if a[0] == resnr]
    if not names or names[0].upper() in NO_CHI1:
        return None
    gamma = GAMMA.get(names[0].upper(), "CG")
    try:
        return mine["N"], mine["CA"], mine["CB"], mine[gamma]
    except KeyError:
        return None


def chi1_series(traj, idx: Tuple[int, int, int, int]) -> List[float]:
    a, b, c, d = idx
    return [dihedral(f.x[a], f.x[b], f.x[c], f.x[d], f.box) for f in traj]


def populations(series: Sequence[float]) -> Dict[str, float]:
    """Fraction of frames in each well."""
    n = len(series)
    if not n:
        return {w: float("nan") for w in WELLS}
    counts = {w: 0 for w in WELLS}
    for chi in series:
        counts[well(chi)] += 1
    return {w: counts[w] / n for w in WELLS}


@dataclass
class Rotamer:
    """chi1 of one catalytic residue: at the start and per replica."""
    label: str
    at_start: float
    #: (replica, fraction of frames per well)
    per_replica: List[Tuple[str, Dict[str, float]]]

    @property
    def start_well(self) -> str:
        return well(self.at_start)

    @property
    def kept(self) -> List[float]:
        """Per replica, the fraction of frames in the starting well."""
        return [p[self.start_well] for _, p in self.per_replica]

    def dominant(self, populations_: Dict[str, float]) -> str:
        return max(WELLS, key=lambda w: populations_[w])


#: Thresholds for naming what happened to a rotamer. Chosen, and printed with
#: the table, the same way the hydrogen-bond verdicts are.
KEPT, FLIPPED, SPLIT = 0.8, 0.2, 0.5


def rotamer_verdict(r: Rotamer) -> str:
    kept = r.kept
    if len(kept) < 2:
        return "one replica"
    if max(kept) - min(kept) > SPLIT:
        return "replicas disagree"
    if min(kept) >= KEPT:
        return "kept"
    if max(kept) <= FLIPPED:
        wells = {r.dominant(p) for _, p in r.per_replica}
        return f"flipped to {wells.pop()}" if len(wells) == 1 else "flipped"
    return "partial"


__all__ = ["GAMMA", "WELLS", "Rotamer", "dihedral", "well", "chi1_atoms", "chi1_series",
           "populations", "rotamer_verdict", "KEPT", "FLIPPED", "SPLIT"]
