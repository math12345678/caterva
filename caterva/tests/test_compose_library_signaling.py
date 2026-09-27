"""What the signalling motifs are FOR, checked by making them do it.

A motif library is easy to test badly. Asserting that a motif has five
ports and eight parameters pins the typing and nothing else: every one of
these would pass with the repression arm wired as an activation, which is
the single most consequential thing that can be wrong with a feed-forward
loop and the thing a reader is relying on.

So the tests that matter here are behavioural, and each one is anchored to
an answer known in closed form:

  * the incoherent loop ADAPTS -- a step in the input produces a pulse, and
    the level it returns to is the closed-form steady state with the input
    cancelled out of it;
  * the coherent loop DELAYS -- the same step produces a monotone rise that
    arrives late, and the lateness disappears when the slow arm is
    pre-loaded, which is the delay measured rather than asserted;
  * the ultrasensitive cycle is SHARPER THAN HYPERBOLIC, against the exact
    benchmark: a hyperbolic response needs an 81-fold change in the input
    to go from 10% to 90%, and 81 is arithmetic, not a fit.

THE REGIME IS SET BY THE TEST, NOT INHERITED FROM THE DEFAULTS
--------------------------------------------------------------
Motif defaults are illustrative placeholders. A test that asserted a
behaviour at whatever the placeholders happen to be would be pinning the
placeholders, and would go red the next time somebody made one more
plausible. Each basis in `library_signaling.py` NAMES the regime its
behaviour needs -- both converter enzymes saturated, the activation arm
unsaturated and the repression arm saturated -- and these tests put the
model in that regime explicitly and check what the basis said would happen.
Where a default is already in the regime, the test still states the
arithmetic it depends on, so the dependency is visible.

WHY THE MODELS ARE BUILT BY HAND
--------------------------------
`compose()` reaches only shapes `grammar.py` has a phrase for, and these
motifs deliberately have none yet -- registering a motif the front door
cannot reach would be a promise it does not keep, and adding the phrases is
a separate change. `_runnable` wraps a hand-built composition in the same
`ComposedModel` the pipeline produces, so `simulate.run` applies the same
refusals: it still consults the composition's unit findings before
integrating, and still checks the conservation laws afterwards.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Dict, Sequence, Tuple

import pytest

from caterva.compose.builder import Composition
from caterva.compose.grammar import Recognition
from caterva.compose.library import LIBRARY, PHOSPHORYLATION_CYCLE
from caterva.compose.library_signaling import (
    ALIASES, COHERENT_FEEDFORWARD, INCOHERENT_FEEDFORWARD, SCAFFOLD_ASSEMBLY,
    SIGNALING_LIBRARY, SINGLE_COPY_GENE_MM, TWO_COMPONENT_SYSTEM,
    ULTRASENSITIVE_CYCLE, signaling_motif,
)
from caterva.compose.motifs import (
    KIND_CONCENTRATION, KIND_EXPONENT, MotifError, RESOLVABLE_KINDS,
)
from caterva.compose.pipeline import ComposedModel
from caterva.compose.simulate import run
from caterva.compose.units import parse_unit, rate_unit_for

engine = pytest.importorskip(
    "roadrunner", reason="the behavioural tests need the time course"
)


# ---------------------------------------------------------------------------
# Building a runnable model out of a hand-wired composition
# ---------------------------------------------------------------------------


def _runnable(composition: Composition, network=None) -> ComposedModel:
    """The pipeline's model around a composition the grammar cannot reach.

    `simulate.run` takes a `ComposedModel` rather than a network because it
    consults the composition's unit findings before integrating -- the
    refusal that stops a dimensionally broken law producing a smooth curve
    that is wrong by an unknown factor. Going round it by calling the
    engine directly would run these motifs with that check switched off,
    which is the one check a motif library most needs.
    """
    return ComposedModel(
        query="built by test_compose_library_signaling",
        recognition=Recognition(
            composition=composition,
            rule="hand_wired",
            reading="wired in the test, not recognised from a phrase",
        ),
        network=composition.to_network() if network is None else network,
        resolvable=composition.quantities_to_resolve(),
        chosen=composition.chosen_quantities(),
        subject=None,
    )


def _tuned(composition: Composition, **values: float):
    """The composition's network with named parameter values replaced.

    Refuses on an unknown parameter id rather than ignoring it. A typo in a
    parameter name would otherwise leave the model at its default and the
    test would report a behaviour of the placeholders while claiming to
    have set the regime -- passing for the wrong reason, which is the only
    kind of green worth being afraid of.
    """
    network = composition.to_network()
    known = {parameter.id for parameter in network.parameters}
    unknown = sorted(set(values) - known)
    if unknown:
        raise AssertionError(
            f"no parameter(s) {unknown} in this composition; it has "
            f"{sorted(known)}"
        )
    return replace(
        network,
        parameters=tuple(
            replace(p, value=float(values[p.id])) if p.id in values else p
            for p in network.parameters
        ),
    )


def _defaults_of(motif) -> Dict[str, float]:
    """A motif's own parameter defaults, by bare name.

    Read off the motif rather than written into the test, so a later change
    to a placeholder moves the prediction with it instead of turning a
    correct model into a failing test. A test that hard-coded 0.05 for
    k_auto would fail the day somebody found a better placeholder, and
    would fail for a reason that has nothing to do with the mechanism.
    """
    return {parameter.name: parameter.default for parameter in motif.parameters}


def _first_time_at_or_above(
    times: Sequence[float], values: Sequence[float], target: float
) -> float:
    """When a rising trace first reaches `target`.

    Raises rather than returning a sentinel when it never does: a `None`
    silently compared against a number is how a test that measured nothing
    reports a pass.
    """
    for time, value in zip(times, values):
        if value >= target:
            return time
    raise AssertionError(
        f"the trace never reached {target:.6g}; it ended at "
        f"{values[-1]:.6g} after {times[-1]:.6g}"
    )


# ---------------------------------------------------------------------------
# The incoherent loop: adaptation
# ---------------------------------------------------------------------------
#
# The regime the basis names, spelled out here so the arithmetic below is
# checkable by eye rather than only by running it:
#
#   X_LOW, X_HIGH << Kxy = Kxz = 1 mM   both activation arms unsaturated
#   Y_ss >> Kyz = 1e-6 mM               the repression arm saturated
#   n = 1                               the exponent at which it is EXACT
#   d_z = 0.05 >> d_y = 1e-3            the output faster than the repressor
#
# All four hold at the motif's defaults, which is deliberate -- a motif
# whose defaults sit outside the regime its own basis names would be a
# motif that never demonstrates itself.

IFFL_LOW = 0.1
IFFL_HIGH = 0.5

#: Four times the repressor's own time constant (1/d_y = 1000 s), which is
#: what `simulate.SETTLING_MULTIPLES` would choose if the steady-state
#: search could be run on this model. Six is used instead of four because
#: the adapted level is the thing being measured and the last 2% of the
#: approach is exactly where it lives.
IFFL_END = 6_000.0


def _iffl_constants(network) -> Dict[str, float]:
    return {p.id.removeprefix("loop_"): p.value for p in network.parameters}


def _iffl_y_steady(k: Dict[str, float], gene: float, x: float) -> float:
    """Y's closed-form steady state: (k_y*Gy/d_y) * X/(Kxy + X)."""
    return (k["k_y"] * gene / k["d_y"]) * x / (k["Kxy"] + x)


