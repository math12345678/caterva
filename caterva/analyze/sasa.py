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
equal-area. DOTS = 2000 is a choice between accuracy and time, measured on
eight lysozyme runs of scripts/md_smoke.py (each: em.gro, 1,960 protein
atoms in 129 residues, and five frames of each of two replicas; 88
structures in all; the runs are not committed) against the same areas
with 20,000 points. At 2,000 points the largest error of any residue's
area in one structure was between 0.0098 and 0.0157 nm^2 in the eight
runs (root mean square 0.0023 to 0.0024 in each). On four of them,
1,000 points left it within 0.017 to 0.025, and 4,000 within 0.0061 to
0.0070, for about 1.4 times the time (0.34 s a frame of em.gro against
0.24 s at 2,000, fastest of five, on a machine at load average 34). The table prints areas to 0.01 nm^2,
so the area of a single structure, the one at the start, can be off by
one or two in its last printed digit. A replica's mean is steadier,
because each frame turns the protein against the fixed points: over only
five frames the means were within 0.0052 nm^2 in all eight runs, and a
real run has hundreds of frames or more. caterva/tests/test_sasa.py
checks the convergence on the committed T4 lysozyme structure.

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
same areas: on the committed T4 lysozyme structure, with 10,000 points
each, every residue agreed to 0.0044 nm^2 (root mean square 0.0013), and
on the em.gro of one of the lysozyme runs above, gmx sasa at 10,000 points
was within 0.0035 nm^2 of Caterva at 50,000 on every residue (totals
66.356 and 66.361 nm^2). As the two routes run (2,000 points here, and
-ndots 2000 there, which gmx rounds up to 2,252: GMX_DOTS), they
differ by the two point sets' errors added, and the difference grows
with the surface a residue exposes. Over the eight lysozyme runs above
(all 129 residues in each of the 88 structures, each structure written
out whole and given to both) and T4 lysozyme's 162 residues, 11,514
residue areas in all, the root mean square difference was about 0.0047
sqrt(area) nm^2 (area in nm^2) above 0.1 nm^2; the largest was 0.0205
nm^2, on Arg45 with 1.80 nm^2 exposed, and below 0.1 nm^2 none exceeded
0.0058. A single bound for every residue, set from the catalytic
residues of one run, would not hold: 0.02 nm^2 was exceeded by that
arginine. `routes_agree_nm2` is the bound the routes are held to, set
from these measurements. The lysozyme runs are not committed. The
committed checks, in caterva/tests/test_sasa.py, are an isolated atom;
two overlapping atoms against the spherical caps worked out by hand;
every residue of T4 lysozyme against `gmx sasa` at 10,000 points and at
2,000; and the six catalytic residues of 21 committed lysozyme frames
against the command analyze.sh runs, frame by frame.

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
chain-terminating residues, which lack a peptide bond on one side, so a
catalytic residue that lacks one in em.gro (`Surface.in_chain`: the first
or last residue of the chain, or one beside a break in it) has no fraction
and no verdict.

