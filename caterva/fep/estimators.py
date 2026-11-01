"""Free-energy estimation from alchemical samples, implemented here from the papers.

No black box between the trajectories and the number: `gmx bar` reports a
total and an error; this reports how that total was reached and whether it
should be believed. From the dhdl.xvg files GROMACS writes:

* **Equilibration** is detected per window by the point after which the
  number of effectively independent samples is largest (Chodera 2016).
* **Correlation** is removed by subsampling at the statistical inefficiency
  g = 1 + 2 sum (1 - t/N) C(t) (Chodera et al. 2007): samples written every
  0.2 ps are not independent, and counting them as if they were shrinks
  every error bar.
* **MBAR** (Shirts & Chodera 2008) uses every sample at every state at
  once, solved self-consistently in log space, with its asymptotic
  covariance for the error.
* **BAR** (Bennett 1976) between neighbouring states, the estimator
  `gmx bar` uses, as a cross-check on MBAR.
* **Overlap**: the MBAR overlap matrix. Neighbouring states that barely
  overlap make any estimator unreliable, and the smallest overlap is
  reported and judged.
* **Convergence**: MBAR on growing fractions of the data from the start
  and from the end. A forward and a reverse estimate that disagree say the
  run has not sampled what it needs.

Energies are reduced (divided by kT) inside; results are in kJ/mol.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

R_KJ = 8.314462618e-3
#: Neighbouring states whose overlap falls below this are unreliable: the
#: threshold commonly used with MBAR's overlap matrix.
MIN_OVERLAP = 0.03


# -- reading GROMACS -----------------------------------------------------------

@dataclass
class Window:
    state: int                       # this window's lambda-state index
    temperature: float               # K
    time: np.ndarray                 # ps
    du: np.ndarray                   # (K, n) reduced u_k(x_n) - u_state(x_n)
    components: List[str] = field(default_factory=list)   # e.g. ["coul", "vdw"]
    lambdas: Optional[np.ndarray] = None                   # (K, C) every state's lambda vector
    dhdl: Optional[np.ndarray] = None                      # (C, n) dH/dlambda, kJ/mol


_TEMP = re.compile(r"T\s*=\s*([\d.]+)\s*\(K\)")
_STATE = re.compile(r"state\s+(\d+)")


def read_dhdl(path: Path) -> Window:
    """A GROMACS dhdl.xvg written with calc-lambda-neighbors = -1 (every state)."""
    text = Path(path).read_text().splitlines()
    temperature = state = None
    legends: Dict[int, str] = {}
    rows = []
    for line in text:
        if line.startswith("@"):
            if "subtitle" in line:
                m = _TEMP.search(line)
                temperature = float(m.group(1)) if m else temperature
                s = _STATE.search(line)
                state = int(s.group(1)) if s else state
            m = re.match(r'@ s(\d+) legend "(.*)"', line)
            if m:
                legends[int(m.group(1))] = m.group(2)
        elif line and not line.startswith("#"):
            rows.append([float(x) for x in line.split()])
    if temperature is None or state is None:
        raise ValueError(f"{path}: no 'T = ... (K)' and lambda state in the subtitle")
    data = np.array(rows)
    dh_cols = [i for i, l in sorted(legends.items()) if "H \\xl\\f{} to" in l or "\\xD\\f{}H" in l and " to " in l]
    dhdl_cols = [(i, re.search(r"(\w+)-lambda", l).group(1)) for i, l in sorted(legends.items())
                 if l.startswith("dH/d") and re.search(r"(\w+)-lambda", l)]
    targets = []
    for i in dh_cols:
        m = re.search(r"to \(([^)]*)\)", legends[i]) or re.search(r"to ([-\d.]+)", legends[i])
        targets.append([float(v) for v in m.group(1).split(",")] if m else [])
    if not dh_cols:
        raise ValueError(f"{path}: no energy differences to other states")
    beta = 1.0 / (R_KJ * temperature)
    # Column 0 is time; series s_i is data column i + 1.
    du = beta * data[:, [c + 1 for c in dh_cols]].T
    if len(dh_cols) < 3:
        raise ValueError(f"{path}: energies at {len(dh_cols)} states only; MBAR needs every state "
                         "(calc-lambda-neighbors = -1)")
    lambdas = np.array(targets) if targets and all(len(t) == len(targets[0]) for t in targets) else None
    dhdl = data[:, [c + 1 for c, _ in dhdl_cols]].T if dhdl_cols else None
    return Window(state, temperature, data[:, 0], du, [c for _, c in dhdl_cols], lambdas, dhdl)


# -- correlation and equilibration ------------------------------------------------

def statistical_inefficiency(x: np.ndarray, mintime: int = 3) -> float:
    """g = 1 + 2 sum_{t=1}^{N-1} (1 - t/N) C(t), summed until C(t) first falls
    to zero after `mintime` lags (Chodera et al. 2007, eq. 20-21). Every lag
    is summed; the autocorrelation comes from an FFT, so this is O(N log N).
    (A geometric-stride shortcut read 3.5 for an AR(1) process whose exact
    g is 3.0, and was replaced.)"""
    x = np.asarray(x, float)
    n = len(x)
    dx = x - x.mean()
    var = float(np.dot(dx, dx) / n)
    if n < 2 or var == 0.0:
        return 1.0
    size = 1 << (2 * n - 1).bit_length()
    f = np.fft.rfft(dx, size)
    acov = np.fft.irfft(f * np.conj(f), size)[:n]
    c = acov / (np.arange(n, 0, -1) * var)  # C(t), unbiased per lag
    g = 1.0
    for t in range(1, n - 1):
        if c[t] <= 0.0 and t > mintime:
            break
        g += 2.0 * c[t] * (1.0 - t / n)
    return max(1.0, g)


def detect_equilibration(x: np.ndarray, nskip: int = 1) -> Tuple[int, float, float]:
    """(t0, g, N_eff): discard the first t0 samples to maximise the number of
    effectively independent samples (Chodera 2016)."""
    x = np.asarray(x, float)
    n = len(x)
    best = (0, statistical_inefficiency(x), 0.0)
    best = (0, best[1], n / best[1])
    for t0 in range(1, max(1, n - 5), nskip):
        g = statistical_inefficiency(x[t0:])
        neff = (n - t0) / g
        if neff > best[2]:
            best = (t0, g, neff)
    return best


def subsample(n: int, g: float) -> np.ndarray:
    """Indices spaced by g, rounded, never repeated."""
    idx = np.unique(np.round(np.arange(0, n, max(1.0, g))).astype(int))
    return idx[idx < n]


# -- MBAR ----------------------------------------------------------------------------

def _logsumexp(a: np.ndarray, axis=None, b: Optional[np.ndarray] = None) -> np.ndarray:
    m = np.max(a, axis=axis, keepdims=True)
    s = np.exp(a - m) if b is None else b * np.exp(a - m)
    out = np.log(np.sum(s, axis=axis, keepdims=True)) + m
    return np.squeeze(out, axis=axis) if axis is not None else float(out.squeeze())


@dataclass
class MbarResult:
    f: np.ndarray            # reduced free energies, f[0] = 0
    df: np.ndarray           # their standard errors relative to state 0
    overlap: np.ndarray      # (K, K)
    iterations: int


def mbar(u_kn: np.ndarray, N_k: Sequence[int], tol: float = 1e-10, max_iter: int = 100000) -> MbarResult:
    """Solve the MBAR equations (Shirts & Chodera 2008, eq. 11):

        f_i = -ln sum_n exp(-u_i(x_n)) / sum_k N_k exp(f_k - u_k(x_n))

    u_kn[k, n] is sample n's reduced potential at state k; N_k the samples
    drawn from each state, in the order of the columns. Converged by the
    self-consistent iteration, in log space throughout.
    """
    u = np.asarray(u_kn, float)
    N = np.asarray(N_k, float)
    K = u.shape[0]
    logN = np.log(np.where(N > 0, N, 1.0))
    mask = N > 0
    f = np.zeros(K)
    for it in range(1, max_iter + 1):
        with np.errstate(under="ignore"):
            log_denom = _logsumexp((f + logN)[mask][:, None] - u[mask], axis=0)
            f_new = -_logsumexp(-u - log_denom[None, :], axis=1)
        f_new -= f_new[0]
        if np.max(np.abs(f_new - f)) < tol:
            f = f_new
            break
        f = f_new
    # Floating-point flags are silenced here and finiteness is checked
    # instead: exp() of a decoupled state's 1e16 kT overlap energy underflows
    # to the 0 it should be, and Apple's Accelerate BLAS raises spurious
    # divide/overflow flags even on small random finite matrices (measured:
    # six warnings, finite output). A real non-finite result still raises.
    with np.errstate(all="ignore"):
        log_denom = _logsumexp((f + logN)[mask][:, None] - u[mask], axis=0)
        W = np.exp(f[:, None] - u - log_denom[None, :]).T  # (Ntot, K), columns sum to 1
        overlap = W.T @ W * N[None, :]
        # Asymptotic covariance (eq. D6), through the SVD of W for stability.
        U, S, Vt = np.linalg.svd(W, full_matrices=False)
        V = Vt.T
        inner = np.eye(K) - (S[:, None] * (V.T @ np.diag(N) @ V)) * S[None, :]
        theta = V @ np.diag(S) @ np.linalg.pinv(inner) @ np.diag(S) @ V.T
    if not (np.all(np.isfinite(f)) and np.all(np.isfinite(overlap)) and np.all(np.isfinite(theta))):
        raise FloatingPointError("MBAR produced a non-finite free energy, overlap or covariance")
    d = np.diag(theta)
    var = d + d[0] - 2 * theta[:, 0]
    return MbarResult(f, np.sqrt(np.clip(var, 0, None)), overlap, it)


# -- BAR -------------------------------------------------------------------------------

def bar(w_f: np.ndarray, w_r: np.ndarray) -> Tuple[float, float]:
    """Bennett's acceptance ratio for one pair of states (reduced units).

    w_f: u_1 - u_0 on samples from state 0; w_r: u_0 - u_1 on samples from
    state 1. Solves sum 1/(1 + exp(M + w_f - Δf)) = sum 1/(1 + exp(-M + w_r + Δf)),
    M = ln(n_f / n_r), by bisection; the variance is the asymptotic one of
    Shirts et al. 2003 (eq. 10)."""
    wf, wr = np.asarray(w_f, float), np.asarray(w_r, float)
    nf, nr = len(wf), len(wr)
    M = math.log(nf / nr)

    def residual(df):
        a = np.sum(1.0 / (1.0 + np.exp(np.clip(M + wf - df, -700, 700))))
        b = np.sum(1.0 / (1.0 + np.exp(np.clip(-M + wr + df, -700, 700))))
        return a - b

    lo, hi = min(wf.min(), -wr.max()) - 50, max(wf.max(), -wr.min()) + 50
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if residual(mid) > 0:
            hi = mid
        else:
            lo = mid
    df = 0.5 * (lo + hi)
    # Shirts et al. 2003, eq. 10: forward work and the negated reverse work
    # pooled through 1/(2 + 2 cosh(M + W - Δf)). (A per-direction Fermi
    # ratio used first covered the exact answer 69% of the time at 2 sigma.)
    n = nf + nr
    x = np.concatenate([M + wf - df, M - wr - df])
    mean = float(np.mean(1.0 / (2.0 + 2.0 * np.cosh(np.clip(x, -700, 700)))))
    var = (1.0 / mean - (n / nf + n / nr)) / n
    return df, math.sqrt(max(var, 0.0))


# -- thermodynamic integration ------------------------------------------------------

def ti(lambdas: np.ndarray, means: np.ndarray, sems: np.ndarray) -> Tuple[float, float]:
    """ΔG = sum over components c of integral <dH/dlambda_c> dlambda_c along
    the path through the states in order, by the trapezoid rule (Kirkwood
    1935). lambdas (K, C); means and sems (K, C), kJ/mol. The error
    propagates each window's standard error through the trapezoid weights.
    """
    K, C = lambdas.shape
    w = np.zeros((K, C))
    for i in range(K - 1):
        d = lambdas[i + 1] - lambdas[i]
        w[i] += 0.5 * d
        w[i + 1] += 0.5 * d
    return float(np.sum(w * means)), float(np.sqrt(np.sum((w * sems) ** 2)))


# -- thermodynamic length and where windows should go ---------------------------------

def segment_lengths(windows: Sequence["Window"], idx_sets: Sequence[np.ndarray]) -> np.ndarray:
    """Thermodynamic length of each step between neighbouring states
    (Shenfeld et al. 2009): the standard deviation, in kT, of the reduced
    energy gap between them, averaged over the samples of both ends. A step
    longer than about 1 kT is where overlap runs out."""
    K = len(windows)
    L = np.zeros(K - 1)
    for i in range(K - 1):
        a, b = windows[i], windows[i + 1]
        sa = np.std(a.du[i + 1, idx_sets[i]] - a.du[i, idx_sets[i]])
        sb = np.std(b.du[i, idx_sets[i + 1]] - b.du[i + 1, idx_sets[i + 1]])
        L[i] = 0.5 * (sa + sb)
    return L


#: The step length a schedule should not exceed, in kT: about where
#: neighbouring states stop sharing configurations. A chosen threshold.
TARGET_STEP_KT = 1.0


def redistribute(lambdas: np.ndarray, lengths: np.ndarray, n: int) -> np.ndarray:
    """n states along the same path, spaced to equal thermodynamic length.

    The path is the piecewise-linear curve through the current states; its
    cumulative length is known at them, so a state at length s is placed by
    interpolating along the segment that contains s. With lengths measured
    on a pilot run, this equalises the difficulty of every step, which is
    the schedule that minimises the variance of the total (Shenfeld 2009).
    """
    cum = np.concatenate([[0.0], np.cumsum(lengths)])
    out = []
    for s in np.linspace(0.0, cum[-1], n):
        i = min(int(np.searchsorted(cum, s, side="right")) - 1, len(lengths) - 1)
        seg = cum[i + 1] - cum[i]
        t = 0.0 if seg == 0 else (s - cum[i]) / seg
        out.append(lambdas[i] + t * (lambdas[i + 1] - lambdas[i]))
    return np.round(np.array(out), 4)


# -- the analysis of one leg -------------------------------------------------------

@dataclass
class LegAnalysis:
    temperature: float
    states: int
    samples_raw: List[int]
    samples_used: List[int]
    discarded: List[int]            # equilibration samples dropped per window
    inefficiency: List[float]
    dg_mbar: float                  # kJ/mol, last state minus first
    err_mbar: float
    dg_bar: float
    err_bar: float
    min_overlap: float
    min_overlap_pair: Tuple[int, int]
    dg_ti: Optional[float] = None
    err_ti: Optional[float] = None
    lengths: List[float] = field(default_factory=list)       # kT per step
    components: List[str] = field(default_factory=list)
    lambdas: Optional[List[List[float]]] = None
    forward: List[Tuple[float, float, float]] = field(default_factory=list)   # (fraction, dG, err)
    reverse: List[Tuple[float, float, float]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _stack(windows: Sequence[Window], index_sets: Sequence[np.ndarray]) -> Tuple[np.ndarray, List[int]]:
    cols, n_k = [], []
    for w, idx in zip(windows, index_sets):
        cols.append(w.du[:, idx])
        n_k.append(len(idx))
    return np.concatenate(cols, axis=1), n_k


def analyse_leg(paths: Sequence[Path]) -> LegAnalysis:
    windows = sorted((read_dhdl(p) for p in paths), key=lambda w: w.state)
    K = windows[0].du.shape[0]
    states = [w.state for w in windows]
    if states != list(range(K)):
        raise ValueError(f"windows for states {states}, but the files describe {K} states: "
                         f"missing {sorted(set(range(K)) - set(states))}")
    T = windows[0].temperature
    kt = R_KJ * T
    idx_sets, discarded, gs = [], [], []
    for w in windows:
        # Equilibration and correlation read from the energy gap to the
        # neighbouring state, the quantity BAR and MBAR actually average.
        nb = w.state + 1 if w.state + 1 < K else w.state - 1
        t0, g, _ = detect_equilibration(w.du[nb])
        sub = t0 + subsample(w.du.shape[1] - t0, g)
        idx_sets.append(sub)
        discarded.append(t0)
        gs.append(g)
    u, n_k = _stack(windows, idx_sets)
    res = mbar(u, n_k)

    # BAR over neighbours, on the same decorrelated samples.
    dg_bar, var_bar = 0.0, 0.0
    for i in range(K - 1):
        a, b = windows[i], windows[i + 1]
        wf = a.du[i + 1, idx_sets[i]] - a.du[i, idx_sets[i]]
        wr = b.du[i, idx_sets[i + 1]] - b.du[i + 1, idx_sets[i + 1]]
        d, e = bar(wf, wr)
        dg_bar += d
        var_bar += e * e

    off = [(res.overlap[i, i + 1], (i, i + 1)) for i in range(K - 1)]
    min_ov, pair = min(off)

    def partial(frac: float, from_end: bool):
        sets = []
        for s in idx_sets:
            k = max(2, int(round(len(s) * frac)))
            sets.append(s[-k:] if from_end else s[:k])
        uu, nn = _stack(windows, sets)
        r = mbar(uu, nn)
        return frac, float(r.f[-1] * kt), float(r.df[-1] * kt)

    fracs = [0.1 * i for i in range(1, 11)]
    fwd = [partial(x, False) for x in fracs]
    rev = [partial(x, True) for x in fracs]
    a = LegAnalysis(T, K, [w.du.shape[1] for w in windows], n_k, discarded, gs,
                    float(res.f[-1] * kt), float(res.df[-1] * kt), dg_bar * kt, math.sqrt(var_bar) * kt,
                    float(min_ov), pair, fwd, rev)
    if min_ov < MIN_OVERLAP:
        a.warnings.append(f"states {pair[0]} and {pair[1]} overlap {min_ov:.3f} (< {MIN_OVERLAP}): "
                          "add a window between them")
    half_f, half_r = fwd[4], rev[4]
    if abs(half_f[1] - half_r[1]) > 2 * math.hypot(half_f[2], half_r[2]):
        a.warnings.append(f"first and second halves disagree ({half_f[1]:.2f} vs {half_r[1]:.2f} kJ/mol "
                          "beyond 2 sigma): not converged")
    if abs(a.dg_mbar - a.dg_bar) > 2 * math.hypot(a.err_mbar, a.err_bar):
        a.warnings.append(f"MBAR and BAR disagree ({a.dg_mbar:.2f} vs {a.dg_bar:.2f} kJ/mol): "
                          "the states are too far apart for either to be trusted")
    L = segment_lengths(windows, idx_sets)
    a.lengths = [float(x) for x in L]
    worst = int(np.argmax(L))
    if L[worst] > TARGET_STEP_KT:
        a.warnings.append(f"step {worst}-{worst + 1} is {L[worst]:.1f} kT long (> {TARGET_STEP_KT:g}): "
                          "`caterva fep --optimise` places windows to even it out")
    if windows[0].lambdas is not None and all(w.dhdl is not None for w in windows):
        lam = windows[0].lambdas
        means = np.array([w.dhdl[:, ix].mean(axis=1) for w, ix in zip(windows, idx_sets)])
        sems = np.array([w.dhdl[:, ix].std(axis=1, ddof=1) / math.sqrt(len(ix)) for w, ix in zip(windows, idx_sets)])
        a.dg_ti, a.err_ti = ti(lam, means, sems)
        a.components = list(windows[0].components)
        a.lambdas = lam.tolist()
        if abs(a.dg_ti - a.dg_mbar) > 2 * math.hypot(a.err_ti, a.err_mbar):
            a.warnings.append(f"TI and MBAR disagree ({a.dg_ti:.2f} vs {a.dg_mbar:.2f} kJ/mol): <dH/dlambda> "
                              "is not smooth enough between windows for the trapezoid rule")
    if min(n_k) < 20:
        a.warnings.append(f"as few as {min(n_k)} independent samples in a window after subsampling")
    return a


__all__ = ["ti", "segment_lengths", "redistribute", "TARGET_STEP_KT", "Window", "read_dhdl", "statistical_inefficiency", "detect_equilibration", "subsample",
           "mbar", "MbarResult", "bar", "LegAnalysis", "analyse_leg", "MIN_OVERLAP"]
