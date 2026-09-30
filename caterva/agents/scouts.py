"""One agent per unknown constant, searching the literature in parallel.

WHAT MAKES A SCOUT DIFFERENT FROM A LOOKUP
------------------------------------------
`resolve_kinetic_value` already answers "what is the Km of this enzyme".
A scout answers "what is the Km of this enzyme, given everything the rest of
the run has since discovered" -- and re-answers it when that changes.

It declares no blackboard reads. Its only input besides its own request is
the constraint store, which every agent can see, so the scheduler re-runs it
exactly when the constraints move. That is the loop: the coherence critic
finds two organisms, requires one, and every scout searches again inside it.

WHAT A SCOUT WILL NOT DO
------------------------
It will not widen its own search to succeed. If a constraint rules out the
only value that exists, the scout returns a gap and says which constraint
closed it. A scout that quietly dropped the organism requirement to come
back with something would produce exactly the value the critic rejected,
wearing the critic's approval.

RE-SELECTION IS CHOICE AMONG MEASURED ROWS, NOT INVENTED NUMBERS
----------------------------------------------------------------
The one exception to "the resolver's answer stands" is an assay window
(ADR 0171). The resolver already returns the whole graded frontier of rows
it considered (`ensemble_candidates`); when a constraint demands that this
value sit inside another value's conditions, the scout re-selects among
those SAME rows -- the row that actually sits at the reference. It never
interpolates, averages or corrects toward the window, because the rows are
already there and "adjust the number to fit" is the exact fabrication this
codebase exists to refuse. If no row of the frontier satisfies the window,
the resolver's choice stands, and the note says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Any, Callable, List, Optional, Tuple

try:
    from .assay_window import (
        candidate_distance,
        parse_window_requirement,
        window_requirement,
        within_window,
    )
    from .blackboard import View
    from .constraints import ANY_SUBJECT, Constraint
    from .protocol import AgentResult
    from .adapters import citation_text, to_parameter_source
except ImportError:  # pragma: no cover - flat import
    from assay_window import (  # type: ignore[no-redef]
        candidate_distance,
        parse_window_requirement,
        window_requirement,
        within_window,
    )
    from blackboard import View  # type: ignore[no-redef]
    from constraints import ANY_SUBJECT, Constraint  # type: ignore[no-redef]
    from protocol import AgentResult  # type: ignore[no-redef]
    from adapters import citation_text, to_parameter_source  # type: ignore[no-redef]

#: Blackboard key for a resolved quantity. One namespace so the critics can
#: declare their reads from the model's quantity list without knowing which
#: scout will serve each one.
PARAM_PREFIX = "param:"


def param_key(quantity: str) -> str:
    return f"{PARAM_PREFIX}{quantity}"


def _number(value: Any) -> Optional[float]:
    """A real numeric row axis, or None for 'not stated'."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _row_description(source: Any) -> str:
    """One line naming a row the reader can find again."""
    parts = []
    if source.ph is not None:
        parts.append(f"pH {source.ph:g}")
    if source.temperature_c is not None:
        parts.append(f"{source.temperature_c:g} C")
    if getattr(source, "buffer", None):
        parts.append(f"in {source.buffer}")
    conditions = ", ".join(parts) or "conditions unstated"
    return f"{source.value} {source.unit or ''} @ {conditions}".strip()


def _row_citation(resolver_citation: Optional[str], reference_id: Any) -> str:
    """The citation of a row the assay window re-selected, in the form the
    adapter cites the resolver's own row (`citation_text`): "BRENDA ref
    670748". The source is read off the resolver's citation, since both rows
    come from one table; the title is never carried, because it is the
    other row's paper. Until 2026-09-30 this was "reference_id:670748", so a
    reader could tell from the citation alone which path had produced it,
    which `citation_text` exists to prevent."""
    found = re.match(r"\s*(\S+) ref \S", resolver_citation or "")
    return citation_text(SimpleNamespace(source=found.group(1) if found else None,
                                         reference_id=str(reference_id)))


