"""Runs agents in dependency order, in parallel, until nothing changes.

THE SHAPE
---------
Data flow is a DAG: agent A depends on B when A reads something B writes.
Cycles are rejected at construction, not discovered at runtime, because a
cyclic data dependency has no correct execution order and the useful moment
to say so is before anything has run.

Control flow iterates. The DAG is executed as a round; critics in that round
may emit constraints; a constraint invalidates every value derived without
it; the affected agents re-run. Repeat until a round adds no new constraint.

Keeping those separate is the point. The iteration comes from evidence
arriving, not from the graph, so the graph stays statically checkable and
the iteration stays bounded and reportable.

WHAT RE-RUNS
------------
An agent re-runs when either:

  * the constraint fingerprint changed since its last run -- it may have
    searched a space now known to be too wide; or
  * something it declared as a read has been written since its last run.

Both tests come from declarations that `View` enforces, so an agent cannot
be skipped because of a dependency it forgot to mention.

TERMINATION, STATED HONESTLY
----------------------------
Constraints only accumulate, so a round that adds none is identical to the
next and the loop stops: that is convergence. It is not a bound on rounds --
an agent emitting an endlessly narrowing requirement would keep adding new
constraints forever. `max_rounds` bounds that case, and when it bites the
report says `converged=False` and names the constraints still arriving. A
non-converged run is not presented as a finished one.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

try:
    from .blackboard import Blackboard, UndeclaredWrite, View
    from .constraints import Constraint, ConstraintStore
    from .protocol import Agent, AgentResult
except ImportError:  # pragma: no cover - flat import
    from blackboard import Blackboard, UndeclaredWrite, View  # type: ignore[no-redef]
    from constraints import Constraint, ConstraintStore  # type: ignore[no-redef]
    from protocol import Agent, AgentResult  # type: ignore[no-redef]

#: Enough rounds for a constraint to be discovered, propagate to the scouts,
#: and be re-checked, twice over. A run that needs more is not converging on
#: evidence; it is oscillating, and the report should say so rather than
#: grinding.
DEFAULT_MAX_ROUNDS = 6


class CyclicDependency(ValueError):
    """Agents' reads and writes form a cycle."""


class DuplicateWriter(ValueError):
    """Two agents declare the same write key."""


@dataclass(frozen=True)
class AgentRun:
    agent: str
    round_index: int
    wrote: Tuple[str, ...]
    raised: Tuple[Constraint, ...]
    notes: Tuple[str, ...]
    failed: bool
    failure: str


@dataclass(frozen=True)
class RoundRecord:
    index: int
    ran: Tuple[AgentRun, ...]
    skipped: Tuple[str, ...]
    new_constraints: Tuple[Constraint, ...]
    invalidated: Tuple[str, ...]


@dataclass(frozen=True)
class RunReport:
    rounds: Tuple[RoundRecord, ...]
    converged: bool
    blackboard: Blackboard
    constraints: ConstraintStore
    failures: Tuple[AgentRun, ...]

    @property
    def round_count(self) -> int:
        return len(self.rounds)

    def values(self) -> Dict[str, object]:
        return self.blackboard.snapshot()

    def summary(self) -> str:
        lines = [
            f"{self.round_count} round(s), "
            f"{len(self.constraints)} constraint(s) discovered."
        ]
        if not self.converged:
            still = self.rounds[-1].new_constraints if self.rounds else ()
            lines.append(
                "DID NOT CONVERGE: the round cap was reached while "
                "constraints were still arriving"
                + (
                    " (" + "; ".join(str(c) for c in still) + ")"
                    if still
                    else ""
                )
                + ". Results below are from an unfinished search and should "
                "not be read as a settled answer."
            )
        if self.failures:
            lines.append(
                "Agents that could not complete: "
                + "; ".join(f"{f.agent} ({f.failure})" for f in self.failures)
            )
        return " ".join(lines)


def _levels(agents: Sequence[Agent]) -> Tuple[Tuple[Agent, ...], ...]:
    """Topological levels. Agents in one level are independent."""
    writer_of: Dict[str, str] = {}
    for agent in agents:
        for key in agent.writes:
            if key in writer_of:
                raise DuplicateWriter(
                    f"{key!r} is written by both {writer_of[key]!r} and "
                    f"{agent.name!r}. Two writers means the value depends on "
                    f"execution order, which the scheduler is free to change."
                )
            writer_of[key] = agent.name

    by_name = {a.name: a for a in agents}
    if len(by_name) != len(agents):
        raise ValueError("agent names must be unique within a run")

    depends: Dict[str, Set[str]] = {
        a.name: {
            writer_of[key]
            for key in a.reads
            if key in writer_of and writer_of[key] != a.name
        }
        for a in agents
    }

    placed: Set[str] = set()
    levels: List[Tuple[Agent, ...]] = []
    while len(placed) < len(agents):
        ready = tuple(
            by_name[name]
            for name in sorted(depends)
            if name not in placed and depends[name] <= placed
        )
        if not ready:
            remaining = sorted(set(depends) - placed)
            raise CyclicDependency(
                "these agents depend on each other's output and cannot be "
                f"ordered: {', '.join(remaining)}. Iteration in this "
                "architecture comes from constraints, not from cyclic reads."
            )
        levels.append(ready)
        placed.update(a.name for a in ready)
    return tuple(levels)


