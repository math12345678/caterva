"""The resolver's row for this model, and the row the evidence alone would take.

WHY COMPOSE ASKS THE RESOLVER WHAT THE MODEL IS OF
--------------------------------------------------
`caterva compose` used to ask the literature layer's resolver
(Tests/fallback_logic.py, `resolve_kinetic_value`) for each constant on
evidence alone, and then choose among the rows it returned: the isoform
`--isoform` asked for (isoform.py), and for a Ki the model's inhibition mode
(ki_mode.py). Those rows are the resolver's evidence frontier, the few rows no
other row beats on every axis of evidence. The API and the TypeScript CLI ask
the same resolver WITH the isoform and the mode, and it ranks every row it
holds by them before it builds the frontier. The two orders give different
answers where a row of the model's mode is beaten on evidence by a row that
states no mode:

    Trypanosoma cruzi hexokinase and ADP, competitive model, on the recorded
    page (Tests/fixtures/recorded/brenda_2.7.1.1.html.gz):
      0.13 mM  (no commentary)
      1.3 mM   "natural hexokinase from epimastigotes, at pH 7.5"
      1.5 mM   "competitive to ATP"
      7.0 mM   "noncompetitive to glucose"
    The frontier keeps 1.3 alone, the one row with a pH. Compose could only
    carry 1.3, which states no mode; the resolver asked for the mode returns
    1.5, which states the model's.

So compose now asks the resolver with the model's isoform, and for a Ki of an
inhibition motif with its mode and substrate (`ComposedModel.
parameter_requests`), and carries the row it returns. One ranking, applied at
one point, for all three front ends.

WHAT IS LEFT FOR ISOFORM.PY AND KI_MODE.PY
------------------------------------------
Saying what the choice did. The report says which row the model's isoform or
mode replaced and why ("the resolver's pick (0.00059 mM) measured competitive
inhibition ...; the row stating noncompetitive inhibition versus pyruvate
(0.00252 mM) ... is used instead"), every export says why the carried row was
carried, and a row of another mode measured against the model's own substrate
is named as evidence against the model's mechanism. All of that compares the
row carried with the rows it was chosen over, which the resolver's answer to
the question no longer holds: its frontier is of the rows it kept. So the
resolver also returns the answer it would have given unasked
(`KineticResult.evidence_only`: that row first, then its frontier), and
`evidence_view` hands the two selections a Measurement shaped as they have
always read one: the unasked pick as "the resolver's pick", with the asked
row first among the alternatives, then the rest of both frontiers. They choose
as before, and in every case the tests exercise they arrive at the asked row.

WHERE THEY COULD STILL DIFFER, AND WHAT HAPPENS THEN
----------------------------------------------------
The selections rank the rows they are shown; the resolver ranked every row
and then chose among the best-ranked by evidence (its frontier, then the
lowest value). A row the resolver's frontier dropped can therefore lose to a
row the selections see, when the two rank alike for the model: the rows naming
the isoform asked for, say, are several, and the frontier of those alone keeps
a lower value than the first of them the unasked frontier held. `carry`
settles that the one way that keeps the front ends agreeing: the resolver's
row is carried, the report says the resolver ranked every row for the model
and chose it, and its `chosen_because` says so in every export.

With `--any-mode` the resolver is asked for the isoform alone, and the note
saying what the default would carry is ki_mode's, over the rows that answer
holds, exactly as before 2026-09-30. It can therefore be wrong where the
default is now right: for Trypanosoma cruzi and ADP above, `--any-mode`
carries 1.3 mM and says nothing, because 1.5 mM is not among its rows, where
the default carries 1.5 mM. Stated rather than fixed: fixing it costs a
second fetch and parse of BRENDA's page for every constant, on a flag that
exists to turn the choice off.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence

try:
    from caterva.compose.isoform import _from_row
except ImportError:  # pragma: no cover - flat layout
    from compose.isoform import _from_row  # type: ignore[no-redef]


def _row_of(m: Any) -> Dict[str, Any]:
    """A Measurement's own row, as the dicts the resolver's frontiers hold."""
    return {
        "value": float(m.value), "unit": m.unit, "organism": getattr(m, "organism", None),
        "reference_id": getattr(m, "reference_id", None) or _reference(m),
        "conditions": getattr(m, "commentary", None),
        "ph": getattr(m, "assay_ph", None), "temperature_c": getattr(m, "assay_temperature_c", None),
        "buffer": getattr(m, "assay_buffer", None),
    }


def _reference(m: Any) -> Optional[str]:
    try:
        from caterva.compose.ki_mode import _reference as reference
    except ImportError:  # pragma: no cover - flat layout
        from compose.ki_mode import _reference as reference  # type: ignore[no-redef]
    return reference(m)


def same_row(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """One BRENDA row, whichever frontier it came in: its value, commentary
    and reference. Two rows of one paper differ in value or commentary."""
    try:
        if float(a["value"]) != float(b["value"]):
            return False
    except (KeyError, TypeError, ValueError):
        return False
    ref_a, ref_b = a.get("reference_id"), b.get("reference_id")
    return ((a.get("conditions") or None) == (b.get("conditions") or None)
            and (ref_a is None or ref_b is None or str(ref_a) == str(ref_b)))


def _merged(*groups: Sequence[Any]) -> tuple:
    out: List[Dict[str, Any]] = []
    for group in groups:
        for row in group:
            if isinstance(row, dict) and not any(same_row(row, seen) for seen in out):
                out.append(dict(row))
    return tuple(out)


@dataclass
class Narrowed:
    #: The Measurements the selections start from, one per constant.
    measured: Dict[str, Any]
    #: Constant -> the row the resolver returned for this model, for each
    #: constant it was asked about (the rest are absent).
    chosen: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: Constant -> the resolver's own Measurement of that row, with its full
    #: citation, for `carry`.
    answers: Dict[str, Any] = field(default_factory=dict)


def evidence_view(measured: Mapping[str, Any],
                  evidence_only: Mapping[str, Sequence[Mapping[str, Any]]]) -> Narrowed:
    """Each constant the resolver was asked about, as the two selections
    read it: the unasked pick as the resolver's pick, and the asked row
    first among its alternatives. A constant with no `evidence_only` (the
    resolver was asked nothing, or would have returned nothing unasked) is
    passed through as the resolver returned it.

    The alternatives are the asked row, the frontier of the rows the
    resolver kept for the model, and the frontier it would have chosen from
    unasked. They are also what `Measurement.spread` spans, so a model's
    printed spread covers both frontiers. That is the rule compose applied
    before 2026-09-30 whenever a selection moved off the resolver's pick
    (`_from_row` keeps the Measurement's alternatives, then the unasked
    frontier): human LDH and the quinoline sulfonamide, competitive or
    noncompetitive, has always printed 0.00059 to 0.00252 mM. What is new is
    the kept rows' frontier, the rows the resolver itself called equally well
    evidenced for the model, and cases where the carried row changed:
    Trypanosoma cruzi and ADP, competitive, carried 1.3 mM with no spread and
    now carries 1.5 mM with a 1.3 to 1.5 mM spread, since 1.3 is still an
    ADP Ki BRENDA holds for that enzyme."""
    out = Narrowed(measured={})
    for identifier, m in measured.items():
        rows = [r for r in (evidence_only.get(identifier) or ()) if isinstance(r, dict)]
        if not rows:
            out.measured[identifier] = m
            continue
        mine = _row_of(m)
        out.chosen[identifier] = mine
        out.answers[identifier] = m
        alternatives = _merged([mine], getattr(m, "alternatives", ()) or (), rows)
        unasked = rows[0]
        if same_row(unasked, mine):
            out.measured[identifier] = replace(m, alternatives=alternatives)
        else:
            view = _from_row(m, unasked, None)
            out.measured[identifier] = replace(view, alternatives=alternatives)
    return out


def _asked(isoform: Optional[str], mode: Optional[str]) -> str:
    parts = ([isoform] if isoform else []) + ([f"a {mode} model"] if mode else [])
    return " and ".join(parts) or "this model"


def _label(row: Mapping[str, Any], unit: Optional[str]) -> str:
    ref = row.get("reference_id")
    return f"{float(row['value']):g} {unit or row.get('unit') or ''}".rstrip() + (
        f", BRENDA ref {ref}" if ref else "")


def carry(measured: Mapping[str, Any], refused: Mapping[str, str], narrowed: Narrowed,
          modes: Mapping[str, Optional[str]], isoform: Optional[str]) -> tuple:
    """`(measured, refused, notes)` with the resolver's row carried for every
    constant it was asked about. The module docstring says when the
    selections can arrive elsewhere; this is where that is settled, and said.

    `modes` maps a constant to the inhibition mode the resolver was asked
    for it (None for none)."""
    out = dict(measured)
    still_refused = dict(refused)
    notes: List[str] = []
    for identifier, row in narrowed.chosen.items():
        answer = narrowed.answers[identifier]
        carried = out.get(identifier)
        if carried is not None and same_row(_row_of(carried), row):
            continue
        what = _asked(isoform, modes.get(identifier))
        because = (f"the resolver's row for {what}, ranked among every row BRENDA holds "
                   f"before choosing on evidence")
        view = narrowed.measured[identifier]
        out[identifier] = replace(answer, alternatives=getattr(view, "alternatives", ()),
                                  chosen_because=because)
        if carried is None:
            # Unreachable while the selections rank with the resolver's own
            # function: its row ranks first there too. Said, not assumed.
            why = still_refused.pop(identifier, "refused")
            notes.append(
                f"`{identifier}`: the selections here refused it ({why}); the resolver, asked "
                f"for {what}, returns {_label(row, answer.unit)}, which is used")
            continue
        notes.append(
            f"`{identifier}`: choosing among the rows the evidence alone returned arrives at "
            f"{_label(_row_of(carried), carried.unit)}; the resolver, asked for {what}, ranks "
            f"every row BRENDA holds by it before choosing on evidence, and returns "
            f"{_label(row, answer.unit)}, which is used, so this model carries the row the API "
            f"and the TypeScript CLI return for it")
    return out, still_refused, notes


@dataclass
class Selection:
    """What `caterva compose` carries for each constant the search returned."""
    #: The Measurements to build the model from.
    measured: Dict[str, Any]
    #: Constants found and not used, and why: refused by the resolver for
    #: the model's isoform or mode, or (should its rows disagree with the
    #: resolver's) by a selection. Placeholders, never "not found".
    withheld: Dict[str, str] = field(default_factory=dict)
    #: One sentence each: what the isoform and the mode changed, and what a
    #: reader must know about the row carried.
    notes: List[str] = field(default_factory=list)


def select_for_model(search: Any, constants: Mapping[str, tuple], *,
                     substrate: Optional[str], isoform: Optional[str],
                     any_mode: bool) -> Selection:
    """The row each constant carries, from a search whose requests carried
    the model's isoform and modes (`ComposedModel.parameter_requests`).

    In order: constants the resolver refused for the model are withheld,
    with the flag that changes it; the rest go to `isoform.select_isoform`
    (with `isoform`) and then `ki_mode.select_mode`, shown the resolver's
    row beside the row the evidence alone would take (`evidence_view`); and
    `carry` makes sure the row carried is the resolver's. `constants` maps a
    parameter id to (motif name, table), as `ki_mode.constants_of` gives."""
    try:
        from caterva.agents.adapters import NOT_FOUND_REASONS
        from caterva.compose.export import (
            evidence_only_from_search, measured_from_search, unresolved_from_search,
            withheld_by_resolver,
        )
        from caterva.compose.ki_mode import ANY_MODE_FLAG, select_mode
        from caterva.compose.row_scope import INHIBITION_TABLES, MODE_OF_MOTIF
    except ImportError:  # pragma: no cover - flat layout
        from agents.adapters import NOT_FOUND_REASONS  # type: ignore[no-redef]
        from compose.export import (  # type: ignore[no-redef]
            evidence_only_from_search, measured_from_search, unresolved_from_search,
            withheld_by_resolver,
        )
        from compose.ki_mode import ANY_MODE_FLAG, select_mode  # type: ignore[no-redef]
        from compose.row_scope import INHIBITION_TABLES, MODE_OF_MOTIF  # type: ignore[no-redef]

    out = Selection(measured={})
    reasons = unresolved_from_search(search)
    for identifier, outcome in withheld_by_resolver(search).items():
        reason = reasons.get(identifier) or NOT_FOUND_REASONS.get(outcome, outcome)
        if outcome == "mode_withheld":
            reason += (f". Pass {ANY_MODE_FLAG} to use the resolver's pick whatever mode it "
                       f"states; the report still flags it")
        elif outcome == "isoform_withheld" and isoform:
            reason += f" (--isoform {isoform})"
        out.withheld[identifier] = reason

    narrowed = evidence_view(measured_from_search(search), evidence_only_from_search(search))
    measured = narrowed.measured
    refused: Dict[str, str] = {}
    if isoform:
        try:
            from caterva.compose.isoform import select_isoform
        except ImportError:  # pragma: no cover - flat layout
            from compose.isoform import select_isoform  # type: ignore[no-redef]
        by_isoform = select_isoform(measured, isoform)
        measured = by_isoform.measured
        refused.update(by_isoform.refused)
        out.notes.extend(by_isoform.notes)
    # The isoform first, then the mode, over the same ranked rows; ki_mode's
    # docstring says why in that order.
    by_mode = select_mode(measured, constants, substrate=substrate, isoform=isoform,
                          any_mode=any_mode)
    refused.update(by_mode.refused)
    out.notes.extend(by_mode.notes)
    asked_modes = {
        identifier: (None if any_mode or table not in INHIBITION_TABLES
                     else MODE_OF_MOTIF.get(motif or ""))
        for identifier, (motif, table) in constants.items()
    }
    out.measured, refused, carried = carry(by_mode.measured, refused, narrowed, asked_modes,
                                           isoform)
    out.withheld.update(refused)
    out.notes.extend(carried)
    return out


__all__ = ["Narrowed", "Selection", "evidence_view", "carry", "same_row", "select_for_model"]
