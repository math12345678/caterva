"""`caterva analyze`: the questions an enzyme's mechanism asks of its trajectory.

    caterva md --pdb 1I10 --chain A --out ldha-md && bash ldha-md/run.sh
    caterva analyze ldha-md
    caterva analyze ldha-md --script-only     # write analyze.sh, run nothing

For every pair of catalytic residues (M-CSA, mapped by `caterva prepare`),
the distance between their functional groups in each replica, against the
same distance in the starting crystal structure; and the flexibility (RMSF)
of the active-site pocket against the rest of the protein. Each quantity is
reported as a spread across replicas with block-averaged errors, and called
a result only when the replicas agree (see `caterva md --summarise`).

Caterva does the measuring itself, from the .xtc files it reads natively
(caterva/md/xtc.py), so this runs where GROMACS is not installed. The
same measurements as GROMACS commands are written to analyze.sh, and
`--gromacs` uses them instead, as a cross-check.

Exit codes: 0 every quantity is a consistent result, 4 at least one is not
(unconverged, replicas disagree, one sample), 2 malformed question,
3 refused and said why (no finished run, no catalytic residues), 1 a crash.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from caterva.analyze.plan import POCKET_RADIUS, Plan, plan, read_pdb
from caterva.analyze.hbonds import Occupancy
from caterva.analyze.rotamers import Rotamer
from caterva.md.convergence import CONFIDENCE, Summary, summarise

CONFIDENCE_PCT = CONFIDENCE * 100

#: A consistent mean this far from the crystal distance is reported as the
#: geometry having changed. 0.1 nm (1 A) is about a hydrogen bond's length
#: tolerance; a choice, stated as one.
MOVED_NM = 0.1

EXIT_NOT_A_RESULT = 4
#: A fluctuation needs at least two frames; below that RMSF is not measured,
#: on either route.
MIN_RMSF_FRAMES = 2


class AnalyzeError(Exception):
    """The analysis could not be run, as distinct from finding nothing."""


def read_columns(path: Path) -> List[List[float]]:
    """All numeric columns of an .xvg: [times, col1, col2, ...]."""
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line[0] in "#@":
            continue
        rows.append([float(x) for x in line.split()])
    return [list(c) for c in zip(*rows)] if rows else []


def setup_info(directory: Path) -> Tuple[str, Optional[str]]:
    """The PDB id and chain a `caterva md` directory was written for."""
    meta = directory / "caterva-setup.json"
    if meta.exists():
        d = json.loads(meta.read_text())
        return d["pdb"], d.get("chain")
    run = directory / "run.sh"
    if run.exists():
        m = re.search(r"# Caterva MD setup: PDB (\w{4})(?:, chain (\w))?", run.read_text())
        if m:
            return m.group(1), m.group(2)
    raise AnalyzeError(f"{directory} is not a `caterva md` setup (no caterva-setup.json or run.sh)")


def replicas(directory: Path) -> List[Path]:
    reps = sorted((p for p in directory.glob("rep*") if p.is_dir()),
                  key=lambda p: int(re.sub(r"\D", "", p.name) or 0))
    return [r for r in reps if (r / "md.xtc").exists() and (r / "md.tpr").exists()]


def catalytic_residues(pdb: str, chain: Optional[str]) -> Tuple[List[Tuple[int, str]], str]:
    """Catalytic residues in the structure's own numbering, via `caterva prepare`."""
    from caterva.prepare.__main__ import _cache_dir, cached, live_fetch, run_audit

    a = run_audit(pdb, cached(live_fetch(), _cache_dir()))
    if a.reference is None:
        raise AnalyzeError(f"no catalytic residues for {pdb}: {'; '.join(a.not_checked[:1])}")
    use = chain or (a.chains[0] if a.chains else None)
    out = []
    for c in a.catalytic:
        if c.chain == use and c.found and c.auth_seq_id.lstrip("-").isdigit():
            out.append((int(c.auth_seq_id), c.found))
    source = (f"M-CSA entry {a.reference.mcsa_id} ({a.reference.enzyme}), mapped onto {pdb} chain {use} "
              f"at {a.reference.identity:.0%} identity")
    return out, source