def _iffl_z_steady(k: Dict[str, float], gene: float, x: float) -> float:
    """Z's closed form, with the repression evaluated at Y's own steady state.

    In the regime the basis names this is independent of x -- which is the
    claim, and is checked against a second value of x below rather than
    being taken on trust.
    """
    y = _iffl_y_steady(k, gene, x)
    repression = k["Kyz"] ** k["n"] / (k["Kyz"] ** k["n"] + y ** k["n"])
    return (k["k_z"] * gene / k["d_z"]) * x / (k["Kxz"] + x) * repression


@pytest.fixture(scope="module")
def iffl_step():
    """A step input, applied by starting the loop at rest for the OLD input.

    X is a constant of this motif -- nothing consumes or produces it -- so
    a step is exactly this: Y and Z at the levels they held while X was
    IFFL_LOW, and X already at IFFL_HIGH when the clock starts.
    """
    composition = Composition("incoherent_feedforward")
    composition.add(INCOHERENT_FEEDFORWARD, "loop")
    network = composition.to_network()
    constants = _iffl_constants(network)
    gene = next(s.initial for s in network.species if s.id == "loop_Gy")

    composition.set_initial("loop_X", IFFL_HIGH)
    composition.set_initial("loop_Y", _iffl_y_steady(constants, gene, IFFL_LOW))
    composition.set_initial("loop_Z", _iffl_z_steady(constants, gene, IFFL_LOW))

    trajectory = run(_runnable(composition), end=IFFL_END, points=601)
    return constants, gene, trajectory


class TestTheIncoherentLoopAdapts:
    """The reason the motif exists, tested by making it do it.

    Every structural assertion about this motif -- five ports, a repression
    arm, a Hill exponent -- would still pass if the repression were wired
    as an activation. Only the trajectory notices.
    """

    def test_the_output_pulses_and_comes_back(self, iffl_step) -> None:
        constants, gene, trajectory = iffl_step
        z = trajectory.columns["loop_Z"]
        baseline, peak, adapted = z[0], max(z), z[-1]

        assert peak > 2.5 * baseline, (
            f"a step of {IFFL_HIGH / IFFL_LOW:g}x produced no pulse: peak "
            f"{peak:.6g} against a baseline of {baseline:.6g}"
        )
        assert adapted < peak / 2.0, "the output did not come back down"
        # And it came back essentially all the way, which is the difference
        # between adaptation and a smaller-than-expected rise.
        recovered = (peak - adapted) / (peak - baseline)
        assert recovered > 0.95, f"only {recovered:.1%} of the pulse decayed"

    def test_the_adapted_level_is_the_baseline_it_started_from(
        self, iffl_step
    ) -> None:
        """Perfect adaptation, stated as the thing that can be measured.

        The system was at rest for one input and ends at rest for an input
        five times larger, and the two resting levels agree to under 2%.
        The residual is not solver noise -- it is the exact amount by which
        the regime is not exactly satisfied, since X/(Kxz + X) is not quite
        proportional to X at X = 0.5 against a Kxz of 1.
        """
        _, _, trajectory = iffl_step
        z = trajectory.columns["loop_Z"]
        assert z[-1] == pytest.approx(z[0], rel=0.02)

    def test_it_lands_where_the_closed_form_says(self, iffl_step) -> None:
        """An independent computation, not a re-reading of the same one.

        The trajectory comes from an integrator working on compiled SBML;
        the closed form is algebra done in this file. They share no code
        below the network, so agreement is evidence and disagreement would
        be a bug in one of them.
        """
        constants, gene, trajectory = iffl_step
        predicted = _iffl_z_steady(constants, gene, IFFL_HIGH)
        assert trajectory.columns["loop_Z"][-1] == pytest.approx(
            predicted, rel=0.01
        )

    def test_the_two_closed_form_levels_barely_differ(self, iffl_step) -> None:
        """The structural claim, checked without integrating anything.

        If adaptation were a property of the numbers rather than of the
        wiring, the two closed-form levels would differ by the five-fold
        step. They differ by under 1%.
        """
        constants, gene, _ = iffl_step
        low = _iffl_z_steady(constants, gene, IFFL_LOW)
        high = _iffl_z_steady(constants, gene, IFFL_HIGH)
        assert high / low == pytest.approx(1.0, abs=0.02)
        # And the loop is not simply insensitive to its input: the
        # repressor arm moved by the full step, so the cancellation is real
        # rather than there being nothing to cancel.
        assert _iffl_y_steady(constants, gene, IFFL_HIGH) > 3.0 * (
            _iffl_y_steady(constants, gene, IFFL_LOW)
        )

    def test_the_peak_stays_under_the_bound_the_mechanism_imposes(
        self, iffl_step
    ) -> None:
        """An exact upper bound, from the shape of the equations alone.

        Y only rises after the step, so Z's production term only falls, so
        Z can never exceed the level it would reach if Y stayed where it
        started. That bound is arithmetic and holds for every parameter
        set; a trajectory above it would mean the integrator, not the
        model.
        """
        constants, gene, trajectory = iffl_step
        y_before = _iffl_y_steady(constants, gene, IFFL_LOW)
        repression = constants["Kyz"] ** constants["n"] / (
            constants["Kyz"] ** constants["n"] + y_before ** constants["n"]
        )
        bound = (
            (constants["k_z"] * gene / constants["d_z"])
            * IFFL_HIGH / (constants["Kxz"] + IFFL_HIGH)
            * repression
        )
        assert max(trajectory.columns["loop_Z"]) <= bound * (1.0 + 1e-9)

    def test_the_conservation_laws_survived_the_run(self, iffl_step) -> None:
        # The input and the two genes are constants of this model, so they
        # are its conservation laws. The integrator does not know they
        # exist, which is what makes this an independent check.
        _, _, trajectory = iffl_step
        assert trajectory.invariants, "this model has constants to check"
        assert trajectory.sound, [
            check.describe() for check in trajectory.invariants
            if not check.held
        ]


