"""Solvent exposure of the catalytic residues (caterva/analyze/sasa.py).

Three kinds of check. Geometry that has an answer on paper: one atom alone
has the whole area of its grown sphere, and two overlapping atoms each lose
the spherical cap the other covers. The shortcuts against the plain method:
the cell grid finds exactly the overlapping pairs a comparison of every
pair finds, and the patches decide exactly the points that testing each
point alone decides, on a real protein. And `gmx sasa` itself, which uses
a different set of points (the double cubic lattice), on two committed
structures (fixtures/md/README.md): every residue of T4 lysozyme against
`gmx sasa -ndots 10000`, and the six catalytic residues of hen lysozyme in
21 real frames against the command analyze.sh runs.
"""
from __future__ import annotations

import gzip
import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.distance import cdist

from caterva.analyze import sasa
from caterva.analyze.__main__ import (AnalyzeError, Analysis, _exposures, _gro_atoms, _gro_box, commands,
                                      gromacs_sasa, measure_native, sasa_section)
from caterva.analyze.plan import Atom, plan
from caterva.md import xtc

MD = Path(__file__).parent / "fixtures" / "md"
REPO = Path(__file__).resolve().parents[2]
CATALYTIC = [48, 50, 46, 59, 52, 35]  # lysozyme's, in M-CSA's order, as the lysozyme run had them


def _gro(tmp_path_factory, name: str) -> Path:
    path = tmp_path_factory.mktemp(name.replace(".", "_")) / "em.gro"
    path.write_bytes(gzip.decompress((MD / f"{name}.gro.gz").read_bytes()))
    return path


def _brute(x: np.ndarray, radii: np.ndarray, dots: int) -> np.ndarray:
    """Shrake & Rupley with nothing left out: every point of every atom
    tested against every other atom whose grown sphere overlaps it."""
    R = radii + sasa.PROBE_NM
    u = sasa.sphere(dots)
    out = np.zeros(len(x))
    for i in range(len(x)):
        d = x - x[i]
        dist2 = (d * d).sum(1)
        near = np.flatnonzero((dist2 < (R + R[i]) ** 2) & (np.arange(len(x)) != i))
        t = (R[i] ** 2 + dist2[near] - R[near] ** 2) / (2.0 * R[i])
        with np.errstate(all="ignore"):
            buried = (u @ d[near].T > t).any(1)
        out[i] = 4.0 * math.pi * R[i] * R[i] * (dots - buried.sum()) / dots
    return out


# --- radii and points ----------------------------------------------------------------------

@pytest.mark.parametrize("name,r", [("CA", 0.17), ("C", 0.17), ("HB1", 0.12), ("H", 0.12), ("N", 0.155),
                                    ("NZ", 0.155), ("OD1", 0.152), ("OC2", 0.152), ("SG", 0.18),
                                    ("SD", 0.18), ("Cl", 0.175), ("CL", 0.17)])
def test_radii_are_the_ones_vdwradii_dat_lists(name, r):
    """By the longest entry the name starts with, as GROMACS reads the
    file. "CL" is not "Cl": the file is case-sensitive, and GROMACS gives a
    chloride named CL a carbon's radius too (only "C" is a prefix of it)."""
    assert sasa.radius(name) == r


@pytest.mark.parametrize("name", ["1HB", "ZN", "MW", ""])
def test_an_atom_name_no_radius_starts_is_refused(name):
    with pytest.raises(ValueError, match="no van der Waals radius"):
        sasa.radius(name)


def test_the_points_are_on_the_sphere_in_bands_of_equal_area():
    """Point k sits at z = 1 - (2k + 1)/n, so a band of the sphere holds
    its share of the points to within half a point, whatever the band."""
    n = 2000
    u = sasa.sphere(n)
    assert u.shape == (n, 3) and np.allclose((u * u).sum(1), 1.0)
    assert np.array_equal(u, sasa.sphere(n))
    for low, high in [(-1.0, 1.0), (0.0, 1.0), (-0.37, 0.52), (0.9, 1.0), (-1.0, -0.999)]:
        inside = int(((u[:, 2] > low) & (u[:, 2] <= high)).sum())
        assert abs(inside - n * (high - low) / 2) <= 1.0


