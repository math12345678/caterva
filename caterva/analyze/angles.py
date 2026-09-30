"""Angles between catalytic groups: a-v-b at a vertex group v, frame by frame.

A distance between two catalytic groups says how far apart they are, not
from which side one meets the other. When two groups both act on a third
(a general base and an acid both holding the same carboxylate, the relay of
a catalytic triad), the chemistry needs them on particular sides of it, and
both distances to the vertex can hold while one group swings around it to
the other face. The angle a-v-b at the vertex sees that; the distances in
the report cannot.

Each group is reduced to its functional-group centre of geometry, the same
centre the pair distances use (caterva/analyze/plan.py), and the angle is
taken between the two vectors from the vertex centre, each to its nearest
periodic image. The angle is atan2(|u x w|, u . w), which stays exact near 0
and 180 degrees where arccos of the dot product loses precision; GROMACS's
own gmx_angle() (gromacs/utility/vec.h in the 2026.1 headers) is the same
formula, and its comment gives the same reason. Checked against `gmx gangle
-g1 angle` on
24 angles between six catalytic groups of hen lysozyme over 21 frames, to
the 0.001 degree that tool prints.

Which triples: only those whose two arms are both in contact in the
starting structure (CONTACT_NM, in caterva/analyze/plan.py). An angle
between groups that never touch the vertex is a fact about the fold, not
about the active site, and without the cutoff the number of angles grows as
the cube of the number of catalytic residues (six give 60; lysozyme keeps
24 under the cutoff).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from caterva.md.convergence import Summary

#: A consistent mean this far from the crystal angle is reported as the
#: geometry having changed. Derived from the distance threshold (MOVED_NM,
#: 0.1 nm) rather than picked separately: a group 0.4 nm from the vertex
#: that turns by 15 degrees moves 2 x 0.4 x sin(7.5 deg) = 0.104 nm. 0.4 nm
#: is a typical arm: the arms of lysozyme's 24 angles run from 0.29 to 0.58
#: nm in the crystal. A choice, stated as one and printed with the table.
MOVED_DEG = 15.0

#: The precision an angle needs before "held" or "moved" can be decided:
#: half the moved threshold, as RESOLVE_NM is for distances.
RESOLVE_DEG = MOVED_DEG / 2


def angle_deg(pa: np.ndarray, pv: np.ndarray, pb: np.ndarray, box: Optional[np.ndarray] = None) -> float:
    """The angle a-v-b in degrees, [0, 180], at v. With a box, each arm is
    taken to its nearest periodic image, so groups on opposite sides of a
    boundary still read correctly."""
    u, w = pa - pv, pb - pv
    if box is not None:
        from caterva.md.xtc import nearest_image
        u, w = nearest_image(np.stack([u, w]), box)
    return math.degrees(math.atan2(float(np.linalg.norm(np.cross(u, w))), float(np.dot(u, w))))


def angle_series(traj, ia: Sequence[int], iv: Sequence[int], ib: Sequence[int]) -> List[float]:
    """Per frame, the angle (degrees) between the functional-group centres
    of three atom groups, vertex in the middle: `gmx gangle -g1 angle
    -group1 'cog of (A) plus cog of (V) plus cog of (B)'`, computed by
    Caterva. Each group is made whole before its centre is taken, as
    `distance_series` does, so a carboxylate split across the boundary has
    its centre between its two oxygens and not in the middle of the box."""
    from caterva.md import xtc
    out = []
    for f in traj:
        c = [xtc.make_whole(f.x[list(g)], f.box).mean(0) for g in (ia, iv, ib)]
        out.append(angle_deg(c[0], c[1], c[2], f.box))
    return out


@dataclass
class AngleResult:
    """One angle between catalytic groups: in the crystal, and across replicas."""
    label: str
    crystal_deg: float
    summary: Summary

    @property
    def change_deg(self) -> float:
        return self.summary.mean - self.crystal_deg

    @property
    def moved(self) -> bool:
        return abs(self.change_deg) > MOVED_DEG


__all__ = ["MOVED_DEG", "RESOLVE_DEG", "AngleResult", "angle_deg", "angle_series"]
