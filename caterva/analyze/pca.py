"""The active site's principal motions: what each replica's catalytic
residues mostly do, whether the replicas do the same, and whether the
largest of those motions is only the run still drifting.

Every other measurement in `caterva analyze` is chosen in advance: a
distance, an angle, a dihedral, a count. Principal component analysis asks
the trajectory instead which directions the active site moved in most, and
that answers two questions nothing else here can. Did the replicas sample
the same motions, or did each wander off its own way? And is a replica's
dominant motion something it sampled back and forth, or a one-way drift of
the kind random diffusion makes, which every short run has and which says
the sampling has not converged (Hess 2000, 2002)?

THE ATOMS
---------
Every heavy atom of every catalytic residue the plan has (Plan.sites):
backbone N, CA, C and O as well as the side chain; hydrogens left out. Not
the CA and side chain alone, because some catalytic residues act through
their backbone: a glycine in an oxyanion hole donates its amide, and the
plan stands such a residue in with its CA (plan.py) for want of functional
atoms. With the CA and side chain it would contribute one atom and none of
the backbone it acts through. Hydrogens are left out because their
positions follow their heavy atoms (bond lengths constrained, fast
librations about them) and would add three coordinates each of motion that
says nothing the heavy atoms do not. On hen lysozyme's six catalytic
residues (Glu35, Asn46, Asp48, Ser50, Asp52, Asn59) this is 47 atoms, 141
coordinates.

THE FIT
-------
Each frame is made whole (the atoms taken one after another to their
nearest periodic image, caterva.md.xtc.make_whole) and superposed on the
same atoms of em.gro by unweighted least squares (Kabsch,
caterva.md.xtc.kabsch_fit). em.gro and not the average structure, because
it is the structure every replica began from and the one the RMSF is
fitted to: the modes of different replicas are then in one frame of
reference and can be compared, which is what `gmx anaeig` asks of an
overlap ("the analysis should use the same fitting structure"). Unweighted,
because `gmx covar` makes the fit unweighted when the fit and analysis
groups are the same and the analysis is not mass-weighted (its covar.log
says "Fit is non-mass weighted"), and because a mass-weighted analysis
would give eigenvalues in amu nm^2 rather than nm^2.

The fit removes six directions exactly. The superposed atoms keep the
reference's centroid, so no coordinate moves along a uniform translation;
and at the least-squares optimum the sum over atoms of r_ref x x vanishes,
so no displacement has a component along an infinitesimal rotation of the
reference. Every mode therefore lies in the 3N - 6 directions left, and
that is the space the chance level below is taken in.

THE COVARIANCE
--------------
About the replica's own mean, divided by the number of frames (as `gmx
covar` does; its trace agrees with Caterva's to the six digits it prints).
Every frame is used, as for the rotamers and water, and nothing is
discarded as relaxation: a drift away from the starting structure is one of
the things this looks for, and throwing the first half away would hide it.
The eigenvalues are the mean-square fluctuation (nm^2) along each mode, and
their sum, the trace, is the total. The pooled analysis joins every
replica's superposed frames in one covariance about their common mean. By
the law of total variance its trace is the frame-weighted mean of the
replicas' own traces plus the spread of the replicas' mean structures, so
1 - (weighted mean of the replicas' traces) / (pooled trace) is the part of
the pooled motion that is the replicas sitting in different places rather
than moving about them (`PrincipalMotions.between`). Both routes have every
trace, so both report it.

DO THE REPLICAS MOVE THE SAME WAY?
----------------------------------
The root-mean-square inner product of two replicas' first k modes (Amadei,
Ceruso & Di Nola 1999, Proteins 36:419):
RMSIP^2 = (1/k) sum_i sum_j (a_i . b_j)^2 over i, j = 1..k. It is 1 when
the two sets of modes span the same directions and 0 when every mode of one
is perpendicular to every mode of the other. Its square is the mean, over
one replica's k modes, of the fraction of each (its squared length) that
lies in the other replica's k-dimensional subspace.

k = RMSIP_MODES = 10, a choice. Ten modes hold most of an active site's
motion (0.89 of it on the lysozyme fixture's 21 frames, 0.98 in both
replicas of a 0.4 ps smoke run on 2026-09-30), and they are few enough
that 21 frames span twice as many directions (HOW MANY FRAMES, below). The
share the ten hold is printed beside them, so what they cover is on the
page, and the chance level below is worked out for whatever k is, so "low"
is calibrated regardless.

What chance gives. For a fixed k-dimensional subspace A and a uniformly
random one B in D dimensions, sum_ij (a_i . b_j)^2 = tr(P_A P_B). By
rotational invariance E[P_B] = (k/D) I, so E[RMSIP^2] = k/D. The second
moment follows from the fourth-order isotropic moments of a random
projection (E[P (x) P] = alpha I(x)I + beta (the two pairings), fixed by
P^2 = P and tr P = k): Var(RMSIP^2) = 2 (D - k)^2 / (D^2 (D - 1) (D + 2)).
Both are checked against random subspaces in caterva/tests/test_pca.py. On
lysozyme, D = 3 x 47 - 6 = 135 and k = 10: chance gives RMSIP^2 = 0.074
with standard deviation 0.010, RMSIP about 0.27.

Verdicts (chosen thresholds): same motions when RMSIP^2 is at least
SAME_RMSIP2 = 0.5 (RMSIP at least 0.71): on average more than half of each
replica's mode lies in the other's. No more alike than chance when RMSIP^2
is within CHANCE_SD = 3 standard deviations of k/D. Partly shared in
between. An active site with so few atoms that the two bands meet (k/D +
3 sd reaching 0.5, which happens at 10 heavy atoms or fewer, D of 24 or
less) has no room for ten modes to be a small part of its motion, and is
refused.

IS THE LARGEST MOTION ONLY DIFFUSION?
-------------------------------------
Hess (2000, Phys Rev E 62:8438) derived that the principal components of
high-dimensional random diffusion are cosines: the projection on PC i
follows cos(i pi t / T), i/2 periods over the run. A run too short to have
sampled a motion back and forth looks like that along its largest modes.
The cosine content (Hess 2002, Phys Rev E 65:031910) measures how closely a
projection p(t) follows its cosine. Here it is

    c_i = (sum_t cos(i pi t/(n-1)) p_t)^2 / (sum_t cos^2(i pi t/(n-1)) sum_t p_t^2)

over the n frames, t = 0..n-1: the squared correlation between the
projection and the cosine. It is exactly 1 for a pure cosine and at most 1
for anything (Cauchy-Schwarz), and it tends to Hess's integral as n grows.
`gmx analyze -cc` divides by n sum p_t^2 / 2 instead, which is the same
only in that limit: sum_t cos^2 is (n + 1)/2 over these frames, so it
prints (n + 1)/n times this, and a pure cosine reads 1.048 there at 21
frames. The GROMACS route converts its values (`from_gmx_cosine`); on the
lysozyme fixture the two agree to the digits gmx prints.

What an uncorrelated run gives. If the frames were drawn independently from
a Gaussian distribution, the time-side unit vector of each principal
component would be uniform on the sphere of mean-zero n-vectors (the data
matrix's distribution does not change under any rotation of the frames
that keeps their mean), so c_1 would follow Beta(1/2, (n-2)/2), with mean
1/(n - 1): 0.05 at 21 frames, and 0.5 or more with probability 0.0003. PC2's
cosine has a mean of 1/n over the frames, which scales both by
1 - 2/(n(n + 1)). `uncorrelated_cosine` computes this, and the report
prints it beside the values so the reader can see what low means at that
length.

Verdict (chosen threshold): diffusion-like, not converged, when the cosine
content of PC1 or PC2 is at least DIFFUSIVE = 0.5, that is when the one
cosine accounts for at least half of the projection's mean square. A low
cosine content does not show convergence: a replica can sample one basin
thoroughly and never find the next. The replica comparison is the check on
that, and neither is the check on the chemistry, which the distances are.

HOW MANY FRAMES
---------------
MIN_PCA_FRAMES = 2 k + 1 = 21, below which nothing is reported. The
covariance of n frames has at most n - 1 non-zero eigenvalues. With n - 1
= k every direction the frames span is among the k "principal" ones and
the RMSIP only asks whether two replicas visited the same few points; at 2k
+ 1 the k compared are at most half of the directions sampled. At 21
frames uncorrelated frames reach the cosine threshold by chance with
probability 0.0003, while 200 random walks of 21 steps in 141 dimensions
gave PC1 a cosine content between 0.97 and 1.00 (test_pca.py), so the
test separates the two; at 5 frames, the smoke run's old length, the chance
is 0.18 and it would not.

CHECKED AGAINST GROMACS
-----------------------
On the 21 frames of lysozyme replica 1 in caterva/tests/fixtures/md
(residues 1-59, the catalytic heavy atoms fitted to that run's em.gro):
`gmx covar` gives the same eigenvalues to within 6e-6 relative (it prints
six significant digits) and the same trace; `gmx anaeig -proj` the same
projections on PC1 and PC2 (up to the sign of each mode) to the 1e-5 nm it
prints; `gmx analyze -cc` the same cosine contents after conversion; and
`gmx anaeig -over` on the two halves of the replica the same RMSIP^2 to the
0.001 it prints. The references are in lyso_1aki_rep1_gmx_pca.txt and the
comparison is a test. On a 0.4 ps smoke run (two replicas of 21 frames,
2026-09-30), gmx covar run directly gave the first ten eigenvalues of each
replica to within 8.2e-6 relative of Caterva's, gmx analyze the cosine
contents to 4e-6 after conversion, and gmx anaeig -over the RMSIP^2 (0.1029
here, 0.103 there) to its 0.001; scripts/md_smoke.py compares the two
routes' tables on every CI run.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

#: How many modes the replicas are compared on (the k of the RMSIP). A
#: choice; see the module docstring.
RMSIP_MODES = 10
#: Frames a replica needs before any of this is reported: the k compared
#: modes are then at most half of the n - 1 the frames can span.
MIN_PCA_FRAMES = 2 * RMSIP_MODES + 1
#: The modes whose cosine content is taken: PC1 and PC2.
COSINE_MODES = 2
#: Cosine content at or above which a mode is called diffusion-like: the
#: one cosine accounts for at least half of the projection's mean square.
DIFFUSIVE = 0.5
#: RMSIP^2 at or above which two replicas are said to share their motions:
#: on average more than half of each mode lies in the other's subspace.
SAME_RMSIP2 = 0.5
#: How many standard deviations of the chance RMSIP^2 still count as chance.
CHANCE_SD = 3.0
#: Directions the least-squares fit removes: three translations, three
#: rotations.
RIGID = 6

DIFFUSION_LIKE = "diffusion-like, not converged"
NOT_DIFFUSIVE = "not diffusion-like"
SAME = "same motions"
PARTLY = "partly shared"
CHANCE = "no more alike than chance"


def is_hydrogen(name: str) -> bool:
    """GROMACS names a protein's hydrogens H, HA, HB1, HD21 ...; no heavy
    atom of a standard residue has a name starting with H. A leading digit
    (1HB, in some PDB files) is skipped."""
    return name.lstrip("0123456789")[:1] == "H"


def heavy_atoms(atoms: Sequence[Tuple], resnrs: Sequence[int]) -> List[int]:
    """0-based indices, in the system's order, of every heavy atom of the
    residues numbered `resnrs`. `atoms` is (resnr, resname, name, xyz) for
    the whole system (em.gro), protein first. Only each residue's first run
    of atoms is taken: a .gro residue number has five digits and wraps, so a
    water far down the file can carry a catalytic residue's number, and the
    first occurrence is the one pdb2gmx gave the protein (as _gro_index in
    caterva/analyze/__main__.py also takes it)."""
    want = set(resnrs)
    done = set()
    out: List[int] = []
    current = None
    for i, a in enumerate(atoms):
        if a[0] != current:
            if current in want:
                done.add(current)
            current = a[0]
        if current in want and current not in done and not is_hydrogen(a[2]):
            out.append(i)
    return out


def _finite(x: np.ndarray, what: str) -> np.ndarray:
    # Apple's Accelerate BLAS raises spurious divide/overflow flags on finite
    # products (see caterva.md.xtc.kabsch_fit), so the products here run
    # under errstate and are checked afterwards instead.
    if not np.all(np.isfinite(x)):
        raise FloatingPointError(f"{what} came out non-finite")
    return x


def fitted(traj, idx: Sequence[int], reference: np.ndarray) -> np.ndarray:
    """(frames, 3N) coordinates of the atoms `idx`, each frame made whole
    and superposed on `reference` (the same atoms, whole) by unweighted
    least squares; x1 y1 z1 x2 ..., the order of gmx covar's coordinates."""
    from caterva.md.xtc import kabsch_fit, make_whole
    idx = list(idx)
    out = np.empty((len(traj), 3 * len(idx)))
    for k, f in enumerate(traj):
        x = make_whole(f.x[idx], f.box)
        R, t = kabsch_fit(x, reference)
        with np.errstate(all="ignore"):
            out[k] = (x @ R + t).ravel()
    return _finite(out, "the superposed coordinates")


