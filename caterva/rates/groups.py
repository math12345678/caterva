"""Two or more groups of rates, and which constants differ between them.

THE QUESTION
------------
Wild type against a mutant, treated against untreated: the same law fitted
to each group separately gives two Vmax and two Km, and they will differ,
because two noisy datasets always do. Whether they differ by more than the
noise is a test: fit a model in which one constant is SHARED by every group
and the rest are not, and ask how much worse it fits than the model in which
nothing is shared. The shared model is the separate one with G - 1
equalities imposed, all interior, so the reference is chi-square on G - 1
degrees of freedom with sigma known, and the extra-sum-of-squares F test
with sigma estimated.

Bates & Watts (1988, Nonlinear Regression Analysis and Its Applications)
analyse the puromycin data of examples/rates/puromycin.csv exactly so: does
puromycin change Vm only, or K as well? The test here asks the same
question of any law and any constant, one constant at a time, and then of
all of them at once (do the groups differ at all?).

WHAT THE TEST ASSUMES, SAID IN THE REPORT
-----------------------------------------
With sigma from the residuals the F test's denominator is the separate fits'
pooled scatter, which assumes both groups are measured with the same
precision. Each group's own fit is still reported with its own residual
standard error, as R's nls reports it, so a reader can see whether that is
so; the test does not check it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from caterva.rates import stats
from caterva.rates.fit import Fit, FitRefused, Interval, build_problem, fit, profile_all
from caterva.rates.models import RateLaw
from caterva.rates.table import Dataset
from caterva.rates.uncertainty import KNOWN, POOLED, Uncertainty


@dataclass
class SharedTest:
    #: The constant shared (its label), or "all" for every constant.
    constant: str
    fit: Fit
    intervals: List[Interval]
    statistic: float
    df: tuple
    reference: str
    p: Optional[float]
    rejected: bool


@dataclass
class GroupComparison:
    law: RateLaw
    groups: List[str]
    separate: Fit
    tests: List[SharedTest] = field(default_factory=list)
    sentences: List[str] = field(default_factory=list)
    refused: Optional[str] = None


def _test(separate: Fit, shared: Fit, significance: float) -> tuple:
    q = separate.p - shared.p
    rise = max(shared.chi2 - separate.chi2, 0.0)
    source = separate.problem.source
    if source == KNOWN:
        return rise, (q,), f"chi-square rise on {q} df", stats.chi2_tail(rise, q)
    if source == POOLED:
        nu = separate.problem.uncertainty.dof
        f = rise / q
        return f, (q, nu), f"F({q}, {nu})", stats.f_tail(f, q, nu)
    dof = separate.dof
    f = (rise / q) / (separate.chi2 / dof) if dof > 0 and separate.chi2 > 0 else float("inf")
    return f, (q, dof), f"F({q}, {dof})", (stats.f_tail(f, q, dof) if math.isfinite(f) else 0.0)


def compare_groups(law: RateLaw, data: Dataset, uncertainty: Uncertainty,
                   per_group: Dict[str, Fit], level: float, significance: float) -> GroupComparison:
    """Fit `law` with each constant shared in turn, and all at once, and test
    each against the fully separate fit. `per_group` holds each group's own
    fit of `law`, whose estimates seed every combined fit."""
    groups = list(per_group)
    constants = [c.name for c in law.constants]
    separate_problem = build_problem(law, data, uncertainty, groups=groups)
    seed = np.zeros(separate_problem.p)
    for k, (name, owner) in enumerate(zip(separate_problem.constants, separate_problem.owners)):
        seed[k] = per_group[owner].theta[per_group[owner].problem.constants.index(name)]
    separate = fit(separate_problem, starts=[seed])
    out = GroupComparison(law, groups, separate)
    if separate.dof <= 0:
        out.refused = ("there are no degrees of freedom left after fitting every group "
                       "separately, so nothing can be tested")
        return out

    def seeds_for(shared: frozenset) -> List[np.ndarray]:
        problem = build_problem(law, data, uncertainty, groups=groups, shared=shared)
        starts = []
        for pick in [None] + groups:
            theta = np.zeros(problem.p)
            for k, (name, owner) in enumerate(zip(problem.constants, problem.owners)):
                if owner is not None:
                    source = per_group[owner]
                    theta[k] = source.theta[source.problem.constants.index(name)]
                elif pick is None:
                    theta[k] = float(np.mean([f.theta[f.problem.constants.index(name)]
                                              for f in per_group.values()]))
                else:
                    source = per_group[pick]
                    theta[k] = source.theta[source.problem.constants.index(name)]
            starts.append(theta)
        return starts

    for name in constants + ["all"]:
        shared = frozenset(constants if name == "all" else [name])
        problem = build_problem(law, data, uncertainty, groups=groups, shared=shared)
        try:
            fitted = fit(problem, starts=seeds_for(shared))
            fitted, intervals = profile_all(fitted, level)
        except FitRefused as exc:
            out.sentences.append(f"sharing {name} could not be fitted: {exc}")
            continue
        statistic, df, reference, p = _test(separate, fitted, significance)
        label = "all" if name == "all" else law.constant(name).label
        out.tests.append(SharedTest(label, fitted, intervals, statistic, df, reference, p,
                                    p is not None and p < significance))
    out.sentences[:0] = _sentences(out, law, significance)
    return out


def _sentences(out: GroupComparison, law: RateLaw, significance: float) -> List[str]:
    lines = []
    differ = [t for t in out.tests if t.constant != "all" and t.rejected]
    same = [t for t in out.tests if t.constant != "all" and not t.rejected]
    everything = next((t for t in out.tests if t.constant == "all"), None)
    names = " and ".join(out.groups)
    if everything is not None and not everything.rejected:
        lines.append(
            f"The data do not show {names} to differ at all: one set of constants for every group "
            f"fits as well as separate ones ({everything.reference} = {everything.statistic:.3g}, "
            f"p = {everything.p:.3g}).")
    for t in differ:
        lines.append(
            f"{t.constant} differs between {names}: sharing it fits worse than separate values "
            f"({t.reference} = {t.statistic:.3g}, p = {t.p:.3g}).")
    for t in same:
        shared_iv = next((iv for iv in t.intervals if iv.label == t.constant), None)
        where = ""
        if shared_iv is not None:
            if shared_iv.bounded:
                where = (f"; the shared fit gives {t.constant} = {shared_iv.estimate:.4g} "
                         f"({shared_iv.low:.4g} to {shared_iv.high:.4g})")
            else:
                where = f"; the shared fit gives {shared_iv.describe()}"
        lines.append(
            f"{t.constant}: no difference between {names} detectable by these data "
            f"({t.reference} = {t.statistic:.3g}, p = {t.p:.3g}){where}. Not detected is not the "
            f"same as equal.")
    return lines


__all__ = ["SharedTest", "GroupComparison", "compare_groups"]
