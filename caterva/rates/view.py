"""What a screen draws from one `Analysis`: the figure's numbers, the tables, the cautions.

`report.py` writes the analysis as text, JSON and CSV. A page needs the same
facts in the shape of a plot and a table: points with error bars, the fitted
curve with its band, the residuals, one row per constant, one row per law
compared. This module produces them from the one `Analysis`, so the figure,
the tables and the report cannot disagree, and it adds no statistics of its
own: every number is read from a fit, a profile, a test or the data, and every
sentence is the engine's or says only what a p-value above or below the
convention means.

WHAT THE ERROR BARS ARE
-----------------------
A bar is the standard deviation the fit used for that rate: the file's own
sigma, or the pooled replicate estimate, or (for a fit by residuals) the
fit's residual standard error, one bar length for every point because that is
what ordinary least squares assumes. `bars` says which, in a sentence, so a
reader of the figure is told what the whiskers are.

WHAT THE BAND IS
----------------
`fit.curve`'s: asymptotic and pointwise, multiplicative on the rate, and
conditional on any constant held at the edge of the search. `band` repeats
`fit.band_note` for each curve, and a curve with no band says why.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from caterva.rates import report
from caterva.rates.analysis import Analysis, GroupResult, LawResult
from caterva.rates.fit import Interval, band_note, curve
from caterva.rates.table import INHIBITOR, RATE, SUBSTRATE
from caterva.rates.uncertainty import KNOWN, POOLED, RESIDUAL

#: Grid points of a drawn curve: a linear stretch for the straight axis and a
#: geometric one so a logarithmic axis is as smooth.
LINEAR_POINTS = 120
GEOMETRIC_POINTS = 80

_INTERVAL_BASIS = {
    KNOWN: "a rise in chi-square of the squared normal quantile (the error bars are taken as known)",
    POOLED: "a rise in chi-square of the squared t quantile on the pooled degrees of freedom",
    RESIDUAL: "the profile-t statistic against Student's t on the residual degrees of freedom",
}


def _f(x: Any) -> Optional[float]:
    try:
        value = float(x)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _floats(values: Sequence[Any]) -> List[Optional[float]]:
    return [_f(v) for v in values]


def _axis(analysis: Analysis, role: str, name: str) -> Dict[str, Any]:
    cu = analysis.data.units.get(role)
    return {"name": name, "unit": cu.text if cu else "", "column": cu.column if cu else name}


def _grid(s: np.ndarray) -> np.ndarray:
    positive = s[s > 0]
    if positive.size == 0:
        return np.array([])
    top = float(positive.max()) * 1.08
    low = float(positive.min()) / 8.0
    return np.unique(np.concatenate([np.linspace(low, top, LINEAR_POINTS), np.geomspace(low, top, GEOMETRIC_POINTS)]))


def _bars(analysis: Analysis, law: LawResult) -> Dict[str, Any]:
    fit = law.fit
    unit = analysis.unit_of("rate")
    u = f" {unit}" if unit else ""
    source = fit.problem.source
    if source == KNOWN:
        return {"source": source, "text": "Error bars are the standard deviations in your table, one for each rate"
                                          + (f", in {unit}." if unit else ".")}
    if source == POOLED:
        return {"source": source, "text": "Error bars are one standard deviation of the pooled replicate scatter: "
                                          + analysis.uncertainty.describe(unit) + "."}
    se = fit.residual_se
    return {"source": source, "text": ("Error bars are one residual standard error of the fit"
                                       + (f" ({se:.4g}{u})" if se else "")
                                       + ", the same for every point: this fit took its scale from its own residuals.")}


def _label(group: Optional[str], inhibitor: Optional[float], unit: str, has_inhibitor: bool) -> str:
    parts = []
    if group:
        parts.append(str(group))
    if has_inhibitor:
        parts.append(f"[I] {inhibitor:g}" + (f" {unit}" if unit else ""))
    return ", ".join(parts)


def figure(analysis: Analysis) -> Dict[str, Any]:
    """Points, curves, bands and residuals, one series per group and inhibitor
    level, for the law each group's verdict reports first."""
    data = analysis.data
    level = analysis.options.level
    has_i = data.inhibitor is not None and data.has_inhibitor
    i_unit = analysis.unit_of("inhibitor")
    series: List[Dict[str, Any]] = []
    notes: List[str] = []
    bars: Optional[Dict[str, Any]] = None
    for result in analysis.results:
        if not result.reported:
            continue
        law = result.reported[0]
        fit = law.fit
        problem = fit.problem
        s = np.asarray(problem.s, dtype=float)
        i = np.asarray(problem.i, dtype=float)
        v = np.asarray(problem.v, dtype=float)
        sigma = np.asarray(problem.sigma, dtype=float)
        if problem.source == RESIDUAL:
            rse = fit.residual_se
            sigma = np.full_like(v, rse if rse is not None else np.nan)
        centre_rows, _lo, _hi = curve(fit, s, i, result.group, level)
        residual = v - centre_rows
        if bars is None:
            bars = _bars(analysis, law)
        if len(result.reported) > 1:
            others = ", ".join(r.law.title for r in result.reported[1:])
            notes.append((f"[{result.group}] " if result.group else "") + f"The curve is the {law.law.title} law; "
                         f"the data do not rule out {others} either.")
        for level_i in sorted(set(i.tolist())):
            mask = i == level_i
            grid = _grid(s[mask])
            c, lo, hi = curve(fit, grid, np.full_like(grid, level_i), result.group, level)
            order = np.argsort(s[mask], kind="stable")
            rows = np.flatnonzero(mask)[order]
            series.append({
                "key": f"{result.group or 'all'}|{level_i:g}",
                "label": _label(result.group, level_i, i_unit, has_i),
                "group": result.group, "inhibitor": float(level_i) if has_i else None,
                "law": law.law.name, "law_title": law.law.title, "equation": law.law.equation,
                "points": {"s": _floats(s[rows]), "v": _floats(v[rows]), "sigma": _floats(sigma[rows]),
                           "fitted": _floats(centre_rows[rows]), "residual": _floats(residual[rows]),
                           "line": [data.lines[result.rows[k]] for k in rows]},
                "curve": {"s": _floats(grid), "v": _floats(c), "low": _floats(lo), "high": _floats(hi)},
                "band": band_note(fit), "level": level,
            })
    return {
        "x": _axis(analysis, SUBSTRATE, "substrate concentration"),
        "y": _axis(analysis, RATE, "initial rate"),
        "inhibitor": _axis(analysis, INHIBITOR, "inhibitor concentration") if has_i else None,
        "series": series, "bars": bars, "notes": notes,
        "residual_note": "Residuals are the measured rate minus the fitted rate; a curve that follows the "
                         "data leaves them scattered about zero with no run of one sign.",
    }


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _interval_row(analysis: Analysis, group: Optional[str], law: LawResult, iv: Interval, unit: str,
                  undetermined: Sequence[str], product: bool = False) -> Dict[str, Any]:
    determined = iv.bounded and iv.label not in undetermined
    return {
        "group": group, "law": law.law.name, "law_title": law.law.title, "constant": iv.label,
        "unit": unit or "", "estimate": _f(iv.estimate) if determined else None,
        "standard_error": _f(iv.se) if determined else None,
        "low": _f(iv.low), "high": _f(iv.high), "level": iv.level, "determined": determined,
        "interval": report._interval_cell(iv, ""),
        "interval_method": "profile likelihood", "product": product,
        "n": law.fit.n,
        "statement": None if determined else iv.describe(unit),
    }


