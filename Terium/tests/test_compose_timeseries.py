"""What a trajectory shows, checked against answers that are known exactly.

WHY ALMOST EVERY TEST HERE BUILDS ITS OWN ARRAY
-----------------------------------------------
A sine of period 7 and amplitude 3 has a period of 7 and an amplitude of 3.
No integrator is involved, no model is involved, and there is nothing to
argue about -- so when `oscillation` returns 7.0001 the only possible
explanation is this module's arithmetic, which is the thing under test.

Testing against a simulation instead would check two things at once and
attribute a failure to neither. The repressilator appears at the end, once,
because a reading that works on written-down arrays and not on a real
trajectory would be a reading of nothing -- but it is the last test, not the
first, and it asserts agreement between two methods rather than a number
nobody can derive.

THE TOLERANCES ARE MEASURED, NOT CHOSEN
---------------------------------------
`WORST_*` below were measured over the grid `SINE_GRID` describes: five
sampling densities, five record lengths and six phases, 150 combinations.
Each is the largest relative error seen, rounded up to leave room and no
more. A tolerance loose enough never to fail is not a tolerance, and a
tolerance tuned to the last digit fails on the next numpy.
"""

from __future__ import annotations

import math

import pytest

from Terium.compose.timeseries import (
    AGREEMENT_TOLERANCE, DECAYING, ENVELOPE_RESOLUTION, GROWING,
    MINIMUM_CYCLES, MINIMUM_SAMPLES_PER_PERIOD, NYQUIST_SAMPLES_PER_PERIOD,
    RISE_HIGH_FRACTION, RISE_LOW_FRACTION, SETTLING_BAND, SUSTAINED,
    Series, TimeSeriesRefused, adaptation, damping, mean_crossings,
    oscillation, read, sample_spacing, step_response, turning_points,
)

numpy = pytest.importorskip("numpy", reason="reading a trajectory needs numpy")
np = numpy


# -- the signals, written down --------------------------------------------

PERIOD = 7.0
AMPLITUDE = 3.0
OFFSET = 2.0


def sine(
    *,
    period: float = PERIOD,
    amplitude: float = AMPLITUDE,
    offset: float = OFFSET,
    cycles: float = 6.1,
    samples_per_period: float = 40.0,
    phase: float = 0.0,
    growth: float = 0.0,
) -> Series:
    """offset + amplitude * exp(growth*t) * sin(2*pi*t/period + phase).

    `growth` is the thing `Damping` has to recover: negative decays,
    positive grows, and the per-cycle ratio is exactly exp(growth*period)
    whatever else is going on.
    """
    count = int(round(cycles * samples_per_period)) + 1
    times = np.linspace(0.0, cycles * period, count)
    values = offset + amplitude * np.exp(growth * times) * np.sin(
        2.0 * np.pi * times / period + phase
    )
    return Series.of(times, values, "X")


#: (samples per period, cycles, phase). Non-integer cycle counts on purpose:
#: a record of EXACTLY n periods that starts exactly on an upward crossing
#: yields n-1 measurable intervals, because the crossing at t=0 has no
#: sample below the mean before it and the one at the end has none above it
#: after. That is correct behaviour and it is not what these rows are for.
SINE_GRID = [
    (spp, cycles, phase)
    for spp in (10.0, 12.0, 16.0, 20.0, 40.0)
    for cycles in (4.3, 5.5, 6.1, 7.4, 10.2)
    for phase in (0.0, 0.31, 1.0, 2.2, 4.0, 5.5)
]

#: Largest relative errors measured over SINE_GRID, rounded up.
#: crossings 2.2e-4, autocorrelation 2.3e-3, extremum amplitude 9.2e-3,
#: variance amplitude 1.7e-2.
WORST_PERIOD_BY_CROSSINGS = 1e-3
WORST_PERIOD_BY_AUTOCORRELATION = 5e-3
WORST_AMPLITUDE_BY_EXTREMA = 1.5e-2
WORST_AMPLITUDE_BY_VARIANCE = 3e-2