def commands(p: Plan, reps: Sequence[str], gmx: str = "$GMX") -> List[str]:
    sel = " ".join(f"'{q.selection()}'" for q in p.pairs)
    lines = []
    for r in reps:
        if p.pairs:
            lines.append(f'{gmx} distance -s {r}/md.tpr -f {r}/md.xtc -select {sel} '
                         f'-oall {r}/catalytic.xvg -tu ns')
        # gmx rmsf fits every frame to the -s coordinates AS STORED, and a
        # tpr stores them wrapped into the box: on lysozyme (1AKI, 2026-09-29)
        # residues 66-74 sat a box length from their neighbours, and the fit
        # to that broken reference put their RMSF about 10% high. So the
        # reference is em.gro made whole (the one the native route fits to)
        # and the trajectory is made whole first; the two routes then agree
        # to 0.0001 nm on every residue.
        lines.append(f"printf 'Protein\\n' | {gmx} trjconv -s {r}/md.tpr -f em.gro -pbc mol "
                     f"-o {r}/rmsf_reference.pdb")
        lines.append(f"printf 'Protein\\n' | {gmx} trjconv -s {r}/md.tpr -f {r}/md.xtc -pbc mol "
                     f"-o {r}/md_whole.xtc")
        lines.append(f"printf 'C-alpha\\n' | {gmx} rmsf -s {r}/rmsf_reference.pdb -f {r}/md_whole.xtc "
                     f"-res -o {r}/rmsf.xvg")
    return lines


def script(p: Plan, reps: Sequence[str]) -> str:
    return ("#!/usr/bin/env bash\n# Written by `caterva analyze`. Needs GROMACS (gmx on PATH, or GMX=...).\n"
            "set -euo pipefail\nGMX=\"${GMX:-gmx}\"\ncd \"$(dirname \"$0\")\"\n\n"
            + "\n".join(commands(p, reps)) + "\n")


@dataclass
class DistanceResult:
    label: str
    crystal_nm: Optional[float]
    summary: Summary

    @property
    def drift_nm(self) -> Optional[float]:
        return None if self.crystal_nm is None else self.summary.mean - self.crystal_nm

    @property
    def moved(self) -> bool:
        return self.drift_nm is not None and abs(self.drift_nm) > MOVED_NM


@dataclass
class Flexibility:
    per_replica: List[Tuple[str, float, float]]  # (replica, pocket mean RMSF, rest mean RMSF)

    @property
    def ratios(self) -> List[float]:
        return [p / r for _, p, r in self.per_replica
                if r > 0 and not math.isnan(p) and not math.isnan(r)]


@dataclass
class Analysis:
    pdb: str
    chain: Optional[str]
    source: str
    plan: Plan
    distances: List[DistanceResult] = field(default_factory=list)
    flexibility: Optional[Flexibility] = None
    #: Hydrogen-bond occupancy between catalytic side chains; None when the
    #: GROMACS route measured (it does not count hydrogen bonds).
    hbonds: Optional[List["Occupancy"]] = None
    #: chi1 rotamers of the catalytic residues; None on the GROMACS route.
    rotamers: Optional[List["Rotamer"]] = None

    @property
    def all_consistent(self) -> bool:
        return bool(self.distances) and all(d.summary.verdict == "consistent" for d in self.distances)


def measure(directory: Path, p: Plan, reps: Sequence[Path]) -> Tuple[List[DistanceResult], Flexibility]:
    per_pair: Dict[int, List[Tuple[str, List[float]]]] = {i: [] for i in range(len(p.pairs))}
    flex = []
    pocket, rest = set(p.pocket), set(p.rest)
    for r in reps:
        frames = None
        if p.pairs:
            cols = read_columns(r / "catalytic.xvg")
            frames = len(cols[0])
            for i in range(len(p.pairs)):
                per_pair[i].append((r.name, [x for x in cols[i + 1]]))
        if frames is not None and frames < MIN_RMSF_FRAMES:
            # One frame has no fluctuation. gmx rmsf still prints 0.0001-
            # 0.0002 nm, its single-precision sqrt(<x^2> - <x>^2) on
            # coordinates of a few nm, and the native route says not
            # measurable; CI's comparison of the two routes found it.
            continue
        cols = read_columns(r / "rmsf.xvg")
        rmsf = dict(zip((int(x) for x in cols[0]), cols[1]))
        pv = [v for k, v in rmsf.items() if k in pocket and not math.isnan(v)]
        rv = [v for k, v in rmsf.items() if k in rest and not math.isnan(v)]
        if pv and rv:
            flex.append((r.name, sum(pv) / len(pv), sum(rv) / len(rv)))
    results = [DistanceResult(q.label, q.crystal_nm, summarise(per_pair[i], q.label, "nm"))
               for i, q in enumerate(p.pairs)]
    return results, Flexibility(flex)


