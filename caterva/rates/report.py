"""The report, the JSON, the two CSV exports and the methods paragraph.

Every one is a view of one `analysis.Analysis`, so none can print a number
another does not have. The human report puts the verdict first, as compose
does: what the data rule out, what they cannot decide, what they determine
and what they do not, and the worst thing wrong, before any table.

A CONSTANT THE DATA DO NOT BOUND IS NOT PRINTED AS A NUMBER
-----------------------------------------------------------
Where a profile is open on one side (fit.py), the tables print the one-sided
statement ("Km > [bound]") and leave the estimate and its standard error out,
because the optimiser's stopping point along a flat direction is not an
estimate of anything. The CSV has an empty estimate cell and a `determined`
column saying no; the JSON has the bound and `"determined": false`.
"""
from __future__ import annotations

import csv
import io
import json
import math
import platform
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from caterva.rates import linearize
from caterva.rates.analysis import Analysis, GroupResult, LawResult
from caterva.rates.fit import Interval, curve
from caterva.rates.models import law_for
from caterva.rates.table import INHIBITOR, RATE, SUBSTRATE
from caterva.rates.uncertainty import KNOWN, POOLED, RESIDUAL

BRENDA_CITATION = "BRENDA (Chang et al. 2021, Nucleic Acids Res. 49:D498, doi:10.1093/nar/gkaa1025)"
REFERENCES = [
    "Cornish-Bowden A. Fundamentals of Enzyme Kinetics, 4th ed. Wiley-Blackwell, 2012 (rate laws).",
    "Segel IH. Enzyme Kinetics. Wiley, 1975 (inhibition laws).",
    "Bates DM, Watts DG. Nonlinear Regression Analysis and Its Applications. Wiley, 1988 "
    "(profile intervals).",
    "Self SG, Liang KY. J. Am. Stat. Assoc. 82:605 (1987) (tests on the boundary).",
    "Draper NR, Smith H. Applied Regression Analysis. Wiley (lack of fit and pure error).",
    "Hurvich CM, Tsai CL. Biometrika 76:297 (1989) (AICc).",
    "Brooks HB et al. Basics of Enzymatic Assays for HTS. Assay Guidance Manual, NCBI Bookshelf "
    "NBK92007 (the 0.2-5 Km design range).",
]


def g(x: Optional[float], digits: int = 4) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "-"
    return f"{x:.{digits}g}"


def fmt_p(p: Optional[float]) -> str:
    """A p-value as printed: three figures, and a stated floor where the tail
    underflows to zero in double precision rather than a p of exactly 0."""
    if p is None:
        return "-"
    if p <= 0:
        return "< 1e-300"
    return f"{p:.3g}"


def _pct(level: float) -> str:
    return f"{level * 100:g}%"


def _units(analysis: Analysis, result: LawResult) -> Dict[str, str]:
    labels = result.fit.problem.labels if result.fit is not None else ()
    return analysis.units_for(result.law, labels)


def _interval_cell(iv: Interval, unit: str) -> str:
    u = f" {unit}" if unit else ""
    if iv.bounded:
        return f"{g(iv.low)} to {g(iv.high)}{u}"
    if iv.low is None and iv.high is None:
        return "not bounded either way"
    if iv.high is None:
        return f"> {g(iv.low)}{u} (no upper bound)"
    return f"< {g(iv.high)}{u} (no lower bound)"


def _where(group: Optional[str]) -> str:
    return f"[{group}] " if group else ""


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


