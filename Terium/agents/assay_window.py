"""The condition window that turns a pH/temperature mismatch into a search.

WHY A WINDOW, AND WHY ATTACHED TO THE VALUE
-------------------------------------------
The resolver already returns every surviving row with the score that weights
it (`ensemble_candidates`), because the sample weights need per-candidate
scores. That frontier was never re-used as an answer set. When the coherence
critic saw two constants measured at different pH, the frontier was handing
it the fix and nobody looked: "a pH requirement would be a demand nothing
can satisfy" was true of the resolver's one-row answer and false of the
frontier it returned alongside it.

A window makes the demand satisfiable exactly when it should be. The critic
asks "is there a row of your own frontier inside the other value's
conditions?" and -- only then -- emits a `Constraint(kind="assay_window",
...)`; the scout, honouring it, re-selects among the same rows by how far
each sits from the reference. Nothing is invented. No interpolation, no
averaging, no Q10 correction: re-selection means "return the row that
actually sits at those conditions", never "adjust the number to fit".

THE WINDOW IS THE JUDGED THRESHOLD, NOT A SECOND ONE
----------------------------------------------------
This module declares no new "how far is too far". It reuses the thresholds
the model judge already carries -- `PH_UNITS_SERIOUS` and
`TEMPERATURE_C_SERIOUS` from Tests/model_compatibility.py -- as the window
half-widths, for the same reason the resolver reuses its own graded rows: a
second threshold for the same scientific judgement is a second opinion that
drifts, which is ADR 0027's shape. A candidate is inside the window when,
on every axis both it and the reference state, it lies within one of those
thresholds. An axis either side is silent on is skipped; a candidate that
states no conditions is UNASSESSABLE -- never close, never chosen. Reporting
silence as proximity is how a model becomes wrong quietly.

REQUIREMENTS ARE CANONICAL AND ROUND-TRIPPABLE
----------------------------------------------
A constraint's identity is `(kind, subject, requirement)`, so two otherwise
identical windows must render into the SAME string or the store will not
deduplicate them and the run will never converge. `window_requirement` and
`parse_window_requirement` are the only two places the text is formed or
read, and the pair is tested round-trip.
"""

from __future__ import annotations

import re
from typing import Any, Optional, Tuple

#: The kind of constraint this module gives its name to. Emission sites still
#: write `kind="assay_window"` and honouring sites `constraints_of_kind(
#: "assay_window")` as literals, because the actionability guard
#: (scripts/check_constraints_are_actionable.py) can only match a literal
#: vocabulary. This constant exists for the tests to refer to by name.
WINDOW_KIND = "assay_window"

_NUMBER = r"[-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?"
_PH_RE = re.compile(rf"\bpH ({_NUMBER})")
_TEMPERATURE_RE = re.compile(rf"\btemperature ({_NUMBER})")


def _thresholds() -> Tuple[float, float]:
    """The window half-widths, imported lazily.

    `Tests/model_compatibility.py` declares `PH_UNITS_SERIOUS` and
    `TEMPERATURE_C_SERIOUS` as stated judgements carrying their own reasoning.
    Consuming them here rather than copying their values is what makes the
    window "the same question, answered by re-searching" instead of a new,
    looser opinion.
    """
    try:
        from Tests.model_compatibility import (  # type: ignore
            PH_UNITS_SERIOUS,
            TEMPERATURE_C_SERIOUS,
        )
        return PH_UNITS_SERIOUS, TEMPERATURE_C_SERIOUS
    except ImportError:  # pragma: no cover - flat import
        from model_compatibility import (  # type: ignore
            PH_UNITS_SERIOUS,
            TEMPERATURE_C_SERIOUS,
        )
        return PH_UNITS_SERIOUS, TEMPERATURE_C_SERIOUS


def _axis(prefix: str, value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return f"{prefix} {value:g}"


def window_requirement(*, ph: Optional[float], temperature_c: Optional[float]) -> str:
    """The canonical text of an assay window, as a constraint requirement.

    Only the axes the reference states appear. A window with neither axis is
    rejected before it is ever called (the critic never emits one); the empty
    requirement is returned rather than half-invented, so the parse is total
    on anything format produced.
    """
    return "; ".join(
        part
        for part in (_axis("pH", ph), _axis("temperature", temperature_c))
        if part is not None
    )


def parse_window_requirement(requirement: str) -> Tuple[Optional[float], Optional[float]]:
    """Back to `(ph, temperature_c)`, exactly as formatted; `None` when the
    window does not name that axis."""
    ph_match = _PH_RE.search(requirement)
    temp_match = _TEMPERATURE_RE.search(requirement)
    return (
        float(ph_match.group(1)) if ph_match else None,
        float(temp_match.group(1)) if temp_match else None,
    )


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def candidate_distance(
    candidate: Any,
    *,
    reference_ph: Optional[float] = None,
    reference_temperature_c: Optional[float] = None,
) -> Optional[float]:
    """The metric a scout ranks frontier rows by under an assay window.

    Returns the greatest normalised deviation across the axes that BOTH the
    reference and the row state -- Chebyshev distance scaled axis-by-axis,
    with each axis's half-width being the corresponding `*_SERIOUS`
    threshold. A row inside the window has distance at most 1; distance 0 is
    a row sitting exactly on the reference. Returns `None` when no axis is
    comparable, which is exactly the unassessable case and is deliberately
    distinguishable from distance 0: the row is neither inside the window
    nor outside it, and it must not be reported as either.

    The normalisation does not claim the axes are commensurable. It answers
    "how far out is this row, measured with the same ruler the model judge
    uses" -- one unit of pH and one Q10 interval each counting as one step
    of the reference's own judgement.
    """
    ph_half, temperature_half = _thresholds()
    deviations: list = []
    row_ph = _number(candidate.get("ph"))
    row_temp = _number(candidate.get("temperature_c"))
    if reference_ph is not None and row_ph is not None:
        deviations.append(abs(row_ph - reference_ph) / ph_half)
    if reference_temperature_c is not None and row_temp is not None:
        deviations.append(abs(row_temp - reference_temperature_c) / temperature_half)
    if not deviations:
        return None
    return max(deviations)


def within_window(
    candidate: Any,
    *,
    reference_ph: Optional[float],
    reference_temperature_c: Optional[float],
) -> bool:
    """Whether one row satisfies one window.

    The guard the critic uses before emitting and the scout uses while
    re-selecting -- one implementation of "in or out", not one each.
    """
    distance = candidate_distance(
        candidate,
        reference_ph=reference_ph,
        reference_temperature_c=reference_temperature_c,
    )
    return distance is not None and distance <= 1.0


__all__ = [
    "WINDOW_KIND",
    "window_requirement",
    "parse_window_requirement",
    "candidate_distance",
    "within_window",
]