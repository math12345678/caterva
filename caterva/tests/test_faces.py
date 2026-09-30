"""Which face of a catalytic group its partners are on (caterva/analyze/faces.py).

The anchor is real: `gmx gangle -g1 plane -group1 'cog of (A) plus cog of
(V) plus cog of (B)' -g2 vector -group2 'cog of (V) plus cog of (resnr V
and name CA)'` (GROMACS 2026.1) on the 24 angles lysozyme's catalytic groups
make under the contact cutoff, all 21 frames of a `caterva md` replica
(fixtures/md/lyso_1aki_rep1_gmx_faces.txt), and again on the same frames
translated so that the active site straddles the periodic box
(lyso_1aki_rep1_gmx_faces_wrapped.txt, gangle with the run's md.tpr). And
`gmx gangle -g1 dihedral` on the same four points, each angle both ways
round (lyso_1aki_rep1_gmx_dihedrals.txt): the check that the elevation
names the same face as the dihedral a-v-b-CA in every frame, and the
evidence that the dihedral is the wrong number to put a dead band on. The
rest is constructed geometry whose answer can be worked by hand.
"""
from __future__ import annotations

import gzip
import json
import math
import random
from pathlib import Path

import numpy as np
import pytest

from caterva.analyze.__main__ import (EXIT_NOT_A_RESULT, AnalyzeError, Analysis, _gro_atoms, _gro_index,
                                      commands, face_section, gromacs_faces, main, measure_native)
from caterva.analyze.angles import MOVED_DEG, RESOLVE_DEG, angle_deg
from caterva.analyze.faces import (FLAT, FLAT_DEG, FLAT_IN_CRYSTAL, Face, elevation_deg, elevation_series,
                                   face_fractions, face_name, face_verdict, from_gangle, polar_sine, side)
from caterva.analyze.plan import Atom, plan, read_pdb
from caterva.analyze.rotamers import dihedral
from caterva.md import xtc

MD = Path(__file__).parent / "fixtures" / "md"
#: The six M-CSA catalytic residues of hen lysozyme and their functional atoms.
LYSOZYME = {35: ("OE1", "OE2"), 46: ("OD1", "ND2"), 48: ("OD1", "OD2"), 50: ("OG",),
            52: ("OD1", "OD2"), 59: ("OD1", "ND2")}
#: M-CSA's order, as the lysozyme run had it; it fixes which partner of each
#: angle comes first, and so the sign of its face.
MCSA_ORDER = [48, 50, 46, 59, 52, 35]


def _printed(name):
    """(a, v, b) -> the 21 per-frame values gmx gangle printed."""
    out = {}
    for line in (MD / name).read_text().splitlines():
        parts = line.split()
        out[tuple(int(v) for v in parts[:3])] = [float(v) for v in parts[3:]]
    return out


def _unzip(tmp, name):
    gro = tmp / name.replace(".gz", "")
    gro.write_bytes(gzip.decompress((MD / name).read_bytes()))
    return gro


@pytest.fixture(scope="module")
def stored(tmp_path_factory):
    gro = _unzip(tmp_path_factory.mktemp("stored"), "lyso_1aki_res1-59.gro.gz")
    return _gro_index(gro), xtc.read(MD / "lyso_1aki_res1-59.xtc"), _printed("lyso_1aki_rep1_gmx_faces.txt")


@pytest.fixture(scope="module")
def wrapped(tmp_path_factory):
    gro = _unzip(tmp_path_factory.mktemp("wrapped"), "lyso_1aki_res1-59_water_wrapped.gro.gz")
    return (_gro_index(gro), xtc.read(MD / "lyso_1aki_res1-59_water_wrapped.xtc"),
            _printed("lyso_1aki_rep1_gmx_faces_wrapped.txt"))


def _groups(index):
    return {r: [index[(r, n)] for n in LYSOZYME[r]] for r in LYSOZYME}


# --- against gmx gangle, on real frames -----------------------------------------------------