def verdict_lines(analysis: Analysis) -> List[str]:
    out: List[str] = []
    for result in analysis.results:
        where = _where(result.group)
        verdict = result.verdict
        if verdict is not None:
            if not verdict.sentences and len(result.laws) == 1:
                only = next(iter(result.laws))
                out.append(f"{where}{law_for(only).title}, the law asked for (--model {only}); no "
                           f"other law was fitted or tested.")
            for sentence in verdict.sentences:
                out.append(where + sentence)
        for law in result.reported:
            headline = _headline(analysis, law)
            if headline:
                out.append(f"{where}{law.law.title}: {headline}")
        if verdict is not None:
            for sentence in verdict.advice:
                out.append(where + "To decide: " + sentence)
        for law in result.reported:
            det = law.determination
            if det is not None:
                for finding in det.findings:
                    out.append(f"{where}{law.law.title}: {finding}")
            if law.lack_of_fit is not None and law.lack_of_fit.p is not None and \
                    law.lack_of_fit.p < analysis.options.significance:
                out.append(f"{where}{law.law.title}: "
                           + law.lack_of_fit.sentence(analysis.options.significance))
            fit = law.fit
            if fit is not None and fit.gof_p() is not None:
                p = fit.gof_p()
                if p < 0.01:
                    out.append(f"{where}{law.law.title}: chi-square {g(fit.chi2)} on {fit.dof} "
                               f"degrees of freedom (p = {p:.3g}): the rates scatter more than the "
                               f"stated errors allow, so either the law or the error bars are wrong.")
                elif p > 0.99:
                    out.append(f"{where}{law.law.title}: chi-square {g(fit.chi2)} on {fit.dof} "
                               f"degrees of freedom (p = {p:.3g}): the fit is closer than the "
                               f"stated errors allow; they are probably overstated.")
            if (fit is not None and fit.other_minimum is not None and
                    fit.normalised(fit.other_minimum) < fit.threshold(analysis.options.level)):
                out.append(f"{where}{law.law.title}: a second minimum fits almost as well "
                           f"(objective {g(fit.other_minimum)} against {g(fit.chi2)}, inside the "
                           f"interval threshold); the data do not clearly choose between them, "
                           f"and the lower is reported.")
    if analysis.comparison is not None:
        out.extend("Between groups: " + s for s in analysis.comparison.sentences)
    for c in analysis.literature:
        out.append("Literature: " + literature_sentence(c))
    if analysis.literature_refused:
        out.append("Literature: not compared -- " + analysis.literature_refused)
    return out


def _headline(analysis: Analysis, law: LawResult) -> str:
    """The reported law's determined constants in one line."""
    if law.fit is None:
        return ""
    units = _units(analysis, law)
    undetermined = set(law.determination.undetermined if law.determination else ())
    parts = []
    for iv in law.intervals:
        if iv.bounded and iv.label not in undetermined:
            unit = units.get(iv.label, "")
            parts.append(f"{iv.label} {g(iv.estimate)} ({g(iv.low)} to {g(iv.high)}"
                         + (f" {unit})" if unit else ")"))
    if not parts:
        return ""
    return ", ".join(parts) + f" ({_pct(analysis.options.level)} profile intervals)."


def literature_sentence(c) -> str:
    where = f" [{c.group}]" if c.group else ""
    what = f"{c.constant}{where}, {c.law}"
    if c.refused and not c.found:
        return f"{what}: {c.refused}."
    ref = f"BRENDA ref {c.reference}" if c.reference else "no reference id"
    text = f"{what}: cited {c.cited:g} {c.cited_unit} ({ref}"
    text += f", {c.organism})" if c.organism else ")"
    if c.converted is None:
        return text + f"; {c.refused or 'the fitted value could not be expressed in that unit'}."
    fitted = _interval_cell(c.converted, c.cited_unit or "")
    inside = "inside" if c.contains else "OUTSIDE"
    text += (f"; fitted {g(c.converted.estimate)} {c.cited_unit} ({fitted}): the cited value is "
             f"{inside} the fitted interval, ratio fitted/cited {g(c.ratio, 3)}")
    if c.conditional:
        text += f"; {c.conditional}"
    return text + "."


# ---------------------------------------------------------------------------
# The human report
# ---------------------------------------------------------------------------


def _law_table(analysis: Analysis, law: LawResult, level: float) -> List[str]:
    units = _units(analysis, law)
    undetermined = set(law.determination.undetermined if law.determination else ())
    lines = [f"| constant | estimate | standard error | {_pct(level)} profile interval | unit |",
             "|---|---|---|---|---|"]
    for iv in law.intervals:
        unit = units.get(iv.label, "")
        if iv.bounded and iv.label not in undetermined:
            est, se = g(iv.estimate), g(iv.se)
        else:
            est, se = "not determined", "-"
        lines.append(f"| {iv.label} | {est} | {se} | {_interval_cell(iv, '')} | {unit or '-'} |")
    if law.determination is not None:
        for product in law.determination.products:
            lines.append(f"| {product.label} | {g(product.estimate)} | {g(product.se)} | "
                         f"{_interval_cell(product, '')} | - |")
    return lines


