"""The curve a pharmacologist measures, computed from the mechanism instead.

THE QUESTION THIS ANSWERS
-------------------------
Drug and receptor biology is reported as a dose-response curve: vary one
input, measure one output, quote an EC50 and a Hill slope. That is the
shape of nearly every number in a pharmacology paper, and it is the shape
of nothing Caterva could previously produce.

The EC50 in a paper is FITTED TO DATA. The EC50 here is COMPUTED FROM A
MECHANISM -- the steady-state readout at each dose, solved from the rate
laws, then summarised the same way an experimentalist would summarise their
plate. That makes the two directly comparable, which is the point: it turns
a mechanism into a prediction somebody can check against an assay they have
already run, rather than into a trajectory nobody measured.

It also makes the comparison falsifiable in the useful direction. A
mechanism that implies an EC50 a hundred-fold from the measured one is
wrong about something, and the model says which constants the EC50 rests on
(see `compose/sensitivity.py`).

THE DOSE IS HELD, NOT DUMPED IN
-------------------------------
A dose is applied to a bath and BUFFERED: the agonist sits at its nominal
concentration for the whole experiment, and the cell's consumption of it
does not move the number on the tube. So the input species is CLAMPED --
turned from a state variable into a constant at that dose -- and the
remaining system is solved to steady state.

The alternative, setting the input's initial amount and integrating,
computes something else entirely. A closed Michaelis-Menten model started
at S = 1 ends at P = 1 no matter what kcat and Km are, because S + P is
conserved: the "curve" that comes out is the line P = dose, which is a mass
balance wearing a dose-response's clothes. Every point on it is correct and
the figure means nothing. `compose/sensitivity.py` reports the same pinning
from the other direction, as a steady state no rate constant can move.

Clamping is visible in the model rather than hidden in the solver: it drops
the species, adds a parameter of the same name, and strips that species
from the stoichiometry -- exactly what SBML calls a boundary condition.
`clamped` is public because the OTHER species an experiment holds fixed --
the substrate, in an inhibitor assay -- are held the same way, by the
caller, before the dose is varied.

A SPECIES, NOT A PARAMETER
--------------------------
The dose is a concentration the experimenter controls, so it is a species.
Asking what happens when a rate CONSTANT changes is a different question
with a different tool: `compose/bifurcation.py`'s sweep. The two get
confused because both draw a curve, and the distinction is the difference
between "what does this drug do" and "what if the enzyme were faster".

A FITTED HILL SLOPE IS NOT A SUBUNIT COUNT
------------------------------------------
This module reports a Hill slope, and the single most common error made
with that number is to read it as the number of binding sites.

It is not one. The Hill slope is a DESCRIPTION OF THE CURVE'S STEEPNESS at
its midpoint and nothing else. It is real-valued and routinely
non-integer; it is bounded above by the number of sites and equals that
number only in the unreachable limit of all-or-none binding; it moves with
the conditions of the assay while the number of subunits does not.
Haemoglobin has four sites and a Hill slope near 2.8, and no interpretation
of "2.8 sites" is available.

Worse here than in a paper, because here the curve came from a MECHANISM.
The slope this module fits to a cooperative motif's output comes back equal
to that motif's own exponent when the mechanism is exactly Hill-shaped --
and that agreement is a property of the rate law that was written down, not
evidence about any protein's structure. Reading it as a site count would
turn an assumption of the model into a finding about biology.

`HillFit.hill_slope` says so in its docstring, `describe` says so in its
output, and neither is decoration: a number that is going to be misread has
to arrive with the correction attached.

WHY A BIPHASIC CURVE IS REFUSED, WHICH IS THE MOST IMPORTANT THING HERE
-----------------------------------------------------------------------
EC50 is defined as the dose at half-maximal response. That definition
presumes the response is a one-to-one function of the dose. A curve that
rises and then falls has TWO doses at every response between its ends, so
there is no such thing as the dose at half-maximum: there are two, and they
can be orders of magnitude apart.

Substrate inhibition produces exactly this shape, and it is not exotic --
the library's own `substrate_inhibition` motif peaks at sqrt(Km * Ksi) and
falls away on both sides of it. Fitting a Hill equation through that gives
four numbers and a residual, all of which are arithmetic, and an EC50 that
describes nothing. So `fit_hill` refuses, names the dose the curve turns
at, and says what to report instead.

The refusal is deliberately narrow. `emax` and `dynamic_range` are still
defined for a biphasic curve and still returned -- the peak really is the
largest response, and the span really is the span. Only the EC50 and the
slope are undefined, because only they assume a shape the curve does not
have. A blanket "this curve cannot be analysed" would be a bigger claim
than the true one and would throw away two readouts that are fine.

WHAT THE NUMBERS HERE ARE NOT
-----------------------------
A computed EC50 is NOT A MEASUREMENT and carries no citation. It is what
the mechanism implies AT THE VALUES THE MODEL CURRENTLY HOLDS, and for an
ungrounded model those are the motif library's illustrative placeholders.
`DoseResponse.unmeasured` carries the constants with no measured value
behind them and the summary names them, because an EC50 computed on
placeholders is a property of the SHAPE of the mechanism and a reader who
takes it for a prediction about a protein has been misled by the format
rather than by the number.

The doses are not measurements either, and could not be: a dose is a
concentration, concentrations are CHOSEN rather than resolved (ADR 0013's
neighbour -- nobody publishes what was in your tube), and this module never
asks the literature for one.

THE UNIT IS RECOVERED, NOT ASSUMED
----------------------------------
An EC50 without its unit cannot be compared with a measured one, which is
the only thing it exists for. Recovering it takes two sources because
neither is enough alone:

    core.network.Species     carries an amount and NO unit
    core.network.Parameter   carries a value and NO unit -- the unit lives
                             on the MotifParameter the builder read and is
                             dropped at build time
    Composition              declares ONE concentration unit for the model

A dose is a species concentration, so the composition's declared unit is
the authority. `scale.units_from_model` recovers what each motif declared
for its parameters, and those are the CHECK on it: an affinity is added to
a concentration inside the rate law -- `Km + S` -- so an affinity declared
in a unit the species are not in means the unit belonging on an EC50 is a
guess between two. `dose_unit_of` reports that disagreement instead of
resolving it, and `curve` on a bare network leaves the unit unset rather
than assuming millimolar, because a wrong unit on a number offered for
comparison is worse than no unit at all.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from .sensitivity import STARTS_PER_SPECIES
except ImportError:  # pragma: no cover - flat import
    from sensitivity import STARTS_PER_SPECIES  # type: ignore[no-redef]


#: The largest reversal, as a fraction of the curve's span, that is still
#: called monotonic.
#:
#: MEASURED at both ends. The Michaelis-Menten readout below -- a clamped
#: catalytic step feeding a first-order outflow -- comes back with a
#: reversal of exactly 0.0 over 25 doses: the root find lands on the
#: analytic answer to the last bit. Substrate inhibition over the same
#: doses comes back at 0.89.
#:
#: Neither end is where the threshold has to sit, because an exact 0.0 is a
#: property of a model this easy. The steady states behind a curve are roots
#: accepted at `analysis.RESIDUAL_TOLERANCE` (1e-9) on quantities of order
#: one, so two neighbouring doses on a harder model can disagree in the
#: ninth digit for reasons that are entirely the solver's. Calling that
#: biphasic would refuse an EC50 for curves that are perfectly monotone,
#: which is the expensive direction to be wrong in -- the refusal is only
#: worth having if it fires on substrate inhibition and on nothing else.
#:
#: 1e-3 of the span sits six orders above that convergence noise and three
#: below a real reversal. `DoseResponse.reversal` reports what was actually
#: seen, so a reader never has to take the threshold on trust.
MONOTONIC_TOLERANCE = 1e-3

#: Below this relative span there is no curve to summarise.
#:
#: Relative to the readout's own magnitude, so it means the same thing for a
#: readout of order 1e-3 as for one of order 1e3. A thousand times the
#: solver's convergence noise, and still a millionth of the readout -- no
#: assay resolves a millionth, so a "curve" this flat is a readout the dose
#: does not reach rather than a shallow response.
FLAT_TOLERANCE = 1e-6

#: Fewest doses a four-parameter fit is allowed to run on.
#:
#: Four points fix four parameters with zero degrees of freedom: the
#: residual is then a property of the arithmetic rather than evidence the
#: curve is Hill-shaped, and a residual of zero would read as a perfect fit
#: when it is an interpolation. Five is the fewest that leaves the residual
#: anything to say. It is a floor, not a recommendation -- five points
#: spanning two decades determine an EC50 far less well than twenty do.
MINIMUM_DOSES = 5

#: How far up the fitted curve the highest dose must reach before the
#: asymptote is called observed rather than extrapolated.
#:
#: A JUDGEMENT. The top of a Hill curve is approached and never arrived at,
#: so "did it plateau" has no exact answer; 95% of the way from the basal
#: level to the asymptote is where a plate reader's noise would stop
#: resolving the difference. Below it the fitted maximum -- and therefore
#: the EC50, which is measured against that maximum -- is an extrapolation
#: beyond the doses tested, and `HillFit.describe` says so. This is the
#: commonest way a published EC50 is wrong, and it is invisible in the
#: number itself.
PLATEAU_FRACTION = 0.95

#: Smallest Hill slope the fit may return. Positive by construction: the
#: direction of the response is carried by the asymptotes, not by the sign
#: of the slope -- see `fit_hill` on why allowing both makes the fit
#: non-identifiable.
MIN_HILL_SLOPE = 1e-6

#: Convergence tolerances for the fit. Matched to `analysis.analyse`, which
#: produced the points: a fit converged less tightly than its own data would
#: report a residual that was its own stopping rule.
FIT_TOLERANCE = 1e-14


class DoseResponseUnavailable(RuntimeError):
    """The curve, or a readout from it, could not be computed."""


class NotMonotonic(DoseResponseUnavailable):
    """The curve turns around, so EC50 and Hill slope are undefined.

    A separate type because the caller's options are different. Every other
    refusal here means something could not be computed; this one means the
    QUANTITY DOES NOT EXIST for this curve, and no amount of extra doses or
    a better solver will produce it. A caller that retries on
    `DoseResponseUnavailable` should not retry on this.
    """


# ---------------------------------------------------------------------------
# The curve
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DosePoint:
    """One dose, and the steady-state readout at it."""

    dose: float
    response: float
    #: Largest absolute time derivative at the state this was read from.
    #: Carried rather than discarded so a reader can see HOW converged each
    #: point is, in the same spirit as `analysis.FixedPoint.residual`.
    residual: float
    #: How many starting points the search used at this dose. The meaning of
    #: "one stable state" depends entirely on how hard it looked.
    starts_tried: int


@dataclass(frozen=True)
class DoseResponse:
    """A readout at each dose, and what can be said about the shape."""

    input_species: str
    readout: str
    points: Tuple[DosePoint, ...]
    #: The unit the doses -- and therefore any EC50 fitted to them -- are
    #: in. `None` means no unit was recorded, which is the honest state for
    #: a bare network: see `dose_unit_of`.
    dose_unit: Optional[str] = None
    #: Parameters behind this curve with no measured value. Filled by
    #: `curve_for_model` from the model's own account of what it could not
    #: resolve; empty from `curve`, which has only a network and cannot
    #: know. Empty therefore means "not established", never "all grounded".
    unmeasured: Tuple[str, ...] = ()
    starts_per_species: int = STARTS_PER_SPECIES

    @property
    def doses(self) -> Tuple[float, ...]:
        return tuple(p.dose for p in self.points)

    @property
    def responses(self) -> Tuple[float, ...]:
        return tuple(p.response for p in self.points)

    @property
    def baseline(self) -> float:
        """The readout at the LOWEST dose tested, which need not be zero.

        Not called "the untreated control": if the caller's lowest dose is
        already active, this is a partly treated system and the dynamic
        range measured from it understates the real one. The dose it was
        read at is in `points[0].dose` and the summary prints it.
        """
        return self.points[0].response

    @property
    def peak(self) -> DosePoint:
        """The dose with the largest readout.

        Meaningful for every curve including a biphasic one -- it is where
        substrate inhibition turns over -- which is why it is a property of
        the curve rather than of the fit.
        """
        return max(self.points, key=lambda p: p.response)

    @property
    def extreme(self) -> DosePoint:
        """The dose at which the readout is FURTHEST from its baseline.

        Not `peak`. For a rising curve the two coincide; for a FALLING one
        -- an inhibitor titrated against a readout it suppresses -- the
        peak is the lowest dose, where nothing has happened yet, and the
        extreme is the highest, where the most has. `emax` and
        `dynamic_range` used to read `peak`, so an inhibitor's maximal
        effect was reported as its vehicle control and its dynamic range
        as exactly zero. Emax is maximal EFFECT, and for an inhibitor the
        effect is the fall.
        """
        baseline = self.baseline
        return max(self.points, key=lambda p: abs(p.response - baseline))

    @property
    def trough(self) -> DosePoint:
        return min(self.points, key=lambda p: p.response)

    @property
    def span(self) -> float:
        """Largest readout minus smallest, in the readout's own units."""
        return self.peak.response - self.trough.response

    @property
    def rising(self) -> bool:
        """Whether the readout is higher at the top dose than the bottom."""
        return self.points[-1].response >= self.points[0].response

    @property
    def reversal(self) -> float:
        """How far the curve turns back on itself, as a fraction of its span.

        Exactly zero for any monotone curve, in either direction, and it has
        to be exact rather than approximate or the threshold would be
        measuring the metric instead of the curve.

        The construction: track the largest fall below a preceding maximum
        (a drawdown) and the largest rise above a preceding minimum. A
        non-decreasing curve has no drawdown; a non-increasing curve has no
        rise; a curve that goes up and then down has both, and the SMALLER
        of the two is how far it reversed. Taking the smaller is what makes
        the measure direction-blind: an inhibitor's falling curve is not a
        reversal, and neither is an agonist's rising one.
        """
        responses = self.responses
        span = self.span
        if span <= 0.0:
            return 0.0
        peak = trough = responses[0]
        drawdown = rise = 0.0
        for value in responses:
            peak = max(peak, value)
            trough = min(trough, value)
            drawdown = max(drawdown, peak - value)
            rise = max(rise, value - trough)
        return min(drawdown, rise) / span

    @property
    def monotonic(self) -> bool:
        """Whether an EC50 is defined for this curve at all."""
        return self.reversal <= MONOTONIC_TOLERANCE

    @property
    def flat(self) -> bool:
        """Whether the dose moves the readout by anything worth calling a
        response."""
        scale = max((abs(value) for value in self.responses), default=0.0)
        return self.span <= FLAT_TOLERANCE * max(scale, 1e-300)

    def dose_with_unit(self, dose: float) -> str:
        """A dose formatted with its unit, or plainly without one."""
        return f"{dose:.4g} {self.dose_unit}" if self.dose_unit else f"{dose:.4g}"

    def summary(self) -> str:
        lines = [
            f"{self.readout} at steady state over {len(self.points)} "
            f"doses of {self.input_species}, from "
            f"{self.dose_with_unit(self.points[0].dose)} to "
            f"{self.dose_with_unit(self.points[-1].dose)}. The dose is held "
            f"fixed at each point, as it is in a bath, rather than consumed."
        ]

        if self.flat:
            lines.append(
                f"The readout does not move: it spans {self.span:.3g} over "
                f"the whole dose range, which is below the "
                f"{FLAT_TOLERANCE:g} of its own magnitude that counts as a "
                f"response. That is a finding about this pair -- either "
                f"{self.input_species} does not reach {self.readout} "
                f"through the mechanism as written, or every dose tested is "
                f"already saturating."
            )
        elif self.monotonic:
            direction = "rises" if self.rising else "falls"
            lines.append(
                f"The readout {direction} monotonically, from "
                f"{self.baseline:.4g} to {self.points[-1].response:.4g} -- "
                f"a span of {self.span:.4g}. An EC50 is defined for this "
                f"shape."
            )
        else:
            lines.append(
                f"The readout is BIPHASIC: it peaks at "
                f"{self.peak.response:.4g} at a dose of "
                f"{self.dose_with_unit(self.peak.dose)} and reverses by "
                f"{self.reversal:.0%} of its span. No EC50 exists for this "
                f"curve -- two different doses give every response between "
                f"the ends, so 'the dose at half-maximal response' names "
                f"two numbers rather than one."
            )

        if self.unmeasured:
            lines.append(
                f"{len(self.unmeasured)} of the constants this curve rests "
                f"on have no measured value behind them ("
                + ", ".join(self.unmeasured[:5])
                + (", ..." if len(self.unmeasured) > 5 else "")
                + "). Anything read off this curve is therefore what the "
                "SHAPE of the mechanism implies at the library's "
                "illustrative values, and is not a prediction about any "
                "particular protein. Ground those constants and the same "
                "computation becomes comparable to a measured curve, which "
                "is the whole reason for computing it."
            )

        lines.append(
            f"Computed from the mechanism, not fitted to data: each point "
            f"is the unique stable steady state at that dose, found from "
            f"{self.points[0].starts_tried} starting points and converged "
            f"to a residual of at most "
            f"{max(p.residual for p in self.points):.1g}."
        )
        return " ".join(lines)


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------


