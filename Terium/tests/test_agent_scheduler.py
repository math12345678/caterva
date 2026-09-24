"""The architecture's load-bearing properties, each with a way to fail.

WHAT THESE PIN
--------------
The scheduler decides what to re-run from what agents declare they read.
Four things have to hold or that decision is unsound:

  * an agent cannot read what it did not declare (else the graph is fiction);
  * an agent cannot write what it did not declare (else two agents can race);
  * level-mates actually run at the same time (else the architecture buys
    nothing over the `if` chain it replaces);
  * a constraint discovered late invalidates what was derived early, and the
    affected agents re-run under it.

Plus the two ways iteration can go wrong: not stopping, and stopping while
pretending it finished.
"""

from __future__ import annotations

import threading

import pytest

from Terium.agents.blackboard import Blackboard, UndeclaredRead, UndeclaredWrite, View
from Terium.agents.constraints import ANY_SUBJECT, Constraint, ConstraintStore
from Terium.agents.protocol import AgentResult, FunctionAgent
from Terium.agents.scheduler import (
    CyclicDependency,
    DuplicateWriter,
    Scheduler,
)

HUMAN = "Homo sapiens"
ECOLI = "Escherichia coli"


def agent(name, reads, writes, fn):
    return FunctionAgent(name=name, reads=tuple(reads), writes=tuple(writes), fn=fn)


class TestDeclarationsAreEnforced:
    def test_an_undeclared_read_raises_rather_than_returning_none(self) -> None:
        # The whole invalidation scheme rests on `reads` being complete. A
        # view that returned None for an undeclared key would let an agent
        # depend on something invisibly and be skipped when it changed.
        def peek(view):
            return AgentResult(writes={"out": view.get("secret")})

        sched = Scheduler([agent("peeker", [], ["out"], peek)])
        report = sched.run(seed={"secret": 42})
        failure = report.failures[0]
        assert "UndeclaredRead" in failure.failure
        assert "did not declare" in failure.failure

    def test_an_undeclared_write_is_a_hard_error_not_a_failed_agent(self) -> None:
        # Distinct from a read: a stray write corrupts state other agents
        # will trust, so it stops the run instead of being recorded and
        # carried past.
        def sprawl(view):
            return AgentResult(writes={"declared": 1, "sneaky": 2})

        sched = Scheduler([agent("sprawler", [], ["declared"], sprawl)])
        with pytest.raises(UndeclaredWrite, match="sneaky"):
            sched.run()

    def test_two_agents_writing_one_key_is_rejected_before_running(self) -> None:
        sched_args = [
            agent("a", [], ["shared"], lambda v: AgentResult()),
            agent("b", [], ["shared"], lambda v: AgentResult()),
        ]
        with pytest.raises(DuplicateWriter, match="shared"):
            Scheduler(sched_args)

    def test_a_dependency_cycle_is_rejected_at_construction(self) -> None:
        # Before running, not on the round it would have deadlocked.
        cyclic = [
            agent("a", ["from_b"], ["from_a"], lambda v: AgentResult()),
            agent("b", ["from_a"], ["from_b"], lambda v: AgentResult()),
        ]
        with pytest.raises(CyclicDependency):
            Scheduler(cyclic)


class TestParallelism:
    def test_agents_in_one_level_run_concurrently(self) -> None:
        """The reason this architecture beats the chain it replaces.

        Eight unknown constants are eight literature searches with no reason
        to wait for each other. A barrier is used rather than timing: if the
        two agents are run one after the other, the first blocks forever and
        the barrier times out, so a sequential implementation cannot pass
        this by being fast.
        """
        barrier = threading.Barrier(2, timeout=5)

        def meet(key):
            def fn(view):
                barrier.wait()
                return AgentResult(writes={key: "met"})

            return fn

        sched = Scheduler(
            [
                agent("left", [], ["l"], meet("l")),
                agent("right", [], ["r"], meet("r")),
            ]
        )
        report = sched.run()
        assert report.failures == (), report.failures
        assert report.values() == {"l": "met", "r": "met"}

    def test_a_dependent_agent_waits_for_its_input(self) -> None:
        order: list[str] = []

        def first(view):
            order.append("first")
            return AgentResult(writes={"x": 1})

        def second(view):
            order.append("second")
            return AgentResult(writes={"y": view["x"] + 1})

        sched = Scheduler(
            [
                agent("second", ["x"], ["y"], second),
                agent("first", [], ["x"], first),
            ]
        )
        report = sched.run()
        assert order == ["first", "second"]
        assert report.values()["y"] == 2