def _statistics(analysis: Analysis, law: LawResult) -> List[str]:
    fit = law.fit
    out = []
    source = fit.problem.source
    if source == RESIDUAL:
        out.append(f"Residual standard error {g(fit.residual_se)} {analysis.unit_of('rate')} on "
                   f"{fit.dof} degrees of freedom. No goodness-of-fit chi-square is given: sigma was "
                   f"estimated from these residuals, so the chi-square is {fit.dof} by construction "
                   f"and cannot test the law it was computed from.")
    elif source == POOLED:
        u = analysis.uncertainty
        out.append(f"Chi-square {g(fit.chi2)} on {fit.dof} degrees of freedom, with sigma pooled from "
                   f"replicates ({u.dof} degrees of freedom). Most of that chi-square is the replicate "
                   f"scatter sigma was estimated from, so it is not a test; the lack-of-fit F test is.")
    else:
        p = fit.gof_p()
        out.append(f"Chi-square {g(fit.chi2)} on {fit.dof} degrees of freedom"
                   + (f", p = {p:.3g}" if p is not None else "") +
                   ": the test of this law and the stated errors together.")
    corr = fit.correlation()
    pairs = []
    for a in range(fit.p):
        for b in range(a + 1, fit.p):
            if np.isfinite(corr[a, b]):
                pairs.append(f"{fit.problem.labels[a]}-{fit.problem.labels[b]} {corr[a, b]:+.3f}")
    if pairs:
        out.append("Correlations of the estimates: " + ", ".join(pairs) + ".")
    out.append(f"Starts: {fit.starts_agreeing} of {fit.starts_tried} reached this minimum"
               + (f"; the lowest other minimum found had objective {g(fit.other_minimum)}."
                  if fit.other_minimum is not None else "; no start found a different one."))
    out.append(f"Condition number of the weighted Jacobian (log constants): {g(fit.condition_number, 3)}.")
    if law.lack_of_fit is not None:
        out.append("Lack of fit: " + law.lack_of_fit.sentence(analysis.options.significance))
    else:
        out.append("Lack of fit: not tested (it needs replicates, and more distinct conditions "
                   "than constants).")
    for edge, label in zip(fit.edge, fit.problem.labels):
        if edge:
            out.append(f"{label} ran to the {'upper' if edge == 'high' else 'lower'} edge of the "
                       f"search (a factor of 1e8 beyond the data's range): its term in the law is "
                       f"negligible, and the fit is the limiting law.")
    out.extend(fit.notes)
    return out


def _group_heading(result: GroupResult) -> str:
    return f" ({result.group})" if result.group else ""


