"""Building the agent set for a model, running it, and reporting the run.

THE OUTPUT THIS ARCHITECTURE MAKES POSSIBLE
-------------------------------------------
A per-parameter resolver can say "no human kcat found". Only a run that
searched, was corrected, and searched again can say:

    A kcat was found in Escherichia coli. Your Km is human, so the E. coli
    value was rejected and the search was repeated in Homo sapiens, where
    BRENDA has no kcat for this enzyme and substrate. That measurement does
    not exist in the sources searched.

Those are different answers. The first sends a researcher to look for
something; the second tells them what to measure. The difference is the
constraint history, which is why `ModelBuild` carries it rather than only
the final values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:
    from .blackboard import View
    from .constraints import Constraint
    from .critics import COMPATIBILITY_KEY, STRUCTURE_KEY, CoherenceCritic, StructureCritic
    from .protocol import Agent, AgentResult
    from .scheduler import RunReport, Scheduler
    from .scouts import ParameterScout, frontier_row, param_key
    from .adapters import UnitMismatch, UnresolvedQuantity, with_resolved_values
except ImportError:  # pragma: no cover - flat import
    from blackboard import View  # type: ignore[no-redef]
    from constraints import Constraint  # type: ignore[no-redef]
    from critics import (  # type: ignore[no-redef]
        COMPATIBILITY_KEY, STRUCTURE_KEY, CoherenceCritic, StructureCritic,
    )
    from protocol import Agent, AgentResult  # type: ignore[no-redef]
    from scheduler import RunReport, Scheduler  # type: ignore[no-redef]
    from scouts import ParameterScout, frontier_row, param_key  # type: ignore[no-redef]
    from adapters import (  # type: ignore[no-redef]
        UnitMismatch, UnresolvedQuantity, with_resolved_values,
    )

SIMULATION_KEY = "simulation"
VERDICT_KEY = "verdict"


@dataclass(frozen=True)
class Executor:
    """Compiles and runs the model -- unless it must not be run.

    Refuses on a BLOCKING finding. That is the one severity that says the
    parameters describe no real system, and a trajectory computed from them
    would be a picture of nothing, indistinguishable on screen from a
    correct one. Serious findings do not stop the run: a 12 C gap produces a
    model that is wrong by a stated factor, which is a usable thing to look
    at as long as it is labelled, and it is.
    """

    quantities: Tuple[str, ...]
    #: `(network) -> Any`. Injected: libRoadRunner is a heavy optional
    #: dependency and the architecture is exercised without it.
    simulate: Optional[Callable[[Any], Any]] = None

    name: str = "executor"

    @property
    def reads(self) -> Tuple[str, ...]:
        return ("network", COMPATIBILITY_KEY, STRUCTURE_KEY) + tuple(
            param_key(q) for q in self.quantities
        )

    @property
    def writes(self) -> Tuple[str, ...]:
        return (SIMULATION_KEY,)

    def run(self, view: View) -> AgentResult:
        compatibility = view[COMPATIBILITY_KEY]
        structure = view[STRUCTURE_KEY]

        # An ABSENT key counts as missing, not as nothing to check.
        #
        # A scout that raised -- a timed-out BRENDA request -- never writes
        # its key at all. Skipping it here left its constant at the
        # placeholder the network was constructed with, and the model ran:
        # the partial-substitution fabrication that `with_resolved_values`
        # refuses, arriving instead through an outage. The two cases keep
        # separate wording because they are separate facts, and telling a
        # researcher that a measurement does not exist when a server was
        # down is the specific mistake this codebase spends its time not
        # making.
        unresolved: List[str] = []
        never_reported: List[str] = []
        for quantity in self.quantities:
            key = param_key(quantity)
            if not view.has(key):
                never_reported.append(quantity)
            elif view[key].source is None:
                unresolved.append(quantity)

        if unresolved or never_reported:
            reasons: List[str] = []
            if unresolved:
                reasons.append(
                    f"no measured value for {', '.join(sorted(unresolved))}; "
                    f"Caterva does not substitute a default for a constant "
                    f"the literature did not supply"
                )
            if never_reported:
                reasons.append(
                    f"the search for {', '.join(sorted(never_reported))} did "
                    f"not complete, so whether a value exists is unknown -- "
                    f"this is an outage, not a literature gap, and must not "
                    f"be read as one"
                )
            return AgentResult(
                writes={
                    SIMULATION_KEY: {
                        "ran": False,
                        "refused_because": "; ".join(reasons),
                        "unresolved": tuple(sorted(unresolved)),
                        "never_reported": tuple(sorted(never_reported)),
                    }
                }
            )

        if compatibility.blocking:
            return AgentResult(
                writes={
                    SIMULATION_KEY: {
                        "ran": False,
                        "refused_because": (
                            "the parameters do not describe one system: "
                            + "; ".join(f.detail for f in compatibility.blocking)
                        ),
                    }
                }
            )

        if not structure["well_posed"]:
            return AgentResult(
                writes={
                    SIMULATION_KEY: {
                        "ran": False,
                        "refused_because": (
                            "the network itself is not well posed: "
                            + "; ".join(structure["problems"])
                        ),
                    }
                }
            )

        if self.simulate is None:
            return AgentResult(
                writes={
                    SIMULATION_KEY: {
                        "ran": False,
                        "refused_because": (
                            "no simulator was supplied to this run; the model "
                            "is assembled and would run"
                        ),
                        "assembled": True,
                    }
                }
            )

        # The resolved network, not the placeholder one. The network was
        # constructed with stand-in values so its structure could be checked
        # before any literature was searched; simulating THAT would plot the
        # stand-ins under a report full of citations.
        try:
            resolved_network = with_resolved_values(
                view["network"],
                {
                    q: view[param_key(q)]
                    for q in self.quantities
                    if view.has(param_key(q))
                },
            )
        except (UnresolvedQuantity, UnitMismatch) as exc:
            return AgentResult(
                writes={
                    SIMULATION_KEY: {
                        "ran": False,
                        "refused_because": str(exc),
                    }
                }
            )

        return AgentResult(
            writes={
                SIMULATION_KEY: {
                    "ran": True,
                    "result": self.simulate(resolved_network),
                    "network": resolved_network,
                }
            }
        )


@dataclass(frozen=True)
class ModelBuild:
    """Everything the run concluded, and how it got there."""

    run: RunReport
    quantities: Tuple[str, ...]

    @property
    def resolutions(self) -> Dict[str, Any]:
        return {
            q: self.run.blackboard.get(param_key(q))
            for q in self.quantities
            if self.run.blackboard.has(param_key(q))
        }

    @property
    def compatibility(self) -> Any:
        return self.run.blackboard.get(COMPATIBILITY_KEY)

    @property
    def simulation(self) -> Dict[str, Any]:
        return self.run.blackboard.get(SIMULATION_KEY) or {}

    @property
    def missing(self) -> Tuple[str, ...]:
        return tuple(
            q for q, r in self.resolutions.items() if r is None or r.source is None
        )

    @property
    def usable(self) -> bool:
        compatibility = self.compatibility
        return (
            self.run.converged
            and not self.missing
            and compatibility is not None
            and compatibility.coherent
        )

    def rejected_values(self) -> Tuple[str, ...]:
        """Values a round found and a later constraint ruled out.

        Read from the blackboard history: a key whose earlier entry had a
        source and whose current one does not was answered and then
        un-answered, which is the fact the plain resolver cannot report.
        """
        rejected: List[str] = []
        for quantity in self.quantities:
            history = self.run.blackboard.history_of(param_key(quantity))
            if len(history) < 2:
                continue
            first, last = history[0].value, history[-1].value
            had = getattr(first, "source", None)
            has = getattr(last, "source", None)
            if had is not None and has is None:
                rejected.append(
                    f"{quantity}: found in {had.organism or 'another organism'} "
                    f"on the first pass, then ruled out"
                )
            elif (
                had is not None
                and has is not None
                and had.organism != has.organism
            ):
                rejected.append(
                    f"{quantity}: first resolved in {had.organism}, "
                    f"re-resolved in {has.organism}"
                )
            elif (
                had is not None
                and has is not None
                and had.organism == has.organism
                and had.value != has.value
                and self.run.constraints.of_kind("assay_window")
            ):
                # The same organism, a different value, and an assay window
                # in force: the only mechanism that replaces a value while
                # keeping the organism is condition re-selection (ADR 0171).
                # Reported like the organism move above -- the plain
                # resolver cannot say this at all.
                now, was = _substrates_if_moved(has, had)
                rejected.append(
                    f"{quantity}: re-selected to {has.value} "
                    f"{has.unit or ''}{now} at {_conditions_of(has)} under an "
                    f"assay window, replacing {had.value} {had.unit or ''}{was} "
                    f"at {_conditions_of(had)}"
                )
        return tuple(rejected)

    def summary(self) -> str:
        lines: List[str] = [self.run.summary()]

        found = len(self.quantities) - len(self.missing)
        lines.append(f"Resolved {found} of {len(self.quantities)} constants.")

        discovered = self.run.constraints.all()
        if discovered:
            lines.append(
                "The run discovered and searched under: "
                + "; ".join(str(c) for c in discovered)
                + "."
            )
        for note in self.rejected_values():
            lines.append(note + ".")

        if self.missing:
            lines.append(
                "No measured value for: "
                + "; ".join(
                    f"{q} ({self.resolutions[q].reason})"
                    for q in self.missing
                    if self.resolutions.get(q) is not None
                )
                + "."
            )

        compatibility = self.compatibility
        if compatibility is not None:
            lines.append(compatibility.summary())

        simulation = self.simulation
        if simulation.get("ran"):
            lines.append("Simulated.")
        elif simulation.get("refused_because"):
            reason = simulation["refused_because"]
            # The blocking findings were just printed in full by
            # `compatibility.summary()`. Printing them again under "Not
            # simulated" made the report read as two separate problems.
            if compatibility is not None and compatibility.blocking and (
                "do not describe one system" in reason
            ):
                reason = "the parameters do not describe one system, as above"
            lines.append("Not simulated: " + reason.rstrip(".") + ".")

        return " ".join(lines)


def build_agents(
    *,
    requests: Sequence[Any],
    resolve: Callable[..., Any],
    requested_organism: Optional[str] = None,
    simulate: Optional[Callable[[Any], Any]] = None,
    include_structure: bool = True,
) -> List[Agent]:
    """The agent set for one model build.

    Every scout is independent, so they occupy one level and run at once;
    the structure critic joins them because it needs only the network. The
    coherence critic sits below every scout, and the executor below both
    critics. That shape is derived from the declarations, not written down
    here -- `Scheduler` computes it, and rejects the set if it is cyclic.
    """
    quantities = tuple(r.quantity for r in requests)
    agents: List[Agent] = [
        ParameterScout(request=request, resolve=resolve) for request in requests
    ]
    if include_structure:
        agents.append(StructureCritic())
    agents.append(
        CoherenceCritic(quantities=quantities, requested_organism=requested_organism)
    )
    agents.append(Executor(quantities=quantities, simulate=simulate))
    return agents


def build_model(
    *,
    network: Any,
    requests: Sequence[Any],
    resolve: Callable[..., Any],
    requested_organism: Optional[str] = None,
    simulate: Optional[Callable[[Any], Any]] = None,
    max_rounds: int = 6,
    initial_constraints: Sequence[Constraint] = (),
) -> ModelBuild:
    """One fixpoint run: resolve, criticise, re-resolve, until settled."""
    agents = build_agents(
        requests=requests,
        resolve=resolve,
        requested_organism=requested_organism,
        simulate=simulate,
        include_structure=network is not None,
    )
    scheduler = Scheduler(agents, max_rounds=max_rounds)
    report = scheduler.run(
        seed={"network": network} if network is not None else None,
        initial_constraints=initial_constraints,
    )
    return ModelBuild(run=report, quantities=tuple(r.quantity for r in requests))


# ---------------------------------------------------------------------------
# Branching over candidate organisms
# ---------------------------------------------------------------------------
#
# WHY THE FIXPOINT ALONE IS NOT ENOUGH
# ------------------------------------
# Two constants resolved from two organisms is the commonest real mismatch,
# and it is always a tie: one value each. The coherence critic correctly
# declines to break it, because preferring whichever organism sorted first
# would be an invisible scientific decision.
#
# The answer is not a cleverer tiebreak. It is to stop choosing: run the
# search once inside EACH organism that the literature actually offered, and
# report what each one yields. That turns an arbitrary pick into an
# exhaustive statement --
#
#     Two single-organism models are possible here. In rabbit both constants
#     exist. In human the Km exists and no Ki has been measured.
#
# -- which is a fact about the literature rather than a preference of ours.
# The candidate set is bounded by the organisms observed in the first pass,
# so this is a handful of runs, not a sweep.


@dataclass(frozen=True)
class Branch:
    #: None for the unconstrained first pass.
    organism: Optional[str]
    build: ModelBuild

    @property
    def complete(self) -> bool:
        compatibility = self.build.compatibility
        return (
            not self.build.missing
            and compatibility is not None
            and compatibility.coherent
        )


@dataclass(frozen=True)
class ModelSearch:
    branches: Tuple[Branch, ...]
    chosen: Optional[Branch]
    #: Organisms that each yield a complete model, when more than one does
    #: and nothing principled separates them.
    undecided: Tuple[str, ...]

    @property
    def first_pass(self) -> ModelBuild:
        """The unconstrained run that discovered what was available."""
        return self.branches[0].build

    @property
    def build(self) -> Optional[ModelBuild]:
        """The model, or None when the search settled on no single one.

        Deliberately None rather than the first pass. That pass drew its
        values from several organisms, so returning it would hand a caller
        an assembled model made of constants that describe no animal -- the
        exact object this whole architecture exists to refuse. A caller with
        no model must be made to say so.
        """
        return self.chosen.build if self.chosen else None

    def _branch_lines(self) -> List[str]:
        lines: List[str] = []
        explored = [b for b in self.branches if b.organism is not None]
        if not explored:
            return lines
        lines.append(
            f"Values came from {len(explored)} different organisms, so "
            f"Caterva built the model separately inside each rather than "
            f"choosing one:"
        )
        for branch in explored:
            if branch.complete:
                state = "complete"
            elif branch.build.missing:
                state = "no measured " + ", ".join(branch.build.missing)
            else:
                state = "found, but the values do not hold together"
            lines.append(f"[{branch.organism}: {state}]")
        return lines

    def summary(self) -> str:
        if len(self.branches) == 1:
            return self.first_pass.summary()

        lines = self._branch_lines()

        if self.undecided:
            lines.append(
                "More than one organism yields a complete model ("
                + ", ".join(self.undecided)
                + ") and nothing in the request separates them, so Caterva "
                "has not chosen: name the organism you want and it will "
                "build that one."
            )
            return " ".join(lines)

        if self.chosen is not None:
            lines.append(f"Built in {self.chosen.organism}.")
            lines.append(self.chosen.build.summary())
            return " ".join(lines)

        # Nothing completed. Report THAT, not the mixed-organism first pass:
        # its "resolved 2 of 2" would read as success over a model made of
        # constants from two animals.
        gaps = sorted(
            {
                quantity
                for branch in self.branches
                if branch.organism
                for quantity in branch.build.missing
            }
        )
        lines.append(
            "No single organism has every constant this model needs, so "
            "Caterva has not assembled one."
        )
        if gaps:
            lines.append(
                "The measurements that would complete it, in whichever "
                "organism you choose: " + ", ".join(gaps) + "."
            )
        return " ".join(lines)


def _substrates_if_moved(has: Any, had: Any) -> Tuple[str, str]:
    """(" for NAD+", " for pyruvate"): the substrate of each source's row,
    for the re-selection line, when their frontier rows state different
    ones; ("", "") otherwise.

    A re-selection moves between rows of one frontier, and those differ in
    substrate only when the request named none (`fallback_logic.
    _score_frontier`). Neither `ParameterSource` has a substrate, so each
    row is found in the frontier by its value and commentary
    (`scouts.frontier_row`), which works for the re-selected row because it
    carries its own commentary."""
    now = (frontier_row(has) or {}).get("substrate")
    was = (frontier_row(had) or {}).get("substrate")
    if now and was and now != was:
        return f" for {now}", f" for {was}"
    return "", ""


def _conditions_of(source: Any) -> str:
    parts = []
    if getattr(source, "ph", None) is not None:
        parts.append(f"pH {source.ph:g}")
    if getattr(source, "temperature_c", None) is not None:
        parts.append(f"{source.temperature_c:g} C")
    if getattr(source, "buffer", None):
        parts.append(f"in {getattr(source, 'buffer')}")
    return ", ".join(parts) or "conditions unstated"


def _observed_organisms(build: ModelBuild) -> Tuple[str, ...]:
    seen: List[str] = []
    for resolution in build.resolutions.values():
        source = getattr(resolution, "source", None)
        organism = getattr(source, "organism", None)
        if organism and organism not in seen:
            seen.append(organism)
    return tuple(seen)


def search_model(
    *,
    network: Any,
    requests: Sequence[Any],
    resolve: Callable[..., Any],
    requested_organism: Optional[str] = None,
    simulate: Optional[Callable[[Any], Any]] = None,
    max_rounds: int = 6,
) -> ModelSearch:
    """Build the model, exploring every organism the literature offered.

    One unconstrained pass discovers what is available. If it already
    settled on a single organism, that is the answer and no further search
    runs. Otherwise each observed organism gets its own run.
    """
    # A named organism is a requirement from the outset, not something for
    # a critic to rediscover. Seeding it means the first pass searches
    # inside it directly -- otherwise the scouts search unconstrained, the
    # critic notices the mismatch, and a second round repeats every
    # literature query for an answer the user had already given.
    seeded: Tuple[Constraint, ...] = ()
    if requested_organism:
        seeded = (
            Constraint(
                kind="organism",
                subject="*",
                requirement=requested_organism,
                reason="the organism named in the request",
                raised_by="<input>",
            ),
        )

    first = build_model(
        network=network, requests=requests, resolve=resolve,
        requested_organism=requested_organism, simulate=simulate,
        max_rounds=max_rounds, initial_constraints=seeded,
    )
    branches: List[Branch] = [Branch(organism=None, build=first)]

    candidates = _observed_organisms(first)
    if len(candidates) <= 1:
        return ModelSearch(
            branches=tuple(branches),
            chosen=branches[0],
            undecided=(),
        )

    for organism in candidates:
        branches.append(
            Branch(
                organism=organism,
                build=build_model(
                    network=network, requests=requests, resolve=resolve,
                    requested_organism=organism, simulate=simulate,
                    max_rounds=max_rounds,
                    initial_constraints=(
                        Constraint(
                            kind="organism",
                            subject="*",
                            requirement=organism,
                            reason=(
                                "exploring the model that would follow from "
                                "using this organism throughout"
                            ),
                            raised_by="search_model",
                        ),
                    ),
                ),
            )
        )

    complete = [b for b in branches if b.organism is not None and b.complete]

    if requested_organism:
        preferred = [b for b in complete if b.organism == requested_organism]
        if preferred:
            return ModelSearch(tuple(branches), preferred[0], ())
    if len(complete) == 1:
        return ModelSearch(tuple(branches), complete[0], ())
    if len(complete) > 1:
        # Several organisms each give a whole, coherent model. That is a
        # genuine finding, not a failure -- and picking one would discard it.
        return ModelSearch(
            tuple(branches), None, tuple(b.organism or "" for b in complete)
        )
    return ModelSearch(tuple(branches), None, ())


__all__ = [
    "Executor",
    "ModelBuild",
    "ModelSearch",
    "Branch",
    "build_agents",
    "build_model",
    "search_model",
    "SIMULATION_KEY",
    "VERDICT_KEY",
]