@dataclass
class Modes:
    """One covariance analysis: every eigenvalue (nm^2, largest first), the
    first modes as unit columns, and each frame's projection on the first
    COSINE_MODES of them (nm)."""

    eigenvalues: np.ndarray
    vectors: np.ndarray
    projections: np.ndarray
    trace: float

    @property
    def frames(self) -> int:
        return len(self.projections)


def modes(coords: np.ndarray, k: Optional[int] = None) -> Modes:
    """Principal components of the rows of `coords` (frames x coordinates),
    about their mean, with gmx covar's divisor (the number of frames). By
    singular value decomposition of the centred frames, which gives the
    covariance's eigenvectors and eigenvalues (squared singular values over
    n) without forming it, and no more of them than the frames can span.
    The first k modes are kept (RMSIP_MODES unless given)."""
    k = RMSIP_MODES if k is None else k
    x = np.asarray(coords, dtype=float)
    n = len(x)
    centred = x - x.mean(0)
    with np.errstate(all="ignore"):
        _, s, vt = np.linalg.svd(centred, full_matrices=False)
        proj = centred @ vt[:COSINE_MODES].T
        trace = float((centred * centred).sum() / n)
    _finite(s, "the singular values")
    _finite(proj, "the projections")
    return Modes(s * s / n, vt[:k].T.copy(), proj, trace)


