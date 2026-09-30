"""Solvent exposure of the catalytic residues: their solvent-accessible surface area.

Whether an active site opens to solvent or closes over its catalytic groups
is part of the mechanism, and nothing else in `caterva analyze` measures
it. The water table (caterva/analyze/water.py) counts water oxygens near a
residue's functional atoms, which says whether a water is there, not how
much of the residue water could reach; the distances, angles and rotamers
are all between protein atoms. This is the area.

WHAT IS MEASURED. The solvent-accessible surface of Lee & Richards (1971)
J. Mol. Biol. 55:379, doi:10.1016/0022-2836(71)90324-X: the surface traced
by the centre of a probe sphere rolled over the atoms' van der Waals
spheres, measured as Shrake & Rupley (1973) J. Mol. Biol. 79:351,
doi:10.1016/0022-2836(73)90011-9 measured it on lysozyme. Every atom's
sphere, grown by the probe radius, carries a fixed set of points; a point
inside any other atom's grown sphere is buried; the atom's area is its
grown sphere's area times the fraction of its points left. A residue's area
is the sum over its atoms, in nm^2.

- Probe 0.14 nm, a water molecule, as in Lee & Richards and `gmx sasa`'s
  default.
- Radii (RADII_NM) exactly as GROMACS's share/top/vdwradii.dat lists them
  (read from GROMACS 2026.1, 2026-09-30), which cites A. Bondi (1964) J.
  Phys. Chem. 68:441, doi:10.1021/j100785a001: H 0.12, C 0.17, N 0.155,
  O 0.152, S 0.18 nm and so on, each atom by the start of its name, as
  `gmx sasa` assigns them. Bondi's paper itself was not checked; the
  numbers are the file's, and the GROMACS route reads the same file.
- Hydrogens are atoms of the surface: `caterva md` runs an all-atom force
  field, and `gmx sasa` counts them too.

WHAT THE SURFACE IS. The whole protein, in every frame: a catalytic
residue's exposure is set by its neighbours, so its area cannot be taken
from it alone. Water and the ions `caterva md` adds (SOLVENT) are not part
of it. No ligand is either: `caterva md` strips every ligand before
pdb2gmx (MD roadmap M4), so there is none in the system to decide about;
when ligands are simulated, whether a bound ligand counts as covering the
site has to be decided with them. The protein is made whole in each frame
(caterva/md/xtc.py make_whole) and its periodic images are not considered:
an image touching the protein is an artefact of the box, not the enzyme's
structure, and `caterva md`'s box leaves at least 2 nm between images at
the start. The GROMACS route asks `gmx sasa` for the same (-nopbc; it
makes molecules whole from the tpr itself).

THE POINTS. `sphere(n)`: the golden-section spiral, deterministic and
equal-area. DOTS = 2000, chosen by convergence on lysozyme's minimised,
solvated structure from a real `caterva md` run (em.gro, 1,960 protein
atoms, 129 residues) and five frames of each of its two replicas: against
the same areas with 20,000 points, 2,000 put every residue's area within
0.011 nm^2 in every one of those 11 structures (root mean square 0.0024
nm^2), where 1,000 left it within 0.019 and 4,000 within 0.006. The report
prints areas to 0.01 nm^2, which 2,000 points hold. On em.gro alone,
against 50,000 points, every atom's area was within 0.0036 nm^2 at 2,000
and 0.0066 at 1,000. caterva/tests/test_sasa.py checks this convergence
on the committed T4 lysozyme structure.

HOW IT IS FAST ENOUGH. Shrake & Rupley's whole cost is testing every point
of every atom against every neighbour whose grown sphere overlaps it.
Neighbours are found on a cell grid (`neighbour_pairs`), and the points are
grouped into patches, so that most are decided a patch at a time
(`atom_areas`). The areas equal those of testing every point, exactly: the
tests hold them to it on T4 lysozyme's 2,603 atoms at 777 and 2,000
points. On lysozyme's em.gro (1,960 atoms) a frame took 0.38 s at 2,000
points, where testing every point took 1.0 s (0.32 and 0.50 s at 1,000),
each the fastest of five runs on a machine under heavy load; finding the
patches buried whole in one pass rather than two then took T4 lysozyme
from 0.6 s to 0.42 s a frame. The trajectory reader
(caterva/md/xtc.py) took 0.13 s a frame for the whole solvated lysozyme
system (23,873 atoms), so the areas are now the largest cost of the native
route, about three times the reading.

CHECKED AGAINST `gmx sasa` (GROMACS 2026.1), which uses a different set of
points, the double cubic lattice method of Eisenhaber et al. (1995) J.
Comput. Chem. 16:273, doi:10.1002/jcc.540160303. The two converge on the
same areas: on lysozyme's em.gro, gmx sasa at -ndots 10000 was within
0.0035 nm^2 of Caterva at 50,000 points on every residue, and its total
of 66.355 nm^2 against 66.360. At 2,000 points each (the GROMACS route
asks for -ndots DOTS), over the 11 structures above, the two routes'
residue areas differed by at most 0.0145 nm^2 (root mean square 0.0033),
which is the two point sets' error added. The committed checks are in
caterva/tests/test_sasa.py: an isolated atom, two overlapping atoms
against the spherical caps worked out by hand, and the per-residue areas
`gmx sasa` printed for a committed structure (every residue of T4
lysozyme) and a committed trajectory (lysozyme's catalytic residues, frame
by frame).

WHAT IS REPORTED, per catalytic residue: the area in em.gro, the
minimised, solvated structure every replica began from (not the crystal's
protein.pdb, which has no hydrogens: set against an all-atom surface, a
change would be only the hydrogens); and per replica the mean and standard
deviation (n - 1) across frames, and the range the middle 95% of frames
fall in (2.5th to 97.5th percentile, interpolated). Every frame is
counted, as for the water: nothing is discarded as relaxation.

RELATIVE AREA. An area alone does not say buried or exposed: a fully
exposed glycine has less surface than a buried tryptophan. So each area is
also given as a fraction of the largest area the residue type can have,
from Tien et al. (2013) PLoS ONE 8:e80635, doi:10.1371/journal.pone.0080635,
Table 1, the theoretical values for the ALLOWED Ramachandran region, which
they recommend (read from the full text in PMC, PMC3836772, 2026-09-30).
Those maxima are DSSP's areas: heavy atoms only, DSSP's own radii, the
residue between two glycines. These areas are all-atom with Bondi's radii,
so the fraction is a guide to how exposed a residue is for its size, not a
value on Tien's scale. It is not wildly off it: on lysozyme's em.gro no
residue's all-atom area exceeds Tien's maximum for its type (the largest
fraction is 0.96, Thr47; median 0.23 over the 127 residues that are not
chain ends), and on the committed T4 lysozyme structure none does either
(largest 0.82, median 0.24, 160 residues). Tien et al. give no maxima for
chain ends, so a catalytic residue at either end of the chain has no
fraction and no verdict.

VERDICTS. With the fraction f: buried below BURIED (0.20), exposed at
EXPOSED (0.40) or above, partly exposed in between. The start is judged by
its area and each replica by its mean, each as the table prints it (to a
whole per cent), so that a verdict can be checked against the numbers
beside it. Two thresholds rather than one, so that a residue near a single
boundary is not called buried in one replica and exposed in the next by a
few hundredths. Both are choices, printed with the table.
"""
from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from typing import Collection, Dict, List, Optional, Sequence, Tuple