def render(analysis: Analysis) -> str:
    data = analysis.data
    level = analysis.options.level
    L: List[str] = [f"# Initial rates: {data.source}", "", "## Verdict", ""]
    L += [f"- {line}" for line in verdict_lines(analysis)] or ["- Nothing to report."]
    L += ["", "## The data", ""]
    conditions = len({data.condition(r) for r in range(len(data))})
    replicated = len(data) - conditions
    groups = data.groups()
    L.append(f"{len(data)} rate(s) at {conditions} distinct condition(s)"
             + (f" ({replicated} replicate row(s))" if replicated else "")
             + (f", in {len(groups)} groups by {data.group_column!r}: " +
                ", ".join(f"{gname} ({len(data.rows_of(gname))})" for gname in groups) if groups else "")
             + ".")
    unit_parts = []
    for role in (SUBSTRATE, INHIBITOR, RATE):
        if role in data.units:
            cu = data.units[role]
            if cu.convertible:
                unit_parts.append(f"{role} in {cu.text}")
            elif role == RATE:
                unit_parts.append(f"{role} in {cu.text} (an arbitrary unit: fitted as given)")
            else:
                unit_parts.append(f"{role} in {cu.text} (not convertible to molar: fitted as given, "
                                  f"and not comparable with a cited constant)")
    L.append("Units: " + "; ".join(unit_parts) + ".")
    L.append("Uncertainty: " + analysis.uncertainty.describe(analysis.unit_of("rate")) + ".")
    for note in analysis.notes:
        L.append(note)

    for result in analysis.results:
        for law in result.reported:
            L += ["", f"## {law.law.title}{_group_heading(result)}", "", f"`{law.law.equation}`", ""]
            L += _law_table(analysis, law, level)
            L.append("")
            L += [f"- {s}" for s in _statistics(analysis, law)]
            if result.design is not None and law is result.reported[0]:
                L += [f"- Substrate range: {s}" for s in result.design.text]
        others = [r for n, r in result.laws.items() if r not in result.reported]
        if result.tests or others:
            L += ["", f"## The laws tested{_group_heading(result)}", ""]
            if result.tests:
                L += ["| restricted law | general law | restriction | kind | statistic | p | verdict |",
                      "|---|---|---|---|---|---|---|"]
                for test in result.tests.values():
                    n = test.nesting
                    kind = "boundary (50:50 mixture)" if n.boundary else "interior"
                    verdict = "ruled out" if test.rejected else "not ruled out"
                    L.append(f"| {n.special} | {n.general} | {n.constraint} | {kind} | "
                             f"{test.reference} = {g(test.statistic)} | "
                             f"{fmt_p(test.p)} | {verdict} |")
                L += ["", f"Ruled out means p below {analysis.options.significance:g}, a convention; "
                          f"every p-value is printed so another can be applied. A boundary restriction "
                          f"(a constant going to infinity) is tested against the 50:50 mixture of "
                          f"chi-square(0) and chi-square(1) (Self & Liang 1987): half the ordinary "
                          f"p-value."]
            if result.verdict is not None:
                L += ["", *result.verdict.described]
            for other in others:
                if other.fit is None:
                    L += ["", f"{other.law.title}: not fitted -- {other.refused}"]
                    continue
                L += ["", f"{other.law.title}, for comparison (`{other.law.equation}`):", ""]
                L += _law_table(analysis, other, level)
    comparison = analysis.comparison
    if comparison is not None:
        L += ["", f"## Between groups ({comparison.law.title})", ""]
        L += ["| shared constant | statistic | p | verdict |", "|---|---|---|---|"]
        for t in comparison.tests:
            verdict = "differs" if t.rejected else "no difference detected"
            if t.constant == "all":
                verdict = "the groups differ" if t.rejected else "no difference detected at all"
            L.append(f"| {t.constant} | {t.reference} = {g(t.statistic)} | "
                     f"{fmt_p(t.p)} | {verdict} |")
        L += [""] + [f"- {s}" for s in comparison.sentences]
        if analysis.uncertainty.source == RESIDUAL:
            L.append("- The F tests pool the scatter of every group's separate fit, which assumes "
                     "each group was measured with the same precision; each group's own residual "
                     "standard error is in its section above.")
        for t in comparison.tests:
            if t.constant != "all" and not t.rejected:
                L += ["", f"The fit with {t.constant} shared:", ""]
                units = analysis.units_for(comparison.law, t.fit.problem.labels)
                L += ["| constant | estimate | standard error | "
                      f"{_pct(level)} profile interval | unit |", "|---|---|---|---|---|"]
                for iv in t.intervals:
                    unit = units.get(iv.label, "")
                    L.append(f"| {iv.label} | {g(iv.estimate) if iv.bounded else 'not determined'} | "
                             f"{g(iv.se) if iv.bounded else '-'} | {_interval_cell(iv, '')} | "
                             f"{unit or '-'} |")
    if analysis.literature or analysis.literature_refused:
        L += ["", "## Against the literature", ""]
        if analysis.literature_refused:
            L.append(f"Not compared: {analysis.literature_refused}")
        for c in analysis.literature:
            L.append(f"- {literature_sentence(c)}")
            if c.commentary:
                L.append(f"  - Row commentary: \"{c.commentary}\"")
            for concern in c.concerns:
                L.append(f"  - {concern}")
            if c.spread and c.spread_rows > 1:
                L.append(f"  - The resolver found {c.spread_rows} equally well evidenced rows, "
                         f"{g(c.spread[0])} to {g(c.spread[1])} {c.cited_unit}; that spread is "
                         f"disagreement between papers, not measurement error.")
            if c.evidence_against:
                L.append(f"  - {c.evidence_against}.")
        if analysis.literature:
            L.append(f"\nCited values from {BRENDA_CITATION}, through Caterva's literature resolver.")
    if any(r.linearizations for r in analysis.results):
        L += ["", "## Straight-line plots (for teaching; never the estimate)", "", linearize.WHY]
        for result in analysis.results:
            for lin in result.linearizations:
                head = f"{_where(result.group)}[I] = {lin.inhibitor:g}".strip()
                L += ["", f"### {head}", ""]
                L += ["| plot | x | y | points (x, y) | Vmax | Km |", "|---|---|---|---|---|---|"]
                for line in lin.lines:
                    pts = "; ".join(f"({g(x, 3)}, {g(y, 3)})" for x, y in line.points)
                    L.append(f"| {line.plot} | {line.x_label} | {line.y_label} | {pts} | "
                             f"{g(line.vmax)} | {g(line.km)} |" + (f" {line.note}" if line.note else ""))
                nonlinear = result.reported[0] if result.reported else None
                if nonlinear is not None and lin.inhibitor == 0:
                    vm = nonlinear.interval("Vmax")
                    km = nonlinear.interval("Km")
                    if vm is not None and km is not None:
                        L.append(f"| nonlinear fit ({nonlinear.law.name}) | | | | {g(vm.estimate)} | "
                                 f"{g(km.estimate)} |")
    L += ["", "## What these numbers are", "",
          "- FITTED to this file's rates, under the law named, not measured constants: their "
          "provenance is this dataset and this law, and they are conditional on both.",
          f"- Intervals are {_pct(level)} profile-likelihood intervals (Bates & Watts 1988); the "
          "standard errors are asymptotic and are what a +-2 SE interval would be built from, which "
          "for Km is often too symmetric.",
          "- A fit this good is not evidence that the law is right; the tests above compare the laws "
          "fitted, and a law not fitted was not considered.",
          "- References: " + " ".join(REFERENCES)]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def _interval_json(iv: Interval, unit: str, undetermined: Sequence[str] = ()) -> Dict[str, Any]:
    determined = iv.bounded and iv.label not in undetermined
    return {
        "constant": iv.label, "unit": unit or None,
        "estimate": iv.estimate if determined else None,
        "standard_error": iv.se if determined else None,
        "low": iv.low, "high": iv.high, "level": iv.level, "interval": "profile likelihood",
        "determined": determined,
    }