class TestConstraintFeedback:
    """The mechanism the whole thing exists for."""

    def test_a_late_constraint_re_runs_the_search_that_preceded_it(self) -> None:
        # Round 0: the scout, unconstrained, returns an E. coli value.
        # The critic sees two organisms and requires human.
        # Round 1: the scout re-runs and honours it.
        #
        # This is the behaviour that does not exist in the pipeline this
        # replaces, where the mismatch is reported and nothing re-searches.
        attempts: list[str] = []

        def scout(view):
            required = [
                c.requirement for c in view.constraints_of_kind("organism")
            ]
            organism = required[0] if required else ECOLI
            attempts.append(organism)
            return AgentResult(writes={"kcat_organism": organism})

        def critic(view):
            found = {view["kcat_organism"], HUMAN}
            if len(found) > 1:
                return AgentResult(
                    constraints=(
                        Constraint(
                            kind="organism",
                            subject=ANY_SUBJECT,
                            requirement=HUMAN,
                            reason="Km is human; the set must be one organism",
                            raised_by="critic",
                        ),
                    )
                )
            return AgentResult(writes={"coherent": True})

        sched = Scheduler(
            [
                agent("scout", [], ["kcat_organism"], scout),
                agent("critic", ["kcat_organism"], ["coherent"], critic),
            ]
        )
        report = sched.run()

        assert attempts == [ECOLI, HUMAN], attempts
        assert report.converged
        assert report.values()["kcat_organism"] == HUMAN
        assert report.values()["coherent"] is True
        assert report.round_count == 2

    def test_a_value_derived_before_the_constraint_is_dropped(self) -> None:
        # Not merely recomputed: it must not survive the round it was
        # invalidated in, or a downstream agent could read the pre-constraint
        # value in the meantime.
        def scout(view):
            return AgentResult(writes={"value": len(view.constraints_of_kind("k"))})

        def critic(view):
            _ = view["value"]
            if not view.constraints_of_kind("k"):
                return AgentResult(
                    constraints=(Constraint("k", ANY_SUBJECT, "yes"),)
                )
            return AgentResult()

        sched = Scheduler(
            [
                agent("scout", [], ["value"], scout),
                agent("critic", ["value"], [], critic),
            ]
        )
        report = sched.run()
        assert report.rounds[0].invalidated == ("value",)
        assert report.values()["value"] == 1

    def test_an_unchanged_agent_is_not_re_run(self) -> None:
        # Re-running everything every round would work and would make the
        # real system re-query BRENDA needlessly on each pass.
        runs: list[str] = []

        def independent(view):
            runs.append("independent")
            return AgentResult(writes={"unrelated": 1})

        def nagger(view):
            n = len(view.constraints_of_kind("n"))
            if n < 1:
                return AgentResult(
                    writes={"n": n},
                    constraints=(Constraint("n", ANY_SUBJECT, "1"),),
                )
            return AgentResult(writes={"n": n})

        sched = Scheduler(
            [
                agent("independent", [], ["unrelated"], independent),
                agent("nagger", [], ["n"], nagger),
            ]
        )
        report = sched.run()
        assert report.round_count == 2
        # `independent` reads nothing and its own output was invalidated by
        # the constraint, so it does re-run -- but it must be *reported* as
        # having re-run, not silently skipped while its stale value stands.
        assert report.values()["unrelated"] == 1
        assert "independent" in {r.agent for r in report.rounds[1].ran}


class TestTermination:
    def test_a_run_that_settles_reports_convergence(self) -> None:
        sched = Scheduler([agent("quiet", [], ["x"], lambda v: AgentResult(writes={"x": 1}))])
        report = sched.run()
        assert report.converged
        assert report.round_count == 1

    def test_an_agent_that_never_settles_is_stopped_and_says_so(self) -> None:
        """The honest half of the termination story.

        Constraints accumulate monotonically, so a round adding none has
        converged -- but that is not a bound on rounds. An agent emitting an
        endlessly narrowing requirement runs forever. The cap stops it, and
        the report must not present the partial result as a finished one.
        """
        def insatiable(view):
            n = len(view.constraints_of_kind("narrow"))
            return AgentResult(
                writes={"n": n},
                constraints=(Constraint("narrow", ANY_SUBJECT, str(n)),),
            )

        sched = Scheduler(
            [agent("insatiable", [], ["n"], insatiable)], max_rounds=4
        )
        report = sched.run()
        assert not report.converged
        assert report.round_count == 4
        assert "DID NOT CONVERGE" in report.summary()
        assert "should not be read as a settled answer" in report.summary()


class TestFailureIsolation:
    def test_one_agent_failing_does_not_lose_its_level_mates(self) -> None:
        # Eight parallel literature searches: the seventh timing out must
        # not discard the six that returned.
        def boom(view):
            raise RuntimeError("BRENDA unreachable")

        sched = Scheduler(
            [
                agent("good", [], ["kept"], lambda v: AgentResult(writes={"kept": "value"})),
                agent("bad", [], ["lost"], boom),
            ]
        )
        report = sched.run()
        assert report.values()["kept"] == "value"
        assert [f.agent for f in report.failures] == ["bad"]
        assert "BRENDA unreachable" in report.failures[0].failure

    def test_a_failure_is_reported_not_recorded_as_an_empty_result(self) -> None:
        # The distinction that matters scientifically: an outage presented
        # as a literature gap would have Terrium tell a researcher that a
        # measurement does not exist because a server was down.
        def boom(view):
            raise TimeoutError("read timed out")

        sched = Scheduler([agent("scout", [], ["km"], boom)])
        report = sched.run()
        assert not report.blackboard.has("km")
        assert "could not complete" in report.summary()
        assert "read timed out" in report.summary()


