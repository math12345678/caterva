"""Exact stochastic simulation of a composed model, and when you need it.

WHY THIS IS A DIFFERENT ANSWER AND NOT A NOISIER ONE
-----------------------------------------------------
The ODE in `compose/simulate.py` is a large-number approximation. It is the
limit of the chemical master equation as the copy number goes to infinity,
and it is excellent at a millimolar concentration in a test tube, where the
number of molecules is order 1e17 and the relative fluctuation is order
1e-9.

A gene has one copy. A transcription factor is present at tens of molecules
per cell. At those numbers the smooth curve is not the mean of what happens
with a bit of scatter around it; it can be a qualitatively different claim:

  * a bistable switch has a finite chance of flipping on its own, and the
    ODE says the probability is exactly zero for all time;
  * a species the ODE holds at 0.4 molecules is either absent or present,
    and "0.4" describes neither state;
  * the mean of a nonlinear system is not the system evaluated at the mean,
    so even the average trajectory is not the deterministic one.

So this module is not a plotting variant of `simulate.py`. It answers a
question the ODE cannot be asked. `discreteness_matters` is the check that
says whether you are in that regime, and it is meant to be run BEFORE
trusting a deterministic answer, not after being surprised by one.

THE VOLUME IS REQUIRED AND HAS NO DEFAULT
-----------------------------------------
A `ReactionNetwork` holds concentrations. A propensity is defined over
COUNTS. The conversion between them is the system volume, and it is the
only thing in this module that cannot be derived from the model:

    molecules = concentration * volume * Avogadro

Every number a stochastic run produces is set by that factor. The same
network at 1 mM has 6e17 molecules in a millilitre and 600 in a
femtolitre; the first is indistinguishable from the ODE and the second is
dominated by noise. A stochastic result reported without its volume is not
an imprecise result, it is not a result -- the reader cannot tell which of
those two systems was simulated.

Hence `volume` is a required keyword argument everywhere it appears, and so
is `concentration_unit`. Neither has a default and neither ever will. mM
and uM are dimensionally identical and differ by a thousand in copy number,
which is the entire content of the answer; a default there would be a
silent factor of a thousand, and `compose/units.py` already declines to
convert silently for exactly this reason.

THE MASS-ACTION CHECK IS THE POINT OF THE MODULE
------------------------------------------------
A propensity is only defined for an ELEMENTARY reaction. Gillespie's
derivation counts collisions: the probability that a particular
combination of reactant molecules reacts in the next dt is a constant
times dt, and the propensity is that constant times the number of distinct
combinations available. That argument needs the reaction to be a physical
event with a fixed set of participants.

A Michaelis-Menten rate law is not such an event. `kcat*E*S/(Km+S)` is what
is LEFT of the mechanism E + S <-> ES -> E + P after the quasi-steady-state
assumption has averaged the complex away -- and that assumption is itself a
large-number argument, the same one the ODE makes. Simulating it with the
SSA applies a small-number method to a large-number approximation. The
result is neither the exact stochastic answer nor the deterministic one; it
is a Markov chain whose jump rates were borrowed from a model of a
different thing, and nothing about the output says so.

So a non-mass-action rate law is REFUSED, by name, with the mechanism the
caller should write instead. That refusal is the most valuable thing here:
running the simulation anyway is easy, produces a plot, and is wrong in a
way no plot shows.

WHAT COUNTS AS MASS ACTION, PRECISELY
-------------------------------------
The rate law must be a MONOMIAL: a constant coefficient (numbers and
parameters, in any arithmetic) multiplied by species raised to non-negative
INTEGER LITERAL powers. Anything else is refused:

    a species in a denominator          saturation; not a collision count
    a species inside a sum              saturation; the Michaelis-Menten
                                        and Hill shapes
    a species raised to a parameter     a Hill coefficient is a fitted
                                        description of cooperativity, not
                                        a number of colliding molecules
    a function call                     no collision interpretation

and one more that is about the stoichiometry rather than the algebra: a
species the reaction CONSUMES must appear in the rate law raised to exactly
its stoichiometric coefficient. `zero_order_degradation` in the motif
library is the case -- it consumes X at rate `v_max`, which does not
mention X -- and the motif's own basis already says the law "would drive
the species negative". In the ODE that is a modelling caveat. In the SSA it
is a propensity that stays positive when the count is zero, so the chain
walks X to -1, and there is no such state.

THE COMBINATORIAL CORRECTION IS NOT COSMETIC
--------------------------------------------
For a monomial of total order m, with species powers p_i, the propensity is

    a(n) = k * Omega^(1-m) * prod_i [ n_i * (n_i - 1) * ... * (n_i - p_i + 1) ]

-- a falling factorial, not a power. The two agree to O(1/n) and disagree
completely where this module is used. Dimerisation (2M -> D) at n = 2 has
propensity k*2*1/Omega; the naive k*n^2/Omega is twice that, because it
lets a molecule collide with itself. At n = 1 the exact propensity is zero
and the naive one is not, which is the difference between a reaction that
cannot happen and one that happens at a quarter speed.

WHY THIS IS NOT `Terium/discrete/gillespie_ssa.py`
--------------------------------------------------
That module was searched for first and IS the house SSA, but its interface
does not reach a composed model and could not be made to without becoming
this module. It exposes `simulate_gillespie_ssa(a0, k, end, seed)` and
`simulate_gillespie_ssa_bimolecular(a0, b0, k, end, seed)`: scalar counts
and one hard-coded rate constant, with the two reaction shapes written out
by hand as `a -= 1; b += 1`. There is no stoichiometry, no species vector,
no rate-law parsing and therefore nothing to refuse. ADR 0009 says this in
as many words -- "no multi-species networks in this stage ... leaves room
for a later extension (a reaction-network variant)" -- and this is that
extension for the compose layer.

What IS reused is its conventions, deliberately, so the two agree: the
Direct Method with tau = -ln(u)/a_total, `numpy.random.default_rng(seed)`
per ADR 0005, one row per event, and a final row snapped to the horizon so
the trajectory ends where every other domain's does.

ONE DELIBERATE DEVIATION FROM ADR 0005
--------------------------------------
`seed` here is REQUIRED and has no default, where the ADR specifies
`seed: int | None = None`. ADR 0005 permits a deviation with a stated
reason, and the reason is this module's purpose: its output is evidence
about whether a deterministic answer can be trusted. An unseeded run
cannot be reproduced, and a piece of evidence nobody can reproduce is not
evidence. `None` would still work as numpy entropy, which is why it is
excluded rather than merely discouraged.

WHAT THIS DOES NOT CLAIM
------------------------
That the system is well mixed. The SSA assumes it is -- that any molecule
is equally likely to meet any other -- and a cell is not a beaker.
Diffusion limitation, membranes and localisation all break the assumption,
and nothing here detects that; it is a property of the biology, not of the
model text.

That a copy number above `DISCRETENESS_THRESHOLD` makes stochastic effects
absent. It makes the RELATIVE fluctuation at steady state small. Rare
events -- the switch that flips, the transcript that fails to appear --
have probabilities that fall exponentially with the copy number and never
reach zero, and a threshold on the mean says nothing about them.

That a single trajectory is an answer. It is one realisation. Anything
quantitative needs an ensemble, and the seed of each member has to be
stated for the ensemble to be reproducible.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from .units import BASE_CONCENTRATION, UnitError, parse_unit
except ImportError:  # pragma: no cover - flat import
    from units import (  # type: ignore[no-redef]
        BASE_CONCENTRATION, UnitError, parse_unit,
    )


#: Molecules per mole. FIXED BY DEFINITION, not measured: the 2019 revision
#: of the SI defines the mole as exactly this many entities, so the number
#: carries no uncertainty and no citation to a measurement would be
#: appropriate for it.
AVOGADRO = 6.02214076e23

#: The relative uncertainty a deterministic model of this kind already
#: carries from its constants.
#:
#: A JUDGEMENT, and the same one `compose/sensitivity.py` states when it
#: sets NEGLIGIBLE_INFLUENCE: enzyme constants are rarely known to better
#: than about +/-20%, and a composed model's placeholders are not known at
#: all. It is used here only to derive a threshold, and the derivation is
#: shown so the threshold can be argued with by arguing with this.
PARAMETER_UNCERTAINTY = 0.2

#: Copy number below which the deterministic answer should not be trusted.
#:
#: DERIVED, not chosen. For a birth-death process at steady state the
#: stationary distribution is Poisson, so the standard deviation is
#: sqrt(N) and the relative fluctuation is
#:
#:     sigma / mean = sqrt(N) / N = 1 / sqrt(N).
#:
#: That fluctuation is a real feature of the system which the ODE omits
#: entirely. It stops being the dominant error when it drops below the
#: error the model already has, which is PARAMETER_UNCERTAINTY:
#:
#:     1 / sqrt(N) < 0.2   <=>   N > 25.
#:
#: So at 25 copies the noise the deterministic model ignores is as large as
#: the uncertainty it admits to, and below that the ODE is wrong about the
#: thing it is most confident about. Above it, the ODE is not exact -- it
#: is merely no longer the biggest problem, which is a different and much
#: weaker claim, and `DiscretenessReport.summary` makes it in those words.
#:
#: Not a bound on rare events. A bistable system flips at any copy number;
#: the rate falls exponentially with N and is never zero, and no threshold
#: on a mean can speak to that.
DISCRETENESS_THRESHOLD = 25

#: How many reaction events a single run may fire before it gives up.
#:
#: The SSA costs one step per event, and the event rate grows with the copy
#: number: a system large enough to be expensive is a system large enough
#: not to need this module. Hitting the ceiling is therefore a refusal with
#: a real conclusion in it rather than a resource error -- see
#: `simulate_ssa`. Matched to ADR 0009's MAX_API_SSA_POPULATION, which
#: bounds the same quantity for the single-reaction domain.
DEFAULT_MAX_EVENTS = 1_000_000

#: How a run ended. Carried on the trajectory rather than inferred from it:
#: a run that stopped because nothing could happen and one that ran out of
#: horizon have identical last rows and completely different meanings.
ENDED_AT_HORIZON = "reached the end of the requested window"
ENDED_ABSORBED = "every propensity reached zero -- nothing further can happen"


class StochasticRefusal(RuntimeError):
    """The model was not simulated stochastically, and the message says why."""


class NotMassAction(StochasticRefusal):
    """A rate law has no propensity, because it is not a collision count.

    A subclass so a caller can distinguish "this model cannot be simulated
    stochastically at all" from "this particular run could not be set up".
    The first is a statement about the model and is not fixed by changing
    the volume or the seed.
    """


# ---------------------------------------------------------------------------
# Reading a rate law as a monomial
# ---------------------------------------------------------------------------


def _source(node: ast.AST, fallback: str) -> str:
    """The text of a sub-expression, for an error message."""
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001 - a message helper must not raise
        return fallback


def _refuse(reaction_id: str, rate_law: str, detail: str, advice: str) -> NotMassAction:
    """Build the refusal, always naming mass action.

    Every path out of the reader goes through here so that no refusal can
    describe a symptom without naming the property that was violated. A
    reader who is told "unsupported expression" learns nothing; one who is
    told the rate law is not mass action and therefore has no propensity
    knows both what is wrong and why nothing can be done about it inside
    this module.
    """
    return NotMassAction(
        f"reaction {reaction_id!r} does not have a MASS-ACTION rate law, so "
        f"it has no propensity and cannot be simulated stochastically. "
        f"{detail} Rate law: {rate_law!r}. {advice}"
    )


_MECHANISM_ADVICE = (
    "A propensity counts collisions between a fixed set of molecules, so it "
    "exists only for an elementary reaction. Write the mechanism the "
    "saturating law replaced -- E + S <-> ES -> E + P, three mass-action "
    "reactions, which `reversible_binding` and `mass_action_conversion` in "
    "`compose/library.py` already provide -- and simulate that. It has "
    "propensities; the reduced form does not, and simulating the reduced "
    "form would apply a small-number method to an approximation that "
    "assumed large numbers."
)


def _read_monomial(
    node: ast.AST,
    *,
    species: Mapping[str, int],
    parameters: Mapping[str, float],
    reaction_id: str,
    rate_law: str,
) -> Tuple[float, Dict[str, int]]:
    """`(coefficient, {species: power})` for a mass-action rate law.

    Recursive over the expression rather than pattern-matching the text,
    because `k*A*B`, `A*k*B` and `(2*k)*A*B` are the same law and a
    text-shaped check would accept one and refuse the others. The
    coefficient is evaluated numerically as it goes; only species carry
    powers, and every place a species can appear that is not a
    multiplicative factor raises.
    """
    def read(child: ast.AST) -> Tuple[float, Dict[str, int]]:
        """Recurse, carrying the context every refusal needs to name."""
        return _read_monomial(
            child,
            species=species,
            parameters=parameters,
            reaction_id=reaction_id,
            rate_law=rate_law,
        )

    if isinstance(node, ast.Expression):
        return read(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise _refuse(
                reaction_id, rate_law,
                f"the literal {node.value!r} is not a number.",
                "A rate law is arithmetic over numbers, parameters and "
                "species.",
            )
        return float(node.value), {}

    if isinstance(node, ast.Name):
        if node.id in species:
            return 1.0, {node.id: 1}
        if node.id in parameters:
            return float(parameters[node.id]), {}
        raise _refuse(
            reaction_id, rate_law,
            f"the symbol {node.id!r} is neither a species nor a parameter of "
            f"this network.",
            "Nothing can be evaluated for it, so no propensity can be "
            "formed. Check the name against the network's species and "
            "parameters.",
        )

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.UAdd):
            return read(node.operand)
        if isinstance(node.op, ast.USub):
            coefficient, powers = read(node.operand)
            return -coefficient, powers
        raise _refuse(
            reaction_id, rate_law,
            f"the unary operator in {_source(node, rate_law)!r} has no "
            f"meaning in a rate law.",
            "Only + and - apply to a rate.",
        )

    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Mult):
            left_coefficient, left_powers = read(node.left)
            right_coefficient, right_powers = read(node.right)
            powers = dict(left_powers)
            for name, power in right_powers.items():
                powers[name] = powers.get(name, 0) + power
            return left_coefficient * right_coefficient, powers

        if isinstance(node.op, ast.Div):
            numerator, numerator_powers = read(node.left)
            denominator, denominator_powers = read(node.right)
            if denominator_powers:
                raise _refuse(
                    reaction_id, rate_law,
                    f"the species "
                    f"{', '.join(sorted(denominator_powers))} "
                    f"appear(s) in a DENOMINATOR "
                    f"({_source(node.right, rate_law)!r}), so the rate "
                    f"saturates instead of being proportional to a product "
                    f"of concentrations.",
                    _MECHANISM_ADVICE,
                )
            if denominator == 0.0:
                raise _refuse(
                    reaction_id, rate_law,
                    f"the denominator {_source(node.right, rate_law)!r} "
                    f"evaluates to zero at the network's parameter values.",
                    "The coefficient is not finite, so there is no rate to "
                    "convert.",
                )
            return numerator / denominator, numerator_powers

        if isinstance(node.op, (ast.Add, ast.Sub)):
            left_coefficient, left_powers = read(node.left)
            right_coefficient, right_powers = read(node.right)
            offenders = sorted(set(left_powers) | set(right_powers))
            if offenders:
                raise _refuse(
                    reaction_id, rate_law,
                    f"the species {', '.join(offenders)} appear(s) inside a "
                    f"SUM ({_source(node, rate_law)!r}). A sum of that shape "
                    f"is what makes a rate saturate -- it is the "
                    f"Michaelis-Menten and Hill denominators -- and a "
                    f"saturating law is ALREADY a coarse-graining that "
                    f"assumed the molecule numbers were large enough to "
                    f"average the enzyme-substrate complex away.",
                    _MECHANISM_ADVICE,
                )
            if isinstance(node.op, ast.Add):
                return left_coefficient + right_coefficient, {}
            return left_coefficient - right_coefficient, {}

        if isinstance(node.op, ast.Pow):
            base_coefficient, base_powers = read(node.left)
            exponent_coefficient, exponent_powers = read(node.right)
            if exponent_powers:
                raise _refuse(
                    reaction_id, rate_law,
                    f"a species appears in an EXPONENT "
                    f"({_source(node.right, rate_law)!r}).",
                    "A propensity is polynomial in the counts; a count in "
                    "an exponent describes no collision.",
                )
            if not base_powers:
                return base_coefficient ** exponent_coefficient, {}
            literal = _integer_literal(node.right)
            if literal is None:
                raise _refuse(
                    reaction_id, rate_law,
                    f"the species "
                    f"{', '.join(sorted(base_powers))} "
                    f"is raised to {_source(node.right, rate_law)!r}, which "
                    f"is not a non-negative integer LITERAL. A Hill "
                    f"coefficient is a fitted description of cooperativity, "
                    f"not a count of colliding molecules, and its value "
                    f"happening to be integral today would not make it one.",
                    "An exponent in a propensity is how many molecules of "
                    "that species take part in the event, so it has to be "
                    "written as an integer in the model rather than resolved "
                    "from a parameter. "
                    + _MECHANISM_ADVICE,
                )
            return (
                base_coefficient ** literal,
                {name: power * literal for name, power in base_powers.items()},
            )

        raise _refuse(
            reaction_id, rate_law,
            f"the operator in {_source(node, rate_law)!r} is not one a rate "
            f"law may use.",
            "A mass-action rate law uses only multiplication, division by "
            "constants, and integer powers.",
        )

    if isinstance(node, ast.Call):
        raise _refuse(
            reaction_id, rate_law,
            f"the rate law calls a function "
            f"({_source(node, rate_law)!r}).",
            "No function of a molecule count is a collision count. If the "
            "call involves only constants, evaluate it and put the number "
            "in the parameter instead, where it can carry a provenance.",
        )

    raise _refuse(
        reaction_id, rate_law,
        f"{_source(node, rate_law)!r} is not an expression a rate law may "
        f"contain.",
        "A mass-action rate law is a product of constants and species.",
    )


def _integer_literal(node: ast.AST) -> Optional[int]:
    """The value of `node` if it is a non-negative integer literal."""
    if isinstance(node, ast.Constant) and not isinstance(node.value, bool):
        if isinstance(node.value, int) and node.value >= 0:
            return node.value
        if isinstance(node.value, float) and node.value >= 0 and node.value.is_integer():
            return int(node.value)
    return None


def _parse_rate_law(rate_law: str, reaction_id: str) -> ast.Expression:
    """Parse a rate law, translating `^` to Python's `**` first.

    The same translation `compose/analysis.py` makes and for the same
    reason: SBML and Antimony spell exponentiation `^`, Python spells XOR
    that way, and `2^3` is 1 rather than 8. Here the consequence would be
    worse than a wrong number -- `R^n` would parse as a BitXor, be refused
    as an operator a rate law may not use, and the refusal would name the
    wrong problem.
    """
    try:
        return ast.parse(rate_law.replace("^", "**"), mode="eval")
    except SyntaxError as exc:
        raise _refuse(
            reaction_id, rate_law,
            f"it does not parse as an expression ({exc}).",
            "Nothing can be checked or converted until it does.",
        ) from exc


def mass_action_problems(network: Any) -> Tuple[str, ...]:
    """Every reason this network has no propensity description, or ().

    Returns rather than raises so one refusal can name all of them at once,
    which is the same split `ReactionNetwork.problems` uses. A caller shown
    one non-mass-action reaction at a time will fix it, re-run, and be told
    about the next one; a caller shown four knows the model is the wrong
    shape for this method rather than one edit away from it.
    """
    problems: List[str] = []

    for rule in getattr(network, "rate_rules", ()):
        problems.append(
            f"species {getattr(rule, 'target', '?')!r} is driven by a RATE "
            f"RULE, not by reactions. A rate rule states a time derivative "
            f"directly; it has no reactants, no stoichiometry and no event "
            f"to have a propensity for. It cannot be decomposed into "
            f"reactions automatically either, because more than one "
            f"mechanism produces the same derivative and choosing one would "
            f"be inventing the mechanism."
        )
    for rule in getattr(network, "assignment_rules", ()):
        problems.append(
            f"quantity {getattr(rule, 'target', '?')!r} is set by an "
            f"ASSIGNMENT RULE. It is recomputed from other quantities rather "
            f"than changed by events, so there is no state for it in a "
            f"Markov chain over counts."
        )

    species = {s.id: index for index, s in enumerate(network.species)}
    parameters = {p.id: float(p.value) for p in network.parameters}

    for reaction in network.reactions:
        try:
            tree = _parse_rate_law(reaction.rate_law, reaction.id)
            coefficient, powers = _read_monomial(
                tree,
                species=species,
                parameters=parameters,
                reaction_id=reaction.id,
                rate_law=reaction.rate_law,
            )
        except NotMassAction as exc:
            problems.append(str(exc))
            continue

        if coefficient < 0.0:
            problems.append(
                f"reaction {reaction.id!r} has a rate law whose constant "
                f"coefficient is negative ({coefficient:g}) at this "
                f"network's parameter values. A propensity is a probability "
                f"per unit time and cannot be negative. A reaction that runs "
                f"backwards is a second reaction, written the other way "
                f"round, with its own positive rate constant."
            )

        for name, count in reaction.reactants.items():
            power = powers.get(name, 0)
            if power == count:
                continue
            if power == 0:
                problems.append(
                    f"reaction {reaction.id!r} consumes {name!r} but its rate "
                    f"law {reaction.rate_law!r} does not mention it. In an "
                    f"ODE that is a modelling caveat; in an exact simulation "
                    f"it is a propensity that stays positive when the count "
                    f"is zero, so the next event takes {name!r} to -1 and "
                    f"there is no such state. Mass action requires the rate "
                    f"to be proportional to the reactants, which is what "
                    f"makes it vanish as they run out."
                )
            else:
                problems.append(
                    f"reaction {reaction.id!r} consumes {count} x {name!r} "
                    f"but its rate law is order {power} in it. Mass action "
                    f"requires the rate to be proportional to each reactant "
                    f"raised to its stoichiometric coefficient; these "
                    f"disagree, so the law describes a different event from "
                    f"the one the stoichiometry declares and there is no "
                    f"single collision to count."
                )

    return tuple(problems)


def check_mass_action(network: Any) -> None:
    """Raise `NotMassAction` unless every reaction has a propensity."""
    problems = mass_action_problems(network)
    if not problems:
        return
    raise NotMassAction(
        f"{len(problems)} reason(s) this model has no propensity "
        f"description, so it cannot be simulated exactly:\n  - "
        + "\n  - ".join(problems)
    )


# ---------------------------------------------------------------------------
# The propensity description
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PropensityReaction:
    """One reaction, as an event over counts rather than a rate over
    concentrations."""

    id: str
    #: k * Omega^(1-m): the deterministic constant carried into count space.
    #: Multiplied by the falling factorials to give events per unit time.
    coefficient: float
    #: (species index, power in the rate law). Includes modifiers -- a
    #: catalyst is a collision partner even though it is not consumed.
    orders: Tuple[Tuple[int, int], ...]
    #: (species index, net change per event), from the STOICHIOMETRY. Kept
    #: separate from `orders` because the two are genuinely different
    #: questions: what has to meet, and what changes when it does. An
    #: enzyme appears in the first and not the second.
    net: Tuple[Tuple[int, int], ...]
    rate_law: str

    @property
    def order(self) -> int:
        return sum(power for _, power in self.orders)


@dataclass(frozen=True)
class PropensitySystem:
    """A network in counts, with everything the conversion depended on.

    The volume and the unit are carried rather than consumed, because a
    trajectory is only readable next to them: 40 molecules is a different
    statement in a bacterium and in a hepatocyte, and the numbers alone do
    not say which was meant.
    """

    name: str
    species: Tuple[str, ...]
    #: The integer state the run starts from.
    initial_counts: Tuple[int, ...]
    #: What the concentrations actually converted to, before rounding.
    #: Carried so the rounding is visible: an initial condition of 2.4
    #: molecules cannot be represented and the reader should see that it
    #: was 2.4, not discover a 2 with no history.
    expected_initial_counts: Tuple[float, ...]
    reactions: Tuple[PropensityReaction, ...]
    volume: float
    concentration_unit: str
    #: Omega: molecules per unit of `concentration_unit` in `volume`.
    molecules_per_concentration: float

    def propensity_vector(self, counts: Sequence[int]) -> List[float]:
        """Events per unit time for each reaction, in the given state.

        Falling factorials, not powers -- see the module docstring. The
        early exit when a count is below the required power is the exact
        statement that a reaction needing two molecules cannot fire with
        one, which is where this differs from the ODE.
        """
        values: List[float] = []
        for reaction in self.reactions:
            value = reaction.coefficient
            for index, power in reaction.orders:
                available = counts[index]
                if available < power:
                    value = 0.0
                    break
                for taken in range(power):
                    value *= float(available - taken)
            values.append(value)
        return values

    def concentrations_of(self, counts: Sequence[int]) -> Dict[str, float]:
        """Counts back in the model's concentration unit.

        For comparing against a deterministic trajectory. Exact only in the
        sense that it inverts the same factor; a count of 3 was never a
        concentration and the number this returns is a bookkeeping device,
        not a measurement.
        """
        return {
            name: float(count) / self.molecules_per_concentration
            for name, count in zip(self.species, counts)
        }

    def summary(self) -> str:
        rounded = [
            f"{name} {expected:.4g} -> {actual}"
            for name, expected, actual in zip(
                self.species, self.expected_initial_counts, self.initial_counts
            )
            if abs(expected - actual) > 1e-9
        ]
        lines = [
            f"{self.name}: {len(self.species)} species and "
            f"{len(self.reactions)} reaction(s) as an exact Markov chain "
            f"over molecule counts.",
            f"Volume {self.volume:.4g} L with concentrations in "
            f"{self.concentration_unit}, so one {self.concentration_unit} is "
            f"{self.molecules_per_concentration:.4g} molecule(s). Every "
            f"number below is set by that factor and means nothing without "
            f"it.",
            "Initial state: "
            + ", ".join(
                f"{name}={count}"
                for name, count in zip(self.species, self.initial_counts)
            )
            + ".",
        ]
        orders = ", ".join(
            f"{reaction.id} (order {reaction.order})"
            for reaction in self.reactions
        )
        lines.append(f"Reaction orders: {orders}.")
        if rounded:
            lines.append(
                "Rounded to whole molecules: "
                + "; ".join(rounded)
                + ". A fractional molecule is not a state the system can be "
                "in, and the difference is not rounding error -- it is the "
                "discreteness this simulation exists to represent."
            )
        return " ".join(lines)


def molecules_per_concentration(volume: float, concentration_unit: str) -> float:
    """Omega: molecules per unit concentration in this volume.

    `volume` is in LITRES, because the concentration units this codebase
    uses are all molar and molar is per litre. Stated here rather than
    assumed, since a volume in microlitres passed as though it were litres
    is wrong by 1e6 and produces a perfectly smooth trajectory.
    """
    if not isinstance(volume, (int, float)) or isinstance(volume, bool):
        raise StochasticRefusal(
            f"the volume must be a number of litres, not {volume!r}."
        )
    volume = float(volume)
    if not math.isfinite(volume) or volume <= 0.0:
        raise StochasticRefusal(
            f"the volume must be a positive, finite number of litres; got "
            f"{volume!r}. There is no limiting sense in which a zero volume "
            f"gives a deterministic answer -- it gives zero molecules of "
            f"everything, which is a different model."
        )

    try:
        unit = parse_unit(concentration_unit)
    except UnitError as exc:
        raise StochasticRefusal(
            f"cannot read {concentration_unit!r} as a concentration unit: "
            f"{exc}"
        ) from exc

    dimensions = {name: power for name, power in unit.dimensions.items() if power}
    if dimensions != {BASE_CONCENTRATION: 1}:
        raise StochasticRefusal(
            f"{concentration_unit!r} is not a concentration (it has "
            f"dimensions {dict(unit.dimensions)}). The conversion to counts "
            f"is concentration x volume x Avogadro and there is nothing to "
            f"multiply if the first factor is not an amount per volume."
        )

    return volume * unit.scale * AVOGADRO


def to_propensities(
    network: Any,
    *,
    volume: float,
    concentration_unit: str,
) -> PropensitySystem:
    """Convert a `ReactionNetwork` into an exact Markov chain over counts.

    `volume` (litres) and `concentration_unit` are keyword-only and have no
    defaults. Keyword-only because `to_propensities(net, 1e-15, "mM")` does
    not say which number is the volume, and required because both change
    every output by orders of magnitude -- see the module docstring.

    Refuses rather than approximating in four cases, all of which produce a
    runnable, plausible, wrong simulation if waved through:

      * the network is not well posed (`ReactionNetwork.problems`);
      * a rate law is not mass action, so it has no propensity at all;
      * a species with a strictly positive concentration converts to fewer
        than half a molecule, so it would silently start at zero and switch
        its mechanism off;
      * the volume or the unit is not a volume or a concentration.
    """
    problems = list(network.problems())
    if problems:
        raise StochasticRefusal(
            "the network is not well posed, so there is nothing coherent to "
            "convert: " + "; ".join(problems)
        )

    check_mass_action(network)

    omega = molecules_per_concentration(volume, concentration_unit)

    species = tuple(s.id for s in network.species)
    index_of = {name: index for index, name in enumerate(species)}
    parameters = {p.id: float(p.value) for p in network.parameters}

    expected: List[float] = []
    counts: List[int] = []
    for entry in network.species:
        exact = float(entry.initial) * omega
        # Nearest whole molecule, halves upward. Python's round() is
        # banker's rounding, which would send 0.5 molecules to 0 and 1.5 to
        # 2 -- an asymmetry with no physical meaning that would be invisible
        # in the output.
        count = int(math.floor(exact + 0.5))
        if entry.initial > 0.0 and count == 0:
            needed = 1.0 / (float(entry.initial) * omega / volume)
            raise StochasticRefusal(
                f"{entry.id!r} starts at {entry.initial:g} "
                f"{concentration_unit}, which in {volume:g} L is "
                f"{exact:.3g} molecules and rounds to zero. Starting it at "
                f"zero would switch off every reaction it takes part in and "
                f"the run would look completely normal. Either raise the "
                f"volume to at least {needed:.3g} L, where this species is "
                f"one molecule, or set its initial amount deliberately. A "
                f"species present at less than one molecule is a statement "
                f"about a population of cells, not about the one cell this "
                f"simulation follows."
            )
        expected.append(exact)
        counts.append(count)

    reactions: List[PropensityReaction] = []
    for reaction in network.reactions:
        tree = _parse_rate_law(reaction.rate_law, reaction.id)
        coefficient, powers = _read_monomial(
            tree,
            species=index_of,
            parameters=parameters,
            reaction_id=reaction.id,
            rate_law=reaction.rate_law,
        )
        order = sum(powers.values())

        net: Dict[str, int] = {}
        for name, count in reaction.reactants.items():
            net[name] = net.get(name, 0) - int(count)
        for name, count in reaction.products.items():
            net[name] = net.get(name, 0) + int(count)

        reactions.append(
            PropensityReaction(
                id=reaction.id,
                # k has units concentration^(1-m)/time; one factor of Omega
                # converts the rate itself to events per time and each
                # reactant contributes an inverse Omega turning its
                # concentration into a count.
                coefficient=coefficient * omega ** (1 - order),
                orders=tuple(
                    sorted(
                        (index_of[name], power)
                        for name, power in powers.items()
                        if power
                    )
                ),
                net=tuple(
                    sorted(
                        (index_of[name], change)
                        for name, change in net.items()
                        if change
                    )
                ),
                rate_law=reaction.rate_law,
            )
        )

    return PropensitySystem(
        name=network.name,
        species=species,
        initial_counts=tuple(counts),
        expected_initial_counts=tuple(expected),
        reactions=tuple(reactions),
        volume=float(volume),
        concentration_unit=concentration_unit,
        molecules_per_concentration=omega,
    )


# ---------------------------------------------------------------------------
# The Direct Method
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Trajectory:
    """One exact realisation, and everything needed to reproduce it."""

    system: PropensitySystem
    species: Tuple[str, ...]
    times: Tuple[float, ...]
    #: One row per event, plus the initial row and a final row snapped to
    #: the horizon. Counts, not concentrations.
    counts: Tuple[Tuple[int, ...], ...]
    events: int
    end: float
    seed: int
    #: Why the run stopped. See ENDED_AT_HORIZON / ENDED_ABSORBED.
    ended: str

    def column(self, species_id: str) -> Tuple[int, ...]:
        try:
            index = self.species.index(species_id)
        except ValueError:
            raise KeyError(
                f"no species {species_id!r} in this trajectory; have "
                f"{', '.join(self.species)}"
            ) from None
        return tuple(row[index] for row in self.counts)

    def final_counts(self) -> Dict[str, int]:
        return dict(zip(self.species, self.counts[-1]))

    def state_at(self, time: float) -> Dict[str, int]:
        """The state held at `time`, as a zero-order hold.

        An SSA trajectory is piecewise constant: the count set by an event
        holds until the next one. Interpolating between rows would report
        counts the system never held -- and, worse, fractional ones, which
        is the exact thing this module exists to stop reporting. The same
        argument `discrete/gillespie_ssa.py` records after measuring the
        bias that linear interpolation introduced there.
        """
        import bisect

        index = bisect.bisect_right(self.times, float(time)) - 1
        index = min(max(index, 0), len(self.counts) - 1)
        return dict(zip(self.species, self.counts[index]))

    def summary(self) -> str:
        lines = [
            f"{self.events} event(s) to t={self.times[-1]:.4g} of a "
            f"requested {self.end:.4g}, from seed {self.seed}: {self.ended}.",
            "Final counts: "
            + ", ".join(
                f"{name}={count}"
                for name, count in sorted(self.final_counts().items())
            )
            + f" in {self.system.volume:.4g} L.",
            "One realisation. It is not a mean and not a prediction -- "
            "another seed gives a different trajectory of the same process, "
            "and any quantitative claim needs an ensemble whose seeds are "
            "stated.",
        ]
        return " ".join(lines)


def simulate_ssa(
    system: PropensitySystem,
    end: float,
    seed: int,
    max_events: int = DEFAULT_MAX_EVENTS,
) -> Trajectory:
    """Gillespie's Direct Method, exact, over a `PropensitySystem`.

    Exact means no approximation of the chemical master equation: every
    reaction event is generated, and the distribution of the state at any
    time is the master equation's own. Nothing here is a tau-leap and
    nothing is a Langevin approximation, both of which trade exactness for
    speed and would need their own error statements.

    At each step the total propensity `a0` sets an exponential waiting time
    `tau = -ln(u)/a0`, and a second uniform picks which reaction fired in
    proportion to its propensity. Both facts follow from the propensities
    being constant between events, which is what makes the method exact
    rather than a fine-grained Euler step.

    `seed` is required; see the module docstring on the deliberate
    deviation from ADR 0005's `seed: int | None = None`. It is a
    positional-or-keyword argument so that
    `scripts/check_rng_convention.py` can see it, and the RNG is
    `numpy.random.default_rng(seed)` exactly as the ADR requires.

    Raises rather than truncating when `max_events` is reached: a
    trajectory that stopped early has a final state that looks like an
    answer, and an ensemble built from truncated runs is biased in a
    direction nothing in the output reveals.
    """
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise StochasticRefusal(
            f"the SSA needs numpy for its RNG (ADR 0005), which is in "
            f"requirements.txt but not importable here: {exc}"
        ) from exc

    end = float(end)
    if not math.isfinite(end) or end <= 0.0:
        raise StochasticRefusal(
            f"the horizon must be a positive, finite time; got {end!r}."
        )
    if int(max_events) < 1:
        raise StochasticRefusal(
            f"max_events must be at least 1; got {max_events!r}."
        )

    rng = np.random.default_rng(seed)

    counts = list(system.initial_counts)
    time = 0.0
    times: List[float] = [0.0]
    states: List[Tuple[int, ...]] = [tuple(counts)]
    events = 0
    ended = ENDED_AT_HORIZON

    while True:
        propensities = system.propensity_vector(counts)
        total = math.fsum(propensities)
        if total <= 0.0:
            ended = ENDED_ABSORBED
            break

        # 1 - random() lies in (0, 1]; random() alone can return exactly
        # 0.0, whose logarithm is -inf. It happens about once in 2^53
        # draws, which over a long ensemble is a run that silently jumps to
        # the horizon rather than an error anybody sees.
        tau = -math.log(1.0 - rng.random()) / total
        if time + tau > end:
            break

        time += tau
        target = rng.random() * total
        cumulative = 0.0
        chosen = -1
        for index, value in enumerate(propensities):
            cumulative += value
            if cumulative > target:
                chosen = index
                break
        if chosen < 0:
            # Only reachable when rounding leaves the running sum a few ulp
            # short of `target`. The last reaction with a positive
            # propensity is the one the draw fell in; picking it keeps the
            # selection a partition of [0, total) rather than silently
            # skipping an event.
            chosen = max(
                index for index, value in enumerate(propensities) if value > 0.0
            )

        for index, change in system.reactions[chosen].net:
            counts[index] += change
        events += 1
        times.append(time)
        states.append(tuple(counts))

        if events >= int(max_events):
            raise StochasticRefusal(
                f"the run fired the ceiling of {int(max_events)} events and "
                f"had only reached t={time:.4g} of {end:.4g}. The trajectory "
                f"so far is real but is not the run that was asked for, and "
                f"an ensemble of truncated runs is biased in a direction "
                f"nothing in the output shows -- so it is refused rather "
                f"than returned. Either raise max_events, or read the event "
                f"count as the answer it is: a system this busy has copy "
                f"numbers high enough that the deterministic model in "
                f"`compose/simulate.py` is the right tool, and "
                f"`discreteness_matters` will say so in one call instead of "
                f"a million."
            )

    # Final row snapped to the horizon, matching every other simulation
    # domain in this codebase, so that trajectories from different engines
    # can be compared row for row at their endpoints.
    times.append(end)
    states.append(tuple(counts))

    return Trajectory(
        system=system,
        species=system.species,
        times=tuple(times),
        counts=tuple(states),
        events=events,
        end=end,
        seed=int(seed),
        ended=ended,
    )


# ---------------------------------------------------------------------------
# Whether the deterministic answer can be trusted
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiscretenessReport:
    """The smallest steady-state copy number, and what follows from it."""

    #: species id -> expected molecules at the steady state examined.
    copy_numbers: Mapping[str, float]
    #: The smallest of those, over species the deterministic model puts
    #: strictly above zero.
    minimum: float
    minimum_species: str
    threshold: int
    volume: float
    concentration_unit: str
    molecules_per_concentration: float
    #: How many stable steady states the search found. More than one is
    #: itself the strongest argument for simulating exactly.
    states_found: int
    #: Species the deterministic model puts at exactly zero. Excluded from
    #: the minimum because 1/sqrt(N) is not defined there -- and called out
    #: because that is the case where the two models differ most, not
    #: least: a stochastic system visits 1 and a deterministic one cannot.
    zero_species: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()

    @property
    def relative_fluctuation(self) -> float:
        """1/sqrt(N) at the scarcest species: the size of what the ODE omits."""
        return 1.0 / math.sqrt(self.minimum)

    @property
    def matters(self) -> bool:
        return self.minimum < self.threshold

    def summary(self) -> str:
        lines = [
            f"At the steady state, the scarcest species is "
            f"{self.minimum_species} at {self.minimum:.4g} molecules in "
            f"{self.volume:.4g} L (concentrations read as "
            f"{self.concentration_unit}; one {self.concentration_unit} is "
            f"{self.molecules_per_concentration:.4g} molecule(s))."
        ]
        lines.append(
            f"For a birth-death process the stationary distribution is "
            f"Poisson, so the standard deviation is sqrt(N) and the relative "
            f"fluctuation is 1/sqrt(N) = "
            f"{self.relative_fluctuation:.1%} here."
        )
        if self.matters:
            lines.append(
                f"That is at or above the ~{PARAMETER_UNCERTAINTY:.0%} the "
                f"model's own constants are uncertain by, which is where the "
                f"threshold of {self.threshold} molecules comes from. The "
                f"deterministic answer should NOT be trusted for this "
                f"species: the noise it leaves out is now the largest error "
                f"in it, and for a switch or a threshold the difference is "
                f"qualitative rather than a band around the curve. Convert "
                f"with `to_propensities` and run `simulate_ssa`."
            )
        else:
            lines.append(
                f"That is below the ~{PARAMETER_UNCERTAINTY:.0%} the model's "
                f"constants are uncertain by, so the fluctuation is no "
                f"longer the biggest error in the deterministic answer. That "
                f"is a much weaker claim than the ODE being right: the noise "
                f"is still there, and it is only smaller than the "
                f"uncertainty you already have."
            )
        if self.zero_species:
            lines.append(
                f"Excluded from the minimum: "
                + ", ".join(self.zero_species)
                + " sit at exactly zero, where 1/sqrt(N) is undefined. That "
                "is not a reassurance -- a species the deterministic model "
                "pins at zero is precisely one the stochastic system can "
                "visit at one molecule, and no threshold on a mean speaks "
                "to how often."
            )
        if self.states_found > 1:
            lines.append(
                f"{self.states_found} stable steady states were found. A "
                f"system with more than one is the strongest case for "
                f"simulating exactly at any copy number: the deterministic "
                f"model says the probability of leaving a stable state is "
                f"zero forever, and the true probability is small but "
                f"finite. The number above is the scarcest species over all "
                f"of the states."
            )
        lines.extend(self.notes)
        lines.append(
            "This is a statement about the MEAN at steady state. Rare "
            "events -- a switch flipping, a transcript that never appears -- "
            "have probabilities that fall exponentially with the copy number "
            "and never reach zero, and nothing here bounds them."
        )
        return " ".join(lines)


def discreteness_matters(
    network: Any,
    *,
    volume: float,
    concentration_unit: str,
    starts_per_species: Optional[int] = None,
) -> DiscretenessReport:
    """The smallest expected copy number at steady state, and the verdict.

    Deliberately does NOT require mass action. This is the diagnosis and
    `to_propensities` is the treatment: the most useful thing this can tell
    a caller about a Michaelis-Menten model is that its enzyme is present
    at four copies, at which point the quasi-steady-state assumption behind
    that rate law has already failed and the model needs rewriting as a
    mechanism -- which is a conclusion the refusal in `to_propensities`
    then makes concrete.

    Refuses when no stable steady state was found, rather than reporting
    the copy numbers at the initial condition. The initial condition is
    where the caller put the system, not where it lives, and calling it
    "the steady state" would answer a question nobody asked with a number
    that looks like the one they wanted.
    """
    try:
        from .analysis import analyse
    except ImportError:  # pragma: no cover - flat import
        from analysis import analyse  # type: ignore[no-redef]

    omega = molecules_per_concentration(volume, concentration_unit)

    if starts_per_species is None:
        report = analyse(network)
    else:
        report = analyse(network, starts_per_species=starts_per_species)

    stable = report.stable_points
    if not stable:
        raise StochasticRefusal(
            f"no stable steady state was found from {report.starts_tried} "
            f"starting points, so there is no steady-state copy number to "
            f"report. That is not the same as the system having none -- a "
            f"root find reports where it converged -- and it is a real "
            f"answer for an oscillator or a system with a source and no "
            f"sink, neither of which HAS a resting level. Simulate the time "
            f"course instead: `to_propensities` followed by `simulate_ssa` "
            f"needs no steady state, and the counts along the trajectory "
            f"answer the same question directly."
        )

    # The scarcest species over every stable state, not over one of them.
    # A bistable switch is scarce in a different species in each state and
    # reporting only the first found would depend on the search order.
    best_state: Optional[Mapping[str, float]] = None
    best_minimum = math.inf
    best_species = ""
    zero_species: Tuple[str, ...] = ()

    for point in stable:
        counts = {
            name: float(value) * omega for name, value in point.state.items()
        }
        positive = {
            name: value for name, value in counts.items() if value > 0.0
        }
        if not positive:
            continue
        name = min(positive, key=lambda key: positive[key])
        if positive[name] < best_minimum:
            best_minimum = positive[name]
            best_species = name
            best_state = counts
            zero_species = tuple(
                sorted(key for key, value in counts.items() if value <= 0.0)
            )

    if best_state is None:
        raise StochasticRefusal(
            f"every species is at zero in all {len(stable)} stable steady "
            f"state(s) found, so there is no copy number to take a "
            f"fluctuation of. The relative fluctuation 1/sqrt(N) is not "
            f"defined at N = 0, and reporting a threshold verdict here would "
            f"be arithmetic on an empty system. Check the initial "
            f"concentrations: a mechanism whose species all start at zero "
            f"stays there."
        )

    notes: List[str] = []
    if report.any_oscillatory:
        notes.append(
            "Some eigenvalues at these states are complex, so the approach "
            "is oscillatory. A copy number taken at a fixed point says "
            "nothing about the amplitude of an oscillation around it, and a "
            "small-number oscillator can lose coherence entirely."
        )

    return DiscretenessReport(
        copy_numbers=dict(best_state),
        minimum=best_minimum,
        minimum_species=best_species,
        threshold=DISCRETENESS_THRESHOLD,
        volume=float(volume),
        concentration_unit=concentration_unit,
        molecules_per_concentration=omega,
        states_found=len(stable),
        zero_species=zero_species,
        notes=tuple(notes),
    )


__all__ = [
    "AVOGADRO",
    "DEFAULT_MAX_EVENTS",
    "DISCRETENESS_THRESHOLD",
    "ENDED_ABSORBED",
    "ENDED_AT_HORIZON",
    "PARAMETER_UNCERTAINTY",
    "DiscretenessReport",
    "NotMassAction",
    "PropensityReaction",
    "PropensitySystem",
    "StochasticRefusal",
    "Trajectory",
    "check_mass_action",
    "discreteness_matters",
    "mass_action_problems",
    "molecules_per_concentration",
    "simulate_ssa",
    "to_propensities",
]
