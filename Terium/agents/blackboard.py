"""Shared state that records who wrote what, under which constraints.

THE DEPENDENCY GRAPH HAS TO BE TRUE, NOT DOCUMENTED
---------------------------------------------------
The scheduler decides what to re-run from each agent's declared `reads`. If
an agent quietly reads something it did not declare, the graph is wrong, the
invalidation is unsound, and the system silently serves a stale answer -- the
worst possible failure here, because it looks like a fresh one.

So declarations are not documentation. `View` is a capability: it exposes
exactly the declared keys and raises `UndeclaredRead` on anything else. An
agent cannot reach the blackboard except through its view, so the graph is
true by construction. Same for writes, checked by the scheduler.

This is the difference between a pipeline whose comments claim an ordering
and one whose ordering is enforced.

APPEND-ONLY
-----------
Every write is kept. `entries` is the current value of each key; `history` is
every value it ever had, with the agent, the round and the constraint
fingerprint in force at the time. A model that changed after a constraint
arrived can therefore be shown as it was and as it became, which is what
makes the run auditable rather than merely logged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

try:
    from .constraints import Constraint, ConstraintStore
except ImportError:  # pragma: no cover - flat import, matches Tests/ convention
    from constraints import Constraint, ConstraintStore  # type: ignore[no-redef]


class UndeclaredRead(KeyError):
    """An agent read a key it did not declare in `reads`."""


class UndeclaredWrite(KeyError):
    """An agent wrote a key it did not declare in `writes`."""


@dataclass(frozen=True)
class Entry:
    key: str
    value: Any
    written_by: str
    round_index: int
    #: Monotonic across the whole blackboard. Lets an agent ask "has anything
    #: I read changed since I last ran?" without comparing values, which
    #: would need every value to be comparable and cheap to compare.
    version: int
    #: The constraints in force when this was computed. An entry whose
    #: fingerprint is stale was derived without a requirement that has since
    #: been discovered, and must be recomputed.
    constraint_fingerprint: FrozenSet[Tuple[str, str, str]]

    #: False for run inputs -- the query, the network, the user's own
    #: measurements. Inputs are not COMPUTED under the constraints, so a
    #: constraint discovered later says nothing about them and must not
    #: invalidate them. Getting this wrong deletes the model out from under
    #: the run the moment a critic speaks; see
    #: `test_agent_scheduler.py::TestInputsSurviveConstraints`.
    derived: bool = True


class Blackboard:
    def __init__(self) -> None:
        self._entries: Dict[str, Entry] = {}
        self._history: List[Entry] = []
        self._version = 0

    # -- writing ------------------------------------------------------

    def write(
        self,
        key: str,
        value: Any,
        *,
        written_by: str,
        round_index: int,
        constraint_fingerprint: FrozenSet[Tuple[str, str, str]],
        derived: bool = True,
    ) -> Entry:
        self._version += 1
        entry = Entry(
            key=key,
            value=value,
            written_by=written_by,
            round_index=round_index,
            version=self._version,
            constraint_fingerprint=constraint_fingerprint,
            derived=derived,
        )
        self._entries[key] = entry
        self._history.append(entry)
        return entry

    # -- reading ------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        entry = self._entries.get(key)
        return default if entry is None else entry.value

    def has(self, key: str) -> bool:
        return key in self._entries

    def entry(self, key: str) -> Optional[Entry]:
        return self._entries.get(key)

    def max_version_of(self, keys: Iterable[str]) -> int:
        """Highest version among `keys`. 0 when none has been written.

        The scheduler's staleness test. Absent keys contribute 0 rather than
        raising, because "not written yet" is a normal state on round 0.
        """
        versions = [
            self._entries[k].version for k in keys if k in self._entries
        ]
        return max(versions) if versions else 0

    def keys(self) -> Tuple[str, ...]:
        return tuple(self._entries)

    def snapshot(self) -> Dict[str, Any]:
        return {k: e.value for k, e in self._entries.items()}

    @property
    def history(self) -> Tuple[Entry, ...]:
        return tuple(self._history)

    def history_of(self, key: str) -> Tuple[Entry, ...]:
        return tuple(e for e in self._history if e.key == key)

    # -- invalidation -------------------------------------------------

    def stale_keys(
        self, fingerprint: FrozenSet[Tuple[str, str, str]]
    ) -> Tuple[str, ...]:
        """Keys computed under a constraint set that has since grown.

        Compared for equality, not subset. An entry derived under strictly
        fewer constraints was allowed to consider possibilities now ruled
        out, so it has to be recomputed even though the old constraints all
        still hold.
        """
        return tuple(
            key
            for key, entry in self._entries.items()
            if entry.derived and entry.constraint_fingerprint != fingerprint
        )

    def drop(self, key: str) -> None:
        """Remove the current value. History is untouched -- an invalidated
        entry is part of the record of how the run reached its answer."""
        self._entries.pop(key, None)


class View:
    """An agent's capability-scoped window onto the blackboard."""

    def __init__(
        self,
        blackboard: Blackboard,
        *,
        agent: str,
        reads: Iterable[str],
        constraints: ConstraintStore,
        round_index: int,
    ) -> None:
        self._blackboard = blackboard
        self._agent = agent
        self._reads = frozenset(reads)
        self._constraints = constraints
        self.round_index = round_index

    def _check(self, key: str) -> None:
        if key not in self._reads:
            raise UndeclaredRead(
                f"agent {self._agent!r} read {key!r}, which it did not "
                f"declare. Declared reads: {sorted(self._reads) or 'none'}. "
                f"The scheduler decides what to re-run from those "
                f"declarations, so an undeclared read would make it serve a "
                f"stale value as a fresh one."
            )

    def __getitem__(self, key: str) -> Any:
        self._check(key)
        if not self._blackboard.has(key):
            raise KeyError(
                f"agent {self._agent!r} required {key!r}, which nothing has "
                f"written yet"
            )
        return self._blackboard.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        self._check(key)
        return self._blackboard.get(key, default)

    def has(self, key: str) -> bool:
        self._check(key)
        return self._blackboard.has(key)

    # -- constraints are readable by every agent ----------------------
    #
    # Not capability-scoped: a constraint is a requirement on the whole run,
    # and an agent that could not see one would violate it. The scoping that
    # matters is on derived VALUES, where staleness lives.

    def constraints_for(self, subject: str) -> Tuple[Constraint, ...]:
        return self._constraints.for_subject(subject)

    def constraints_of_kind(self, kind: str) -> Tuple[Constraint, ...]:
        return self._constraints.of_kind(kind)

    @property
    def constraints(self) -> ConstraintStore:
        return self._constraints


__all__ = [
    "Blackboard",
    "Entry",
    "View",
    "UndeclaredRead",
    "UndeclaredWrite",
]
