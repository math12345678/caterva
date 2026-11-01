"""The three straight-line plots, for teaching, never for the answer.

    Lineweaver-Burk   1/v against 1/[S]:   intercept 1/Vmax, slope Km/Vmax
    Eadie-Hofstee     v against v/[S]:     intercept Vmax, slope -Km
    Hanes-Woolf       [S]/v against [S]:   intercept Km/Vmax, slope 1/Vmax

Each is the Michaelis-Menten law rearranged into a straight line, and each
gives a different Km and Vmax from the same rates, because the
rearrangement moves the error around: 1/v turns a small error on a small
rate into a large error on a large 1/v, so an unweighted straight line
through the Lineweaver-Burk points is pulled hardest by the least precise
rates; Eadie-Hofstee puts v on both axes, so its errors are no longer in one
variable; Hanes-Woolf divides by v too, so its errors are not the rates'
either, and none of the three is the weighting the rates' own errors call
for. Dowd & Riggs
(1965, J. Biol. Chem. 240:863, PubMed 14275146) compared estimates from the
three; Cornish-Bowden (Fundamentals of Enzyme Kinetics, 4th ed., 2012)
treats the plots as ways to SEE data and the nonlinear fit as the way to
estimate from it. That is how they are used here: printed beside the
nonlinear fit with --show-linearizations, and never the reported estimate.

Each straight line is ordinary unweighted least squares, which is what a
student drawing the plot is doing, per inhibitor concentration (each line
of a Lineweaver-Burk plot of an inhibition experiment is one [I]).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

PLOTS = ("Lineweaver-Burk", "Eadie-Hofstee", "Hanes-Woolf")

WHY = (
    "The three straight-line estimates differ from the nonlinear fit, and from one another, "
    "because each rearrangement reweights the errors: 1/v magnifies the error of the smallest "
    "rates most, so a straight line through the transformed points gives the least precise "
    "rates the most pull (Dowd & Riggs 1965, J. Biol. Chem. 240:863; Cornish-Bowden, "
    "Fundamentals of Enzyme Kinetics, 4th ed., 2012). They are shown to be looked at; the "
    "nonlinear fit is the estimate."
)


@dataclass
class Line:
    plot: str
    x_label: str
    y_label: str
    points: List[Tuple[float, float]]
    slope: Optional[float]
    intercept: Optional[float]
    vmax: Optional[float]
    km: Optional[float]
    note: str = ""


@dataclass
class Linearization:
    inhibitor: float
    group: Optional[str]
    lines: List[Line] = field(default_factory=list)


def _line(x: np.ndarray, y: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
    if len(set(x.tolist())) < 2:
        return None, None
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)


def linearize(s: Sequence[float], v: Sequence[float]) -> List[Line]:
    """The three plots of one set of (S, v), with the constants each line gives."""
    s = np.asarray(s, dtype=float)
    v = np.asarray(v, dtype=float)
    keep = (s > 0) & (v > 0)
    s, v = s[keep], v[keep]
    out: List[Line] = []

    x, y = 1.0 / s, 1.0 / v
    slope, intercept = _line(x, y)
    vmax = km = None
    note = ""
    if slope is not None and intercept is not None:
        if intercept > 0:
            vmax, km = 1.0 / intercept, slope / intercept
        else:
            note = "the line meets the 1/v axis at or below zero: no positive Vmax"
    out.append(Line(PLOTS[0], "1/[S]", "1/v", list(zip(x.tolist(), y.tolist())), slope, intercept,
                    vmax, km, note))

    x, y = v / s, v
    slope, intercept = _line(x, y)
    vmax = km = None
    note = ""
    if slope is not None and intercept is not None:
        if slope < 0 and intercept > 0:
            vmax, km = intercept, -slope
        else:
            note = "the line does not fall from a positive intercept: no positive Km"
    out.append(Line(PLOTS[1], "v/[S]", "v", list(zip(x.tolist(), y.tolist())), slope, intercept,
                    vmax, km, note))

    x, y = s, s / v
    slope, intercept = _line(x, y)
    vmax = km = None
    note = ""
    if slope is not None and intercept is not None:
        if slope > 0 and intercept > 0:
            vmax, km = 1.0 / slope, intercept / slope
        else:
            note = "the line does not rise from a positive intercept: no positive Km"
    out.append(Line(PLOTS[2], "[S]", "[S]/v", list(zip(x.tolist(), y.tolist())), slope, intercept,
                    vmax, km, note))
    return out


def by_inhibitor(s: Sequence[float], v: Sequence[float], i: Optional[Sequence[float]],
                 group: Optional[str] = None) -> List[Linearization]:
    s = np.asarray(s, dtype=float)
    v = np.asarray(v, dtype=float)
    i = np.zeros_like(s) if i is None else np.asarray(i, dtype=float)
    out = []
    for level in sorted(set(i.tolist())):
        rows = i == level
        out.append(Linearization(level, group, linearize(s[rows], v[rows])))
    return out


__all__ = ["PLOTS", "WHY", "Line", "Linearization", "linearize", "by_inhibitor"]