def _gro_index(path: Path) -> Dict[Tuple[int, str], int]:
    """(residue number, atom name) -> 0-based index in the simulated system,
    first occurrence; the numbering pdb2gmx keeps."""
    lines = path.read_text().splitlines()
    n = int(lines[1].split()[0])
    out: Dict[Tuple[int, str], int] = {}
    for i, l in enumerate(lines[2:2 + n]):
        out.setdefault((int(l[0:5]), l[10:15].strip()), i)
    return out


def distance_series(traj, ia: Sequence[int], ib: Sequence[int]) -> List[float]:
    """Per frame, the distance (nm) between the geometric centres of two atom
    groups, each made whole, across periodic boundaries: `gmx distance -select
    'cog of (...) plus cog of (...)'`, computed by Caterva."""
    import numpy as np
    from caterva.md import xtc
    out = []
    for f in traj:
        ca_ = xtc.make_whole(f.x[list(ia)], f.box).mean(0)
        cb_ = xtc.make_whole(f.x[list(ib)], f.box).mean(0)
        out.append(float(np.linalg.norm(xtc.nearest_image(cb_ - ca_, f.box)[0])))
    return out


def _gro_box(line: str):
    """A .gro box line as box vectors (rows): 3 values for a rectangular box,
    9 for a triclinic one, in the order v1(x) v2(y) v3(z) v1(y) v1(z) v2(x)
    v2(z) v3(x) v3(y)."""
    import numpy as np
    v = [float(x) for x in line.split()]
    box = np.diag(v[:3])
    if len(v) == 9:
        box[0, 1], box[0, 2], box[1, 0], box[1, 2], box[2, 0], box[2, 1] = v[3:9]
    return box


def _gro_atoms(path: Path):
    """(resnr, resname, name, xyz) for every atom of a .gro file."""
    import numpy as np
    lines = path.read_text().splitlines()
    n = int(lines[1].split()[0])
    return [(int(l[0:5]), l[5:10].strip(), l[10:15].strip(),
             np.array([float(l[20 + 8 * k:28 + 8 * k]) for k in range(3)])) for l in lines[2:2 + n]]