def test_every_elevation_equals_gmx_gangle_on_every_frame(stored):
    index, traj, reference = stored
    assert len(reference) == 24 and all(len(v) == 21 for v in reference.values())
    g = _groups(index)
    for (a, v, b), alpha in reference.items():
        got = elevation_series(traj, g[a], g[v], g[b], index[(v, "CA")])
        worst = max(abs(x - from_gangle(y)) for x, y in zip(got, alpha))
        # gmx prints three decimals; 0.001 is one unit of the last digit.
        assert worst < 0.001, f"{a}-{v}-{b}: {worst:.4f} degrees from gmx gangle"


def test_every_elevation_equals_gmx_gangle_across_the_periodic_boundary(wrapped):
    """The same frames with the active site split across the triclinic cell
    (fixtures/md/README.md). Every elevation still equals gangle's, which
    made the molecules whole from the run's md.tpr; taken without the
    periodic handling, 489 of the 504 are more than a degree off and 282
    name the wrong face, which is what makes this a test of that handling."""
    index, traj, reference = wrapped
    assert len(reference) == 24 and all(len(v) == 21 for v in reference.values())
    g = _groups(index)
    off = wrong_face = 0
    for (a, v, b), alpha in reference.items():
        got = elevation_series(traj, g[a], g[v], g[b], index[(v, "CA")])
        worst = max(abs(x - from_gangle(y)) for x, y in zip(got, alpha))
        assert worst < 0.001, f"{a}-{v}-{b}: {worst:.4f} degrees from gmx gangle"
        raw = [elevation_deg(*(f.x[g[r]].mean(0) for r in (a, v, b)), f.x[index[(v, "CA")]]) for f in traj]
        off += sum(1 for x, y in zip(raw, alpha) if abs(x - from_gangle(y)) > 1.0)
        wrong_face += sum(1 for x, y in zip(raw, alpha) if x * from_gangle(y) < 0)
    assert off > 400 and wrong_face > 200


def test_the_elevation_names_the_face_the_dihedral_does_in_every_frame(stored):
    """The elevation is signed as the dihedral a-v-b-CA: gmx gangle's
    dihedral has the elevation's sign in every one of the 21 frames of all
    24 angles, taken either way round (b-v-a-CA has the opposite sign). No
    frame is so close to flat that rounding could decide it: the smallest
    elevation here is 0.098 degrees."""
    index, traj, faces = stored
    dihedrals = _printed("lyso_1aki_rep1_gmx_dihedrals.txt")
    assert len(dihedrals) == 48
    for (a, v, b), phi in dihedrals.items():
        sign = 1 if (a, v, b) in faces else -1
        elevation = [sign * from_gangle(x) for x in faces[(a, v, b) if sign == 1 else (b, v, a)]]
        assert all(abs(e) > 0.05 for e in elevation)
        assert all((e > 0) == (p > 0) for e, p in zip(elevation, phi)), f"{a}-{v}-{b}"


def test_the_dihedral_goes_to_pieces_where_the_elevation_does_not(stored):
    """Asp48 sits almost straight out along Asn59's side chain: the angle
    CA-Asn59-Asp48 reaches 179.3 degrees. The dihedral Asn46-Asn59-Asp48-CA
    turns about that line, so it has almost no value there, and gmx gangle
    prints it anywhere from -168.9 to +132.4 degrees over 21 frames; a dead
    band on it would put frame 10 (-64.9) firmly on one face and frame 20
    (+132.4) firmly on the other. The elevation of Asn59's CA out of the
    plane of the angle stays within 11.3 degrees of it, and the polar sine
    calls both frames flat."""
    index, traj, faces = stored
    g = _groups(index)
    ca = index[(59, "CA")]
    axis = [angle_deg(f.x[ca], *(xtc.make_whole(f.x[g[r]], f.box).mean(0) for r in (59, 48)), f.box)
            for f in traj]
    assert max(axis) > 179.0
    phi = _printed("lyso_1aki_rep1_gmx_dihedrals.txt")[(46, 59, 48)]
    assert min(phi) < -160 and max(phi) > 130
    assert phi[10] == -64.892 and phi[20] == 132.382
    # The plan's angle is Asp48-Asn59-Asn46, the other way round: its
    # elevation is minus that of Asn46-Asn59-Asp48.
    elevation = [-from_gangle(x) for x in faces[(48, 59, 46)]]
    theta = _printed("lyso_1aki_rep1_gmx_angles.txt")[(48, 59, 46)]
    assert max(abs(e) for e in elevation) < 11.33
    assert side(polar_sine(theta[10], elevation[10])) == 0 and side(polar_sine(theta[20], elevation[20])) == 0
    # And the tools' own agreement on that dihedral is the worst of all 48:
    # the ill-conditioning shows as single against double precision.
    worst = {}
    for (a, v, b), printed in _printed("lyso_1aki_rep1_gmx_dihedrals.txt").items():
        mine = []
        for f in traj:
            c = [xtc.make_whole(f.x[g[r]], f.box).mean(0) for r in (a, v, b)]
            mine.append(dihedral(c[0], c[1], c[2], f.x[index[(v, "CA")]], f.box))
        worst[(a, v, b)] = max(abs((x - y + 180) % 360 - 180) for x, y in zip(mine, printed))
    ranked = sorted(worst, key=worst.get, reverse=True)
    assert {k[2] for k in ranked[:3]} == {48} and {k[1] for k in ranked[:3]} == {59}
    assert worst[ranked[0]] > 0.0015 and worst[ranked[3]] < 0.001