def rmsip(a: np.ndarray, b: np.ndarray) -> float:
    """Root-mean-square inner product of two sets of k orthonormal columns
    (Amadei, Ceruso & Di Nola 1999)."""
    if a.shape != b.shape:
        raise ValueError(f"cannot compare {a.shape[1]} modes with {b.shape[1]}")
    with np.errstate(all="ignore"):
        o = a.T @ b
    return math.sqrt(float((_finite(o, "the inner products") ** 2).sum()) / a.shape[1])


def _cosine(n: int, i: int) -> np.ndarray:
    return np.cos(np.pi * i * np.arange(n) / (n - 1))


def cosine_content(p: Sequence[float], i: int) -> float:
    """How closely the projection p (one value per frame, equally spaced)
    follows a cosine of i/2 periods over the run: the squared correlation
    with it, 1 for a pure cosine. NaN when there is nothing to correlate
    (fewer than two frames, or no motion)."""
    p = np.asarray(p, dtype=float)
    n = len(p)
    if n < 2:
        return float("nan")
    c = _cosine(n, i)
    pp = float(p @ p)
    if pp == 0.0:
        return float("nan")
    return float((c @ p) ** 2 / (float(c @ c) * pp))


def from_gmx_cosine(value: float, n: int, i: int) -> float:
    """`gmx analyze -cc`'s cosine content of set i over n frames, which is
    2 (sum cos p)^2 / (n sum p^2), converted to `cosine_content`'s."""
    c = _cosine(n, i)
    return value * n / (2.0 * float(c @ c))


