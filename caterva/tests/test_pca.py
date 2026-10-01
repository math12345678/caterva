"""The active site's principal motions (caterva/analyze/pca.py), checked
against GROMACS on a real trajectory and against what the theory says on
synthetic ones.

The real frames are the 21 of lysozyme replica 1 in fixtures/md
(lyso_1aki_res1-59.*, residues 1-59, which hold all six catalytic
residues). lyso_1aki_rep1_gmx_pca.txt holds what gmx covar, gmx anaeig and
gmx analyze printed for them (fixtures/md/README.md has the commands).

Every trajectory built here from random numbers is SYNTHETIC, made only to
check that a known mode is recovered, that a rigid motion leaves nothing,
or that the chance levels this module prints are what random subspaces and
random frames actually give. None of it reaches a report.
"""
from __future__ import annotations

import gzip
import math
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from caterva.analyze import pca
from caterva.analyze.__main__ import (Analysis, AnalyzeError, _gro_atoms, _gro_box, commands, gromacs_pca,
                                      pca_section, write_pca_index)
from caterva.analyze.plan import Atom, plan
from caterva.md import xtc

MD = Path(__file__).parent / "fixtures" / "md"
ORDER = [48, 50, 46, 59, 52, 35]      # M-CSA's order, as the lysozyme run had it


def _gmx() -> dict:
    """lyso_1aki_rep1_gmx_pca.txt: key -> the values gmx printed, as floats."""
    out = {}
    for line in (MD / "lyso_1aki_rep1_gmx_pca.txt").read_text().splitlines():
        key, *values = line.split()
        out[key] = [float(v) for v in values]
    return out


@pytest.fixture(scope="module")
def lysozyme(tmp_path_factory):
    """The fixture's atoms, box, frames, catalytic heavy atoms, the whole
    reference, the superposed frames, and the plan made from its protein."""
    d = tmp_path_factory.mktemp("lyso")
    gro = d / "em.gro"
    gro.write_bytes(gzip.decompress((MD / "lyso_1aki_res1-59.gro.gz").read_bytes()))
    atoms = _gro_atoms(gro)
    box = _gro_box(gro.read_text().splitlines()[-1])
    traj = xtc.read(MD / "lyso_1aki_res1-59.xtc")
    idx = pca.heavy_atoms(atoms, ORDER)
    ref = xtc.make_whole(np.array([atoms[i][3] for i in idx]), box)
    protein = [Atom("A", r, n, name, tuple(float(v) * 10 for v in xyz)) for r, n, name, xyz in atoms]
    p = plan(protein, [(r, next(a.resname for a in protein if a.resnr == r)) for r in ORDER])
    return {"atoms": atoms, "box": box, "traj": traj, "idx": idx, "ref": ref,
            "X": pca.fitted(traj, idx, ref), "plan": p}


# --- the atoms ------------------------------------------------------------------------

def test_the_atoms_are_every_heavy_atom_of_each_catalytic_residue(lysozyme):
    atoms, idx = lysozyme["atoms"], lysozyme["idx"]
    assert len(idx) == 47 and idx == sorted(idx)
    names = {}
    for i in idx:
        names.setdefault(atoms[i][0], []).append(atoms[i][2])
    assert names[35] == ["N", "CA", "CB", "CG", "CD", "OE1", "OE2", "C", "O"]
    assert names[50] == ["N", "CA", "CB", "OG", "C", "O"]
    assert sorted(names) == sorted(ORDER)
    assert not any(pca.is_hydrogen(atoms[i][2]) for i in idx)


def test_a_water_that_shares_a_catalytic_residue_number_is_not_taken():
    # .gro residue numbers wrap at 100000, so a water can carry one.
    xyz = np.zeros(3)
    atoms = [(5, "SER", "N", xyz), (5, "SER", "H", xyz), (5, "SER", "OG", xyz), (6, "GLY", "CA", xyz),
             (5, "SOL", "OW", xyz), (5, "SOL", "HW1", xyz)]
    assert pca.heavy_atoms(atoms, [5]) == [0, 2]
    assert pca.is_hydrogen("1HB") and not pca.is_hydrogen("OH")


# --- against GROMACS, on the real frames ---------------------------------------------