def _core_network() -> Any:
    try:
        from caterva.core import network as module  # type: ignore
    except ImportError:  # pragma: no cover - flat import
        from core import network as module  # type: ignore[no-redef]
    return module


def _stability_module() -> Any:
    try:
        from . import analysis  # type: ignore
    except ImportError:  # pragma: no cover - flat import
        import analysis  # type: ignore[no-redef]
    return analysis


def clamped(network: Any, species_id: str, value: float) -> Any:
    """The same network with one species HELD at `value`.

    What a bath does to a drug: the concentration is whatever was pipetted
    in, the system's consumption of it does not move that number, and the
    species stops being a state variable. SBML calls it a boundary
    condition and this is the same operation -- the species is dropped, a
    parameter of the same name and value takes its place, and the species
    is stripped out of every stoichiometry so the mass it supplies comes
    from outside the model.

    The rate laws are left exactly as written. Every symbol that referred to
    the species now resolves to the parameter, which is the whole trick: the
    mechanism is unchanged and only the bookkeeping about where the
    molecules come from has moved.

    A rate rule driving the clamped species is DROPPED, because a clamp and
    a rate rule are two determinations of one quantity and SBML forbids
    that. Silently keeping both would let the rule fight the clamp and
    produce a converged answer to a question nobody asked.

    Public because a dose-response usually holds more than one thing fixed.
    An inhibitor assay holds the substrate as well as the drug, and the
    substrate is held by the caller, with this, before `curve` varies the
    drug.
    """
    core = _core_network()
    known = {s.id for s in network.species}
    if species_id not in known:
        raise DoseResponseUnavailable(
            f"no species {species_id!r} to clamp in this network. It has: "
            f"{', '.join(sorted(known))}. A parameter is already a constant "
            f"and does not need clamping -- to vary one, use "
            f"compose/bifurcation.py's sweep, which asks a different "
            f"question."
        )
    if len(known) == 1:
        raise DoseResponseUnavailable(
            f"clamping {species_id!r} would leave this network with no "
            f"species at all, so there would be nothing left to solve for "
            f"and no readout to report. A dose-response needs something "
            f"downstream of the dose to read; add the species the dose acts "
            f"on, or ask this question of a larger model."
        )

    def without(mapping: Mapping[str, int]) -> Dict[str, int]:
        return {k: v for k, v in mapping.items() if k != species_id}

    return replace(
        network,
        species=tuple(s for s in network.species if s.id != species_id),
        parameters=tuple(network.parameters)
        + (core.Parameter(species_id, float(value)),),
        reactions=tuple(
            replace(r, reactants=without(r.reactants), products=without(r.products))
            for r in network.reactions
        ),
        rate_rules=tuple(
            rule for rule in network.rate_rules if rule.target != species_id
        ),
    )


