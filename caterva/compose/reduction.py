"""Whether a composed model may honestly be made smaller, and what that costs.

WHAT A REDUCTION IS AND WHY IT NEEDS PERMISSION
-----------------------------------------------
A model with a fast variable and a slow one can be made smaller. Set the
fast variable's derivative to zero, solve the resulting algebraic equation
for it, substitute back, and the system loses a dimension. That is the
quasi-steady-state assumption, and it is not an approximation you may make
because the model is inconveniently large. It is licensed by a fact about
the model -- that the fast process finishes while the slow one has barely
started -- and when that fact does not hold the reduced model is wrong in a
way nothing downstream can detect. It integrates, it produces a smooth
curve, and the curve is wrong by whatever the missing dynamics were doing.

The condition has a name and a size. If the fast modes relax on tau_fast
and the slow ones on tau_slow, then eps = tau_fast / tau_slow is the small
parameter of a singular perturbation, and Tikhonov's theorem says the
reduced model tracks the full one to order eps once the initial transient
is over. So the question "may I reduce this?" is the question "how small is
eps?", and eps is computable from the Jacobian at a steady state. That is
all this module does.

THIS IS THE ASSUMPTION THE CATALOGUE ALREADY MADE
-------------------------------------------------
Michaelis-Menten IS a quasi-steady-state assumption. `CATALYTIC_STEP` says
so in its basis: the enzyme-substrate complex is treated as constant
because it is short-lived relative to the reaction, which holds while
[E]0 << [S] and fails for a tightly-binding enzyme at low substrate. Every
composed model that uses a catalytic step has already had a reduction
applied to it, by the motif, before the model existed.

Which means a limitation has to be stated plainly rather than left for
somebody to discover: THIS MODULE CANNOT CHECK THAT ONE. The variable
Michaelis-Menten eliminates is the ES complex, and a model built from
`catalytic_step` does not have an ES complex among its species. There is no
eigenvalue for a variable that is not in the state vector. To ask whether
the motif's own QSSA holds for your enzyme you have to write the mechanism
out with the complex explicit -- `reversible_binding` into
`mass_action_conversion` -- and ask about THAT model. What this module
checks is separations among the species the model actually has.

WHY IT ADVISES RATHER THAN TRANSFORMS
-------------------------------------
Deciding and doing are different jobs with different failure modes, and
only one of them is small.

Doing it needs a computer algebra system. The elimination step is: solve
f_fast(x_fast; x_slow) = 0 for x_fast. For mass action that is a polynomial
root; past mass action it frequently has no closed form at all -- a Hill
term with n = 2.8 gives an equation no CAS will solve in radicals -- and
where it does have one it often has SEVERAL, and picking a branch is a
modelling decision rather than an algebraic one. That is the same problem
`sensitivity.py` refuses on when it finds two stable states, and it would
have to be refused here too, at the point where the reader has already been
promised a smaller model.

Deciding needs a Jacobian and an eigenvalue decomposition, and is worth
shipping on its own, because the two errors are not symmetric. A missing
transformation produces nothing: you keep the model you had. A wrong
decision produces a smaller model that runs, and every number it emits is
confidently wrong. The decision is where the damage is, so the decision is
what this module is.

WHAT IT REFUSES, AND WHY THAT IS THE POINT
------------------------------------------
When the eigenvalues are bunched together there is no fast subsystem, and
`candidates_for_elimination` says so and names the ratio it found rather
than returning the least-slow variable as a suggestion. A ranking always
has a first row; a ranking of timescales that differ by a factor of 1.3 has
a first row that means nothing, and printing it invites exactly the
reduction this module exists to prevent.

The refusal is the most useful output here. "Your model has four species
and four timescales within a factor of two of each other, so it cannot be
reduced -- integrate all four" is an answer. A quasi-steady-state
approximation applied to it is a plot.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple

try:
    from . import analysis
    from .sensitivity import STARTS_PER_SPECIES
except ImportError:  # pragma: no cover - flat import
    import analysis  # type: ignore[no-redef]
    from sensitivity import STARTS_PER_SPECIES  # type: ignore[no-redef]


#: How many times faster the fast modes must be before a reduction is
#: licensed. A JUDGEMENT, and the one everything else here rests on.
#:
#: Ten is the textbook rule of thumb, and it is a rule of thumb because the
#: error of a quasi-steady-state reduction is of order eps = 1 / ratio.
#: A factor of ten therefore buys a reduced model that is wrong by of order
#: 10% in the slow variables -- not "at most 10%": the leading term of the
#: asymptotic series has a coefficient of order one that nobody computes, so
#: 10% is an order of magnitude, not a bound.
#:
#: WHAT THE CHOICE COSTS, in both directions:
#:
#:   at 10   a licensed reduction can still be wrong by a tenth, which is
#:           comparable to the uncertainty on a well-measured kcat and is
#:           more than most readers expect from a step described as valid.
#:   at 100  the error drops to about a percent and almost no real model
#:           qualifies -- metabolic and signalling timescales in one cell
#:           rarely spread two clean decades, so the threshold would refuse
#:           nearly everything and stop being consulted.
#:   at 3    a third of the answer, presented as a simplification.
#:
#: Kept at ten, and the number is reported alongside every verdict so a
#: reader who wants a stricter one can say so: `threshold` is an argument on
#: every function here, not a constant baked into a comparison.
SEPARATION_THRESHOLD = 10.0

#: The share of a species' motion that must lie in the fast subspace before
#: it is called a candidate for elimination. A JUDGEMENT.
#:
#: A half is the natural line -- more of this species moves on the fast
#: timescale than on the slow one -- and it costs exactly what a line
#: through the middle of a continuum costs: a species at 0.51 and one at
#: 0.49 are the same species as far as the mathematics is concerned, and
#: they land on opposite sides. That is why every row carries its
#: participation and why the summary prints the number rather than only the
#: verdict. A candidate near a half is a question, not an answer.
FAST_PARTICIPATION = 0.5

#: How far the fast transient must decay before the reduced model's answer
#: is worth reading. A JUDGEMENT.
#:
#: The reduced model does not represent the initial transient at all -- it
#: replaces it with an instantaneous jump onto the slow manifold -- so
#: before the fast modes have died its error is order one rather than order
#: eps. A hundredth is where a fast mode stops mattering for a plot, and it
#: puts the layer at ln(100) = 4.6 fast timescales. Reported as a duration
#: rather than as a caveat because "the first 4.6 tau_fast are meaningless"
#: is something a reader can act on and "there is an initial layer" is not.
LAYER_TOLERANCE = 0.01

#: Below this an eigenvalue counts as a structural zero from a conservation
#: law rather than a dynamic mode. MIRRORS the rule in `analysis.analyse`,
#: which drops as many near-zero eigenvalues as the network has conservation
#: laws, because the dynamics do not move along a conserved direction.
#:
#: Duplicated rather than imported because `analysis` applies it inline and
#: exports only the eigenVALUES, while this module needs the eigenVECTORS to
#: say which species are fast -- so it has to redo the decomposition. The
#: duplication is made falsifiable rather than trusted:
#: `TestTheSpectrumAgreesWithTheAnalysisModule` asserts the two produce the
#: same retained spectrum on a model that has conservation laws, so a change
#: to one rule that is not made to the other turns a test red.
STRUCTURAL_ZERO = 1e-6


class ReductionRefused(RuntimeError):
    """This model cannot be reduced, and this says which fact makes it so.

    Carries the ratio that was actually found wherever one exists. A
    refusal that says "no timescale separation" and stops leaves the reader
    unable to tell a model that missed by a hair from one whose modes are
    identical, and those call for different next steps.
    """


# ---------------------------------------------------------------------------
# The spectrum
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mode:
    """One eigenvalue of the Jacobian, read as a timescale."""

    eigenvalue: complex
    #: 1 / |Re lambda|, in the model's time unit. The e-folding time of this
    #: mode; NOT the period, which a complex pair also has and which is
    #: reported separately because they are different numbers about
    #: different things.
    timescale: float

    @property
    def oscillatory(self) -> bool:
        return abs(self.eigenvalue.imag) > analysis.MARGINAL_EIGENVALUE

    @property
    def growing(self) -> bool:
        """The mode moves AWAY from this state.

        Fatal for a fast mode and harmless for a slow one, which is why the
        sign is carried per mode rather than tested once on the fixed
        point's classification. A quasi-steady state is a state the fast
        subsystem relaxes TO; a growing fast mode has none to relax to.
        """
        return self.eigenvalue.real > 0.0

    @property
    def period(self) -> Optional[float]:
        if not self.oscillatory:
            return None
        return 2.0 * math.pi / abs(self.eigenvalue.imag)

    def describe(self) -> str:
        parts = [f"tau = {self.timescale:.3g} (lambda = {self.eigenvalue.real:+.3g}"]
        if self.oscillatory:
            parts[0] += f" {self.eigenvalue.imag:+.3g}i"
        parts[0] += ")"
        if self.period is not None:
            parts.append(f"ringing with period {self.period:.3g}")
        if self.growing:
            parts.append("GROWING, not relaxing")
        return "; ".join(parts)


@dataclass(frozen=True)
class TimescaleSeparation:
    """The spectrum at one state, and the gap in it, if there is one."""

    #: Where this was computed. A spectrum is a property of a state, not of
    #: a model, and a report that did not say which state would be
    #: uncheckable.
    state: Mapping[str, float]
    species: Tuple[str, ...]
    #: Fastest first: sorted by |Re lambda| descending, so `modes[0]` has the
    #: shortest timescale.
    modes: Tuple[Mode, ...]
    #: Ratio between each adjacent pair, `tau[i+1] / tau[i]`. Always >= 1.
    #: One shorter than `modes`; a spectrum of n modes has n-1 places to cut.
    ratios: Tuple[float, ...]
    #: Number of modes on the fast side of the widest gap, so
    #: `modes[:split]` are fast and `modes[split:]` are slow.
    split: int
    #: The widest ratio -- the one at `split`. THE number this module exists
    #: to produce.
    gap: float
    threshold: float

    @property
    def fast_modes(self) -> Tuple[Mode, ...]:
        return self.modes[: self.split]

    @property
    def slow_modes(self) -> Tuple[Mode, ...]:
        return self.modes[self.split :]

    @property
    def fast_modes_relax(self) -> bool:
        """Every fast mode decays.

        The condition a quasi-steady state needs and a large gap does not
        supply. At a saddle whose unstable direction happens to be the quick
        one, the gap can be enormous and the reduction still meaningless:
        setting the derivative of a variable that is running away to zero
        replaces it with a constraint it is moving off.
        """
        return not any(mode.growing for mode in self.fast_modes)

    @property
    def licensed(self) -> bool:
        return self.gap >= self.threshold and self.fast_modes_relax

    @property
    def fast_timescale(self) -> float:
        """The SLOWEST of the fast modes -- the one that ends the transient."""
        return self.modes[self.split - 1].timescale

    @property
    def slow_timescale(self) -> float:
        """The FASTEST of the slow modes -- the one the gap is measured to."""
        return self.modes[self.split].timescale

    def summary(self) -> str:
        lines = [
            f"{len(self.modes)} dynamic mode(s) at "
            + ", ".join(f"{k}={v:.4g}" for k, v in sorted(self.state.items()))
            + ", by e-folding time:"
        ]
        for position, mode in enumerate(self.modes):
            marker = "fast" if position < self.split else "slow"
            lines.append(f"  - [{marker}] " + mode.describe())

        lines.append(
            f"The widest gap is a factor of {self.gap:.3g}, between "
            f"tau = {self.fast_timescale:.3g} and tau = "
            f"{self.slow_timescale:.3g}."
        )

        if not self.fast_modes_relax:
            lines.append(
                "At least one fast mode GROWS. A quasi-steady state is a "
                "state the fast subsystem relaxes to, and this one has none "
                "-- so however wide the gap, there is nothing here to "
                "eliminate. The size of the gap describes how quickly this "
                "state is left, not how quickly anything settles."
            )
        elif self.licensed:
            lines.append(
                f"That clears the stated threshold of {self.threshold:g}, so "
                f"a quasi-steady-state reduction of the {self.split} fast "
                f"mode(s) is licensed here, at an expected error of order "
                f"{1.0 / self.gap:.2g} in the slow variables. Licensed is "
                f"not free: see `validity_report` for what it costs and for "
                f"the window at the start where the reduced model says "
                f"nothing."
            )
        else:
            lines.append(
                f"That is under the stated threshold of {self.threshold:g}, "
                f"so no reduction is licensed at this state. The modes are "
                f"not separated: whatever was eliminated would still be "
                f"moving while the rest of the model moved."
            )

        lines.append(
            "Local, and to a state. These are the eigenvalues of the "
            "Jacobian at one steady state at the parameter values the model "
            "currently holds. A separation is a function of the rate "
            "constants and can appear or vanish when they change."
        )
        return " ".join(lines)


def timescale_separation(
    network: Any,
    *,
    at: Optional[Any] = None,
    threshold: float = SEPARATION_THRESHOLD,
    starts_per_species: int = STARTS_PER_SPECIES,
) -> TimescaleSeparation:
    """The spectrum of timescales at a steady state, and the gap in it.

    Reports the absence of a gap rather than raising on it: a ratio of 1.2
    is a finding about the model and the caller may want to print it. What
    it does raise on is the cases where no spectrum exists to report --
    no steady state, more than one, a mode with no timescale, or a single
    mode with nothing to compare against. Each of those would otherwise have
    to be papered over with a number, and there is no honest number for any
    of them.

    `at` names the state. Left out, the state is found by the same multistart
    search `sensitivity.py` uses, at the same measured depth, and more than
    one stable state is refused rather than picked between.
    """
    point = at if at is not None else _the_one_stable_point(network, starts_per_species)
    state = dict(point.state)

    values, _vectors, species = _dynamic_spectrum(network, state)

    if not values:
        raise ReductionRefused(
            "this model has no dynamic modes at all: every direction in its "
            "state space is fixed by a conservation law, so nothing relaxes "
            "and there is nothing to separate. A model like this is an "
            "algebraic system wearing a differential system's clothes."
        )

    marginal = [v for v in values if abs(v.real) <= analysis.MARGINAL_EIGENVALUE]
    if marginal:
        raise ReductionRefused(
            f"{len(marginal)} eigenvalue(s) here have a real part of "
            f"essentially zero (the smallest is "
            f"{min(abs(v.real) for v in marginal):.2g}, against a "
            f"marginality tolerance of {analysis.MARGINAL_EIGENVALUE:g}), so "
            f"those modes have no timescale: 1 / |Re lambda| is a division "
            f"by zero, not an infinite separation. Reducing here would "
            f"eliminate variables on the strength of an infinity the "
            f"arithmetic produced. This happens at a bifurcation, where the "
            f"linearisation decides nothing, and along a continuum of fixed "
            f"points, where the state reached is set by the transient rather "
            f"than by the equations at rest. If it is instead a conservation "
            f"law that was not accounted for, `network.conservation_laws()` "
            f"lists what was found and this dropped "
            f"{len(species) - len(values)} structural zero(s) for them."
        )

    modes = tuple(
        sorted(
            (Mode(eigenvalue=v, timescale=1.0 / abs(v.real)) for v in values),
            key=lambda m: m.timescale,
        )
    )

    if len(modes) == 1:
        raise ReductionRefused(
            f"this model has one dynamic mode, at tau = "
            f"{modes[0].timescale:.3g}. A timescale separation is a ratio "
            f"between two of them, so there is none to report: nothing here "
            f"is fast RELATIVE to anything, and a model with one mode is "
            f"already as small as a quasi-steady-state argument can make it. "
            f"The other {len(species) - 1} species are fixed by conservation "
            f"laws rather than being slow."
        )

    ratios = tuple(
        modes[i + 1].timescale / modes[i].timescale for i in range(len(modes) - 1)
    )
    split = 1 + max(range(len(ratios)), key=lambda i: ratios[i])

    return TimescaleSeparation(
        state=state,
        species=species,
        modes=modes,
        ratios=ratios,
        split=split,
        gap=ratios[split - 1],
        threshold=float(threshold),
    )


# ---------------------------------------------------------------------------
# Which variables are the fast ones
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """One species, and how much of its motion is in the fast subspace."""

    species: str
    #: Share of this species' motion carried by the fast modes, in [0, 1].
    #: 1.0 means the slow modes do not move this species at all.
    participation: float
    fast_weight: float
    slow_weight: float
    threshold: float = FAST_PARTICIPATION

    @property
    def eliminable(self) -> bool:
        return self.participation >= self.threshold

    def describe(self) -> str:
        if self.eliminable:
            return (
                f"{self.species}: {self.participation * 100:.0f}% of its "
                f"motion is on the fast timescale -- a candidate to be "
                f"solved for algebraically"
            )
        return (
            f"{self.species}: only {self.participation * 100:.0f}% of its "
            f"motion is fast, so it must stay a differential variable"
        )


def candidates_for_elimination(
    network: Any,
    *,
    at: Optional[Any] = None,
    threshold: float = SEPARATION_THRESHOLD,
    starts_per_species: int = STARTS_PER_SPECIES,
    separation: Optional[TimescaleSeparation] = None,
) -> Tuple[Candidate, ...]:
    """Which species move on the fast timescale, ranked, or a refusal.

    REFUSES when no separation is licensed, and this is the point of the
    module. Participations are computable whatever the spectrum looks like:
    with the modes bunched together the arithmetic still runs, still ranks
    the species, and still puts something first. That first row would be
    read as a recommendation, and acting on it produces a smaller model
    whose error is of order one. So the gap is checked before the ranking is
    produced, and the refusal names the ratio it found.

    RETURNS EVERY SPECIES, not only the ones over the line. A species at 0.49
    is the row a reader most needs to see, because it is the one the
    threshold decided by a hair, and a function that returned only the
    winners would hide exactly the case where the judgement is weakest.
    `.eliminable` marks the ones that cleared it.

    THE MEASURE, and its limits. Each right eigenvector of the Jacobian is a
    direction in state space that relaxes at its own rate; numpy returns
    them with unit norm, so the square of a species' component in a mode is
    that mode's share of the species' motion. Summing the squares over the
    fast modes and over the slow ones and taking the ratio gives a number in
    [0, 1] per species.

    That is a HEURISTIC and is called one. The eigenvectors are not
    orthogonal in general, so "share" is a projection onto a non-orthogonal
    basis and the two weights are not a partition of anything exactly. The
    rigorous version is computational singular perturbation, which builds
    the fast and slow subspaces properly and refines them; this is the first
    step of it and is reported as an indication of which variables to look
    at, not as a proof that they are the right ones.

    `separation` hands in a report the caller already has, so a summary that
    prints both does not pay for the steady-state search twice. It must be
    the report for THIS network at the state being asked about; nothing here
    can check that, and a mismatched one would rank the wrong species with
    complete confidence.
    """
    if separation is None:
        separation = timescale_separation(
            network, at=at, threshold=threshold, starts_per_species=starts_per_species
        )

    if not separation.fast_modes_relax:
        growing = [m for m in separation.fast_modes if m.growing]
        raise ReductionRefused(
            f"this state has {len(growing)} fast mode(s) that GROW rather "
            f"than relax (the quickest at tau = "
            f"{min(m.timescale for m in growing):.3g}), so no variable here "
            f"can be put at a quasi-steady state: the assumption is that the "
            f"fast subsystem has settled, and this one is leaving. The gap "
            f"of {separation.gap:.2f} is real and says how fast the state is "
            f"departed, not how fast anything arrives. Ask about a stable "
            f"steady state instead, or about the limit cycle if the "
            f"departure ends in one."
        )

    if not separation.licensed:
        raise ReductionRefused(
            f"this model cannot be reduced at this state: the widest gap in "
            f"its spectrum is a factor of {separation.gap:.2f}, and a "
            f"quasi-steady-state reduction needs at least "
            f"{separation.threshold:g}. Its {len(separation.modes)} "
            f"timescales are "
            + ", ".join(f"{m.timescale:.3g}" for m in separation.modes)
            + " (as 1 / |Re lambda|, in the model's time unit). With the "
            "modes this close together there is no fast subsystem: whatever "
            "variable was eliminated would still be moving while the rest of "
            "the model moved, and the reduced model's error would be of "
            f"order {1.0 / separation.gap:.2g} -- the same size as the "
            "answer. What to do instead: integrate the model as it stands, "
            f"which is {len(separation.species)} species and cheap; or look "
            "for a regime where a separation exists, since the gap is a "
            "function of the rate constants and a sweep can find one; or "
            "accept that this system genuinely has no fast part, which is "
            "itself a finding about the biology and not a failure of the "
            "analysis."
        )

    _values, vectors, species = _dynamic_spectrum(network, separation.state)
    order = _match_modes(_values, separation.modes)

    rows: List[Candidate] = []
    for index, name in enumerate(species):
        weights = [abs(vectors[index][column]) ** 2 for column in order]
        fast = sum(weights[: separation.split])
        slow = sum(weights[separation.split :])
        total = fast + slow
        if total <= 0.0:
            # A species no eigenvector touches. Possible only for a species
            # that does not appear in the Jacobian at all -- one whose row
            # and column are identically zero -- and reporting a
            # participation for it would be dividing nothing by nothing.
            rows.append(Candidate(name, 0.0, 0.0, 0.0, FAST_PARTICIPATION))
            continue
        rows.append(
            Candidate(
                species=name,
                participation=fast / total,
                fast_weight=fast,
                slow_weight=slow,
                threshold=FAST_PARTICIPATION,
            )
        )

    return tuple(sorted(rows, key=lambda row: row.participation, reverse=True))


# ---------------------------------------------------------------------------
# What the reduction costs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidityReport:
    """The error a reduction at this separation would introduce."""

    gap: float
    threshold: float
    licensed: bool
    #: Order of the relative error in the slow variables, once the initial
    #: transient is over. An ORDER, not a bound -- see `relative_error`.
    relative_error: float
    fast_timescale: float
    slow_timescale: float
    #: How long the reduced model says nothing. Before this the fast modes
    #: are still moving and the reduced model has replaced them with an
    #: instantaneous jump.
    initial_layer: float
    #: The most variables any reduction here may eliminate: the dimension of
    #: the fast subspace, which is the number of fast modes and no more.
    rank_limit: int
    #: How many species the participation test flagged.
    flagged: int

    @property
    def over_reduced(self) -> bool:
        """More species look fast than there are fast directions.

        A real and easy mistake. Three species can each carry most of their
        motion in a two-dimensional fast subspace -- they are sharing those
        two directions -- and eliminating all three would remove a dimension
        the model still needs. The fast subspace's dimension is the number
        of fast modes, full stop, and the participation ranking cannot see
        that on its own.
        """
        return self.flagged > self.rank_limit

    def summary(self) -> str:
        lines = [
            f"Gap of {self.gap:.3g} against a threshold of "
            f"{self.threshold:g}: a quasi-steady-state reduction here is "
            + ("licensed." if self.licensed else "NOT licensed.")
        ]
        lines.append(
            f"Expected error in the slow variables: of order "
            f"{self.relative_error * 100:.2g}%. That is the leading term of "
            f"a singular-perturbation expansion in eps = tau_fast / tau_slow "
            f"= {self.relative_error:.3g}, whose coefficient is of order one "
            f"and is not computed -- so it is an order of magnitude and not "
            f"a bound. A reduction at the threshold should be expected to be "
            f"wrong by about a tenth, which is more than the word "
            f"'simplification' usually implies."
        )
        lines.append(
            f"The reduced model says nothing for the first "
            f"{self.initial_layer:.3g} time units. It replaces the fast "
            f"transient with an instantaneous jump onto the slow manifold, "
            f"so during the transient its error is of order one rather than "
            f"of order {self.relative_error:.2g}. "
            f"{self.initial_layer:.3g} is how long the fast modes take to "
            f"fall to {LAYER_TOLERANCE:g} of their initial size at "
            f"tau_fast = {self.fast_timescale:.3g}."
        )
        lines.append(
            "The steady state is not evidence either way. A quasi-steady-"
            "state reduction sets the fast derivatives to zero, which is "
            "exactly what the full model's fixed point already satisfies, so "
            "the reduced model has the same fixed point by construction -- "
            "at every gap, including a gap of one. A reduced model that "
            "lands in the right place has demonstrated nothing about its "
            "validity; the error lives entirely in the approach."
        )
        if self.over_reduced:
            lines.append(
                f"{self.flagged} species look fast but the fast subspace has "
                f"only {self.rank_limit} dimension(s). They are sharing those "
                f"directions, and eliminating all {self.flagged} would remove "
                f"a degree of freedom the model still needs. At most "
                f"{self.rank_limit} variable(s) may go."
            )
        return " ".join(lines)


def validity_report(
    separation: TimescaleSeparation,
    candidates: Sequence[Candidate] = (),
) -> ValidityReport:
    """What a reduction at this separation would cost.

    Takes the separation rather than the network, for two reasons. The
    steady-state search behind a separation is the expensive part and
    recomputing it to answer a question about a number already in hand would
    be waste. And more importantly, a report recomputed from the network
    could silently describe a DIFFERENT state from the one the caller was
    shown -- the search is global, the model may have several -- and a
    validity report about a state nobody asked about is worse than none.

    Produced whether or not the reduction is licensed. An unlicensed one is
    where the number does the most work: "of order 80% error" is the
    argument the refusal is making, in the units the reader cares about.
    """
    epsilon = 1.0 / separation.gap
    return ValidityReport(
        gap=separation.gap,
        threshold=separation.threshold,
        licensed=separation.licensed,
        relative_error=epsilon,
        fast_timescale=separation.fast_timescale,
        slow_timescale=separation.slow_timescale,
        initial_layer=separation.fast_timescale * math.log(1.0 / LAYER_TOLERANCE),
        rank_limit=len(separation.fast_modes),
        flagged=sum(1 for row in candidates if row.eliminable),
    )


# ---------------------------------------------------------------------------
# The state, and the decomposition at it
# ---------------------------------------------------------------------------


def _the_one_stable_point(network: Any, starts_per_species: int) -> Any:
    """The unique stable steady state, or a refusal naming the ambiguity.

    The same rule `sensitivity.py` applies, for the same reason and at the
    same measured search depth: a quantity read off a choice between
    attractors describes the choice. Here the consequence is sharper than a
    derivative, because each state has its own Jacobian and therefore its
    own answer about whether a reduction is licensed -- one state can be
    stiff and the other not, and "this model can be reduced" would then be
    true of half the model's behaviour.
    """
    report = analysis.analyse(network, starts_per_species=starts_per_species)
    stable = report.stable_points
    if not stable:
        raise ReductionRefused(
            f"no stable steady state was found at these values, from "
            f"{report.starts_tried} starting points, so there is no state to "
            f"linearise about and no spectrum to separate. A timescale here "
            f"is a property of the Jacobian AT a state; without one there is "
            f"nothing to take eigenvalues of. If this system oscillates "
            f"forever its timescales are the period and the rate of approach "
            f"to the cycle, and a reduction argument would have to be made "
            f"about the limit cycle rather than about a point -- which this "
            f"module does not do."
        )
    if len(stable) > 1:
        raise ReductionRefused(
            f"{len(stable)} stable states were found at these values. Each "
            f"has its own Jacobian, its own spectrum, and possibly its own "
            f"answer about whether a reduction is licensed -- a switch can "
            f"be stiff in one state and not in the other -- so 'this model's "
            f"timescales' is not a well-formed question for a system that "
            f"rests in more than one place. Pass one of them as `at=` and "
            f"ask about that state; `analysis.analyse(network).stable_points` "
            f"lists them."
        )
    return stable[0]


def _dynamic_spectrum(
    network: Any, state: Mapping[str, float]
) -> Tuple[Tuple[complex, ...], List[List[complex]], Tuple[str, ...]]:
    """Eigenvalues AND eigenvectors at a state, conserved directions removed.

    `analysis.analyse` already computes the eigenvalues and already drops the
    structural zeros, and this redoes both -- because it returns only the
    values, and deciding WHICH SPECIES are fast needs the vectors. The
    dropping rule is therefore duplicated, which is a risk, and the risk is
    handled by a test that asserts the two agree on a model with
    conservation laws rather than by a comment asserting they do.

    `vectors[i][j]` is species i's component of mode j. numpy returns
    columns of unit norm, which is what makes a squared component a share.
    """
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise ReductionRefused(
            "timescale analysis needs numpy, which is in requirements.txt "
            f"but not importable here: {exc}"
        ) from exc

    rhs, species = analysis.derivative_function(network)
    missing = [name for name in species if name not in state]
    if missing:
        raise ReductionRefused(
            f"the state given has no value for {missing}, which this network "
            f"has as species. A Jacobian at a partial state would be a "
            f"Jacobian somewhere else."
        )
    vector = [float(state[name]) for name in species]
    matrix = np.array(analysis.jacobian(rhs, vector), dtype=float)
    values, columns = np.linalg.eig(matrix)

    keep = list(range(len(values)))
    laws = _conservation_law_count(network)
    if laws:
        by_size = sorted(keep, key=lambda i: abs(values[i]))
        structural = {i for i in by_size[:laws] if abs(values[i]) <= STRUCTURAL_ZERO}
        keep = [i for i in keep if i not in structural]

    retained = tuple(complex(values[i]) for i in keep)
    vectors = [[complex(columns[row][i]) for i in keep] for row in range(len(species))]
    return retained, vectors, species


def _conservation_law_count(network: Any) -> int:
    try:
        return len(network.conservation_laws())
    except Exception:  # noqa: BLE001 - the count is a courtesy, not a result
        return 0


def _match_modes(values: Sequence[complex], modes: Sequence[Mode]) -> List[int]:
    """Column indices of `values` in the order `modes` are in.

    `timescale_separation` sorts the modes by timescale and
    `candidates_for_elimination` needs the eigenvector that goes with each,
    so the sort has to be reproduced on the columns. Matched by nearest
    eigenvalue rather than by re-sorting, because a repeated eigenvalue
    sorts ambiguously and a mismatch would attribute one mode's eigenvector
    to another -- a wrong answer that looks entirely reasonable.

    Each column is used once. With a repeated eigenvalue the choice between
    its columns is arbitrary and cannot be otherwise: a degenerate
    eigenvalue's eigenvectors span a subspace and no rule picks a
    distinguished basis for it. The participation sums over the whole fast
    or slow block, so any consistent assignment within a block gives the
    same answer.
    """
    remaining = set(range(len(values)))
    order: List[int] = []
    for mode in modes:
        best = min(remaining, key=lambda i: abs(values[i] - mode.eigenvalue))
        remaining.discard(best)
        order.append(best)
    return order


__all__ = [
    "Candidate",
    "Mode",
    "ReductionRefused",
    "TimescaleSeparation",
    "ValidityReport",
    "candidates_for_elimination",
    "timescale_separation",
    "validity_report",
    "FAST_PARTICIPATION",
    "LAYER_TOLERANCE",
    "SEPARATION_THRESHOLD",
    "STRUCTURAL_ZERO",
]