def test_eigenvalues_trace_and_projections_equal_gmx_covar_and_anaeig(lysozyme):
    """gmx covar -s em.gro -n <the 47 atoms> (fit and analysis group the
    same, so an unweighted fit), and gmx anaeig -proj on PC1 and PC2."""
    ref = _gmx()
    m = pca.modes(lysozyme["X"])
    assert m.frames == int(ref["full_frames"][0]) == 21
    gmx_eig = np.array(ref["full_eigenvalues"])
    # gmx prints six significant digits; three of the ten differ by one in the
    # sixth, the worst (mode 9) by 5.7e-6 relative.
    assert np.max(np.abs(m.eigenvalues[:10] - gmx_eig) / gmx_eig) < 2e-5
    assert abs(m.trace - ref["full_trace"][0]) / ref["full_trace"][0] < 2e-5
    # The covariance of 21 frames has 20 non-zero eigenvalues and no more.
    assert m.eigenvalues[19] > 1e-4 and m.eigenvalues[20] < 1e-12
    for j in range(2):
        gmx_p = np.array(ref[f"full_projection_pc{j + 1}"])
        sign = np.sign(gmx_p @ m.projections[:, j])      # a mode's sign is arbitrary
        assert np.max(np.abs(sign * m.projections[:, j] - gmx_p)) < 1.5e-5   # gmx prints 1e-5 nm


def test_cosine_content_equals_gmx_analyze_after_its_normalisation(lysozyme):
    ref = _gmx()
    X = lysozyme["X"]
    for part, frames in (("full", X), ("first", X[:10]), ("second", X[10:])):
        m = pca.modes(frames, k=5)
        for j in range(2):
            native = pca.cosine_content(m.projections[:, j], j + 1)
            printed = ref[f"{part}_cosine"][j]
            assert abs(native - pca.from_gmx_cosine(printed, m.frames, j + 1)) < 2e-5
            # gmx's own normalisation is (n + 1)/n times this one.
            assert abs(printed - native * (m.frames + 1) / m.frames) < 3e-5
    # Replica 1's first mode over its 10 ps is nearly the half-cosine of diffusion.
    full = pca.modes(X)
    assert round(pca.cosine_content(full.projections[:, 0], 1), 3) == 0.768


def test_what_gmx_anaeig_over_prints_is_the_rmsip_squared(lysozyme):
    """gmx anaeig -v <first half> -v2 <second half> -first 1 -last 5 -over:
    row m is (1/5) sum over the five modes of the first half and the first m
    of the second of the squared inner products, so row 5 is RMSIP^2."""
    ref = _gmx()
    X = lysozyme["X"]
    a, b = pca.modes(X[:10], k=5), pca.modes(X[10:], k=10)
    with np.errstate(all="ignore"):   # Accelerate's spurious flags, as in caterva/md/xtc.py
        squared = (a.vectors.T @ b.vectors) ** 2
    for m, printed in enumerate(ref["first_second_overlap"], start=1):
        assert abs(squared[:, :m].sum() / 5 - printed) <= 0.0005 + 1e-9    # printed to 0.001
    b5 = pca.modes(X[10:], k=5)
    assert abs(pca.rmsip(a.vectors, b5.vectors) ** 2 - ref["first_second_overlap"][4]) <= 0.0005 + 1e-9


def _write_gmx_outputs(d: Path, ref: dict):
    """What pca_commands leaves behind, written from what gmx printed for
    the fixture, with its two halves as the two replicas and the whole run
    as the pooled frames."""
    for rep, part in (("rep1", "first"), ("rep2", "second")):
        r = d / rep
        r.mkdir(exist_ok=True)
        (r / "pca_covar.log").write_text(f"Read {int(ref[part + '_frames'][0])} frames from rep/md_whole.xtc\n"
                                         f"Trace of the covariance matrix before diagonalizing: "
                                         f"{ref[part + '_trace'][0]:g}\n")
        (r / "pca_eigenval.xvg").write_text("@ title\n" + "".join(
            f"{i} {v:g}\n" for i, v in enumerate(ref[part + "_eigenvalues"], 1)))
        (r / "pca_cosine.xvg").write_text("".join(f"{i} {v:g}\n" for i, v in enumerate(ref[part + "_cosine"], 1)))
    (d / "pca_pooled_covar.log").write_text(f"Read 21 frames\nTrace of the covariance matrix before "
                                            f"diagonalizing: {ref['full_trace'][0]:g}\n")
    (d / "pca_pooled_eigenval.xvg").write_text("".join(f"{i} {v:g}\n"
                                                       for i, v in enumerate(ref["full_eigenvalues"], 1)))
    (d / "pca_overlap_rep1_rep2.xvg").write_text("".join(f"{i} {v:.3f}\n"
                                                         for i, v in enumerate(ref["first_second_overlap"], 1)))
    return [d / "rep1", d / "rep2"]