def frontier_row(source: Any) -> Optional[dict]:
    """The frontier row a `ParameterSource` carries: the one among its
    `candidates` with its value and its commentary. The resolver's pick, or
    since 2026-09-30 the row an assay window re-selected, whose commentary
    is now its own. None when no row has both, as for a stand-in resolver
    that states no commentary."""
    commentary = getattr(source, "commentary", None) or None
    return next((row for row in getattr(source, "candidates", ()) or ()
                 if row.get("value") == source.value
                 and (row.get("conditions") or None) == commentary), None)


def _describe_windows(
    refs: List[Tuple[Optional[float], Optional[float], Optional[str], Any]],
) -> str:
    return "; ".join(
        window_requirement(ph=ph, temperature_c=temperature_c, buffer=buffer)
        for ph, temperature_c, buffer, _ in refs
    )


def _resolution_cls():
    try:
        from Tests.parameterize import ParameterRequest, Resolution  # type: ignore
        return ParameterRequest, Resolution
    except ImportError:
        # Neither form resolves from an ordinary interpreter; the helper
        # puts the checkout's Tests/ on the path and says so when it cannot
        # (ADR 0178).
        from caterva.checkout import literature_module
        _module = literature_module("parameterize")
        ParameterRequest = _module.ParameterRequest
        Resolution = _module.Resolution
        return ParameterRequest, Resolution


