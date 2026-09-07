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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple

try:
    from .blackboard import View
    from .constraints import ANY_SUBJECT, Constraint
    from .protocol import AgentResult
    from .adapters import to_parameter_source
except ImportError:  # pragma: no cover - flat import
    from blackboard import View  # type: ignore[no-redef]
    from constraints import ANY_SUBJECT, Constraint  # type: ignore[no-redef]
    from protocol import AgentResult  # type: ignore[no-redef]
    from adapters import to_parameter_source  # type: ignore[no-redef]

#: Blackboard key for a resolved quantity. One namespace so the critics can
#: declare their reads from the model's quantity list without knowing which
#: scout will serve each one.
PARAM_PREFIX = "param:"


def param_key(quantity: str) -> str:
    return f"{PARAM_PREFIX}{quantity}"


def _resolution_cls():
    try:
        from Tests.parameterize import ParameterRequest, Resolution  # type: ignore
        return ParameterRequest, Resolution
    except ImportError:
        from parameterize import ParameterRequest, Resolution  # type: ignore
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

        notes: Tuple[str, ...] = ()
        if source is None and organism_constraint is not None:
            # Say which requirement closed the search. Without this the
            # report reads "no Km found", which is false: one was found and
            # then ruled out, and the reader would go looking for a
            # measurement that is already in the database.
            reason = (
                f"{reason} (searched under the requirement that "
                f"{organism_constraint}, raised by "
                f"{organism_constraint.raised_by or 'an earlier round'})"
            )
        if source is not None and organism_constraint is not None:
            notes = (
                f"{quantity} re-resolved in {organism} after "
                f"{organism_constraint.raised_by or 'a critic'} required it",
            )

        return AgentResult(
            writes={
                param_key(quantity): Resolution(
                    request=self.request, source=source, reason=reason
                )
            },
            notes=notes,
        )

    def _required_organism(
        self, view: View, quantity: str
    ) -> Tuple[Optional[str], Optional[Constraint]]:
        for constraint in view.constraints_for(quantity):
            if constraint.kind == "organism":
                return constraint.requirement, constraint
        return self.request.organism, None

    def _cross_species_allowed(self, view: View, quantity: str) -> bool:
        # Default is False: ADR 0024's position is that a value from
        # another organism is offered, never substituted. A constraint can
        # only tighten this, never loosen it -- there is deliberately no
        # constraint kind that turns cross-species use on, because that is
        # the user's decision and no critic is entitled to make it.
        return False


def brenda_resolver(**resolver_kwargs: Any) -> Callable[..., Any]:
    """The live resolver, adapted to the scout's calling convention.

    Imported lazily: `fallback_logic` pulls in httpx and a dozen sibling
    modules, and the architecture must be testable without any of them.
    """

    def resolve(request: Any, *, organism: Optional[str], allow_cross_species: bool):
        try:
            from Tests.fallback_logic import resolve_kinetic_value  # type: ignore
        except ImportError:
            from fallback_logic import resolve_kinetic_value  # type: ignore

        if not request.ec_number:
            raise ValueError(
                f"{request.quantity} needs an EC number to resolve through "
                f"BRENDA; none was identified for {request.subject!r}"
            )
        return resolve_kinetic_value(
            enzyme_ec=request.ec_number,
            organism=organism or "",
            substrate=request.substrate or "",
            enzyme_name=request.subject,
            quantity=request.table or "km",
            allow_cross_species=allow_cross_species,
            **resolver_kwargs,
        )

    return resolve


__all__ = ["ParameterScout", "param_key", "PARAM_PREFIX", "brenda_resolver"]
