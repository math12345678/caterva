"""One run of `caterva rates`: every fit, test and comparison, before any is printed.

The report (report.py) only formats what this computes, so the human report,
--json and every export are views of one `Analysis` and cannot disagree
about a number.

THE ORDER, AND WHY
------------------
For each group (or the whole table): every law the question needs is
fitted, the restricted laws first, so that each general law is also started
from each restricted optimum (with the extra constant at the edge, or the
two constants equal). A general law then always fits at least as well as
anything it contains, and a likelihood ratio cannot come out negative
because the optimiser missed the boundary. Then the profiles, the lack of
fit, what the data determine, the nested tests and the verdict. Then, across
groups, which constants differ; then the literature.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from caterva.rates import discriminate, groups as group_tests, linearize
from caterva.rates.determine import Determination, DesignAdvice, design_advice, determine
from caterva.rates.fit import Fit, FitRefused, Interval, build_problem, fit, profile_all
from caterva.rates.literature import Comparison, compare
from caterva.rates.models import (
    LAWS, NESTINGS, ROLE_EXPONENT, ROLE_INHIBITOR, ROLE_RATE, ROLE_SUBSTRATE, RateLaw,
    WITH_INHIBITOR, WITHOUT_INHIBITOR, law_for,
)
from caterva.rates.table import INHIBITOR, RATE, SUBSTRATE, Dataset
from caterva.rates.uncertainty import Uncertainty

AUTO = "auto"
MODEL_CHOICES = (AUTO,) + tuple(LAWS)


class Refused(ValueError):
    """The run cannot produce a fit to report: exit code 3."""


@dataclass
class Options:
    model: str = AUTO
    level: float = 0.95
    significance: float = discriminate.DEFAULT_SIGNIFICANCE
    linearizations: bool = False


@dataclass
class LawResult:
    law: RateLaw
    fit: Optional[Fit] = None
    intervals: List[Interval] = field(default_factory=list)
    determination: Optional[Determination] = None
    lack_of_fit: Optional[discriminate.LackOfFit] = None
    aicc: Optional[float] = None
    refused: Optional[str] = None

    def interval(self, label: str) -> Optional[Interval]:
        for iv in self.intervals:
            if iv.label == label:
                return iv
        return None


@dataclass
class GroupResult:
    group: Optional[str]
    rows: List[int]
    laws: Dict[str, LawResult] = field(default_factory=dict)
    tests: Dict[str, discriminate.Test] = field(default_factory=dict)
    verdict: Optional[discriminate.Verdict] = None
    design: Optional[DesignAdvice] = None
    linearizations: List[linearize.Linearization] = field(default_factory=list)

    @property
    def reported(self) -> List[LawResult]:
        names = self.verdict.reported if self.verdict else list(self.laws)
        return [self.laws[n] for n in names if n in self.laws and self.laws[n].fit is not None]


@dataclass
class Analysis:
    data: Dataset
    uncertainty: Uncertainty
    options: Options
    results: List[GroupResult] = field(default_factory=list)
    comparison: Optional[group_tests.GroupComparison] = None
    literature: List[Comparison] = field(default_factory=list)
    literature_refused: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def unit_of(self, role: str) -> str:
        column = {ROLE_RATE: RATE, ROLE_SUBSTRATE: SUBSTRATE, ROLE_INHIBITOR: INHIBITOR}.get(role)
        if column is None or column not in self.data.units:
            return ""
        return self.data.units[column].text

    def units_for(self, law: RateLaw, labels: Sequence[str] = ()) -> Dict[str, str]:
        """Parameter label -> unit, for the law's constants and any grouped
        labels ("Km [treated]")."""
        out = {}
        for c in law.constants:
            out[c.label] = self.unit_of(c.role) if c.role != ROLE_EXPONENT else ""
        for label in labels:
            base = label.split(" [", 1)[0]
            if base in out:
                out[label] = out[base]
        return out


def laws_for(data: Dataset, model: str) -> List[str]:
    if model == AUTO:
        return list(WITH_INHIBITOR if data.has_inhibitor else WITHOUT_INHIBITOR)
    law = law_for(model)
    if law.needs_inhibitor and not data.has_inhibitor:
        raise Refused(f"--model {model} needs rates measured with an inhibitor, and the file has "
                      f"no inhibitor concentration above zero")
    if not law.needs_inhibitor and data.has_inhibitor:
        raise Refused(f"--model {model} has no inhibitor in it, and the file has rates measured with "
                      f"one; fitting them to it would treat inhibited rates as uninhibited. Choose "
                      f"an inhibition law, or --model auto")
    return [model]


def _extra_starts(law: RateLaw, special: Fit) -> List[np.ndarray]:
    """A start for a general law from a restricted law's optimum: the extra
    constant at its edge for a boundary nesting (infinity, clipped to the
    search's edge by the caller), or equal to its twin for an interior one
    (Ki' = Ki, or n = 1 with K0.5 = Km)."""
    match = [x for x in NESTINGS if x.general == law.name and x.special == special.law.name]
    if not match:
        return []
    nesting = match[0]
    values = dict(zip(special.law.names, special.theta))
    theta = []
    for c in law.constants:
        if c.name == nesting.to_infinity:
            theta.append(np.inf)
        elif c.name in values:
            theta.append(values[c.name])
        elif c.name == "Ki_prime" and "Ki" in values:
            theta.append(values["Ki"])
        elif c.name == "K_half" and "Km" in values:
            theta.append(values["Km"])
        elif c.name == "n":
            theta.append(0.0)
        else:
            return []
    return [np.asarray(theta, dtype=float)]


def _fit_law(law: RateLaw, data: Dataset, uncertainty: Uncertainty, rows: Sequence[int],
             options: Options, restricted: Dict[str, LawResult], units: Dict[str, str]) -> LawResult:
    out = LawResult(law)
    try:
        problem = build_problem(law, data, uncertainty, rows=rows)
        starts = None
        extra = []
        for special in restricted.values():
            if special.fit is not None:
                extra.extend(_extra_starts(law, special.fit))
        if extra:
            from caterva.rates.fit import grid_starts

            starts = grid_starts(problem) + [np.clip(e, problem.lower, problem.upper) for e in extra]
        fitted = fit(problem, starts=starts)
        fitted, intervals = profile_all(fitted, options.level)
    except FitRefused as exc:
        out.refused = str(exc)
        return out
    out.fit = fitted
    out.intervals = intervals
    out.determination = determine(fitted, intervals, units, options.level)
    out.lack_of_fit = discriminate.lack_of_fit(fitted)
    out.aicc = discriminate.aicc(fitted)
    return out


def _analyse_rows(data: Dataset, uncertainty: Uncertainty, options: Options, rows: List[int],
                  group: Optional[str], names: List[str], analysis: Analysis) -> GroupResult:
    result = GroupResult(group, rows)
    order = [n for n in names if n not in ("mixed", "substrate-inhibition", "hill")] + [
        n for n in names if n in ("mixed", "substrate-inhibition", "hill")]
    for name in order:
        law = law_for(name)
        units = analysis.units_for(law)
        restricted = {n: result.laws[n] for n in result.laws
                      if any(x.general == name and x.special == n for x in NESTINGS)}
        result.laws[name] = _fit_law(law, data, uncertainty, rows, options, restricted, units)
    fits = {n: r.fit for n, r in result.laws.items() if r.fit is not None}
    if not fits:
        reasons = "; ".join(f"{n}: {r.refused}" for n, r in result.laws.items())
        where = f" for group {group!r}" if group else ""
        raise Refused(f"no law could be fitted{where}: {reasons}")
    result.tests = discriminate.tests_for(fits, options.significance)
    intervals = {n: r.intervals for n, r in result.laws.items()}
    units = {}
    for n in fits:
        units.update(analysis.units_for(law_for(n)))
    if len(names) == 1:
        result.verdict = discriminate.Verdict(standing=list(fits), reported=list(fits))
    elif data.has_inhibitor:
        result.verdict = discriminate.inhibition_verdict(fits, intervals, result.tests,
                                                         options.significance, units)
    else:
        result.verdict = discriminate.substrate_verdict(fits, intervals, result.tests,
                                                        options.significance, units)
    first = result.reported[0] if result.reported else None
    if first is not None:
        km = first.interval("Km") or first.interval("K0.5")
        if km is not None:
            s = [data.substrate[r] for r in rows]
            result.design = design_advice(km, s, analysis.unit_of(ROLE_SUBSTRATE))
    if options.linearizations:
        result.linearizations = linearize.by_inhibitor(
            [data.substrate[r] for r in rows], [data.rate[r] for r in rows],
            None if data.inhibitor is None else [data.inhibitor[r] for r in rows], group)
    return result


def analyse(data: Dataset, uncertainty: Uncertainty, options: Options) -> Analysis:
    names = laws_for(data, options.model)
    analysis = Analysis(data, uncertainty, options, notes=list(data.notes))
    labels = data.groups()
    if labels:
        for label in labels:
            rows = data.rows_of(label)
            if len(rows) < 2:
                raise Refused(
                    f"group {label!r} has {len(rows)} row(s); no rate law can be fitted to one rate, "
                    f"and a group comparison needs each group fitted on its own")
        for label in labels:
            analysis.results.append(_analyse_rows(data, uncertainty, options, data.rows_of(label),
                                                  label, names, analysis))
        analysis.comparison = _compare_groups(analysis, names)
    else:
        analysis.results.append(_analyse_rows(data, uncertainty, options, list(range(len(data))),
                                              None, names, analysis))
    return analysis


def _compare_groups(analysis: Analysis, names: List[str]) -> Optional[group_tests.GroupComparison]:
    """The shared-constant tests, with the law every group's verdict agrees
    on. When they disagree, or a verdict is undecided: mixed inhibition for
    rates with an inhibitor, since it contains the other three; Michaelis-
    Menten without, since substrate inhibition and the Hill law each
    contain it and neither contains the other. A note says which was used."""
    chosen = [tuple(r.verdict.reported) if r.verdict else () for r in analysis.results]
    if len(names) == 1:
        law_name = names[0]
    elif all(len(c) == 1 for c in chosen) and len(set(chosen)) == 1:
        law_name = chosen[0][0]
    else:
        law_name = "mixed" if analysis.data.has_inhibitor else "michaelis-menten"
        analysis.notes.append(
            "The groups' own verdicts differ or are undecided ("
            + "; ".join(f"{r.group}: {', '.join(c) or 'none'}" for r, c in zip(analysis.results, chosen))
            + f"), so the comparison of constants between groups uses the {law_name} law for all.")
    per_group = {}
    for r in analysis.results:
        result = r.laws.get(law_name)
        if result is None or result.fit is None:
            analysis.notes.append(
                f"The groups were not compared: the {law_name} law could not be fitted to group "
                f"{r.group!r}" + (f" ({result.refused})" if result is not None and result.refused else ""))
            return None
        per_group[r.group] = result.fit
    try:
        return group_tests.compare_groups(law_for(law_name), analysis.data, analysis.uncertainty,
                                          per_group, analysis.options.level,
                                          analysis.options.significance)
    except FitRefused as exc:
        analysis.notes.append(f"The groups were not compared: {exc}")
        return None


def compare_literature(analysis: Analysis, *, ec: str, organism: Optional[str],
                       substrate: Optional[str], inhibitor: Optional[str], isoform: Optional[str],
                       resolver=None) -> None:
    """Fill `analysis.literature`: the reported law's Km under `substrate`,
    and each reported inhibition law's constant under `inhibitor`."""
    data = analysis.data
    for result in analysis.results:
        reported = result.reported
        if not reported:
            continue
        decided = len(reported) == 1
        if substrate:
            first = reported[0]
            km = first.interval("Km")
            if km is None:
                analysis.literature.append(Comparison(
                    "Km", first.law.name, result.group, substrate, None, None,
                    data.units[SUBSTRATE].text, declined=True,
                    refused=(f"the {first.law.title} law has no Km (its K0.5 is the concentration at "
                             f"half Vmax of a sigmoid, not a Michaelis constant), so it is not "
                             f"compared with a cited Km")))
            else:
                analysis.literature.append(compare(
                    constant="Km", law=first.law, interval=km, column=data.units[SUBSTRATE],
                    ec=ec, organism=organism, compound=substrate, substrate=substrate,
                    isoform=isoform, group=result.group, resolver=resolver,
                    determined=_determined(first, "Km")))
        if inhibitor and data.has_inhibitor:
            for law_result in reported:
                law = law_result.law
                if not law.needs_inhibitor:
                    continue
                label = law.constant(law.literature_ki).label if law.literature_ki else "Ki"
                conditional = None if decided else (
                    "the data do not choose this mechanism over "
                    + ", ".join(r.law.name for r in reported if r is not law_result)
                    + ", so this comparison holds only if it is the right one")
                found = compare(
                    constant=label, law=law, interval=law_result.interval(label),
                    column=data.units[INHIBITOR], ec=ec, organism=organism, compound=inhibitor,
                    substrate=substrate, isoform=isoform, group=result.group, resolver=resolver,
                    conditional=conditional, determined=_determined(law_result, label))
                _relate(found, result)
                analysis.literature.append(found)


def _determined(law: LawResult, label: str) -> bool:
    det = law.determination
    return det is None or label not in det.undetermined


def _relate(found: Comparison, result: GroupResult) -> None:
    """Set a cited row that contradicts the mechanism beside what these rates
    say about that mechanism: the two can be the same finding or opposite
    ones, and the reader should not have to work out which."""
    mode = found.evidence_mode
    if not found.evidence_against or not mode or result.verdict is None:
        return
    if mode in result.verdict.ruled_out:
        found.evidence_against += (f"; these rates rule {mode} inhibition out, so this experiment "
                                   f"and that reference disagree about the mechanism itself")
    elif mode in result.verdict.standing:
        found.evidence_against += (f"; these rates do not rule {mode} inhibition out either")


__all__ = ["AUTO", "MODEL_CHOICES", "Refused", "Options", "LawResult", "GroupResult", "Analysis",
           "analyse", "compare_literature", "laws_for"]