@dataclass(frozen=True)
class ParameterScout:
    """Resolves one quantity, under whatever constraints are in force."""

    request: Any  # ParameterRequest
    #: `(request, organism, allow_cross_species) -> KineticResult`. Injected
    #: so the agent set can be exercised without BRENDA; the default wires
    #: to the live resolver.
    resolve: Callable[..., Any]

    @property
    def name(self) -> str:
        return f"scout:{self.request.quantity}"

    @property
    def reads(self) -> Tuple[str, ...]:
        return ()

    @property
    def writes(self) -> Tuple[str, ...]:
        return (param_key(self.request.quantity),)

    def run(self, view: View) -> AgentResult:
        _, Resolution = _resolution_cls()
        quantity = self.request.quantity

        organism, organism_constraint = self._required_organism(view, quantity)
        allow_cross_species = self._cross_species_allowed(view, quantity)

        result = self.resolve(
            self.request,
            organism=organism,
            allow_cross_species=allow_cross_species,
        )
        source, reason = to_parameter_source(quantity, result)

        notes: List[str] = []
        if source is None and organism_constraint is not None:
            # Say which requirement closed the search. Without this the
            # report reads "no Km found", which is false: one was found and
            # then ruled out, and the reader would go looking for a
            # measurement that is already in the database.
            reason = (
                f"{reason} (searched under the requirement that "
                f"{organism_constraint}, raised by "
                f"{self._who_raised(organism_constraint, 'an earlier round')})"
            )
        if source is not None and organism_constraint is not None:
            notes.append(
                f"{quantity} re-resolved in {organism} after "
                f"{self._who_raised(organism_constraint, 'a critic')} required it"
            )
        if source is not None:
            windows = self._windows(view, quantity)
            if windows:
                source, reason, window_note = self._re_select_under_window(
                    quantity, source, windows, reason
                )
                if window_note is not None:
                    notes.append(window_note)

        return AgentResult(
            writes={
                param_key(quantity): Resolution(
                    request=self.request, source=source, reason=reason,
                    # The resolver's word for a refusal, so compose can tell
                    # "found and withheld for this model" from "not found".
                    outcome=None if source is not None else getattr(result, "source", None),
                )
            },
            notes=tuple(notes),
        )

    def _required_organism(
        self, view: View, quantity: str
    ) -> Tuple[Optional[str], Optional[Constraint]]:
        for constraint in view.constraints_for(quantity):
            if constraint.kind == "organism":
                return constraint.requirement, constraint
        return self.request.organism, None

    @staticmethod
    def _who_raised(constraint: Any, default: str) -> str:
        """Whose requirement this was, in words a reader recognises.

        `<input>` is the blackboard's label for a constraint that came from
        what the caller typed (`assembly.py`). It is exactly right inside
        the agent set and reads as leaked machinery on a page a researcher
        is reading, where the honest translation is "you asked for it".
        """
        raised_by = getattr(constraint, "raised_by", None) or default
        return "your own request" if raised_by == "<input>" else raised_by

    def _cross_species_allowed(self, view: View, quantity: str) -> bool:
        # Default is False: ADR 0024's position is that a value from
        # another organism is offered, never substituted. A constraint can
        # only tighten this, never loosen it -- there is deliberately no
        # constraint kind that turns cross-species use on, because that is
        # the user's decision and no critic is entitled to make it.
        return False

    # -- assay windows (ADR 0171) ------------------------------------

    def _windows(self, view: View, quantity: str) -> Tuple[Constraint, ...]:
        """The assay-window requirements binding this quantity, if any."""
        return tuple(
            c for c in view.constraints_for(quantity) if c.kind == "assay_window"
        )

    def _re_select_under_window(
        self,
        quantity: str,
        source: Any,
        windows: Tuple[Constraint, ...],
        reason: Optional[str],
    ) -> Tuple[Any, Optional[str], Optional[str]]:
        """Re-choose the frontier row inside the windows, when one exists.

        Returns `(source, reason, note)`. Only rows the resolver itself
        returned are eligible; only rows inside EVERY window are chosen; the
        chosen row is the one nearest the reference(s) by the normalised
        distance metric. When the resolver's default choice is already the
        nearest inside row, it stands and the note records that the window
        was satisfied without a change; when no frontier row satisfies the
        window, the default stands too -- re-selecting an outside row would
        be manufacturing an answer the literature does not support.

        A re-selected row is carried as the row it is: its value and unit,
        pH, temperature, buffer, commentary, reference and organism, each
        from its own frontier dict. What stays is what belongs to the
        resolver's answer rather than to one row: the frontier itself
        (`candidates`, which the spread is taken over, and which holds the
        new row), `evidence_only` and `mode_default`.

        The substrate is the one per-row field with nowhere to go:
        `ParameterSource` has none, nor has the Measurement compose builds,
        because a request names one. A request that names none gets rows of
        every substrate the table holds, and the row nearest the window can
        be another substrate's: on the committed LDH turnover page kcat
        moves from 21.1 1/s, a pyruvate row, to 32.0 1/s, an NAD+ row. So
        when the frontier's labels differ (`_score_frontier`'s "substrate")
        the scout's note names both, and so does the line the search's
        summary prints for the re-selection (`ModelBuild.rejected_values`).
        A request that names a substrate labels every row with it, and
        nothing is said.
        """
        refs = []
        for window in windows:
            ph, temperature_c, buffer = parse_window_requirement(window.requirement)
            if ph is None and temperature_c is None:
                # A window with no numeric axis is unsatisfiable by
                # construction (distance needs one) and is never emitted by
                # the critic; a hand-authored one would just loop forever.
                continue
            refs.append((ph, temperature_c, buffer, window))
        if not refs or not source.candidates:
            return source, reason, None

        eligible = [
            candidate
            for candidate in source.candidates
            if all(
                within_window(
                    candidate,
                    reference_ph=ph,
                    reference_temperature_c=temperature_c,
                    reference_buffer=buffer,
                )
                for ph, temperature_c, buffer, _ in refs
            )
        ]
        if not eligible:
            return (
                source,
                reason,
                f"{quantity}: no row the resolver returned satisfies the "
                f"assay window ({_describe_windows(refs)}), so its choice "
                f"stands -- re-selecting an outside row would invent a "
                f"measurement",
            )

        def rank(candidate: Any) -> float:
            return max(
                candidate_distance(
                    candidate,
                    reference_ph=ph,
                    reference_temperature_c=temperature_c,
                )
                for ph, temperature_c, _, _ in refs
            )

        def value_of(candidate: Any) -> float:
            return float(candidate["value"])

        # Distance ties are decided by the resolver's own preference (the
        # smallest value), so a re-selection never behaves differently from
        # the resolver on the question the window leaves open.
        best = min(eligible, key=lambda c: (rank(c), value_of(c)))

        if best["value"] == source.value:
            return (
                source,
                reason,
                f"{quantity} is already the nearest frontier row inside "
                f"the assay window ({_describe_windows(refs)}), so its "
                f"choice stands",
            )

        chosen = replace(
            source,
            value=value_of(best),
            unit=best.get("unit") or source.unit,
            ph=_number(best.get("ph")),
            temperature_c=_number(best.get("temperature_c")),
            # The row's own parsed buffer, exactly as the frontier carries it
            # (ADR 0175). None when the row states no buffer -- the honest
            # form of "the window matched on pH, and this row's buffer is
            # unknown" -- rather than the old winner's buffer carried forward.
            buffer=best.get("buffer") or None,
            citation=(
                _row_citation(source.citation, best["reference_id"])
                if best.get("reference_id")
                else source.citation
            ),
            # The row's own commentary, verbatim. Everything downstream reads
            # what a row measured from this field: `row_scope` its isoform,
            # inhibition mode, what it was measured versus and the
            # preparation, and every export's SOURCE ROW line and CSV
            # columns. Kept from the resolver's pick, as it was until
            # 2026-09-30, it described a row that was not carried: LDH's
            # turnover number re-selected to 32.0 1/s at pH 8 still read
            # "pH 6.0, 25°C, ... in presence of fructose 1,6-bisphosphate",
            # the 21.1 1/s row it replaced.
            commentary=best.get("conditions") or None,
            # The re-selected row is a different measurement; the frontier
            # dict carries the conditions axes (ph, temperature_c, buffer)
            # but not the winner's explicitly_unreported claims, so none are
            # carried forward for it.
            explicitly_unreported=(),
        )
        row_organism = best.get("organism") or None
        if row_organism and row_organism != source.organism:
            chosen = replace(
                chosen, organism=row_organism, cross_species=True
            )

        passed_desc = _row_description(source)
        chosen_desc = _row_description(chosen)
        new_reason = (
            f"re-selected {quantity} under the assay window "
            f"({_describe_windows(refs)}) raised by "
            f"{refs[0][3].raised_by or 'a critic'}: chose {chosen_desc} "
            f"(distance {rank(best):g}) over the resolver's default "
            f"{passed_desc}; {len(source.candidates) - len(eligible)} "
            f"of {len(source.candidates)} frontier row(s) fall outside the "
            f"window"
        )
        # Which substrate each row is for, when the frontier's labels say
        # they differ (docstring above): nothing downstream carries it.
        was = (frontier_row(source) or {}).get("substrate")
        now = best.get("substrate")
        if was and now and was != now:
            new_reason += (
                f"; the row chosen is for {now}, the resolver's default for "
                f"{was}"
                + ("" if self.request.substrate else
                   ": the request named no substrate, so its rows are of "
                   "every substrate the table holds")
            )
        return chosen, new_reason, new_reason


