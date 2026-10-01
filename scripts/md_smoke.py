"""Run a `caterva md` setup through every GROMACS stage, capped to seconds.

    make md-smoke                      # gmx on PATH
    make md-smoke GMX=/path/to/gmx

Writes a setup for hen lysozyme (PDB 1AKI: small, one chain, the standard
GROMACS test protein), caps minimisation at 500 steps and each dynamics
stage at 200, runs run.sh with two replicas, and fails unless every stage of
every replica wrote coordinates and `--summarise` reads the result.
The inputs and topology are the real ones; only the lengths are cut. CI
runs exactly this, so a failure there reproduces here.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "md-smoke"


def _distance_rows(text: str) -> dict:
    """pair -> simulated mean (nm) from an ANALYSIS.md catalytic-geometry table.

    Only that section is read. The hydrogen-bond table below it has rows of
    the same shape (`| Asp48-Ser50 | 1 | 1.00 |`), and reading the whole file
    let an occupancy of 1.00 overwrite a 0.30 nm distance: the "0.697 nm
    disagreement" CI reported on 2026-09-29 was this parser, not the geometry.
    """
    section = text.split("## Catalytic geometry", 1)[-1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        m = re.match(r"\|\s*([A-Z][a-z]{2}\d+\S*[A-Z][a-z]{2}\d+)\s*\|\s*[\d.]+\s*\|\s*([\d.]+)", line)
        if m:
            rows[m.group(1)] = float(m.group(2))
    return rows


def _flexibility_rows(text: str) -> dict:
    """replica -> (pocket, rest) mean Calpha RMSF (nm) from the flexibility table.

    Compared across the two routes since 2026-09-29. Before then the GROMACS
    route fitted to the wrapped tpr coordinates and, on lysozyme, put the
    RMSF of residues 66-74 about 10% above the native route's; nothing
    compared them, so the gap was recorded as unexplained rather than caught.
    """
    section = text.split("## Active-site flexibility", 1)[-1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        m = re.match(r"\|\s*(rep\w+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|", line)
        if m:
            rows[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return rows


def _rotamer_rows(text: str) -> dict:
    """residue -> per-replica fractions in the starting chi1 well."""
    section = text.split("## Catalytic side-chain rotamers", 1)[-1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        m = re.match(r"\|\s*([A-Z][a-z]{2}\d+)\s*\|\s*-?\d+ \([^)]*\)\s*\|(.*)\|[^|]*\|\s*$", line)
        if m:
            rows[m.group(1)] = tuple(float(v) for v in m.group(2).split("|") if v.strip())
    return rows


def _table_rows(text: str, heading: str) -> dict:
    """First cell -> the other cells, for every body row of the table under
    one heading. Only that section is read, for the reason _distance_rows
    gives: tables further down have rows of the same shape."""
    section = text.split(heading, 1)[-1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells and re.match(r"[A-Z][a-z]{2}\d+", cells[0]):
            rows[cells[0]] = cells[1:]
    return rows


def _angle_rows(text: str) -> dict:
    """angle -> (crystal, each replica's mean, mean across replicas), degrees.

    Compared across the routes since angles were added (2026-09-29): gmx
    gangle and the native reader agreed to 0.0006 degrees per frame on both
    10 ps lysozyme replicas, so the printed means (0.1 degree) may differ by
    one unit of their last digit and no more.
    """
    out = {}
    for label, cells in _table_rows(text, "## Angles between catalytic groups").items():
        numbers = []
        for c in cells:
            m = re.match(r"-?\d+\.\d", c)
            if not m:  # the confidence interval ("± 35.0") ends the numbers compared
                break
            numbers.append(float(m.group(0)))
        out[label] = tuple(numbers)
    return out


def _face_rows(text: str) -> dict:
    """angle -> every cell of its row in the face table: how far the crystal
    is from flat, the crystal's face, each replica's fractions on it and on
    the other face (for an angle in plane in the crystal, on the clockwise
    face, the anticlockwise face and flat), and the verdict. Both routes
    render a row through caterva.analyze.faces.face_cells and face_verdict,
    so a row is the same string on both whenever the frames are judged
    alike. The two routes measure the same
    elevation (gmx gangle -g1 plane -g2 vector against the native one, to
    0.00061 degrees per frame on both 10 ps lysozyme replicas, 2026-09-29)
    and decide each frame's face the same way, so the rows must be
    identical. A frame whose polar sine sat within gangle's rounding of the
    band edge could split them; on those replicas the nearest was 0.00099
    from it, a hundred times the rounding."""
    return _table_rows(text, "## Which face of the vertex its partners are on")


#: Frames the smoke run keeps per replica: 200 steps, one every 50.
SMOKE_FRAMES = 5


def _faces_agree(native: dict, gromacs: dict) -> tuple:
    """(agree, rows that differed by one edge frame).

    The GROMACS route rebuilds each frame's polar sine from gmx gangle's
    output, printed to 0.001 degree, so it differs from the native value by
    about 1e-5. A frame whose polar sine sits that close to the band edge
    lands on opposite sides on the two routes. On the 10 ps lysozyme
    replicas the nearest frame was 0.00099 from the edge, but CI makes a new
    trajectory every run, and with about 1.3 frames per unit of polar sine
    near the edges a split is expected in well under 1% of runs (the review
    of this check, 2026-09-30). So: every row identical, except at most one
    row in which one frame of one replica is flat on one route and on a
    face on the other (`_one_edge_frame`). A real disagreement between the
    routes moves more than one frame, moves a frame from one face to the
    other, or differs in more than one row.

    The crystal's two cells (how far it is from flat, and its face) must be
    identical: both routes take them from the same analysis plan, built from
    the crystal's coordinates, not from either route's frames. Only the
    verdict, the last cell, may differ in its words, since one frame can move
    it across a threshold.

    The fractions are read out of each cell, since a replica's cell holds
    two or three of them ("1.00 (0.00)", or "clockwise 0.29, anticlockwise
    0.00, flat 0.71" in plane in the crystal) and is not one number. Until
    2026-09-30 a cell was compared only when it parsed as a single float,
    so in the one row allowed to differ no replica's fractions were compared
    at all. Until 2026-10-01 each number in each cell of that row could be a
    frame off, so both replicas could differ, and a frame could be on the
    clockwise face on one route and the anticlockwise one on the other: a
    sign flip across the band, not rounding at its edge."""
    if not native or native.keys() != gromacs.keys():
        return False, 0
    differing = [k for k in native if native[k] != gromacs[k]]
    if len(differing) > 1:
        return False, len(differing)
    for k in differing:
        x, y = native[k], gromacs[k]
        if len(x) != len(y) or len(x) < 4 or x[:2] != y[:2]:
            return False, 1
        cells = [(a, b) for a, b in zip(x[2:-1], y[2:-1]) if a != b]
        if len(cells) != 1 or not _one_edge_frame(*cells[0]):
            return False, 1
    return True, len(differing)


def _one_edge_frame(native: str, gromacs: str) -> bool:
    """True when two renderings of one replica's cell differ by one frame
    that is flat on one route and on a face on the other, and in nothing
    else. A cell with a crystal face is "k (o)", the fractions on the
    crystal's face and on the other: exactly one of the two moves, by one
    frame. A cell in plane in the crystal is "clockwise a, anticlockwise b,
    flat c": flat moves by one frame and exactly one face by the same frame
    the other way. A frame that changes face changes both faces' fractions,
    and is refused either way."""
    if _FRACTION.sub("#", native) != _FRACTION.sub("#", gromacs):
        return False
    xs = [float(v) for v in _FRACTION.findall(native)]
    ys = [float(v) for v in _FRACTION.findall(gromacs)]
    frame, rounding = 1 / SMOKE_FRAMES, 0.006
    moved = [i for i, (a, b) in enumerate(zip(xs, ys)) if abs(b - a) > rounding]
    if not all(abs(abs(ys[i] - xs[i]) - frame) <= rounding for i in moved):
        return False
    if len(xs) == 2:
        return len(moved) == 1
    if len(xs) == 3:
        return (len(moved) == 2 and 2 in moved
                and (ys[2] - xs[2]) * (ys[moved[0]] - xs[moved[0]]) < 0)
    return False


#: A number as the face table prints one: a fraction ("0.29") or the
#: crystal's distance from flat ("+2.1").
_FRACTION = re.compile(r"[-+]?\d+\.\d+")


def _water_rows(text: str) -> dict:
    """residue -> every cell of its row: atoms, count at start, per replica
    mean and fraction, verdict. Water counts are integers on both routes, so
    the rows must be identical, not close."""
    return _table_rows(text, "## Water at the catalytic residues")


def main() -> int:
    gmx = os.environ.get("GMX", "gmx")
    if shutil.which(gmx) is None and not Path(gmx).exists():
        print(f"GROMACS not found ({gmx!r}): set GMX=/path/to/gmx. Could not run -- not a pass.")
        return 2
    shutil.rmtree(OUT, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "caterva.app", "md", "--pdb", "1AKI",
                    "--out", str(OUT), "--ns", "0.001", "--replicas", "2"], check=True, cwd=ROOT)
    em = OUT / "em.mdp"
    em.write_text(re.sub(r"^nsteps\s*=\s*50000$", "nsteps          = 500", em.read_text(), flags=re.M))
    # A frame every 50 steps, so the 200-step production run keeps five and
    # RMSF has something to fluctuate over. At the setup's own interval it
    # kept only frame 0, where the native route rightly measures no RMSF and
    # gmx rmsf printed 0.0001 nm of rounding; nothing compared the two.
    md = OUT / "md.mdp"
    md.write_text(re.sub(r"^nstxout-compressed\s*=\s*\d+$", "nstxout-compressed = 50",
                         md.read_text(), flags=re.M))
    run = OUT / "run.sh"
    run.write_text(re.sub(r'(mdrun -deffnm "\$d/(?:nvt|npt|md)") \$MDRUN_FLAGS$',
                          r"\1 $MDRUN_FLAGS -nsteps 200", run.read_text(), flags=re.M))
    subprocess.run(["bash", str(run)], check=True, env={**os.environ, "GMX": gmx})
    stages = ["em.gro"] + [f"rep{r}/{s}.gro" for r in (1, 2) for s in ("nvt", "npt", "md")] \
        + ["rep1/rmsd.xvg", "rep2/rmsd.xvg"]
    missing = [s for s in stages if not (OUT / s).exists() or not (OUT / s).stat().st_size]
    if missing:
        print(f"FAIL: no coordinates from {missing}")
        return 1
    # The summary must run on real GROMACS output. 200 steps cannot converge,
    # so the expected verdict is "not a result" -- which is the point.
    code = subprocess.run([sys.executable, "-m", "caterva.app", "md", "--summarise", str(OUT)],
                          cwd=ROOT).returncode
    if code not in (0, 4):
        print(f"FAIL: --summarise exited {code} on real output")
        return 1
    # And the enzyme analysis, which fetches lysozyme's catalytic residues
    # (M-CSA via `caterva prepare`), twice: measured by Caterva from the
    # trajectories it reads itself, and by gmx distance, rmsf, angle, gangle
    # and select. The distance, flexibility, rotamer, angle, face and water
    # tables must agree, so this job checks the native reader and geometry
    # against GROMACS on every run.
    tables, flex, rot, ang, wet, face = {}, {}, {}, {}, {}, {}
    for route, extra in (("native", []), ("gromacs", ["--gromacs"])):
        code = subprocess.run([sys.executable, "-m", "caterva.app", "analyze", str(OUT), *extra],
                              cwd=ROOT, env={**os.environ, "GMX": gmx}).returncode
        if code not in (0, 4):
            print(f"FAIL: caterva analyze ({route}) exited {code} on real output")
            return 1
        text = (OUT / "ANALYSIS.md").read_text()
        tables[route] = _distance_rows(text)
        flex[route] = _flexibility_rows(text)
        rot[route] = _rotamer_rows(text)
        ang[route] = _angle_rows(text)
        wet[route] = _water_rows(text)
        face[route] = _face_rows(text)
    if not (OUT / "rep2" / "catalytic.xvg").exists():
        print("FAIL: caterva analyze --gromacs wrote no catalytic.xvg")
        return 1
    if not tables["native"] or tables["native"].keys() != tables["gromacs"].keys():
        print(f"FAIL: native and GROMACS analyses list different pairs: "
              f"{sorted(tables['native'])} vs {sorted(tables['gromacs'])}")
        return 1
    worst = max(abs(tables["native"][k] - tables["gromacs"][k]) for k in tables["native"])
    if worst > 0.002:
        print(f"FAIL: native and GROMACS catalytic distances differ by up to {worst:.4f} nm")
        return 1
    print(f"OK: native and GROMACS agree on {len(tables['native'])} catalytic distances "
          f"(largest difference {worst:.4f} nm).")
    if not flex["native"] or flex["native"].keys() != flex["gromacs"].keys():
        print(f"FAIL: native and GROMACS flexibility tables list different replicas: "
              f"{sorted(flex['native'])} vs {sorted(flex['gromacs'])}")
        return 1
    worst_f = max(abs(a - b) for k in flex["native"]
                  for a, b in zip(flex["native"][k], flex["gromacs"][k]))
    if worst_f > 0.0005:
        print(f"FAIL: native and GROMACS mean RMSF differ by up to {worst_f:.4f} nm")
        return 1
    print(f"OK: native and GROMACS agree on mean Calpha RMSF for {len(flex['native'])} replicas "
          f"(largest difference {worst_f:.4f} nm).")
    if not rot["native"] or rot["native"] != rot["gromacs"]:
        print(f"FAIL: native and GROMACS chi1 rotamer tables differ: {rot['native']} vs {rot['gromacs']}")
        return 1
    print(f"OK: native and GROMACS agree on the chi1 rotamers of {len(rot['native'])} catalytic residues.")
    # Angles between catalytic groups: gmx gangle against the native
    # centres and nearest-image arms. Lysozyme's six catalytic groups give
    # 24 angles under the contact cutoff, so an empty table is a failure.
    if not ang["native"] or ang["native"].keys() != ang["gromacs"].keys():
        print(f"FAIL: native and GROMACS angle tables list different angles: "
              f"{sorted(ang['native'])} vs {sorted(ang['gromacs'])}")
        return 1
    if any(len(ang["native"][k]) != len(ang["gromacs"][k]) for k in ang["native"]):
        print(f"FAIL: native and GROMACS angle rows have different shapes: {ang['native']} vs {ang['gromacs']}")
        return 1
    worst_a = max(abs(a - b) for k in ang["native"] for a, b in zip(ang["native"][k], ang["gromacs"][k]))
    if worst_a > 0.1 + 1e-9:
        print(f"FAIL: native and GROMACS angles between catalytic groups differ by up to {worst_a:.1f} degrees")
        return 1
    print(f"OK: native and GROMACS agree on {len(ang['native'])} angles between catalytic groups "
          f"(largest difference in the printed means {worst_a:.1f} degrees; the table prints 0.1).")
    # Which face of each angle's vertex its partners are on: gmx gangle's
    # plane-vector angle against the native elevation. One row per angle,
    # so an empty table is a failure here too.
    faces_ok, edge_rows = _faces_agree(face["native"], face["gromacs"])
    if not faces_ok:
        print(f"FAIL: native and GROMACS face tables differ: {face['native']} vs {face['gromacs']}")
        return 1
    print(f"OK: native and GROMACS agree on which face of the vertex the partners of {len(face['native'])} "
          "angles are on, row for row"
          + (f", except one frame on the band edge in {edge_rows} row (gangle prints 0.001 degree)."
             if edge_rows else "."))
    # Water at each catalytic residue: gmx select against the native count.
    if not wet["native"] or wet["native"] != wet["gromacs"]:
        print(f"FAIL: native and GROMACS water tables differ: {wet['native']} vs {wet['gromacs']}")
        return 1
    print(f"OK: native and GROMACS agree on the water at {len(wet['native'])} catalytic residues, "
          "count for count.")
    print("OK: minimisation, then NVT, NPT, production and RMSD for two replicas, the summary, "
          "and the enzyme analysis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