class TestASineIsRecoveredByBothMethods:
    """The test that matters.

    Two estimators that share nothing below the samples, on a signal whose
    answer is written in its own definition. If this fails, every reading
    this module takes off a real trajectory is worthless, and no amount of
    agreement with a simulation would tell you so.
    """

    def test_both_methods_return_the_period_that_was_written_down(self) -> None:
        reading = oscillation(sine(), "X")
        assert reading.period_by_crossings == pytest.approx(
            PERIOD, rel=WORST_PERIOD_BY_CROSSINGS
        )
        assert reading.period_by_autocorrelation == pytest.approx(
            PERIOD, rel=WORST_PERIOD_BY_AUTOCORRELATION
        )

    def test_both_methods_return_the_amplitude_that_was_written_down(self) -> None:
        reading = oscillation(sine(), "X")
        assert reading.amplitude_by_extrema == pytest.approx(
            AMPLITUDE, rel=WORST_AMPLITUDE_BY_EXTREMA
        )
        assert reading.amplitude_by_variance == pytest.approx(
            AMPLITUDE, rel=WORST_AMPLITUDE_BY_VARIANCE
        )

    @pytest.mark.parametrize("samples_per_period,cycles,phase", SINE_GRID)
    def test_the_tolerances_hold_across_sampling_length_and_phase(
        self, samples_per_period: float, cycles: float, phase: float
    ) -> None:
        """150 combinations, because one is an anecdote.

        The phase matters and is the reason this sweep exists: where the
        grid happens to land relative to a peak changes what the sample
        extrema see by several percent, and a single well-chosen phase
        would hide it.
        """
        reading = oscillation(
            sine(
                samples_per_period=samples_per_period, cycles=cycles, phase=phase
            ),
            "X",
        )
        assert reading.period_by_crossings == pytest.approx(
            PERIOD, rel=WORST_PERIOD_BY_CROSSINGS
        )
        assert reading.period_by_autocorrelation == pytest.approx(
            PERIOD, rel=WORST_PERIOD_BY_AUTOCORRELATION
        )
        assert reading.amplitude_by_extrema == pytest.approx(
            AMPLITUDE, rel=WORST_AMPLITUDE_BY_EXTREMA
        )
        assert reading.amplitude_by_variance == pytest.approx(
            AMPLITUDE, rel=WORST_AMPLITUDE_BY_VARIANCE
        )

    def test_the_two_methods_agree_and_a_single_period_is_available(self) -> None:
        reading = oscillation(sine(), "X")
        assert reading.methods_agree
        assert reading.disagreement < AGREEMENT_TOLERANCE
        assert reading.period == pytest.approx(PERIOD, rel=1e-3)

    def test_the_period_survives_the_sampling_floor(self) -> None:
        # Eight samples per period is the least this module will report
        # from, so it is the case where the claim is weakest and the one
        # worth pinning.
        reading = oscillation(
            sine(samples_per_period=MINIMUM_SAMPLES_PER_PERIOD, cycles=6.1), "X"
        )
        assert reading.samples_per_period == pytest.approx(
            MINIMUM_SAMPLES_PER_PERIOD, rel=1e-2
        )
        assert reading.period_by_crossings == pytest.approx(PERIOD, rel=1e-3)
        assert reading.period_by_autocorrelation == pytest.approx(PERIOD, rel=5e-3)


class TestWhyTheAutocorrelationIsNormalisedPerLag:
    """The design claim, driven against the estimator it rejects.

    `autocorrelation` normalises every lag by the two overlaps' own root
    sums of squares rather than by a fixed record length. That is a choice,
    and a choice defended only by a paragraph is a choice nobody can check.
    The textbook unbiased estimator is written out here and compared on a
    signal whose period is written in its own definition.

    SPLIT OUT SO IT CAN FAIL. A mutation swapping the per-lag normalisation
    for the textbook one survived the rest of this file: at 40 samples per
    period over five or more cycles, the two agree to better than the stated
    tolerance and the distinction is unfalsifiable where it lived. It is
    visible at 10 samples per period over the shortest record this module
    accepts, which is exactly where a real trajectory sits.
    """

    #: 10 samples per period and 4.3 cycles: coarse and short, and both
    #: within what this module will report from. Measured worst case over
    #: the six phases -- textbook unbiased 0.66%, shipped 0.23%.
    SAMPLES_PER_PERIOD = 10.0
    CYCLES = 4.3
    PHASE = 2.2

    def _textbook_period(self, times, values) -> float:
        """r(k) = sum(x_i * x_{i+k}) / (n - k), one global mean.

        The unbiased estimator as it is written in every signal-processing
        text. Reimplemented here rather than imported, because the point is
        to compare against something this module does NOT contain.
        """
        series = np.asarray(values, dtype=float)
        series = series - series.mean()
        count = series.size
        max_lag = count // 2
        raw = np.array(
            [float(np.sum(series[: count - k] * series[k:])) / (count - k)
             for k in range(max_lag + 1)]
        )
        raw = raw / raw[0]
        spacing = (times[-1] - times[0]) / (len(times) - 1)
        negative = next(k for k in range(1, max_lag + 1) if raw[k] < 0.0)
        for lag in range(negative + 1, max_lag):
            if raw[lag] >= raw[lag - 1] and raw[lag] > raw[lag + 1]:
                curvature = raw[lag - 1] - 2.0 * raw[lag] + raw[lag + 1]
                offset = 0.5 * (raw[lag - 1] - raw[lag + 1]) / curvature
                return (lag + offset) * spacing
        raise AssertionError("the textbook estimator found no repeat")

    def test_the_shipped_normalisation_is_the_more_accurate_one(self) -> None:
        series = sine(
            samples_per_period=self.SAMPLES_PER_PERIOD,
            cycles=self.CYCLES,
            phase=self.PHASE,
        )
        shipped = oscillation(series, "X").period_by_autocorrelation
        textbook = self._textbook_period(series.times, series.columns["X"])
        assert abs(shipped - PERIOD) < abs(textbook - PERIOD)

    def test_the_estimator_this_module_rejects_misses_the_stated_tolerance(
        self,
    ) -> None:
        """Otherwise "better" could mean better by a part in a million.

        The textbook estimator is out by more than
        WORST_PERIOD_BY_AUTOCORRELATION here, so swapping the normalisation
        would not be a refinement -- it would break the tolerance this file
        asserts everywhere else.
        """
        series = sine(
            samples_per_period=self.SAMPLES_PER_PERIOD,
            cycles=self.CYCLES,
            phase=self.PHASE,
        )
        textbook = self._textbook_period(series.times, series.columns["X"])
        assert abs(textbook / PERIOD - 1.0) > WORST_PERIOD_BY_AUTOCORRELATION
        shipped = oscillation(series, "X").period_by_autocorrelation
        assert abs(shipped / PERIOD - 1.0) < WORST_PERIOD_BY_AUTOCORRELATION