VERDICTS. With the fraction f: buried below BURIED (0.20), exposed at
EXPOSED (0.40) or above, partly exposed in between. The start is judged by
its area and each replica by its mean, each as the table prints it (to a
whole per cent), so that a verdict can be checked against the numbers
beside it. With one replica there is no verdict, as for the water: the
verdict says whether a change from the start happens again in another
run, which one run cannot say. Two thresholds rather than one, so that
buried and exposed are never a few hundredths apart. That does not keep a
mean near either threshold from falling on either side of it in another
run of the same system, or on the other route: lysozyme's Asn46 was at
19% of its maximum in rep2 of one scripts/md_smoke.py run, and buried by
that, and at 20% in the next. So a replica whose mean crosses a threshold
while its middle 95% of frames still reaches back into the starting state
is reported as such ("buried in rep2 by its mean, with frames still
partly exposed"), not as having left it, and does not make the replicas
disagree (`exposure_verdict`). The start is one structure with no spread,
so a start near a threshold is only as firm as the share printed for it.
Both thresholds are choices, printed with the table.
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

#: Points per atom (module docstring: THE POINTS). The GROMACS route passes
#: the same number to `gmx sasa -ndots`, which rounds it up to the next
#: size of its icosahedral tessellation (10 k^2 + 2 points), so the two
#: carry about the same discretisation error, not the same points.
DOTS = 2000

#: How many points `gmx sasa -ndots DOTS` places per atom: counted in the
#: dots `gmx sasa -q` wrote for one isolated atom (GROMACS 2026.1; 10,242
#: for -ndots 10000). The GROMACS route's section says this number, not
#: DOTS, since that is what its areas were measured with.
GMX_DOTS = 2252

#: Patches the points are grouped into (`atom_areas`). Any number gives the
#: same areas; 64 was the fastest on lysozyme.
PATCHES = 64

#: The two routes' areas of one residue in one frame, at DOTS points each,
#: are held to within ROUTES_AGREE_NM times the square root of the
#: residue's area, and never less than ROUTES_AGREE_FLOOR_NM2
#: (`routes_agree_nm2`). One number for every residue would not do: the
#: difference is the two point sets' errors added, and it grows with the
#: surface a residue exposes (module docstring, CHECKED AGAINST). Over the
#: 11,514 residue areas measured there, no difference came nearer this
#: bound than 0.71 of it (0.0082 nm^2 against 0.0115, Phe3 with 0.15 nm^2
#: exposed), and the largest difference was 0.51 of it (0.0205 against
#: 0.0402, Arg45 with 1.80 nm^2); on T4 lysozyme alone, at most 0.52. The
#: factor and the floor are choices made from those measurements, not
#: limits derived from the two methods, and margins set from a few runs
#: can shrink as runs are added: when they were set, a factor of 0.025
#: from three runs had left a fifth within 0.86 of it at Phe3.
ROUTES_AGREE_NM = 0.03
ROUTES_AGREE_FLOOR_NM2 = 0.0075

#: Residues `caterva md` adds around the protein: water (pdb2gmx and gmx
#: solvate name it SOL) and genion's ions (-pname NA -nname CL). Everything
#: else in its system is the protein, which is the surface.
SOLVENT = ("SOL", "NA", "CL")

#: The same surface as a `gmx sasa -surface` selection: the default index
#: group GROMACS builds from residue names (share/top/residuetypes.dat),
#: where the native route takes protein.pdb's residues less SOLVENT. The two
#: hold the same atoms on lysozyme's em.gro (1,960) and T4 lysozyme's
#: (2,603), the only systems they have been compared on. They could differ:
#: a residue pdb2gmx builds but residuetypes.dat does not call a protein
#: residue would be in the native surface and not in gmx's. CI compares the
#: two routes' areas on lysozyme only.
SURFACE_GROUP = "Protein"

#: A C-N distance (nm) below this is a peptide bond (`Surface.in_chain`):
#: well above the bond's 0.133 nm, and well below the 0.325 nm at which
#: the van der Waals spheres of an unbonded C and N (RADII_NM) touch.
PEPTIDE_BOND_NM = 0.2


def routes_agree_nm2(area: float) -> float:
    """How far apart the two routes' areas (nm^2) of one residue in one
    frame may be, for a residue with this area (nm^2): ROUTES_AGREE_NM
    sqrt(area), at least ROUTES_AGREE_FLOOR_NM2. A mean or a percentile of
    frames differs between the routes by no more than the frames do, and
    this bound changes little over one residue's frames, so the smoke run
    (scripts/md_smoke.py) applies it to those at their own values."""
    return max(ROUTES_AGREE_FLOOR_NM2, ROUTES_AGREE_NM * math.sqrt(max(float(area), 0.0)))


def radius(name: str) -> float:
    """The radius of an atom by its name: the RADII_NM entry that is the
    longest prefix of it, the first such entry on a tie. vdwradii.dat is
    read that way ("longest matches are used"), and every atom name
    pdb2gmx writes for a protein starts with its element (CA, HB1, OD2,
    SG). A name no entry starts is refused rather than given a guess.
    Only the file's element entries ("???" for any residue) are kept: its
    residue-specific entries give radius 0 to virtual-site masses (GLY MN1,
    ALA MCB1) and to the charge sites of 4-site water (SOL MW), which a
    `caterva md` system (amber99sb-ildn, no virtual sites, water excluded)
    does not have. Such a name is refused here, where gmx would give it no
    area; if virtual sites are ever added, those entries belong here."""
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
    if not np.all(np.isfinite(x)):
        # A NaN atom falls in no cell of the grid, so it would have no
        # neighbours: it and the atoms around it would keep their whole
        # area, with nothing said.
        raise ValueError(f"{int((~np.isfinite(x).all(1)).sum())} of {n} atoms have a coordinate that is "
                         "not a finite number")
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
    residue is not in it, or when its number belongs to two residues: two
    chains simulated with the same numbering, or two neighbours told apart
    only by a PDB insertion code (52 and 52A), which a .gro file drops. An
    area summed over both would be no residue's, and `gmx sasa`'s `resnr`
    selection would sum the same two."""
    where = np.array([k for k, i in enumerate(surface) if atoms[i][0] == resnr], dtype=int)
    if not len(where):
        raise ValueError(f"residue {resnr} has no atoms in the protein")
    if where[-1] - where[0] + 1 != len(where):
        raise ValueError(f"residue number {resnr} appears in more than one place in the protein (more "
                         "than one chain simulated?); its solvent exposure needs one chain: `caterva md "
                         "--chain`")
    names = [atoms[surface[k]][2] for k in where]
    if len(set(names)) != len(names):
        twice = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"residue number {resnr} has two atoms named {', '.join(twice)}, so it numbers two "
                         "residues (a PDB insertion code, which a .gro file drops?); its solvent exposure "
                         "would be the sum of both")
    return where


def peptide_bonded(atoms: Sequence[Tuple[int, str, str, np.ndarray]], surface: Sequence[int],
                   where: Sequence[int], box: Optional[np.ndarray] = None) -> bool:
    """Whether the residue at positions `where` of `surface` has a peptide
    bond on both sides: its N within PEPTIDE_BOND_NM of the C of the residue
    before it in the structure, and its C of the N of the residue after.
    Not by residue number, which can skip where nothing is missing (a
    numbering that follows a homologue's) or run on across a break. `box`,
    when given, is the periodic box, and the bond is measured to the
    nearest image. A residue without N or C, or next to one, has no bond
    there."""
    def residue_at(k: int, step: int) -> List[int]:
        r, out = atoms[surface[k]][0], []
        while 0 <= k < len(surface) and atoms[surface[k]][0] == r:
            out.append(k)
            k += step
        return out

    def position(ks: Sequence[int], name: str) -> Optional[np.ndarray]:
        found = [atoms[surface[k]][3] for k in ks if atoms[surface[k]][2] == name]
        return np.asarray(found[0], float) if found else None

    from caterva.md.xtc import nearest_image
    if where[0] == 0 or where[-1] == len(surface) - 1:
        return False
    ends = (position(residue_at(where[0] - 1, -1), "C"), position(where, "N"),
            position(where, "C"), position(residue_at(where[-1] + 1, 1), "N"))
    if any(e is None for e in ends):
        return False
    for a, b in ((ends[0], ends[1]), (ends[2], ends[3])):
        d = b - a if box is None else nearest_image(b - a, box)[0]
        if float(np.sqrt((d * d).sum())) >= PEPTIDE_BOND_NM:
            return False
    return True


class Surface:
    """The protein of one system, ready to measure: its atoms, their radii,
    which of them belong to each residue asked about, and whether each of
    those residues is inside the chain (`peptide_bonded`, in the structure
    given), which Tien et al.'s maxima need."""

    def __init__(self, atoms: Sequence[Tuple[int, str, str, np.ndarray]], residues: Sequence[int],
                 protein: Optional[Collection[int]] = None, box: Optional[np.ndarray] = None):
        self.index = np.array(surface_atoms(atoms, protein), dtype=int)
        self.radii = np.array([radius(atoms[i][2]) for i in self.index])
        self.members = [residue_members(atoms, self.index, r) for r in residues]
        self.in_chain = [peptide_bonded(atoms, self.index, m, box) for m in self.members]

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
    #: False for a residue without a peptide bond on both sides (the first
    #: or last of the chain, or one beside a break in it), which Tien et al.
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


#: The three states in order of exposure, so that a replica's range of
#: frames can be asked whether it spans the starting state.
STATES = ("buried", "partly exposed", "exposed")


def exposure_verdict(e: Exposure) -> str:
    """The residue's state at the start against its state in each replica:
    "buried throughout", "buried at the start, exposed in every replica",
    or, when the replicas differ, which of them left the starting state
    ("buried at the start, exposed in rep2; replicas disagree").

    A replica whose mean is in another state, but whose middle 95% of
    frames still reaches back into the starting state, has not clearly
    left it: its mean sits near a threshold, and another run of the same
    system can put it on the other side (lysozyme's Asn46 was at 19% of its
    maximum in rep2 of one scripts/md_smoke.py run, with frames from 17% to
    23%, and at 20% in the next). Such a replica is named with "by its mean,
    with frames still <start state>", and it is not counted towards
    "replicas disagree", which is kept for replicas that each clearly stayed
    or clearly left."""
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
    def judged(area: float) -> str:
        return state(round(e.relative(area), 2))

    start = judged(e.at_start)
    clear: List[Tuple[str, str]] = []    # (replica, state) where the replica clearly stayed or left
    near: List[Tuple[str, str]] = []     # (replica, state by its mean) where its frames reach back
    for name, mean, _, low, high in e.per_replica:
        s = judged(mean)
        reach = [STATES.index(judged(v)) for v in (low, high) if not math.isnan(v)]
        if s != start and reach and min(reach) <= STATES.index(start) <= max(reach):
            near.append((name, s))
        else:
            clear.append((name, s))
    if not near and all(s == start for _, s in clear):
        return f"{start} throughout"
    if not near and len({s for _, s in clear}) == 1:
        return f"{start} at the start, {clear[0][1]} in every replica"
    moved: Dict[str, List[str]] = {}
    for name, s in clear:
        if s != start:
            moved.setdefault(s, []).append(name)
    parts = [f"{s} in {' and '.join(names)}" for s, names in moved.items()]
    parts += [f"{s} in {name} by its mean, with frames still {start}" for name, s in near]
    disagree = len({s for _, s in clear}) > 1
    return f"{start} at the start, " + ", ".join(parts) + ("; replicas disagree" if disagree else "")


def output_selection(resnr: int) -> str:
    """One catalytic residue as a `gmx sasa -output` selection: a subset of
    the surface, as -output requires, even if water numbering ever reached
    the residue's number."""
    return f"group {SURFACE_GROUP} and resnr {resnr}"


def gmx_options() -> str:
    """The `gmx sasa` options that make its surface this module's: the same
    atoms, probe and number of points asked for (gmx rounds -ndots up: GMX_DOTS),
    no periodic images."""
    return f"-surface {SURFACE_GROUP} -probe {PROBE_NM:g} -ndots {DOTS} -nopbc"


__all__ = ["PROBE_NM", "RADII_NM", "DOTS", "GMX_DOTS", "PATCHES", "ROUTES_AGREE_NM", "ROUTES_AGREE_FLOOR_NM2",
           "routes_agree_nm2", "SOLVENT", "SURFACE_GROUP", "PEPTIDE_BOND_NM", "radius", "sphere",
           "neighbour_pairs", "atom_areas", "surface_atoms", "residue_members", "peptide_bonded", "Surface",
           "summarise_areas",
           "TIEN_MAX_A2", "BURIED", "EXPOSED", "Exposure", "state", "STATES", "exposure_verdict", "CHAIN_END",
           "NO_FRAMES", "ONE_REPLICA", "no_maximum", "output_selection", "gmx_options"]
