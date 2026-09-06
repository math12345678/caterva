"""How much does the answer depend on each number?

WHY THIS EXISTS
---------------
A researcher assembling a model from literature scavenges parameters out of
several papers, measured in different organisms under different conditions.
Some of those numbers matter enormously to the conclusion and some do not
matter at all, and there is no way to tell which is which by looking at the
model. The usual way to find out is for the model to be wrong.

Terrium already knows where every number came from -- that is what
`network_provenance.py` enforces. This module supplies the other half: how
much the trajectory actually depends on each one. The two together answer a
question no existing tool answers, because no existing tool has both
halves. COPASI computes sensitivities and knows nothing about provenance;
BRENDA knows provenance and has no model.

    influence x weakness  ->  what to measure next

That product is the point. A parameter that dominates the result and came
from another organism is the weakest link in a conclusion; a parameter with
a perfect citation that the result does not depend on is not worth a
morning's work.

WHAT IS COMPUTED
----------------
Relative (logarithmic) sensitivity coefficients:

    S_ij = (dy_i / dp_j) * (p_j / y_i)

read as: a 1% change in parameter j moves species i by S_ij percent.
Dimensionless on purpose -- a Km in mM and a rate in 1/s are not otherwise
comparable, and the whole question here is comparing them.

Central differences, because a one-sided difference has first-order error
and these values get ranked against each other; an ordering produced by
truncation error is not an ordering.

THE HONEST LIMITS, STATED
-------------------------
This is LOCAL sensitivity: it describes the model in a neighbourhood of the
parameter values given, not over the range they might plausibly take. A
parameter whose true value is an order of magnitude away may behave
completely differently there. That is the standard caveat on every local
method and it is not a defect, but reporting a ranking without it would
imply a global claim this cannot support.

It is also a statement about the MODEL, not about nature. If the model's
structure is wrong, a sensitivity computed from it is a precise fact about
a wrong thing.

Both limits are carried in `SensitivityReport.caveats` so a caller cannot
print the ranking without them.
"""

from __future__ import annotations


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """See Terium/core/import_mode.py. Inlined deliberately: this
    guards the import machinery itself, so it cannot import a
    helper to do its job."""
    name = getattr(exc, "name", None)
    return bool(name) and (name == "Terium" or name.startswith("Terium."))


import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

try:
    from Terium.core.data_structures import ModelBuildError
except ModuleNotFoundError as _exc:  # flat mode: Terium/ on sys.path
    if not _package_path_missing(_exc):
        # A missing THIRD-PARTY dependency. Flat mode cannot fix it, and
        # retrying replaces the real reason with a confusing
        # 'No module named core'. See Terium/core/import_mode.py.
        raise
    from core.data_structures import ModelBuildError  # type: ignore[no-redef]

try:
    from Terium.core.network import Parameter, ReactionNetwork, Species
except ModuleNotFoundError as _exc:
    if not _package_path_missing(_exc):
        raise
    from core.network import (  # type: ignore[no-redef]
        Parameter,
        ReactionNetwork,
        Species,
    )


#: Relative step for the central difference.
#:
#: 1e-3, not the textbook cube-root-of-machine-epsilon (~6e-6). The
#: derivative here is taken through an adaptive ODE solver, so the function
#: being differenced is only accurate to its own integration tolerance
#: (1e-10 relative in this engine). A step near machine epsilon puts the
#: difference of two trajectories below the solver's own noise floor and
#: measures the integrator rather than the model.
#:
#: 1e-3 is comfortably above that noise and small enough that the O(h^2)
#: truncation error of a central difference is ~1e-6 relative -- far finer
#: than the distinctions this ranking is used to make.
DEFAULT_RELATIVE_STEP = 1e-3

#: Below this, a species is treated as absent rather than as a denominator.
#:
#: The relative sensitivity divides by y_i. A species sitting at 1e-18
#: because it has not been produced yet would otherwise generate an enormous
#: coefficient from a numerically meaningless difference. Scaled against the
#: species' own maximum over the run, so it means "negligible compared with
#: how big this species ever gets" rather than a fixed absolute cutoff.
NEGLIGIBLE_FRACTION = 1e-9


@dataclass(frozen=True)
class QuantitySensitivity:
    """How much one quantity moves the answer."""

    quantity: str
    #: Peak |relative sensitivity| over all species and all time points.
    peak: float
    #: The species and time at which that peak occurred.
    peak_species: str
    peak_time: float
    #: Per-species peak, for a caller that cares about one output.
    by_species: Dict[str, float] = field(default_factory=dict)

    @property
    def negligible(self) -> bool:
        """The answer does not measurably depend on this quantity.

        1e-6 means a 1% change in the parameter moves every species by less
        than a millionth of a percent -- indistinguishable from the
        integrator's own noise, and not worth a researcher's time.
        """
        return self.peak < 1e-6


@dataclass(frozen=True)
class SensitivityReport:
    ranked: Tuple[QuantitySensitivity, ...]
    caveats: Tuple[str, ...]

    def most_influential(self, n: int = 3) -> Tuple[QuantitySensitivity, ...]:
        return self.ranked[:n]


#: Attached to every report. A ranking printed without these implies a
#: global claim about nature; it is a local claim about a model.
STANDING_CAVEATS: Tuple[str, ...] = (
    "Local sensitivity: this describes the model near the parameter values "
    "given, not across the range they might plausibly take. A parameter "
    "whose true value is an order of magnitude away may behave differently "
    "there.",
    "A statement about the MODEL, not about nature. If the structure is "
    "wrong, these are precise facts about a wrong thing.",
)


