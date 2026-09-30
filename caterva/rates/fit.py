"""Weighted nonlinear least squares for initial rates, and what its intervals mean.

WHY NOT compose/fitting.fit
---------------------------
`compose/fitting.fit` estimates constants of a reaction NETWORK: every
prediction is an ODE solve or a steady-state continuation, its precision is
declared at 1e-9, and its derivatives are finite differences sized to that.
An initial rate is an algebraic function of [S] and [I]; putting it through a
network, an integrator and a differencing step would add error to a quantity
that has none. It also refuses to estimate sigma from the residuals, which
is one of the three sources this command must offer (uncertainty.py). So
this module fits the rate laws directly. What it keeps from fitting.py is
the reasoning, and the code where the code fits: the log parameter space and
its reasons, the refusal to rescale a known error by the residual, the
chi-square tail and the normal quantile.

WHY LOG SPACE, AND WHY THERE ARE BOUNDS AS WELL
-----------------------------------------------
Every constant here is positive and spans decades, and fitting.py's three
reasons for fitting log p apply unchanged: positivity is structural rather
than a bound the optimiser sits on, a step is a factor and means the same for
a Vmax of 1e4 and a Ki of 1e-6, and the uncertainty of a constant is a factor
too. The log is not enough on its own, for a reason fitting.py never met: a
competitive inhibitor fitted with the mixed law has Ki' = infinity at its
best, and in log space infinity is an unending walk. So each log constant is
also bounded, EDGE (1e8) times beyond the range of the data that constant
acts on: Km between min([S])/1e8 and max([S])*1e8, and likewise for the
others. At the edge the constant's term in the law is below 1e-8 of the
others, which is the limit law to within rounding, and a constant that ends
there is reported as running to the edge, never as a number.

MULTI-START
-----------
Vmax enters every law linearly, so for any trial value of the other
constants the best Vmax is a weighted linear regression. The starting points
are a grid over the other constants, spread across the range of the data
they act on (Km across the substrate concentrations, Ki across the inhibitor
concentrations, n around the slope of the Hill plot), each with its best
Vmax; the best few seed full fits. The report says how many starts reached
the minimum reported, and the lowest other minimum any start found, so a
local minimum is not presented as the answer without the reader being able
to see that nothing better was found.

DERIVATIVES BY THE COMPLEX STEP
-------------------------------
Im f(x + ih) / h is the derivative of an analytic f to rounding error for any
h small enough, with no subtraction and so no step to trade truncation
against cancellation (Squire & Trapp 1998, SIAM Rev. 40:110). The rate laws
are rational functions and powers, all analytic, so the Jacobian the
covariance and the profiles are built from is exact rather than the
finite-difference estimate fitting.py has to use on an integrator.

THE INTERVAL IS THE PROFILE, NOT +-2 SE
---------------------------------------
The asymptotic standard error is reported, because it is what papers
report and what R's `nls` prints, but the interval is the profile likelihood:
fix the constant, refit the others, and find where the objective has risen
by the threshold. For Km it is routinely asymmetric, and when the data
cannot bound a constant on one side the profile never rises that far, and
the interval is reported as one-sided ("Km > [bound]: the data do not
determine an upper bound") rather than as a number with an absurd width.
Bates & Watts (1988), Nonlinear Regression Analysis and Its Applications,
is the treatment; R's `confint` on an `nls` fit computes the same interval,
and the tests reproduce its numbers.

The threshold depends on where sigma came from:

    column      chi-square rises by z^2 (the normal quantile squared;
                3.84 at 95%). The errors are known.
    replicates  chi-square rises by t^2 on the pooled degrees of freedom.
    residuals   SS rises by s^2 t^2 on n - p degrees of freedom, s^2 the
                fit's residual variance: R's profile-t interval exactly.

As in fitting.py, a known sigma is not rescaled by the residual: a model of
the wrong shape does not get wider intervals, it gets a chi-square the
report calls too large.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from caterva.rates import stats
from caterva.rates.models import (
    ROLE_INHIBITOR, ROLE_RATE, ROLE_SUBSTRATE, RateLaw,
)
from caterva.rates.table import Dataset
from caterva.rates.uncertainty import KNOWN, POOLED, RESIDUAL, Uncertainty

#: How far beyond the data's range a constant may go, as a factor, before it
#: is at the edge of the search. At 1e8 its term in the law is 1e-8 of the
#: others, the limit law to within rounding at any realistic noise.
EDGE = 1e8

#: The Hill coefficient's range. Not a physical claim: an exponent of 100
#: is a step function, and one that runs there is reported as at the edge.
HILL_RANGE = (1e-2, 1e2)

#: Imaginary step for the complex-step derivative, in log-parameter units.
COMPLEX_STEP = 1e-30

#: Starts seeded into full fits, taken from the best of the grid.
STARTS = 6

#: Two minima whose objectives differ by less than this relative amount
#: are the same minimum.
SAME_MINIMUM = 1e-7


class FitRefused(ValueError):
    """The fit was not attempted, or its result is not fit to report."""


# ---------------------------------------------------------------------------
# The problem: which rows, which constants, which weights
# ---------------------------------------------------------------------------


@dataclass
class Problem:
    law: RateLaw
    #: Printed name of each fitted parameter, e.g. "Km" or "Km [treated]".
    labels: Tuple[str, ...]
    #: The law's constant each parameter is.
    constants: Tuple[str, ...]
    #: The group each parameter belongs to, or None when shared or ungrouped.
    owners: Tuple[Optional[str], ...]
    #: Per group: (row indices, parameter index of each of the law's constants).
    maps: Tuple[Tuple[np.ndarray, Tuple[int, ...]], ...]
    s: np.ndarray
    i: np.ndarray
    v: np.ndarray
    sigma: np.ndarray
    conditions: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    uncertainty: Uncertainty
    group_names: Tuple[Optional[str], ...] = (None,)

    @property
    def n(self) -> int:
        return len(self.v)

    @property
    def p(self) -> int:
        return len(self.labels)

    @property
    def source(self) -> str:
        return self.uncertainty.source

    def predict(self, theta: np.ndarray) -> np.ndarray:
        complex_ = np.iscomplexobj(theta)
        out = np.zeros(self.n, dtype=complex if complex_ else float)
        for rows, index in self.maps:
            values = {c.name: np.exp(theta[k]) for c, k in zip(self.law.constants, index)}
            out[rows] = self.law.law(values, self.s[rows], self.i[rows])
        return out

    def residuals(self, theta: np.ndarray) -> np.ndarray:
        return (self.v - self.predict(theta)) / self.sigma

    def objective(self, theta: np.ndarray) -> float:
        r = self.residuals(np.asarray(theta, dtype=float))
        return float(np.dot(r, r))

    def jacobian(self, theta: np.ndarray) -> np.ndarray:
        """d(residual)/d(log parameter), by the complex step."""
        base = np.asarray(theta, dtype=complex)
        out = np.empty((self.n, self.p))
        for k in range(self.p):
            step = base.copy()
            step[k] += 1j * COMPLEX_STEP
            out[:, k] = self.residuals(step).imag / COMPLEX_STEP
        return out

    def distinct_conditions(self) -> int:
        return len(set(self.conditions.tolist()))

    def rows_for(self) -> Dict[int, np.ndarray]:
        """Parameter index -> the rows it acts on, for the Vmax parameters."""
        out: Dict[int, List[int]] = {}
        position = [k for k, c in enumerate(self.law.constants) if c.role == ROLE_RATE][0]
        for rows, index in self.maps:
            out.setdefault(index[position], []).extend(int(r) for r in rows)
        return {k: np.asarray(sorted(v), dtype=int) for k, v in out.items()}

    def rate_parameters(self) -> List[int]:
        return sorted(self.rows_for())


def _range(values: np.ndarray, what: str) -> Tuple[float, float]:
    positive = values[values > 0]
    if positive.size == 0:
        raise FitRefused(f"no {what} concentration in these rows is above zero, so no "
                         f"constant acting on it can be estimated")
    return float(positive.min()), float(values.max())


def _bounds_for(role: str, s: np.ndarray, i: np.ndarray, v: np.ndarray) -> Tuple[float, float]:
    if role == ROLE_RATE:
        top = float(np.max(np.abs(v)))
        return math.log(top / EDGE), math.log(top * EDGE)
    if role == ROLE_SUBSTRATE:
        low, high = _range(s, "substrate")
        return math.log(low / EDGE), math.log(high * EDGE)
    if role == ROLE_INHIBITOR:
        low, high = _range(i, "inhibitor")
        return math.log(low / EDGE), math.log(high * EDGE)
    return math.log(HILL_RANGE[0]), math.log(HILL_RANGE[1])


def build_problem(
    law: RateLaw,
    data: Dataset,
    uncertainty: Uncertainty,
    *,
    rows: Optional[Sequence[int]] = None,
    groups: Optional[Sequence[str]] = None,
    shared: frozenset = frozenset(),
) -> Problem:
    """The fit of `law` to `rows` of `data` (all rows by default), with one
    set of constants per group in `groups`, except the constants named in
    `shared`, which all groups have in common."""
    picked = list(range(len(data))) if rows is None else list(rows)
    s_all = np.asarray(data.substrate, dtype=float)
    i_all = (np.zeros(len(data)) if data.inhibitor is None
             else np.asarray(data.inhibitor, dtype=float))
    v_all = np.asarray(data.rate, dtype=float)
    sigma_all = np.asarray(uncertainty.sigma, dtype=float)
    keys: Dict[Tuple[object, ...], int] = {}
    cond_all = np.array([keys.setdefault(data.condition(r), len(keys)) for r in range(len(data))])

    s, i, v = s_all[picked], i_all[picked], v_all[picked]
    if law.needs_inhibitor and not np.any(i > 0):
        raise FitRefused(f"the {law.title} law needs rates measured with inhibitor, and none "
                         f"of these rows has any")
    if not np.any(v > 0):
        raise FitRefused("no rate in these rows is above zero, so there is no Vmax to estimate")

    names = list(groups) if groups else [None]
    position = {row: k for k, row in enumerate(picked)}
    group_rows: List[np.ndarray] = []
    for name in names:
        if name is None:
            group_rows.append(np.arange(len(picked)))
        else:
            mine = [position[r] for r in data.rows_of(name) if r in position]
            group_rows.append(np.asarray(mine, dtype=int))

    labels: List[str] = []
    constants: List[str] = []
    owners: List[Optional[str]] = []
    lower: List[float] = []
    upper: List[float] = []
    index_of: Dict[Tuple[str, Optional[str]], int] = {}
    for c in law.constants:
        together = c.name in shared or len(names) == 1
        for name, rows_g in zip(names, group_rows):
            key = (c.name, None if together else name)
            if key in index_of:
                continue
            index_of[key] = len(labels)
            labels.append(c.label if together or name is None else f"{c.label} [{name}]")
            constants.append(c.name)
            owners.append(None if together else name)
            span = np.arange(len(picked)) if together else rows_g
            lo, hi = _bounds_for(c.role, s[span], i[span], v[span])
            lower.append(lo)
            upper.append(hi)
    maps = []
    for name, rows_g in zip(names, group_rows):
        index = tuple(
            index_of[(c.name, None if (c.name in shared or len(names) == 1) else name)]
            for c in law.constants)
        maps.append((rows_g, index))
    return Problem(
        law=law, labels=tuple(labels), constants=tuple(constants), owners=tuple(owners),
        maps=tuple(maps), s=s, i=i, v=v, sigma=sigma_all[picked], conditions=cond_all[picked],
        lower=np.asarray(lower), upper=np.asarray(upper), uncertainty=uncertainty,
        group_names=tuple(names),
    )


# ---------------------------------------------------------------------------
# Starting points, from the data
# ---------------------------------------------------------------------------


def _geometric(low: float, high: float, count: int) -> List[float]:
    if count == 1 or high <= low:
        return [math.sqrt(low * high)]
    ratio = (high / low) ** (1.0 / (count - 1))
    return [low * ratio ** k for k in range(count)]


def _hill_slope(s: np.ndarray, v: np.ndarray) -> Optional[float]:
    """The slope of log(v / (V - v)) against log [S], V a little above the
    largest rate: the Hill plot's estimate of n, used only to place starts."""
    top = 1.05 * float(v.max())
    keep = (s > 0) & (v > 0) & (v < top)
    if keep.sum() < 2 or len(set(s[keep].tolist())) < 2:
        return None
    x = np.log(s[keep])
    y = np.log(v[keep] / (top - v[keep]))
    slope = float(np.polyfit(x, y, 1)[0])
    return slope if slope > 0 else None