# --- geometry with an answer on paper ------------------------------------------------------

@pytest.mark.parametrize("name", ["H", "C", "N", "O", "S"])
def test_an_isolated_atom_has_the_whole_area_of_its_grown_sphere(name):
    r = sasa.radius(name)
    area = sasa.atom_areas(np.array([[1.0, 2.0, 3.0]]), np.array([r]))
    assert area[0] == pytest.approx(4 * math.pi * (r + sasa.PROBE_NM) ** 2, rel=1e-12)
    assert sasa.atom_areas(np.zeros((1, 3)), np.array([r]), probe=0.0)[0] == pytest.approx(4 * math.pi * r * r)


def _cap_exposed(Ri: float, Rj: float, d: float) -> float:
    """The area of sphere i (radius Ri) outside sphere j (radius Rj) at
    distance d: the whole sphere less the cap inside j, 2 pi Ri^2 (1 - c),
    where c is the cosine of the cap's half-angle seen from i's centre."""
    c = (Ri * Ri + d * d - Rj * Rj) / (2 * Ri * d)
    return 2 * math.pi * Ri * Ri * (1 + min(max(c, -1.0), 1.0))


#: Two atoms at bonded and non-bonded distances (nm), along directions that
#: are not the points' own axis, where the bands would make it exact.
PAIRS = [("C", "C", 0.153), ("C", "O", 0.123), ("N", "H", 0.101), ("S", "S", 0.204), ("C", "H", 0.109),
         ("C", "O", 0.300), ("C", "N", 0.500), ("H", "H", 0.300)]
DIRECTIONS = [np.array(v) / np.linalg.norm(v) for v in ([1.0, 2.0, 3.0], [-0.3, 0.8, 0.52], [0.9, -0.1, -0.4])]


@pytest.mark.parametrize("a,b,d", PAIRS)
def test_two_atoms_each_lose_the_cap_the_other_covers(a, b, d):
    """At DOTS points the area is within 0.5% of the grown sphere of the
    answer (on these pairs the error was at most 0.39% when this was
    written), and at 32,000 points within 0.1% (0.057%): a cap's edge
    crosses the points, so the error falls as the points get denser."""
    ra, rb = sasa.radius(a), sasa.radius(b)
    Ra, Rb = ra + sasa.PROBE_NM, rb + sasa.PROBE_NM
    want = (_cap_exposed(Ra, Rb, d), _cap_exposed(Rb, Ra, d))
    for u in DIRECTIONS:
        x = np.array([[0.3, -0.2, 0.1], [0.3, -0.2, 0.1] + d * u])
        for dots, share in ((sasa.DOTS, 0.005), (32000, 0.001)):
            got = sasa.atom_areas(x, np.array([ra, rb]), dots=dots)
            for g, w, R in zip(got, want, (Ra, Rb)):
                assert abs(g - w) <= share * 4 * math.pi * R * R, (a, b, d, dots)


def test_atoms_out_of_reach_keep_their_area_and_a_swallowed_atom_has_none():
    rc, rh = sasa.radius("C"), sasa.radius("H")
    Rc, Rh = rc + sasa.PROBE_NM, rh + sasa.PROBE_NM
    far = sasa.atom_areas(np.array([[0.0, 0.0, 0.0], [Rc + Rh + 1e-6, 0.0, 0.0]]), np.array([rc, rh]))
    assert far == pytest.approx([4 * math.pi * Rc * Rc, 4 * math.pi * Rh * Rh], rel=1e-12)
    # The hydrogen's grown sphere (0.26 nm) lies wholly inside the carbon's
    # (0.31 nm) when their centres are 0.01 nm apart: no point of it is
    # left, and every point of the carbon's is outside the hydrogen's.
    inside = sasa.atom_areas(np.array([[0.0, 0.0, 0.0], [0.006, 0.008, 0.0]]), np.array([rc, rh]))
    assert inside[1] == 0.0 and inside[0] == pytest.approx(4 * math.pi * Rc * Rc, rel=1e-12)
    # At one point, the larger buries all of the smaller and loses nothing.
    same = sasa.atom_areas(np.zeros((2, 3)), np.array([rc, rh]))
    assert same[1] == 0.0 and same[0] == pytest.approx(4 * math.pi * Rc * Rc, rel=1e-12)