def measure_native(directory: Path, p: Plan, reps: Sequence[Path]
                   ) -> Tuple[List[DistanceResult], Flexibility, List["Occupancy"], List["Rotamer"]]:
    """The same distances and RMSF as analyze.sh, computed by Caterva from the
    trajectories it reads itself (caterva/md/xtc.py), with no GROMACS."""
    import numpy as np
    from caterva.md import xtc
    ref_gro = directory / "em.gro"
    if not ref_gro.exists():
        raise AnalyzeError(f"{ref_gro} does not exist: run {directory}/run.sh first")
    index = _gro_index(ref_gro)

    def atoms_of(site) -> List[int]:
        missing = [n for n in site.atoms if (site.resnr, n) not in index]
        if missing:
            raise AnalyzeError(f"{site.label}: atom(s) {', '.join(missing)} not in {ref_gro.name}")
        return [index[(site.resnr, n)] for n in site.atoms]

    pair_atoms = [(atoms_of(q.a), atoms_of(q.b)) for q in p.pairs]
    residues = sorted(set(p.pocket) | set(p.rest))
    ca = [(r, index[(r, "CA")]) for r in residues if (r, "CA") in index]
    ref_lines = ref_gro.read_text().splitlines()
    ref = np.array([[float(ref_lines[2 + i][20 + 8 * k:28 + 8 * k]) for k in range(3)] for _, i in ca])
    from caterva.analyze.hbonds import Occupancy, count_frame, occupancy, side_chain_group
    per_pair: Dict[int, List[Tuple[str, List[float]]]] = {i: [] for i in range(len(p.pairs))}
    flex = []
    pocket, rest = set(p.pocket), set(p.rest)
    atoms = _gro_atoms(ref_gro)
    groups = {}
    for q in p.pairs:
        for site in (q.a, q.b):
            if site.resnr not in groups:
                try:
                    groups[site.resnr] = side_chain_group(atoms, site.resnr)
                except ValueError:
                    groups[site.resnr] = None  # glycine: no side chain to bond
    start_x = np.array([a[3] for a in atoms])
    start_box = _gro_box(ref_lines[-1])
    from caterva.analyze.rotamers import Rotamer, chi1_atoms, chi1_series, dihedral, populations
    chi_sites = []
    for site in p.sites:
        idx = chi1_atoms(atoms, site.resnr)
        if idx is not None:
            chi_sites.append((site, idx))
    chi_pops: Dict[int, List[Tuple[str, Dict[str, float]]]] = {site.resnr: [] for site, _ in chi_sites}
    hb: Dict[int, List[Tuple[str, float, float]]] = {i: [] for i in range(len(p.pairs))}
    for r in reps:
        traj = xtc.read(r / "md.xtc")
        for i, q in enumerate(p.pairs):
            ga, gb = groups[q.a.resnr], groups[q.b.resnr]
            if ga is not None and gb is not None:
                frac, mean, _ = occupancy(traj, ga, gb)
                hb[i].append((r.name, frac, mean))
        for i, (ia, ib) in enumerate(pair_atoms):
            per_pair[i].append((r.name, distance_series(traj, ia, ib)))
        for site, idx in chi_sites:
            chi_pops[site.resnr].append((r.name, populations(chi1_series(traj, idx))))
        if len(traj) < MIN_RMSF_FRAMES:
            continue
        f_ca = xtc.rmsf(traj, [i for _, i in ca], ref)
        rmsf = {res: float(v) for (res, _), v in zip(ca, f_ca)}
        pv = [v for k, v in rmsf.items() if k in pocket]
        rv = [v for k, v in rmsf.items() if k in rest]
        if pv and rv:
            flex.append((r.name, sum(pv) / len(pv), sum(rv) / len(rv)))
    results = [DistanceResult(q.label, q.crystal_nm, summarise(per_pair[i], q.label, "nm"))
               for i, q in enumerate(p.pairs)]
    occupancies = []
    for i, q in enumerate(p.pairs):
        ga, gb = groups[q.a.resnr], groups[q.b.resnr]
        if ga is None or gb is None:
            continue
        occupancies.append(Occupancy(q.label, hb[i], count_frame(start_x, start_box, ga, gb)))
    rotamers = [Rotamer(site.label, dihedral(*(start_x[i] for i in idx), start_box), chi_pops[site.resnr])
                for site, idx in chi_sites]
    return results, Flexibility(flex), occupancies, rotamers


#: Occupancy thresholds for naming what happened to a hydrogen bond. Chosen,
#: and printed with the table.
KEPT, LOST, FORMED, SPLIT = 0.8, 0.2, 0.5, 0.5


def hbond_verdict(o) -> str:
    fr = o.fractions
    if len(fr) < 2:
        return "one replica"
    if max(fr) - min(fr) > SPLIT:
        return "replicas disagree"
    if o.at_start > 0 and min(fr) >= KEPT:
        return "kept"
    if o.at_start > 0 and max(fr) <= LOST:
        return "lost"
    if o.at_start == 0 and min(fr) >= FORMED:
        return "formed"
    if o.at_start == 0 and max(fr) <= LOST:
        return "rarely formed"
    return "partial"


def run_gromacs(directory: Path, p: Plan, reps: Sequence[Path], gmx: str) -> None:
    for line in commands(p, [r.name for r in reps], gmx=shlex_quote(gmx)):
        proc = subprocess.run(["bash", "-c", line], cwd=directory, capture_output=True, text=True)
        if proc.returncode != 0:
            raise AnalyzeError(f"GROMACS failed:\n  {line}\n{proc.stderr.strip()[-800:]}")


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