# --- geometry -------------------------------------------------------------------------------

def test_clockwise_seen_from_the_ca_is_positive():
    v, a, b = np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    # Seen from +z, x runs anticlockwise to y.
    assert elevation_deg(a, v, b, np.array([0, 0, 1.0])) == pytest.approx(-90.0)
    assert elevation_deg(a, v, b, np.array([0, 0, -1.0])) == pytest.approx(90.0)
    assert dihedral(a, v, b, np.array([0.3, 0.2, -1.0])) > 0
    assert face_name(1) == "clockwise" and face_name(-1) == "anticlockwise" and face_name(0) == "flat"


def test_a_partner_turned_to_the_other_face_keeps_its_angle_and_changes_sign():
    # The construction test_angles.py uses to show what an angle cannot see.
    v, b, a = np.zeros(3), np.array([0.5, 0.0, 0.0]), np.array([0.2, 0.3, 0.1])
    turned = np.array([a[0], -a[1], -a[2]])
    ca = np.array([-0.1, 0.1, 0.25])
    assert angle_deg(turned, v, b) == pytest.approx(angle_deg(a, v, b), abs=1e-12)
    before, after = elevation_deg(a, v, b, ca), elevation_deg(turned, v, b, ca)
    assert before * after < 0
    assert side(polar_sine(angle_deg(a, v, b), before)) == -side(polar_sine(angle_deg(a, v, b), after)) != 0


def test_the_polar_sine_is_the_volume_of_the_unit_arms():
    """sin(angle) x sin(elevation) is the triple product of the three arms
    over their lengths; relabelling the arms changes only its sign; and when
    it is at least sin FLAT_DEG, every arm stands at least FLAT_DEG out of
    the plane of the other two, which is the statement the band rests on."""
    rng = np.random.default_rng(20260929)
    for _ in range(2000):
        u, w, r = rng.normal(size=(3, 3))
        v = np.zeros(3)
        p = polar_sine(angle_deg(u, v, w), elevation_deg(u, v, w, r))
        assert p == pytest.approx(np.dot(np.cross(w, u), r) / (np.linalg.norm(u) * np.linalg.norm(w)
                                                              * np.linalg.norm(r)), abs=1e-12)
        assert polar_sine(angle_deg(w, v, u), elevation_deg(w, v, u, r)) == pytest.approx(-p, abs=1e-12)
        assert polar_sine(angle_deg(w, v, r), elevation_deg(w, v, r, u)) == pytest.approx(p, abs=1e-12)
        if abs(p) >= FLAT:
            for x, y, z in ((u, w, r), (w, r, u), (r, u, w)):
                assert abs(elevation_deg(x, v, y, z)) >= FLAT_DEG - 1e-9