class TestTheShapeRatioIsWaveformNotError:
    """Two amplitudes differing is information, and it is checkable.

    sqrt(2 * variance) is the amplitude of a SINE with that variance. A
    square wave of amplitude A has variance A^2, so the ratio to the
    extremum amplitude is exactly sqrt(2); a triangle has variance A^2/3 and
    gives sqrt(2/3). Both are exact, neither is a fault, and a module that
    reported one amplitude would have thrown the distinction away.
    """

    def _wave(self, kind: str) -> Series:
        times = np.linspace(0.0, 6.0 * PERIOD, 6 * 80 + 1)
        angle = 2.0 * np.pi * times / PERIOD + 0.13
        if kind == "square":
            shape = np.sign(np.sin(angle))
        else:
            shape = (2.0 / np.pi) * np.arcsin(np.sin(angle))
        return Series.of(times, OFFSET + AMPLITUDE * shape, "X")

    def test_a_square_wave_gives_exactly_root_two(self) -> None:
        reading = oscillation(self._wave("square"), "X")
        assert reading.shape_ratio == pytest.approx(math.sqrt(2.0), rel=1e-4)
        assert reading.amplitude_by_extrema == pytest.approx(AMPLITUDE, rel=1e-9)

    def test_a_triangle_wave_gives_root_two_thirds(self) -> None:
        reading = oscillation(self._wave("triangle"), "X")
        assert reading.shape_ratio == pytest.approx(math.sqrt(2.0 / 3.0), rel=0.03)

    def test_a_plateau_never_reports_a_peak_above_every_sample(self) -> None:
        """The reason the parabola is fitted only at a strict turning point.

        On a square wave the three samples around a peak are (h, h, -h). The
        vertex of the parabola through them sits half a sample to the left
        at h + (h - -h)/8, which is 25% above anything the signal ever did.
        A refinement that invents a value above every sample is this module
        making a number up, so a plateau keeps its sample.
        """
        peaks = turning_points(
            self._wave("square").times, self._wave("square").columns["X"]
        )
        assert peaks, "a square wave has peaks"
        ceiling = max(self._wave("square").columns["X"])
        for peak in peaks:
            assert peak.value <= ceiling


class TestDamping:
    """Sustained, decaying or growing, against an exponent written down."""

    @pytest.mark.parametrize(
        "growth,verdict",
        [(-0.03, DECAYING), (-0.005, DECAYING), (0.0, SUSTAINED),
         (0.005, GROWING), (0.03, GROWING)],
    )
    def test_the_verdict_and_the_ratio_follow_the_exponent(
        self, growth: float, verdict: str
    ) -> None:
        reading = oscillation(sine(growth=growth, cycles=6.1), "X")
        assert reading.damping is not None
        assert reading.damping.verdict == verdict
        # The envelope of A*exp(g*t)*sin(2*pi*t/P) shrinks by exactly
        # exp(g*P) each period. Nothing empirical about it.
        assert reading.damping.per_cycle_ratio == pytest.approx(
            math.exp(growth * PERIOD), rel=5e-3
        )
        assert reading.damping.rate == pytest.approx(growth, abs=1e-4)

    def test_a_sustained_sine_is_indistinguishable_from_constant(self) -> None:
        reading = oscillation(sine(growth=0.0), "X")
        assert reading.damping is not None
        assert abs(reading.damping.per_cycle_ratio - 1.0) < ENVELOPE_RESOLUTION
        assert "indistinguishable from constant" in reading.damping.describe()

    def test_a_constant_swing_on_a_rising_baseline_is_still_sustained(self) -> None:
        """Why the envelope is peak-to-trough and not peak-above-the-mean.

        This signal's PEAKS climb every cycle, by construction. Its SWING
        does not change at all. Measuring peak height above the window mean
        would report a growing oscillation, which would be a confident
        answer to a question nobody asked -- the baseline moved, the
        oscillation did not.
        """
        times = np.linspace(0.0, 6.1 * PERIOD, 6 * 40 + 1)
        values = (
            OFFSET
            + 0.4 * times
            + AMPLITUDE * np.sin(2.0 * np.pi * times / PERIOD)
        )
        reading = damping(Series.of(times, values, "X"), "X", period=PERIOD)
        assert reading.verdict == SUSTAINED
        assert reading.per_cycle_ratio == pytest.approx(1.0, abs=SETTLING_BAND)

    def test_the_cycle_length_can_come_from_the_peaks_themselves(self) -> None:
        """No period given, so the peak spacing supplies one.

        That spacing is a THIRD estimate of the period and it is used only
        to turn a rate into a per-cycle ratio -- it is never reported as the
        period, because a number measured from three peaks has no second
        method behind it.
        """
        series = sine(growth=-0.03, cycles=6.1)
        inferred = damping(series, "X")
        told = damping(series, "X", period=PERIOD)
        assert inferred.verdict == told.verdict == DECAYING
        assert inferred.rate == pytest.approx(told.rate, rel=1e-9)
        assert inferred.per_cycle_ratio == pytest.approx(
            math.exp(-0.03 * PERIOD), rel=1e-2
        )

    def test_damping_refuses_when_it_cannot_infer_a_cycle_length(self) -> None:
        # One peak gives no spacing, and no period was passed. Inventing one
        # would make the per-cycle ratio a number about nothing.
        times = np.linspace(0.0, 1.2 * PERIOD, 121)
        values = OFFSET + AMPLITUDE * np.sin(2.0 * np.pi * times / PERIOD)
        with pytest.raises(TimeSeriesRefused, match="no peak spacing"):
            damping(Series.of(times, values, "X"), "X")

    def test_damping_refuses_when_there_is_no_second_swing_to_compare(self) -> None:
        # One excursion is a swing; a trend needs two. Defaulting to
        # "sustained" here would be the module answering from no evidence.
        times = np.linspace(0.0, 1.2 * PERIOD, 121)
        values = OFFSET + AMPLITUDE * np.sin(2.0 * np.pi * times / PERIOD)
        with pytest.raises(TimeSeriesRefused, match="at least two"):
            damping(Series.of(times, values, "X"), "X", period=PERIOD)