def _law_json(analysis: Analysis, law: LawResult) -> Dict[str, Any]:
    if law.fit is None:
        return {"law": law.law.name, "fitted": False, "refused": law.refused}
    fit = law.fit
    units = _units(analysis, law)
    undetermined = law.determination.undetermined if law.determination else []
    corr = fit.correlation()
    return {
        "law": law.law.name, "equation": law.law.equation, "fitted": True,
        "constants": [_interval_json(iv, units.get(iv.label, ""), undetermined) for iv in law.intervals],
        "determined_products": [_interval_json(p, "") for p in
                                (law.determination.products if law.determination else [])],
        "findings": law.determination.findings if law.determination else [],
        "n": fit.n, "parameters": fit.p, "degrees_of_freedom": fit.dof,
        "objective": fit.chi2,
        "objective_is": ("residual sum of squares" if fit.problem.source == RESIDUAL
                         else "chi-square"),
        "chi_square": fit.chi2 if fit.problem.source != RESIDUAL else None,
        "chi_square_p": fit.gof_p(),
        "residual_standard_error": fit.residual_se,
        "correlation": {f"{fit.problem.labels[a]}~{fit.problem.labels[b]}": float(corr[a, b])
                        for a in range(fit.p) for b in range(a + 1, fit.p) if np.isfinite(corr[a, b])},
        # The whole matrix, in the order of `constants`; null where a
        # constant ran to the edge of the search and has no covariance.
        "correlation_matrix": [[float(corr[a, b]) if np.isfinite(corr[a, b]) else None
                                for b in range(fit.p)] for a in range(fit.p)],
        "condition_number": fit.condition_number,
        "starts": {"tried": fit.starts_tried, "reached_minimum": fit.starts_agreeing,
                   "other_minimum": fit.other_minimum},
        "at_edge": {label: edge for label, edge in zip(fit.problem.labels, fit.edge) if edge},
        "lack_of_fit": None if law.lack_of_fit is None else {
            "F": law.lack_of_fit.f, "df_lack_of_fit": law.lack_of_fit.df_lof,
            "df_pure_error": law.lack_of_fit.df_pe, "p": law.lack_of_fit.p},
        "aicc": law.aicc,
        "notes": list(fit.notes),
    }