def test_no_atoms_and_one_atom_need_no_neighbours():
    assert sasa.atom_areas(np.zeros((0, 3)), np.zeros(0)).shape == (0,)
    i, j = sasa.neighbour_pairs(np.zeros((1, 3)), np.array([0.3]))
    assert len(i) == len(j) == 0


# --- the shortcuts, against the plain method on a real protein -----------------------------

@pytest.fixture(scope="module")
def t4l(tmp_path_factory):
    """T4 lysozyme's protein from a real `caterva complex` em.gro: 2,603
    atoms with hydrogens, residues 1-162 (the benzene and water after them
    are not part of the surface)."""
    atoms = _gro_atoms(_gro(tmp_path_factory, "t4l_bnz_first6000"))
    index = sasa.surface_atoms(atoms, range(1, 163))
    x = np.array([atoms[i][3] for i in index])
    radii = np.array([sasa.radius(atoms[i][2]) for i in index])
    resnr = np.array([atoms[i][0] for i in index])
    return x, radii, resnr, {atoms[i][0]: atoms[i][1] for i in index}


def test_the_fixture_is_the_protein_the_readme_describes(t4l):
    x, _, resnr, names = t4l
    assert len(x) == 2603 and set(resnr) == set(range(1, 163)) and names[1] == "MET"


def test_the_cell_grid_finds_exactly_the_overlapping_pairs(t4l):
    x, radii, _, _ = t4l
    reach = radii + sasa.PROBE_NM
    i, j = sasa.neighbour_pairs(x, reach)
    d = cdist(x, x)
    want_i, want_j = np.nonzero((d < reach[:, None] + reach[None, :]) & ~np.eye(len(x), dtype=bool))
    assert np.array_equal(i, want_i) and np.array_equal(j, want_j)
    assert len(i) > 100_000  # a real neighbour list, not a trivial one


@pytest.mark.parametrize("dots", [sasa.DOTS, 777])
def test_the_patches_decide_every_point_as_testing_it_alone_would(t4l, dots):
    x, radii, _, _ = t4l
    assert np.array_equal(sasa.atom_areas(x, radii, dots=dots), _brute(x, radii, dots))


def test_the_areas_converge_as_points_are_added(t4l):
    """Against 20,000 points: the root-mean-square error of an atom's area
    falls as the points are made denser (0.0029 nm^2 at 250, 0.0010 at
    1,000, 0.00037 at 4,000 when this was written), and at DOTS no atom is
    off by more than 0.005 nm^2 (0.0036) and no residue by more than 0.01
    (0.0065), which the table's 0.01 nm^2 holds."""
    x, radii, resnr, _ = t4l
    ref = sasa.atom_areas(x, radii, dots=20000)
    rms = []
    for dots in (250, 1000, 4000):
        err = sasa.atom_areas(x, radii, dots=dots) - ref
        rms.append(float(np.sqrt((err * err).mean())))
    assert all(a > b for a, b in zip(rms, rms[1:])), rms
    at = sasa.atom_areas(x, radii) - ref
    assert np.abs(at).max() <= 0.005
    assert np.abs(np.bincount(resnr, weights=at)).max() <= 0.01


def test_every_residue_of_t4_lysozyme_matches_gmx_sasa(t4l):
    """`gmx sasa -ndots 10000` on the same atoms: every residue within
    ROUTES_AGREE_NM2 at DOTS points (0.0088 nm^2 at most when this was
    written, 0.0024 root mean square), and closer as Caterva's points are
    made denser (0.0044 at 10,000), because the two converge on the same
    surface."""
    x, radii, resnr, names = t4l
    printed = [line.split() for line in (MD / "t4l_bnz_first6000_gmx_sasa.txt").read_text().splitlines()]
    assert [int(r) for r, _, _ in printed] == list(range(1, 163))
    assert all(names[int(r)] == n for r, n, _ in printed)
    gmx = np.array([float(a) for _, _, a in printed])
    for dots, worst, rms in ((sasa.DOTS, sasa.ROUTES_AGREE_NM2, 0.004), (10000, 0.006, 0.002)):
        mine = np.bincount(resnr, weights=sasa.atom_areas(x, radii, dots=dots))[1:]
        assert np.abs(mine - gmx).max() <= worst, dots
        assert float(np.sqrt(((mine - gmx) ** 2).mean())) <= rms, dots


