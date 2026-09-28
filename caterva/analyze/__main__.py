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

GROMACS does the measuring (`gmx distance`, `gmx rmsf`); the commands are
written to analyze.sh so they can be read, rerun, or run elsewhere.

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
from caterva.md.convergence import Summary, summarise

#: A consistent mean this far from the crystal distance is reported as the
#: geometry having changed. 0.1 nm (1 A) is about a hydrogen bond's length
#: tolerance; a choice, stated as one.
MOVED_NM = 0.1

EXIT_NOT_A_RESULT = 4


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
        lines.append(f"printf 'C-alpha\\n' | {gmx} rmsf -s {r}/md.tpr -f {r}/md.xtc -res -o {r}/rmsf.xvg")
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

    @property
    def all_consistent(self) -> bool:
        return bool(self.distances) and all(d.summary.verdict == "consistent" for d in self.distances)


def measure(directory: Path, p: Plan, reps: Sequence[Path]) -> Tuple[List[DistanceResult], Flexibility]:
    per_pair: Dict[int, List[Tuple[str, List[float]]]] = {i: [] for i in range(len(p.pairs))}
    flex = []
    pocket, rest = set(p.pocket), set(p.rest)
    for r in reps:
        if p.pairs:
            cols = read_columns(r / "catalytic.xvg")
            for i in range(len(p.pairs)):
                per_pair[i].append((r.name, [x for x in cols[i + 1]]))
        cols = read_columns(r / "rmsf.xvg")
        rmsf = dict(zip((int(x) for x in cols[0]), cols[1]))
        pv = [v for k, v in rmsf.items() if k in pocket and not math.isnan(v)]
        rv = [v for k, v in rmsf.items() if k in rest and not math.isnan(v)]
        if pv and rv:
            flex.append((r.name, sum(pv) / len(pv), sum(rv) / len(rv)))
    results = [DistanceResult(q.label, q.crystal_nm, summarise(per_pair[i], q.label, "nm"))
               for i, q in enumerate(p.pairs)]
    return results, Flexibility(flex)


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
          "| pair | crystal (nm) | simulated (nm, mean ± SD of replicas) | change | verdict |",
          "|---|---|---|---|---|"]
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
        L.append(f"| {d.label} | {cr} | {sim} | {ch} | {s.verdict} |")
    L.append("")
    grouped: Dict[str, List[str]] = {}
    for d in a.distances:
        if d.summary.verdict != "consistent" and d.summary.reasons:
            grouped.setdefault(d.summary.reasons[0], []).append(d.label)
    for reason, labels in grouped.items():
        who = "every pair" if len(labels) == len(a.distances) and len(labels) > 1 else ", ".join(labels)
        L.append(f"- {who}: {reason}")
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
          "- angles and hydrogen-bond occupancy between catalytic groups (next)", "",
          f"`{MOVED_NM:g} nm` is the chosen threshold for calling a distance changed. The measuring commands "
          "are in analyze.sh. Errors: Flyvbjerg & Petersen (1989) J. Chem. Phys. 91:461, "
          "doi:10.1063/1.457480. Catalytic residues: Ribeiro et al. (2018) Nucleic Acids Res. "
          "46:D618, doi:10.1093/nar/gkx1012."]
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
        if not args.no_run:
            gmx = os.environ.get("GMX", "gmx")
            if shutil.which(gmx) is None and not Path(gmx).exists():
                raise AnalyzeError(f"GROMACS not found ({gmx!r}): set GMX=/path/to/gmx, or run analyze.sh "
                                   "elsewhere and rerun with --no-run")
            run_gromacs(d, p, reps, gmx)
        distances, flex = measure(d, p, reps)
    except AnalyzeError as e:
        print(f"caterva analyze: {e}", file=sys.stderr)
        return 3
    a = Analysis(pdb, chain, source, p, distances, flex)
    text = "\n".join(report(a)) + "\n"
    print(text, end="")
    (d / "ANALYSIS.md").write_text(text, encoding="utf-8")
    return 0 if a.all_consistent else EXIT_NOT_A_RESULT


def console_main() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