def to_json(analysis: Analysis) -> str:
    data = analysis.data
    u = analysis.uncertainty
    results = []
    for result in analysis.results:
        verdict = result.verdict
        results.append({
            "group": result.group,
            "rows": len(result.rows),
            "reported": [law.law.name for law in result.reported],
            "verdict": verdict.sentences if verdict else [],
            "ruled_out": verdict.ruled_out if verdict else [],
            "standing": verdict.standing if verdict else [],
            "to_decide": verdict.advice if verdict else [],
            "not_tested": verdict.described if verdict else [],
            "tests": [{
                "restricted": t.nesting.special, "general": t.nesting.general,
                "restriction": t.nesting.constraint, "boundary": t.nesting.boundary,
                "reference": t.reference, "statistic": t.statistic, "p": t.p,
                "ruled_out": t.rejected} for t in result.tests.values()],
            "laws": [_law_json(analysis, law) for law in result.laws.values()],
            "substrate_range": None if result.design is None else {
                "relative_to": result.design.km_label, "span_in_Km": list(result.design.span),
                "below": result.design.below, "above": result.design.above,
                "inside_0.2_to_5": result.design.inside, "brackets": result.design.brackets,
                "recommended": result.design.recommended, "text": result.design.text},
            "linearizations": [{
                "inhibitor": lin.inhibitor,
                "lines": [{"plot": line.plot, "x": line.x_label, "y": line.y_label,
                           "points": line.points, "slope": line.slope, "intercept": line.intercept,
                           "vmax": line.vmax, "km": line.km, "note": line.note}
                          for line in lin.lines]} for lin in result.linearizations],
        })
    comparison = analysis.comparison
    out = {
        "caterva": _version(),
        "file": data.source,
        "rows": len(data),
        "units": {role: {"column": cu.column, "unit": cu.text, "kind": cu.kind,
                         "convertible": cu.convertible} for role, cu in data.units.items()},
        "uncertainty": {"source": u.source, "error_model": u.error_model, "pooled": u.pooled,
                        "degrees_of_freedom": u.dof, "replicate_sets": u.sets,
                        "description": u.describe(analysis.unit_of("rate"))},
        "level": analysis.options.level,
        "significance": analysis.options.significance,
        "verdict": verdict_lines(analysis),
        "results": results,
        "groups": None if comparison is None else {
            "law": comparison.law.name, "groups": comparison.groups,
            "tests": [{"shared": t.constant, "reference": t.reference, "statistic": t.statistic,
                       "p": t.p, "differs": t.rejected,
                       "fit": {"objective": t.fit.chi2,
                               "constants": [_interval_json(iv, analysis.units_for(
                                   comparison.law, t.fit.problem.labels).get(iv.label, ""))
                                   for iv in t.intervals]}} for t in comparison.tests],
            "sentences": comparison.sentences},
        "literature": [_literature_json(c) for c in analysis.literature],
        "literature_refused": analysis.literature_refused,
        "notes": analysis.notes,
    }
    return json.dumps(out, indent=2, default=_default) + "\n"


def _literature_json(c) -> Dict[str, Any]:
    return {
        "constant": c.constant, "law": c.law, "group": c.group, "asked_under": c.compound,
        "mode": c.mode, "found": c.found, "cited": c.cited, "cited_unit": c.cited_unit,
        "brenda_reference": c.reference, "organism": c.organism, "commentary": c.commentary,
        "resolver_source": c.source, "concerns": c.concerns,
        "spread": list(c.spread) if c.spread else None, "equally_evidenced_rows": c.spread_rows,
        "tie": c.tie, "evidence_against_mechanism": c.evidence_against,
        "fitted_in_cited_unit": None if c.converted is None else {
            "estimate": c.converted.estimate, "low": c.converted.low, "high": c.converted.high},
        "contains_cited": c.contains, "ratio_fitted_to_cited": c.ratio,
        "refused": c.refused, "conditional": c.conditional,
    }