def chance_rmsip2(k: int, dim: int) -> Tuple[float, float]:
    """Mean and standard deviation of RMSIP^2 between a fixed k-dimensional
    subspace and a uniformly random one in `dim` dimensions (derived in the
    module docstring)."""
    mean = k / dim
    var = 2.0 * (dim - k) ** 2 / (dim * dim * (dim - 1) * (dim + 2))
    return mean, math.sqrt(var)


def uncorrelated_cosine(n: int, i: int = 1, threshold: float = DIFFUSIVE) -> Tuple[float, float]:
    """Mean cosine content of PC i over n frames drawn independently from a
    Gaussian distribution, and the probability that it reaches `threshold`
    by chance: a scaled Beta(1/2, (n-2)/2) (module docstring)."""
    from scipy.stats import beta
    u = _cosine(n, i)
    u0 = u - u.mean()
    scale = float(u0 @ u0) / float(u @ u)
    mean = scale / (n - 1)
    tail = float(beta(0.5, (n - 2) / 2.0).sf(threshold / scale)) if threshold < scale else 0.0
    return mean, tail


def too_few_atoms(atoms: int, k: Optional[int] = None) -> Optional[str]:
    """Why an active site of `atoms` heavy atoms is refused, or None: the
    band chance fills must stay below the one called shared."""
    k = RMSIP_MODES if k is None else k
    dim = 3 * atoms - RIGID
    if dim > k:
        mean, sd = chance_rmsip2(k, dim)
        if mean + CHANCE_SD * sd < SAME_RMSIP2:
            return None
    return (f"the catalytic residues have {atoms} heavy atoms, which leave {max(dim, 0)} directions once the fit "
            f"has removed rotation and translation: too few for {k} modes to be a small part of their motion "
            f"(two random sets of {k} would already look alike)")


@dataclass
class ReplicaModes:
    """What the report prints for one replica, or for the pooled frames:
    the same on both routes."""

    name: str
    frames: int
    #: The first RMSIP_MODES eigenvalues, nm^2, largest first.
    eigenvalues: List[float]
    #: The sum of every eigenvalue: the total mean-square fluctuation, nm^2.
    trace: float
    #: Cosine content of PC1 and PC2; None for the pooled frames, which are
    #: not one run in time.
    cosine: Optional[Tuple[float, float]] = None

    def share(self, m: int) -> float:
        return sum(self.eigenvalues[:m]) / self.trace if self.trace > 0 else float("nan")


