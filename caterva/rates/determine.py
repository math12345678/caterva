"""What the data determine, what they do not, and what to measure instead.

THE FAILURE THIS MODULE EXISTS FOR
----------------------------------
Fit Michaelis-Menten to rates measured only well below Km and the optimiser
still returns a Vmax and a Km. Neither is determined: at [S] << Km the law
is v = (Vmax/Km)[S], so every pair with the same ratio fits equally well,
and the pair printed is wherever the search happened to stop. Printed with
a +-2 SE interval it looks like a measurement; printed with an interval
that runs below zero it at least looks wrong. Neither is what the data say,
which is: Vmax/Km is known to within this interval; Km is larger than this
bound; nothing more.

HOW IT IS DETECTED
------------------
From the profiles (fit.py), not from a rule about [S] against a guessed Km.
A constant whose profile never rises to the threshold before the search's
edge is not bounded on that side. Three patterns are named:

  Km and Vmax both unbounded above: every [S] is well below Km, and only
      Vmax/Km is determined. Its interval is the profile of the product
      Vmax * Km^-1, refitting Km freely at each value, so it carries the
      uncertainty of the Km that the data could not fix.
  Km unbounded below, Vmax bounded: every [S] is well above Km, and only
      Vmax is determined; Km is below a stated bound.
  Any other constant unbounded on a side: the one-sided statement, and what
      concentration range would bound it.

The Jacobian's condition number is reported beside this, as a second
opinion; the profile is the one decisions are made on, because a
condition number cannot say WHICH direction is undetermined or give the
one-sided bound a reader needs.

WHETHER THE RANGE BRACKETS Km
-----------------------------
The design guideline used is the Assay Guidance Manual's: "Measure the
initial velocity of the reaction at substrate concentrations between
0.2-5.0 Km" with "8 or more substrate concentrations", and "multiple points
above and below the Km" (Brooks HB, Geeganage S, Kahl SD, Montrose C,
Sittampalam S, Smith MC, Weidner JR, "Basics of Enzymatic Assays for HTS",
in Markossian S et al., eds., Assay Guidance Manual, Eli Lilly & Company and
NCATS, 2004-, chapter updated 1 October 2012; NCBI Bookshelf NBK92007, PMID
22553875). The wording was checked on 2026-09-30 in the chapter's own XML,
eabasics.nxml in NCBI's open-access Bookshelf archive of the manual
(pub/litarch, assayguide_NBK53196.tar.gz), under the heading "How to measure
Km"; the HTML page sits behind a robot check.

A range is said to bracket Km when at least two distinct concentrations lie
on each side of it. The recommendation is eight
concentrations evenly spaced on a log scale from 0.2 times the lowest Km the
interval allows to 5 times the highest, so the guideline holds wherever in
its interval Km turns out to be.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from caterva.rates.fit import Fit, Interval, profile_product
from caterva.rates.models import ROLE_INHIBITOR

#: The Assay Guidance Manual's design range and count (docstring above).
LOW_MULTIPLE = 0.2
HIGH_MULTIPLE = 5.0
RECOMMENDED_COUNT = 8
#: "Multiple points above and below the Km", read as at least two.
EACH_SIDE = 2


@dataclass
class DesignAdvice:
    km_label: str
    km: float
    km_low: Optional[float]
    km_high: Optional[float]
    distinct: int
    below: int
    above: int
    inside: int
    span: tuple
    brackets: bool
    recommended: List[float] = field(default_factory=list)
    text: List[str] = field(default_factory=list)


@dataclass
class Determination:
    #: One sentence per finding, most important first.
    findings: List[str] = field(default_factory=list)
    #: Constants (labels) the data do not bound on at least one side.
    undetermined: List[str] = field(default_factory=list)
    #: Products that ARE determined when their factors are not (Vmax/Km).
    products: List[Interval] = field(default_factory=list)
    design: Optional[DesignAdvice] = None


def _sig(value: float, digits: int = 2) -> float:
    if value <= 0 or not math.isfinite(value):
        return value
    return round(value, -int(math.floor(math.log10(abs(value)))) + digits - 1)


def determine(fitted: Fit, intervals: Sequence[Interval], units: Dict[str, str],
              level: float) -> Determination:
    """What this fit's data determine. `units` maps a parameter label to its
    unit, for the sentences."""
    problem = fitted.problem
    out = Determination()
    by_label = {iv.label: iv for iv in intervals}
    law = problem.law
    names = problem.constants
    labels = problem.labels

    # The Vmax/Km pattern, per group (a shared fit has one Vmax or Km).
    for _rows, index in problem.maps:
        roles = {law.constants[k].name: index[k] for k in range(len(index))}
        v_k = roles.get("Vmax")
        km_k = roles.get("Km", roles.get("K_half"))
        if v_k is None or km_k is None:
            continue
        v_iv, km_iv = intervals[v_k], intervals[km_k]
        km_name = labels[km_k]
        if km_iv.high is None and v_iv.high is None:
            ratio = profile_product(fitted, {v_k: 1.0, km_k: -1.0}, level,
                                    f"{labels[v_k]}/{km_name}")
            if ratio is not None and ratio not in out.products:
                out.products.append(ratio)
            lead = (f"Every substrate concentration is well below {km_name}: the data determine "
                    f"only {labels[v_k]}/{km_name}")
            if ratio is not None and ratio.bounded:
                lead += (f" = {ratio.estimate:.4g} ({level:.0%} interval {ratio.low:.4g} to "
                         f"{ratio.high:.4g} {_ratio_unit(units, labels[v_k], km_name)})")
            lead += (f", and neither constant alone. {km_iv.describe(units.get(km_name, ''))}; "
                     f"{v_iv.describe(units.get(labels[v_k], ''))}. Estimates of either are "
                     f"not reported, because any pair with that ratio fits these data equally well.")
            out.findings.append(lead)
            for label in (labels[v_k], km_name):
                if label not in out.undetermined:
                    out.undetermined.append(label)
        elif km_iv.low is None and v_iv.bounded:
            out.findings.append(
                f"Every substrate concentration is well above {km_name}: the data determine "
                f"{labels[v_k]} ({v_iv.low:.4g} to {v_iv.high:.4g} {units.get(labels[v_k], '')}) "
                f"and only an upper bound on {km_name}: "
                f"{km_iv.describe(units.get(km_name, ''))}.")
            if km_name not in out.undetermined:
                out.undetermined.append(km_name)

    for label, name in zip(labels, names):
        if label in out.undetermined:
            continue
        iv = by_label[label]
        if iv.bounded:
            continue
        out.undetermined.append(label)
        role = law.constant(name).role
        unit = units.get(label, "")
        sentence = iv.describe(unit) + "."
        if role == ROLE_INHIBITOR and iv.high is None:
            if name == "Ki_prime":
                sentence += (" The inhibitor's binding to the enzyme-substrate complex is too weak "
                             "to see at these concentrations; it shows at [S] well above Km with "
                             f"[I] above about {iv.low:.3g} {unit}.")
            else:
                sentence += (" The inhibitor's binding to free enzyme is too weak to see at these "
                             "concentrations; it shows at [S] well below Km with [I] above about "
                             f"{iv.low:.3g} {unit}.")
        elif name == "Ksi" and iv.high is None:
            sentence += (" No substrate inhibition is detectable in this range; it would show at "
                         f"[S] approaching {iv.low:.3g} {unit} or above.")
        out.findings.append(sentence)
    return out


def _ratio_unit(units: Dict[str, str], top: str, bottom: str) -> str:
    a, b = units.get(top, ""), units.get(bottom, "")
    if a and b:
        return f"{a} per {b}"
    return a or ""


def design_advice(km_interval: Interval, substrate: Sequence[float], unit: str) -> DesignAdvice:
    """How the substrate concentrations sit against Km, and what would
    satisfy the design guideline (module docstring)."""
    km = km_interval.estimate
    values = sorted({float(s) for s in substrate if s > 0})
    below = sum(1 for s in values if s < km)
    above = sum(1 for s in values if s > km)
    inside = sum(1 for s in values if LOW_MULTIPLE * km <= s <= HIGH_MULTIPLE * km)
    span = (values[0] / km, values[-1] / km) if values else (float("nan"), float("nan"))
    brackets = below >= EACH_SIDE and above >= EACH_SIDE
    advice = DesignAdvice(km_interval.label, km, km_interval.low, km_interval.high, len(values),
                          below, above, inside, span, brackets)
    label = km_interval.label
    u = f" {unit}" if unit else ""
    if km_interval.high is None and km_interval.low is not None:
        floor = HIGH_MULTIPLE * km_interval.low
        advice.text.append(
            f"The substrate range cannot place {label}: it is above {km_interval.low:.3g}{u}, "
            f"and the highest concentration used is {values[-1]:.3g}{u}. Extend the highest "
            f"concentration to at least {_sig(floor):g}{u} (5 times the smallest {label} these "
            f"data allow), then space {RECOMMENDED_COUNT} concentrations from 0.2 to 5 times "
            f"{label} once it is located.")
        return advice
    if km_interval.low is None and km_interval.high is not None:
        ceiling = LOW_MULTIPLE * km_interval.high
        advice.text.append(
            f"The substrate range cannot place {label}: it is below {km_interval.high:.3g}{u}, "
            f"and the lowest concentration used is {values[0]:.3g}{u}. Bring the lowest "
            f"concentration down to {_sig(ceiling):g}{u} or below (0.2 times the largest "
            f"{label} these data allow).")
        return advice
    if not km_interval.bounded:
        advice.text.append(f"{label} is not determined in either direction, so no range can be "
                           f"recommended from these data.")
        return advice
    advice.text.append(
        f"Your {len(values)} substrate concentration(s) span {span[0]:.2g} to {span[1]:.2g} "
        f"times {label} (below {label}: {below}; above: {above}; in the guideline range of 0.2 "
        f"to 5 times {label}: {inside}). The Assay Guidance Manual asks for "
        f"{RECOMMENDED_COUNT} or more in that range, with several on each side of {label}.")
    if brackets and inside >= RECOMMENDED_COUNT:
        advice.text.append(f"The range brackets {label} as the guideline asks.")
        return advice
    low = LOW_MULTIPLE * km_interval.low
    high = HIGH_MULTIPLE * km_interval.high
    ratio = (high / low) ** (1.0 / (RECOMMENDED_COUNT - 1))
    advice.recommended = [_sig(low * ratio ** k) for k in range(RECOMMENDED_COUNT)]
    reason = ("does not bracket " + label if not brackets
              else f"brackets {label} with fewer than {RECOMMENDED_COUNT} concentrations in the guideline range")
    advice.text.append(
        f"The range {reason}. Eight concentrations evenly spaced on a log scale from 0.2 times "
        f"the lowest to 5 times the highest {label} in its interval would satisfy the guideline "
        f"wherever {label} lies: " + ", ".join(f"{x:g}" for x in advice.recommended) + f"{u}.")
    return advice


__all__ = ["Determination", "DesignAdvice", "determine", "design_advice",
           "LOW_MULTIPLE", "HIGH_MULTIPLE", "RECOMMENDED_COUNT"]