# ---------------------------------------------------------------------------
# The coherent loop: delay
# ---------------------------------------------------------------------------

CFFL_INPUT = 0.1

#: Twelve times the slow arm's time constant (1/d_y = 1000 s). The delay
#: being measured is roughly one of those, so the window has to cover the
#: delay AND the rise that follows it.
CFFL_END = 12_000.0


def _cffl_runs():
    """The same loop from a cold start and with the slow arm pre-loaded.

    The pre-loaded run is the control, and it is the whole design of this
    test: it has identical constants, identical wiring and identical input,
    and differs only in whether Y has already arrived. Any difference in
    the response time is therefore the delay the second arm imposes, and
    nothing else.
    """
    constants: Dict[str, float] = {}
    traces = {}
    for label, preload in (("cold", False), ("warm", True)):
        composition = Composition("coherent_feedforward")
        composition.add(COHERENT_FEEDFORWARD, "loop")
        network = composition.to_network()
        constants = {
            p.id.removeprefix("loop_"): p.value for p in network.parameters
        }
        gene = next(s.initial for s in network.species if s.id == "loop_Gy")
        gate = CFFL_INPUT ** constants["n"] / (
            constants["Kxy"] ** constants["n"] + CFFL_INPUT ** constants["n"]
        )
        y_steady = (constants["k_y"] * gene / constants["d_y"]) * gate

        composition.set_initial("loop_X", CFFL_INPUT)
        composition.set_initial("loop_Y", y_steady if preload else 0.0)
        traces[label] = run(
            _runnable(composition), end=CFFL_END, points=1201
        )
        constants["_gene"] = gene
        constants["_y_steady"] = y_steady
    return constants, traces


@pytest.fixture(scope="module")
def cffl():
    return _cffl_runs()


