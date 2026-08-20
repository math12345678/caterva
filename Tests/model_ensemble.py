"""Run the simulation once per sampled parameter set, and report the envelope.

THE HALF THAT MAKES IT A SIMULATION
------------------------------------
`ensemble.py` turns scored literature values into a weighted sample of
PARAMETERS. That is Bakker's weighting, and on its own it produces a spread
of numbers.

Sauro's sentence is about what you do with them:

    "With Jessie's approach you don't get any simulation, with Barbara's you
     can **sample and get an ensemble distribution**. That is the right way
     to do it."

The point is not that you learn Km is uncertain. It is that you still get a
trajectory — many of them — instead of a refusal. This module runs the model
once per draw and reports what the family of runs does.

So the product changes shape. Today, a Km the literature disagrees about
either becomes one number chosen by `min()` or stops the run. After this it
becomes a band: this is what the system does across everything the
literature actually reports.

WHAT IS AND IS NOT REJECTED
---------------------------
Bakker's published ensemble rejects models that disagree with measured flux.
Terrium has no flux data and does not invent a substitute — the spread here
is still not an uncertainty estimate, and `ensemble.DISCLAIMER` still travels
with it.

There is one rejection this CAN do honestly, and it is a different kind: a
parameter set that **fails to integrate**. That is a numerical fact about the
solver, not a judgement about biology, and conflating the two would be
exactly the overreach ADR 0024 warned about. Failures are counted, reported,
and never silently dropped — an envelope drawn over 160 of 200 runs with the
other 40 unmentioned would be a quiet lie about its own support.

WHY THE TIME GRID IS FORCED
---------------------------
An envelope is only meaningful if every run is sampled at the same times. If
one run returns 51 points and another 40, "the median at t=3" is a comparison
between different quantities. So the grid is fixed once and passed to every
run, and a run that comes back on a different grid is a failure rather than
something to interpolate onto the others -- interpolating would manufacture
values no run produced, which is the same rule `ensemble.py` follows when it
resamples rather than fits.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

try:  # pragma: no cover - import shape differs between callers
    from ensemble import DISCLAIMER, EnsembleResult
except ImportError:  # pragma: no cover
    from Tests.ensemble import DISCLAIMER, EnsembleResult  # type: ignore


@dataclass(frozen=True)
class FailedRun:
    """A parameter set the solver could not integrate."""

    parameters: Mapping[str, float]
    reason: str


@dataclass(frozen=True)
class Envelope:
    """Order statistics of one output column, at each time point."""

    column: str
    times: tuple[float, ...]
    low: tuple[float, ...]
    p05: tuple[float, ...]
    median: tuple[float, ...]
    p95: tuple[float, ...]
    high: tuple[float, ...]


@dataclass(frozen=True)
class ModelEnsembleResult:
    """A family of runs, and an honest account of which ones happened."""

    envelopes: tuple[Envelope, ...]
    #: Runs that integrated. The envelope is drawn over exactly these.
    succeeded: int
    #: Runs that did not. Never silently dropped — see the module docstring.
    failed: tuple[FailedRun, ...]
    #: What was varied, and the draws that varied it.
    swept: tuple[str, ...]
    seed: int
    disclaimer: str

    @property
    def attempted(self) -> int:
        return self.succeeded + len(self.failed)

    def support_note(self) -> str:
        """One sentence a reader needs before believing the band.

        Stated always, not only on failure: "200 of 200" is information too,
        and a note that appears only when something went wrong trains a
        reader to skim past it when it matters.
        """
        if not self.failed:
            return f"The band covers all {self.succeeded} runs; none failed to integrate."
        return (
            f"The band covers {self.succeeded} of {self.attempted} runs. "
            f"{len(self.failed)} parameter set(s) could not be integrated and are "
            "excluded — a numerical failure, not a judgement about the biology."
        )


def _nearest_rank(ordered: Sequence[float], p: float) -> float:
    """Percentile without interpolation.

    Same rule as `ensemble.summary`: interpolating between two runs reports a
    trajectory value no run produced. With a handful of distinct parameter
    values the runs cluster heavily, and a smoothed percentile would invent
    the smoothness.
    """
    n = len(ordered)
    index = min(n - 1, max(0, math.ceil(p * n) - 1))
    return ordered[index]


def run_model_ensemble(
    *,
    simulate: Callable[..., object],
    base_parameters: Mapping[str, float],
    parameter_draws: Mapping[str, Sequence[float]],
    seed: int,
    max_runs: int | None = None,
) -> ModelEnsembleResult:
    """Run `simulate` once per drawn parameter set and summarise the family.

    `parameter_draws` maps a parameter name to the values drawn for it — the
    `draws` of an `EnsembleResult`. Every list must be the same length: draw
    *i* of each parameter belongs to run *i*, so that a run is one coherent
    parameter set rather than a cross-product of unrelated samples.

    That pairing matters and is easy to get wrong. Two parameters sampled
    independently and then combined arbitrarily would explore combinations no
    single source supports; keeping draw *i* together preserves whatever
    correlation the sampling produced.
    """
    if not parameter_draws:
        raise ValueError(
            "nothing to vary: an ensemble over zero sampled parameters is just "
            "one run, and calling it an ensemble would overstate it."
        )

    lengths = {name: len(values) for name, values in parameter_draws.items()}
    if len(set(lengths.values())) != 1:
        raise ValueError(
            f"parameter draws have different lengths ({lengths}). Draw i of each "
            "parameter forms run i, so unequal lengths mean the pairing is "
            "undefined."
        )
    n_draws = next(iter(lengths.values()))
    if n_draws < 1:
        raise ValueError("no draws to run")
    if max_runs is not None:
        n_draws = min(n_draws, max_runs)

    swept = tuple(sorted(parameter_draws))
    by_time: dict[str, dict[float, list[float]]] = {}
    failures: list[FailedRun] = []
    grid: tuple[float, ...] | None = None
    succeeded = 0

    for i in range(n_draws):
        params = dict(base_parameters)
        for name, values in parameter_draws.items():
            params[name] = values[i]
        try:
            result = simulate(**params)
            colnames = list(getattr(result, "colnames"))
            rows = [list(r) for r in getattr(result, "data")]
        except Exception as exc:  # noqa: BLE001 - any solver failure is a failure
            failures.append(FailedRun(parameters=params, reason=f"{type(exc).__name__}: {exc}"))
            continue

        if not rows or not colnames:
            failures.append(FailedRun(parameters=params, reason="the run produced no rows"))
            continue

        times = tuple(float(r[0]) for r in rows)
        if grid is None:
            grid = times
        elif times != grid:
            # Not interpolated onto the reference grid. See the docstring: an
            # envelope across mismatched grids compares different quantities,
            # and interpolating would manufacture values no run produced.
            failures.append(
                FailedRun(
                    parameters=params,
                    reason=(
                        f"returned {len(times)} time points, not the "
                        f"{len(grid)} the first run used"
                    ),
                )
            )
            continue

        succeeded += 1
        for col_index, name in enumerate(colnames[1:], start=1):
            column = by_time.setdefault(name, {})
            for row_index, t in enumerate(times):
                column.setdefault(t, []).append(float(rows[row_index][col_index]))

    if succeeded == 0:
        raise ValueError(
            f"every one of the {len(failures)} run(s) failed, so there is no "
            "envelope. Report the failures rather than an empty band."
        )

    assert grid is not None
    envelopes = []
    for name in sorted(by_time):
        per_time = by_time[name]
        ordered_per_time = [sorted(per_time[t]) for t in grid]
        envelopes.append(
            Envelope(
                column=name,
                times=grid,
                low=tuple(vals[0] for vals in ordered_per_time),
                p05=tuple(_nearest_rank(vals, 0.05) for vals in ordered_per_time),
                median=tuple(_nearest_rank(vals, 0.50) for vals in ordered_per_time),
                p95=tuple(_nearest_rank(vals, 0.95) for vals in ordered_per_time),
                high=tuple(vals[-1] for vals in ordered_per_time),
            )
        )

    return ModelEnsembleResult(
        envelopes=tuple(envelopes),
        succeeded=succeeded,
        failed=tuple(failures),
        swept=swept,
        seed=seed,
        disclaimer=DISCLAIMER,
    )


def ensemble_over(
    *,
    simulate: Callable[..., object],
    base_parameters: Mapping[str, float],
    parameter: str,
    drawn: EnsembleResult,
    max_runs: int | None = 200,
) -> ModelEnsembleResult:
    """Convenience: one parameter, varied by an `EnsembleResult`'s draws.

    `max_runs` defaults to 200 rather than to every draw. A parameter
    ensemble is usually drawn a few thousand times because that is cheap;
    integrating an ODE a few thousand times is not, and a student waiting a
    minute for a band that stopped changing after two hundred runs would
    reasonably conclude the tool is slow rather than thorough.

    The number actually run is reported in `attempted`, so the cap is visible
    rather than a silent truncation.
    """
    return run_model_ensemble(
        simulate=simulate,
        base_parameters=base_parameters,
        parameter_draws={parameter: drawn.draws},
        seed=drawn.seed,
        max_runs=max_runs,
    )