def parameter_rows(analysis: Analysis) -> List[Dict[str, Any]]:
    """One row per constant of each reported law (and the products the data do
    determine when their factors are not), with what is and is not determined."""
    rows: List[Dict[str, Any]] = []
    for result in analysis.results:
        for law in result.reported:
            units = report._units(analysis, law)
            det = law.determination
            undetermined = det.undetermined if det else []
            for iv in law.intervals:
                rows.append(_interval_row(analysis, result.group, law, iv, units.get(iv.label, ""), undetermined))
            if det is not None:
                for product in det.products:
                    rows.append(_interval_row(analysis, result.group, law, product,
                                              det.product_units.get(product.label, ""), [], True))
    return rows


def interval_basis(analysis: Analysis) -> Dict[str, str]:
    return {"method": f"{analysis.options.level * 100:g}% profile-likelihood interval (Bates and Watts 1988)",
            "bounded_by": _INTERVAL_BASIS[analysis.uncertainty.source]}


def comparison(analysis: Analysis) -> List[Dict[str, Any]]:
    """The laws fitted to each group, with AICc and what the tests concluded."""
    out: List[Dict[str, Any]] = []
    for result in analysis.results:
        verdict = result.verdict
        fitted = [r for r in result.laws.values() if r.fit is not None and r.aicc is not None]
        best = min((r.aicc for r in fitted), default=None)
        laws = []
        for name, law in result.laws.items():
            if law.fit is None:
                laws.append({"law": name, "title": law.law.title, "fitted": False, "refused": law.refused,
                             "status": "not fitted"})
                continue
            status = ("reported" if verdict and name in verdict.reported else
                      "ruled out" if verdict and name in verdict.ruled_out else
                      "not ruled out" if verdict and name in verdict.standing else "fitted")
            lof = law.lack_of_fit
            laws.append({
                "law": name, "title": law.law.title, "equation": law.law.equation, "fitted": True,
                "parameters": law.fit.p, "n": law.fit.n,
                "objective": _f(law.fit.chi2),
                "objective_is": "residual sum of squares" if law.fit.problem.source == RESIDUAL else "chi-square",
                "aicc": _f(law.aicc),
                "delta_aicc": _f(law.aicc - best) if law.aicc is not None and best is not None else None,
                "lack_of_fit_p": _f(lof.p) if lof else None, "status": status,
            })
        tests = [{"restricted": t.nesting.special, "general": t.nesting.general,
                  "restriction": t.nesting.constraint, "boundary": t.nesting.boundary,
                  "statistic": f"{t.reference} = {report.g(t.statistic)}", "p": _f(t.p),
                  "p_text": report.fmt_p(t.p), "ruled_out": t.rejected, "sentence": t.sentence()}
                 for t in result.tests.values()]
        out.append({
            "group": result.group, "laws": laws, "tests": tests,
            "decided": bool(verdict and len(verdict.reported) == 1),
            "reported": list(verdict.reported) if verdict else [],
            "ruled_out": list(verdict.ruled_out) if verdict else [],
            "standing": list(verdict.standing) if verdict else [],
            "verdict": list(verdict.sentences) if verdict else [],
            "described": list(verdict.described) if verdict else [],
            "to_decide": list(verdict.advice) if verdict else [],
            "significance": analysis.options.significance,
            "note": ("AICc is Akaike's criterion with the small-sample correction (Hurvich and Tsai 1989), "
                     "lower is better; it is a description, and the tests decide only nested laws."),
        })
    return out