def test_three_arms_bunched_together_are_flat_though_each_is_off_the_others_plane():
    """Three arms within 5 degrees of one line: each stands about 7.5
    degrees out of the plane of the other two, but a turn of any one by a
    few degrees makes the four points flat. The polar sine is small, and
    the frame is on no face."""
    tilt = math.radians(5)
    arms = [np.array([math.sin(tilt) * math.cos(k), math.sin(tilt) * math.sin(k), math.cos(tilt)])
            for k in (0.0, 2 * math.pi / 3, 4 * math.pi / 3)]
    v = np.zeros(3)
    assert abs(elevation_deg(arms[0], v, arms[1], arms[2])) > 7.0
    assert side(polar_sine(angle_deg(arms[0], v, arms[1]), elevation_deg(arms[0], v, arms[1], arms[2]))) == 0


def test_ca_on_the_line_through_v_and_b_is_flat_not_noise():
    """Where the dihedral a-v-b-CA has no value: CA on the line v-b. The
    elevation is 0 there and a hair's move of CA off the line changes it by
    a hair; the dihedral jumps across the circle."""
    v, b, a = np.zeros(3), np.array([0.4, 0.0, 0.0]), np.array([0.1, 0.3, 0.1])
    on_line = np.array([-0.3, 0.0, 0.0])
    assert elevation_deg(a, v, b, on_line) == pytest.approx(0.0, abs=1e-12)
    up, down = on_line + np.array([0, 0, 1e-4]), on_line - np.array([0, 0, 1e-4])
    assert abs(elevation_deg(a, v, b, up)) < 0.05 and abs(elevation_deg(a, v, b, down)) < 0.05
    assert abs((dihedral(a, v, b, up) - dihedral(a, v, b, down) + 180) % 360 - 180) > 100
    assert side(polar_sine(angle_deg(a, v, b), elevation_deg(a, v, b, up))) == 0


def test_a_straight_angle_has_no_plane_and_is_flat():
    v, a, b, ca = np.zeros(3), np.array([-0.3, 0, 0]), np.array([0.4, 0, 0]), np.array([0.1, 0.2, 0.2])
    assert angle_deg(a, v, b) == pytest.approx(180.0)
    assert polar_sine(angle_deg(a, v, b), elevation_deg(a, v, b, ca)) == pytest.approx(0.0, abs=1e-12)


def test_arms_are_taken_to_their_nearest_periodic_image():
    box = np.diag([3.0, 3.0, 3.0])
    v, a, b, ca = np.zeros(3), np.array([0.3, 0, 0]), np.array([0, 0.4, 0]), np.array([0.1, 0.1, 0.25])
    whole = elevation_deg(a, v, b, ca, box)
    for shift in ([3.0, 0, 0], [0, -3.0, 0], [0, 0, 3.0]):
        assert elevation_deg(a, v, b, ca + np.array(shift), box) == pytest.approx(whole, abs=1e-9)
    # Taken as stored, the CA a box length away reads as another angle altogether.
    assert abs(elevation_deg(a, v, b, ca + np.array([0, 0, 3.0])) - whole) > 20


def test_a_group_split_across_the_boundary_is_made_whole_before_its_centre():
    class F:
        pass
    f = F()
    f.box = np.diag([3.0, 3.0, 3.0])
    f.x = np.array([[0.0, 0, 0],      # the vertex
                    [0.05, 0.3, 0],   # a's first oxygen
                    [2.95, 0.3, 0],   # a's second, at x = -0.05, wrapped to the far side
                    [0.4, 0, 0],      # b
                    [0.0, 0.0, 0.2]])  # the vertex's CA
    (e,) = elevation_series([f], [1, 2], [0], [3], 4)
    assert e == pytest.approx(elevation_deg(np.array([0.0, 0.3, 0]), f.x[0], f.x[3], f.x[4]), abs=1e-9)
    assert e == pytest.approx(90.0, abs=1e-9)


# --- the band and the verdicts --------------------------------------------------------------

def test_the_band_is_half_the_moved_threshold():
    # A partner counted on opposite faces in two frames has turned at least
    # 2 x FLAT_DEG across the flat arrangement: MOVED_DEG, the angle table's
    # own threshold for calling an angle moved.
    assert FLAT_DEG == RESOLVE_DEG == MOVED_DEG / 2
    assert FLAT == pytest.approx(math.sin(math.radians(7.5)))


