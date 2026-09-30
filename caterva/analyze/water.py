"""Water at the catalytic residues, counted frame by frame.

Whether water reaches a catalytic group is part of the mechanism: a
hydrolase needs one at its nucleophile, a group that should stay dry
(an aspartate whose pKa the protein shifts) changes its chemistry when
water gets in. Nothing else in `caterva analyze` can see it: the distances,
angles and rotamers are all between protein atoms.

For each catalytic residue, per frame, the number of water oxygens within
WATER_NM of any of its functional atoms (Site.atoms: the same atoms the
distances and angles reduce to a centre, here used one by one, because a
water at either oxygen of a carboxylate is at the carboxylate). Distances
are to the nearest periodic image. Reported per replica as the mean count
and the fraction of frames with at least one water, beside the count in
the starting structure (em.gro, the minimised, solvated system: the
crystal's own waters are not in it, because run.sh drops every HETATM
record before pdb2gmx, and gmx solvate fills the box afresh).

Water is recognised as `caterva md` writes it: residue SOL, oxygen OW
(pdb2gmx -water tip3p, then gmx solvate; checked in the em.gro of a real
lysozyme run). Ions (NA, CL) are not water and are not counted.

Checked against `gmx select -select 'resname SOL and name OW and within
0.35 of (resnr N and name ...)' -os`, frame by frame, on a real lysozyme
trajectory with its active-site water (fixtures/md/README.md): every count
equal, for six catalytic residues over 21 frames.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np

#: A water oxygen this close to a functional atom is counted at the residue.
#: A choice with two reasons behind it. It is gmx hbond's donor-acceptor
#: limit (the one caterva/analyze/hbonds.py uses), so a counted water is one
#: close enough to hydrogen-bond to the group. And it is where the first
#: hydration shell ends: on replica 1 of a 10 ps lysozyme run (TIP3P, `gmx
#: rdf` of OW about OW, 0.002 nm bins, 2026-09-29) the water O-O g(r) peaks
#: at 0.278 nm (2.83), and from 0.34 nm out to 1.0 nm it stays between 0.985
#: and 1.077. TIP3P has almost no structure beyond that first shell, so
#: there is no sharper minimum to take instead.
WATER_NM = 0.35

#: How `caterva md` names water: pdb2gmx and gmx solvate write SOL, OW.
WATER_RESNAME = "SOL"
WATER_OXYGEN = "OW"


def water_oxygens(atoms: Sequence[Tuple[int, str, str, np.ndarray]]) -> List[int]:
    """0-based indices of every water oxygen. `atoms` is (resnr, resname,
    name, xyz) for the whole system, in order."""
    return [i for i, a in enumerate(atoms) if a[1] == WATER_RESNAME and a[2] == WATER_OXYGEN]


def count_frame(x: np.ndarray, box: np.ndarray, site: Sequence[int], oxygens: np.ndarray) -> int:
    """Water oxygens within WATER_NM of any atom of `site`, in one frame,
    each distance to its nearest periodic image. An oxygen near two atoms of
    the site counts once, as it does in `gmx select`'s `within`."""
    from caterva.md.xtc import nearest_image
    ox = x[oxygens]
    near = np.zeros(len(oxygens), dtype=bool)
    for i in site:
        d = nearest_image(ox - x[i], box)
        near |= (d * d).sum(-1) <= WATER_NM * WATER_NM
    return int(near.sum())


def counts(traj, site: Sequence[int], oxygens: Sequence[int]) -> List[int]:
    ox = np.asarray(list(oxygens), dtype=int)
    return [count_frame(f.x, f.box, site, ox) for f in traj]


def selection(resnr: int, names: Sequence[str]) -> str:
    """The same count as a `gmx select` selection; -os prints its size per frame."""
    return (f"resname {WATER_RESNAME} and name {WATER_OXYGEN} and within {WATER_NM:g} of "
            f"(resnr {resnr} and name {' '.join(names)})")


@dataclass
class Hydration:
    """Water at one catalytic residue: at the start and per replica."""
    label: str
    at_start: int
    #: (replica, mean water oxygens per frame, fraction of frames with at least one)
    per_replica: List[Tuple[str, float, float]]

    @property
    def fractions(self) -> List[float]:
        return [f for _, _, f in self.per_replica]


def summarise_counts(name: str, series: Sequence[int]) -> Tuple[str, float, float]:
    """(replica, mean count, fraction of frames with at least one water)."""
    n = len(series)
    if not n:
        return name, float("nan"), float("nan")
    return name, sum(series) / n, sum(1 for c in series if c) / n


#: Thresholds for naming what the water did, chosen, and printed with the
#: table; the same numbers the hydrogen-bond and rotamer verdicts use.
WET, DRY, SPLIT = 0.8, 0.2, 0.5


def hydration_verdict(h: Hydration) -> str:
    fr = h.fractions
    if len(fr) < 2:
        return "one replica"
    if max(fr) - min(fr) > SPLIT:
        return "replicas disagree"
    if min(fr) >= WET:
        return "hydrated"
    if max(fr) <= DRY:
        return "dry"
    return "intermittent"


__all__ = ["WATER_NM", "WATER_RESNAME", "WATER_OXYGEN", "Hydration", "water_oxygens", "count_frame",
           "counts", "selection", "summarise_counts", "hydration_verdict", "WET", "DRY", "SPLIT"]