def _hanes_woolf_km(s: np.ndarray, v: np.ndarray) -> Optional[float]:
    keep = (s > 0) & (v > 0)
    if keep.sum() < 2 or len(set(s[keep].tolist())) < 2:
        return None
    slope, intercept = np.polyfit(s[keep], s[keep] / v[keep], 1)
    if slope > 0 and intercept > 0:
        return float(intercept / slope)
    return None


def grid_starts(problem: Problem) -> List[np.ndarray]:
    """Starts for an ungrouped problem: a grid over every constant but Vmax,
    spread across the data those constants act on, each with its best Vmax."""
    law = problem.law
    s, i, v = problem.s, problem.i, problem.v
    choices: List[List[float]] = []
    for c in law.constants:
        if c.role == ROLE_RATE:
            choices.append([1.0])
        elif c.role == ROLE_SUBSTRATE:
            low, high = _range(s, "substrate")
            values = _geometric(low / 3.0, high * 3.0, 7)
            km = _hanes_woolf_km(s[i == 0] if np.any(i == 0) else s, v[i == 0] if np.any(i == 0) else v)
            if km is not None and low / EDGE < km < high * EDGE:
                values.append(km)
            choices.append(values)
        elif c.role == ROLE_INHIBITOR:
            low, high = _range(i, "inhibitor")
            choices.append(_geometric(low / 3.0, high * 3.0, 5))
        else:
            n0 = _hill_slope(s, v) or 1.0
            choices.append(sorted({n0 / 2.0, n0, 2.0 * n0, 1.0}))
    grids = np.meshgrid(*[np.log(c) for c in choices], indexing="ij")
    candidates = np.stack([g.ravel() for g in grids], axis=1)
    rate_index = [k for k, c in enumerate(law.constants) if c.role == ROLE_RATE][0]
    weight = 1.0 / problem.sigma ** 2
    scored: List[Tuple[float, np.ndarray]] = []
    for theta in candidates:
        theta = theta.copy()
        theta[rate_index] = 0.0
        shape = problem.predict(theta)
        denominator = float((weight * shape * shape).sum())
        if denominator <= 0:
            continue
        vmax = float((weight * v * shape).sum()) / denominator
        if not (vmax > 0):
            continue
        theta[rate_index] = math.log(vmax)
        theta = np.clip(theta, problem.lower, problem.upper)
        scored.append((problem.objective(theta), theta))
    scored.sort(key=lambda item: item[0])
    starts: List[np.ndarray] = []
    for _value, theta in scored:
        if all(np.max(np.abs(theta - other)) > 0.5 for other in starts):
            starts.append(theta)
        if len(starts) >= STARTS:
            break
    if not starts:
        raise FitRefused("no starting point gave a positive Vmax: the rates do not rise with "
                         "substrate anywhere a rate law of this kind can follow")
    return starts