class TestTheCoherentLoopDelays:
    """Sign-consistent wiring, and therefore a different job.

    The incoherent loop's output comes back; this one's does not, and what
    the second arm buys instead is time. Both claims are made against the
    same pair of runs, so a wiring change that turned one motif into the
    other would fail both classes rather than quietly passing one.
    """

    def test_the_output_never_comes_back_down(self, cffl) -> None:
        _, traces = cffl
        z = traces["cold"].columns["loop_Z"]

        # Monotone to within the integrator's own tolerance. Stated as a
        # relative slack against the final level rather than an absolute
        # one, since the trace spans four orders of magnitude.
        slack = 1e-9 * z[-1]
        assert all(later >= earlier - slack for earlier, later in zip(z, z[1:]))
        assert max(z) == pytest.approx(z[-1], rel=1e-6), (
            "the maximum is not at the end, so this loop pulsed -- which is "
            "the incoherent loop's behaviour, not this one's"
        )

    def test_the_rise_arrives_late_and_the_lateness_is_the_slow_arm(
        self, cffl
    ) -> None:
        """The delay, measured against a control that differs in one thing.

        Pre-loading Y removes the wait and nothing else. The cold run must
        take substantially longer to reach the same level, and the warm run
        must take about ln(2)/d_z -- the time constant of Z alone, with no
        gate to wait for -- which pins the control as a control rather than
        just a second number.
        """
        constants, traces = cffl
        cold, warm = traces["cold"], traces["warm"]
        target = 0.5 * warm.columns["loop_Z"][-1]

        warm_time = _first_time_at_or_above(
            warm.times, warm.columns["loop_Z"], target
        )
        cold_time = _first_time_at_or_above(
            cold.times, cold.columns["loop_Z"], target
        )

        expected_warm = math.log(2.0) / constants["d_z"]
        assert warm_time == pytest.approx(expected_warm, abs=CFFL_END / 1201 * 2)
        assert cold_time > 1.5 * warm_time, (
            f"the cold run reached half maximum at {cold_time:.4g} and the "
            f"pre-loaded run at {warm_time:.4g}; with no delay from the "
            f"slow arm these would be the same"
        )

    def test_both_runs_end_in_the_same_place(self, cffl) -> None:
        """Delay, not attenuation.

        A motif that merely produced LESS output when Y started from zero
        would pass the timing test and be a different mechanism. The two
        runs must converge on one steady state, and on the closed form for
        it.
        """
        constants, traces = cffl
        gene = constants["_gene"]
        n = constants["n"]
        gate_x = CFFL_INPUT ** n / (constants["Kxz"] ** n + CFFL_INPUT ** n)
        y = constants["_y_steady"]
        gate_y = y ** n / (constants["Kyz"] ** n + y ** n)
        predicted = (constants["k_z"] * gene / constants["d_z"]) * gate_x * gate_y

        for label in ("cold", "warm"):
            final = traces[label].columns["loop_Z"][-1]
            assert final == pytest.approx(predicted, rel=1e-3), label

    def test_the_two_loops_disagree_about_the_second_half_of_the_run(
        self, cffl, iffl_step
    ) -> None:
        """The contrast stated in one place, so neither drifts alone.

        Adapting and delaying are opposite answers to the same question --
        what does the output do after the input steps? -- and a test file
        that checked each motif only against itself could let both drift
        into the same behaviour without noticing.
        """
        _, traces = cffl
        _, _, incoherent = iffl_step

        coherent_z = traces["cold"].columns["loop_Z"]
        incoherent_z = incoherent.columns["loop_Z"]

        assert coherent_z[-1] / max(coherent_z) == pytest.approx(1.0, abs=1e-6)
        assert incoherent_z[-1] / max(incoherent_z) < 0.5


# ---------------------------------------------------------------------------
# The Goldbeter-Koshland cycle: sharpness
# ---------------------------------------------------------------------------

#: Kinase-to-phosphatase ratios the sweep uses: 25 points, log-spaced over
#: four decades. Wide enough to bracket the 10% and 90% crossings of a
#: HYPERBOLIC response, which needs 81-fold on its own, and fine enough
#: (a factor of 1.35 per step) that a log-linear interpolation between
#: neighbouring points is worth reading.
RATIOS: Tuple[float, ...] = tuple(
    10 ** (-1.6 + 3.2 * index / 24) for index in range(25)
)

#: The total protein in the cycle, in mM. Every statement about saturation
#: is a statement about a Km RELATIVE to this number, which is why it is
#: named rather than left as a literal.
CYCLE_TOTAL = 1.0

#: The phosphatase amount, held fixed while the kinase is swept. Only the
#: RATIO enters the steady state, so which one moves is arbitrary; fixing
#: the phosphatase makes the swept variable the one a reader thinks of as
#: the input.
CYCLE_PHOSPHATASE = 1e-3

#: A hyperbolic response needs exactly this much change in its input to go
#: from 10% to 90%: (0.9/0.1) / (0.1/0.9) = 81. It is arithmetic, not a
#: fit, and it is the benchmark ultrasensitivity is defined against.
HYPERBOLIC_RESPONSE_COEFFICIENT = 81.0


def _cycle_fraction_phosphorylated(km: float, ratio: float, end: float) -> float:
    """Steady-state Xp/(X + Xp) for one kinase-to-phosphatase ratio."""
    composition = Composition("goldbeter_koshland")
    composition.add(ULTRASENSITIVE_CYCLE, "cycle")
    composition.set_initial("cycle_X", CYCLE_TOTAL)
    composition.set_initial("cycle_Xp", 0.0)
    composition.set_initial("cycle_kinase", CYCLE_PHOSPHATASE * ratio)
    composition.set_initial("cycle_phosphatase", CYCLE_PHOSPHATASE)
    network = _tuned(composition, cycle_Km_kin=km, cycle_Km_pptase=km)

    final = run(_runnable(composition, network), end=end, points=11).final_state()
    total = final["cycle_X"] + final["cycle_Xp"]
    assert total == pytest.approx(CYCLE_TOTAL, rel=1e-6), (
        "the cycle's conserved total moved during the run, so the fraction "
        "phosphorylated is being read off a trajectory that is already wrong"
    )
    return final["cycle_Xp"] / total


def _response_coefficient(
    inputs: Sequence[float], outputs: Sequence[float]
) -> float:
    """The input ratio between the 10% and 90% points.

    Log-linear interpolation between the two bracketing samples, because
    the sweep is log-spaced and the curve is close to straight in that
    coordinate near each crossing. Raises when a crossing is not bracketed:
    an extrapolated coefficient would be a number with no measurement
    behind it, which is worse here than a failure.
    """

    def crossing(level: float) -> float:
        pairs = list(zip(inputs, outputs))
        for (x0, y0), (x1, y1) in zip(pairs, pairs[1:]):
            if y0 <= level <= y1:
                if y1 == y0:
                    return x0
                weight = (level - y0) / (y1 - y0)
                return math.exp(
                    math.log(x0) + weight * (math.log(x1) - math.log(x0))
                )
        raise AssertionError(
            f"the sweep never crosses {level:.0%} -- it runs from "
            f"{outputs[0]:.3f} to {outputs[-1]:.3f}, so the response "
            f"coefficient is not bracketed and would have to be extrapolated"
        )

    return crossing(0.9) / crossing(0.1)