def test_both_routes_give_the_same_section_on_real_frames(lysozyme, tmp_path, monkeypatch):
    """The fixture's two halves (10 and 11 frames) stand in for two
    replicas. They are too short for ten modes, so both routes run here with
    five modes and a minimum of 10 frames (the module's constants patched);
    the arithmetic is the same at ten."""
    monkeypatch.setattr(pca, "RMSIP_MODES", 5)
    monkeypatch.setattr(pca, "MIN_PCA_FRAMES", 10)
    X, p = lysozyme["X"], lysozyme["plan"]
    labels = [s.label for s in p.sites]
    native = pca.from_frames([("rep1", X[:10]), ("rep2", X[10:])], 47, labels)
    reps = _write_gmx_outputs(tmp_path, _gmx())
    gromacs = gromacs_pca(tmp_path, p, reps, lysozyme["idx"])
    assert [r.frames for r in native.replicas] == [r.frames for r in gromacs.replicas] == [10, 11]
    for n, g in zip([*native.replicas, native.pooled], [*gromacs.replicas, gromacs.pooled]):
        assert np.max(np.abs(np.array(n.eigenvalues) - g.eigenvalues) / np.array(g.eigenvalues)) < 2e-5
        assert abs(n.trace - g.trace) / g.trace < 2e-5
    for n, g in zip(native.replicas, gromacs.replicas):
        assert max(abs(x - y) for x, y in zip(n.cosine, g.cosine)) < 2e-5
    assert abs(native.overlaps[0][2] - gromacs.overlaps[0][2]) < 0.001
    # The law of total variance, on gmx's own traces: a fifth of the whole
    # run's motion is the difference between its two halves' mean structures.
    assert abs(native.between - gromacs.between) < 1e-4
    assert round(gromacs.between, 2) == 0.20
    sections = [pca_section(Analysis("1AKI", "A", "test", p, [], None, motions=m)) for m in (native, gromacs)]
    assert sections[0] == sections[1]
    text = "\n".join(sections[0])
    assert "| rep1 | 10 | 0.008722 | 0.007784 | 0.007272 | 0.03787 |" in text
    assert "| pooled | 21 | 0.01498 | 0.007462 | 0.005129 | 0.04803 |" in text
    assert "| rep1–rep2 | 0.546 | 0.298 | partly shared |" in text


def test_a_run_too_short_is_refused_alike_on_both_routes(lysozyme, tmp_path):
    X, p = lysozyme["X"], lysozyme["plan"]
    native = pca.from_frames([("rep1", X[:5]), ("rep2", X[5:10])], 47, [s.label for s in p.sites])
    for rep in ("rep1", "rep2"):
        (tmp_path / rep).mkdir()
        (tmp_path / rep / "pca_covar.log").write_text(
            "Read 5 frames\nTrace of the covariance matrix before diagonalizing: 0.01\n")
    gromacs = gromacs_pca(tmp_path, p, [tmp_path / "rep1", tmp_path / "rep2"], lysozyme["idx"])
    assert native.too_short == gromacs.too_short == [("rep1", 5), ("rep2", 5)]
    assert native.replicas == gromacs.replicas == [] and native.pooled is gromacs.pooled is None
    section = [pca_section(Analysis("1AKI", "A", "test", p, [], None, motions=m)) for m in (native, gromacs)]
    assert section[0] == section[1]
    assert any(line.startswith("Not measured in rep1 (5 frames), rep2 (5 frames)") for line in section[0])
    assert native.consistent   # nothing measured, so nothing says unconverged