def lack_of_fit(analysis: Analysis) -> List[Dict[str, Any]]:
    """The lack-of-fit test of each reported law in the engine's sentence, and
    what the result does and does not say about trusting the law."""
    sig = analysis.options.significance
    out = []
    for result in analysis.results:
        for law in result.reported:
            lof = law.lack_of_fit
            if lof is None:
                out.append({"group": result.group, "law": law.law.name, "title": law.law.title,
                            "tested": False, "p": None, "failed": False,
                            "sentence": "Lack of fit was not tested: it needs replicates (rows with identical "
                                        "conditions) and more distinct conditions than constants.",
                            "trust": "Without it, nothing here says whether the law's shape matches your rates; "
                                     "the residual plot is the only check."})
                continue
            failed = lof.p is not None and lof.p < sig
            out.append({
                "group": result.group, "law": law.law.name, "title": law.law.title, "tested": True,
                "p": _f(lof.p), "f": _f(lof.f), "df_lack_of_fit": lof.df_lof, "df_pure_error": lof.df_pe,
                "failed": failed, "sentence": lof.sentence(sig)[0].upper() + lof.sentence(sig)[1:],
                "trust": ("Treat the constants as describing this law's curve, not as properties of the enzyme, "
                          "until a law that follows the data is found." if failed else
                          "A pass does not prove the law right; it means these replicates could not show it wrong."),
            })
    return out


# ---------------------------------------------------------------------------
# Cautions and what to change
# ---------------------------------------------------------------------------