class TestNyquist:
    """Aliasing, which does not look like anything going wrong."""

    def _aliased(self) -> Series:
        # A period of 1.0 sampled every 0.7: 1.43 samples per period, well
        # under Nyquist, so the true frequency cannot be represented at all.
        times = np.arange(0.0, 30.0, 0.7)
        return Series.of(times, np.sin(2.0 * np.pi * times / 1.0), "X")

    def test_a_signal_sampled_below_nyquist_is_refused_by_name(self) -> None:
        with pytest.raises(TimeSeriesRefused) as caught:
            oscillation(self._aliased(), "X")
        message = str(caught.value)
        assert "ALIASING" in message
        assert f"{NYQUIST_SAMPLES_PER_PERIOD:g} samples per period" in message
        assert "points >=" in message, "a refusal has to say what to do"

    def test_the_aliased_period_is_wrong_and_looks_fine(self) -> None:
        """Measured on the primitive, because this is the whole argument.

        The refusal is not defending against an obviously broken number. The
        crossings of this signal are evenly spaced and the interval between
        them is stable -- it is simply 2.33 instead of 1.0, the true
        frequency folded about the sampling frequency. Nothing downstream
        could have caught it.
        """
        series = self._aliased()
        crossings = np.diff(np.asarray(mean_crossings(series.times, series.columns["X"])))
        apparent = float(crossings.mean())
        assert apparent == pytest.approx(2.333, rel=0.05)
        assert apparent > 2.0 * 1.0, "the apparent period is not the true 1.0"

    def test_the_floor_bites_in_both_directions(self) -> None:
        # Seven samples per period refused, eight accepted. A threshold that
        # only ever passes is not a threshold.
        coarse = sine(samples_per_period=7.0, cycles=6.0)
        with pytest.raises(TimeSeriesRefused, match="ALIASING"):
            oscillation(coarse, "X")
        fine = sine(samples_per_period=8.0, cycles=6.0)
        assert oscillation(fine, "X").samples_per_period == pytest.approx(8.0, rel=1e-2)


class TestTooShortAWindow:
    """A period from one interval is an extrapolation wearing a number."""

    def test_under_the_stated_number_of_cycles_is_refused(self) -> None:
        with pytest.raises(TimeSeriesRefused) as caught:
            oscillation(sine(cycles=2.3, samples_per_period=60.0), "X")
        message = str(caught.value)
        assert f"{MINIMUM_CYCLES} is the fewest" in message
        assert "EXTRAPOLATION" in message
        assert "re-run to end >=" in message, "a refusal has to say what to do"

    def test_the_cycle_count_bites_in_both_directions(self) -> None:
        with pytest.raises(TimeSeriesRefused, match="fewest"):
            oscillation(sine(cycles=2.9, samples_per_period=60.0), "X")
        accepted = oscillation(sine(cycles=3.4, samples_per_period=60.0), "X")
        assert accepted.cycles >= MINIMUM_CYCLES

    def test_a_signal_that_never_repeats_says_which_two_things_it_could_be(self) -> None:
        """A monotone approach and a too-short window look identical.

        Naming one of them would be a guess, and the data genuinely cannot
        separate them, so the refusal names both.
        """
        times = np.linspace(0.0, 20.0, 401)
        values = 1.0 - np.exp(-times / 3.0)
        with pytest.raises(TimeSeriesRefused) as caught:
            oscillation(Series.of(times, values, "X"), "X")
        message = str(caught.value)
        assert "crosses its own mean upward" in message
        assert "monotone approach" in message
        assert "longer than the window" in message

    def test_a_constant_species_has_no_period_and_says_so(self) -> None:
        """And the test that a constant is constant is not trivial.

        `np.full(401, 1e-3)` does not have a mean of exactly 1e-3 once 401
        copies have been summed and divided, so its variance comes back at
        about 1e-38 rather than at zero. A check for exactly zero variance
        called that an oscillation and went looking for its period, which is
        why the floor is relative to the signal's own magnitude.
        """
        times = np.linspace(0.0, 20.0, 401)
        with pytest.raises(TimeSeriesRefused, match="does not change over"):
            oscillation(Series.of(times, np.full(times.shape, 1e-3), "X"), "X")