def test_an_analyze_sh_older_than_the_principal_motions_is_refused_by_name(lysozyme, tmp_path):
    (tmp_path / "rep1").mkdir()
    with pytest.raises(AnalyzeError, match=r"pca_covar\.log does not exist: run analyze\.sh again"):
        gromacs_pca(tmp_path, lysozyme["plan"], [tmp_path / "rep1"], lysozyme["idx"])
    assert gromacs_pca(tmp_path, lysozyme["plan"], [tmp_path / "rep1"], []) is None   # no em.gro


# --- the GROMACS commands ------------------------------------------------------------

def test_covar_fits_to_the_whole_reference_and_trajectory_the_rmsf_uses(lysozyme, tmp_path):
    p, idx = lysozyme["plan"], lysozyme["idx"]
    lines = commands(p, ["rep1", "rep2"], pca=idx)
    covar = [line for line in lines if " covar " in line]
    assert covar[0] == ("printf '0\\n0\\n' | $GMX covar -s rep1/rmsf_reference.pdb -f rep1/md_whole.xtc "
                        "-n pca.ndx -last 10 -o rep1/pca_eigenval.xvg -v rep1/pca_eigenvec.trr "
                        "-av rep1/pca_average.pdb -l rep1/pca_covar.log")
    assert "-f pca_pooled.xtc" in covar[2] and "-l pca_pooled_covar.log" in covar[2]
    made = max(i for i, line in enumerate(lines) if "-o rep2/md_whole.xtc" in line)
    assert lines.index(covar[0]) > made
    assert "$GMX trjcat -f rep1/md_whole.xtc rep2/md_whole.xtc -cat -o pca_pooled.xtc" in lines
    over = [line for line in lines if "-over" in line]
    assert over == ["$GMX anaeig -v rep1/pca_eigenvec.trr -v2 rep2/pca_eigenvec.trr -first 1 -last 10 "
                    "-over pca_overlap_rep1_rep2.xvg"]
    proj = lines.index(next(line for line in lines if "-proj rep1/" in line))
    assert "-first 1 -last 2" in lines[proj]
    assert lines[proj + 1] == "$GMX analyze -f rep1/pca_proj.xvg -n 2 -cc rep1/pca_cosine.xvg"
    assert not any(" covar " in line for line in commands(p, ["rep1"]))            # no em.gro, no atoms
    assert not any(" covar " in line for line in commands(p, ["rep1"], pca=idx[:10]))   # too few atoms
    write_pca_index(tmp_path, idx)
    text = (tmp_path / "pca.ndx").read_text()
    assert text.startswith("[ active_site ]\n534 536 538 ") and len(text.split()) == 3 + 47


# --- the exit code and the verdicts ----------------------------------------------------

def test_a_diffusion_like_replica_makes_the_run_not_a_result(lysozyme, monkeypatch):
    """Replica 1 over its 10 ps drifts along PC1 (cosine content 0.768);
    its first 5 ps alone do not (0.144 and 0.015, gmx analyze: 0.159 and
    0.016 before conversion)."""
    X, labels = lysozyme["X"], [s.label for s in lysozyme["plan"].sites]
    whole = pca.from_frames([("rep1", X)], 47, labels)
    assert pca.cosine_verdict(whole.replicas[0]) == pca.DIFFUSION_LIKE and not whole.consistent
    a = Analysis("1AKI", "A", "test", lysozyme["plan"], [], None, motions=whole)
    assert not a.all_consistent
    monkeypatch.setattr(pca, "MIN_PCA_FRAMES", 10)
    first = pca.from_frames([("rep1", X[:10])], 47, labels)
    assert [round(c, 3) for c in first.replicas[0].cosine] == [0.144, 0.015]
    assert pca.cosine_verdict(first.replicas[0]) == pca.NOT_DIFFUSIVE and first.consistent


@pytest.mark.parametrize("rmsip,verdict", [(0.72, pca.SAME), (0.40, pca.PARTLY), (0.30, pca.CHANCE)])
def test_rmsip_verdicts_at_lysozymes_size(rmsip, verdict):
    # 47 atoms: 135 directions; chance is RMSIP^2 0.074 +/- 0.010, at most 0.103.
    assert pca.rmsip_verdict(rmsip, 135) == verdict