import numpy as np

#: The solvent probe's radius: a water molecule, as in Lee & Richards (1971)
#: and `gmx sasa`'s default.
PROBE_NM = 0.14

#: Van der Waals radii (nm) by the start of the atom name, exactly as
#: GROMACS 2026.1's share/top/vdwradii.dat lists them for any residue
#: ("???"); that file cites A. Bondi (1964) J. Phys. Chem. 68:441,
#: doi:10.1021/j100785a001. In the file's order, which breaks a tie.
RADII_NM: Tuple[Tuple[str, float], ...] = (
    ("H", 0.12), ("C", 0.17), ("N", 0.155), ("O", 0.152), ("F", 0.147), ("P", 0.18), ("S", 0.18),
    ("Cl", 0.175),
)

#: Points per atom (module docstring: THE POINTS). The GROMACS route asks
#: `gmx sasa` for as many (-ndots), so the two carry about the same
#: discretisation error.
DOTS = 2000

#: Patches the points are grouped into (`atom_areas`). Any number gives the
#: same areas; 64 was the fastest on lysozyme.
PATCHES = 64

#: The largest difference expected between the two routes' areas (nm^2) of
#: one residue in one frame, from their different point sets at DOTS points
#: each (module docstring, CHECKED AGAINST): at most 0.0145 over the 1,419
#: residue-frames of a lysozyme run, 0.0096 over the 126 catalytic
#: residue-frames of the committed lysozyme frames, and 0.0076 over the 66
#: of a later smoke run (both replicas and em.gro), rounded up. The smoke
#: run (scripts/md_smoke.py) and caterva/tests/test_sasa.py hold the routes
#: to it. A mean over frames, and a percentile of them, can differ by no
#: more than the largest single frame does.
ROUTES_AGREE_NM2 = 0.02