def cautions(analysis: Analysis) -> Dict[str, Any]:
    """Every caution the engine produced, once each, with what to change, and
    the measurements that would make the fit better. Nothing here is a
    refusal: a refused run has no analysis and shows the engine's message."""
    sig = analysis.options.significance
    found: List[Dict[str, Any]] = []
    seen: set = set()

    def add(group: Optional[str], law: Optional[str], kind: str, text: str, change: Optional[str] = None) -> None:
        key = (group, text)
        if text and key not in seen:
            seen.add(key)
            found.append({"group": group, "law": law, "kind": kind, "text": text, "change": change})

    for note in analysis.notes:
        add(None, None, "note", note)
    better: List[str] = []
    for result in analysis.results:
        group = result.group
        for law in result.reported:
            title = law.law.title
            det = law.determination
            fit = law.fit
            km = law.interval("Km") or law.interval("K0.5")
            vmax = law.interval("Vmax")
            top = max((analysis.data.substrate[r] for r in result.rows), default=None)
            low = min((analysis.data.substrate[r] for r in result.rows if analysis.data.substrate[r] > 0), default=None)
            unit = analysis.unit_of("substrate")
            u = f" {unit}" if unit else ""
            move = None
            if km is not None and vmax is not None and top is not None:
                if km.high is None and vmax.high is None:
                    move = (f"Every concentration you used is below {km.label}, and the highest is {top:g}{u}: "
                            f"measure at higher concentrations, until the rate stops rising with them.")
                elif km.low is None and vmax.bounded and low is not None:
                    move = (f"Every concentration you used is above {km.label}, and the lowest is {low:g}{u}: "
                            f"measure at lower concentrations, where the rate still rises with them.")
            for finding in (det.findings if det else []):
                add(group, law.law.name, "undetermined", finding,
                    move or "Measure over a wider range of substrate concentrations, at the end the sentence names.")
            if move:
                better.append(move)
            lof = law.lack_of_fit
            if lof is not None and lof.p is not None and lof.p < sig:
                add(group, law.law.name, "lack-of-fit", lof.sentence(sig),
                    "Look at the residual plot for a pattern, check the replicates for an outlier, or fit another law.")
            p = fit.gof_p()
            if p is not None and p < 0.01:
                add(group, law.law.name, "error-bars",
                    f"Chi-square {report.g(fit.chi2)} on {fit.dof} degrees of freedom (p = {p:.3g}): the rates "
                    f"scatter more than the stated errors allow, so either the law or the error bars are wrong.",
                    "Check the sigma column, or estimate the uncertainty from replicates instead.")
            elif p is not None and p > 0.99:
                add(group, law.law.name, "error-bars",
                    f"Chi-square {report.g(fit.chi2)} on {fit.dof} degrees of freedom (p = {p:.3g}): the fit is "
                    f"closer than the stated errors allow; they are probably overstated.",
                    "Check the sigma column against the replicate scatter.")
            if fit.other_minimum is not None and fit.normalised(fit.other_minimum) < fit.threshold(analysis.options.level):
                add(group, law.law.name, "second-minimum",
                    f"A second minimum fits almost as well (objective {report.g(fit.other_minimum)} against "
                    f"{report.g(fit.chi2)}, inside the interval threshold); the data do not clearly choose "
                    f"between them, and the lower is reported.")
            for edge, label, name in zip(fit.edge, fit.problem.labels, fit.problem.constants):
                if edge:
                    add(group, law.law.name, "edge", report._edge_note(name, label, edge))
            for note in fit.notes:
                add(group, law.law.name, "fit", note)
            if result.design is not None and law is result.reported[0]:
                design = result.design
                if design.recommended:
                    better.append(design.text[-1])
                elif design.km_low is None or design.km_high is None:
                    better.extend(t for t in design.text[:1] if "cannot place" in t or "no range" not in t)
        verdict = result.verdict
        if verdict is not None:
            for sentence in verdict.advice:
                better.append(sentence)
    seen_better: List[str] = []
    for line in better:
        if line not in seen_better:
            seen_better.append(line)
    return {"cautions": found, "better": seen_better[:4]}


def groups(analysis: Analysis) -> Optional[Dict[str, Any]]:
    """The between-group tests, in the engine's words."""
    c = analysis.comparison
    if c is None:
        return None
    rows = []
    for t in c.tests:
        rows.append({
            "constant": t.constant, "statistic": f"{t.reference} = {report.g(t.statistic)}",
            "p": _f(t.p), "p_text": report.fmt_p(t.p), "differs": t.rejected,
            "verdict": ("the groups differ" if t.rejected else "no difference detected at all")
            if t.constant == "all" else ("differs" if t.rejected else "no difference detected")})
    return {"law": c.law.name, "law_title": c.law.title, "groups": list(c.groups), "tests": rows,
            "sentences": list(c.sentences), "significance": analysis.options.significance}


__all__ = ["cautions", "comparison", "figure", "groups", "interval_basis", "lack_of_fit", "parameter_rows"]