class Scheduler:
    def __init__(
        self,
        agents: Sequence[Agent],
        *,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        max_workers: int = 8,
    ) -> None:
        self.agents = tuple(agents)
        self.levels = _levels(self.agents)
        self.max_rounds = max_rounds
        self.max_workers = max_workers

    def run(
        self,
        *,
        seed: Optional[Dict[str, object]] = None,
        initial_constraints: Sequence[Constraint] = (),
    ) -> RunReport:
        blackboard = Blackboard()
        constraints = ConstraintStore(initial_constraints)

        # Seeded values (the user's query, their own measurements) are
        # written by a synthetic agent so they appear in the trace with a
        # provenance like everything else, rather than materialising.
        for key, value in (seed or {}).items():
            blackboard.write(
                key,
                value,
                written_by="<input>",
                round_index=-1,
                constraint_fingerprint=constraints.fingerprint(),
                derived=False,
            )

        #: agent name -> (constraint fingerprint, max read version) at its
        #: last completed run. The staleness test.
        last_run: Dict[str, Tuple[FrozenSet, int]] = {}

        rounds: List[RoundRecord] = []
        failures: List[AgentRun] = []
        converged = False

        for round_index in range(self.max_rounds):
            fingerprint = constraints.fingerprint()
            ran: List[AgentRun] = []
            skipped: List[str] = []
            new_constraints: List[Constraint] = []

            for level in self.levels:
                due = [
                    agent
                    for agent in level
                    if self._should_run(agent, blackboard, fingerprint, last_run)
                ]
                skipped.extend(
                    a.name for a in level if a not in due
                )
                if not due:
                    continue

                # Reads are captured BEFORE running, so an agent's recorded
                # read version reflects what it actually saw. Capturing
                # after would race with writes from its own level -- there
                # are none by construction, but the invariant should not
                # depend on that holding forever.
                read_versions = {
                    agent.name: blackboard.max_version_of(agent.reads)
                    for agent in due
                }

                results = self._execute(due, blackboard, constraints, round_index)

                for agent, result in zip(due, results):
                    undeclared = set(result.writes) - set(agent.writes)
                    if undeclared:
                        raise UndeclaredWrite(
                            f"agent {agent.name!r} wrote "
                            f"{sorted(undeclared)}, which it did not declare. "
                            f"Declared writes: {sorted(agent.writes)}."
                        )
                    for key, value in result.writes.items():
                        blackboard.write(
                            key,
                            value,
                            written_by=agent.name,
                            round_index=round_index,
                            constraint_fingerprint=fingerprint,
                        )
                    fresh = constraints.extend(result.constraints)
                    new_constraints.extend(fresh)

                    record = AgentRun(
                        agent=agent.name,
                        round_index=round_index,
                        wrote=tuple(sorted(result.writes)),
                        raised=tuple(fresh),
                        notes=result.notes,
                        failed=result.failed,
                        failure=result.failure,
                    )
                    ran.append(record)
                    if result.failed:
                        failures.append(record)
                    last_run[agent.name] = (fingerprint, read_versions[agent.name])

            invalidated: Tuple[str, ...] = ()
            if new_constraints:
                # Everything derived under the old constraint set searched a
                # space now known to be too wide.
                invalidated = blackboard.stale_keys(constraints.fingerprint())
                for key in invalidated:
                    blackboard.drop(key)

            rounds.append(
                RoundRecord(
                    index=round_index,
                    ran=tuple(ran),
                    skipped=tuple(sorted(set(skipped))),
                    new_constraints=tuple(new_constraints),
                    invalidated=invalidated,
                )
            )

            if not new_constraints:
                converged = True
                break

        return RunReport(
            rounds=tuple(rounds),
            converged=converged,
            blackboard=blackboard,
            constraints=constraints,
            failures=tuple(failures),
        )

    def _should_run(
        self,
        agent: Agent,
        blackboard: Blackboard,
        fingerprint: FrozenSet,
        last_run: Dict[str, Tuple[FrozenSet, int]],
    ) -> bool:
        previous = last_run.get(agent.name)
        if previous is None:
            return True
        ran_under, read_version = previous
        if ran_under != fingerprint:
            return True
        if blackboard.max_version_of(agent.reads) > read_version:
            return True
        # Its own output may have been invalidated by a constraint even
        # though its inputs are unchanged.
        return any(not blackboard.has(key) for key in agent.writes)

    def _execute(
        self,
        agents: Sequence[Agent],
        blackboard: Blackboard,
        constraints: ConstraintStore,
        round_index: int,
    ) -> List[AgentResult]:
        """Run one level. Independent by construction, so concurrent.

        Concurrency is the reason this architecture is worth having for the
        real workload: a model with eight unknown constants means eight
        literature searches that have no reason to wait for each other. The
        views are per-agent and read-only, and no agent writes to the
        blackboard until the level has finished, so there is nothing to lock.
        """
        def invoke(agent: Agent) -> AgentResult:
            view = View(
                blackboard,
                agent=agent.name,
                reads=agent.reads,
                constraints=constraints,
                round_index=round_index,
            )
            try:
                return agent.run(view)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                # One scout failing must not lose the other seven results.
                # It is recorded as a failure and surfaces in the report; it
                # is never turned into an empty-but-successful result, which
                # would present an outage as a literature gap.
                return AgentResult(
                    failed=True,
                    failure=f"{type(exc).__name__}: {exc}",
                )

        if len(agents) == 1:
            return [invoke(agents[0])]
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            return list(pool.map(invoke, agents))


__all__ = [
    "Scheduler",
    "RunReport",
    "RoundRecord",
    "AgentRun",
    "CyclicDependency",
    "DuplicateWriter",
    "DEFAULT_MAX_ROUNDS",
]
