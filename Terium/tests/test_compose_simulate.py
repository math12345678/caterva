"""Running a composed model, and the checks the engine cannot make.

The engine integrates whatever it is given. These tests pin what this layer
adds: a window derived from the system's own timescale rather than guessed,
an independent check that the conservation laws survived, and refusals for
the two cases where a trajectory would mislead -- a rate law that does not
balance, and a species silently missing from the output.
"""

from __future__ import annotations

import pytest

from Terium.compose.analysis import analyse
from Terium.compose.pipeline import compose
from Terium.compose.simulate import (
    CONSERVATION_DRIFT_TOLERANCE, FALLBACK_END, SETTLING_MULTIPLES,
    InvariantCheck, SimulationRefused, check_invariants, choose_window, run,
)

pytest.importorskip("roadrunner", reason="the time course needs the engine")


class TestTheWindow:
    def test_it_is_derived_from_the_settling_time(self) -> None:
        """`end=10` is a guess about a system nobody has looked at.

        The slowest eigenvalue at the steady state gives the settling time;
        a few multiples of it show the whole approach.
        """
        model = compose("three step phosphorylation cascade")
        end, basis = choose_window(model.network)

        report = analyse(model.network)
        slowest = max(
            p.slowest_timescale for p in report.physical_points
            if p.stable and p.slowest_timescale is not None
        )
        assert end == pytest.approx(SETTLING_MULTIPLES * slowest)
        assert "slowest settling time" in basis
        assert "Jacobian" in basis

    def test_a_caller_window_wins_and_says_so(self) -> None:
        model = compose("three step phosphorylation cascade")
        end, basis = choose_window(model.network, requested=3.5)
        assert end == 3.5
        assert "given by the caller" in basis

    def test_the_fallback_admits_it_is_a_guess(self) -> None:
        # A model with no stable steady state has no timescale to derive
        # from. The default is used and the report must not present it as
        # anything more than a default.
        from Terium.compose.builder import Composition
        from Terium.compose.library import CONSTANT_INFLOW

        composition = Composition("unbounded")
        composition.add(CONSTANT_INFLOW, "feed")
        end, basis = choose_window(composition.to_network())
        assert end == FALLBACK_END
        assert "guess" in basis


class TestInvariants:
    def test_the_conservation_laws_survive_a_real_integration(self) -> None:
        """The cheapest error detector available, and it is free.

        The integrator does not know these laws exist -- they are the left
        null space of the stoichiometry over rationals. If total protein
        drifts, the trajectory is wrong and the plot looks normal.
        """
        trajectory = run(compose("three step phosphorylation cascade"), points=101)
        assert trajectory.invariants, "this model has conservation laws to check"
        assert trajectory.sound
        for check in trajectory.invariants:
            assert check.held, check.describe()

    def test_the_shared_pool_of_a_competition_is_conserved(self) -> None:
        # `enzyme1_S + enzyme1_P + enzyme2_P` is the proof that the two
        # enzymes really do draw on one pool rather than having private
        # substrates that happen to be named alike.
        trajectory = run(compose("two enzymes competing for the same substrate"))
        laws = [check.law for check in trajectory.invariants]
        assert any("enzyme1_S" in law and "enzyme2_P" in law for law in laws), laws
        assert trajectory.sound

    def test_a_drifting_invariant_is_reported_as_the_integrator_s_fault(self) -> None:
        # Constructed, because a real drift needs a badly-tuned integrator.
        # The wording matters: the law is exact, so a drift is never the
        # model's.
        drifted = InvariantCheck(
            law="A + B", initial=1.0, final=1.05, worst_drift=0.05,
        )
        assert not drifted.held
        assert "DRIFTED" in drifted.describe()
        assert "the integrator's, not the model's" in drifted.describe()

    def test_the_tolerance_bites_in_both_directions(self) -> None:
        below = InvariantCheck("A", 1.0, 1.0, CONSERVATION_DRIFT_TOLERANCE * 0.5)
        at = InvariantCheck("A", 1.0, 1.0, CONSERVATION_DRIFT_TOLERANCE * 2)
        assert below.held
        assert not at.held


class TestConstantSpecies:
    def test_a_modifier_is_filled_exactly_not_dropped(self) -> None:
        """Antimony emits no column for a species nothing changes.

        An enzyme that appears only as a modifier is constant BY
        CONSTRUCTION, so its trajectory is a flat line at its initial value
        -- derived from the model's structure, not measured by the
        integrator. Dropping it would show a reader a partial system.
        """
        model = compose("three step phosphorylation cascade")
        trajectory = run(model, points=51)

        for species in model.network.species:
            assert species.id in trajectory.columns, species.id

        kinase = trajectory.columns["tier1_kinase"]
        assert len(set(kinase)) == 1
        assert kinase[0] == pytest.approx(1e-3)