def test_the_band_edge_is_on_a_face():
    edge = math.degrees(math.asin(FLAT))
    assert side(polar_sine(90.0, edge)) == 1 and side(polar_sine(90.0, -edge)) == -1
    assert side(polar_sine(90.0, edge - 1e-6)) == 0


def test_fractions_count_every_frame_and_the_flat_ones_as_neither():
    name, kept, other = face_fractions("rep1", [90.0] * 5, [-40.0, -40.0, 0.0, 3.0, 40.0], crystal_side=-1)
    assert (name, kept, other) == ("rep1", 0.4, 0.2)
    assert math.isnan(face_fractions("rep2", [], [], -1)[1])


def _face(*replicas, crystal=-0.5):
    return Face("Asp20–His10–Ser30", -30.0, crystal,
                [(f"rep{i + 1}", k, o) for i, (k, o) in enumerate(replicas)])


@pytest.mark.parametrize("face,verdict", [
    (_face((1.0, 0.0), crystal=0.05), FLAT_IN_CRYSTAL),
    (_face((1.0, 0.0)), "one replica"),
    (_face((1.0, 0.0), (float("nan"), float("nan"))), "no frames"),
    (_face((0.95, 0.0), (0.85, 0.05)), "kept its face"),
    (_face((0.05, 0.9), (0.0, 0.95)), "changed face"),
    (_face((0.1, 0.05), (0.0, 0.1)), "went flat"),
    (_face((1.0, 0.0), (0.2, 0.3)), "replicas disagree"),
    (_face((0.3, 0.1), (0.1, 0.7)), "replicas disagree"),
    (_face((0.6, 0.0), (0.7, 0.1)), "partial"),
])
def test_verdicts(face, verdict):
    assert face_verdict(face) == verdict


# --- the plan -------------------------------------------------------------------------------

def _atom(serial, name, resname, resnr, x, y, z):
    return (f"ATOM  {serial:5d} {name:<4} {resname:>3} A{resnr:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           {name[0]}")


def _triad(his_ca_z=1.5, his_ca=True):
    """test_angles.py's triad in Angstrom, His10 the vertex with Asp20 and
    Ser30 its partners, all functional atoms in the plane z = 0, with
    His10's CA lifted out of it by `his_ca_z`."""
    lines = [_atom(2, "ND1", "HIS", 10, 1.0, 0, 0), _atom(3, "NE2", "HIS", 10, 1.0, 2.0, 0),
             _atom(4, "CA", "ASP", 20, 6.0, 0, 0), _atom(5, "OD1", "ASP", 20, 5.0, 0, 0),
             _atom(6, "OD2", "ASP", 20, 5.0, 2.0, 0),
             _atom(7, "CA", "SER", 30, 0.0, 7.5, 0), _atom(8, "OG", "SER", 30, 1.0, 6.0, 0),
             _atom(9, "CA", "GLY", 40, 1.0, -3.0, 0)]
    if his_ca:
        lines.insert(0, _atom(1, "CA", "HIS", 10, 0.0, 0.0, his_ca_z))
    return "\n".join(lines) + "\nEND\n"


CATALYTIC = [(10, "HIS"), (20, "ASP"), (30, "SER")]


def test_the_crystal_face_is_taken_against_the_vertex_ca():
    (angle,) = plan(read_pdb(_triad()), CATALYTIC).angles
    assert angle.label == "Asp20–His10–Ser30"
    # Arms from His10's ring centre (1, 1, 0): Asp20 along +x, Ser30 along
    # +y, CA at (-1, -1, 1.5). Seen from the CA, above the plane, +x runs
    # anticlockwise to +y.
    expected = elevation_deg(np.array([5.0, 1, 0]), np.array([1.0, 1, 0]), np.array([1.0, 6, 0]),
                             np.array([0.0, 0, 1.5]))
    assert angle.crystal_elevation_deg == pytest.approx(expected, abs=1e-12)
    assert expected == pytest.approx(-math.degrees(math.atan2(1.5, math.sqrt(2))))
    assert angle.arm_selection() == "cog of (resnr 10 and name ND1 NE2) plus cog of (resnr 10 and name CA)"