def brenda_resolver(**resolver_kwargs: Any) -> Callable[..., Any]:
    """The live resolver, adapted to the scout's calling convention.

    Imported lazily: `fallback_logic` pulls in httpx and a dozen sibling
    modules, and the architecture must be testable without any of them.
    """

    def resolve(request: Any, *, organism: Optional[str], allow_cross_species: bool):
        try:
            from Tests.fallback_logic import resolve_kinetic_value  # type: ignore
        except ImportError:
            # Neither form resolves from an ordinary interpreter; the
            # checkout's Tests/ has to be put on the path (ADR 0178).
            from caterva.checkout import literature_module
            resolve_kinetic_value = literature_module(
                "fallback_logic").resolve_kinetic_value

        if not request.ec_number:
            raise ValueError(
                f"{request.quantity} needs an EC number to resolve through "
                f"BRENDA; none was identified for {request.subject!r}"
            )
        # What the model is of, when the request says: the resolver ranks
        # by the isoform, and a Ki by the model's inhibition mode and
        # substrate, over every row BRENDA holds, before it chooses one.
        # `caterva compose` fills these (ComposedModel.parameter_requests);
        # a request without them is ranked on evidence alone, as before.
        # `compare_mode` ranks nothing: the resolver answers as with no mode
        # and says what the mode would have returned (compose --any-mode).
        asked = {
            name: getattr(request, name, None)
            for name in ("isoform", "inhibition_mode", "model_substrate", "compare_mode")
            if getattr(request, name, None)
        }
        return resolve_kinetic_value(
            enzyme_ec=request.ec_number,
            organism=organism or "",
            substrate=request.substrate or "",
            enzyme_name=request.subject,
            quantity=request.table or "km",
            allow_cross_species=allow_cross_species,
            **{**asked, **resolver_kwargs},
        )

    return resolve


__all__ = ["ParameterScout", "param_key", "PARAM_PREFIX", "brenda_resolver", "frontier_row"]