# ---------------------------------------------------------------------------
# The fit
# ---------------------------------------------------------------------------


@dataclass
class Fit:
    problem: Problem
    theta: np.ndarray
    #: Sum of squared weighted residuals: chi-square for a known or pooled
    #: sigma, the plain residual sum of squares for RESIDUAL.
    chi2: float
    #: Per parameter: "low", "high" or None -- at the edge of the search.
    edge: Tuple[Optional[str], ...]
    #: Covariance of the log parameters; NaN rows and columns at the edge.
    cov_log: np.ndarray
    singular: np.ndarray
    starts_tried: int
    starts_agreeing: int
    #: The lowest objective any start reached at a different minimum.
    other_minimum: Optional[float] = None
    notes: List[str] = field(default_factory=list)
    #: Whether the optimiser met its tolerance at the reported minimum.
    converged: bool = True

    @property
    def law(self) -> RateLaw:
        return self.problem.law

    @property
    def n(self) -> int:
        return self.problem.n

    @property
    def p(self) -> int:
        return self.problem.p

    @property
    def dof(self) -> int:
        return self.n - self.p

    @property
    def values(self) -> np.ndarray:
        return np.exp(self.theta)

    def value(self, label: str) -> float:
        return float(self.values[self.problem.labels.index(label)])

    @property
    def scale2(self) -> float:
        """The residual variance for RESIDUAL (SS / (n - p)); 1 otherwise,
        because a known or pooled sigma is not rescaled."""
        if self.problem.source == RESIDUAL:
            return self.chi2 / self.dof if self.dof > 0 else float("nan")
        return 1.0

    @property
    def residual_se(self) -> Optional[float]:
        return math.sqrt(self.scale2) if self.problem.source == RESIDUAL and self.dof > 0 else None

    @property
    def se_log(self) -> np.ndarray:
        return np.sqrt(np.diag(self.cov_log))

    @property
    def se(self) -> np.ndarray:
        """Asymptotic standard errors in the constants' own units (the delta
        method from log space, exact at first order: se(p) = p se(log p))."""
        return self.values * self.se_log

    def correlation(self) -> np.ndarray:
        d = self.se_log
        with np.errstate(invalid="ignore", divide="ignore"):
            return self.cov_log / np.outer(d, d)

    @property
    def condition_number(self) -> float:
        if self.singular.size == 0 or self.singular[-1] <= 0:
            return float("inf")
        return float(self.singular[0] / self.singular[-1])

    def critical(self, level: float) -> float:
        """The quantile the intervals use: normal for a known sigma, t on the
        pooled degrees of freedom, t on n - p for the residuals."""
        if self.problem.source == KNOWN:
            return stats.z_for(level)
        if self.problem.source == POOLED:
            return stats.t_for(level, self.problem.uncertainty.dof)
        return stats.t_for(level, self.dof)

    def threshold(self, level: float) -> float:
        """How far the normalised objective may rise inside the interval."""
        return self.critical(level) ** 2

    def normalised(self, objective: float) -> float:
        return (objective - self.chi2) / self.scale2

    def gof_p(self) -> Optional[float]:
        """P(chi-square >= observed) under the model and a KNOWN sigma. None
        for the other two sources: a pooled sigma's chi-square is mostly the
        pure error it was estimated from, and a residual sigma's is n - p by
        construction."""
        if self.problem.source != KNOWN or self.dof <= 0:
            return None
        return stats.chi2_tail(self.chi2, self.dof)