def test_the_crystal_face_equals_the_frames_formula_on_24_real_angles(tmp_path):
    """The plan's pure-Python elevation (no numpy, like its angles) against
    elevation_deg on the same crystal points, for every angle a structure
    of lysozyme gives."""
    gro = _unzip(tmp_path, "lyso_1aki_res1-59.gro.gz")
    atoms = [Atom("A", r, n, name, tuple(float(c) * 10 for c in xyz)) for r, n, name, xyz in _gro_atoms(gro)]
    p = plan(atoms, [(r, next(a.resname for a in atoms if a.resnr == r)) for r in MCSA_ORDER])
    assert len(p.angles) == 24 and p.faces == p.angles
    pos = {(a.resnr, a.name): np.array(a.xyz) for a in atoms}
    for t in p.angles:
        c = [np.mean([pos[(s.resnr, n)] for n in s.atoms], axis=0) for s in (t.a, t.v, t.b)]
        assert t.crystal_elevation_deg == pytest.approx(elevation_deg(*c, pos[(t.v.resnr, "CA")]), abs=1e-9)


def test_a_vertex_without_a_ca_gets_no_face_and_a_note():
    p = plan(read_pdb(_triad(his_ca=False)), CATALYTIC)
    assert len(p.angles) == 1 and p.faces == []
    assert any(n.startswith("His10 has no CA in the structure") for n in p.notes)
    assert not any(" -g1 plane " in line for line in commands(p, ["rep1"]))


# --- the GROMACS route ----------------------------------------------------------------------

def test_one_plane_vector_call_per_replica_measures_every_face():
    p = plan(read_pdb(_triad()), CATALYTIC)
    lines = [line for line in commands(p, ["rep1", "rep2"]) if " -g1 plane " in line]
    assert len(lines) == 2
    assert lines[0] == ("$GMX gangle -s rep1/md.tpr -f rep1/md.xtc -g1 plane -group1 "
                        f"'{p.angles[0].selection()}' -g2 vector -group2 '{p.angles[0].arm_selection()}' "
                        "-oav rep1/faces.xvg")


def test_gangle_face_output_is_read_with_the_angles_and_a_stale_one_is_refused(tmp_path):
    p = plan(read_pdb(_triad()), CATALYTIC)
    rep = tmp_path / "rep1"
    rep.mkdir()
    (rep / "angles.xvg").write_text("@ title\n0.0 90.0\n0.5 90.0\n1.0 90.0\n1.5 90.0\n")
    # The crystal is anticlockwise (elevation -46.7): gangle's angle from
    # the normal is 90 minus the elevation, so 136.7 is the crystal's face,
    # 43.3 the other and 90 flat.
    (rep / "faces.xvg").write_text("@ title\n0.0 136.7\n0.5 136.7\n1.0 90.0\n1.5 43.3\n")
    (face,) = gromacs_faces(p, [rep])
    assert face.label == "Asp20–His10–Ser30" and face.crystal_side == -1
    assert face.per_replica == [("rep1", 0.5, 0.25)]
    (rep / "faces.xvg").write_text("0.0 136.7\n0.5 136.7\n")
    with pytest.raises(AnalyzeError, match="2 frames"):
        gromacs_faces(p, [rep])
    (rep / "faces.xvg").write_text("0.0 136.7 1.0\n")
    with pytest.raises(AnalyzeError, match="2 columns of which face"):
        gromacs_faces(p, [rep])
    (rep / "faces.xvg").unlink()
    with pytest.raises(AnalyzeError, match="faces.xvg does not exist: run analyze.sh again"):
        gromacs_faces(p, [rep])