class TestWhenTheMethodsDisagree:
    """Disagreement is the finding, not a failure to produce a number."""

    def _two_tone(self) -> Series:
        # A fundamental and its second harmonic, out of phase. The mean
        # crossings see the fundamental; the autocorrelation matches the
        # half-period copy better. Neither is wrong -- the signal does not
        # have one period.
        times = np.linspace(0.0, 8.0 * PERIOD, 1401)
        values = (
            OFFSET
            + AMPLITUDE * np.sin(2.0 * np.pi * times / PERIOD)
            + 2.0 * np.sin(2.0 * np.pi * times / (PERIOD / 2.0) + 0.4)
        )
        return Series.of(times, values, "X")

    def test_the_disagreement_is_flagged_rather_than_averaged(self) -> None:
        reading = oscillation(self._two_tone(), "X")
        assert not reading.methods_agree
        assert reading.disagreement > AGREEMENT_TOLERANCE

    def test_the_single_period_refuses_and_names_both_numbers(self) -> None:
        reading = oscillation(self._two_tone(), "X")
        with pytest.raises(TimeSeriesRefused) as caught:
            _ = reading.period
        message = str(caught.value)
        assert f"{reading.period_by_crossings:.6g}" in message
        assert f"{reading.period_by_autocorrelation:.6g}" in message
        assert "no single period" in message

    def test_both_numbers_are_still_reported(self) -> None:
        # Refusing the average must not cost the reader the measurements.
        reading = oscillation(self._two_tone(), "X")
        assert reading.period_by_crossings > 0.0
        assert reading.period_by_autocorrelation > 0.0
        assert "disagree" in reading.summary()


