"""kcat from a fitted Vmax and an enzyme concentration you give.

The engine fits Vmax, in the rate's unit. Dividing it by the concentration of
active enzyme in the assay gives the turnover number, `kcat = Vmax / [E]`.
The division is exact for a determined Vmax and its profile interval (the
concentration is a constant, so the interval's ends divide the same way), and
it is the only thing this module does. Three things it will not do:

  * Make a kcat from a Vmax the data do not determine. An open-ended Vmax
    gives a one-sided kcat, and no estimate.
  * Convert a rate that is not a concentration per time. Counts per minute
    cannot become a turnover without a calibration nobody gave.
  * Carry an uncertainty the enzyme concentration was not given. It is taken
    as exact, and the sentence says so: a kcat interval is the interval of
    Vmax alone.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from caterva.rates.analysis import Analysis
from caterva.rates.ingest import normalise_unit
from caterva.rates.table import RATE, UnitRefused, read_unit


class TurnoverRefused(ValueError):
    """The turnover number cannot be made from this fit: the reason."""


def _f(x: Optional[float]) -> Optional[float]:
    return float(x) if x is not None and math.isfinite(x) else None


def enzyme_scale(concentration: float, unit: str) -> float:
    """The enzyme concentration in molar."""
    if not isinstance(concentration, (int, float)) or isinstance(concentration, bool) \
            or not math.isfinite(concentration) or concentration <= 0:
        raise TurnoverRefused("the enzyme concentration must be a positive number")
    text, _changed = normalise_unit(unit)
    try:
        cu = read_unit("enzyme", text, "substrate")
    except UnitRefused as exc:
        raise TurnoverRefused(f"the enzyme concentration's unit: {exc}") from None
    if cu.unit is None:
        raise TurnoverRefused(f"the enzyme concentration {unit!r} is not a molar unit (M, mM, uM, nM or pM); "
                              f"a turnover number needs the molar concentration of active enzyme")
    return float(concentration) * cu.unit.scale


def turnover(analysis: Analysis, concentration: float, unit: str) -> List[Dict[str, Any]]:
    """kcat per group and reported law, in 1/s and 1/min."""
    enzyme_molar = enzyme_scale(concentration, unit)
    rate = analysis.data.units.get(RATE)
    if rate is None or rate.unit is None or rate.kind != "concentration per time":
        raise TurnoverRefused(
            f"the rate is in {rate.text if rate else 'no unit'}, which is not a molar concentration per "
            f"time, so Vmax cannot be divided by an enzyme concentration to give a turnover number. "
            f"Write the rate as uM/min (or another molar unit per time) to get kcat.")
    per_second = rate.unit.scale / enzyme_molar
    rows: List[Dict[str, Any]] = []
    for result in analysis.results:
        for law in result.reported:
            vmax = law.interval("Vmax")
            if vmax is None:
                continue
            det = law.determination
            determined = vmax.bounded and "Vmax" not in (det.undetermined if det else [])
            for unit_text, factor in (("1/s", per_second), ("1/min", per_second * 60.0)):
                rows.append({
                    "group": result.group, "law": law.law.name, "law_title": law.law.title,
                    "constant": "kcat", "unit": unit_text,
                    "estimate": _f(vmax.estimate * factor) if determined else None,
                    "low": _f(vmax.low * factor) if vmax.low is not None else None,
                    "high": _f(vmax.high * factor) if vmax.high is not None else None,
                    "standard_error": _f(vmax.se * factor) if determined and vmax.se is not None else None,
                    "determined": determined, "level": vmax.level,
                    "enzyme": {"concentration": float(concentration), "unit": unit},
                })
    return rows


def sentence(concentration: float, unit: str) -> str:
    return (f"The turnover number kcat is the fitted Vmax divided by the enzyme concentration given "
            f"({concentration:g} {unit}), taken as exact: its interval is Vmax's, and carries no "
            f"uncertainty in that concentration.")


__all__ = ["TurnoverRefused", "enzyme_scale", "sentence", "turnover"]
