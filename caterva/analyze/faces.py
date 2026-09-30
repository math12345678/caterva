"""Which face of a catalytic group its partners are on: what the angle cannot see.

The angle a-v-b between catalytic groups (caterva/analyze/angles.py) is
unchanged when a turns about the line through v and b, so it cannot tell
which side of the vertex a partner is on; nor can the distances, which fix
the triangle a-v-b and nothing off it. Telling the two faces apart needs a
fourth point off that line, and it has to belong to the vertex, or the
question becomes where a is relative to some other group. The vertex
residue's own CA is used: with the functional-group centre it fixes the
side chain's axis, and it is where the side chain meets the backbone. A
partner that goes to the vertex's other face, or a vertex whose side chain
turns over under its partners, changes which side of the plane of a-v-b
that CA is on. That is the quantity: the handedness of the four points a,
v, b and CA.

Three ways of measuring it were weighed. All three tell the faces apart in
exactly the same frames, because the sign of each is the orientation of the
same four points (the sign of the determinant of three of their
differences, which a relabelling of the points changes only by its parity,
so two of the three always agree in sign or always disagree):

- the dihedral a-v-b-CA, which turns a about the line v-b, measured from
  the half-plane that holds CA: exactly the motion the angle cannot see;
- the dihedral a-CA-v-b about the side chain's own CA-to-centre axis,
  which is how far apart a and b are seen from along the side chain;
- the signed volume of the three arms from v (to a, to b and to CA).

What differs is where each stops meaning anything. The dihedral a-v-b-CA
has no value when CA lies on the line through v and b, and that happens:
in replica 1 of a 10 ps hen lysozyme run (fixtures/md/README.md) Asp48 sits
almost straight out along Asn59's side chain, the angle CA-Asn59-Asp48
reaching 179.3 degrees, and over those 21 frames the dihedral
Asn46-Asn59-Asp48-CA runs from -168.9 through -64.9 to +132.4 degrees,
while Asn59's CA never stands more than 11.3 degrees out of the plane of
Asn46-Asn59-Asp48. A dead band on that dihedral would call the -64.9 frame
firmly on one face and the +132.4 frame firmly on the other. The
ill-conditioning shows in the tools as well: on the three dihedrals about
the line Asn59-Asp48, gmx gangle's single-precision value and Caterva's
double-precision one differ by up to 0.0019 degrees, and on the other 45
(each angle's dihedral taken both ways round) by at most 0.0008. The
dihedral about the side-chain axis has no value when either partner is on
that axis, which is where Asp48 was. The signed volume never loses its
value, but it is in nm^3 and grows with the arms, so one threshold on it
means different things at different triples; divided by the three arms'
lengths it is the polar sine, which decides below which frames are on a
face at all, but it is not an angle a reader can picture, and no gmx tool
prints it.

So the face is read as the elevation of the arm from v to its CA out of the
plane of the angle a-v-b: `elevation_deg`, in [-90, 90], signed by the
normal (b - v) x (a - v), which gives it the sign of the dihedral a-v-b-CA.
Positive: seen from CA, a runs clockwise to b about v. It stays small and
well defined when CA comes onto the line v-b (CA is then in the plane of
the angle), and it goes to pieces only when the angle a-v-b is itself
straight, 0 or 180 degrees, which the angle table already shows: on
lysozyme's 24 angles it stayed between 19.9 and 143.8 degrees in every frame
of both replicas. It is what `gmx gangle -g1 plane -g2 vector` measures
(the angle between the plane's normal and the arm, 90 degrees minus the
elevation), and it equals that to 0.001 degree, the precision gangle
prints, on those 24 angles over 21 frames: once as the run stored the frames
and once with the active site across the periodic box
(tests: caterva/tests/test_faces.py).

Which frames are on a face at all. Near flat, the sign is noise: with no
dead band, the faces of the 24 angles changed 81 times between consecutive
frames (0.5 ps apart) over the two replicas' 1008 angle-frames, 79 of them
in series that spend more than half their frames within the band chosen
below: triples that sit flat and flicker. The test is on the polar sine of the
three arms, P = (w x u) . r / (|u| |w| |r|) with u = a - v, w = b - v,
r = CA - v, which equals sin(a-v-b) sin(elevation), is zero exactly when
the four points are flat (including when any two arms line up), and does not
depend on how long the arms are. A frame is on a face when |P| >= sin
FLAT_DEG. Because P is also the sine of the angle between any two of the
arms times the sine of the third's elevation out of their plane, every arm
then stands at least FLAT_DEG out of the plane of the other two.

FLAT_DEG is RESOLVE_DEG, half of MOVED_DEG, derived rather than picked: a
partner counted on the crystal's face in one frame and on the other face in
another has turned through at least 2 x FLAT_DEG = MOVED_DEG across the flat
arrangement, the turn at which the angle table calls an angle moved; and so
has every other arm. At the arm lengths measured on 1AKI (0.24-0.31 nm from
a functional-group centre to its own CA, 0.29-0.58 nm to a partner) 7.5
degrees holds each arm's end 0.03-0.08 nm off the plane of the other two,
so crossing it moves the end 0.06-0.15 nm, about MOVED_NM. On the two
lysozyme replicas this band takes in 246 of the 1008 angle-frames and
leaves 6 changes of face among the rest, every one to or from a lone frame
on the other face (five such frames, none next to another) whose arcsin |P|
is at most 9.4 degrees. A band of 10 degrees would have left none; but that
is on this one short run, and a threshold fitted to one run is not a
threshold.

Every frame is counted, as for the hydrogen bonds, rotamers and water.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from caterva.analyze.angles import RESOLVE_DEG

#: A frame is on a face when every arm stands at least this far out of the
#: plane of the other two (module docstring): half the moved threshold.
FLAT_DEG = RESOLVE_DEG
#: The same, as the bound on |polar sine|.
FLAT = math.sin(math.radians(FLAT_DEG))

#: Thresholds for naming what happened to a face, chosen and printed with the
#: table; the numbers the rotamer and water verdicts use.
KEPT, SPLIT = 0.8, 0.5

#: The verdict of an angle whose four points are flat in the crystal: there
#: is no face to keep or leave.
FLAT_IN_CRYSTAL = "flat in the crystal, no face to keep"


def elevation_deg(pa: np.ndarray, pv: np.ndarray, pb: np.ndarray, pr: np.ndarray,
                  box: Optional[np.ndarray] = None) -> float:
    """The elevation, in degrees, of the arm v->r out of the plane of the
    angle a-v-b, in [-90, 90], positive on the side of (b - v) x (a - v):
    the sign of the dihedral a-v-b-r. With a box, each arm from v is taken
    to its nearest periodic image. By atan2, which keeps its precision near
    +-90 where arcsin of the normalised dot product would not; with a, v
    and b in line the plane has no normal and this is 0, as the polar sine
    is."""
    u, w, r = pa - pv, pb - pv, pr - pv
    if box is not None:
        from caterva.md.xtc import nearest_image
        u, w, r = nearest_image(np.stack([u, w, r]), box)
    n = np.cross(w, u)
    return math.degrees(math.atan2(float(np.dot(n, r)), float(np.linalg.norm(np.cross(n, r)))))


def from_gangle(alpha_deg: float) -> float:
    """The elevation from what `gmx gangle -g1 plane -group1 'A plus V plus
    B' -g2 vector -group2 'V plus R'` prints: the angle between the plane's
    normal, which gangle takes as (V - A) x (B - A) = (B - V) x (A - V), and
    the vector V->R."""
    return 90.0 - alpha_deg


def polar_sine(angle_deg: float, elevation: float) -> float:
    """The polar sine of the three arms from v, from the angle a-v-b and
    the elevation of the third arm out of their plane:
    sin(angle) x sin(elevation), which is (w x u) . r / (|u| |w| |r|)."""
    return math.sin(math.radians(angle_deg)) * math.sin(math.radians(elevation))


def side(p: float) -> int:
    """+1 or -1, the face a frame with polar sine p is on, or 0 when its
    four points are within FLAT_DEG of flat and its sign is noise."""
    if p >= FLAT:
        return 1
    if p <= -FLAT:
        return -1
    return 0


def elevation_series(traj, ia: Sequence[int], iv: Sequence[int], ib: Sequence[int], ir: int) -> List[float]:
    """Per frame, the elevation (degrees) of the arm from the vertex's
    functional-group centre to atom `ir` (its CA) out of the plane of the
    angle between the three groups' centres: `gmx gangle -g1 plane -group1
    'cog of (A) plus cog of (V) plus cog of (B)' -g2 vector -group2 'cog of
    (V) plus cog of (CA)'`, computed by Caterva. Each group is made whole
    before its centre is taken, as angle_series does."""
    from caterva.md import xtc
    out = []
    for f in traj:
        c = [xtc.make_whole(f.x[list(g)], f.box).mean(0) for g in (ia, iv, ib)]
        out.append(elevation_deg(c[0], c[1], c[2], f.x[ir], f.box))
    return out


def face_fractions(name: str, angles: Sequence[float], elevations: Sequence[float],
                   crystal_side: int) -> Tuple[str, float, float]:
    """(replica, fraction of frames on the crystal's face, fraction on the
    other face); the rest are flat. NaN for a replica with no frames."""
    n = len(elevations)
    if not n:
        return name, float("nan"), float("nan")
    sides = [side(polar_sine(t, e)) for t, e in zip(angles, elevations)]
    return (name, sum(1 for s in sides if s and s == crystal_side) / n,
            sum(1 for s in sides if s and s == -crystal_side) / n)


@dataclass
class Face:
    """Which face of the vertex the partners of one angle are on: in the
    crystal, and per replica."""
    label: str
    crystal_elevation_deg: float
    crystal_polar_sine: float
    #: (replica, fraction of frames on the crystal's face, fraction on the other)
    per_replica: List[Tuple[str, float, float]]

    @property
    def crystal_side(self) -> int:
        return side(self.crystal_polar_sine)

    @property
    def crystal_out_of_flat_deg(self) -> float:
        """arcsin of the crystal's polar sine, signed: every arm from the
        vertex stands at least this far out of the plane of the other two.
        The report prints this, so that the number and the FLAT_DEG test on
        it are the same thing."""
        return math.degrees(math.asin(max(-1.0, min(1.0, self.crystal_polar_sine))))

    @property
    def kept(self) -> List[float]:
        return [s for _, s, _ in self.per_replica]

    @property
    def other(self) -> List[float]:
        return [o for _, _, o in self.per_replica]


def face_verdict(f: Face) -> str:
    if f.crystal_side == 0:
        return FLAT_IN_CRYSTAL
    kept, other = f.kept, f.other
    # A replica with no frames has NaN fractions, and every comparison with
    # NaN is False: without this it would fall through to "partial".
    if any(math.isnan(x) for x in kept + other):
        return "no frames"
    if len(kept) < 2:
        return "one replica"
    if max(kept) - min(kept) > SPLIT or max(other) - min(other) > SPLIT:
        return "replicas disagree"
    if min(kept) >= KEPT:
        return "kept its face"
    if min(other) >= KEPT:
        return "changed face"
    if min(1.0 - k - o for k, o in zip(kept, other)) >= KEPT:
        return "went flat"
    return "partial"


def face_name(s: int) -> str:
    """How a face reads in the report: which way a runs to b about v, seen
    from the vertex's CA."""
    return {1: "clockwise", -1: "anticlockwise"}.get(s, "flat")


__all__ = ["FLAT_DEG", "FLAT", "KEPT", "SPLIT", "FLAT_IN_CRYSTAL", "Face", "elevation_deg",
           "elevation_series", "face_fractions", "face_name", "face_verdict", "from_gangle", "polar_sine", "side"]