class TestExtraction:
    """The contract with the engine's result, tested directly.

    Every model here produces complete columns, so the refusal path for a
    CHANGING species with no column is never reached through `run` -- a
    mutation that filled such a species with zeros instead of refusing
    survived the whole suite. It is exercised on `_extract` itself.
    """

    def _result(self, colnames, rows):
        return type("R", (), {"colnames": colnames, "data": rows, "time": [r[0] for r in rows]})()

    def test_a_changing_species_with_no_column_is_refused(self) -> None:
        from Terium.compose.simulate import _extract

        model = compose("two enzymes competing for the same substrate")
        network = model.network
        # `enzyme1_S` is consumed by both reactions, so it changes. Omit it.
        present = [s.id for s in network.species if s.id != "enzyme1_S"]
        colnames = ["time"] + [f"[{name}]" for name in present]
        rows = [[0.0] + [1.0] * len(present), [1.0] + [1.0] * len(present)]

        with pytest.raises(SimulationRefused) as caught:
            _extract(self._result(colnames, rows), network)
        message = str(caught.value)
        assert "enzyme1_S" in message
        assert "not constant" in message
        assert "silently absent" in message

    def test_a_constant_species_with_no_column_is_filled_not_refused(self) -> None:
        from Terium.compose.simulate import _extract

        model = compose("two enzymes competing for the same substrate")
        network = model.network
        # `enzyme1_E` appears only as a modifier, so it is constant.
        present = [s.id for s in network.species if s.id != "enzyme1_E"]
        colnames = ["time"] + [f"[{name}]" for name in present]
        rows = [[0.0] + [1.0] * len(present), [1.0] + [1.0] * len(present)]

        _, columns = _extract(self._result(colnames, rows), network)
        assert "enzyme1_E" in columns
        initial = next(s.initial for s in network.species if s.id == "enzyme1_E")
        assert len(set(columns["enzyme1_E"])) == 1
        assert columns["enzyme1_E"][0] == pytest.approx(initial)

    def test_a_result_with_no_time_column_is_refused(self) -> None:
        # Inventing an x-axis would be worse than failing.
        from Terium.compose.simulate import _extract

        network = compose("two enzymes competing for the same substrate").network
        bare = type("R", (), {"colnames": ["a"], "data": [[1.0]]})()
        with pytest.raises(SimulationRefused, match="no time column"):
            _extract(bare, network)


class TestRefusals:
    def test_it_will_not_integrate_a_dimensionally_broken_model(self) -> None:
        """A curve that is wrong by an unknown factor and looks normal.

        There is no later point in the pipeline at which this becomes
        visible, so the refusal has to happen before the integration.
        """
        from dataclasses import replace

        from Terium.core.network import Parameter

        model = compose("three step phosphorylation cascade")
        # Break a rate constant's declared unit by rebuilding the motif's
        # parameter as a concentration. The composition's unit check is what
        # `run` consults, so this is patched there.
        composition = model.recognition.composition
        broken = [
            type("F", (), {"severity": "blocking", "detail": "planted", "where": "x"})()
        ]
        composition.unit_findings = lambda: broken  # type: ignore[assignment]

        with pytest.raises(SimulationRefused, match="do not balance dimensionally"):
            run(model)

    def test_the_refusal_names_what_it_would_have_produced(self) -> None:
        model = compose("three step phosphorylation cascade")
        composition = model.recognition.composition
        composition.unit_findings = lambda: [  # type: ignore[assignment]
            type("F", (), {"severity": "blocking", "detail": "planted", "where": "x"})()
        ]
        with pytest.raises(SimulationRefused) as caught:
            run(model)
        assert "wrong by an unknown factor" in str(caught.value)
        assert "looks normal" in str(caught.value)


class TestAgreementWithTheAnalysis:
    def test_the_toggle_settles_into_a_state_the_analysis_predicted(self) -> None:
        """A real cross-check between two independent computations.

        The steady states come from a root find on the derivative function;
        the trajectory comes from an integrator working on compiled SBML.
        They share no code path below the network, so agreement is evidence
        and disagreement would be a bug in one of them.
        """
        model = compose("a toggle switch between two repressors")
        report = analyse(model.network)

        # Deliberately longer than the default window.
        #
        # `SETTLING_MULTIPLES` is 4, which shows the whole approach -- and
        # leaves about 2% of it un-run. On the SMALL coordinate that 2% is
        # 37% in relative terms (0.0345 against a limit of 0.0251), so a
        # test asserting agreement at the default window is asking whether
        # the curve has converged from a window chosen to show it
        # converging. Measured: 3x reaches four significant figures, 12x
        # reaches eleven.
        window, _ = choose_window(model.network)
        trajectory = run(model, end=window * 6, points=201)
        final = trajectory.final_state()

        stable = report.stable_points
        assert stable, "no stable state to settle into"
        matched = [
            point for point in stable
            if all(
                final[name] == pytest.approx(value, rel=0.05, abs=1e-3)
                for name, value in point.state.items()
            )
        ]
        assert matched, (
            f"integration ended at {final}, which matches none of the "
            f"predicted stable states "
            f"{[dict(p.state) for p in stable]}"
        )

    def test_the_unmeasured_constants_are_named_on_the_trajectory(self) -> None:
        # A curve whose shape is a property of the mechanism and whose
        # scale is a property of numbers nobody measured. Said on the
        # trajectory itself, not only in the model report.
        trajectory = run(compose("a toggle switch between two repressors"))
        assert trajectory.unmeasured
        assert "not measurements" in trajectory.summary()