def test_an_active_site_too_small_for_ten_modes_is_refused():
    # 10 heavy atoms leave 24 directions: chance reaches 0.417 + 3 x 0.034 > 0.5.
    assert pca.too_few_atoms(10) is not None and "24 directions" in pca.too_few_atoms(10)
    assert pca.too_few_atoms(11) is None
    assert pca.from_frames([], 10, ["Ser50"]).not_measured == pca.too_few_atoms(10)


# --- synthetic trajectories: what the analysis must recover --------------------------------

def _internal_direction(ref: np.ndarray, rng) -> np.ndarray:
    """A unit 3N-vector with no part along a translation or an infinitesimal
    rotation of `ref`: a motion the fit cannot remove."""
    c = ref - ref.mean(0)
    rigid = [np.tile(e, len(ref)) for e in np.eye(3)] + [np.cross(c, e).ravel() for e in np.eye(3)]
    q, _ = np.linalg.qr(np.array(rigid).T)
    v = rng.normal(size=3 * len(ref))
    v -= q @ (q.T @ v)
    return v / np.linalg.norm(v)


def _frames(xs, box):
    return [xtc.Frame(i, float(i), box, x, 1000.0) for i, x in enumerate(xs)]


def test_one_synthetic_mode_is_recovered_with_its_eigenvalue(lysozyme):
    """SYNTHETIC: the real reference moved along one internal direction by
    A sin(2 pi t / n), whose variance over the n frames is A^2 / 2."""
    ref, rng = lysozyme["ref"], np.random.default_rng(20260930)
    v = _internal_direction(ref, rng)
    n, amp = 40, 0.01
    a = amp * np.sin(2 * np.pi * np.arange(n) / n)
    X = ref.ravel() + a[:, None] * v
    m = pca.modes(X)
    assert abs(m.eigenvalues[0] - amp * amp / 2) < 1e-15 and m.eigenvalues[1] < 1e-25
    assert abs(abs(m.vectors[:, 0] @ v) - 1) < 1e-12
    # Through the fit: the direction is internal, so the fit keeps it, up to
    # a rotation of second order in A.
    box = np.diag([10.0, 10.0, 10.0])
    fitted = pca.fitted(_frames([x.reshape(-1, 3) for x in X], box), range(len(ref)), ref)
    mf = pca.modes(fitted)
    assert abs(mf.eigenvalues[0] / (amp * amp / 2) - 1) < 1e-3
    assert abs(mf.vectors[:, 0] @ v) > 0.9999 and mf.eigenvalues[1] < 1e-6 * mf.eigenvalues[0]


def test_a_rigidly_moved_frame_has_no_variance_after_the_fit(lysozyme):
    """SYNTHETIC: the real reference, rotated and translated at random."""
    from scipy.spatial.transform import Rotation
    ref = lysozyme["ref"]
    rots = Rotation.random(12, random_state=7).as_matrix()
    shifts = np.random.default_rng(8).uniform(-1, 1, size=(12, 3))
    c = ref.mean(0)
    xs = [(ref - c) @ R.T + c + s for R, s in zip(rots, shifts)]
    X = pca.fitted(_frames(xs, np.diag([20.0, 20.0, 20.0])), range(len(ref)), ref)
    assert np.max(np.abs(X - ref.ravel())) < 1e-12
    assert pca.modes(X).trace < 1e-24