class TestAdaptation:
    """Peak, time to peak, and how much of the excursion came back."""

    def _perfect(self) -> Series:
        # exp(-t/slow) - exp(-t/fast) returns to zero exactly, so this
        # adapts perfectly by construction. Its peak is at
        # (fast*slow/(slow-fast)) * ln(slow/fast), which is an identity and
        # not a fit.
        times = np.linspace(0.0, 100.0, 100001)
        values = OFFSET + (np.exp(-times / 10.0) - np.exp(-times / 1.0))
        return Series.of(times, values, "X")

    def test_a_perfect_adapter_returns_all_of_its_excursion(self) -> None:
        reading = adaptation(self._perfect(), "X")
        assert reading.recovered == pytest.approx(1.0, abs=1e-3)
        assert reading.residual == pytest.approx(0.0, abs=1e-3)
        assert reading.settled

    def test_the_time_to_peak_is_the_analytic_one(self) -> None:
        fast, slow = 1.0, 10.0
        expected = (fast * slow / (slow - fast)) * math.log(slow / fast)
        reading = adaptation(self._perfect(), "X")
        assert reading.time_to_peak == pytest.approx(expected, rel=1e-3)
        assert reading.peak == pytest.approx(
            OFFSET + math.exp(-expected / slow) - math.exp(-expected / fast),
            rel=1e-6,
        )

    def _pulse(self, held: float, decay_windows: float) -> Series:
        """Rise to a peak at t=3, then relax toward a stated residual.

        Piecewise and exact: the peak is `OFFSET + 4` at t = 3 to the
        sample, and the value at the end is `OFFSET + 4*held` to within
        exp(-decay_windows). So `recovered` is 1 - held, with no fitting
        anywhere in the construction.
        """
        peak_at, size, decay = 3.0, 4.0, 1.0
        end = peak_at + decay_windows * decay
        times = np.linspace(0.0, end, int(round(end * 1000.0)) + 1)
        rising = OFFSET + size * (1.0 - np.cos(np.pi * np.minimum(times, peak_at) / peak_at)) / 2.0
        falling = OFFSET + size * (
            held + (1.0 - held) * np.exp(-(times - peak_at) / decay)
        )
        return Series.of(times, np.where(times <= peak_at, rising, falling), "X")

    def test_a_partial_adapter_reports_the_fraction_and_not_a_verdict(self) -> None:
        reading = adaptation(self._pulse(held=0.25, decay_windows=20.0), "X")
        assert reading.recovered == pytest.approx(0.75, abs=1e-6)
        assert reading.peak == pytest.approx(OFFSET + 4.0, rel=1e-9)
        assert reading.time_to_peak == pytest.approx(3.0, abs=1e-3)
        assert reading.settled

    def test_a_run_that_ends_mid_return_says_the_fraction_is_not_final(self) -> None:
        """The honest half of a partial answer.

        Cut at one decay half-life, exactly half the excursion has come
        back. That number is correct about the window and wrong about the
        mechanism, which is going to 100%, and the only way a reader can
        tell is if the module says the run had not finished.
        """
        reading = adaptation(
            self._pulse(held=0.0, decay_windows=math.log(2.0)), "X"
        )
        assert reading.recovered == pytest.approx(0.5, abs=1e-5)
        assert not reading.settled
        assert "still moving" in reading.summary()
        assert "not in this trajectory" in reading.summary()

    def test_a_step_recovers_nothing_and_that_is_zero_not_a_refusal(self) -> None:
        times = np.linspace(0.0, 40.0, 4001)
        values = OFFSET + 3.0 * (1.0 - np.exp(-times / 2.0))
        reading = adaptation(Series.of(times, values, "X"), "X")
        assert reading.recovered == pytest.approx(0.0, abs=1e-6)
        assert reading.excursion == pytest.approx(3.0, rel=1e-6)

    def test_the_fraction_is_measured_from_the_baseline_and_not_from_zero(self) -> None:
        """`final / peak` is the other reading, and it is the wrong one.

        Two signals with identical dynamics, one offset by 100. A fraction
        measured from zero calls them 0.5 and 0.995 adapted; measured from
        the baseline, both are perfect, which is what they are. Where zero
        happens to sit is not a property of the response.
        """
        low = adaptation(self._perfect(), "X")
        times = np.asarray(self._perfect().times)
        shifted = np.asarray(self._perfect().columns["X"]) + 100.0
        high = adaptation(Series.of(times, shifted, "X"), "X")
        assert low.recovered == pytest.approx(high.recovered, abs=1e-6)
        assert high.final / high.peak != pytest.approx(high.recovered, abs=1e-3)

    def test_the_peak_is_a_sample_and_never_above_one(self) -> None:
        # A pulse driven by a stimulus applied at a moment has a corner, not
        # a smooth maximum, and a parabola through a corner returns a value
        # the signal never took.
        series = self._pulse(held=0.25, decay_windows=20.0)
        reading = adaptation(series, "X")
        assert reading.peak == max(series.columns["X"])
        assert reading.time_to_peak in series.times

    def test_a_falling_pulse_is_read_the_same_way(self) -> None:
        times = np.asarray(self._perfect().times)
        inverted = 2.0 * OFFSET - np.asarray(self._perfect().columns["X"])
        reading = adaptation(Series.of(times, inverted, "X"), "X")
        assert reading.direction == "falling"
        assert reading.recovered == pytest.approx(1.0, abs=1e-3)

    def test_a_signal_that_never_moves_is_refused(self) -> None:
        times = np.linspace(0.0, 10.0, 101)
        with pytest.raises(TimeSeriesRefused, match="no peak to adapt from"):
            adaptation(Series.of(times, np.full(times.shape, 2.0), "X"), "X")

    def test_the_assumed_baseline_is_declared(self) -> None:
        reading = adaptation(self._perfect(), "X")
        assert reading.baseline_is_assumed
        assert "assumes the run starts before" in reading.summary()

        told = adaptation(self._perfect(), "X", baseline=OFFSET)
        assert not told.baseline_is_assumed
        assert "assumes the run starts before" not in told.summary()