def report(a: Analysis) -> List[str]:
    L = [f"# Enzyme analysis: {a.pdb}" + (f" chain {a.chain}" if a.chain else ""), "",
         f"Catalytic residues from {a.source}.", ""]
    if a.plan.notes:
        L += [f"- {n}" for n in a.plan.notes] + [""]
    L += ["## Catalytic geometry", "",
          "Distance between the functional groups of each pair of catalytic residues "
          "(geometric centres), across replicas, against the starting crystal structure.", "",
          "| pair | crystal (nm) | simulated (nm, mean ± SD of replicas) | 95% CI of the mean | change | verdict |",
          "|---|---|---|---|---|---|"]
    for d in a.distances:
        s = d.summary
        sim = f"{s.mean:.3f}" + (f" ± {s.spread:.3f}" if s.spread is not None else "")
        cr = "?" if d.crystal_nm is None else f"{d.crystal_nm:.3f}"
        if d.drift_nm is None:
            ch = "?"
        elif s.verdict != "consistent":
            ch = f"({d.drift_nm:+.3f}, not yet a result)"
        else:
            ch = f"**{d.drift_nm:+.3f}, moved**" if d.moved else f"{d.drift_nm:+.3f}, held"
        ci = "n/a" if math.isnan(s.ci95) else f"± {s.ci95:.3f}"
        L.append(f"| {d.label} | {cr} | {sim} | {ci} | {ch} | {s.verdict} |")
    L.append("")
    L += replica_sufficiency(a)
    grouped: Dict[str, List[str]] = {}
    for d in a.distances:
        if d.summary.verdict != "consistent" and d.summary.reasons:
            grouped.setdefault(d.summary.reasons[0], []).append(d.label)
    for reason, labels in grouped.items():
        who = "every pair" if len(labels) == len(a.distances) and len(labels) > 1 else ", ".join(labels)
        L.append(f"- {who}: {reason}")
    L += hbond_section(a)
    L += rotamer_section(a)
    f = a.flexibility
    L += ["", "## Active-site flexibility", "",
          f"Mean Cα RMSF of the {len(a.plan.pocket)} residues within {POCKET_RADIUS:g} Å of a catalytic "
          f"residue (the pocket) against the other {len(a.plan.rest)}.", ""]
    rs = f.ratios if f else []
    if f and f.per_replica and rs:
        L += ["| replica | pocket (nm) | rest (nm) | pocket / rest |", "|---|---|---|---|"]
        for name, pv, rv in f.per_replica:
            ratio = f"{pv / rv:.2f}" if rv > 0 else "n/a"
            L.append(f"| {name} | {pv:.4f} | {rv:.4f} | {ratio} |")
        if len(rs) > 1:
            m = sum(rs) / len(rs)
            sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (len(rs) - 1))
            if a.all_consistent:
                L += ["", f"Pocket / rest: {m:.2f} ± {sd:.2f} across {len(rs)} replicas "
                          "(below 1: the active site is more rigid than the protein around it)."]
            else:
                L += ["", f"Not yet a result: pocket / rest {m:.2f} ± {sd:.2f}, from runs the catalytic "
                          "distances above show are unconverged. RMSF from unconverged runs measures "
                          "how far each residue got, not how mobile it is."]
        else:
            L += ["", "One usable replica: the ratio has no spread."]
    else:
        L += ["Not measurable: RMSF needs more than one frame per replica, and these runs are too short."]
    L += ["", "## Not measured", "",
          "- ligand pose and contacts: `caterva md` strips ligands until they can be parameterised "
          "(MD roadmap M4)",
          "- angles between catalytic groups (next)", "",
          f"`{MOVED_NM:g} nm` is the chosen threshold for calling a distance changed. The measuring commands "
          "are in analyze.sh. Errors: Flyvbjerg & Petersen (1989) J. Chem. Phys. 91:461, "
          "doi:10.1063/1.457480. Catalytic residues: Ribeiro et al. (2018) Nucleic Acids Res. "
          "46:D618, doi:10.1093/nar/gkx1012."]
    return L