# --- the catalytic residues of lysozyme, frame by frame -----------------------------------

def _gmx_lysozyme():
    """resnr (or "total") -> (area in the .gro, the 21 per-frame areas)."""
    out = {}
    for line in (MD / "lyso_1aki_rep1_gmx_sasa.txt").read_text().splitlines():
        parts = line.split()
        key = parts[0] if parts[0] == "total" else int(parts[0])
        out[key] = (float(parts[2]), [float(v) for v in parts[3:]])
    return out


@pytest.fixture(scope="module")
def lysozyme(tmp_path_factory):
    gro = _gro(tmp_path_factory, "lyso_1aki_res1-59")
    return gro, xtc.read(MD / "lyso_1aki_res1-59.xtc")


def test_catalytic_areas_match_gmx_sasa_in_every_frame(lysozyme):
    """The command analyze.sh runs, on 21 real frames: every catalytic
    residue in every frame, and at the start, within ROUTES_AGREE_NM2 (at
    most 0.0096 nm^2 when this was written)."""
    gro, traj = lysozyme
    atoms = _gro_atoms(gro)
    order = sorted(CATALYTIC)
    surface = sasa.Surface(atoms, order)
    assert len(surface.index) == 900
    reference = _gmx_lysozyme()
    per_frame = surface.series(traj)
    start = surface.areas(np.array([a[3] for a in atoms]), _gro_box(gro.read_text().splitlines()[-1]))
    worst = 0.0
    for k, resnr in enumerate(order):
        at_start, frames = reference[resnr]
        assert len(frames) == len(per_frame[k]) == 21
        worst = max(worst, abs(start[k] - at_start), *(abs(a - b) for a, b in zip(per_frame[k], frames)))
    assert worst <= sasa.ROUTES_AGREE_NM2
    assert worst > 0.001  # two point sets: close, not identical


def test_the_area_survives_the_periodic_boundary(tmp_path_factory):
    """The same frames with the active site across the periodic box
    (fixtures/md/README.md): the protein is made whole first, so every area
    equals the unwrapped one to within the 0.001 nm re-rounding of putting
    atoms back in the box (0.0027 nm^2 at most over all 21 frames when this
    was written). Taken as stored, not one residue-frame would be right.
    Every third frame, to keep the test quick; the fixture is split across
    the box in all of them."""
    series = {}
    for name in ("lyso_1aki_res1-59_water", "lyso_1aki_res1-59_water_wrapped"):
        atoms = _gro_atoms(_gro(tmp_path_factory, name))
        surface = sasa.Surface(atoms, CATALYTIC)
        traj = xtc.read(MD / f"{name}.xtc")[::3]
        series[name] = np.array(surface.series(traj))
    unwrapped, wrapped = series["lyso_1aki_res1-59_water"], series["lyso_1aki_res1-59_water_wrapped"]
    assert not any(np.allclose(xtc.make_whole(f.x[surface.index], f.box), f.x[surface.index]) for f in traj)
    raw = np.array([[a[m].sum() for m in surface.members]
                    for a in (sasa.atom_areas(f.x[surface.index], surface.radii) for f in traj)]).T
    assert len(traj) == 7 and np.abs(wrapped - unwrapped).max() <= 0.005
    assert int((np.abs(raw - unwrapped) > 0.05).sum()) == raw.size == 42


# --- which atoms, and which residue ---------------------------------------------------------

def test_the_surface_is_the_protein_without_water_ions_or_ligand():
    x = np.zeros(3)
    atoms = [(1, "MET", "N", x), (1, "MET", "CA", x), (2, "GLU", "OE1", x), (163, "BNZ", "C1", x),
             (164, "SOL", "OW", x), (165, "NA", "NA", x), (166, "CL", "CL", x)]
    assert sasa.surface_atoms(atoms) == [0, 1, 2, 3]
    assert sasa.surface_atoms(atoms, protein={1, 2}) == [0, 1, 2]


