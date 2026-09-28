"""Is a quantity from a set of replicas a result, or one sample of noise?

Two checks, because they catch different failures:

**Within a replica** -- Flyvbjerg & Petersen (1989) block averaging. Frames
of a trajectory are correlated, so the naive standard error of their mean
is too small. Averaging adjacent pairs repeatedly and recomputing the error
lets it grow until the blocks are longer than the correlation time, where
it plateaus. If it is still rising when too few blocks are left to go on,
the run is shorter than its own correlation time and its error bar is a
lower bound, not an estimate.

**Across replicas** -- if independent runs disagree by more than their own
error bars allow, each one sampled a different part of the landscape and
none has converged, however smooth its own curve looks.

A single replica passes neither: it has no spread. It is reported as one
sample, which is what it is.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

#: Fraction of each run discarded as still relaxing before averaging. A
#: choice, and reported as one.
DISCARD = 0.5

#: A block level is trusted only with at least this many blocks.
MIN_BLOCKS = 8

#: A run with fewer effectively independent samples than this is not
#: converged, however its error curve looks.
MIN_EFFECTIVE_SAMPLES = 10

#: Replicas "disagree" when their spread exceeds this multiple of the
#: typical within-replica error.
DISAGREEMENT_FACTOR = 2.0


def read_xvg(path: Path) -> List[Tuple[float, float]]:
    """(time, value) pairs from a GROMACS .xvg, skipping # comments and @ directives."""
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line[0] in "#@":
            continue
        parts = line.split()
        rows.append((float(parts[0]), float(parts[1])))
    return rows


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _sem(xs: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n)


@dataclass
class BlockResult:
    mean: float
    sem: float  # the error at the highest trusted block level
    levels: List[Tuple[int, float]]  # (number of blocks, SEM at that level)
    plateaued: bool

    @property
    def effective_samples(self) -> float:
        """n (naive error / block error)^2: how many independent frames the run is worth."""
        if not self.levels or not self.sem or math.isnan(self.sem):
            return float("nan")
        n, naive = self.levels[0]
        return n * (naive / self.sem) ** 2


def block_average(xs: Sequence[float]) -> BlockResult:
    """Flyvbjerg-Petersen: halve the series by pairing until too few blocks remain."""
    data = list(xs)
    levels: List[Tuple[int, float]] = []
    while len(data) >= MIN_BLOCKS:
        levels.append((len(data), _sem(data)))
        data = [(data[i] + data[i + 1]) / 2 for i in range(0, len(data) - 1, 2)]
    if not levels:
        return BlockResult(_mean(xs) if xs else float("nan"), float("nan"), [], False)
    # An error estimated from n blocks is itself uncertain by a fraction
    # 1/sqrt(2(n-1)) (Flyvbjerg & Petersen, eq. 28). A level is the plateau
    # when every longer-block level agrees with it within two combined
    # uncertainties -- so the noisy last levels are judged by their own
    # noise, not held to a fixed tolerance they cannot meet.
    def u(n: int, e: float) -> float:
        return e / math.sqrt(2 * (n - 1))
    for k, (nk, ek) in enumerate(levels):
        if nk < 2 * MIN_BLOCKS or len(levels) - 1 - k < 2:
            continue  # a plateau needs at least two longer-block levels to agree with it
        if all(abs(ej - ek) <= 2 * math.hypot(u(nk, ek), u(nj, ej)) for nj, ej in levels[k + 1:]):
            return BlockResult(_mean(xs), ek, levels, True)
    return BlockResult(_mean(xs), max(e for _, e in levels), levels, False)


@dataclass
class Replica:
    name: str
    frames: int
    kept: int
    result: BlockResult


@dataclass
class Summary:
    quantity: str
    unit: str
    replicas: List[Replica]
    mean: float
    spread: Optional[float]  # SD of replica means; None for one replica
    typical_error: float  # RMS of the within-replica errors
    verdict: str  # "one sample" | "unconverged" | "replicas disagree" | "consistent"
    reasons: List[str] = field(default_factory=list)