def _least_squares(residual: Callable[[np.ndarray], np.ndarray], n: int, x0: np.ndarray,
                   lower: np.ndarray, upper: np.ndarray) -> Tuple[np.ndarray, bool]:
    """scipy's trust-region-reflective least squares with a complex-step
    Jacobian, on y = x - x0 + 1.

    The shift: the optimiser's first trust region is the length of its
    starting vector, so a start whose log constants are all near zero (every
    constant near 1 in its unit, as a noise-free test hits exactly) gave it
    a region of 1e-15 and it stopped where it began, reporting convergence.
    Shifted, every start is one unit (a factor e) from the origin."""
    from scipy.optimize import least_squares

    offset = x0 - 1.0

    def shifted(y):
        return residual(y + offset)

    def jacobian(y):
        base = np.asarray(y, dtype=complex)
        out = np.empty((n, len(base)))
        for k in range(len(base)):
            step = base.copy()
            step[k] += 1j * COMPLEX_STEP
            out[:, k] = shifted(step).imag / COMPLEX_STEP
        return out

    outcome = least_squares(shifted, x0 - offset, jac=jacobian,
                            bounds=(lower - offset, upper - offset), method="trf",
                            xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=4000)
    return outcome.x + offset, bool(outcome.status > 0)


def _solve(problem: Problem, theta0: np.ndarray, *, free: Optional[np.ndarray] = None,
           assemble: Optional[Callable[[np.ndarray], np.ndarray]] = None,
           linear: Sequence[int] = ()) -> Tuple[np.ndarray, float, bool]:
    """Least squares over the `free` coordinates (all, by default); returns
    (full theta, objective, converged).

    VARIABLE PROJECTION. Each Vmax in `linear` multiplies its rows' rate law
    and appears nowhere else, so for any value of the other constants its
    best value is a weighted linear regression, in closed form (Golub &
    Pereyra 1973, SIAM J. Numer. Anal. 10:413). The optimiser then searches
    only the other constants, which is both faster -- a Km profile of
    Michaelis-Menten needs no search at all -- and better conditioned. The
    optimum is the same; the full least squares is used instead whenever a
    projected Vmax would not be positive or would leave the search's range."""
    if free is None:
        free = np.arange(problem.p)

        def assemble(x):  # noqa: E306 - the identity on all coordinates
            return x
    lower, upper = problem.lower[free], problem.upper[free]
    x0 = np.clip(np.asarray(theta0, dtype=float)[free], lower, upper)
    position = {int(k): n for n, k in enumerate(free)}
    projected = [int(k) for k in linear if int(k) in position]
    if projected:
        answer = _projected(problem, x0, free, assemble, projected, position, lower, upper)
        if answer is not None:
            return answer
    if len(x0) == 0:
        theta = assemble(np.asarray([], dtype=float))
        return theta, problem.objective(theta), True
    x, ok = _least_squares(lambda x: problem.residuals(assemble(x)), problem.n, x0, lower, upper)
    theta = assemble(x)
    return theta, problem.objective(theta), ok