def _mentions(network: Any, species_id: str) -> bool:
    """Whether any rate law or rule expression names this species.

    By whole token: `S` must not match `Ksi`, and `X` must not match `Xp`.
    The same rule as `sensitivity.law_mentions`, for the same reason -- a
    substring match would report that a dose reaches a readout it never
    touches.
    """
    sources = [r.rate_law for r in network.reactions]
    sources += [rule.expression for rule in network.rate_rules]
    sources += [rule.expression for rule in network.assignment_rules]
    return any(
        species_id in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text) for text in sources
    )


# ---------------------------------------------------------------------------
# Computing the curve
# ---------------------------------------------------------------------------


def curve(
    network: Any,
    input_species: str,
    readout: str,
    doses: Sequence[float],
    *,
    dose_unit: Optional[str] = None,
    unmeasured: Sequence[str] = (),
    starts_per_species: int = STARTS_PER_SPECIES,
) -> DoseResponse:
    """The steady-state `readout` at each dose of `input_species`.

    At every dose the input is clamped and the remaining system is searched
    globally for its steady states, at `sensitivity.STARTS_PER_SPECIES`
    starting points per species -- the depth that module MEASURED to be
    necessary before a refusal about multiple states means anything. A
    shallower search reports one stable state for models that have two, and
    a dose-response built on that would be a smooth curve through points
    that each silently picked an attractor.

    REFUSES AT THE FIRST DOSE WITH NO UNIQUE STABLE STATE, naming it, rather
    than dropping the point. Dropping it is the tempting thing: the curve
    still draws, the gap closes up, and the figure looks like a
    dose-response with a slightly coarser sampling. What is actually there
    is a system that switches -- the dose window where a genetic toggle has
    both states available is exactly the interesting part -- and a curve
    with that window quietly deleted is a drawing of a different mechanism.
    A missing point is not a missing number; it is a missing behaviour.

    `doses` are sorted before use and may include zero, which is the vehicle
    control. Negative doses are refused: a negative concentration is not a
    small one.
    """
    analysis = _stability_module()

    species_ids = [s.id for s in network.species]
    if input_species not in species_ids:
        raise DoseResponseUnavailable(
            f"no species {input_species!r} in this network, so there is "
            f"nothing to dose. It has: {', '.join(sorted(species_ids))}. If "
            f"{input_species!r} is a rate constant rather than something you "
            f"pipette, the question is a parameter sweep -- see "
            f"compose/bifurcation.py."
        )
    if readout == input_species:
        raise DoseResponseUnavailable(
            f"the readout and the dose are both {readout!r}. A clamped "
            f"species is held at whatever it was set to, so that curve is "
            f"the line y = x and measures the clamp rather than the "
            f"mechanism. Read out something the dose acts ON -- the complex "
            f"it forms, the product it drives, the species it represses."
        )
    if readout not in species_ids:
        raise DoseResponseUnavailable(
            f"no species {readout!r} to read out. This network has: "
            f"{', '.join(sorted(species_ids))}."
        )
    if not _mentions(network, input_species):
        raise DoseResponseUnavailable(
            f"no rate law in this network mentions {input_species!r}, so "
            f"changing its concentration cannot change anything. The curve "
            f"would be flat for a structural reason rather than a "
            f"pharmacological one, and reporting a flat curve would invite "
            f"the reading that the dose was tried and did nothing."
        )

    ordered = sorted(float(d) for d in doses)
    if len(ordered) < 2:
        raise DoseResponseUnavailable(
            f"a dose-response needs at least two doses; {len(ordered)} were "
            f"given. One dose is a measurement, not a curve."
        )
    if ordered[0] < 0.0:
        raise DoseResponseUnavailable(
            f"dose {ordered[0]:g} is negative. A negative concentration is "
            f"not a small dose, it is a unit or sign error."
        )

    points: List[DosePoint] = []
    for dose in ordered:
        held = clamped(network, input_species, dose)
        try:
            report = analysis.analyse(held, starts_per_species=starts_per_species)
        except Exception as exc:  # noqa: BLE001 - the dose is the useful part
            raise DoseResponseUnavailable(
                f"the steady states at a dose of {dose:g} could not be "
                f"found: {exc}"
            ) from exc

        stable = report.stable_points
        if not stable:
            raise DoseResponseUnavailable(
                f"no stable steady state at a dose of {dose:g}, from "
                f"{report.starts_tried} starting points, so there is no "
                f"readout to plot there. This point is NOT dropped and the "
                f"curve is not drawn around it: a dose at which the system "
                f"does not settle is a property of the mechanism, and a "
                f"model whose readout runs away above some dose is telling "
                f"you something a smoothed curve would hide. Ask for a time "
                f"course at this dose, which is what an unbounded system "
                f"has instead of a steady state."
            )
        if len(stable) > 1:
            values = ", ".join(
                f"{readout}={p.state[readout]:.4g}" for p in stable
            )
            raise DoseResponseUnavailable(
                f"{len(stable)} stable steady states at a dose of "
                f"{dose:g} ({values}), so there is no single readout at this "
                f"dose. The system switches here, and which state it is in "
                f"depends on where it came from -- which is hysteresis, the "
                f"behaviour a dose-response curve cannot represent, and not "
                f"a numerical difficulty. Reporting either value would be "
                f"choosing one silently; averaging them would report a state "
                f"the system is never in. Map the window with "
                f"compose/bifurcation.py's sweep, which is built to follow "
                f"branches through a fold."
            )

        point = stable[0]
        if readout not in point.state:
            raise DoseResponseUnavailable(
                f"{readout!r} is not in the solved state at a dose of "
                f"{dose:g}; clamping {input_species!r} removed it from the "
                f"system being solved."
            )
        points.append(
            DosePoint(
                dose=dose,
                response=float(point.state[readout]),
                residual=float(point.residual),
                starts_tried=int(report.starts_tried),
            )
        )

    return DoseResponse(
        input_species=input_species,
        readout=readout,
        points=tuple(points),
        dose_unit=dose_unit,
        unmeasured=tuple(unmeasured),
        starts_per_species=starts_per_species,
    )


