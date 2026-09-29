"""Hydrogen bonds between catalytic side chains, measured frame by frame.

The criterion is GROMACS's (`gmx hbond`), so the two can be compared on the
same trajectory: a donor D (N or O carrying a hydrogen H) and an acceptor A
(N or O) are hydrogen-bonded when |D-A| <= 0.35 nm and the angle A-D-H is at
most 30 degrees. Each (D, H, A) triple counts once per frame, in both
directions between the two residues.

Only side-chain atoms take part. Backbone N-H and C=O would make every pair
of residues on one helix "hydrogen-bonded" through the helix itself, which
says nothing about how two catalytic groups hold each other.

Hydrogens are assigned to their heavy atom from the starting structure's
geometry (nearest N or O within 0.12 nm), because Caterva reads coordinates,
not GROMACS's binary topology. In a structure pdb2gmx built, every polar
hydrogen sits about 0.1 nm from its donor and nowhere near another N or O.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np

#: gmx hbond's defaults (-hbr 0.35 nm, -hba 30 degrees).
MAX_DA_NM = 0.35
MAX_ANGLE_DEG = 30.0
#: A hydrogen belongs to the nearest N or O within this distance.
BOND_NM = 0.12
BACKBONE = {"N", "H", "H1", "H2", "H3", "CA", "HA", "HA1", "HA2", "HA3", "C", "O", "OC1", "OC2", "OXT"}


def element(name: str) -> str:
    """The element of a GROMACS atom name: its first letter (N, O, H, C, S).
    Two-letter elements do not occur in protein side chains."""
    letters = [c for c in name if c.isalpha()]
    return letters[0].upper() if letters else "?"


@dataclass
class Group:
    """One residue's side-chain polar atoms: donors with their hydrogens,
    and acceptors, as 0-based indices into the system."""
    resnr: int
    resname: str
    donors: List[Tuple[int, List[int]]] = field(default_factory=list)
    acceptors: List[int] = field(default_factory=list)


def side_chain_group(atoms: Sequence[Tuple[int, str, str, np.ndarray]], resnr: int) -> Group:
    """atoms: (resnr, resname, name, xyz) for the whole system, in order."""
    mine = [(i, a) for i, a in enumerate(atoms) if a[0] == resnr and a[2] not in BACKBONE]
    if not mine:
        raise ValueError(f"residue {resnr} has no side-chain atoms")
    polar = [(i, a) for i, a in mine if element(a[2]) in ("N", "O")]
    hyd = [(i, a) for i, a in mine if element(a[2]) == "H"]
    g = Group(resnr, mine[0][1][1])
    owner: Dict[int, List[int]] = {i: [] for i, _ in polar}
    for hi, h in hyd:
        best, dist = None, BOND_NM
        for pi, p in polar:
            d = float(np.linalg.norm(h[3] - p[3]))
            if d <= dist:
                best, dist = pi, d
        if best is not None:
            owner[best].append(hi)
    for pi, _ in polar:
        g.acceptors.append(pi)
        if owner[pi]:
            g.donors.append((pi, owner[pi]))
    return g


def _nearest(d: np.ndarray, box: np.ndarray) -> np.ndarray:
    from caterva.md.xtc import nearest_image
    return nearest_image(d, box)


def count_frame(x: np.ndarray, box: np.ndarray, a: Group, b: Group) -> int:
    """Hydrogen bonds between two groups in one frame, both directions."""
    n = 0
    cos_max = math.cos(math.radians(MAX_ANGLE_DEG))
    for don, acc in ((a, b), (b, a)):
        for d, hs in don.donors:
            for ac in acc.acceptors:
                da = _nearest((x[ac] - x[d])[None, :], box)[0]
                r = float(np.linalg.norm(da))
                if r > MAX_DA_NM or r == 0.0:
                    continue
                for h in hs:
                    dh = _nearest((x[h] - x[d])[None, :], box)[0]
                    c = float(np.dot(da, dh) / (r * np.linalg.norm(dh)))
                    if c >= cos_max:
                        n += 1
    return n


@dataclass
class Occupancy:
    """How often two residues were hydrogen-bonded, per replica."""
    label: str
    per_replica: List[Tuple[str, float, float]]  # (replica, fraction of frames bonded, mean bonds per frame)
    at_start: int                                # bonds in the starting structure

    @property
    def fractions(self) -> List[float]:
        return [f for _, f, _ in self.per_replica]


def occupancy(traj, a: Group, b: Group) -> Tuple[float, float, List[int]]:
    """(fraction of frames with >= 1 bond, mean bonds per frame, per-frame counts)."""
    counts = [count_frame(f.x, f.box, a, b) for f in traj]
    if not counts:
        return 0.0, 0.0, []
    return sum(1 for c in counts if c) / len(counts), sum(counts) / len(counts), counts


__all__ = ["Group", "Occupancy", "side_chain_group", "count_frame", "occupancy", "element",
           "MAX_DA_NM", "MAX_ANGLE_DEG", "BACKBONE"]