@pytest.fixture(scope="module")
def saturated_sweep():
    # Km = 0.1 against a total of 1.0: both converter enzymes work at a
    # tenth of the total, which is the zero-order regime the basis names.
    # The window is 5000 s against a turnover time of about
    # total/(kcat*E) = 100 s.
    return [_cycle_fraction_phosphorylated(0.1, r, 5_000.0) for r in RATIOS]


@pytest.fixture(scope="module")
def unsaturated_sweep():
    # Km = 100 against a total of 1.0: neither enzyme is anywhere near
    # saturation, so each arm is first order in its own substrate and the
    # cycle should behave like a binding curve.
    #
    # The window is 400 times longer for a reason that is not padding: an
    # unsaturated enzyme runs at kcat*E*S/Km, so a Km a thousand times
    # larger is a rate a thousand times slower and a relaxation time a
    # thousand times longer. Read at 5000 s this sweep reports 0.31 where
    # the steady state is 0.50 -- a curve that looks plausibly graded and
    # is simply unfinished.
    return [_cycle_fraction_phosphorylated(100.0, r, 2_000_000.0) for r in RATIOS]


class TestZeroOrderUltrasensitivity:
    def test_a_hyperbolic_response_needs_eighty_one_fold(self) -> None:
        """The benchmark, computed the same way as everything measured.

        Passing an exact hyperbola through `_response_coefficient` checks
        the measuring instrument against a case whose answer is known
        exactly, so a later failure of the sweeps is a statement about the
        cycle rather than about the interpolation.
        """
        hyperbolic = [ratio / (1.0 + ratio) for ratio in RATIOS]
        measured = _response_coefficient(RATIOS, hyperbolic)
        assert measured == pytest.approx(
            HYPERBOLIC_RESPONSE_COEFFICIENT, rel=0.02
        )

    def test_the_saturated_cycle_is_far_sharper_than_hyperbolic(
        self, saturated_sweep
    ) -> None:
        coefficient = _response_coefficient(RATIOS, saturated_sweep)
        assert coefficient < 5.0, (
            f"a response coefficient of {coefficient:.3g} is not "
            f"ultrasensitive"
        )
        assert coefficient < HYPERBOLIC_RESPONSE_COEFFICIENT / 10.0

    def test_outside_the_zero_order_regime_it_is_not_a_switch(
        self, unsaturated_sweep
    ) -> None:
        """The basis's own 'where it fails', checked rather than asserted.

        Same motif, same rate laws, same conserved total -- only the two Km
        values moved, from a tenth of the total to a hundred times it. The
        sharp switch becomes an ordinary binding curve, which is why the
        basis says sharpness is a joint property of the Km values and the
        total protein and not a property of the mechanism.
        """
        coefficient = _response_coefficient(RATIOS, unsaturated_sweep)
        assert coefficient > HYPERBOLIC_RESPONSE_COEFFICIENT / 2.0
        assert coefficient <= HYPERBOLIC_RESPONSE_COEFFICIENT * 1.02, (
            "a cycle cannot be LESS sharp than hyperbolic; 81 is the "
            "limit this response approaches from below"
        )

    def test_the_two_regimes_are_the_same_model(
        self, saturated_sweep, unsaturated_sweep
    ) -> None:
        # The strongest form of the claim. If the two sweeps had come from
        # different motifs the comparison would say nothing about
        # saturation, so this pins that only the Km moved -- both curves
        # pass through 50% at a ratio of one, which is where equal kcat and
        # equal Km put it regardless of how large those Km are.
        for sweep in (saturated_sweep, unsaturated_sweep):
            midpoint = sweep[len(RATIOS) // 2]
            assert RATIOS[len(RATIOS) // 2] == pytest.approx(1.0, rel=1e-9)
            assert midpoint == pytest.approx(0.5, abs=0.02)

        assert _response_coefficient(RATIOS, saturated_sweep) < (
            _response_coefficient(RATIOS, unsaturated_sweep) / 10.0
        )


class TestTheUltrasensitiveCycleIsNotASecondCopy:
    """A second definition would be two answers to one question.

    `library_enzymology.py` refuses this at import time and explains why:
    four implementations of Michaelis-Menten, and no way for a reader to
    tell which one the product used. The Goldbeter-Koshland cycle IS the
    phosphorylation cycle, symbol for symbol, so it is an alias.
    """

    def test_the_alias_is_the_same_object(self) -> None:
        assert ULTRASENSITIVE_CYCLE is PHOSPHORYLATION_CYCLE

    def test_the_registry_does_not_hold_it_twice(self) -> None:
        assert PHOSPHORYLATION_CYCLE.name not in SIGNALING_LIBRARY
        assert ALIASES["ultrasensitive_cycle"] == PHOSPHORYLATION_CYCLE.name

    def test_the_alias_resolves_through_the_lookup(self) -> None:
        assert signaling_motif("ultrasensitive_cycle") is PHOSPHORYLATION_CYCLE
        assert signaling_motif("goldbeter_koshland") is PHOSPHORYLATION_CYCLE

    def test_the_basis_states_the_zero_order_condition(self) -> None:
        """The sentence the alias exists to have added.

        Aliasing without it would have shipped a name for a mechanism whose
        own description never said when it is sharp -- which is the only
        thing a reader needs from it.
        """
        prose = " ".join(ULTRASENSITIVE_CYCLE.basis.split())
        assert "ZERO-ORDER CONDITION" in prose
        assert "far below the total protein" in prose
        assert "NOT SHARP AT ALL" in prose
        assert "81-fold" in prose
        # And it says where its own derivation strains, which is the same
        # regime.
        assert "quasi-steady-state form assumes" in prose

    def test_a_typo_is_refused_with_the_real_names(self) -> None:
        with pytest.raises(KeyError) as caught:
            signaling_motif("coherant_feedforward")
        message = str(caught.value)
        assert "coherent_feedforward" in message
        assert "ultrasensitive_cycle" in message


# ---------------------------------------------------------------------------
# The scaffold: the non-monotonicity the basis insists on
# ---------------------------------------------------------------------------

#: Total scaffold amounts, in mM, spanning two decades either side of the
#: partner concentration. The partners are at `SIGNALLING_POOL_MM` and are
#: CONSERVED, which is what makes the prozone possible at all: with the
#: partners buffered there is no titration and the curve is monotone.
SCAFFOLD_LEVELS: Tuple[float, ...] = (1e-5, 1e-4, 1e-3, 1e-2, 1e-1)

#: Two hundred times the slowest relaxation (1/koff = 100 s).
SCAFFOLD_END = 20_000.0


@pytest.fixture(scope="module")
def scaffold_titration() -> Dict[float, float]:
    ternary: Dict[float, float] = {}
    for level in SCAFFOLD_LEVELS:
        composition = Composition("scaffold_assembly")
        composition.add(SCAFFOLD_ASSEMBLY, "s")
        composition.set_initial("s_Sc", level)
        # The downstream substrate is set to zero so this measures assembly
        # and nothing else. Catalysis does not feed back on the complexes,
        # so leaving it running would only make the test slower.
        composition.set_initial("s_X", 0.0)
        trajectory = run(_runnable(composition), end=SCAFFOLD_END, points=11)
        assert trajectory.sound, [c.describe() for c in trajectory.invariants]
        ternary[level] = trajectory.final_state()["s_ScAB"]
    return ternary


class TestTheScaffoldEffectIsNotMonotonic:
    """The claim in the basis that a model most needs to get right.

    "More scaffold, more signal" is the intuition, it is wrong past the
    optimum, and a model that reproduces the intuition would advise an
    overexpression that reduces signalling.
    """

    def test_too_much_scaffold_pulls_the_partners_apart(
        self, scaffold_titration
    ) -> None:
        best = max(scaffold_titration, key=scaffold_titration.get)
        assert best not in (SCAFFOLD_LEVELS[0], SCAFFOLD_LEVELS[-1]), (
            f"the optimum is at the edge of the titration ({best:g} mM), so "
            f"this sweep has not bracketed the peak and says nothing about "
            f"non-monotonicity"
        )
        assert scaffold_titration[SCAFFOLD_LEVELS[-1]] < (
            scaffold_titration[best] / 10.0
        ), (
            "a hundred-fold scaffold excess did not suppress the ternary "
            "complex, so this model does not show the prozone effect its "
            "basis promises"
        )

    def test_too_little_scaffold_is_limiting_in_the_ordinary_way(
        self, scaffold_titration
    ) -> None:
        # The other side of the peak, so that the assertion above is about
        # a maximum rather than about a monotonically falling curve.
        assert scaffold_titration[SCAFFOLD_LEVELS[0]] < (
            scaffold_titration[max(scaffold_titration, key=scaffold_titration.get)]
            / 10.0
        )

    def test_the_basis_says_what_the_titration_shows(self) -> None:
        prose = " ".join(SCAFFOLD_ASSEMBLY.basis.split())
        assert "NOT MONOTONIC" in prose
        lowered = prose.lower()
        assert "prozone" in lowered
        # And it draws the practical consequence rather than leaving the
        # reader to. The titration above is the same statement in numbers.
        assert "knockdown" in lowered
        assert "overexpress" in lowered


# ---------------------------------------------------------------------------
# The two-component system: robustness to the regulator pool
# ---------------------------------------------------------------------------

#: Twenty times the regulator's relaxation time, which is its own pool
#: divided by the cycling flux -- about 100 s at the motif's defaults.
#:
#: Not longer, deliberately. Nothing in this motif regenerates ATP, so a
#: long enough run reports exhaustion rather than balance; the basis says
#: so and `test_the_run_is_not_reporting_a_starved_cell` checks that this
#: window is short enough for that not to be what is being measured.
TCS_END = 4_000.0


def _two_component(regulator_pool: float, **overrides: float):
    composition = Composition("two_component_system")
    composition.add(TWO_COMPONENT_SYSTEM, "t")
    composition.set_initial("t_RR", regulator_pool)
    composition.set_initial("t_RRp", 0.0)
    network = _tuned(composition, **overrides) if overrides else None
    return run(_runnable(composition, network), end=TCS_END, points=21)


@pytest.fixture(scope="module")
def two_component_titration():
    """The regulator pool at four levels spanning eight-fold.

    The lowest is deliberately BELOW the output the sensor cycle wants to
    hold, so the sweep contains the boundary of the robust regime as well
    as the regime itself -- a robustness test run only where robustness
    holds cannot show where it stops.
    """
    return {pool: _two_component(pool) for pool in (2.5e-3, 5e-3, 1e-2, 2e-2)}


class TestTheBifunctionalSensorIsRobustToItsRegulator:
    """The signature the basis names, run as the experiment it describes.

    Overexpress the response regulator and watch the phosphorylated pool.
    The claim is not "it changes a bit less than you would think" -- it is
    that the totals cancel out of the steady state exactly, so the only
    residual is the leak term k_off, whose size is also predicted.
    """

    def test_the_output_barely_moves_when_the_pool_quadruples(
        self, two_component_titration
    ) -> None:
        runs = two_component_titration
        small = runs[5e-3].final_state()["t_RRp"]
        large = runs[2e-2].final_state()["t_RRp"]

        assert large / small == pytest.approx(1.0, abs=0.03), (
            f"the regulator pool went up four-fold and the phosphorylated "
            f"pool went from {small:.6g} to {large:.6g}; a bifunctional "
            f"sensor should hold it"
        )
        # And the pool really did change, so there is something for the
        # cancellation to have cancelled.
        for pool, trajectory in runs.items():
            final = trajectory.final_state()
            assert final["t_RR"] + final["t_RRp"] == pytest.approx(pool, rel=1e-6)

    def test_the_held_level_is_the_closed_form_with_the_leak_in_it(
        self, two_component_titration
    ) -> None:
        """The exact answer, including the size of its own imperfection.

        With no autodephosphorylation the steady state is
        k_auto*f(S)*g(ATP)/k_ph and neither total appears. k_off spoils
        that by replacing k_ph with (k_ph + k_off/HK), and the basis says
        so -- so the test checks the corrected form tightly and the
        uncorrected one loosely, which pins that the ~9% gap is the leak
        and not an accident.
        """
        trajectory = two_component_titration[2e-2]
        constants = _defaults_of(TWO_COMPONENT_SYSTEM)
        final = trajectory.final_state()

        stimulus = final["t_S"]
        drive = (
            constants["k_auto"]
            * stimulus / (constants["Ks"] + stimulus)
            * final["t_ATP"] / (constants["Km_atp"] + final["t_ATP"])
        )
        without_leak = drive / constants["k_ph"]
        with_leak = drive / (
            constants["k_ph"] + constants["k_off"] / final["t_HK"]
        )

        assert final["t_RRp"] == pytest.approx(with_leak, rel=0.02)
        assert final["t_RRp"] == pytest.approx(without_leak, rel=0.15)
        assert with_leak < without_leak, "the leak can only lower the output"

    def test_a_monofunctional_sensor_tracks_the_pool_instead(self) -> None:
        """The control, and the reason the phosphatase term is in the motif.

        Setting k_ph to zero removes the only removal term proportional to
        the sensor, so the cancellation in the basis has nothing to cancel
        with. The same four-fold change in the pool now moves the output
        almost four-fold -- which is what the experiment would show for a
        monofunctional sensor, and is how the two are told apart.
        """
        small = _two_component(5e-3, t_k_ph=0.0).final_state()["t_RRp"]
        large = _two_component(2e-2, t_k_ph=0.0).final_state()["t_RRp"]
        assert large / small > 3.0, (
            f"without the sensor phosphatase the output should follow the "
            f"pool; it went from {small:.6g} to {large:.6g}"
        )

    def test_the_run_is_not_reporting_a_starved_cell(
        self, two_component_titration
    ) -> None:
        """The failure the basis warns about, kept out of the measurement.

        Nothing here regenerates ATP, so a long enough run reports
        exhaustion rather than balance. If this window ever became long
        enough for the nucleotide to matter, the robustness above would
        start measuring the ATP curve instead, and would still look like a
        pass.
        """
        for pool, trajectory in two_component_titration.items():
            atp = trajectory.columns["t_ATP"]
            assert atp[-1] > 0.9 * atp[0], pool


# ---------------------------------------------------------------------------
# The library's own rules
# ---------------------------------------------------------------------------


class TestEveryMotifPassesTheUnitChecker:
    """A dimensionally wrong rate law integrates and produces a smooth curve.

    There is no later point in the pipeline at which that becomes visible,
    so every motif has to balance at composition time -- and a motif that
    shipped with a standing finding would train a reader to stop
    reading them.
    """

    def test_the_sweep_covers_every_motif_this_module_defines(self) -> None:
        # Without this the parametrised test below would pass vacuously if
        # the registry were ever emptied.
        assert len(SIGNALING_LIBRARY) >= 7
        assert set(SIGNALING_LIBRARY) == {
            "incoherent_feedforward",
            "coherent_feedforward",
            "two_component_system",
            "gpcr_activation",
            "scaffold_assembly",
            "negative_feedback_oscillator",
            "bistable_positive_feedback",
        }

    @pytest.mark.parametrize("name", sorted(SIGNALING_LIBRARY))
    def test_a_motif_alone_produces_no_finding(self, name: str) -> None:
        composition = Composition(name)
        composition.add(SIGNALING_LIBRARY[name], "m")
        findings = composition.unit_findings()
        assert findings == (), [
            f"{f.severity}: {f.detail}" for f in findings
        ]

    @pytest.mark.parametrize("name", sorted(SIGNALING_LIBRARY))
    def test_a_motif_alone_builds_a_network_with_no_problems(
        self, name: str
    ) -> None:
        composition = Composition(name)
        composition.add(SIGNALING_LIBRARY[name], "m")
        network = composition.to_network()
        assert network.problems() == []
        assert network.reactions, name


class TestTheKindsAreNotDecoration:
    """Kind decides whether a scout is sent, so a wrong one is a fabrication.

    Two rules, and both are enforced here rather than trusted: a
    concentration is never resolvable, and a production rate is never
    lumped.
    """

    def test_no_amount_is_a_parameter(self) -> None:
        """Every concentration in these motifs is a PORT.

        A concentration declared as a parameter would be a quantity the
        caller sets that looks, in the registry, exactly like one somebody
        measured. Nobody publishes how much scaffold is in your cell.
        """
        offenders = [
            (motif.name, parameter.name)
            for motif in SIGNALING_LIBRARY.values()
            for parameter in motif.parameters
            if parameter.kind == KIND_CONCENTRATION
        ]
        assert offenders == []

    def test_every_resolvable_quantity_is_a_constant_or_an_affinity(
        self,
    ) -> None:
        for name, motif in sorted(SIGNALING_LIBRARY.items()):
            composition = Composition(name)
            composition.add(motif, "m")
            resolvable = composition.quantities_to_resolve()
            assert resolvable, f"{name} asks the literature for nothing at all"
            for quantity in resolvable:
                assert quantity.kind in RESOLVABLE_KINDS, quantity
            # And the Hill exponents are on the other side of the line: a
            # cooperativity is a modelling choice with a conventional value,
            # not a measurement of this system.
            exponents = {
                p.name for p in motif.parameters if p.kind == KIND_EXPONENT
            }
            asked = {q.parameter_name for q in resolvable}
            assert exponents & asked == set(), name

    def test_no_parameter_here_is_a_lumped_synthesis_rate(self) -> None:
        """ADR 0013, enforced by dimension rather than by reading names.

        A production rate in mM/s is `k_tx * [gene]` with the copy number
        multiplied in, so a measured value of it is a measurement of
        somebody else's copy number. `library_expression.py` made this
        argument; this asserts that no motif here reintroduced the shape.
        The check is dimensional, so a parameter that avoided the word
        `ks` and kept the units would still be caught.
        """
        lumped = rate_unit_for(parse_unit("mM"))
        offenders = [
            f"{motif.name}.{parameter.name} ({parameter.unit})"
            for motif in SIGNALING_LIBRARY.values()
            for parameter in motif.parameters
            if parse_unit(parameter.unit).same_dimensions(lumped)
        ]
        assert offenders == [], (
            "these carry the units of a lumped synthesis rate: "
            + ", ".join(offenders)
        )

    def test_the_chosen_quantities_include_every_starting_amount(self) -> None:
        composition = Composition("gpcr")
        composition.add(SIGNALING_LIBRARY["gpcr_activation"], "r")
        chosen = set(composition.chosen_quantities())
        assert {"r_L", "r_R", "r_G", "r_RGS"} <= chosen
        resolvable = {q.parameter_id for q in composition.quantities_to_resolve()}
        assert chosen & resolvable == set()


class TestTheRegistryRefusesADuplicate:
    """A guard indistinguishable from its own bug is not yet a guard.

    `_refuse_duplicates` runs at import and has never fired, so nothing so
    far shows that it CAN. Driven here with a planted collision.
    """

    def test_a_name_already_in_the_core_library_is_refused(
        self, monkeypatch
    ) -> None:
        from caterva.compose import library_signaling as module

        monkeypatch.setattr(
            module, "SIGNALING_LIBRARY", {"catalytic_step": LIBRARY["catalytic_step"]}
        )
        with pytest.raises(MotifError) as caught:
            module._refuse_duplicates()
        message = str(caught.value)
        assert "catalytic_step" in message
        assert "library.py" in message
        assert "do not add a second copy" in message

    def test_the_real_registry_is_clean(self) -> None:
        from caterva.compose import library_signaling as module

        module._refuse_duplicates()  # must not raise
        assert set(SIGNALING_LIBRARY) & set(LIBRARY) == set()


class TestTheCopiedConstantCannotRot:
    def test_the_gene_copy_default_agrees_with_the_expression_library(
        self,
    ) -> None:
        """One gene copy per cell volume is spelled out in two files.

        `library_signaling.py` declines to import `library_expression.py`
        so that it stands on its own the way `grammar.py` assumes an
        expansion library can be missing. That leaves a copy, and a copy
        with nothing pinning it is a copy that drifts.
        """
        from caterva.compose.library_expression import (
            SINGLE_COPY_GENE_MM as from_expression,
        )

        assert SINGLE_COPY_GENE_MM == from_expression


class TestEveryBasisSaysWhereItFails:
    """The rule this module states about itself, applied to itself.

    A basis that only says what it assumes has told a reader half of what
    they need. These are keyword checks and they are weak on purpose --
    they cannot judge whether the sentence is any good, only that somebody
    wrote one -- but a motif added later with no failure mode named will
    fail here rather than sail through review.
    """

    @pytest.mark.parametrize("name", sorted(SIGNALING_LIBRARY))
    def test_the_basis_names_a_regime_it_breaks_in(self, name: str) -> None:
        prose = SIGNALING_LIBRARY[name].basis.lower()
        assert prose, name
        assert any(
            phrase in prose
            for phrase in ("fails", "where it fails", "cannot", "not sufficient")
        ), f"{name}'s basis names no failure mode"

    @pytest.mark.parametrize("name", sorted(SIGNALING_LIBRARY))
    def test_every_placeholder_default_is_labelled_as_one(
        self, name: str
    ) -> None:
        """A resolvable default that does not say it is a placeholder.

        The pipeline hands every resolvable parameter to a scout as a
        quantity to go and find, and its default is what a report shows if
        nothing is found. An unlabelled one reads as a measurement.
        """
        unlabelled = [
            parameter.name
            for parameter in SIGNALING_LIBRARY[name].parameters
            if parameter.kind in RESOLVABLE_KINDS
            and "placeholder" not in parameter.description.lower()
        ]
        assert unlabelled == [], f"{name}: {unlabelled}"

    @pytest.mark.parametrize("name", sorted(SIGNALING_LIBRARY))
    def test_no_basis_uses_an_em_dash(self, name: str) -> None:
        # House style, and not only cosmetic: these strings are rendered
        # into reports and into SBML notes, and the two spellings have
        # travelled differently through that pipeline before.
        assert "—" not in SIGNALING_LIBRARY[name].basis, name
        assert "–" not in SIGNALING_LIBRARY[name].basis, name