#: The precision a catalytic distance needs before "held" or "moved" can be
#: decided with confidence: half the moved threshold, so the interval cannot
#: straddle both answers. A choice, derived from MOVED_NM.
RESOLVE_NM = MOVED_NM / 2


def replica_sufficiency(a: Analysis) -> List[str]:
    """Are there enough replicas to decide held or moved? From the spread the
    replicas actually show, not a rule of thumb."""
    measured = [d for d in a.distances if d.summary.spread is not None and not math.isnan(d.summary.ci95)]
    if not measured:
        return []
    n = len(measured[0].summary.replicas)
    short = [(d, d.summary.replicas_for(RESOLVE_NM)) for d in measured if d.summary.ci95 > RESOLVE_NM]
    if not short:
        return [f"- Replicas: {n} are enough; every distance's {int(CONFIDENCE_PCT)}% confidence interval is "
                f"within ± {RESOLVE_NM:g} nm, half the {MOVED_NM:g} nm moved threshold.", ""]
    worst = max(short, key=lambda x: x[0].summary.ci95)
    needs = [k for _, k in short if k is not None]
    most = max(needs) if needs else None
    return [f"- Replicas: {n} are not enough to decide held or moved for {len(short)} of {len(measured)} "
            f"distances: their {int(CONFIDENCE_PCT)}% confidence intervals are wider than ± {RESOLVE_NM:g} nm "
            f"(worst: {worst[0].label}, ± {worst[0].summary.ci95:.3f} nm). "
            + (f"If the spread between runs stays as it is, {most} replicas would resolve all of them."
               if most else "Even many more replicas would not, at the spread seen: the runs are too short.")
            + " (With few replicas the interval is wide by construction: Student's t for 2 replicas is 12.7; "
              "and two runs estimate the spread itself poorly, so treat that count as a first guess.)",
            ""]


def hbond_section(a: Analysis) -> List[str]:
    L = ["", "## Hydrogen bonds between catalytic side chains", ""]
    if a.hbonds is None:
        return L + ["Not measured on the GROMACS route (`--gromacs`); the native route counts them."]
    bonded = [o for o in a.hbonds if o.at_start or any(f > 0 for f in o.fractions)]
    L += ["Fraction of frames in which two catalytic side chains are hydrogen-bonded, per replica. "
          "Donor-acceptor at most 0.35 nm and acceptor-donor-hydrogen at most 30 degrees, the criterion "
          "of `gmx hbond`; backbone atoms excluded.", ""]
    if not bonded:
        return L + [f"None of the {len(a.hbonds)} pairs of catalytic side chains hydrogen-bonded, at the "
                    "start or in any frame."]
    names = [n for n, _, _ in bonded[0].per_replica]
    L += ["| pair | bonds at start | " + " | ".join(names) + " | verdict |",
          "|---|---|" + "---|" * len(names) + "---|"]
    for o in bonded:
        v = hbond_verdict(o)
        if not a.all_consistent and v not in ("one replica",):
            v = f"({v}, not yet a result)"
        L.append(f"| {o.label} | {o.at_start} | " + " | ".join(f"{f:.2f}" for f in o.fractions) + f" | {v} |")
    never = len(a.hbonds) - len(bonded)
    if never:
        L += ["", f"The other {never} pair(s) never hydrogen-bonded, at the start or in any frame."]
    L += ["", f"Verdicts (chosen thresholds): kept, bonded at the start and in at least {KEPT:.0%} of frames "
          f"in every replica; lost, bonded at the start and in at most {LOST:.0%}; formed, not bonded at the "
          f"start and in at least {FORMED:.0%}; rarely formed, not bonded at the start and in at most "
          f"{LOST:.0%}; replicas disagree, when their occupancies differ by more "
          f"than {SPLIT:.0%}."]
    return L