def summarise(series: Sequence[Tuple[str, Sequence[float]]], quantity: str, unit: str) -> Summary:
    reps: List[Replica] = []
    for name, values in series:
        kept = list(values[int(len(values) * DISCARD):])
        reps.append(Replica(name, len(values), len(kept), block_average(kept)))
    means = [r.result.mean for r in reps]
    errs = [r.result.sem for r in reps if not math.isnan(r.result.sem)]
    typical = math.sqrt(_mean([e * e for e in errs])) if errs else float("nan")
    grand = _mean(means)
    reasons: List[str] = []
    short = [r.name for r in reps if not r.result.levels]
    rising = [r.name for r in reps if r.result.levels and not r.result.plateaued]
    if short:
        reasons.append(f"{', '.join(short)}: fewer than {MIN_BLOCKS} frames after discarding the first "
                       f"{DISCARD:.0%}; no error estimate is possible")
    few = [r for r in reps if r.result.levels and r.result.effective_samples < MIN_EFFECTIVE_SAMPLES]
    if few:
        reasons.append("; ".join(f"{r.name}: worth about {r.result.effective_samples:.1f} independent samples"
                                 for r in few)
                       + f" (fewer than {MIN_EFFECTIVE_SAMPLES}): the run is too short for what it measures")
    if rising:
        reasons.append(f"{', '.join(rising)}: the block-averaged error is still rising at the longest "
                       "blocks the run allows, so each run is shorter than its own correlation time and "
                       "its error bar is a lower bound")
    if len(reps) == 1:
        spread = None
        verdict = "one sample"
        reasons.insert(0, "a single trajectory has no spread across runs; nothing it shows can be told "
                          "apart from chance")
    else:
        spread = math.sqrt(sum((m - grand) ** 2 for m in means) / (len(means) - 1))
        if not math.isnan(typical) and spread > DISAGREEMENT_FACTOR * typical:
            reasons.append(f"the replicas' means differ by {spread:.3g} {unit} (SD), more than "
                           f"{DISAGREEMENT_FACTOR:g}x their typical within-run error ({typical:.3g} {unit}): "
                           "each run sampled a different state")
        if short or rising or few:
            verdict = "unconverged"
        elif spread > DISAGREEMENT_FACTOR * typical:
            verdict = "replicas disagree"
        else:
            verdict = "consistent"
    return Summary(quantity, unit, reps, grand, spread, typical, verdict, reasons)


def collect(directory: Path, filename: str = "rmsd.xvg") -> List[Tuple[str, List[float]]]:
    """Every repN/<filename> under a setup directory, in replica order."""
    found = []
    for d in sorted(directory.glob("rep*"), key=lambda p: int(re.sub(r"\D", "", p.name) or 0)):
        f = d / filename
        if f.exists():
            found.append((d.name, [v for _, v in read_xvg(f)]))
    return found


def report(s: Summary) -> List[str]:
    L = [f"# Convergence: {s.quantity}", "",
         f"**Verdict: {s.verdict}.**", ""]
    L += [f"- {r}" for r in s.reasons] + ([""] if s.reasons else [])
    L += ["| replica | frames used | mean | block-averaged error | error plateaued | independent samples |",
          "|---|---|---|---|---|---|"]
    for r in s.replicas:
        e = "n/a" if math.isnan(r.result.sem) else f"{r.result.sem:.3g}"
        L.append(f"| {r.name} | {r.kept} of {r.frames} | {r.result.mean:.4g} {s.unit} | {e} | "
                 f"{'yes' if r.result.plateaued else '**no**'} | {r.result.effective_samples:.0f} |")
    L.append("")
    if s.spread is None:
        L.append(f"Mean {s.mean:.4g} {s.unit} from one run: report it as one sample.")
    else:
        L.append(f"Across {len(s.replicas)} replicas: {s.mean:.4g} ± {s.spread:.2g} {s.unit} "
                 "(mean ± SD of replica means). Report the spread, not only the mean.")
    L += ["", f"The first {DISCARD:.0%} of each run is discarded as relaxation (a choice). Errors are "
          "Flyvbjerg & Petersen (1989) block averages, J. Chem. Phys. 91:461, doi:10.1063/1.457480."]
    return L


__all__ = ["MIN_EFFECTIVE_SAMPLES", "BlockResult", "Replica", "Summary", "block_average", "collect", "read_xvg",
           "report", "summarise", "DISCARD", "MIN_BLOCKS"]