def _projected(problem: Problem, x0: np.ndarray, free: np.ndarray,
               assemble: Callable[[np.ndarray], np.ndarray], projected: List[int],
               position: Dict[int, int], lower: np.ndarray,
               upper: np.ndarray) -> Optional[Tuple[np.ndarray, float, bool]]:
    rows = problem.rows_for()
    others = [n for n, k in enumerate(free) if int(k) not in projected]
    weight = 1.0 / problem.sigma ** 2

    def fill(y: np.ndarray) -> np.ndarray:
        x = np.zeros(len(free), dtype=complex if np.iscomplexobj(y) else float)
        x[others] = y
        return x

    def split(y: np.ndarray) -> Tuple[np.ndarray, Dict[int, Any]]:
        shape = problem.predict(assemble(fill(y)))
        fitted = shape.copy()
        scales: Dict[int, Any] = {}
        for k in projected:
            r = rows[k]
            denominator = (weight[r] * shape[r] * shape[r]).sum()
            scales[k] = (weight[r] * problem.v[r] * shape[r]).sum() / denominator
            fitted[r] = scales[k] * shape[r]
        return (problem.v - fitted) / problem.sigma, scales

    y0 = x0[others]
    ok = True
    if others:
        y, ok = _least_squares(lambda y: split(y)[0], problem.n, y0, lower[others], upper[others])
    else:
        y = y0
    with np.errstate(all="ignore"):
        _residual, scales = split(np.asarray(y, dtype=float))
    x = fill(np.asarray(y, dtype=float))
    for k in projected:
        value = float(np.real(scales[k]))
        n = position[k]
        if not (math.isfinite(value) and value > 0):
            return None
        log_value = math.log(value)
        if not (lower[n] <= log_value <= upper[n]):
            return None
        x[n] = log_value
    theta = assemble(x)
    return theta, problem.objective(theta), ok