def curve_for_model(model: Any, *args: Any, **kwargs: Any) -> DoseResponse:
    """`curve`, with the unit and the unmeasured list the model carries.

    This is the entry point worth using, for the same reason
    `scale.check_model` is. A bare network has forgotten what unit its
    numbers are in and never knew which of them were placeholders, so a
    curve built from one can report an EC50 without a unit and without the
    caveat that the constants behind it were never measured. Both omissions
    are silent, and both change what the number means.
    """
    kwargs.setdefault("dose_unit", dose_unit_of(model))
    # `model.unmeasured`, not `model.resolvable`. A ProvenancedModel has no
    # `resolvable` -- it has origins -- so the old getattr defaulted to ()
    # and a curve over placeholders reported that none of its constants
    # were placeholders. Both model classes answer `unmeasured` from what
    # they actually carry.
    kwargs.setdefault("unmeasured", tuple(getattr(model, "unmeasured", ()) or ()))
    return curve(model.network, *args, **kwargs)


def dose_unit_of(model: Any) -> Optional[str]:
    """The unit a dose -- and so an EC50 fitted to it -- is in.

    RECOVERED, NOT ASSUMED, from two places because neither is sufficient.
    `core.network.Species` carries an amount and no unit at all -- a dose
    IS a species concentration, so that gap is the one that matters here.
    `core.network.Parameter` DOES carry its unit now, populated by the
    builder from the motif that declared it, so a composed network
    describes its own constants; `scale.units_from_model` remains the
    fallback for a network built outside the composer, which carries none.

    The composition declares one concentration unit for the whole model and
    that is the authority for a dose, because a dose IS a species
    concentration. The recovered parameter units are the check on it: an
    affinity sits inside `Km + S`, so an affinity declared in a unit the
    species are not in means the model adds two different units together
    and the unit belonging on an EC50 is a guess between them. That is
    reported here rather than resolved -- printing an EC50 in the wrong unit
    is worse than printing it in none, because a number offered for
    comparison with a measurement will be compared.

    `None` when the model declares nothing, which is the honest answer for
    a network assembled outside the builder.
    """
    try:
        from .scale import units_from_model
        from .units import parse_unit
    except ImportError:  # pragma: no cover - flat import
        from scale import units_from_model  # type: ignore[no-redef]
        from units import parse_unit  # type: ignore[no-redef]

    composition = getattr(getattr(model, "recognition", None), "composition", None)
    declared = getattr(composition, "concentration_unit", None)
    if not declared:
        return None

    species_unit = parse_unit(declared)
    for name, text in sorted(units_from_model(model).items()):
        try:
            unit = parse_unit(text)
        except Exception:  # noqa: BLE001 - an unparseable unit is not a clash
            continue
        # Only a bare concentration can clash with a concentration. A kcat
        # in 1/s and a synthesis rate in mM/s have different dimensions and
        # are never added to a species amount.
        if unit.same_dimensions(species_unit) and not unit.agrees_with(species_unit):
            raise DoseResponseUnavailable(
                f"this model's species are in {declared} but {name} is "
                f"declared in {text}, and the two are added together inside "
                f"a rate law. A dose and an EC50 are concentrations, so "
                f"which of those units an EC50 would be in is undecided -- "
                f"and an EC50 is quoted precisely so it can be compared "
                f"with a measured one, where a factor of a thousand is not "
                f"a rounding difference. Fix the declared units first; "
                f"Composition.unit_findings() reports the rate law that "
                f"does not balance."
            )
    return str(declared)