def test_a_replica_that_did_not_move_is_called_no_motion_on_both_routes(lysozyme):
    """SYNTHETIC: replicas whose frames are the real reference rigidly moved,
    so nothing is left after the fit but rounding (about 1e-32 nm^2). Its
    modes and cosine contents are directions in that noise, and must not
    read as a converged replica or as two replicas with the same motions."""
    from scipy.spatial.transform import Rotation
    ref = lysozyme["ref"]
    c = ref.mean(0)
    reps = []
    for seed in (1, 2):
        rots = Rotation.random(21, random_state=seed).as_matrix()
        xs = [(ref - c) @ R.T + c for R in rots]
        reps.append((f"rep{seed}", pca.fitted(_frames(xs, np.diag([20.0, 20.0, 20.0])), range(len(ref)), ref)))
    m = pca.from_frames(reps, len(ref), ["x"])
    assert all(r.trace < pca.STILL_NM2 for r in m.replicas)
    assert [pca.cosine_verdict(r) for r in m.replicas] == [pca.NO_MOTION] * 2
    assert all(math.isnan(c) for r in m.replicas for c in r.cosine)
    assert math.isnan(m.overlaps[0][2]) and pca.rmsip_verdict(m.overlaps[0][2], m.dim) == pca.NO_MOTION
    assert m.between is None
    # The GROMACS route builds the same records from what gmx printed.
    still = pca.ReplicaModes("rep1", 21, [1e-10] * 10, 1e-9, (0.9, 0.8))
    moved = pca.ReplicaModes("rep2", 21, [1e-3] * 10, 2e-2, (0.9, 0.8))
    assert pca.cosine_verdict(still) == pca.NO_MOTION and pca.cosine_verdict(moved) == pca.DIFFUSION_LIKE
    assert math.isnan(pca.overlap(still, moved, 0.9)) and pca.overlap(moved, moved, 0.9) == 0.9


def test_the_chance_of_a_diffusion_like_verdict_counts_both_modes():
    """The verdict fires on PC1 or PC2, so its chance on uncorrelated frames
    is bounded by the sum of the two modes' tails, not PC1's alone."""
    p1, p2 = pca.uncorrelated_cosine(21, 1)[1], pca.uncorrelated_cosine(21, 2)[1]
    assert pca.chance_diffusion_like(21) == p1 + p2
    assert 3e-4 < p1 < 4e-4 and 3e-4 < p2 < 4e-4 and round(pca.chance_diffusion_like(21), 4) == 0.0007


def test_rmsip_of_the_same_subspace_is_one_and_of_perpendicular_ones_zero():
    rng = np.random.default_rng(3)
    q, _ = np.linalg.qr(rng.normal(size=(60, 20)))
    a, b = q[:, :10], q[:, 10:]
    assert abs(pca.rmsip(a, a) - 1) < 1e-12
    turned, _ = np.linalg.qr(rng.normal(size=(10, 10)))
    with np.errstate(all="ignore"):
        other = a @ turned
    assert abs(pca.rmsip(a, other) - 1) < 1e-12     # another basis of the same subspace
    assert pca.rmsip(a, b) < 1e-12
    half = np.hstack([a[:, :5], b[:, :5]])               # shares five of ten directions
    assert abs(pca.rmsip(a, half) ** 2 - 0.5) < 1e-12
    with pytest.raises(ValueError):
        pca.rmsip(a, a[:, :5])


def test_the_cosine_content_of_a_cosine_is_one():
    for n in (21, 50):
        for i in (1, 2, 3):
            c = np.cos(np.pi * i * np.arange(n) / (n - 1))
            assert abs(pca.cosine_content(c, i) - 1) < 1e-12
            gmx = 2 * (c @ c) ** 2 / (n * (c @ c))    # what gmx analyze -cc computes
            assert abs(pca.from_gmx_cosine(gmx, n, i) - 1) < 1e-12
    assert abs(2 * 11 / 21 - 1.048) < 0.0005          # the report's "1.048 at 21 frames"
    assert math.isnan(pca.cosine_content([0.0] * 21, 1)) and math.isnan(pca.cosine_content([1.0], 1))


def test_random_walks_have_principal_components_that_are_cosines():
    """SYNTHETIC: Hess (2000): the principal components of high-dimensional
    random diffusion are cosines. 200 walks of 21 steps in 141 dimensions,
    lysozyme's active-site size at the frame minimum."""
    rng = np.random.default_rng(2000)
    c1, c2 = [], []
    for _ in range(200):
        m = pca.modes(np.cumsum(rng.normal(size=(21, 141)), axis=0))
        c1.append(pca.cosine_content(m.projections[:, 0], 1))
        c2.append(pca.cosine_content(m.projections[:, 1], 2))
    assert min(c1) > 0.9 and np.mean(c1) > 0.98
    assert np.mean(c2) > 0.9
    assert all(max(x, y) >= pca.DIFFUSIVE for x, y in zip(c1, c2))


