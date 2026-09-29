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
    # trajectories it reads itself, and by gmx distance / gmx rmsf. The two
    # distance tables must agree, so this job checks the native reader and
    # geometry against GROMACS on every run.
    tables, flex = {}, {}
    for route, extra in (("native", []), ("gromacs", ["--gromacs"])):
        code = subprocess.run([sys.executable, "-m", "caterva.app", "analyze", str(OUT), *extra],
                              cwd=ROOT, env={**os.environ, "GMX": gmx}).returncode
        if code not in (0, 4):
            print(f"FAIL: caterva analyze ({route}) exited {code} on real output")
            return 1
        text = (OUT / "ANALYSIS.md").read_text()
        tables[route] = _distance_rows(text)
        flex[route] = _flexibility_rows(text)
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
    print("OK: minimisation, then NVT, NPT, production and RMSD for two replicas, the summary, "
          "and the enzyme analysis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