#: Residues `caterva md` adds around the protein: water (pdb2gmx and gmx
#: solvate name it SOL) and genion's ions (-pname NA -nname CL). Everything
#: else in its system is the protein, which is the surface.
SOLVENT = ("SOL", "NA", "CL")

#: The same surface as a `gmx sasa -surface` selection: the default index
#: group GROMACS builds from residue names. It holds exactly the atoms the
#: native route takes (1,960 on lysozyme's em.gro), and CI compares the two
#: routes' areas on every run.
SURFACE_GROUP = "Protein"


def radius(name: str) -> float:
    """The radius of an atom by its name: the RADII_NM entry that is the
    longest prefix of it, the first such entry on a tie. vdwradii.dat is
    read that way ("longest matches are used"), and every atom name
    pdb2gmx writes for a protein starts with its element (CA, HB1, OD2,
    SG). A name no entry starts is refused rather than given a guess."""
    best, length = None, 0
    for prefix, r in RADII_NM:
        if name.startswith(prefix) and len(prefix) > length:
            best, length = r, len(prefix)
    if best is None:
        raise ValueError(f"no van der Waals radius for an atom named {name!r} (vdwradii.dat has "
                         f"{', '.join(p for p, _ in RADII_NM)})")
    return best


@functools.lru_cache(maxsize=8)
def sphere(n: int) -> np.ndarray:
    """n points on the unit sphere, the golden-section spiral: point k at
    height z = 1 - (2k + 1)/n, turned by the golden angle from the last.
    Equal steps in z cut the sphere into bands of equal area (Archimedes'
    hat-box theorem), so each point stands for 4 pi / n of it; and the
    spiral has no randomness in it, so a structure always gets the same
    areas."""
    if n < 1:
        raise ValueError(f"a sphere needs at least one point, not {n}")
    k = np.arange(n, dtype=float)
    z = 1.0 - (2.0 * k + 1.0) / n
    rho = np.sqrt(np.clip(1.0 - z * z, 0.0, None))
    phi = k * math.pi * (3.0 - math.sqrt(5.0))
    u = np.column_stack([rho * np.cos(phi), rho * np.sin(phi), z])
    u.flags.writeable = False
    return u


@functools.lru_cache(maxsize=8)
def _patches(n: int, m: int):
    """The n points of `sphere(n)` grouped into m patches, each point to the
    nearest of m centres (`sphere(m)`). Returns the patch of each point, the
    centres, the largest angle from a centre to one of its points, and each
    patch's points as a row padded with the index n, a point that is never
    counted."""
    u, c = sphere(n), sphere(min(m, n))
    with np.errstate(all="ignore"):  # Accelerate's BLAS flags finite products; checked below
        cos = u @ c.T
    if not np.all(np.isfinite(cos)):
        raise FloatingPointError("assigning points to patches produced a non-finite value")
    label = np.argmax(cos, axis=1)
    spread = float(np.arccos(np.clip(cos[np.arange(n), label], -1.0, 1.0)).max())
    size = np.bincount(label, minlength=len(c))
    order = np.argsort(label, kind="stable")
    members = np.full((len(c), int(size.max())), n)
    members[label[order], np.arange(n) - (np.cumsum(size) - size)[label[order]]] = order
    for a in (label, c, members):
        a.flags.writeable = False
    return label, c, spread, members