def _edges(problem: Problem, theta: np.ndarray) -> Tuple[Optional[str], ...]:
    out: List[Optional[str]] = []
    for value, lo, hi in zip(theta, problem.lower, problem.upper):
        if value - lo < 1e-3:
            out.append("low")
        elif hi - value < 1e-3:
            out.append("high")
        else:
            out.append(None)
    return tuple(out)


def _covariance(problem: Problem, theta: np.ndarray, edge: Sequence[Optional[str]],
                scale2: float) -> Tuple[np.ndarray, np.ndarray]:
    jac = problem.jacobian(theta)
    live = [k for k, e in enumerate(edge) if e is None]
    cov = np.full((problem.p, problem.p), np.nan)
    if not live:
        return cov, np.array([])
    sub = jac[:, live]
    _u, singular, vt = np.linalg.svd(sub, full_matrices=False)
    if singular.size == 0 or singular[0] <= 0:
        return cov, singular
    keep = singular > singular[0] * 1e-12
    inverse = (vt[keep].T / singular[keep] ** 2) @ vt[keep]
    if not keep.all():
        inverse[:] = np.nan
    block = inverse * scale2
    for a, ka in enumerate(live):
        for b, kb in enumerate(live):
            cov[ka, kb] = block[a, b]
    return cov, singular


def fit(problem: Problem, starts: Optional[Sequence[np.ndarray]] = None) -> Fit:
    """The best fit of `problem` from every start, with its covariance.

    Refuses when there are fewer distinct conditions than constants (no
    number of replicates can separate constants that one condition's rate
    ties together; compose/fitting.py's counting check), or, with sigma from
    the residuals, when nothing is left to estimate it from."""
    distinct = problem.distinct_conditions()
    if distinct < problem.p:
        raise FitRefused(
            f"the {problem.law.title} law has {problem.p} constant(s) "
            f"({', '.join(problem.labels)}) and these rows hold {distinct} distinct "
            f"condition(s). Replicates shrink the error on one rate; they do not add a "
            f"second shape for the law to match, so at least {problem.p} different "
            f"substrate (and inhibitor) concentrations are needed.")
    if problem.source == RESIDUAL and problem.n <= problem.p:
        raise FitRefused(
            f"sigma from the residuals needs more rows than constants: {problem.n} row(s) "
            f"and {problem.p} constant(s) leave nothing to estimate the scatter from")
    seeds = list(starts) if starts is not None else grid_starts(problem)
    results: List[Tuple[float, np.ndarray, bool]] = []
    linear = problem.rate_parameters()
    for seed in seeds:
        theta, value, ok = _solve(problem, np.asarray(seed, dtype=float), linear=linear)
        if np.all(np.isfinite(theta)) and math.isfinite(value):
            results.append((value, theta, ok))
    if not results:
        raise FitRefused(f"the {problem.law.title} fit failed from every start")
    results.sort(key=lambda item: item[0])
    best_value, best_theta, converged = results[0]
    tolerance = SAME_MINIMUM * max(best_value, 1e-12) + 1e-12
    agreeing = sum(1 for value, _t, _ok in results if value - best_value <= tolerance)
    others = [value for value, theta, _ok in results
              if value - best_value > tolerance and np.max(np.abs(theta - best_theta)) > 1e-3]
    edge = _edges(problem, best_theta)
    dof = problem.n - problem.p
    scale2 = best_value / dof if problem.source == RESIDUAL and dof > 0 else 1.0
    cov, singular = _covariance(problem, best_theta, edge, scale2)
    fitted = Fit(problem=problem, theta=best_theta, chi2=best_value, edge=edge, cov_log=cov,
                 singular=singular, starts_tried=len(results), starts_agreeing=agreeing,
                 other_minimum=min(others) if others else None, converged=converged)
    if not converged:
        fitted.notes.append(
            "the optimiser used its whole budget of evaluations at this minimum without meeting "
            "its tolerance; the estimates are where it stopped, which is near a minimum and may "
            "not be one")
    return fitted