# ---------------------------------------------------------------------------
# The fit
# ---------------------------------------------------------------------------


def hill_response(
    dose: float, basal: float, saturated: float, ec50: float, slope: float
) -> float:
    """The Hill equation, evaluated without overflowing.

        y(d) = basal + (saturated - basal) * d^h / (EC50^h + d^h)

    Computed as a logistic in log-dose, which is the same function:
    d^h / (EC50^h + d^h) = 1 / (1 + (EC50/d)^h) = sigma(h * ln(d / EC50)).
    The direct form overflows for a steep slope at a dose far from the
    midpoint -- h = 6 and a dose a thousand-fold below EC50 already asks for
    1e-18 over 1e-18 -- and the logistic form is bounded everywhere, which
    matters because a fit walks through parameter values nobody chose.

    At a dose of zero the response is `basal` exactly: the vehicle control
    is a legitimate point on this curve and is not a limit that has to be
    approached.
    """
    if dose <= 0.0:
        return float(basal)
    exponent = slope * (math.log(dose) - math.log(ec50))
    return float(basal) + (float(saturated) - float(basal)) * _logistic(exponent)


def _logistic(x: float) -> float:
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    value = math.exp(x)
    return value / (1.0 + value)


@dataclass(frozen=True)
class HillFit:
    """Four numbers describing the shape of a curve, and their residual."""

    #: The dose at half the distance from `basal` to `saturated`. For a
    #: falling curve the same number is conventionally called an IC50; the
    #: arithmetic is identical and `describe` uses the right word.
    ec50: float
    #: HOW STEEP THE CURVE IS AT ITS MIDPOINT, AND NOTHING ELSE.
    #:
    #: NOT a count of binding sites, NOT a count of subunits, and NOT
    #: evidence about the structure of any protein. It is a shape parameter
    #: of a curve: real-valued, routinely non-integer, bounded above by the
    #: number of sites and equal to it only in the unreachable all-or-none
    #: limit, and it moves with the conditions of the assay while the number
    #: of subunits does not. Haemoglobin has four sites and a slope near
    #: 2.8.
    #:
    #: Here there is a sharper reason to be careful. This slope was fitted
    #: to a curve computed FROM A RATE LAW, so when the mechanism is exactly
    #: Hill-shaped the slope comes back equal to the exponent that was
    #: written into the rate law. That agreement is a property of the model
    #: as declared, not a measurement of a protein -- reading it as a site
    #: count would promote one of the model's own assumptions into a finding
    #: about biology.
    hill_slope: float
    #: The fitted response at zero dose.
    basal: float
    #: The fitted response at infinite dose. An ASYMPTOTE: no dose reaches
    #: it, and `saturating` says whether the doses tested came close enough
    #: for it to be an observation rather than an extrapolation.
    saturated: float
    #: Root-mean-square of (fitted - computed), in the readout's own units.
    residual: float
    #: The same residual as a fraction of the curve's span, which is the
    #: form that is comparable between models. The absolute one is not:
    #: readouts differ by orders of magnitude between models.
    relative_residual: float
    points: int
    lowest_dose: float
    highest_dose: float
    dose_unit: Optional[str] = None

    @property
    def degrees_of_freedom(self) -> int:
        """Points minus the four parameters. Zero means the residual is
        arithmetic rather than evidence -- see `MINIMUM_DOSES`."""
        return self.points - 4

    @property
    def rising(self) -> bool:
        return self.saturated >= self.basal

    @property
    def approach(self) -> float:
        """The fraction of the fitted span the HIGHEST DOSE TESTED reaches.

        sigma(h * ln(d_max / EC50)) -- how far up its own curve the
        experiment actually got. 0.999 means the top dose is on the plateau;
        0.6 means the plateau was never seen and the fitted maximum is an
        extrapolation.
        """
        return _logistic(
            self.hill_slope
            * (math.log(self.highest_dose) - math.log(self.ec50))
        ) if self.highest_dose > 0.0 else 0.0

    @property
    def saturating(self) -> bool:
        """Whether the doses reached the plateau the EC50 is measured against.

        When this is false the EC50 is not merely uncertain, it is
        determined by the fit's guess about a maximum nobody observed: the
        half-maximal point is defined relative to that maximum, so an
        unobserved plateau propagates straight into the number quoted.
        """
        return self.approach >= PLATEAU_FRACTION

    @property
    def within_tested_doses(self) -> bool:
        """Whether the EC50 lies inside the range of doses used."""
        return self.lowest_dose <= self.ec50 <= self.highest_dose

    def response_at(self, dose: float) -> float:
        return hill_response(
            dose, self.basal, self.saturated, self.ec50, self.hill_slope
        )

    def describe(self) -> str:
        name = "EC50" if self.rising else "IC50"
        unit = f" {self.dose_unit}" if self.dose_unit else ""
        lines = [
            f"{name} = {self.ec50:.4g}{unit}, Hill slope = "
            f"{self.hill_slope:.4g}, from {self.basal:.4g} at zero dose to "
            f"{self.saturated:.4g} at saturation."
        ]
        lines.append(
            f"The fit reproduces the computed curve to an RMS residual of "
            f"{self.residual:.3g} ({self.relative_residual:.2g} of the "
            f"span) over {self.points} doses, {self.degrees_of_freedom} "
            f"degrees of freedom."
        )
        lines.append(
            f"THE HILL SLOPE IS NOT A SUBUNIT COUNT. {self.hill_slope:.4g} "
            f"describes how steeply this curve rises at its midpoint. It is "
            f"not the number of binding sites and not evidence about the "
            f"structure of anything -- a Hill slope is real-valued, is "
            f"bounded above by the site count and reaches it only in the "
            f"all-or-none limit, and moves with the conditions while the "
            f"number of subunits does not. Haemoglobin has four sites and a "
            f"slope near 2.8. This slope in particular was fitted to a "
            f"curve computed from a rate law, so it reports the exponent "
            f"that rate law was written with, which is an assumption of the "
            f"model rather than a measurement of a protein."
        )

        if not self.saturating:
            lines.append(
                f"THE PLATEAU WAS NOT REACHED: the highest dose tested "
                f"({self.highest_dose:.4g}{unit}) gets only "
                f"{self.approach:.0%} of the way to the fitted maximum, and "
                f"{name} is defined against that maximum. The number above "
                f"is therefore extrapolated rather than observed. Extend the "
                f"doses upward until the readout stops moving."
            )
        if not self.within_tested_doses:
            lines.append(
                f"The {name} sits OUTSIDE the doses tested "
                f"({self.lowest_dose:.4g} to {self.highest_dose:.4g}"
                f"{unit}), so no computed point is near it and its value "
                f"rests entirely on the shape the fit assumed."
            )
        if self.degrees_of_freedom <= 0:
            lines.append(
                "With no degrees of freedom the residual is a property of "
                "the arithmetic rather than evidence that this curve is "
                "Hill-shaped."
            )
        return " ".join(lines)


