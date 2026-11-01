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

THE BUFFER AXIS IS CATEGORICAL, AND SILENCE IS NOT COMPLIANCE
-------------------------------------------------------------
A buffer has no graded distance -- two buffers are either the same identity
or they are not -- so there is no "how far out" to measure on that axis.
"Same identity" is `buffers_equivalent` (Tests/assay_conditions.py): the one
rule the model judge already uses when it reports a `buffer_mismatch`, so
this module answers the same question the same way (ADR 0027). Where a
silent pH or temperature is skipped because the axes that ARE stated still
carry information, a row silent on a DEMANDED buffer is NOT inside the
window: claiming that a row measured in an unknown buffer satisfies "must be
in 0.1 M MOPS buffer" is reporting silence as proximity, the exact error
this module exists to refuse. The axis is demanded only when the reference
states a buffer; a window whose reference states none demands none.

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
from typing import Any, Callable, Optional, Tuple

#: The kind of constraint this module gives its name to. Emission sites still
#: write `kind="assay_window"` and honouring sites `constraints_of_kind(
#: "assay_window")` as literals, because the actionability guard
#: (scripts/check_constraints_are_actionable.py) can only match a literal
#: vocabulary. This constant exists for the tests to refer to by name.
WINDOW_KIND = "assay_window"

_NUMBER = r"[-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?"
_PH_RE = re.compile(rf"\bpH ({_NUMBER})")
_TEMPERATURE_RE = re.compile(rf"\btemperature ({_NUMBER})")
_BUFFER_RE = re.compile(r"\bbuffer (.+?)(?:; |$)")


def _buffers_equivalent() -> Callable[[Optional[str], Optional[str]], bool]:
    """The buffer-equality predicate, imported lazily.

    `Tests/assay_conditions.py` owns it as the single offline rule shared
    with the model judge. Imported lazily for the same reason the thresholds
    are: the flat-import fallback keeps the agent package importable without
    `Tests` on the path.
    """
    try:
        from Tests.assay_conditions import buffers_equivalent  # type: ignore
        return buffers_equivalent
    except ImportError:  # pragma: no cover - flat import
        from caterva.checkout import literature_module
        buffers_equivalent = literature_module(
            "assay_conditions").buffers_equivalent
        return buffers_equivalent


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
        from caterva.checkout import literature_module
        _compat = literature_module("model_compatibility")
        PH_UNITS_SERIOUS = _compat.PH_UNITS_SERIOUS
        TEMPERATURE_C_SERIOUS = _compat.TEMPERATURE_C_SERIOUS
        return PH_UNITS_SERIOUS, TEMPERATURE_C_SERIOUS


def _axis(prefix: str, value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return f"{prefix} {value:g}"


def _buffer_axis(buffer: Optional[str]) -> Optional[str]:
    if buffer is None or not str(buffer).strip():
        return None
    return f"buffer {' '.join(str(buffer).split())}"


def window_requirement(
    *,
    ph: Optional[float],
    temperature_c: Optional[float],
    buffer: Optional[str] = None,
) -> str:
    """The canonical text of an assay window, as a constraint requirement.

    Only the axes the reference states appear. A window with neither scalar
    axis is rejected before it is ever called (the critic never emits one,
    because a window naming only a buffer is unsatisfiable by construction --
    distance needs a numeric axis); the empty requirement is returned rather
    than half-invented, so the parse is total on anything the pair produces.
    """
    return "; ".join(
        part
        for part in (
            _axis("pH", ph),
            _axis("temperature", temperature_c),
            _buffer_axis(buffer),
        )
        if part is not None
    )


def parse_window_requirement(
    requirement: str,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Back to `(ph, temperature_c, buffer)`, exactly as formatted; `None`
    when the window does not name that axis."""
    ph_match = _PH_RE.search(requirement)
    temp_match = _TEMPERATURE_RE.search(requirement)
    buffer_match = _BUFFER_RE.search(requirement)
    return (
        float(ph_match.group(1)) if ph_match else None,
        float(temp_match.group(1)) if temp_match else None,
        " ".join(buffer_match.group(1).split()) if buffer_match else None,
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

    BUFFER IS NOT A DISTANCE, AND THIS RETURNS NO BUFFER TERM. A different
    buffer is a categorical mismatch, not a measured "how far": turning a
    wrong buffer into a deviation would give it a graded severity the judge
    never claimed. The buffer is enforced as a hard gate in `within_window`
    instead -- a row that states a different buffer (or is silent under a
    buffer-naming window) is outside no matter how close its numbers are.
    The rank a scout compares rows by therefore never sees a
    buffer-mismatched row: `within_window` has already excluded it, so the
    distance ordering among eligible rows is the ordering this module means.

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


def _buffer_satisfied(candidate: Any, reference_buffer: Optional[str]) -> bool:
    """Whether a row satisfies the window's buffer axis, if it has one.

    The reference states a buffer -> the row MUST state an equivalent one:
    silence is not compliance (see the module docstring). The reference
    states none -> the window demands no buffer, and every row passes.
    """
    if reference_buffer is None:
        return True
    row_buffer = candidate.get("buffer")
    if row_buffer is None:
        return False
    return _buffers_equivalent()(reference_buffer, row_buffer)


def within_window(
    candidate: Any,
    *,
    reference_ph: Optional[float],
    reference_temperature_c: Optional[float],
    reference_buffer: Optional[str] = None,
) -> bool:
    """Whether one row satisfies one window.

    The guard the critic uses before emitting and the scout uses while
    re-selecting -- one implementation of "in or out", not one each.

    Inside requires BOTH the scalar distance and the buffer gate: a wrong
    buffer is not a matter of degree (see `candidate_distance`).
    """
    distance = candidate_distance(
        candidate,
        reference_ph=reference_ph,
        reference_temperature_c=reference_temperature_c,
    )
    return (
        distance is not None
        and distance <= 1.0
        and _buffer_satisfied(candidate, reference_buffer)
    )


__all__ = [
    "WINDOW_KIND",
    "window_requirement",
    "parse_window_requirement",
    "candidate_distance",
    "within_window",
]