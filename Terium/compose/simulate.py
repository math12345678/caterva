"""Running a composed model, and refusing to run one that would mislead.

WHAT THIS ADDS OVER `terium_engine.simulate_sbml`
-------------------------------------------------
The engine integrates whatever it is given. A composed model arrives with
things the engine cannot know and a reader needs: which constants are the
library's illustrative values rather than measurements, what timescale the
system actually settles on, and whether the conservation laws survived the
integration.

That last one is a real check and nothing else performs it. A conservation
law is exact: it is the left null space of the stoichiometry matrix over
rationals, and the integrator has no idea it exists. If total protein drifts
by 3% over the run, the trajectory is wrong -- a tolerance too loose, a
stiff system integrated explicitly -- and the plot looks completely normal.
Checking the invariant after the fact is the cheapest error detector
available and it is free, because the invariant was already derived.

CHOOSING A WINDOW
-----------------
`end=10` is the usual default and it is a guess about a system nobody has
looked at. `analysis.py` computes the slowest eigenvalue at the steady
state, whose reciprocal is the settling time; a window of a few multiples of
that shows the whole approach. When the analysis is available the window is
derived from it and the report says so; when it is not, the default is used
and the report says THAT.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: How many settling times to run for, when the settling time is known.
#:
#: Three covers 95% of the approach for a single exponential and five covers
#: 99%. Four is the compromise, stated rather than hidden: a window too
#: short cuts off the interesting part, and one too long spends every pixel
#: on a flat line.
SETTLING_MULTIPLES = 4.0

#: Used when nothing is known about the timescale. A guess, and labelled as
#: one wherever it is used.
FALLBACK_END = 10.0

DEFAULT_POINTS = 201

#: A conservation law that drifts by more than this FRACTION over the run is
#: reported. Loose enough not to fire on ordinary integrator noise, tight
#: enough that a real failure shows: a 1% drift in total protein is not
#: rounding, it is the wrong answer.
CONSERVATION_DRIFT_TOLERANCE = 1e-3


class SimulationRefused(RuntimeError):
    """The model was not run, and the reason is the message."""


@dataclass(frozen=True)
class InvariantCheck:
    """What happened to a conservation law during the integration."""

    law: str
    initial: float
    final: float
    worst_drift: float

    @property
    def held(self) -> bool:
        scale = max(abs(self.initial), 1e-12)
        return self.worst_drift / scale <= CONSERVATION_DRIFT_TOLERANCE

    def describe(self) -> str:
        scale = max(abs(self.initial), 1e-12)
        relative = self.worst_drift / scale
        if self.held:
            return f"`{self.law}` held to {relative:.2e}"
        return (
            f"`{self.law}` DRIFTED by {relative:.2%} (from {self.initial:.6g} "
            f"to {self.final:.6g}). This law is exact -- it is the left null "
            f"space of the stoichiometry over rationals -- so the drift is "
            f"the integrator's, not the model's. The trajectory is wrong by "
            f"at least that much and looks completely normal."
        )


@dataclass(frozen=True)
class Trajectory:
    """A time course, with everything needed to read it honestly."""

    times: Tuple[float, ...]
    columns: Mapping[str, Tuple[float, ...]]
    end: float
    points: int
    #: Where the window came from: the settling time, or the fallback.
    window_basis: str
    invariants: Tuple[InvariantCheck, ...] = ()
    #: Constants that were the motif library's illustrative values.
    unmeasured: Tuple[str, ...] = ()

    @property
    def sound(self) -> bool:
        return all(check.held for check in self.invariants)

    def final_state(self) -> Dict[str, float]:
        return {name: values[-1] for name, values in self.columns.items()}

    def summary(self) -> str:
        lines = [
            f"Integrated to t={self.end:.4g} in {self.points} points "
            f"({self.window_basis})."
        ]
        final = self.final_state()
        lines.append(
            "Final state: "
            + ", ".join(f"{name}={value:.4g}" for name, value in sorted(final.items()))
            + "."
        )

        if self.invariants:
            broken = [check for check in self.invariants if not check.held]
            if broken:
                lines.append(
                    f"**{len(broken)} conservation law(s) did not hold.** "
                    + " ".join(check.describe() for check in broken)
                )
            else:
                lines.append(
                    f"All {len(self.invariants)} conservation law(s) survived "
                    f"the integration: "
                    + "; ".join(check.describe() for check in self.invariants)
                    + ". The integrator does not know these exist, so this is "
                    "an independent check that the numbers are right."
                )

        if self.unmeasured:
            lines.append(
                f"{len(self.unmeasured)} of these constants are the motif "
                f"library's illustrative values, not measurements: "
                + ", ".join(self.unmeasured[:6])
                + ("..." if len(self.unmeasured) > 6 else "")
                + ". The SHAPE of this curve is a property of the mechanism; "
                "its scale is a property of numbers nobody measured."
            )
        return " ".join(lines)


def choose_window(network: Any, requested: Optional[float] = None) -> Tuple[float, str]:
    """(end time, why). Derived from the settling time when it can be."""
    if requested is not None:
        return float(requested), "window given by the caller"

    try:
        from .analysis import analyse
    except ImportError:  # pragma: no cover - flat import
        from analysis import analyse  # type: ignore[no-redef]

    try:
        report = analyse(network, starts_per_species=4)
    except Exception:  # noqa: BLE001 - a failed analysis is not a failed run
        return FALLBACK_END, (
            f"default window; the steady-state analysis did not run, so the "
            f"timescale is unknown and {FALLBACK_END:g} is a guess"
        )

    timescales = [
        point.slowest_timescale
        for point in report.physical_points
        if point.stable and point.slowest_timescale is not None
    ]
    if not timescales:
        return FALLBACK_END, (
            f"default window; no stable steady state with a defined timescale "
            f"was found, so {FALLBACK_END:g} is a guess rather than a "
            f"derivation"
        )

    slowest = max(timescales)
    end = SETTLING_MULTIPLES * slowest
    return end, (
        f"{SETTLING_MULTIPLES:g} x the slowest settling time ({slowest:.3g}), "
        f"derived from the Jacobian's smallest non-zero eigenvalue"
    )


def check_invariants(network: Any, columns: Mapping[str, Sequence[float]]) -> Tuple[InvariantCheck, ...]:
    """Did the conservation laws survive the integration?

    Free, because the laws were already derived, and the only independent
    check on the trajectory available without a second integrator.
    """
    try:
        from Terium.core.network import describe_conservation_laws
    except ImportError:  # pragma: no cover
        from core.network import describe_conservation_laws  # type: ignore

    try:
        laws = network.conservation_laws()
        described = list(describe_conservation_laws(network))
    except Exception:  # noqa: BLE001
        return ()

    checks: List[InvariantCheck] = []
    for law, text in zip(laws, described):
        series: List[float] = []
        length = len(next(iter(columns.values()))) if columns else 0
        for index in range(length):
            total = 0.0
            usable = True
            for name, coefficient in law.items():
                if name not in columns:
                    usable = False
                    break
                total += float(coefficient) * columns[name][index]
            if not usable:
                break
            series.append(total)
        if len(series) < 2:
            continue
        initial = series[0]
        worst = max(abs(value - initial) for value in series)
        checks.append(
            InvariantCheck(
                law=text, initial=initial, final=series[-1], worst_drift=worst,
            )
        )
    return tuple(checks)


def run(
    model: Any,
    *,
    end: Optional[float] = None,
    points: int = DEFAULT_POINTS,
    start: float = 0.0,
) -> Trajectory:
    """Integrate a `ComposedModel`, checking what the engine cannot.

    Refuses on a dimensional error rather than integrating: a rate law whose
    units do not balance produces a smooth curve that is wrong by an unknown
    factor, and there is no later point at which that becomes visible.
    """
    findings = model.recognition.composition.unit_findings()
    blocking = [f for f in findings if f.severity == "blocking"]
    if blocking:
        raise SimulationRefused(
            f"{len(blocking)} rate law(s) do not balance dimensionally, so "
            f"integrating would produce a curve that is wrong by an unknown "
            f"factor and looks normal: "
            + "; ".join(f.detail for f in blocking)
        )

    network = model.network
    problems = network.problems()
    if problems:
        raise SimulationRefused(
            "the network is not well posed: " + "; ".join(problems)
        )

    window, basis = choose_window(network, end)

    # `terium_engine` sits inside the Terium package but is imported flat by
    # everything that has the package directory on its path. Both spellings
    # are tried rather than assuming a layout, because this module is
    # reached from the CLI, from the API runner and from a test, and those
    # three do not agree about sys.path.
    terium_engine = None
    for attempt in ("Terium.terium_engine", "terium_engine"):
        try:
            terium_engine = __import__(attempt, fromlist=["*"])
            break
        except ImportError:
            continue
    if terium_engine is None:
        raise SimulationRefused(
            "the simulation engine is not importable here. Structure, "
            "dimensions, conservation laws and steady states are all "
            "available without it; only the time course needs it."
        )

    try:
        from Terium.core.network import compile_to_antimony
    except ImportError:  # pragma: no cover
        from core.network import compile_to_antimony  # type: ignore

    antimony = compile_to_antimony(network)
    sbml = terium_engine.antimony_to_sbml(antimony)
    result = terium_engine.simulate_sbml(
        sbml_string=sbml, start=start, end=window, points=points,
    )

    times, columns = _extract(result, network)
    return Trajectory(
        times=times,
        columns=columns,
        end=window,
        points=points,
        window_basis=basis,
        invariants=check_invariants(network, columns),
        unmeasured=tuple(
            quantity.parameter_id for quantity in model.resolvable
        ) if model.structure_only else (),
    )


def _extract(result: Any, network: Any) -> Tuple[Tuple[float, ...], Dict[str, Tuple[float, ...]]]:
    """Pull times and species columns out of whatever the engine returned.

    Tolerant of shape because the engine's result type has changed before
    and this is a consumer, not the contract. It raises rather than guessing
    when it cannot find the times: a trajectory whose x-axis was invented
    would be worse than no trajectory.
    """
    times = getattr(result, "time", None)
    if times is None:
        times = getattr(result, "times", None)
    if times is None and isinstance(result, dict):
        times = result.get("time") or result.get("times")
    if times is None:
        raise SimulationRefused(
            "the engine's result carries no time column under any name this "
            "reader knows, and inventing one would be worse than failing"
        )

    # `SimulationResult` carries `colnames` and a row-major `data` table
    # whose first column is time. Read through the NAMES rather than by
    # position: the engine has reordered columns before, and a positional
    # read would silently attribute one species' trajectory to another --
    # a plot that is completely wrong and completely plausible.
    columns: Dict[str, Tuple[float, ...]] = {}
    colnames = getattr(result, "colnames", None)
    data = getattr(result, "data", None)

    if colnames and data:
        index_of = {name: position for position, name in enumerate(colnames)}
        for species in network.species:
            position = None
            for key in (species.id, f"[{species.id}]"):
                if key in index_of:
                    position = index_of[key]
                    break
            if position is None:
                continue
            columns[species.id] = tuple(float(row[position]) for row in data)
    else:
        # An older or different result shape: attributes named per species.
        for species in network.species:
            values = None
            for key in (species.id, f"[{species.id}]"):
                values = getattr(result, key, None)
                if values is None and isinstance(result, dict):
                    values = result.get(key)
                if values is not None:
                    break
            if values is not None:
                columns[species.id] = tuple(float(v) for v in values)

    # A species the engine gave no column for is one of two things, and
    # they need opposite treatment.
    #
    # If it appears in NO reaction's stoichiometry it is a modifier -- an
    # enzyme, a phosphatase -- and it is constant BY CONSTRUCTION. Its
    # trajectory is a flat line at its initial value, and that is derived
    # from the model's structure rather than measured by the integrator, so
    # filling it in is exact rather than a guess. Antimony omits these
    # because nothing changes them, which is correct of Antimony and
    # unhelpful to a reader who asked for the whole system.
    #
    # If it DOES appear in a stoichiometry and has no column, something is
    # wrong and a trajectory with a species silently absent would let a
    # reader believe they had seen everything.
    changed = set()
    for reaction in network.reactions:
        changed.update(reaction.reactants)
        changed.update(reaction.products)
    for rule in getattr(network, "rate_rules", ()):
        changed.add(getattr(rule, "target", None))

    constant: List[str] = []
    for species in network.species:
        if species.id in columns:
            continue
        if species.id in changed:
            continue
        columns[species.id] = tuple(
            float(species.initial) for _ in range(len(times))
        )
        constant.append(species.id)

    missing = [s.id for s in network.species if s.id not in columns]
    if missing:
        raise SimulationRefused(
            f"the engine returned no column for {', '.join(missing)}, and "
            f"{'that species appears' if len(missing) == 1 else 'those species appear'} "
            f"in a reaction's stoichiometry, so {'it is' if len(missing) == 1 else 'they are'} "
            f"not constant. Reporting a trajectory with a species silently "
            f"absent would let a reader believe they had seen the whole "
            f"system. Columns present: {', '.join(colnames or []) or 'none'}."
        )

    return tuple(float(t) for t in times), columns


__all__ = [
    "Trajectory", "InvariantCheck", "SimulationRefused",
    "run", "choose_window", "check_invariants",
    "SETTLING_MULTIPLES", "FALLBACK_END", "DEFAULT_POINTS",
    "CONSERVATION_DRIFT_TOLERANCE",
]