@pytest.mark.parametrize("which", ["stored", "wrapped"])
def test_both_routes_give_the_same_faces_on_real_frames(tmp_path, which):
    """The native route measured from a fixture's frames, against the
    GROMACS route reading what gmx gangle printed for them. The crystal is
    the stored fixture's own structure on both routes (for the wrapped
    frames too, whose .gro has the same atoms split across the box)."""
    if which == "stored":
        start, frames, faces_txt, angles_txt = ("lyso_1aki_res1-59.gro.gz", "lyso_1aki_res1-59.xtc",
                                                "lyso_1aki_rep1_gmx_faces.txt", "lyso_1aki_rep1_gmx_angles.txt")
        crystal = start
    else:
        start, frames, faces_txt, angles_txt = ("lyso_1aki_res1-59_water_wrapped.gro.gz",
                                                "lyso_1aki_res1-59_water_wrapped.xtc",
                                                "lyso_1aki_rep1_gmx_faces_wrapped.txt",
                                                "lyso_1aki_rep1_gmx_angles_wrapped.txt")
        crystal = "lyso_1aki_res1-59_water.gro.gz"
    (tmp_path / "em.gro").write_bytes(gzip.decompress((MD / start).read_bytes()))
    whole = _unzip(tmp_path, crystal)
    protein = [Atom("A", r, n, name, tuple(float(c) * 10 for c in xyz))
               for r, n, name, xyz in _gro_atoms(whole) if n != "SOL"]
    rep = tmp_path / "rep1"
    rep.mkdir()
    (rep / "md.xtc").write_bytes((MD / frames).read_bytes())
    p = plan(protein, [(r, next(a.resname for a in protein if a.resnr == r)) for r in MCSA_ORDER])
    assert len(p.faces) == 24
    native = measure_native(tmp_path, p, [rep])[6]

    faces, angles = _printed(faces_txt), _printed(angles_txt)
    for name, printed in (("faces.xvg", faces), ("angles.xvg", angles)):
        (rep / name).write_text("".join(
            f"{t * 0.5:.1f} " + " ".join(f"{printed[(a.a.resnr, a.v.resnr, a.b.resnr)][t]:.3f}" for a in p.angles)
            + "\n" for t in range(21)))
    via_gmx = gromacs_faces(p, [rep])
    assert via_gmx == native
    kept = [f.per_replica[0][1] for f in native if f.crystal_side]
    assert kept and any(k < 1.0 for k in kept) and any(k == 1.0 for k in kept)
    one = Analysis("1AKI", None, "test", p, [], None, None, None, [], None, native)
    other = Analysis("1AKI", None, "test", p, [], None, None, None, [], None, via_gmx)
    assert face_section(one) == face_section(other)
    assert len([line for line in face_section(one) if line.startswith("| ") and "–" in line]) == 24


# --- the report and the exit code -----------------------------------------------------------

def _ar1(rng, n, mu, sd, phi=0.5):
    x, out = mu, []
    for _ in range(n):
        x = mu + phi * (x - mu) + rng.gauss(0, sd * math.sqrt(1 - phi * phi))
        out.append(x)
    return out


def _fake_run(tmp_path, elevations, distance_phi=0.5, n=4000):
    """A finished run as analyze.sh leaves it, for the triad above: the
    distances and the angle hold at their crystal values, and each
    replica's faces.xvg holds `elevations[r]` (degrees; its frames cycle
    through the list)."""
    rng = random.Random(1)
    (tmp_path / "caterva-setup.json").write_text(json.dumps({"pdb": "9XYZ", "chain": "A"}))
    (tmp_path / "protein.pdb").write_text(_triad())
    p = plan(read_pdb(_triad()), CATALYTIC)
    for r, cycle in enumerate(elevations, start=1):
        d = tmp_path / f"rep{r}"
        d.mkdir()
        (d / "md.xtc").write_text("")
        (d / "md.tpr").write_text("")
        cols = [_ar1(rng, n, q.crystal_nm, 0.005, distance_phi) for q in p.pairs]
        (d / "catalytic.xvg").write_text("".join(
            f"{i * 0.001:.3f} " + " ".join(f"{c[i]:.5f}" for c in cols) + "\n" for i in range(n)))
        ang = _ar1(rng, n, p.angles[0].crystal_deg, 0.5)
        (d / "angles.xvg").write_text("".join(f"{i * 0.5:.1f} {v:.3f}\n" for i, v in enumerate(ang)))
        (d / "faces.xvg").write_text("".join(f"{i * 0.5:.1f} {90.0 - cycle[i % len(cycle)]:.3f}\n"
                                             for i in range(n)))
        (d / "rmsf.xvg").write_text("10 0.05\n20 0.05\n30 0.06\n40 0.20\n")
        (d / "water.xvg").write_text("0.0 1 0 2\n0.5 1 1 2\n")
    (tmp_path / "water_start.xvg").write_text("0.0 1 0 2\n")
    return tmp_path