def neighbour_pairs(x: np.ndarray, reach: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Every ordered pair (i, j), i != j, with |x_j - x_i| < reach_i +
    reach_j, sorted by i and then j: the atoms whose grown spheres overlap.

    A cell grid, so the work grows with the number of atoms rather than its
    square: cells as wide as the largest reach_i + reach_j, so every
    overlapping pair is in one cell or two adjacent ones. Each cell is
    paired with itself and with 13 of its 26 neighbours (the other 13 give
    the same pairs the other way round), and the pairs found are then
    taken both ways."""
    x = np.asarray(x, float)
    reach = np.asarray(reach, float)
    n = len(x)
    none = (np.zeros(0, dtype=int), np.zeros(0, dtype=int))
    if n < 2:
        return none
    width = 2.0 * float(reach.max())
    cell = np.floor((x - x.min(0)) / width).astype(np.int64) + 1  # an empty cell on every side
    dims = cell.max(0) + 2
    key = (cell[:, 0] * dims[1] + cell[:, 1]) * dims[2] + cell[:, 2]
    order = np.argsort(key, kind="stable")
    sorted_key = key[order]
    firsts, seconds = [], []
    offsets = [(0, 0, 0)] + [o for o in ((a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1))
                             if o > (0, 0, 0)]
    for a, b, c in offsets:
        # The empty margin keeps every neighbouring cell inside the grid, so
        # its key is the atom's key plus a constant.
        target = sorted_key + (a * dims[1] + b) * dims[2] + c
        start = np.searchsorted(sorted_key, target, "left")
        count = np.searchsorted(sorted_key, target, "right") - start
        total = int(count.sum())
        if not total:
            continue
        src = np.repeat(np.arange(n), count)
        dst = np.arange(total) - np.repeat(np.cumsum(count) - count, count) + np.repeat(start, count)
        if (a, b, c) == (0, 0, 0):
            src, dst = src[dst > src], dst[dst > src]
        firsts.append(order[src])
        seconds.append(order[dst])
    if not firsts:
        return none
    i, j = np.concatenate(firsts), np.concatenate(seconds)
    d = x[j] - x[i]
    overlap = (d * d).sum(1) < (reach[i] + reach[j]) ** 2
    i, j = np.concatenate([i[overlap], j[overlap]]), np.concatenate([j[overlap], i[overlap]])
    o = np.lexsort((j, i))
    return i[o], j[o]


#: A patch is decided whole only when every point of it is at least this
#: angle (radians) inside or outside a neighbour's cap; nearer the edge its
#: points are tested one by one. Far beyond double precision, so no point
#: is decided differently from testing it alone.
_EDGE = 1e-6

#: Patch-neighbour pairs tested per block, to bound the memory of a block.
_BLOCK = 16384


def atom_areas(x: np.ndarray, radii: np.ndarray, probe: float = PROBE_NM, dots: int = DOTS,
               patches: int = PATCHES) -> np.ndarray:
    """The solvent-accessible area (nm^2) of each atom, by Shrake & Rupley.

    `x` (nm) is one molecule, whole; periodic images are not considered.
    Each atom's sphere of radius r + probe carries `dots` points
    (`sphere`); a point inside any other atom's grown sphere is buried, and
    the atom's area is 4 pi (r + probe)^2 times the fraction of its points
    left.

    Atom j covers the points of atom i within an angle alpha of the
    direction from i to j, a cap: with d = x_j - x_i and R the grown radii,
    point u is inside j when u . d > (R_i^2 + |d|^2 - R_j^2) / (2 R_i).
    Rather than test every point against every overlapping neighbour, the
    points are grouped into patches (`_patches`): a patch whose centre is
    nearer the cap's axis than alpha minus the patch's radius is buried
    whole, one further than alpha plus it is untouched, and only the
    patches the cap's edge crosses are tested point by point, by the same
    test. The areas equal those of testing every point (module docstring),
    and caterva/tests/test_sasa.py holds them to it on a real protein."""
    x = np.asarray(x, float)
    R = np.asarray(radii, float) + probe
    n = len(x)
    if n == 0:
        return np.zeros(0)
    u = sphere(dots)
    label, centres, spread, members = _patches(dots, patches)
    I, J = neighbour_pairs(x, R)
    d = x[J] - x[I]
    dist = np.sqrt((d * d).sum(1))
    t = (R[I] ** 2 + dist ** 2 - R[J] ** 2) / (2.0 * R[I])
    with np.errstate(divide="ignore", invalid="ignore"):
        # Two atoms at one point: j buries all of i when it is the larger,
        # none of it otherwise (u . 0 > t exactly when R_j > R_i).
        cos_cap = np.where(dist > 0, t / dist, np.where(R[J] > R[I], -2.0, 2.0))
        axis = np.where(dist[:, None] > 0, d / np.where(dist > 0, dist, 1.0)[:, None], 0.0)
    covers = cos_cap < 1.0
    I, d, t, cos_cap, axis = I[covers], d[covers], t[covers], cos_cap[covers], axis[covers]
    alpha = np.arccos(np.clip(cos_cap, -1.0, 1.0))
    inner, outer = alpha - spread - _EDGE, alpha + spread + _EDGE
    cos_inner = np.where(inner > 0, np.cos(np.clip(inner, 0.0, math.pi)), 2.0)
    cos_outer = np.where(outer < math.pi, np.cos(np.clip(outer, 0.0, math.pi)), -2.0)
    with np.errstate(all="ignore"):  # Accelerate's BLAS flags finite products; checked below
        cos_patch = axis @ centres.T
    if not np.all(np.isfinite(cos_patch)):
        raise FloatingPointError("a neighbour's direction produced a non-finite value")
    inside = cos_patch > cos_inner[:, None]
    whole = np.zeros((n, len(centres)), dtype=bool)
    if len(I):
        # The pairs are sorted by i, so each atom's rows are one run.
        first = np.flatnonzero(np.r_[True, I[1:] != I[:-1]])
        whole[I[first]] = np.logical_or.reduceat(inside, first, axis=0)
    # A patch the cap's edge crosses is tested point by point, unless another
    # neighbour buries it whole.
    p, m = np.nonzero((cos_patch > cos_outer[:, None]) & ~whole[I])
    buried = np.zeros((n, dots + 1), dtype=bool)
    points = np.vstack([u, np.zeros((1, 3))])  # the padding point, never counted
    for s in range(0, len(p), _BLOCK):
        pp, idx = p[s:s + _BLOCK], members[m[s:s + _BLOCK]]
        with np.errstate(all="ignore"):
            proj = np.einsum("ksc,kc->ks", points[idx], d[pp])
        if not np.all(np.isfinite(proj)):
            raise FloatingPointError("a point's projection produced a non-finite value")
        hit = (proj > t[pp][:, None]) & (idx < dots)
        buried[np.broadcast_to(I[pp][:, None], idx.shape)[hit], idx[hit]] = True
    exposed = dots - (buried[:, :dots] | whole[:, label]).sum(1)
    return 4.0 * math.pi * R * R * exposed / dots


def surface_atoms(atoms: Sequence[Tuple[int, str, str, np.ndarray]],
                  protein: Optional[Collection[int]] = None) -> List[int]:
    """0-based indices of the surface's atoms: every atom that is not water
    or an ion `caterva md` added and, given `protein` (the residue numbers
    of protein.pdb's ATOM records), belongs to one of those residues, so
    that a ligand simulated some day is left out on this route as the
    GROMACS route's Protein group leaves it out. `atoms` is (resnr,
    resname, name, xyz) for the whole system, in order
    (caterva/analyze/__main__.py _gro_atoms)."""
    keep = None if protein is None else set(protein)
    return [i for i, a in enumerate(atoms) if a[1] not in SOLVENT and (keep is None or a[0] in keep)]


def residue_members(atoms: Sequence[Tuple[int, str, str, np.ndarray]], surface: Sequence[int],
                    resnr: int) -> np.ndarray:
    """Positions in `surface` of residue `resnr`'s atoms. Refused when the
    residue is not in it, or when its number appears in two places (two
    chains simulated with the same numbering): an area summed over both
    would be no residue's."""
    where = np.array([k for k, i in enumerate(surface) if atoms[i][0] == resnr], dtype=int)
    if not len(where):
        raise ValueError(f"residue {resnr} has no atoms in the protein")
    if where[-1] - where[0] + 1 != len(where):
        raise ValueError(f"residue number {resnr} appears in more than one place in the protein (more "
                         "than one chain simulated?); its solvent exposure needs one chain: `caterva md "
                         "--chain`")
    return where


class Surface:
    """The protein of one system, ready to measure: its atoms, their radii,
    and which of them belong to each residue asked about."""

    def __init__(self, atoms: Sequence[Tuple[int, str, str, np.ndarray]], residues: Sequence[int],
                 protein: Optional[Collection[int]] = None):
        self.index = np.array(surface_atoms(atoms, protein), dtype=int)
        self.radii = np.array([radius(atoms[i][2]) for i in self.index])
        self.members = [residue_members(atoms, self.index, r) for r in residues]

    def areas(self, x: np.ndarray, box: np.ndarray) -> List[float]:
        """Each residue's area (nm^2) in one frame of the whole system: the
        protein made whole across the periodic box, then measured alone."""
        from caterva.md.xtc import make_whole
        a = atom_areas(make_whole(np.asarray(x)[self.index], box), self.radii)
        return [float(a[m].sum()) for m in self.members]

    def series(self, traj) -> List[List[float]]:
        """Per residue, its area in every frame of a trajectory."""
        per_frame = [self.areas(f.x, f.box) for f in traj]
        return [[row[k] for row in per_frame] for k in range(len(self.members))]


def summarise_areas(name: str, series: Sequence[float]) -> Tuple[str, float, float, float, float]:
    """(replica, mean, standard deviation, 2.5th percentile, 97.5th
    percentile) of one residue's area over a replica's frames. The
    deviation is the sample one (n - 1), NaN with one frame; everything is
    NaN with none."""
    v = np.asarray(list(series), float)
    if not len(v):
        nan = float("nan")
        return name, nan, nan, nan, nan
    sd = float(v.std(ddof=1)) if len(v) > 1 else float("nan")
    low, high = np.percentile(v, [2.5, 97.5])
    return name, float(v.mean()), sd, float(low), float(high)


#: The largest solvent-accessible area (A^2) of each residue type, between
#: two glycines: Tien et al. (2013) PLoS ONE 8:e80635, Table 1, theoretical,
#: ALLOWED region. DSSP's areas (heavy atoms, its own radii); see the
#: module docstring for what that means for a ratio with these areas.
TIEN_MAX_A2: Dict[str, float] = {
    "ALA": 129.0, "ARG": 274.0, "ASN": 195.0, "ASP": 193.0, "CYS": 167.0, "GLN": 225.0, "GLU": 223.0,
    "GLY": 104.0, "HIS": 224.0, "ILE": 197.0, "LEU": 201.0, "LYS": 236.0, "MET": 224.0, "PHE": 240.0,
    "PRO": 159.0, "SER": 155.0, "THR": 172.0, "TRP": 285.0, "TYR": 263.0, "VAL": 174.0,
}
# Protonation and bonding variants the structure may name a residue by.
for _variant, _parent in (("HID", "HIS"), ("HIE", "HIS"), ("HIP", "HIS"), ("HSD", "HIS"), ("HSE", "HIS"),
                          ("HSP", "HIS"), ("CYX", "CYS"), ("ASH", "ASP"), ("GLH", "GLU"), ("LYN", "LYS")):
    TIEN_MAX_A2[_variant] = TIEN_MAX_A2[_parent]

#: Relative area (of TIEN_MAX_A2) below which a residue is called buried,
#: and at or above which exposed; partly exposed in between. Choices.
BURIED, EXPOSED = 0.20, 0.40


@dataclass
class Exposure:
    """The solvent-accessible area of one catalytic residue: at the start
    and per replica."""
    label: str
    resname: str
    at_start: float
    #: (replica, mean, SD, 2.5th percentile, 97.5th percentile), nm^2
    per_replica: List[Tuple[str, float, float, float, float]]
    #: False for the first or last residue of the chain, which Tien et al.
    #: give no maximum for.
    in_chain: bool = True

    @property
    def max_area(self) -> Optional[float]:
        """Tien's maximum for the residue type, nm^2; None for a chain end
        or a type the table does not have."""
        if not self.in_chain or self.resname not in TIEN_MAX_A2:
            return None
        return TIEN_MAX_A2[self.resname] / 100.0

    def relative(self, area: float) -> Optional[float]:
        m = self.max_area
        return None if m is None or math.isnan(area) else area / m

    @property
    def means(self) -> List[float]:
        return [mean for _, mean, _, _, _ in self.per_replica]


def state(fraction: float) -> str:
    """Buried, partly exposed or exposed, by the relative area."""
    if fraction < BURIED:
        return "buried"
    if fraction >= EXPOSED:
        return "exposed"
    return "partly exposed"


#: Verdicts that are not about the residue's exposure, so they are never
#: marked "not yet a result".
CHAIN_END = "chain end, no maximum area to compare with"
NO_FRAMES = "no frames"
ONE_REPLICA = "one replica"


def no_maximum(resname: str) -> str:
    return f"no maximum area for {resname}"


def exposure_verdict(e: Exposure) -> str:
    """The residue's state at the start against its state in each replica:
    "buried throughout", "buried at the start, exposed in every replica",
    or, when the replicas differ, which of them left the starting state
    ("buried at the start, exposed in rep2; replicas disagree")."""
    if not e.in_chain:
        return CHAIN_END
    if e.max_area is None:
        return no_maximum(e.resname)
    if any(math.isnan(m) for m in e.means):
        return NO_FRAMES
    if len(e.per_replica) < 2:
        return ONE_REPLICA
    # Judged on the share as the table prints it (a whole per cent), so a
    # residue shown at 20% is not called buried below 20%.
    start = state(round(e.relative(e.at_start), 2))
    states = [state(round(e.relative(m), 2)) for m in e.means]
    if all(s == start for s in states):
        return f"{start} throughout"
    if len(set(states)) == 1:
        return f"{start} at the start, {states[0]} in every replica"
    moved: Dict[str, List[str]] = {}
    for (name, *_), s in zip(e.per_replica, states):
        if s != start:
            moved.setdefault(s, []).append(name)
    return (f"{start} at the start, " + ", ".join(f"{s} in {' and '.join(names)}" for s, names in moved.items())
            + "; replicas disagree")


def output_selection(resnr: int) -> str:
    """One catalytic residue as a `gmx sasa -output` selection: a subset of
    the surface, as -output requires, even if water numbering ever reached
    the residue's number."""
    return f"group {SURFACE_GROUP} and resnr {resnr}"


def gmx_options() -> str:
    """The `gmx sasa` options that make its surface this module's: the same
    atoms, probe and number of points, no periodic images."""
    return f"-surface {SURFACE_GROUP} -probe {PROBE_NM:g} -ndots {DOTS} -nopbc"


__all__ = ["PROBE_NM", "RADII_NM", "DOTS", "PATCHES", "ROUTES_AGREE_NM2", "SOLVENT", "SURFACE_GROUP", "radius", "sphere",
           "neighbour_pairs", "atom_areas", "surface_atoms", "residue_members", "Surface", "summarise_areas",
           "TIEN_MAX_A2", "BURIED", "EXPOSED", "Exposure", "state", "exposure_verdict", "CHAIN_END",
           "NO_FRAMES", "ONE_REPLICA", "no_maximum", "output_selection", "gmx_options"]