# ---------------------------------------------------------------------------
# Profile-likelihood intervals
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Interval:
    """A profile interval of one constant or one product of constants.

    `low` or `high` is None when the profile never rises to the threshold
    on that side before the constant reaches the edge of the search: the
    data do not bound it there, and nothing is printed as though they did.
    """

    label: str
    estimate: float
    low: Optional[float]
    high: Optional[float]
    level: float
    #: Asymptotic standard error in the constant's units, or None.
    se: Optional[float] = None

    @property
    def bounded(self) -> bool:
        return self.low is not None and self.high is not None

    def contains(self, value: float) -> bool:
        return ((self.low is None or value >= self.low) and
                (self.high is None or value <= self.high))

    def describe(self, unit: str = "") -> str:
        u = f" {unit}" if unit else ""
        if self.low is None and self.high is None:
            return f"{self.label}: not determined by these data in either direction"
        if self.high is None:
            return (f"{self.label} > {self.low:.4g}{u}: the data do not determine an upper bound")
        if self.low is None:
            return (f"{self.label} < {self.high:.4g}{u}: the data do not determine a lower bound")
        return f"{self.label} {self.low:.4g} to {self.high:.4g}{u}"


class _BetterMinimum(Exception):
    def __init__(self, theta: np.ndarray) -> None:
        super().__init__("the profile found a lower minimum")
        self.theta = theta


def profile(fitted: Fit, exponents: Mapping[int, float], level: float,
            label: Optional[str] = None) -> Interval:
    """The profile interval of prod p_k ** e_k over `exponents` = {k: e_k}.

    One constant is the case {k: 1}. A product (Vmax/Km is {Vmax: 1, Km: -1})
    is profiled by eliminating the constant with the largest exponent: fix
    the log of the product at t, solve for that constant, refit the rest.
    """
    problem = fitted.problem
    p = problem.p
    c = np.zeros(p)
    for k, e in exponents.items():
        c[k] = float(e)
    j = int(np.argmax(np.abs(c)))
    others = np.array([k for k in range(p) if k != j], dtype=int)
    single = int(np.count_nonzero(c)) == 1
    t0 = float(c @ fitted.theta)
    q = fitted.threshold(level)
    se_t = math.sqrt(float(c @ np.nan_to_num(fitted.cov_log) @ c)) if np.all(
        np.isfinite(fitted.cov_log[np.ix_(np.nonzero(c)[0], np.nonzero(c)[0])])) else float("nan")
    name = label or " * ".join(
        (problem.labels[k] if e == 1 else f"{problem.labels[k]}^{e:g}") for k, e in exponents.items())
    estimate = math.exp(t0)
    se_linear = estimate * se_t if math.isfinite(se_t) else None

    def assemble_for(t: float) -> Callable[[np.ndarray], np.ndarray]:
        def assemble(x: np.ndarray) -> np.ndarray:
            theta = np.zeros(p, dtype=complex if np.iscomplexobj(x) else float)
            theta[others] = x
            theta[j] = (t - (c[others] @ x if others.size else 0.0)) / c[j]
            return theta
        return assemble

    cache: Dict[float, Tuple[float, np.ndarray]] = {t0: (0.0, fitted.theta.copy())}
    linear = [k for k in problem.rate_parameters() if k != j and c[k] == 0]

    def delta(t: float) -> float:
        if t in cache:
            return cache[t][0]
        nearest = min(cache, key=lambda u: abs(u - t))
        start = cache[nearest][1].copy()
        theta, value, _ok = _solve(problem, start, free=others, assemble=assemble_for(t),
                                   linear=linear)
        d = fitted.normalised(value)
        if d < -1e-7 * max(1.0, abs(fitted.chi2) / max(fitted.scale2, 1e-300)):
            raise _BetterMinimum(theta)
        cache[t] = (d, theta)
        return d

    limit = math.log(EDGE) + 2.0 * math.log(EDGE)
    def walled(theta: np.ndarray) -> bool:
        """Whether the search's edge, rather than the data, holds this
        profile point up: some other constant sits at its edge and the
        objective would still fall if it could go further. A constant at
        the edge whose term has vanished (Ki' of a competitive inhibitor)
        exerts no such pull and does not count; Km at the edge of a fit to
        rates far below Km, with Vmax held off the ratio the data fix, does."""
        at = [k for k in others
              if theta[k] - problem.lower[k] < 1e-3 or problem.upper[k] - theta[k] < 1e-3]
        if not at:
            return False
        real = np.asarray(theta, dtype=float)
        gradient = 2.0 * problem.residuals(real) @ problem.jacobian(real) / fitted.scale2
        tolerance = 1e-3 * q
        for k in at:
            if problem.upper[k] - real[k] < 1e-3 and gradient[k] < -tolerance:
                return True
            if real[k] - problem.lower[k] < 1e-3 and gradient[k] > tolerance:
                return True
        return False

    def side(direction: int) -> Optional[float]:
        if single:
            wall = problem.upper[j] if direction > 0 else problem.lower[j]
            reach = abs(wall - t0) * abs(c[j])
            if reach < 1e-3:
                return None
        else:
            reach = limit
        # The first step lands where the quadratic (Wald) approximation puts
        # the crossing; for a well-determined constant the profile crosses
        # within a step or two of it.
        step = math.sqrt(q) * se_t if math.isfinite(se_t) and se_t > 0 else 0.1
        step = min(max(step, 1e-4), 1.0)
        previous = t0
        travelled = 0.0
        while True:
            travelled = min(travelled + step, reach)
            t = t0 + direction * travelled
            d = delta(t)
            if d >= q:
                from scipy.optimize import brentq

                root = brentq(lambda u: delta(u) - q, min(previous, t), max(previous, t),
                              xtol=1e-9, rtol=1e-10, maxiter=200)
                delta(root)
                # The wall is judged AT the crossing, not at the step that
                # overshot it. A step can land where another constant has
                # reached the search's edge (the Hill law's n profiled down
                # a long step sends K0.5 past 1e8 times the data) while the
                # profile crossed the threshold earlier, with every constant
                # inside the box: that crossing is the data's bound. Only a
                # crossing the edge itself holds up is not evidence, and
                # that side is then unbounded.
                if walled(cache[root][1]):
                    return None
                return math.exp(root)
            if travelled >= reach:
                return None
            previous = t
            step *= 1.6

    low = side(-1)
    high = side(+1)
    return Interval(name, estimate, low, high, level, se_linear)


