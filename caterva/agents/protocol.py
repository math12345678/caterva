"""What an agent is, precisely enough for the scheduler to reason about it.

An agent is a pure function from (declared reads, constraints) to (writes,
new constraints, notes). Not a class with hidden state, not a step in a
script -- because the scheduler re-runs agents when their inputs change, and
an agent that carried state between runs would make the second run differ
from the first for reasons the trace cannot show.

Everything an agent needs comes through its `View`. Everything it produces
comes back in an `AgentResult`. It touches nothing else. That is the whole
contract, and it is what lets the scheduler parallelise, invalidate and
replay without any agent knowing that it does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Tuple, runtime_checkable

try:
    from .blackboard import View
    from .constraints import Constraint
except ImportError:  # pragma: no cover - flat import
    from blackboard import View  # type: ignore[no-redef]
    from constraints import Constraint  # type: ignore[no-redef]


@dataclass(frozen=True)
class AgentResult:
    """What one agent run produced."""

    #: New values, keyed by blackboard key. Must be a subset of the agent's
    #: declared `writes`; the scheduler raises `UndeclaredWrite` otherwise.
    writes: Mapping[str, Any] = field(default_factory=dict)

    #: Requirements this agent discovered. These are what make the run
    #: iterate: a critic that only reported would leave the search where it
    #: was.
    constraints: Tuple[Constraint, ...] = ()

    #: Human-readable findings that are not requirements -- observations
    #: worth showing the reader but which do not change what anything else
    #: should do.
    notes: Tuple[str, ...] = ()

    #: Set when the agent could not do its job. Distinct from writing an
    #: empty result: "BRENDA returned nothing" and "BRENDA was unreachable"
    #: are different facts and a model built on the first is honest while
    #: one built on the second is an outage presented as a literature gap.
    failed: bool = False
    failure: str = ""


@runtime_checkable
class Agent(Protocol):
    """The interface the scheduler programs against."""

    #: Unique within a run; appears in the trace and in every entry.
    name: str

    #: Blackboard keys this agent may read. The scheduler builds the
    #: dependency graph from these, and `View` enforces them.
    reads: Tuple[str, ...]

    #: Blackboard keys this agent may write.
    writes: Tuple[str, ...]

    def run(self, view: View) -> AgentResult:
        ...


@dataclass(frozen=True)
class FunctionAgent:
    """An agent built from a plain function.

    Most agents have no state worth a class. This keeps them functions while
    still carrying the declarations the scheduler needs.
    """

    name: str
    reads: Tuple[str, ...]
    writes: Tuple[str, ...]
    fn: Any

    def run(self, view: View) -> AgentResult:
        return self.fn(view)


__all__ = ["Agent", "AgentResult", "FunctionAgent"]
