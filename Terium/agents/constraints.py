"""Requirements that agents discover and the rest of the system must respect.

WHY CONSTRAINTS ARE FIRST-CLASS
-------------------------------
The existing pipeline resolves each parameter independently and then, at the
end, reports that they do not compose. That is a diagnosis with no treatment:
the Km came from human and the kcat from E. coli, and nothing goes back and
looks for a human kcat.

A Constraint is that feedback made explicit. When the coherence critic finds
two organisms, it does not only report -- it emits

    Constraint("organism", subject="*", requirement="Homo sapiens")

and the scouts re-run under it. The search is then over parameter SETS
subject to accumulated requirements, not over parameters one at a time.

MONOTONICITY IS THE TERMINATION ARGUMENT
----------------------------------------
The store only ever grows. Nothing is retracted, ever, and `add` is the only
mutator. That gives the scheduler its stopping rule: a round that adds no new
constraint cannot differ from the next one, so the loop has converged.

This does NOT by itself bound the number of rounds, because an agent could
emit an endlessly narrowing sequence of requirements. That is a real failure
mode and it is handled where it belongs -- the scheduler's round cap -- and
reported as non-convergence rather than hidden. See
`test_scheduler.py::TestTermination`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Tuple

#: Applies to every quantity rather than a named one.
ANY_SUBJECT = "*"


@dataclass(frozen=True)
class Constraint:
    """One requirement, discovered by one agent.

    Identity is `(kind, subject, requirement)`. `reason` and `raised_by` are
    annotations for the reader and deliberately excluded: two critics that
    independently conclude the same requirement have found one fact, and
    counting it twice would make the fixpoint check depend on how many
    agents happened to notice.
    """

    kind: str
    subject: str
    requirement: str
    reason: str = ""
    raised_by: str = ""

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.kind, self.subject, self.requirement)

    def applies_to(self, subject: str) -> bool:
        return self.subject in (ANY_SUBJECT, subject)

    def __str__(self) -> str:  # pragma: no cover - display only
        where = "" if self.subject == ANY_SUBJECT else f" [{self.subject}]"
        return f"{self.kind}{where} must be {self.requirement}"


class ConstraintStore:
    """A monotone set of constraints, keyed by `Constraint.key`."""

    def __init__(self, initial: Iterable[Constraint] = ()) -> None:
        self._by_key: Dict[Tuple[str, str, str], Constraint] = {}
        for constraint in initial:
            self.add(constraint)

    def add(self, constraint: Constraint) -> bool:
        """Record a constraint. True when it was not already known.

        The return value is what the scheduler's convergence test reads, so
        the "already known" case must be exact: re-raising a constraint with
        a differently worded `reason` is not new information and must not
        cause another round. The first reason recorded is kept, because it
        is the one whose evidence the trace already holds.
        """
        if constraint.key in self._by_key:
            return False
        self._by_key[constraint.key] = constraint
        return True

    def extend(self, constraints: Iterable[Constraint]) -> List[Constraint]:
        """Add many; return only those that were new."""
        return [c for c in constraints if self.add(c)]

    def for_subject(self, subject: str) -> Tuple[Constraint, ...]:
        """Constraints binding `subject`, including the `*` ones."""
        return tuple(
            c for c in self._by_key.values() if c.applies_to(subject)
        )

    def of_kind(self, kind: str) -> Tuple[Constraint, ...]:
        return tuple(c for c in self._by_key.values() if c.kind == kind)

    def fingerprint(self) -> FrozenSet[Tuple[str, str, str]]:
        """The value the scheduler compares between rounds.

        A frozenset of keys rather than a count: two constraints added and
        one coincidentally identical to a previous one would leave a count
        unchanged while the requirements had in fact moved.
        """
        return frozenset(self._by_key)

    def all(self) -> Tuple[Constraint, ...]:
        return tuple(
            sorted(self._by_key.values(), key=lambda c: c.key)
        )

    def __len__(self) -> int:
        return len(self._by_key)

    def __iter__(self):
        return iter(self.all())

    def __contains__(self, constraint: object) -> bool:
        if not isinstance(constraint, Constraint):
            return False
        return constraint.key in self._by_key


__all__ = ["Constraint", "ConstraintStore", "ANY_SUBJECT"]
