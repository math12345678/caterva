"""Does the conclusion survive the numbers it was computed from?

THE QUESTION THIS ANSWERS, AND WHY THE REST OF THE MODULE NEEDS IT
------------------------------------------------------------------
`compose/` builds a model from a description of its mechanism, fills the rate
constants with the motif library's illustrative values because nobody named an
enzyme, and then reports what the model does: this toggle switch is bistable,
this cascade saturates, this system oscillates with period 43.

Every report already carries the caveat that those conclusions are about the
model's SHAPE rather than about any real system. That caveat is honest and it
is also unquantified, which makes it easy to skim past. A reader wants to know
something sharper: is bistability a property of the MECHANISM, or of the
particular twelve numbers that happened to be in the library?

Those are different claims and only one of them is worth publishing. A toggle
switch that is bistable across four decades of every constant is telling you
something about toggle switches. One that is bistable only within a factor of
two of the library's defaults is telling you about the library.

WHAT IT DOES
------------
Samples the parameter space, re-runs the analysis at each sample, and reports
the FRACTION of samples where the conclusion still holds. That is all. It is
a counting exercise over a stated distribution, and its whole value is that
the distribution is stated rather than implied.

WHAT IT IS NOT
--------------
It is not a probability. "Bistable in 78 of 100 samples" is a statement about
this sampling of this box, not "78% likely to be bistable". Turning a sample
frequency into a probability would require the box to be a prior, and it is
not one -- it is a stated range chosen for want of anything better, and
`SPREAD_DECADES` says so in its own comment.

It is not a proof either way. A conclusion that survives every sample may fail
just outside the box; one that fails most samples may hold precisely where the
real enzyme sits. The report gives the count, the box, and the seed, and
declines to summarise those into a verdict.

WHY LOG-UNIFORM, WHICH IS A REAL CHOICE AND NOT A DEFAULT
----------------------------------------------------------
Rate constants span decades. A kcat is somewhere between 1e-2 and 1e6 per
second across known enzymes, and a linear sample around a placeholder of 100
would spend almost all its draws within a factor of two of it -- exploring
nothing. Sampling uniformly in the LOGARITHM treats "ten times larger" and
"ten times smaller" as equally interesting, which is how these constants
actually vary and how anyone reading a Lineweaver-Burk plot already thinks.

The cost is stated: a log-uniform box cannot represent a parameter genuinely
known to lie near zero, and it never samples zero at all. A parameter whose
placeholder IS zero is skipped rather than sampled, because the logarithm of
zero is not a number and pretending otherwise would silently replace the
model's structure with a different one.

CONCENTRATIONS ARE NOT SAMPLED BY DEFAULT, AND THAT IS THE POINT
-----------------------------------------------------------------
The library's rate constants are placeholders standing in for measurements
nobody has made. Its concentrations are the USER'S SCENARIO -- the amount of
enzyme they intend to add, the substrate they intend to start with. Varying
those answers a different question ("would this work at another dose?") and
mixing the two would make the headline number mean neither.

`vary` defaults to the resolvable parameters only. Pass concentrations
explicitly to ask the dose question, and the report says which set it varied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple,
)

#: How far either side of a placeholder to sample, in powers of ten.
#:
#: A STATED CHOICE, not a measurement, and the number most worth arguing
#: with in this module. One decade either side spans a hundredfold range,
#: which is roughly the spread of kcat values reported for the SAME enzyme
#: across organisms and conditions -- wide enough that surviving it means
#: something, narrow enough that the samples are still recognisably the
#: mechanism the reader asked about.
#:
#: Three decades would make almost every conclusion fail and the report
#: useless; a factor of two would make almost every conclusion survive and
#: the report equally useless. Both failure modes produce a number that
#: looks like evidence, which is why this constant is named and reported
#: rather than buried in a call.
SPREAD_DECADES = 1.0

#: How many samples, when the caller does not say.
#:
#: MEASURED, in the sense that matters here: the sampling error on a
#: fraction p from n draws is about sqrt(p(1-p)/n), so 200 samples put a
#: fraction near one half within about +/-3.5 percentage points. That is
#: finer than the difference anyone should read into this number, and
#: doubling it would halve nothing worth halving while doubling a run that
#: already costs a full steady-state search per sample.
DEFAULT_SAMPLES = 200

#: A conclusion holding in every sample is reported as "every sample", never
#: as "always". This constant exists so the distinction has a name: there is
#: no number of samples that turns a frequency into a guarantee, which is
#: the same rule `analysis.py` applies to its multistart search.
NEVER_CLAIM_ALWAYS = True


class RobustnessError(RuntimeError):
    """The sampling could not be set up, as distinct from finding nothing."""


@dataclass(frozen=True)
class Sample:
    """One draw, and what the conclusion said about it."""

    #: parameter id -> the value used in this draw
    values: Mapping[str, float]
    #: What the conclusion returned. `None` when it could not be evaluated,
    #: which is kept distinct from False: "the analysis failed here" and
    #: "the conclusion is false here" are different facts and averaging them
    #: together would quietly convert solver trouble into evidence.
    held: Optional[bool]
    #: Why it could not be evaluated, when it could not.
    reason: str = ""


@dataclass(frozen=True)
class RobustnessReport:
    """How often a conclusion survived, over a stated box."""

    conclusion: str
    samples: Tuple[Sample, ...]
    #: Which parameters were varied. Reported because "robust" means nothing
    #: without saying robust to WHAT -- a model can be robust to every rate
    #: constant and collapse under a change of enzyme concentration.
    varied: Tuple[str, ...]
    spread_decades: float
    seed: int
    #: Parameters that were left fixed, with the reason. A zero-valued
    #: placeholder cannot be sampled log-uniformly and is listed here rather
    #: than silently dropped.
    fixed: Mapping[str, str] = field(default_factory=dict)
    #: Starting points per species each draw was judged at, or None when
    #: the conclusion does not run a steady-state search.
    #:
    #: REPORTED BECAUSE THE FRACTION IS MEANINGLESS WITHOUT IT. A conclusion
    #: about how many stable states exist is an answer from a search, and a
    #: shallower search finds fewer. This module's docstring says its whole
    #: value is that the distribution is stated rather than implied; the
    #: search depth was the one term in that contract left unstated, and a
    #: caller that chose its conclusion from a different depth produced a
    #: fraction that was partly a measure of the two searches disagreeing.
    starts_per_species: Optional[int] = None
    #: Whether the conclusion held at the model's OWN values -- the centre
    #: of the box every draw perturbs around. None when evaluating it there
    #: raised.
    #:
    #: A fraction built around a centre where the conclusion is FALSE is
    #: not a measure of robustness. It is the rate at which a random
    #: perturbation moved the model into a regime it was not in, which is
    #: a different quantity wearing the same percentage sign.
    held_at_centre: Optional[bool] = None

    @property
    def evaluated(self) -> Tuple[Sample, ...]:
        return tuple(s for s in self.samples if s.held is not None)

    @property
    def failed(self) -> Tuple[Sample, ...]:
        return tuple(s for s in self.samples if s.held is None)

    @property
    def held_count(self) -> int:
        return sum(1 for s in self.evaluated if s.held)

    @property
    def fraction(self) -> Optional[float]:
        """Held / evaluated, or `None` when nothing could be evaluated.

        Deliberately NOT held / total. A run where the solver failed on half
        the draws has a fraction over the half it managed, and the count of
        failures is reported alongside so the reader can discount it. Hiding
        failures in the denominator would make a struggling solver look like
        a fragile mechanism.
        """
        evaluated = self.evaluated
        if not evaluated:
            return None
        return self.held_count / len(evaluated)

    @property
    def uncertainty(self) -> Optional[float]:
        """One standard error on `fraction`, from the binomial.

        sqrt(p(1-p)/n). Reported so that a difference between 0.71 and 0.74
        is visibly not a difference. It is the sampling error only, and says
        nothing about whether the box was the right box -- which is the
        larger uncertainty and is not quantifiable here at all.
        """
        fraction = self.fraction
        if fraction is None:
            return None
        n = len(self.evaluated)
        return math.sqrt(max(fraction * (1.0 - fraction), 0.0) / n)

    def describe_fraction(self) -> str:
        fraction = self.fraction
        if fraction is None:
            return "no sample could be evaluated"
        n = len(self.evaluated)
        if self.held_count == n:
            return f"every one of the {n} sample(s) evaluated"
        if self.held_count == 0:
            return f"none of the {n} sample(s) evaluated"
        return (
            f"{self.held_count} of {n} sample(s), "
            f"{fraction:.0%} +/- {self.uncertainty:.0%}"
        )

    def summary(self) -> str:
        lines = [
            f"'{self.conclusion}' held in {self.describe_fraction()}, "
            f"with {len(self.varied)} parameter(s) varied log-uniformly "
            f"over +/-{self.spread_decades:g} decade(s) around the model's "
            f"current values (seed {self.seed})."
        ]

        if self.held_at_centre is False:
            lines.append(
                f"WARNING: '{self.conclusion}' is FALSE at the model's own "
                f"values, which is the centre of the box every draw "
                f"perturbs around. The figure above is therefore not a "
                f"measure of how robust this conclusion is -- it is the "
                f"rate at which a random perturbation moved the model into "
                f"a regime it was not in to begin with. If that is the "
                f"question you meant to ask, the number stands; if the "
                f"conclusion was chosen from an earlier analysis, that "
                f"analysis and this one disagree and the disagreement is "
                f"the finding."
            )
        elif self.held_at_centre is None:
            lines.append(
                "The conclusion could not be evaluated at the model's own "
                "values, so whether the box is centred on a region where it "
                "holds is UNKNOWN -- which is not the same as centred well."
            )

        if self.starts_per_species is not None:
            lines.append(
                f"Every draw was judged by a steady-state search from "
                f"{self.starts_per_species} starting point(s) per species. "
                f"A conclusion about how many stable states exist is an "
                f"answer from a search, and a shallower one finds fewer -- "
                f"so a fraction produced at one depth cannot be compared "
                f"against a headline produced at another."
            )

        if self.failed:
            lines.append(
                f"{len(self.failed)} sample(s) could not be evaluated and are "
                f"excluded from the fraction rather than counted against the "
                f"conclusion -- 'the analysis failed here' and 'the "
                f"conclusion is false here' are different facts. "
                + f"First reason: {self.failed[0].reason}"
            )

        if self.fixed:
            lines.append(
                f"{len(self.fixed)} parameter(s) were held fixed: "
                + "; ".join(f"{k} ({v})" for k, v in sorted(self.fixed.items()))
                + "."
            )

        lines.append(
            "This is a count over a stated box, not a probability. The box "
            "is a range chosen for want of a measured one, so surviving it "
            "is evidence about the mechanism and failing it is evidence "
            "about how much the answer rests on numbers nobody has measured "
            "-- neither is a proof, and a conclusion that survives every "
            "sample here may still fail just outside."
        )
        return " ".join(lines)


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def _sample_values(
    base: Mapping[str, float],
    names: Sequence[str],
    spread_decades: float,
    count: int,
    seed: int,
) -> List[Dict[str, float]]:
    """Deterministic log-uniform draws around `base`.

    A local linear congruential sequence rather than `random`, for the same
    reason `analysis.py` uses one: a robustness figure that changed between
    runs of the same model could not be cited, and seeding the global module
    would make this function's output depend on whatever else ran first.
    """
    state = (seed * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)

    def next_fraction() -> float:
        nonlocal state
        state = (state * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        return ((state >> 11) & ((1 << 53) - 1)) / float(1 << 53)

    draws: List[Dict[str, float]] = []
    for _ in range(count):
        values: Dict[str, float] = {}
        for name in names:
            exponent = (2.0 * next_fraction() - 1.0) * spread_decades
            values[name] = base[name] * (10.0 ** exponent)
        draws.append(values)
    return draws


def _with_values(network: Any, values: Mapping[str, float]) -> Any:
    """A network with parameters AND species initials taken from `values`.

    Both, because a concentration in a composed model is a SPECIES INITIAL
    and not a parameter -- `core.network.Parameter` holds rate constants and
    affinities, and the amounts a user chooses live on the species. An
    earlier version varied only parameters, which made
    `include_concentrations=True` silently identical to leaving it False:
    the dose question was offered and never asked.
    """
    from dataclasses import replace

    return replace(
        network,
        parameters=tuple(
            replace(p, value=float(values[p.id])) if p.id in values else p
            for p in network.parameters
        ),
        species=tuple(
            replace(sp, initial=float(values[sp.id])) if sp.id in values else sp
            for sp in network.species
        ),
    )


def _resolvable_ids(model: Any) -> Tuple[str, ...]:
    """The constants still unmeasured, from either model class.

    Read `unmeasured` rather than `resolvable`: a ProvenancedModel has no
    `resolvable` attribute, so `assess_model` on a partly-measured model
    used to find nothing to vary and refuse -- when the point of a partly
    measured model is that some constants are still placeholders and those
    are exactly what the placeholder question is about.
    """
    return tuple(getattr(model, "unmeasured", ()) or ())


def assess(
    network: Any,
    conclusion: Callable[[Any], bool],
    *,
    conclusion_name: str = "the conclusion",
    vary: Optional[Sequence[str]] = None,
    samples: int = DEFAULT_SAMPLES,
    spread_decades: float = SPREAD_DECADES,
    seed: int = 0,
    starts_per_species: Optional[int] = None,
) -> RobustnessReport:
    """How often `conclusion(network)` survives resampling the parameters.

    `starts_per_species` is RECORDED, not used here: this function calls
    whatever predicate it was handed and cannot know what depth that
    predicate searches at. Pass the same value given to the conclusion
    factory -- `is_bistable(starts_per_species=N)` -- and the report will
    state it. Passing one here and a different one there would produce a
    report that misdescribes its own evidence, which is worse than one
    that says nothing.

    `conclusion` is a predicate rather than a fixed vocabulary so this can
    ask about anything the rest of the module can compute -- bistability,
    oscillation, a species exceeding a threshold, a settling time under an
    hour. A fixed list of supported conclusions would be a list to keep in
    sync with what people actually ask.

    A conclusion that raises is recorded as unevaluated, NOT as false. The
    steady-state search failing at an extreme corner of the box is a fact
    about the solver, and counting it against the mechanism would make every
    model look more fragile the wider the box got.
    """
    # Parameters AND species: a concentration is a species initial here, so
    # a sampler that saw only parameters could not ask the dose question at
    # all. Names are disjoint by construction (the builder prefixes both),
    # and a collision would be caught below rather than silently preferred.
    known = {p.id: float(p.value) for p in network.parameters}
    species_levels = {s.id: float(s.initial) for s in network.species}
    collisions = set(known) & set(species_levels)
    if collisions:
        raise RobustnessError(
            f"{sorted(collisions)} name both a parameter and a species, so a "
            f"sampled value would be applied to both. Rename one."
        )
    known.update(species_levels)

    names = list(vary) if vary is not None else sorted(known)

    unknown = [n for n in names if n not in known]
    if unknown:
        raise RobustnessError(
            f"{unknown} are not parameters or species of this network. It "
            f"has: {', '.join(sorted(known))}."
        )

    fixed: Dict[str, str] = {}
    sampled: List[str] = []
    for name in names:
        if known[name] == 0.0:
            # log(0) is not a number, and substituting a small positive
            # value would change the model's structure rather than its
            # parameters -- a zero rate constant means a reaction that does
            # not happen.
            fixed[name] = "its value is zero, which has no logarithm to sample around"
            continue
        if known[name] < 0.0:
            fixed[name] = "its value is negative, and a log-uniform box is not defined for it"
            continue
        sampled.append(name)

    if not sampled:
        raise RobustnessError(
            "no parameter could be sampled: "
            + ("; ".join(f"{k} ({v})" for k, v in fixed.items()) or "none were given")
            + ". A robustness figure over an empty box would be a count of "
            "one repeated answer."
        )
    if samples < 1:
        raise RobustnessError(f"{samples} samples is not a sample")
    if spread_decades <= 0.0:
        raise RobustnessError(
            f"a spread of {spread_decades} decades is a box of zero width, so "
            f"every draw would be the model's current values and the "
            f"resulting fraction would be 0 or 1 by construction"
        )

    # THE BOX CENTRE, EVALUATED ONCE, BEFORE ANY DRAW.
    #
    # The cheapest thing this module can do and the one it was not doing.
    # Every draw is a perturbation AROUND the model's own values, so if the
    # conclusion is false THERE, the fraction is not measuring how robust
    # the conclusion is -- it is measuring how often a random perturbation
    # happens to move the model into a regime it was not in to begin with.
    #
    # That is not hypothetical. The CLI chose which conclusion to resample
    # from a search at one depth and had every draw judged at another, and
    # the conclusion it picked was false at the centre. The printed
    # percentage looked like fragility and was an artefact of two searches
    # disagreeing.
    #
    # NOT a refusal. "Does this become bistable somewhere nearby?" is a
    # real question about a conclusion that is false at the centre. It is
    # recorded instead, and `summary()` says so plainly, because the one
    # thing that must not happen is for it to pass unremarked.
    try:
        held_at_centre: Optional[bool] = bool(conclusion(network))
    except Exception:  # noqa: BLE001 - a failed centre is not a false one
        held_at_centre = None

    draws = _sample_values(known, sampled, spread_decades, samples, seed)

    results: List[Sample] = []
    for values in draws:
        try:
            held = bool(conclusion(_with_values(network, values)))
            results.append(Sample(values=values, held=held))
        except Exception as exc:  # noqa: BLE001 - a failed draw is not a false one
            results.append(
                Sample(values=values, held=None, reason=f"{type(exc).__name__}: {exc}")
            )

    return RobustnessReport(
        conclusion=conclusion_name,
        samples=tuple(results),
        varied=tuple(sampled),
        spread_decades=spread_decades,
        seed=seed,
        fixed=fixed,
        starts_per_species=starts_per_species,
        held_at_centre=held_at_centre,
    )


# ---------------------------------------------------------------------------
# Ready-made conclusions
# ---------------------------------------------------------------------------


def default_search_depth() -> int:
    """Starting points per species used to judge every resampled draw.

    `sensitivity.STARTS_PER_SPECIES`, which is a MEASURED floor: that
    module records the depth at which each library model stops changing
    its answer, including a two-enzyme competition that reports the wrong
    number of stable states at 8 and the right one at 16.

    Exposed as a function rather than a constant so a caller can ask what
    depth a report was produced at and search at the SAME depth when
    choosing which conclusion to resample. That was the bug: the CLI chose
    a conclusion from `analysis.analyse`'s own default of 8 and then had
    every draw judged here at 16, so the fraction it printed was partly a
    measure of the two searches disagreeing with each other.
    """
    try:
        from .sensitivity import STARTS_PER_SPECIES
    except ImportError:  # pragma: no cover - flat import
        from sensitivity import STARTS_PER_SPECIES  # type: ignore[no-redef]
    return int(STARTS_PER_SPECIES)


def _stability(network: Any, starts_per_species: Optional[int] = None) -> Any:
    try:
        from . import analysis
    except ImportError:  # pragma: no cover - flat import
        import analysis  # type: ignore[no-redef]
    depth = (
        default_search_depth() if starts_per_species is None
        else int(starts_per_species)
    )
    return analysis.analyse(network, starts_per_species=depth)


def is_bistable(*, starts_per_species: Optional[int] = None) -> Callable[[Any], bool]:
    """More than one stable steady state was FOUND.

    Named for what the search establishes rather than for what a reader
    wants it to mean. `analysis.py` reports "at least two stable states were
    found", never "this system is bistable", and a robustness figure built
    on the stronger reading would inherit a claim its evidence does not
    support at every one of two hundred samples instead of once.
    """
    def conclusion(network: Any) -> bool:
        return len(_stability(network, starts_per_species).stable_points) > 1

    return conclusion


def is_monostable(*, starts_per_species: Optional[int] = None) -> Callable[[Any], bool]:
    """Exactly one stable steady state was found.

    NOT the negation of `is_bistable`: a sample where the search found NO
    stable state is neither, and folding that into "monostable" would report
    a model with no steady state as a model with one.
    """
    def conclusion(network: Any) -> bool:
        return len(_stability(network, starts_per_species).stable_points) == 1

    return conclusion


def oscillates(*, starts_per_species: Optional[int] = None) -> Callable[[Any], bool]:
    """Some fixed point has eigenvalues with a non-zero imaginary part and a
    positive real part -- an unstable spiral, which is what a sustained
    oscillation looks like in a linearisation.

    A stable spiral is excluded on purpose: it rings and settles, which is
    not what anyone means by "this oscillates". The distinction is the sign
    of the real part and it is the whole content of the question.
    """
    def conclusion(network: Any) -> bool:
        report = _stability(network, starts_per_species)
        for point in report.physical_points:
            if point.oscillatory and any(v.real > 0 for v in point.eigenvalues):
                return True
        return False

    return conclusion


def settles_within(
    seconds: float, *, starts_per_species: Optional[int] = None,
) -> Callable[[Any], bool]:
    """The slowest timescale of the unique stable state is under `seconds`.

    The practical question behind "can I see this on a plate reader in an
    afternoon", and the one a researcher can act on without any of the
    machinery above.
    """
    def conclusion(network: Any) -> bool:
        stable = _stability(network, starts_per_species).stable_points
        if len(stable) != 1:
            raise RobustnessError(
                f"{len(stable)} stable states at this draw, so there is no "
                f"single settling time to compare against {seconds}"
            )
        timescale = stable[0].slowest_timescale
        if timescale is None:
            raise RobustnessError("every eigenvalue is marginal, so no timescale is defined")
        return timescale < seconds

    return conclusion


def exceeds(
    species: str, threshold: float, *,
    starts_per_species: Optional[int] = None,
) -> Callable[[Any], bool]:
    """A species' steady-state concentration clears a threshold.

    Refuses on more than one stable state rather than picking: "does the
    output exceed 1 mM" has no answer when the system has two outputs and
    which one it reaches depends on where it started.
    """
    def conclusion(network: Any) -> bool:
        stable = _stability(network, starts_per_species).stable_points
        if len(stable) != 1:
            raise RobustnessError(
                f"{len(stable)} stable states at this draw, so '{species} "
                f"exceeds {threshold}' has no single answer"
            )
        if species not in stable[0].state:
            raise RobustnessError(
                f"no species {species!r} in this model. It has: "
                f"{', '.join(sorted(stable[0].state))}."
            )
        return stable[0].state[species] > threshold

    return conclusion


def assess_model(
    model: Any,
    conclusion: Callable[[Any], bool],
    *,
    conclusion_name: str = "the conclusion",
    include_concentrations: bool = False,
    **kwargs: Any,
) -> RobustnessReport:
    """Assess a `ComposedModel`, varying only what nobody has measured.

    The default is the model's own `resolvable` set -- the constants the
    pipeline would go to the literature for. Those are the placeholders, and
    they are what the question "does this conclusion depend on numbers
    nobody has measured" is about.

    `include_concentrations=True` widens it to every parameter, which asks a
    genuinely different question: would this still work at another dose? Both
    are worth asking and the report says which was asked, because a model can
    be robust to every rate constant and collapse under a change of enzyme
    concentration.
    """
    vary = kwargs.pop("vary", None)
    if vary is None:
        if include_concentrations:
            vary = (
                [p.id for p in model.network.parameters]
                + [s.id for s in model.network.species]
            )
        else:
            vary = list(_resolvable_ids(model))
            if not vary:
                raise RobustnessError(
                    "this model has no unresolved constants to vary, so there "
                    "is no placeholder uncertainty to measure. Pass "
                    "include_concentrations=True to ask the dose question "
                    "instead, or name parameters explicitly."
                )
    return assess(
        model.network, conclusion,
        conclusion_name=conclusion_name, vary=vary, **kwargs,
    )


__all__ = [
    "RobustnessError", "RobustnessReport", "Sample",
    "assess", "assess_model",
    "is_bistable", "is_monostable", "oscillates", "settles_within", "exceeds",
    "SPREAD_DECADES", "DEFAULT_SAMPLES", "NEVER_CLAIM_ALWAYS",
]