def refit_from(problem: Problem, fitted: Fit, theta: np.ndarray) -> Fit:
    """Refit with an added start where a profile found a lower minimum; the
    note says so, because the multi-start had missed it."""
    again = fit(problem, starts=[theta, fitted.theta])
    again.notes.append(
        "a profile found a lower minimum than every start had; the fit was restarted "
        "from it, and the estimates are from that minimum")
    return again


def profile_all(fitted: Fit, level: float) -> Tuple[Fit, List[Interval]]:
    """Every constant's interval. If a profile finds a lower minimum the fit
    is redone from it (once), and every interval recomputed."""
    for _attempt in range(2):
        try:
            intervals = [profile(fitted, {k: 1.0}, level, fitted.problem.labels[k])
                         for k in range(fitted.p)]
            return fitted, intervals
        except _BetterMinimum as better:
            fitted = refit_from(fitted.problem, fitted, better.theta)
    intervals = [profile(fitted, {k: 1.0}, level, fitted.problem.labels[k]) for k in range(fitted.p)]
    return fitted, intervals


def profile_product(fitted: Fit, exponents: Mapping[int, float], level: float,
                    label: str) -> Optional[Interval]:
    try:
        return profile(fitted, exponents, level, label)
    except _BetterMinimum:
        return None


# ---------------------------------------------------------------------------
# Curves
# ---------------------------------------------------------------------------


def curve(fitted: Fit, s: np.ndarray, i: np.ndarray, group: Optional[str], level: float
          ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The fitted rate on a grid, with a first-order band: the delta method
    on log v, so the band is multiplicative like the intervals and cannot
    go below zero. It is ASYMPTOTIC and pointwise, and says so wherever it
    is exported: it is not a profile interval and not a band for the whole
    curve at once."""
    problem = fitted.problem
    index = None
    for (_rows, idx), name in zip(problem.maps, problem.group_names):
        if name == group:
            index = idx
    if index is None:
        index = problem.maps[0][1]
    law = problem.law
    s = np.asarray(s, dtype=float)
    i = np.asarray(i, dtype=float)

    def log_rate(theta: np.ndarray) -> np.ndarray:
        values = {cst.name: np.exp(theta[k]) for cst, k in zip(law.constants, index)}
        return np.log(law.law(values, s, i))

    with np.errstate(divide="ignore", invalid="ignore"):
        centre = np.real(np.exp(log_rate(fitted.theta.astype(complex))))
        grad = np.zeros((len(s), fitted.p))
        for k in range(fitted.p):
            step = fitted.theta.astype(complex)
            step[k] += 1j * COMPLEX_STEP
            grad[:, k] = log_rate(step).imag / COMPLEX_STEP
        cov = np.nan_to_num(fitted.cov_log)
        sd = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", grad, cov, grad), 0.0))
        factor = np.exp(fitted.critical(level) * sd)
        low = np.where(centre > 0, centre / factor, 0.0)
        high = np.where(centre > 0, centre * factor, 0.0)
    return centre, low, high


__all__ = [
    "EDGE", "HILL_RANGE", "FitRefused", "Problem", "Fit", "Interval", "build_problem",
    "grid_starts", "fit", "profile", "profile_all", "profile_product", "curve",
]