@dataclass
class PrincipalMotions:
    atoms: int
    residues: List[str]
    replicas: List[ReplicaModes] = field(default_factory=list)
    #: (replica, frames) for each replica below MIN_PCA_FRAMES.
    too_short: List[Tuple[str, int]] = field(default_factory=list)
    #: Every replica's frames in one covariance; None unless every replica
    #: was measured and there are at least two.
    pooled: Optional[ReplicaModes] = None
    #: (replica, replica, RMSIP) for each pair of measured replicas.
    overlaps: List[Tuple[str, str, float]] = field(default_factory=list)
    #: Why nothing was measured, when nothing was.
    not_measured: Optional[str] = None

    @property
    def dim(self) -> int:
        return 3 * self.atoms - RIGID

    @property
    def between(self) -> Optional[float]:
        """The part of the pooled variance that is the difference between
        the replicas' mean structures (law of total variance)."""
        if self.pooled is None or not self.replicas or self.pooled.trace <= 0:
            return None
        n = sum(r.frames for r in self.replicas)
        within = sum(r.frames * r.trace for r in self.replicas) / n
        return 1.0 - within / self.pooled.trace

    @property
    def consistent(self) -> bool:
        """No measured replica looks like random diffusion along PC1 or PC2,
        and no pair of replicas is no more alike than chance: the two
        verdicts here that say a run has not converged."""
        return (all(cosine_verdict(r) != DIFFUSION_LIKE for r in self.replicas)
                and all(rmsip_verdict(x, self.dim) != CHANCE for _, _, x in self.overlaps))


def cosine_verdict(r: ReplicaModes) -> str:
    if r.cosine is None or any(math.isnan(c) for c in r.cosine):
        return "no motion"
    return DIFFUSION_LIKE if max(r.cosine) >= DIFFUSIVE else NOT_DIFFUSIVE


def rmsip_verdict(value: float, dim: int, k: Optional[int] = None) -> str:
    k = RMSIP_MODES if k is None else k
    sq = value * value
    if sq >= SAME_RMSIP2:
        return SAME
    mean, sd = chance_rmsip2(k, dim)
    return CHANCE if sq <= mean + CHANCE_SD * sd else PARTLY


def _summary(name: str, m: Modes, with_cosine: bool = True) -> ReplicaModes:
    cos = (tuple(cosine_content(m.projections[:, j], j + 1) for j in range(COSINE_MODES))
           if with_cosine else None)
    return ReplicaModes(name, m.frames, [float(v) for v in m.eigenvalues[:RMSIP_MODES]], m.trace, cos)


def from_frames(per_replica: Sequence[Tuple[str, np.ndarray]], atoms: int,
                residues: Sequence[str]) -> PrincipalMotions:
    """The whole analysis from each replica's superposed frames (`fitted`),
    computed by Caterva: the native route."""
    out = PrincipalMotions(atoms, list(residues))
    out.not_measured = too_few_atoms(atoms)
    if out.not_measured:
        return out
    measured = []
    for name, X in per_replica:
        if len(X) < MIN_PCA_FRAMES:
            out.too_short.append((name, len(X)))
            continue
        m = modes(X)
        measured.append((name, m))
        out.replicas.append(_summary(name, m))
    for i in range(len(measured)):
        for j in range(i + 1, len(measured)):
            (a, ma), (b, mb) = measured[i], measured[j]
            out.overlaps.append((a, b, rmsip(ma.vectors, mb.vectors)))
    if len(measured) >= 2 and not out.too_short:
        pooled = modes(np.vstack([X for _, X in per_replica]))
        out.pooled = _summary("pooled", pooled, with_cosine=False)
    return out


__all__ = ["RMSIP_MODES", "MIN_PCA_FRAMES", "COSINE_MODES", "DIFFUSIVE", "SAME_RMSIP2", "CHANCE_SD", "RIGID",
           "DIFFUSION_LIKE", "NOT_DIFFUSIVE", "SAME", "PARTLY", "CHANCE", "is_hydrogen", "heavy_atoms", "fitted",
           "Modes", "modes", "rmsip", "cosine_content", "from_gmx_cosine", "chance_rmsip2",
           "uncorrelated_cosine", "too_few_atoms", "ReplicaModes", "PrincipalMotions", "cosine_verdict",
           "rmsip_verdict", "from_frames"]