def fit_hill(response: DoseResponse) -> HillFit:
    """EC50 and Hill slope by least squares, with the residual reported.

    Four parameters -- basal, saturated, EC50 and slope -- fitted to the
    computed points. The same four-parameter logistic an experimentalist
    fits to a plate, so the number that comes out is the same KIND of number
    as theirs and can be put beside it.

    FITTED IN LOG DOSE, because that is where the curve is a sigmoid and
    where its parameters are separable. A dose ladder spans decades; in
    linear dose the points bunch at one end and the fit is driven almost
    entirely by the top of the range.

    THE SLOPE IS CONSTRAINED POSITIVE AND THE DIRECTION IS CARRIED BY THE
    ASYMPTOTES. The model is invariant under swapping basal with saturated
    and negating the slope -- the two describe the same curve EXACTLY, not
    approximately, which `TestTheDirectionIsCarriedByTheAsymptotes` checks
    against `hill_response` directly. Allowing both makes the fit
    non-identifiable, and which of two equivalent answers came back would
    depend on the starting guess rather than on the data. A falling curve
    gets `saturated < basal` and a positive slope, and `describe` calls the
    midpoint an IC50.

    THE BOUND IS INTENT, NOT THE ONLY THING HOLDING THE SIGN, and that is
    worth saying because it is measurable. A mutation removing the lower
    bound came back NOT CAUGHT: the fit starts at a slope of +1, the
    positive branch is a global minimum for every curve the library
    produces, and the optimiser has no reason to cross zero to reach the
    mirror image. So on these inputs the bounded and unbounded rules agree,
    and the bound earns its place on the curves that are yet to be fitted --
    a badly conditioned one where the optimiser wanders, or a caller's
    starting guess on the other side. Recorded rather than deleted, and
    recorded rather than claimed as load-bearing: the equivalence it rests
    on is the thing the tests can actually falsify, so that is what they
    test.

    REFUSES ON A CURVE THAT IS NOT MONOTONIC. See the module docstring: for
    a biphasic curve the EC50 does not exist rather than being hard to find,
    and substrate inhibition produces one from a mechanism the library
    ships. `emax` and `dynamic_range` still work on such a curve and are the
    honest things to report from it.
    """
    if len(response.points) < MINIMUM_DOSES:
        raise DoseResponseUnavailable(
            f"a four-parameter Hill fit through {len(response.points)} "
            f"points has {len(response.points) - 4} degrees of freedom. "
            f"Below {MINIMUM_DOSES} doses the residual measures the "
            f"arithmetic rather than the curve, and a small one would read "
            f"as a good fit when it is an interpolation. Recompute the "
            f"curve on more doses -- `bifurcation.logarithmic_values` "
            f"spaces them the way a dose-response is read -- and put them "
            f"where the curve turns rather than on the plateau."
        )
    if response.flat:
        raise DoseResponseUnavailable(
            f"the readout moves by {response.span:.3g} over the whole dose "
            f"range, which is less than {FLAT_TOLERANCE:g} of its own "
            f"magnitude. There is no curve here to find a midpoint of: an "
            f"EC50 fitted to a flat line is the dose at the middle of "
            f"nothing, and its value would be decided by where the fit "
            f"happened to start. Either the dose does not reach this "
            f"readout through the mechanism as written, or every dose "
            f"tested is already saturating -- widen the range downward to "
            f"tell those apart."
        )
    if not response.monotonic:
        peak = response.peak
        raise NotMonotonic(
            f"this curve is biphasic: {response.readout} rises to "
            f"{peak.response:.4g} at a dose of "
            f"{response.dose_with_unit(peak.dose)} and then reverses by "
            f"{response.reversal:.0%} of its span. EC50 means the dose at "
            f"half-maximal response, and this curve has TWO doses at every "
            f"response between its ends -- one on the way up and one on the "
            f"way down -- so there is no such dose to report. A Hill fit "
            f"would still return four numbers and a residual, and the EC50 "
            f"among them would describe nothing. Substrate inhibition is "
            f"exactly this shape, and its peak sits at sqrt(Km * Ksi). "
            f"Report instead: the peak ({response.readout} = "
            f"{peak.response:.4g} at "
            f"{response.dose_with_unit(peak.dose)}), the two limbs "
            f"separately if a midpoint is wanted on either, and -- since "
            f"this curve came from a mechanism rather than a plate -- the "
            f"mechanism's own constants, which describe the whole curve "
            f"instead of summarising half of it."
        )

    doses = list(response.doses)
    values = list(response.responses)
    positive = [d for d in doses if d > 0.0]
    if len(set(positive)) < 2:
        raise DoseResponseUnavailable(
            f"a Hill fit needs at least two distinct positive doses; this "
            f"curve has {len(set(positive))}. EC50 is a position on a log "
            f"dose axis and a single point does not locate one."
        )

    try:
        import numpy as np
        from scipy.optimize import least_squares
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise DoseResponseUnavailable(
            f"fitting needs numpy and scipy, which are in requirements.txt "
            f"but not importable here: {exc}"
        ) from exc

    basal, saturated = values[0], values[-1]
    midpoint = (basal + saturated) / 2.0
    # The dose whose computed response is nearest the halfway level. A
    # guess, and a good one: on a real Hill curve it is within one step of
    # the answer, which keeps the fit out of the flat tails where the
    # gradient in log EC50 vanishes.
    guess = min(
        (d for d in positive),
        key=lambda d: abs(values[doses.index(d)] - midpoint),
    )

    start = [basal, saturated, math.log(guess), 1.0]
    lower = [-np.inf, -np.inf, -np.inf, MIN_HILL_SLOPE]
    upper = [np.inf, np.inf, np.inf, np.inf]

    def residuals(theta: Sequence[float]) -> List[float]:
        low, high, log_ec50, slope = theta
        ec50 = math.exp(log_ec50)
        return [
            hill_response(dose, low, high, ec50, slope) - value
            for dose, value in zip(doses, values)
        ]

    outcome = least_squares(
        residuals, start, bounds=(lower, upper),
        xtol=FIT_TOLERANCE, ftol=FIT_TOLERANCE, gtol=FIT_TOLERANCE,
    )
    if not outcome.success:
        raise DoseResponseUnavailable(
            f"the Hill fit did not converge ({outcome.message}). The curve "
            f"is monotone, so a midpoint exists; what failed is the "
            f"four-parameter description of it, which means this curve is "
            f"not Hill-shaped. Report the computed points, or the "
            f"mechanism's own constants."
        )

    low, high, log_ec50, slope = (float(v) for v in outcome.x)
    errors = list(outcome.fun)
    rms = math.sqrt(sum(e * e for e in errors) / len(errors))

    return HillFit(
        ec50=math.exp(log_ec50),
        hill_slope=slope,
        basal=low,
        saturated=high,
        residual=rms,
        relative_residual=rms / response.span if response.span > 0 else float("inf"),
        points=len(doses),
        lowest_dose=doses[0],
        highest_dose=doses[-1],
        dose_unit=response.dose_unit,
    )