def test_a_residue_numbered_in_two_chains_or_absent_is_refused():
    x = np.zeros(3)
    atoms = [(35, "GLU", "N", x), (35, "GLU", "CA", x), (36, "SER", "N", x), (35, "GLU", "N", x)]
    surface = sasa.surface_atoms(atoms)
    assert list(sasa.residue_members(atoms, surface, 36)) == [2]
    with pytest.raises(ValueError, match="more than one place"):
        sasa.residue_members(atoms, surface, 35)
    with pytest.raises(ValueError, match="no atoms"):
        sasa.residue_members(atoms, surface, 99)


# --- what is reported -----------------------------------------------------------------------

def test_mean_sd_and_middle_95_percent_of_frames():
    name, mean, sd, low, high = sasa.summarise_areas("rep1", [0.1, 0.2, 0.3, 0.4, 0.5])
    assert name == "rep1" and mean == pytest.approx(0.3) and sd == pytest.approx(math.sqrt(0.025))
    # Linear interpolation between frames: 2.5% of the way along 4 gaps.
    assert low == pytest.approx(0.11) and high == pytest.approx(0.49)
    _, mean, sd, low, high = sasa.summarise_areas("rep1", [0.7])
    assert mean == low == high == 0.7 and math.isnan(sd)  # one frame has no spread
    assert all(math.isnan(v) for v in sasa.summarise_areas("rep1", [])[1:])


def _e(start, *means, resname="SER", in_chain=True):
    """An Exposure of a serine (largest possible area 1.55 nm^2)."""
    return sasa.Exposure("Ser50", resname, start, [(f"rep{i + 1}", m, 0.01, m, m) for i, m in enumerate(means)],
                         in_chain)


@pytest.mark.parametrize("e,verdict", [
    (_e(0.10, 0.12, 0.08), "buried throughout"),
    (_e(0.40, 0.45, 0.50), "partly exposed throughout"),
    (_e(0.90, 0.80, 0.70), "exposed throughout"),
    (_e(0.10, 0.80, 0.90), "buried at the start, exposed in every replica"),
    (_e(0.90, 0.10, 0.12), "exposed at the start, buried in every replica"),
    (_e(0.10, 0.12, 0.80), "buried at the start, exposed in rep2; replicas disagree"),
    (_e(0.10, 0.50, 0.80, 0.10), "buried at the start, partly exposed in rep1, exposed in rep2; replicas disagree"),
    (_e(0.10, 0.12, 0.13, resname="MSE"), sasa.no_maximum("MSE")),
    (_e(0.10, 0.12, 0.13, in_chain=False), sasa.CHAIN_END),
    (_e(0.10, 0.12, float("nan")), sasa.NO_FRAMES),
    (_e(0.10, 0.12), sasa.ONE_REPLICA),
])
def test_verdicts(e, verdict):
    assert sasa.exposure_verdict(e) == verdict


def test_the_verdict_reads_the_share_as_printed():
    """0.3099 nm^2 of a serine's 1.55 is 19.99%, printed as 20%: partly
    exposed, as the printed number says, not buried by a hundredth of a
    per cent."""
    e = _e(0.3099, 0.3099, 0.3099)
    assert f"{e.relative(0.3099):.0%}" == "20%"
    assert sasa.exposure_verdict(e) == "partly exposed throughout"


def _two_sites():
    """His10 and Ser30 with their functional atoms, and Ala1 and Ala90 at
    the chain's ends (Angstrom)."""
    rows = [(1, "CA", "ALA"), (10, "ND1", "HIS"), (10, "NE2", "HIS"), (30, "OG", "SER"), (90, "CA", "ALA")]
    atoms = [Atom("A", r, n, name, (float(r), 0.0, 0.0)) for r, name, n in rows]
    return plan(atoms, [(10, "HIS"), (30, "SER")])