def rotamer_section(a: Analysis) -> List[str]:
    from caterva.analyze.rotamers import FLIPPED, KEPT, SPLIT, WELLS, rotamer_verdict
    L = ["", "## Catalytic side-chain rotamers", ""]
    if a.rotamers is None:
        return L + ["Not measured on the GROMACS route (`--gromacs`); the native route measures them."]
    if not a.rotamers:
        return L + ["No catalytic residue has a chi1 (glycine and alanine have none)."]
    L += ["chi1 (N-CA-CB-gamma) of each catalytic residue, frame by frame, in the well it is nearest: "
          "+60, 180 or -60 degrees. The distances above are between functional-group centres and cannot "
          "see a side chain turn over; this can. Per replica, the fraction of frames in the well the "
          "residue started in.", ""]
    names = [n for n, _ in a.rotamers[0].per_replica]
    L += ["| residue | chi1 at start | " + " | ".join(names) + " | verdict |",
          "|---|---|" + "---|" * len(names) + "---|"]
    for r in a.rotamers:
        v = rotamer_verdict(r)
        if not a.all_consistent and v != "one replica":
            v = f"({v}, not yet a result)"
        L.append(f"| {r.label} | {r.at_start:.0f} ({r.start_well}) | "
                 + " | ".join(f"{k:.2f}" for k in r.kept) + f" | {v} |")
    L += ["", f"Verdicts (chosen thresholds): kept, in the starting well in at least {KEPT:.0%} of frames in "
          f"every replica; flipped, in at most {FLIPPED:.0%}, named by the well it moved to when the replicas "
          f"agree on one; replicas disagree, when their fractions differ by more than {SPLIT:.0%}. "
          f"The wells are named by angle ({', '.join(WELLS)}) because gauche+ and gauche- are used in both "
          f"senses in the literature."]
    return L


def build_parser(prog: str = "caterva analyze") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=prog, description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=("Examples:\n"
                                        f"  {prog} ldha-md\n  {prog} ldha-md --script-only\n"
                                        "\nExit codes: 0 every quantity consistent, 4 at least one not a result, "
                                        "2 malformed question, 3 refused and said why, 1 a crash."))
    p.add_argument("directory", help="a finished `caterva md` setup")
    p.add_argument("--script-only", action="store_true",
                   help="write analyze.sh and stop; run it, then rerun without this flag")
    p.add_argument("--no-run", action="store_true",
                   help="use the .xvg files analyze.sh already wrote; do not call GROMACS")
    p.add_argument("--gromacs", action="store_true",
                   help="measure with gmx distance and gmx rmsf (analyze.sh) instead of Caterva's own reader")
    return p


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva analyze",
         catalytic=catalytic_residues) -> int:
    args = build_parser(prog).parse_args(argv)
    d = Path(args.directory)
    try:
        pdb, chain = setup_info(d)
        protein = d / "protein.pdb"
        if not protein.exists():
            raise AnalyzeError(f"{protein} does not exist: run {d}/run.sh first")
        residues, source = catalytic(pdb, chain)
        if not residues:
            raise AnalyzeError(f"no catalytic residues of {pdb} could be placed in the simulated chain")
        p = plan(read_pdb(protein.read_text(), chain), residues)
        reps = replicas(d)
        (d / "analyze.sh").write_text(script(p, [r.name for r in reps] or ["rep1"]))
        if args.script_only:
            print(f"Wrote {d}/analyze.sh ({len(p.pairs)} catalytic distances, pocket of {len(p.pocket)} residues).")
            return 0
        if not reps:
            raise AnalyzeError(f"no finished replicas (rep*/md.xtc) under {d}: run {d}/run.sh first")
        if args.gromacs or args.no_run:
            if not args.no_run:
                gmx = os.environ.get("GMX", "gmx")
                if shutil.which(gmx) is None and not Path(gmx).exists():
                    raise AnalyzeError(f"GROMACS not found ({gmx!r}): set GMX=/path/to/gmx, or run analyze.sh "
                                       "elsewhere and rerun with --no-run")
                run_gromacs(d, p, reps, gmx)
            distances, flex = measure(d, p, reps)
            hbonds = rotamers = None
        else:
            distances, flex, hbonds, rotamers = measure_native(d, p, reps)
    except AnalyzeError as e:
        print(f"caterva analyze: {e}", file=sys.stderr)
        return 3
    a = Analysis(pdb, chain, source, p, distances, flex, hbonds, rotamers)
    text = "\n".join(report(a)) + "\n"
    print(text, end="")
    (d / "ANALYSIS.md").write_text(text, encoding="utf-8")
    return 0 if a.all_consistent else EXIT_NOT_A_RESULT


def console_main() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