# ---------------------------------------------------------------------------
# Named readouts
# ---------------------------------------------------------------------------


def ec50(response: DoseResponse) -> float:
    """The dose at half-maximal response, from the fit.

    Refuses for a biphasic curve, because the quantity does not exist there
    -- see `fit_hill`. For a falling curve this is what the literature calls
    an IC50; it is the same number and `HillFit.describe` uses the right
    name for it.

    FITTED rather than interpolated between the two nearest points. The
    fitted value uses every point and the shape they share; a linear
    interpolation between the two straddling the midpoint uses two points
    and a straight line, and on a log dose axis a straight line is not what
    the curve does between them.
    """
    return fit_hill(response).ec50


def emax(response: DoseResponse) -> float:
    """The largest response OBSERVED over the doses given.

    Not `HillFit.saturated`, and the difference is the point. The fitted
    asymptote is the response at infinite dose, which no experiment applies
    and this module does not compute; this is the largest readout at a dose
    that was actually put in. When the curve has plateaued the two agree,
    and when it has not, this is the one that is a measurement of the model
    rather than an extrapolation of a fit -- `HillFit.saturating` says
    which case a given curve is in.

    Defined for a biphasic curve, where it is the peak, and returned for one
    without complaint. Only the EC50 assumes a shape substrate inhibition
    does not have.

    FOR A FALLING CURVE THIS IS THE LOWEST RESPONSE, not the highest. Emax
    is maximal effect. An inhibitor's maximal effect is its maximal
    suppression, and the first version of this read `peak` -- the largest
    response -- which for an inhibitor is the untreated baseline. That
    reported the vehicle control as the drug's Emax.
    """
    return response.extreme.response