def test_the_section_prints_areas_shares_ranges_and_verdicts():
    p = _two_sites()
    nan = float("nan")
    rows = _exposures(p, [0.10, 0.50], {0: [("rep1", 0.80, 0.05, 0.70, 0.90), ("rep2", 0.85, 0.04, 0.78, 0.92)],
                                        1: [("rep1", 0.20, nan, 0.20, 0.20), ("rep2", nan, nan, nan, nan)]})
    section = sasa_section(Analysis("9XYZ", "A", "test", p, [], None, None, None, [], None, None, rows))
    assert section[1] == "## Solvent exposure of the catalytic residues"
    assert "| residue | largest possible (nm²) | at start | rep1 | rep2 | verdict |" in section
    # No distance, so nothing is converged: the exposure verdict waits.
    assert ("| His10 | 2.24 | 0.10 (4%) | 0.80 ± 0.05 [0.70, 0.90] (36%) | 0.85 ± 0.04 [0.78, 0.92] (38%) | "
            "(buried at the start, partly exposed in every replica, not yet a result) |") in section
    assert f"| Ser30 | 1.55 | 0.50 (32%) | 0.20 ± n/a [0.20, 0.20] (13%) | n/a | {sasa.NO_FRAMES} |" in section
    text = "\n".join(section)
    assert "below 20% of the largest possible area" in text and "at 40% or above" in text
    assert "Tien et al. (2013) PLoS ONE 8:e80635" in text and "2000 per atom" in text


def test_a_chain_end_has_no_share_and_no_verdict():
    p = _two_sites()
    rows = [sasa.Exposure("Ala1", "ALA", 0.9, [("rep1", 0.9, 0.1, 0.8, 1.0), ("rep2", 0.9, 0.1, 0.8, 1.0)],
                          in_chain=False)]
    section = sasa_section(Analysis("9XYZ", "A", "test", p, [], None, None, None, [], None, None, rows))
    assert f"| Ala1 | n/a | 0.90 | 0.90 ± 0.10 [0.80, 1.00] | 0.90 ± 0.10 [0.80, 1.00] | {sasa.CHAIN_END} |" in section


def test_the_chain_ends_are_those_of_protein_pdb():
    p = _two_sites()
    assert [e.in_chain for e in _exposures(p, [0.1, 0.1], {0: [], 1: []})] == [True, True]
    ends = plan([Atom("A", r, n, "CA", (float(r), 0.0, 0.0)) for r, n in ((1, "GLY"), (5, "ALA"), (9, "GLY"))],
                [(1, "GLY"), (5, "ALA"), (9, "GLY")])
    assert [e.in_chain for e in _exposures(ends, [0.1] * 3, {0: [], 1: [], 2: []})] == [False, True, False]


def test_not_measured_and_nothing_to_measure_are_said():
    p = _two_sites()
    assert sasa_section(Analysis("9XYZ", "A", "t", p, [], None, None, None, [], None, None, None))[-1] == \
        "Not measured."
    assert sasa_section(Analysis("9XYZ", "A", "t", p, [], None, None, None, [], None, None, []))[-1] == \
        "No catalytic residue to measure."


# --- the GROMACS route ------------------------------------------------------------------------

def test_one_sasa_call_per_replica_and_one_for_the_start():
    p = _two_sites()
    lines = [l for l in commands(p, ["rep1", "rep2"]) if " sasa " in l]
    assert len(lines) == 3
    options = f"-surface Protein -probe 0.14 -ndots {sasa.DOTS} -nopbc"
    outputs = "-output 'group Protein and resnr 10' 'group Protein and resnr 30'"
    assert lines[0] == f"$GMX sasa -s rep1/md.tpr -f rep1/md.xtc {options} {outputs} -o rep1/sasa.xvg " \
                       "-or rep1/sasa_residues.xvg"
    assert lines[1].startswith("$GMX sasa -s rep2/md.tpr -f rep2/md.xtc ") and "-o rep2/sasa.xvg" in lines[1]
    assert lines[2] == f"$GMX sasa -s rep1/md.tpr -f em.gro {options} {outputs} -o sasa_start.xvg"