def _perturbed(
    network: ReactionNetwork, quantity: str, value: float
) -> ReactionNetwork:
    """A copy of the network with one quantity changed.

    Species initials and parameters are both perturbable: an initial
    concentration is an experimental quantity like any other, and a
    conclusion can rest on one just as heavily.
    """
    return ReactionNetwork(
        name=network.name,
        species=tuple(
            Species(s.id, value) if s.id == quantity else s
            for s in network.species
        ),
        parameters=tuple(
            Parameter(p.id, value) if p.id == quantity else p
            for p in network.parameters
        ),
        reactions=network.reactions,
        rate_rules=network.rate_rules,
        assignment_rules=network.assignment_rules,
    )


def _value_of(network: ReactionNetwork, quantity: str) -> float:
    for s in network.species:
        if s.id == quantity:
            return float(s.initial)
    for p in network.parameters:
        if p.id == quantity:
            return float(p.value)
    raise ModelBuildError(
        f"{quantity!r} is not a species or parameter of {network.name!r}"
    )


def _columns(result) -> Dict[str, List[float]]:
    """Trajectory as species -> series, with roadrunner's brackets stripped.

    roadrunner reports a concentration as `[S]` and a rate-rule target as
    `S`. Both are the same species to a reader, and a report that listed
    them as different things would be reporting an artefact of the solver's
    output naming.
    """
    columns: Dict[str, List[float]] = {}
    for index, name in enumerate(result.colnames):
        if name == "time":
            continue
        key = name[1:-1] if name.startswith("[") and name.endswith("]") else name
        columns[key] = [float(row[index]) for row in result.data]
    return columns


def _times(result) -> List[float]:
    if "time" not in result.colnames:
        return list(range(len(result.data)))
    index = result.colnames.index("time")
    return [float(row[index]) for row in result.data]


def analyse(
    network: ReactionNetwork,
    simulate: Callable[[ReactionNetwork], object],
    quantities: Optional[Sequence[str]] = None,
    relative_step: float = DEFAULT_RELATIVE_STEP,
) -> SensitivityReport:
    """Rank a network's quantities by how much the trajectory depends on them.

    `simulate` is injected rather than imported so this module has no
    dependency on roadrunner, on the SBML round-trip, or on how a caller
    chooses to integrate. It is also what makes the whole thing testable
    against closed-form models whose true sensitivities are known by hand --
    see test_sensitivity.py, which checks the machinery against exponential
    decay, where the exact answer is derivable and this must reproduce it.

    Quantities whose value is exactly zero are reported as unmeasurable
    rather than perturbed absolutely. A relative sensitivity is not defined
    at zero, and substituting an absolute step there would put a number of
    different meaning into the same ranking.
    """
    targets = list(quantities) if quantities is not None else list(
        network.quantity_ids()
    )
    if not targets:
        return SensitivityReport(ranked=(), caveats=STANDING_CAVEATS)

    baseline = simulate(network)
    base_columns = _columns(baseline)
    times = _times(baseline)
    if not base_columns:
        raise ModelBuildError(
            f"the baseline run of {network.name!r} produced no species "
            f"columns, so nothing can be differentiated"
        )

    # Scale for each species: its own largest magnitude over the run. Used
    # as the floor below which a value is 'absent' rather than 'small'.
    scale = {
        name: max((abs(v) for v in series), default=0.0)
        for name, series in base_columns.items()
    }

    results: List[QuantitySensitivity] = []
    unmeasurable: List[str] = []

    for quantity in targets:
        value = _value_of(network, quantity)
        if value == 0.0:
            unmeasurable.append(quantity)
            continue

        step = abs(value) * relative_step
        up = _columns(simulate(_perturbed(network, quantity, value + step)))
        down = _columns(simulate(_perturbed(network, quantity, value - step)))

        by_species: Dict[str, float] = {}
        peak, peak_species, peak_time = 0.0, "", 0.0

        for name, base_series in base_columns.items():
            if name not in up or name not in down:
                continue
            floor = scale[name] * NEGLIGIBLE_FRACTION
            species_peak = 0.0
            for i, base_value in enumerate(base_series):
                if abs(base_value) <= floor:
                    # Not yet produced (or already gone). A relative
                    # sensitivity here divides by numerical noise.
                    continue
                derivative = (up[name][i] - down[name][i]) / (2.0 * step)
                relative = derivative * value / base_value
                if not math.isfinite(relative):
                    continue
                magnitude = abs(relative)
                if magnitude > species_peak:
                    species_peak = magnitude
                if magnitude > peak:
                    peak = magnitude
                    peak_species = name
                    peak_time = times[i] if i < len(times) else float(i)
            by_species[name] = species_peak

        results.append(
            QuantitySensitivity(
                quantity=quantity,
                peak=peak,
                peak_species=peak_species,
                peak_time=peak_time,
                by_species=by_species,
            )
        )

    # Descending by influence, then by name so equal values order stably --
    # a ranking that reshuffles between runs is not a ranking.
    results.sort(key=lambda r: (-r.peak, r.quantity))

    caveats = list(STANDING_CAVEATS)
    if unmeasurable:
        caveats.append(
            "Not ranked because their value is exactly zero, where a "
            "relative sensitivity is undefined: "
            + ", ".join(sorted(unmeasurable))
            + ". Give a non-zero value to include them."
        )
    return SensitivityReport(ranked=tuple(results), caveats=tuple(caveats))


__all__ = [
    "QuantitySensitivity",
    "SensitivityReport",
    "STANDING_CAVEATS",
    "DEFAULT_RELATIVE_STEP",
    "analyse",
]