def dynamic_range(response: DoseResponse) -> float:
    """How far the readout moves: `emax` minus the response at the lowest dose.

    A SPAN, IN THE READOUT'S OWN UNITS, not a fold-change. A fold-change is
    what most people mean by dynamic range and it is undefined for the
    commonest case in this library: a readout with no constitutive activity
    sits at exactly zero before the dose, and dividing by it gives
    infinity. A span is defined for every curve, and a reader who wants the
    ratio can take it knowing whether the denominator was zero.

    Measured from the LOWEST DOSE TESTED, which is not necessarily zero. If
    the lowest dose is already active this understates the range, and
    `DoseResponse.summary` prints the dose it was measured from so that is
    visible rather than assumed.

    SIGNED. Positive for a rising curve, negative for a falling one, and
    the sign is the direction of the effect -- an activator raises the
    readout and an inhibitor lowers it, and a reader given only the
    magnitude has to look elsewhere to learn which. The first version
    read `peak - baseline`, which for a falling curve is `baseline -
    baseline`: every inhibitor had a dynamic range of exactly zero.
    """
    return response.extreme.response - response.baseline


__all__ = [
    "DosePoint", "DoseResponse", "DoseResponseUnavailable", "HillFit",
    "NotMonotonic",
    "clamped", "curve", "curve_for_model", "dose_unit_of", "ec50", "emax",
    "dynamic_range", "fit_hill", "hill_response",
    "FIT_TOLERANCE", "FLAT_TOLERANCE", "MINIMUM_DOSES", "MIN_HILL_SLOPE",
    "MONOTONIC_TOLERANCE", "PLATEAU_FRACTION", "STARTS_PER_SPECIES",
]