def _default(value: Any) -> Any:
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"not serialisable: {type(value).__name__}")


def _version() -> str:
    try:
        from caterva import __version__
    except Exception:  # noqa: BLE001 - a version string must never stop an export
        return "unknown"
    return __version__


# ---------------------------------------------------------------------------
# CSV exports
# ---------------------------------------------------------------------------


def parameters_csv(analysis: Analysis) -> str:
    """One row per constant of every law fitted, per group, and per shared
    fit between groups. Units in their own column, because the constants of
    one law are in different units."""
    level = _pct(analysis.options.level)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["group", "law", "reported", "constant", "unit", "estimate", "standard_error",
                     f"low ({level} profile)", f"high ({level} profile)", "determined",
                     "sigma_source"])
    source = analysis.uncertainty.source

    def rows(group, law_name, reported, law_result_intervals, units, undetermined):
        for iv in law_result_intervals:
            determined = iv.bounded and iv.label not in undetermined
            writer.writerow([group or "", law_name, "yes" if reported else "no", iv.label,
                             units.get(iv.label, ""),
                             _num(iv.estimate) if determined else "",
                             _num(iv.se) if determined else "",
                             _num(iv.low), _num(iv.high), "yes" if determined else "no", source])

    for result in analysis.results:
        reported = {law.law.name for law in result.reported}
        for name, law in result.laws.items():
            if law.fit is None:
                continue
            units = _units(analysis, law)
            det = law.determination
            rows(result.group, name, name in reported, law.intervals, units,
                 det.undetermined if det else [])
            if det is not None:
                rows(result.group, name, name in reported, det.products, {}, [])
    comparison = analysis.comparison
    if comparison is not None:
        for t in comparison.tests:
            if t.constant == "all":
                continue
            units = analysis.units_for(comparison.law, t.fit.problem.labels)
            rows(f"shared {t.constant}", comparison.law.name, not t.rejected, t.intervals, units, [])
    return buffer.getvalue()


def _num(x: Optional[float]) -> str:
    if x is None or not math.isfinite(x):
        return ""
    return repr(float(x))


def curves_csv(analysis: Analysis, points: int = 60) -> str:
    """The reported laws' curves on a grid of [S], at each [I] of the data,
    with the measured rates, one row per point, units in the headers. The
    band is ASYMPTOTIC and POINTWISE (fit.curve): not a profile interval,
    and not a band for the whole curve at once."""
    data = analysis.data
    level = _pct(analysis.options.level)
    s_unit = data.units[SUBSTRATE].text
    r_unit = data.units[RATE].text
    has_i = data.inhibitor is not None
    i_unit = data.units[INHIBITOR].text if has_i else ""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    header = ["kind", "group", "law"]
    if has_i:
        header.append(f"inhibitor ({i_unit})")
    header += [f"substrate ({s_unit})", f"rate ({r_unit})",
               f"rate low ({level} pointwise, asymptotic) ({r_unit})",
               f"rate high ({level} pointwise, asymptotic) ({r_unit})"]
    writer.writerow(header)
    for result in analysis.results:
        rows = result.rows
        s = np.asarray([data.substrate[r] for r in rows])
        i = np.asarray([data.inhibitor[r] for r in rows]) if has_i else np.zeros(len(rows))
        v = np.asarray([data.rate[r] for r in rows])
        positive = s[s > 0]
        grid = np.geomspace(positive.min() / 2.0, positive.max() * 1.5, points) if positive.size else np.array([])
        for law in result.reported:
            for level_i in sorted(set(i.tolist())):
                centre, low, high = curve(law.fit, grid, np.full_like(grid, level_i), result.group,
                                          analysis.options.level)
                for x, c, lo, hi in zip(grid, centre, low, high):
                    row = ["fit", result.group or "", law.law.name]
                    if has_i:
                        row.append(_num(level_i))
                    row += [_num(x), _num(c), _num(lo), _num(hi)]
                    writer.writerow(row)
        for x, y, z in zip(s, v, i):
            row = ["measured", result.group or "", ""]
            if has_i:
                row.append(_num(z))
            row += [_num(x), _num(y), "", ""]
            writer.writerow(row)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Methods paragraph