class TestStepResponse:
    """Rise, overshoot and settling, against closed-form control theory."""

    def _first_order(self, tau: float = 2.0) -> Series:
        # 1 - exp(-t/tau). Run to 40*tau so the final sample IS the limit in
        # double precision, which makes the two analytic answers below exact
        # rather than nearly exact.
        times = np.linspace(0.0, 40.0 * tau, 8001)
        return Series.of(times, 1.0 - np.exp(-times / tau), "X")

    def test_a_first_order_rise_time_is_tau_ln_nine(self) -> None:
        # From 10% to 90% of the change: tau*(ln(1/0.1) - ln(1/0.9)) =
        # tau*ln(9). The convention is stated on RISE_LOW/HIGH_FRACTION and
        # the answer follows from it.
        tau = 2.0
        reading = step_response(self._first_order(tau), "X")
        assert RISE_LOW_FRACTION == 0.1 and RISE_HIGH_FRACTION == 0.9
        assert reading.rise_time == pytest.approx(tau * math.log(9.0), rel=1e-4)

    def test_a_first_order_settling_time_is_tau_ln_fifty(self) -> None:
        tau = 2.0
        reading = step_response(self._first_order(tau), "X")
        assert SETTLING_BAND == 0.02
        assert reading.settling_time == pytest.approx(
            tau * math.log(1.0 / SETTLING_BAND), rel=1e-4
        )

    def test_a_first_order_step_does_not_overshoot(self) -> None:
        reading = step_response(self._first_order(), "X")
        assert reading.overshoot == 0.0
        assert reading.settled
        assert "No overshoot" in reading.summary()

    def _second_order(self, zeta: float = 0.5, omega: float = 1.0) -> Series:
        damped = omega * math.sqrt(1.0 - zeta * zeta)
        times = np.linspace(0.0, 40.0, 40001)
        values = 1.0 - np.exp(-zeta * omega * times) * (
            np.cos(damped * times)
            + (zeta / math.sqrt(1.0 - zeta * zeta)) * np.sin(damped * times)
        )
        return Series.of(times, values, "X")

    def test_an_underdamped_overshoot_is_exp_minus_pi_zeta_over_root(self) -> None:
        """The textbook identity, and it is exact.

        A second-order step response overshoots by
        exp(-pi*zeta/sqrt(1-zeta^2)) and peaks at pi/omega_d. Nothing about
        either is empirical, which is what makes them worth testing against.
        """
        zeta, omega = 0.5, 1.0
        reading = step_response(self._second_order(zeta, omega), "X")
        assert reading.overshoot == pytest.approx(
            math.exp(-math.pi * zeta / math.sqrt(1.0 - zeta * zeta)), rel=1e-4
        )
        assert reading.time_to_peak == pytest.approx(
            math.pi / (omega * math.sqrt(1.0 - zeta * zeta)), rel=1e-3
        )

    def test_the_settling_time_is_inside_the_envelope_that_bounds_it(self) -> None:
        # |y - 1| <= exp(-zeta*omega*t)/sqrt(1-zeta^2), so once that falls
        # under the band the response is inside it forever. The settling
        # time cannot exceed where the envelope crosses, and must exceed the
        # rise time.
        zeta, omega = 0.5, 1.0
        reading = step_response(self._second_order(zeta, omega), "X")
        bound = -math.log(SETTLING_BAND * math.sqrt(1.0 - zeta * zeta)) / (
            zeta * omega
        )
        assert reading.settling_time is not None
        assert reading.rise_time < reading.settling_time < bound

    def test_a_falling_step_is_read_the_same_way(self) -> None:
        times = np.asarray(self._second_order().times)
        falling = 5.0 - np.asarray(self._second_order().columns["X"])
        reading = step_response(Series.of(times, falling, "X"), "X")
        assert reading.direction == "falling"
        assert reading.overshoot == pytest.approx(
            math.exp(-math.pi * 0.5 / math.sqrt(0.75)), rel=1e-4
        )

    def test_a_signal_that_ends_where_it_started_is_refused_toward_adaptation(
        self,
    ) -> None:
        """The refusal names the reading that WOULD work.

        Every step-response number is a fraction of the change, and with no
        change they are undefined rather than small. A signal that leaves
        its baseline and comes back is a pulse, and there is a function for
        that.
        """
        times = np.linspace(0.0, 100.0, 10001)
        values = OFFSET + (np.exp(-times / 10.0) - np.exp(-times / 1.0))
        with pytest.raises(TimeSeriesRefused) as caught:
            step_response(Series.of(times, values, "X"), "X")
        message = str(caught.value)
        assert "no step to characterise" in message
        assert "adaptation" in message
        assert "came back" in message


class TestSampling:
    def test_an_uneven_grid_is_refused_with_the_reason(self) -> None:
        """The autocorrelation is indexed by lag, and a lag is not a time.

        On an uneven grid the lag of best match has no time attached to it,
        and multiplying it by a mean interval produces a confident wrong
        period. Refusing is the only honest option and the message says why.
        """
        times = np.concatenate(
            [np.linspace(0.0, 20.0, 201), np.linspace(20.1, 60.0, 200)]
        )
        values = OFFSET + AMPLITUDE * np.sin(2.0 * np.pi * times / PERIOD)
        with pytest.raises(TimeSeriesRefused) as caught:
            oscillation(Series.of(times, values, "X"), "X")
        assert "not evenly spaced" in str(caught.value)
        assert "lag index" in str(caught.value)

    def test_times_that_do_not_increase_are_refused(self) -> None:
        with pytest.raises(TimeSeriesRefused, match="do not increase"):
            sample_spacing([0.0, 1.0, 0.5, 2.0])

    def test_a_uniform_grid_returns_its_one_interval(self) -> None:
        assert sample_spacing(np.linspace(0.0, 10.0, 101)) == pytest.approx(0.1)


class TestReading:
    def test_an_unknown_species_is_refused_with_the_list(self) -> None:
        with pytest.raises(TimeSeriesRefused) as caught:
            read(sine(), "not_here")
        assert "no series named 'not_here'" in str(caught.value)
        assert "X" in str(caught.value)

    def test_a_window_past_the_end_of_the_run_is_refused(self) -> None:
        with pytest.raises(TimeSeriesRefused, match="no sample at or after"):
            read(sine(), "X", after=1e6)

    def test_after_keeps_only_what_was_asked_for(self) -> None:
        times, values = read(sine(), "X", after=10.0)
        assert min(times) >= 10.0
        assert len(times) == len(values)

    def test_a_series_of_mismatched_lengths_is_refused(self) -> None:
        with pytest.raises(TimeSeriesRefused, match="one value per time"):
            Series.of([0.0, 1.0, 2.0], [0.0, 1.0])

    def test_something_that_is_not_a_trajectory_is_refused(self) -> None:
        with pytest.raises(TimeSeriesRefused, match="carries no"):
            read(object(), "X")

    def test_a_column_shorter_than_the_times_is_refused_not_truncated(self) -> None:
        """`zip` would have taken the shorter of the two without a word.

        The window would then end early and every reading below -- period,
        settling time, adaptation fraction -- would be about a window the
        caller did not ask for.
        """
        ragged = type(
            "Ragged", (), {"times": (0.0, 1.0, 2.0), "columns": {"X": (0.0, 1.0)}}
        )()
        with pytest.raises(TimeSeriesRefused, match="quietly ended early"):
            read(ragged, "X")