def _catalytic(pdb, chain):
    return CATALYTIC, "a test mapping"


def _section(out):
    return out.split("## Which face of the vertex its partners are on")[1].split("\n## ")[0]


def test_replicas_that_keep_the_crystal_face(tmp_path, capsys):
    d = _fake_run(tmp_path, [[-45.0], [-40.0, -50.0]])
    assert main([str(d), "--no-run"], catalytic=_catalytic) == 0
    out = capsys.readouterr().out
    row = next(line for line in _section(out).splitlines() if line.startswith("| Asp20–His10–Ser30"))
    assert row == "| Asp20–His10–Ser30 | -46.7 | anticlockwise | 1.00 (0.00) | 1.00 (0.00) | kept its face |"
    # After the angles, before the water; and the angle section points here.
    assert out.index("## Angles between catalytic groups") < out.index("## Which face of the vertex") \
        < out.index("## Water at the catalytic residues")
    assert "signed dihedral" not in out.split("## Not measured")[1]
    assert "went flat, flat in at least 80%" in _section(out)
    assert "`7.5°` is half the 15° angle threshold" in _section(out)


def test_a_partner_on_the_other_face_is_called_changed(tmp_path, capsys):
    # A frame at 3 degrees of elevation is flat (sin 90 x sin 3 < sin 7.5)
    # and counts for neither face.
    d = _fake_run(tmp_path, [[40.0, 40.0, 40.0, 40.0, 3.0], [45.0]])
    main([str(d), "--no-run"], catalytic=_catalytic)
    row = next(line for line in _section(capsys.readouterr().out).splitlines() if line.startswith("| Asp20"))
    assert row.endswith("| 0.00 (0.80) | 0.00 (1.00) | changed face |")


def test_the_verdict_waits_for_the_distances(tmp_path, capsys):
    """Like the rotamers and water, a face has no error bar of its own: it
    is a result only when the distances are."""
    d = _fake_run(tmp_path, [[-45.0], [-45.0]], distance_phi=0.995, n=400)
    assert main([str(d), "--no-run"], catalytic=_catalytic) == EXIT_NOT_A_RESULT
    assert "| (kept its face, not yet a result) |" in _section(capsys.readouterr().out)


def test_a_flat_crystal_has_no_face_to_keep(tmp_path, capsys):
    d = _fake_run(tmp_path, [[-45.0], [-45.0]])
    (d / "protein.pdb").write_text(_triad(his_ca_z=0.0))
    main([str(d), "--no-run"], catalytic=_catalytic)
    row = next(line for line in _section(capsys.readouterr().out).splitlines() if line.startswith("| Asp20"))
    assert row == f"| Asp20–His10–Ser30 | +0.0 | flat | n/a | n/a | {FLAT_IN_CRYSTAL} |"


def test_a_run_analysed_before_the_faces_existed_is_refused_by_name(tmp_path, capsys):
    d = _fake_run(tmp_path, [[-45.0], [-45.0]])
    (d / "rep2" / "faces.xvg").unlink()
    assert main([str(d), "--no-run"], catalytic=_catalytic) == 3
    assert "rep2/faces.xvg does not exist: run analyze.sh again" in capsys.readouterr().err


def test_no_angle_means_no_face(tmp_path, capsys):
    d = _fake_run(tmp_path, [[-45.0], [-45.0]])
    far = _triad().replace("   1.000   6.000", "   1.000   9.000")   # Ser30's OG out of contact
    (d / "protein.pdb").write_text(far)
    for rep in ("rep1", "rep2"):
        (d / rep / "angles.xvg").unlink()
        (d / rep / "faces.xvg").unlink()
    main([str(d), "--no-run"], catalytic=_catalytic)
    assert "None measured: there is no angle above to take the faces of." in _section(capsys.readouterr().out)