# ---------------------------------------------------------------------------


def methods(analysis: Analysis) -> str:
    import numpy
    import scipy

    data = analysis.data
    u = analysis.uncertainty
    level = _pct(analysis.options.level)
    laws = []
    for result in analysis.results:
        for law in result.laws.values():
            if law.fit is not None and law.law.title not in laws:
                laws.append(law.law.title)
    conditions = len({data.condition(r) for r in range(len(data))})
    parts = [
        f"Initial rates ({len(data)} measurements at {conditions} distinct conditions"
        + (f", in {len(data.groups())} groups" if data.groups() else "")
        + f"; substrate in {data.units[SUBSTRATE].text}, rate in {data.units[RATE].text}"
        + (f", inhibitor in {data.units[INHIBITOR].text}" if INHIBITOR in data.units else "")
        + ") were fitted to the " + ", ".join(laws) + " rate law"
        + ("s" if len(laws) > 1 else "")
        + " (Cornish-Bowden 2012; Segel 1975) by nonlinear least squares "
        "(scipy.optimize.least_squares, trust-region reflective, on the logarithms of the "
        "constants, which keeps them positive; derivatives by the complex step; multiple "
        "starting points spread across the range of the data).",
    ]
    if u.source == KNOWN:
        parts.append("Each rate was weighted by the inverse square of its standard deviation, "
                     "given per measurement and taken as known.")
    elif u.source == POOLED:
        if u.error_model == "proportional":
            parts.append(f"Each rate was weighted by the inverse square of a standard deviation "
                         f"proportional to the mean rate at its condition, with the coefficient "
                         f"of variation ({u.pooled:.3g}) pooled from {u.sets} replicate sets "
                         f"({u.dof} degrees of freedom).")
        else:
            parts.append(f"Rates were weighted equally, with the standard deviation "
                         f"({u.pooled:.4g} {data.units[RATE].text}) pooled from {u.sets} replicate "
                         f"sets ({u.dof} degrees of freedom).")
    else:
        parts.append("Rates were weighted equally (ordinary least squares) and the standard "
                     "deviation was estimated from the residuals, which assumes the rate law is "
                     "correct.")
    reference = {KNOWN: "a rise in chi-square of the squared normal quantile",
                 POOLED: "a rise in chi-square of the squared t quantile on the pooled degrees of freedom",
                 RESIDUAL: "the profile-t statistic against Student's t on the residual degrees of freedom"}[u.source]
    parts.append(f"{level} confidence intervals are profile-likelihood intervals (Bates & Watts 1988), "
                 f"bounded by {reference}; asymptotic standard errors are also reported.")
    tested = any(r.tests for r in analysis.results)
    if tested:
        parts.append("Nested rate laws were compared by likelihood-ratio tests (chi-square with the "
                     "error known, extra-sum-of-squares F with it estimated); restrictions that put "
                     "a constant at infinity were referred to the 50:50 mixture of chi-square(0) and "
                     "chi-square(1) (Self & Liang 1987), and non-nested laws were described by AICc "
                     "(Hurvich & Tsai 1989) without a test.")
    if any(law.lack_of_fit is not None for r in analysis.results for law in r.laws.values()):
        parts.append("Lack of fit was tested against pure error from replicates (Draper & Smith).")
    if analysis.comparison is not None:
        parts.append("Differences between groups were tested by fitting each constant shared "
                     "across groups and comparing with separate fits.")
    cited = [c for c in analysis.literature if c.found]
    if cited:
        refs = ", ".join(f"{c.constant} {c.cited:g} {c.cited_unit} (BRENDA ref {c.reference})"
                         for c in cited)
        parts.append(f"Fitted constants were compared with values from {BRENDA_CITATION}: {refs}.")
    parts.append(f"Software: Caterva {_version()} (caterva rates), Python "
                 f"{platform.python_version()}, NumPy {numpy.__version__}, SciPy {scipy.__version__}.")
    return " ".join(parts) + "\n"


__all__ = ["render", "to_json", "parameters_csv", "curves_csv", "methods", "verdict_lines",
           "literature_sentence"]