def test_uncorrelated_frames_follow_the_stated_beta_distribution():
    """SYNTHETIC, statistical: frames drawn independently (Gaussian, each
    coordinate its own spread) give PC1 a cosine content distributed as
    Beta(1/2, (n-2)/2), with mean 1/(n-1)."""
    rng = np.random.default_rng(2002)
    n, scales = 21, np.linspace(1.0, 0.1, 141)
    c1 = np.array([pca.cosine_content(pca.modes(rng.normal(size=(n, 141)) * scales).projections[:, 0], 1)
                   for _ in range(4000)])
    mean, tail = pca.uncorrelated_cosine(n)
    assert abs(mean - 1 / (n - 1)) < 1e-12
    assert abs(c1.mean() - mean) < 4 * c1.std() / math.sqrt(len(c1))
    assert stats.kstest(c1, stats.beta(0.5, (n - 2) / 2).cdf).pvalue > 0.001
    p20 = float(stats.beta(0.5, (n - 2) / 2).sf(0.2))
    assert abs((c1 >= 0.2).mean() - p20) < 4 * math.sqrt(p20 * (1 - p20) / len(c1))
    assert tail < 0.001 and (c1 >= pca.DIFFUSIVE).mean() < 0.002


def test_the_chance_rmsip_is_what_random_subspaces_give():
    """SYNTHETIC, statistical: 3000 uniformly random 10-dimensional
    subspaces of 135 dimensions against a fixed one."""
    rng = np.random.default_rng(1999)
    k, dim = 10, 135
    sq = []
    for _ in range(3000):
        q, _ = np.linalg.qr(rng.normal(size=(dim, k)))
        sq.append((q[:k] ** 2).sum() / k)      # the fixed subspace: the first k axes
    sq = np.array(sq)
    mean, sd = pca.chance_rmsip2(k, dim)
    assert abs(mean - 0.0741) < 1e-4 and abs(sd - 0.00966) < 1e-5
    assert abs(sq.mean() - mean) < 4 * sd / math.sqrt(len(sq))
    assert abs(sq.std(ddof=1) / sd - 1) < 0.06


def test_the_smoke_runs_comparison_reads_the_section_and_catches_a_difference(lysozyme, tmp_path, monkeypatch):
    """scripts/md_smoke.py compares the two routes' principal-motion tables
    on every CI run; here it reads the sections both routes print for the
    fixture's halves, finds them in agreement, and finds an eigenvalue
    moved by 1% and an RMSIP moved by 0.01."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("md_smoke", Path(__file__).parents[2] / "scripts" / "md_smoke.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    monkeypatch.setattr(pca, "RMSIP_MODES", 5)
    monkeypatch.setattr(pca, "MIN_PCA_FRAMES", 10)
    X, p = lysozyme["X"], lysozyme["plan"]
    native = pca.from_frames([("rep1", X[:10]), ("rep2", X[10:])], 47, [s.label for s in p.sites])
    gromacs = gromacs_pca(tmp_path, p, _write_gmx_outputs(tmp_path, _gmx()), lysozyme["idx"])
    texts = ["\n".join(pca_section(Analysis("1AKI", "A", "test", p, [], None, motions=m)))
             for m in (native, gromacs)]
    tables = [smoke._pca_tables(t) for t in texts]
    assert sorted(tables[0]["eigen"]) == ["pooled", "rep1", "rep2"] and list(tables[0]["rmsip"]) == ["rep1–rep2"]
    assert tables[0]["between"] == 0.20 and tables[0]["chance_edge"] is not None
    assert smoke._pca_agree(*tables)[0] == []
    moved = smoke._pca_tables(texts[1].replace("| rep1 | 10 | 0.008722 |", "| rep1 | 10 | 0.008809 |")
                              .replace("| 0.546 | 0.298 |", "| 0.556 | 0.298 |"))
    problems = smoke._pca_agree(tables[0], moved)[0]
    assert any("eigenvalue 0.008722 natively, 0.008809" in x for x in problems)
    assert any("RMSIP 0.546 natively, 0.556" in x for x in problems)
