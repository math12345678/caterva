"""Which mechanisms the data rule out, which they cannot tell apart, and why.

NESTED, ON THE BOUNDARY, OR NOT NESTED AT ALL
---------------------------------------------
Mixed inhibition contains the other three, each by one constraint
(models.NESTINGS), and the constraints are of two kinds that need different
tests:

  noncompetitive   Ki = Ki'. An equality between two constants that can
                   each take any positive value: an INTERIOR restriction.
                   The likelihood ratio (the rise in chi-square from mixed
                   to noncompetitive) is chi-square with 1 degree of freedom
                   when sigma is known; with sigma estimated it is the
                   extra-sum-of-squares F test on 1 and the estimate's
                   degrees of freedom.

  competitive      Ki' -> infinity, and uncompetitive, Ki -> infinity. The
  uncompetitive    restricted value is the EDGE of the parameter space (1/Ki'
                   = 0, and 1/Ki' cannot go below it). There the ordinary
                   reference is wrong: under the restriction, the general
                   fit lands exactly on the boundary in half of all datasets
                   and the statistic is then zero, so its distribution is
                   the 50:50 mixture of a point mass at zero and chi-square
                   with 1 degree of freedom (Self & Liang 1987, J. Am. Stat.
                   Assoc. 82:605). The p-value is half the ordinary one.
                   Using chi-square(1) instead would double every p-value and
                   keep the simpler mechanism when the data had excluded it.
                   With sigma estimated the same halving is applied to the F
                   reference (the signed square root of the statistic is t,
                   and the test is one-sided).

  competitive vs   neither is the other with a constant fixed, so no
  uncompetitive    likelihood-ratio test between them exists. Their fit
                   statistics are printed side by side, and the report says
                   in words that this is a description and not a test.

Without an inhibitor the same holds for the two alternatives to
Michaelis-Menten: substrate inhibition contains it at Ksi -> infinity (a
boundary), and the Hill law contains it at n = 1 (interior).

AICc IS PRINTED HERE, AND ONLY AS A DESCRIPTION
-----------------------------------------------
compare.py leaves information criteria out, for two reasons, and states the
conditions under which one could be added. The first reason, that it needs
data, does not hold here: this is fitted data. The second does: AIC ranks
the models it is handed and says nothing about whether any is right. So
AICc (Akaike's criterion with the small-sample correction of Hurvich & Tsai
1989, Biometrika 76:297) is printed ONLY for the comparisons no test can
make, as a difference from the lowest, with its assumptions attached: the
models were fitted to the SAME rates; the residuals are independent and
normal with the stated sigma; the sample is not small against the number of
constants (the correction helps and does not make 8 rates enough for 4
constants); and a lower value means expected to predict new rates better,
not true. It never decides a verdict, and there are no Akaike weights,
which read as probabilities that a mechanism is right.

LACK OF FIT
-----------
With replicates, the residual sum of squares splits into pure error (the
scatter of replicates about their own mean, which no model of the conditions
can remove) and lack of fit (the rest), and their ratio, each over its
degrees of freedom, is F on (conditions - constants) and (rows - conditions)
degrees of freedom (Draper & Smith, Applied Regression Analysis, Wiley).
The ratio does not depend on the scale of sigma, so it asks whether the
law's SHAPE is wrong whatever the error bars say, and it is the one model
check available when sigma was estimated from the residuals.

VERDICT FIRST
-------------
A mechanism is ruled out when its test against the general law gives p below
the significance level (0.05 by default, a convention stated as one; every
p-value is printed so a reader can apply another). What remains is either
one mechanism, or several the data cannot tell apart, and for the second
case the report names the measurement that would: inhibited rates at [S]
well above Km separate competitive from the rest (competition is overcome
there and nothing else is), and inhibited rates at [S] well below Km
separate uncompetitive from the rest.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from caterva.rates import stats
from caterva.rates.fit import Fit, Interval
from caterva.rates.models import NESTINGS, Nesting, law_for
from caterva.rates.uncertainty import KNOWN, POOLED, RESIDUAL, pure_error

DEFAULT_SIGNIFICANCE = 0.05


@dataclass(frozen=True)
class Test:
    nesting: Nesting
    statistic: float
    reference: str
    p: Optional[float]
    rejected: bool

    def sentence(self) -> str:
        kind = ("a boundary restriction, so the reference is the 50:50 mixture of chi-square(0) "
                "and its one-degree-of-freedom form" if self.nesting.boundary
                else "an interior restriction")
        verdict = ("ruled out" if self.rejected else "not ruled out")
        p = "p not computable" if self.p is None else f"p = {self.p:.3g}"
        return (f"{self.nesting.special} against {self.nesting.general} "
                f"({self.nesting.constraint}; {kind}): {self.reference} = {self.statistic:.4g}, "
                f"{p}: {verdict}.")


@dataclass(frozen=True)
class LackOfFit:
    f: float
    df_lof: int
    df_pe: int
    p: Optional[float]
    ss_lof: float
    ss_pe: float

    def sentence(self, significance: float) -> str:
        head = (f"lack of fit F = {self.f:.3g} on {self.df_lof} and {self.df_pe} degrees of "
                f"freedom, p = {self.p:.3g}" if self.p is not None
                else f"lack of fit F = {self.f:.3g} on {self.df_lof} and {self.df_pe} degrees of freedom")
        if self.p is not None and self.p < significance:
            return (head + ": the rates depart from this law's shape by more than the replicates "
                    "scatter, whatever sigma is.")
        return head + ": no departure from this law's shape beyond the replicates' own scatter."


def lack_of_fit(fitted: Fit) -> Optional[LackOfFit]:
    """The pure-error F test, or None without replicates or spare conditions."""
    problem = fitted.problem
    ss_pe, df_pe, m = pure_error(problem.v, problem.sigma, problem.conditions.tolist())
    df_lof = m - problem.p
    if df_pe <= 0 or df_lof <= 0 or ss_pe <= 0:
        return None
    ss_res = float(np.dot(problem.residuals(fitted.theta), problem.residuals(fitted.theta)))
    ss_lof = max(ss_res - ss_pe, 0.0)
    f = (ss_lof / df_lof) / (ss_pe / df_pe)
    return LackOfFit(f, df_lof, df_pe, stats.f_tail(f, df_lof, df_pe), ss_lof, ss_pe)


def aicc(fitted: Fit) -> Optional[float]:
    """AICc: chi-square + 2k (+ correction) for a known or pooled sigma; with
    sigma from the residuals, n ln(SS/n) + 2(k+1) (+ correction), sigma
    counted as a parameter. None when the correction's denominator is not
    positive -- too few rates for the constants."""
    n, k = fitted.n, fitted.p
    if fitted.problem.source == RESIDUAL:
        k += 1
        if fitted.chi2 <= 0:
            return None
        base = n * math.log(fitted.chi2 / n) + 2 * k
    else:
        base = fitted.chi2 + 2 * k
    if n - k - 1 <= 0:
        return None
    return base + 2.0 * k * (k + 1) / (n - k - 1)


def nested_test(general: Fit, special: Fit, nesting: Nesting, significance: float) -> Test:
    """The test of `special` against `general` (module docstring)."""
    q = general.p - special.p
    source = general.problem.source
    rise = max(special.chi2 - general.chi2, 0.0)
    if source == KNOWN:
        statistic = rise
        one = stats.chi2_tail(statistic, q)
        reference = f"chi-square rise on {q} df" if not nesting.boundary else "chi-square rise"
    elif source == POOLED:
        nu = general.problem.uncertainty.dof
        statistic = rise / q
        one = stats.f_tail(statistic, q, nu)
        reference = f"F({q}, {nu})"
    else:
        dof = general.dof
        statistic = (rise / q) / (general.chi2 / dof) if dof > 0 and general.chi2 > 0 else float("inf")
        one = stats.f_tail(statistic, q, dof) if math.isfinite(statistic) else 0.0
        reference = f"F({q}, {dof})"
    p = stats.boundary_tail(one, statistic) if nesting.boundary else one
    rejected = p is not None and p < significance
    return Test(nesting, statistic, reference, p, rejected)


@dataclass
class Verdict:
    #: Law names the data rule out.
    ruled_out: List[str] = field(default_factory=list)
    #: Law names still standing.
    standing: List[str] = field(default_factory=list)
    #: Law names whose estimates are reported, in order.
    reported: List[str] = field(default_factory=list)
    sentences: List[str] = field(default_factory=list)
    #: What to measure to decide what is left undecided.
    advice: List[str] = field(default_factory=list)
    #: Non-nested comparisons described (not tested).
    described: List[str] = field(default_factory=list)


def _p(test: Optional[Test]) -> str:
    if test is None or test.p is None:
        return "not tested"
    if test.p <= 0:
        return "p < 1e-300"
    return f"p = {test.p:.3g}"


def _describe_untestable(names: Sequence[str], fits: Dict[str, Fit],
                         criteria: Dict[str, Optional[float]]) -> str:
    source = next(iter(fits.values())).problem.source
    what = "residual sum of squares" if source == RESIDUAL else "chi-square"
    parts = []
    finite = [criteria[n] for n in names if criteria.get(n) is not None]
    best = min(finite) if finite else None
    for name in names:
        c = criteria.get(name)
        delta = "" if c is None or best is None else f", AICc {c - best:+.2f} from the lowest"
        parts.append(f"{name}: {what} {fits[name].chi2:.4g} with {fits[name].p} constants{delta}")
    return ("Not nested, so not tested against each other -- neither is the other with a constant "
            "fixed, and no likelihood-ratio test between them exists: " + "; ".join(parts) +
            ". This is a description, not a test: a lower AICc means expected to predict new "
            "rates better under the stated assumptions, not a mechanism shown to be right.")


def inhibition_verdict(fits: Dict[str, Fit], intervals: Dict[str, List[Interval]],
                       tests: Dict[str, Test], significance: float, units: Dict[str, str]) -> Verdict:
    """The verdict for rates with an inhibitor, from the three tests against
    mixed (keys: the special law's name)."""
    out = Verdict()
    specials = ("competitive", "uncompetitive", "noncompetitive")
    available = [s for s in specials if s in fits]
    for name in available:
        test = tests.get(name)
        if test is not None and test.rejected:
            out.ruled_out.append(name)
    standing = [s for s in available if s not in out.ruled_out]
    if "mixed" in fits:
        standing_all = standing + ["mixed"]
    else:
        standing_all = list(standing)
    out.standing = standing_all
    if "mixed" not in fits:
        out.sentences.append(
            "Mixed inhibition could not be fitted, so none of the three simpler mechanisms "
            "could be tested against it; their fits are described, not tested.")
        out.reported = list(standing)
        return out
    km_unit = units.get("Km", "")
    mixed_iv = {iv.label: iv for iv in intervals.get("mixed", [])}
    ki = mixed_iv.get("Ki")
    kip = mixed_iv.get("Ki'")
    if out.ruled_out:
        out.sentences.append(
            "Ruled out: " + "; ".join(f"{n} ({_p(tests.get(n))} against mixed)" for n in out.ruled_out) + ".")
    if not standing:
        out.reported = ["mixed"]
        out.sentences.insert(0, "Mixed inhibition: the inhibitor binds free enzyme and the "
                                "enzyme-substrate complex with different constants; each simpler "
                                "mechanism is ruled out.")
        return out
    if len(standing) == 1:
        name = standing[0]
        out.reported = [name]
        head = f"{name.capitalize()} inhibition: the data rule out " + (
            " and ".join(n for n in out.ruled_out) if out.ruled_out else "nothing else") + "."
        tail = f" Mixed inhibition fits no better than {name} ({_p(tests.get(name))})"
        if name == "competitive" and kip is not None and kip.high is None and kip.low is not None:
            tail += (f"; a mixed inhibitor with Ki' above {kip.low:.3g} {units.get(kip.label, '')} "
                     f"cannot be excluded")
        if name == "uncompetitive" and ki is not None and ki.high is None and ki.low is not None:
            tail += (f"; a mixed inhibitor with Ki above {ki.low:.3g} {units.get(ki.label, '')} "
                     f"cannot be excluded")
        out.sentences.insert(0, head + tail + ".")
        out.advice.extend(_advice([name, "mixed"], fits, intervals, units, km_unit))
        return out
    out.reported = list(standing)
    names = (standing[0] + " and " + standing[1] if len(standing) == 2
             else ", ".join(standing[:-1]) + " and " + standing[-1])
    out.sentences.insert(0, "The data cannot tell " + names + " inhibition apart: "
                         + "; ".join(f"{n} against mixed {_p(tests.get(n))}" for n in standing)
                         + ". Estimates are given for each.")
    criteria = {name: aicc(fits[name]) for name in standing}
    out.described.append(_describe_untestable(standing, fits, criteria))
    out.advice.extend(_advice(standing, fits, intervals, units, km_unit))
    return out


def _estimate(intervals: Dict[str, List[Interval]], law: str, label: str) -> Optional[Interval]:
    for iv in intervals.get(law, []):
        if iv.label == label:
            return iv
    return None


def _advice(names: Sequence[str], fits: Dict[str, Fit], intervals: Dict[str, List[Interval]],
            units: Dict[str, str], km_unit: str) -> List[str]:
    """The measurement that would separate what is left standing."""
    advice = []
    first = names[0]
    km = _estimate(intervals, first, "Km")
    fit0 = fits[first]
    problem = fit0.problem
    inhibited = problem.i > 0
    km_value = km.estimate if km is not None else None
    constant = _estimate(intervals, first, "Ki") or _estimate(intervals, first, "Ki'")
    i_unit = units.get("Ki", units.get("Ki'", ""))
    dose = (f"[I] near or above {constant.estimate:.3g} {i_unit}" if constant is not None
            else "the highest [I] used")
    high_s = low_s = False
    if km_value:
        s_inh = problem.s[inhibited]
        high_s = bool(np.any(s_inh >= 5 * km_value))
        low_s = bool(np.any((s_inh > 0) & (s_inh <= 0.2 * km_value)))
    need_high = ("competitive" in names) and len(set(names) - {"competitive"}) > 0
    need_low = ("uncompetitive" in names) and len(set(names) - {"uncompetitive"}) > 0
    if not need_high and not need_low and "noncompetitive" in names and "mixed" in names:
        # Ki = Ki' is a statement about the two ends of the substrate range
        # at once: the inhibition at low [S] is through Ki, at high [S]
        # through Ki', and only rates at both can show they differ.
        need_high = need_low = True
    if need_high and km_value:
        state = ("you have some; more there, at a higher [I], would sharpen it" if high_s
                 else "none of your inhibited rates is there")
        advice.append(
            f"Rates with inhibitor at [S] of 5 Km or more ({5 * km_value:.3g} {km_unit}) and {dose}: "
            f"substrate outcompetes a competitive inhibitor there, and no other mechanism, so they "
            f"separate competitive from the rest ({state}).")
    if need_low and km_value:
        state = ("you have some; more there, at a higher [I], would sharpen it" if low_s
                 else "none of your inhibited rates is there")
        advice.append(
            f"Rates with inhibitor at [S] of 0.2 Km or less ({0.2 * km_value:.3g} {km_unit}) and "
            f"{dose}: an uncompetitive inhibitor has no effect there and every other mechanism "
            f"does, so they separate uncompetitive from the rest ({state}).")
    return advice


def substrate_verdict(fits: Dict[str, Fit], intervals: Dict[str, List[Interval]],
                      tests: Dict[str, Test], significance: float, units: Dict[str, str]) -> Verdict:
    """The verdict for rates without inhibitor: Michaelis-Menten against
    substrate inhibition (boundary) and the Hill law (interior)."""
    out = Verdict()
    si, hill = tests.get("substrate-inhibition"), tests.get("hill")
    rejected_by = [name for name, t in (("substrate-inhibition", si), ("hill", hill))
                   if t is not None and t.rejected]
    if not rejected_by:
        out.reported = ["michaelis-menten"]
        out.standing = ["michaelis-menten"] + [n for n in ("substrate-inhibition", "hill") if n in fits]
        clauses = []
        if si is not None:
            clauses.append(f"substrate inhibition ({_p(si)})")
        if hill is not None:
            clauses.append(f"cooperativity (Hill, {_p(hill)})")
        out.sentences.append(
            "Michaelis-Menten: the data give no evidence of " + " or ".join(clauses) + "."
            if clauses else "Michaelis-Menten, the only law fitted.")
        ksi = _estimate(intervals, "substrate-inhibition", "Ksi")
        if ksi is not None and ksi.high is None and ksi.low is not None:
            out.sentences.append(
                f"Substrate inhibition with Ksi above {ksi.low:.3g} {units.get('Ksi', '')} is not "
                f"excluded; rates at [S] approaching that would show it or rule it out.")
        return out
    out.ruled_out = ["michaelis-menten"]
    out.standing = rejected_by
    out.reported = list(rejected_by)
    out.sentences.append(
        "The data reject Michaelis-Menten in favour of "
        + " and ".join(f"the {law_for(n).title} law ({_p(tests[n])})" for n in rejected_by) + ".")
    n = _estimate(intervals, "hill", "n")
    if "hill" in rejected_by and n is not None:
        if n.estimate < 1:
            out.sentences.append(
                f"The Hill exponent is below 1 (n = {n.estimate:.3g}): the rate rises more "
                f"gradually with [S] than Michaelis-Menten allows. Negative cooperativity, a "
                f"mixture of enzyme forms with different Km, or an error that changes with [S] all "
                f"do this, and the exponent cannot say which.")
        else:
            out.sentences.append(
                f"The Hill exponent is above 1 (n = {n.estimate:.3g}): the rate rises more "
                f"steeply than Michaelis-Menten allows, as positive cooperativity does. n is a "
                f"fitted exponent, not a count of binding sites.")
    tested = [t for t in (si, hill) if t is not None]
    if len(tested) > 1:
        out.sentences.append(
            f"Two alternatives were tested, each at {significance:g}, so the chance that at least "
            f"one rejects a true Michaelis-Menten law is up to {1 - (1 - significance) ** 2:.3g}.")
    if len(rejected_by) == 2:
        criteria = {n: aicc(fits[n]) for n in rejected_by}
        out.described.append(_describe_untestable(rejected_by, fits, criteria))
    return out


def tests_for(fits: Dict[str, Fit], significance: float) -> Dict[str, Test]:
    """Every nested test whose two laws were both fitted, keyed by the
    special law for inhibitor data and by the general law without."""
    out: Dict[str, Test] = {}
    for nesting in NESTINGS:
        general, special = fits.get(nesting.general), fits.get(nesting.special)
        if general is None or special is None:
            continue
        key = nesting.special if law_for(nesting.general).needs_inhibitor else nesting.general
        out[key] = nested_test(general, special, nesting, significance)
    return out


__all__ = ["DEFAULT_SIGNIFICANCE", "Test", "LackOfFit", "Verdict", "lack_of_fit", "aicc",
           "nested_test", "tests_for", "inhibition_verdict", "substrate_verdict"]