class TestTrace:
    def test_every_value_records_who_wrote_it_and_when(self) -> None:
        sched = Scheduler([agent("w", [], ["x"], lambda v: AgentResult(writes={"x": 7}))])
        report = sched.run(seed={"query": "hexokinase"})
        assert report.blackboard.entry("x").written_by == "w"
        # Seeded input is attributed too, rather than materialising.
        assert report.blackboard.entry("query").written_by == "<input>"

    def test_the_history_keeps_superseded_values(self) -> None:
        # A model that changed once a constraint arrived can be shown as it
        # was and as it became. That is what makes the run auditable.
        def scout(view):
            return AgentResult(writes={"v": len(view.constraints_of_kind("c"))})

        def critic(view):
            _ = view["v"]
            if not view.constraints_of_kind("c"):
                return AgentResult(constraints=(Constraint("c", ANY_SUBJECT, "x"),))
            return AgentResult()

        sched = Scheduler(
            [agent("scout", [], ["v"], scout), agent("critic", ["v"], [], critic)]
        )
        report = sched.run()
        history = [e.value for e in report.blackboard.history_of("v")]
        assert history == [0, 1]


class TestTheTwoCasesThatMakeInvalidationAndDedupMatter:
    """Both were written after mutation testing found the suite blind to them.

    Neither behaviour is exercised by the ordinary success path, and both
    are the difference between a correct answer and a quietly wrong one.
    """

    def test_a_re_search_that_finds_nothing_leaves_a_gap_not_the_old_value(
        self,
    ) -> None:
        """The scientifically dangerous case.

        Round 0: unconstrained, the scout finds an E. coli kcat.
        A critic then requires human.
        Round 1: there is no human kcat. The scout finds nothing.

        The answer must be "no human kcat exists", with the key ABSENT.
        If the round-0 E. coli value survives, Terrium reports a value from
        the wrong organism as though it satisfied the constraint that
        rejected it -- a fabrication assembled from two correct steps.
        """
        def scout(view):
            if view.constraints_of_kind("organism"):
                return AgentResult(notes=("no human kcat in BRENDA",))
            return AgentResult(writes={"kcat": 118.0})

        def critic(view):
            if view.has("kcat") and not view.constraints_of_kind("organism"):
                return AgentResult(
                    constraints=(
                        Constraint("organism", ANY_SUBJECT, HUMAN,
                                   reason="Km is human", raised_by="critic"),
                    )
                )
            return AgentResult()

        sched = Scheduler(
            [
                agent("scout", [], ["kcat"], scout),
                agent("critic", ["kcat"], [], critic),
            ]
        )
        report = sched.run()

        assert not report.blackboard.has("kcat"), (
            "the pre-constraint E. coli value survived the constraint that "
            "ruled it out"
        )
        assert report.converged
        # And the history still shows it was once there, so the trace can
        # explain why the answer is a gap.
        assert [e.value for e in report.blackboard.history_of("kcat")] == [118.0]

    def test_a_finding_that_never_goes_away_still_converges(self) -> None:
        """Dedup is what makes a permanent finding survivable.

        A source that never published its assay pH will never publish it.
        The critic raises that on every round it runs, forever. If the store
        counted each re-raise as new information, the run would iterate to
        the cap and report DID NOT CONVERGE on a model whose only problem is
        a fact about a paper from 1974.
        """
        raises = []

        def critic(view):
            constraint = Constraint(
                "conditions", "kcat", "pH must be reported",
                reason="never published", raised_by="critic",
            )
            raises.append(constraint)
            return AgentResult(constraints=(constraint,))

        sched = Scheduler([agent("critic", [], [], critic)], max_rounds=5)
        report = sched.run()

        assert report.converged, report.summary()
        assert report.round_count == 2, "one round to raise, one to confirm"
        assert len(raises) == 2
        assert len(report.constraints) == 1


class TestInputsSurviveConstraints:
    def test_a_seeded_input_is_not_invalidated_by_a_later_constraint(self) -> None:
        """Found by a failing integration test, not by inspection.

        Invalidation drops everything computed under a superseded constraint
        set. A seeded input carries the fingerprint that was in force when
        the run started, so it looked stale the instant any critic spoke --
        and the network was deleted out from under the agents that needed
        it, one round in.

        Inputs are not computed under the constraints. Nothing a critic
        discovers can make the user's own model wrong.
        """
        def critic(view):
            if not view.constraints_of_kind("c"):
                return AgentResult(constraints=(Constraint("c", ANY_SUBJECT, "x"),))
            return AgentResult()

        def consumer(view):
            return AgentResult(writes={"seen": view["model"]})

        sched = Scheduler(
            [
                agent("critic", [], [], critic),
                agent("consumer", ["model"], ["seen"], consumer),
            ]
        )
        report = sched.run(seed={"model": "NETWORK"})

        assert report.failures == (), report.failures
        assert report.blackboard.has("model")
        assert report.values()["seen"] == "NETWORK"
        assert "model" not in report.rounds[0].invalidated