def test_a_missing_or_stale_sasa_output_is_refused(tmp_path):
    p = _two_sites()
    rep = tmp_path / "rep1"
    rep.mkdir()
    (rep / "sasa.xvg").write_text("0.0 9.0 0.1 0.2\n")
    with pytest.raises(AnalyzeError, match="sasa_start.xvg does not exist"):
        gromacs_sasa(tmp_path, p, [rep])
    (tmp_path / "sasa_start.xvg").write_text("0.0 9.0 0.1\n")  # an older plan: one residue
    with pytest.raises(AnalyzeError, match=r"has 2 columns of solvent-accessible area \(the protein's, then "
                                           r"each catalytic residue's\), the plan has 3"):
        gromacs_sasa(tmp_path, p, [rep])


def _smoke():
    spec = importlib.util.spec_from_file_location("md_smoke", REPO / "scripts" / "md_smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_both_routes_give_the_same_section_on_real_frames(tmp_path, lysozyme):
    """The native route measured on the committed lysozyme frames, against
    the GROMACS route reading what gmx sasa printed for them; judged by the
    helper the CI smoke run uses, and with the same verdicts."""
    gro, _ = lysozyme
    (tmp_path / "em.gro").write_bytes(gro.read_bytes())
    atoms = _gro_atoms(tmp_path / "em.gro")
    protein = [Atom("A", r, n, name, tuple(float(v) * 10 for v in xyz)) for r, n, name, xyz in atoms]
    rep = tmp_path / "rep1"
    rep.mkdir()
    (rep / "md.xtc").write_bytes((MD / "lyso_1aki_res1-59.xtc").read_bytes())
    p = plan(protein, [(r, next(a.resname for a in protein if a.resnr == r)) for r in CATALYTIC])
    native = measure_native(tmp_path, p, [rep])[7]

    reference = _gmx_lysozyme()
    columns = ["total"] + [s.resnr for s in p.sites]
    (tmp_path / "sasa_start.xvg").write_text("0.0 " + " ".join(f"{reference[c][0]:.3f}" for c in columns) + "\n")
    (rep / "sasa.xvg").write_text("".join(
        f"{t * 0.5:.1f} " + " ".join(f"{reference[c][1][t]:.3f}" for c in columns) + "\n" for t in range(21)))
    via_gmx = gromacs_sasa(tmp_path, p, [rep])
    assert [e.label for e in via_gmx] == [e.label for e in native] == [s.label for s in p.sites]

    one = "\n".join(sasa_section(Analysis("1AKI", None, "t", p, [], None, None, None, [], None, None, native)))
    other = "\n".join(sasa_section(Analysis("1AKI", None, "t", p, [], None, None, None, [], None, None, via_gmx)))
    smoke = _smoke()
    rows_native, rows_gmx = smoke._sasa_rows(one), smoke._sasa_rows(other)
    assert len(rows_native) == 6 and all(len(v) == 4 for v in rows_native.values())
    agree, worst = smoke._sasa_agree(rows_native, rows_gmx)
    assert agree and worst <= smoke.SASA_PRINTED_NM2
    # Asn59 is the last residue of this 59-residue fragment, so it is a chain end.
    assert "| Asn59 | n/a |" in one and sasa.CHAIN_END in one
    assert [sasa.exposure_verdict(e) for e in native] == [sasa.exposure_verdict(e) for e in via_gmx]


def test_the_smoke_comparison_holds_areas_to_the_measured_tolerance():
    smoke = _smoke()
    assert smoke.SASA_PRINTED_NM2 == pytest.approx(sasa.ROUTES_AGREE_NM2 + 0.01)
    base = {"Glu35": (0.34, 0.29, 0.24, 0.31), "Ser50": (0.00, 0.01, 0.00, 0.02)}
    near = {"Glu35": (0.33, 0.30, 0.25, 0.33), "Ser50": (0.00, 0.01, 0.00, 0.02)}
    assert smoke._sasa_agree(base, near) == (True, pytest.approx(0.02))
    far = {"Glu35": (0.34, 0.29, 0.24, 0.35), "Ser50": (0.00, 0.01, 0.00, 0.06)}
    assert smoke._sasa_agree(base, far)[0] is False
    assert smoke._sasa_agree(base, {"Glu35": base["Glu35"]})[0] is False     # a residue missing
    assert smoke._sasa_agree(base, {**base, "Ser50": (0.00,)})[0] is False    # a row cut short (n/a)
    assert smoke._sasa_agree({}, {})[0] is False                               # nothing measured