def repressilator(hill: float):
    """The composed three-gene ring, integrated, at a stated cooperativity.

    The Hill coefficient is one of `model.chosen` -- yours to set. Nothing in
    the library supplies it, and this asserts that before changing it, so a
    day when it becomes a resolvable quantity fails here rather than having
    a test quietly overwrite a measurement.
    """
    pytest.importorskip("roadrunner", reason="the time course needs the engine")
    from dataclasses import replace

    from Terium.compose.pipeline import compose
    from Terium.compose.simulate import run

    model = compose("repressilator")
    assert all(
        f"gene{index}_n" in model.chosen for index in (1, 2, 3)
    ), "the cooperativity is the caller's to set, not a measurement"
    network = replace(
        model.network,
        parameters=tuple(
            replace(parameter, value=hill)
            if parameter.id.endswith("_n")
            else parameter
            for parameter in model.network.parameters
        ),
    )
    return run(replace(model, network=network), end=600.0, points=3001)


class TestTheRepressilator:
    """The one test that integrates, because a reading of nothing is nothing.

    The library's illustrative Hill coefficient is 2, and at 2 this ring
    does not sustain an oscillation -- measured below, it decays. The
    coefficient is a CHOSEN parameter, one of `model.chosen`: no paper
    supplies the cooperativity of a mechanism nobody has named an organism
    for, so setting it is a decision the caller makes and this test makes it
    explicitly rather than borrowing a number from anywhere.
    """

    HILL = 4.0

    @pytest.fixture(scope="class")
    def oscillating(self):
        # Class-scoped: three tests want the same 3001-point run and it
        # costs a model build, an Antimony compile and an integration.
        return repressilator(self.HILL)

    def test_both_methods_agree_on_the_period_of_the_limit_cycle(
        self, oscillating
    ) -> None:
        """The point of measuring twice, on something nobody wrote down.

        There is no closed form for this period. What there is, is two
        estimators that share nothing below the samples: one reading the
        times the signal crosses its own mean, one matching the whole record
        against a shifted copy of itself. Agreement between them is
        evidence; a single number from a single method would be an
        assertion.
        """
        reading = oscillation(oscillating, "gene1_X", after=200.0)
        assert reading.methods_agree
        assert reading.disagreement < 1e-3
        assert reading.period_by_crossings == pytest.approx(
            reading.period_by_autocorrelation, rel=1e-3
        )
        assert reading.cycles >= MINIMUM_CYCLES

    def test_the_three_genes_share_one_period(self, oscillating) -> None:
        # A ring of three identical genes has one frequency. If the readings
        # disagreed between species the reading would be wrong, because the
        # model cannot be.
        periods = [
            oscillation(oscillating, f"gene{index}_X", after=200.0).period
            for index in (1, 2, 3)
        ]
        assert periods[0] == pytest.approx(periods[1], rel=1e-4)
        assert periods[0] == pytest.approx(periods[2], rel=1e-4)

    def test_after_the_transient_it_is_sustained_and_before_it_grows(
        self, oscillating
    ) -> None:
        """Both verdicts are correct and they are about different windows.

        The run starts away from the limit cycle and spirals out onto it, so
        over the whole window the envelope grows -- which is a true statement
        about the approach and a false one about the attractor. Reading the
        window after the transient gives the attractor. This is what `after`
        is for, and why a period averaged over both would be the period of
        neither.
        """
        settled = oscillation(oscillating, "gene1_X", after=200.0)
        assert settled.damping is not None
        assert settled.damping.verdict == SUSTAINED

        whole = oscillation(oscillating, "gene1_X")
        assert whole.damping is not None
        assert whole.damping.verdict == GROWING

    def test_damping_reads_a_real_trajectory_directly(self, oscillating) -> None:
        # `damping` on a `Trajectory` rather than a written-down array, with
        # the cycle length taken from the peaks. The same verdict the full
        # reading gives, by a path that does not compute a period at all.
        envelope = damping(oscillating, "gene1_X", after=200.0)
        assert envelope.verdict == SUSTAINED
        assert envelope.per_cycle_ratio == pytest.approx(1.0, abs=1e-3)
        assert envelope.excursions >= 2

    def test_the_illustrative_cooperativity_gives_a_damped_oscillation(self) -> None:
        # The library's own value, unchanged. It decays, and the two methods
        # disagree about its period -- which is the correct report: a signal
        # losing 40% of its swing every cycle does not have one.
        trajectory = repressilator(2.0)
        reading = oscillation(trajectory, "gene1_X")
        assert reading.damping is not None
        assert reading.damping.verdict == DECAYING
        assert reading.damping.per_cycle_ratio < 1.0 - SETTLING_BAND
        assert not reading.methods_agree
