"""Are these two models the same, and which experiment tells them apart.

THE QUESTION THIS ANSWERS
-------------------------
A mechanism paper has the same shape every time: two hypotheses about how
something works, and an argument that some measurement picks one. Before any
data exist there are three questions, and they are asked in this order.

    Are these actually two models, or one model written twice?
    Where do their predictions differ?
    What would I measure -- and can I measure it well enough to care?

This module answers those three and refuses at the point where the honest
answer is that there is nothing to decide.

THE THIRD QUESTION IS THE ONE THAT GETS SKIPPED
-----------------------------------------------
The first two are arithmetic. The third decides whether an experiment is
worth doing, and it is the one an argmax answers wrongly without ever
failing: take the condition where the two curves are furthest apart and call
it the experiment. If the curves are 0.3% apart at their widest and the
assay has a 10% coefficient of variation, that condition is not an
experiment. It is the place where two models differ by the least
unmeasurable amount rather than the most. The argmax is still perfectly
well defined. It is simply not an answer.

So every separation reported here is in units of a STATED measurement
precision, and an observation that does not clear that precision is reported
as not separating the models -- not as the best of a bad set. That is the
whole reason this module is not three lines of `max(...)`.

TWO FLOORS, AND THEY ARE NOT THE SAME FLOOR
-------------------------------------------
A predicted difference has to clear two entirely different things before it
means anything, and `sensitivity.py` had to learn the same lesson about its
own two thresholds.

    numerical floor     Below this the difference is the solver's rounding.
                        It is a fact about floating point and it moves with
                        the readout: a steady state read off a root solved to
                        a 1e-14 residual is exact to machine precision, and a
                        quantity off a finite-difference Jacobian is not.

    measurement error   Below this the difference is inside your error bar.
                        It is a fact about the instrument, it does not move
                        with the arithmetic, and no amount of better
                        computing touches it.

Conflating them produces both failures. A difference of 1e-16 is not a small
real difference; it is not a difference. A difference of 1e-3 on a value of
1 is entirely real, sits ten orders of magnitude above the arithmetic, and
still cannot be seen by an assay with a 10% CV. The first is reported as
unresolvable, the second as real and unmeasurable, and they are different
sentences because they call for different things -- a better solver, and a
better instrument.

WHAT "STRUCTURALLY IDENTICAL" CLAIMS, AND WHAT IT DOES NOT
----------------------------------------------------------
`structurally_identical` looks for a renaming: a bijection of species that
carries one model's reactions onto the other's stoichiometry for
stoichiometry, extended to a bijection of parameters that carries one rate
law onto the other TOKEN FOR TOKEN.

Token for token is a real limitation and it is stated rather than hidden.
`k*S/(Km+S)` and `S*k/(S+Km)` are the same function and this module reports
them as different, because deciding when two expressions are equal is a
computer-algebra problem and claiming to have solved it here would be a
claim about the algebra rather than about the models. The error is always in
one direction -- a false "different", never a false "identical" -- and it is
caught immediately downstream, because two models that differ only in how
their laws are written make identical predictions and
`discriminating_experiment` says exactly that.

SAME WIRING IS A SEPARATE FINDING FROM IDENTICAL
------------------------------------------------
Two models can have the same species, the same reactions and the same
stoichiometry and still differ, because the argument is about the rate law.
That is the commonest shape of a mechanism question: nobody disputes that
the enzyme turns S into P, and the whole paper is about whether the
inhibitor binds free enzyme or the complex. So `same_wiring` and `identical`
are reported separately, and a model pair with the same wiring and a
different law is told that this is what it is.

The third case is reported separately too: the same structure with different
numbers is ONE mechanism at two operating points, not two mechanisms. An
experiment can still tell the two parameter sets apart, and that is a
different paper.

WHAT IS NOT HERE: AIC, BIC, AND EVERY OTHER SELECTION NUMBER
------------------------------------------------------------
Deliberately absent. An information criterion compares how well two models
fit one dataset after a penalty for how many parameters they spend doing it.
That is a useful thing and it is not what this module is for, for two
reasons that are worth stating rather than assuming.

It needs data. Everything here runs before any data exist, which is the
point -- the module is for designing the experiment, and an AIC computed
against the data you have not collected is not a number.

And it says nothing about whether either model is right. AIC compares the
members of the set you handed it; the best of two wrong models is still
wrong, and the number is the same either way. A single number that ranks
mechanisms is the most quotable thing this package could produce and the
least defensible, and it would be quoted without the sentence under it. If
one is ever added here it must arrive with its assumptions attached: that
the models were fitted to the SAME data, that the residuals are independent
and have the stated distribution, that the sample is large relative to the
parameter count, and that "better" means "predicts held-out data better"
rather than "is true".

THE DEFAULT EXPERIMENT, AND WHAT IT DOES NOT LOOK AT
----------------------------------------------------
With no readouts or doses named, `discriminating_experiment` measures the
initial rate of change of every species the two models share, over a dose
series of every species the models CONSUME and never make -- the thing you
put in the tube. Two decades either side of the amount the model already
holds, which is an illustrative range and says so.

That default is narrow on purpose and the report names what it varied.
Varying the inhibitor instead of the substrate is a real experiment, it is
one `Dose` away, and this module does not go looking for it -- an argmax
over a space nobody stated is a confident answer to an unasked question.
What it will not do is stay quiet about the omission.

It also varies one input at a time, which is how these experiments are run
and which cannot see a difference that appears only when two inputs move
together. Said here because a one-at-a-time design that does not admit to
being one reads like a search.

A DOSE IS A CONDITION IN A TUBE
-------------------------------
Not a concentration in a cell. `scale.py`'s cellular bounds -- one molecule
per bacterium, total cellular protein -- are the right questions to ask of a
model's own numbers and the wrong ones to ask of an assay concentration.
100 mM substrate is absurd inside a cell and ordinary in a cuvette.

WHAT NONE OF THIS SAYS
----------------------
That either model is right. Every comparison here is between two models at
the constants they currently hold, and if those constants are the motif
library's illustrative placeholders then the answer is about these two
parameterised models rather than about the two mechanisms in general. The
summaries say so every time, because "measure the rate at saturating
substrate" reads like advice about biochemistry and is, until the constants
are grounded, advice about two particular sets of placeholder numbers.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import (
    Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple,
)

try:
    from .sensitivity import MACHINE_PRECISION, SAFETY
    from .sensitivity import steady_state_of as _steady_state_quantity
except ImportError:  # pragma: no cover - flat import
    from sensitivity import MACHINE_PRECISION, SAFETY  # type: ignore[no-redef]
    from sensitivity import (  # type: ignore[no-redef]
        steady_state_of as _steady_state_quantity,
    )


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

#: How many measurement errors apart two predictions must be before the
#: observation separates the models at all.
#:
#: One. Below one the predicted difference is inside the error bar, and an
#: experiment that puts the two hypotheses inside one error bar has not
#: distinguished them by any reading of the word. This is the floor of
#: meaning rather than a standard of evidence.
MEASURABLE = 1.0

#: Where a single observation starts being an argument rather than a
#: difference you could see if you squinted.
#:
#: A JUDGEMENT ABOUT EXPERIMENTS, and a different kind of claim from
#: `MEASURABLE`. Three errors apart is where one measurement, taken once,
#: begins to be worth showing somebody. It is not a p-value, it is not a
#: confidence level, and it assumes nothing about the distribution of the
#: error -- there is no distribution here, only a stated size. Two
#: predictions three stated errors apart is a fact about the two models and
#: the instrument; whether your measurement lands where the model says is
#: what the replicates are for.
DECISIVE = 3.0

#: Relative accuracy of a steady state read off the analysis module's
#: multistart root find.
#:
#: MEASURED, and deliberately coarser than `sensitivity.steady_state_of`
#: declares. That module measured 1.8e-16 on dX/dt = ks - kd*X, where the
#: root is one linear equation and lands at machine precision. A closed
#: enzymatic model is harder, and it can be checked exactly: competitive
#: inhibition conserves S + P, so started at S = 1 and P = 0 the steady state
#: of P is exactly 1 whatever the kinetics are. Over the six inhibition
#: motifs in the library the worst the solver returned was
#: 1.0000000000000184 -- 1.8e-14 relative, a hundred times the other
#: measurement. Rounded up to one significant figure, because a precision
#: claimed finer than it was measured is the error the constant exists to
#: prevent.
#:
#: Declared here rather than borrowed, and the consequence is exactly the
#: failure this module is about. At machine precision that 1.8e-14 clears
#: the arithmetic floor, and two mechanisms that are PROVABLY identical on
#: that observation -- both end with every S converted to P, by the
#: conservation law -- get reported as differing by a real amount.
STEADY_STATE_PRECISION = 1e-13

#: How far a default dose series reaches either side of the amount the model
#: already holds, in decades.
#:
#: ILLUSTRATIVE. Two decades each way spans sub-saturating to saturating for
#: a Michaelis-Menten enzyme started anywhere near its Km, which is the range
#: the classical discriminations are made over -- but it is a stated range
#: and not a measurement of anybody's assay. A range chosen without knowing
#: the Km can miss the region where two mechanisms diverge, and the report
#: prints the range it used so that a reader can see whether it did.
DEFAULT_DOSE_DECADES = 2.0

#: Points in a default dose series. Odd, so the series contains the amount
#: the model already holds.
DEFAULT_DOSE_POINTS = 9


# ---------------------------------------------------------------------------
# Limits on the structural search
# ---------------------------------------------------------------------------

#: The largest number of species this module will attempt an isomorphism on.
#:
#: The search is worst-case factorial in the number of species. Refinement by
#: degree signature and pruning against partially mapped reactions make the
#: realistic cases instant: the largest model the motif library composes is a
#: three-tier cascade at 8 species and 6 reactions, whose species all have
#: distinct signatures, and it is decided in one pass. Twenty is comfortably
#: above every shape in the library and is a cheap pre-check rather than the
#: real guard -- a network inside it can still be pathological, which is what
#: `MAX_PARTIAL_ASSIGNMENTS` is for.
#:
#: The point of a limit at all is that a search which never returns is
#: indistinguishable, to a reader, from one that says the models differ. That
#: is the worst available way to be wrong here, so this REFUSES instead.
MAX_SPECIES_FOR_ISOMORPHISM = 20

#: The largest number of reactions, for the same reason: the leaf of the
#: species search matches reactions, which is factorial in its own right.
MAX_REACTIONS_FOR_ISOMORPHISM = 40

#: Partial assignments tried before the search gives up.
#:
#: THE REAL GUARD, and MEASURED. The worst case this search has is a network
#: of N interchangeable parallel branches compared against the same network
#: with one branch's rate law changed: every species has N candidates, the
#: pruning cannot reject a branch until the very last one, and (N-1)!
#: assignments have to be tried before the answer is no.
#:
#: Measured on exactly that family, one branch per two species:
#:
#:     16 species   0.7 s    answered (same wiring, different law)
#:     18 species   1.7 s    REFUSED, budget exhausted
#:
#: So this budget costs under two seconds of Python on the case built to
#: defeat it, and it fires before the size limit does. Two seconds is about
#: the longest a question like this should take without saying something.
#: `Terium/tests/test_compose_compare.py` builds both rows.
MAX_PARTIAL_ASSIGNMENTS = 200_000


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


class ComparisonRefused(RuntimeError):
    """Two models were not compared, and the reason is the message."""


class ComparisonTooLarge(ComparisonRefused):
    """The structural search was abandoned rather than left to run.

    Separate from the other refusals because it licenses nothing at all: a
    search that ran out of budget has NOT found the models to be different.
    An exception rather than a `False`, precisely so that it cannot be read
    as one.
    """


class ModelsIndistinguishable(ComparisonRefused):
    """Nothing that was tried separates the two models.

    A REFUSAL THAT IS A FINDING. Two mechanisms that make the same
    predictions everywhere you can look are not two hypotheses; there is no
    experiment to design, and the paper's question is malformed rather than
    unanswered. Raised rather than returned as a low-scoring result, because
    a ranked list with a best entry invites somebody to run the best entry.
    """


# ---------------------------------------------------------------------------
# Measurement precision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Precision:
    """How well the observation can be measured, and where that came from.

    Two terms, because real instruments have two. A RELATIVE term covers
    everything that scales with the signal -- pipetting, enzyme amount, cell
    count. An ABSOLUTE term is the detector's own noise and does not shrink
    when the signal does; it is what makes a measurement at a low dose bad,
    and it is the term that most often decides where an experiment should be
    run. The error at a value is the larger of the two, which is the
    conservative reading of "the instrument is this good".

    `basis` is required and not decorative. A precision with no stated origin
    is a number nobody can argue with, and every threshold in this module is
    built on top of it: an experiment declared decisive rests entirely on
    where that number came from.
    """

    relative: float = 0.0
    absolute: float = 0.0
    basis: str = ""

    def __post_init__(self) -> None:
        for name in ("relative", "absolute"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ComparisonRefused(
                    f"a {name} precision of {value!r} is not a non-negative "
                    f"finite number. It is the size of a measurement error, "
                    f"not a tolerance to be switched off."
                )
        if float(self.relative) == 0.0 and float(self.absolute) == 0.0:
            raise ComparisonRefused(
                "a precision of zero claims a perfect instrument. Every "
                "difference would then clear it, including the arithmetic's "
                "own rounding, and every pair of models would look "
                "distinguishable. State what you can actually measure."
            )
        if not str(self.basis).strip():
            raise ComparisonRefused(
                "a precision with no stated basis is a number nobody can "
                "argue with, and every verdict this module reaches rests on "
                "it. Say where it came from -- an instrument specification, "
                "a replicate series, or an admission that it is a guess."
            )

    def error_in(self, *values: float) -> float:
        """The error to expect on a measurement of this size.

        Taken at the LARGER of the predictions being compared, which is the
        pessimistic choice: the noisier of the two measurements is the one
        that decides whether you can tell them apart.
        """
        scale = max((abs(float(v)) for v in values), default=0.0)
        return max(float(self.absolute), float(self.relative) * scale)

    def describe(self) -> str:
        parts = []
        if self.relative:
            parts.append(f"{self.relative:.3g} of the value")
        if self.absolute:
            parts.append(f"{self.absolute:.3g} absolute")
        joined = " or ".join(parts)
        if len(parts) > 1:
            joined += ", whichever is larger"
        return f"{joined} ({self.basis})"


#: The precision assumed when the caller states none.
#:
#: AN ILLUSTRATIVE PLACEHOLDER, like every default in this package. Nothing
#: here measured anybody's assay and no citation is attached to it: 10% is a
#: coefficient of variation people commonly quote for a plate-reader kinetic
#: assay, which makes it a reasonable shape for a default and not a
#: measurement of your instrument.
#:
#: The absolute term is left at ZERO, which is the OPTIMISTIC assumption and
#: is worth knowing about. With no absolute floor, a measurement of a tiny
#: rate at a low dose looks exactly as good as a measurement of a large rate
#: at a high one, because the error shrinks with the signal. Real detectors
#: do not do that, and it is the absolute floor that ruins the low-dose end
#: of a dose-response. Supply your own and the answer sharpens.
DEFAULT_PRECISION = Precision(
    relative=0.1,
    absolute=0.0,
    basis=(
        "illustrative placeholder: 10% of the measured value, no absolute "
        "floor. Not a measurement of your assay"
    ),
)


# ---------------------------------------------------------------------------
# Reading a network
# ---------------------------------------------------------------------------


def _network_of(model: Any) -> Any:
    """The `ReactionNetwork`, whether a model or a network was handed over."""
    return getattr(model, "network", model)


def _name_of(network: Any) -> str:
    return str(getattr(network, "name", None) or "unnamed model")


def _species_ids(network: Any) -> Tuple[str, ...]:
    return tuple(s.id for s in network.species)


def _parameter_ids(network: Any) -> Tuple[str, ...]:
    return tuple(p.id for p in network.parameters)


#: One lexeme of a rate law: a name, a number, or a single symbol.
#:
#: Whitespace matches nothing and is therefore normalised away, so
#: `a*b` and `a * b` lex identically. Numbers are captured separately from
#: names so that `2` and `2.0` can be compared as numbers rather than as
#: text -- they are the same constant and a textual comparison would call
#: two identical models different.
_LEXEME = re.compile(
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<number>(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)"
    r"|(?P<symbol>[^\sA-Za-z0-9_])"
)


def _lex(law: str) -> Tuple[Tuple[str, str], ...]:
    return tuple(
        (match.lastgroup or "symbol", match.group())
        for match in _LEXEME.finditer(law or "")
    )


def _names_in(law: str) -> Tuple[str, ...]:
    return tuple(text for kind, text in _lex(law) if kind == "name")


# ---------------------------------------------------------------------------
# Structure: is this one model written twice?
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructuralComparison:
    """What a renaming can and cannot make of one model into the other."""

    left: str
    right: str
    #: A renaming exists that carries species, stoichiometry AND every rate
    #: law, token for token.
    identical: bool
    #: A renaming exists that carries species and stoichiometry. Weaker, and
    #: a finding in its own right: the wiring is agreed and the argument is
    #: about the rate law, which is what a mechanism paper usually is.
    same_wiring: bool
    #: left name -> right name, over species, parameters and reactions.
    #: Empty when no renaming was found.
    renaming: Mapping[str, str] = field(default_factory=dict)
    #: Whether the numbers match too, and `None` when no full renaming was
    #: found to compare them under. Structure and numbers are separate
    #: questions -- see the module docstring.
    values_match: Optional[bool] = None
    #: Everything that stopped this being an identity, in words.
    differences: Tuple[str, ...] = ()
    #: Parameters the renaming placed by elimination rather than by evidence:
    #: they appear in no rate law, so nothing constrains where they go and
    #: any bijection of them would do.
    unconstrained: Tuple[str, ...] = ()

    def summary(self) -> str:
        if self.identical and self.values_match:
            return (
                f"`{self.left}` and `{self.right}` are one model written "
                f"twice: a renaming of {len(self.renaming)} symbol(s) carries "
                f"every species, every reaction, every rate law and every "
                f"number of one onto the other. There is no experiment to "
                f"design between them, because there is nothing to decide -- "
                f"two identical mechanisms are not two hypotheses."
            )
        if self.identical:
            return (
                f"`{self.left}` and `{self.right}` have the same structure "
                f"and different numbers. That is ONE mechanism at two "
                f"operating points, not two mechanisms: every rate law "
                f"matches under the renaming and only the constants differ. "
                f"An experiment can still tell the two parameter sets apart "
                f"-- ask `discriminating_experiment` -- but it will not "
                f"answer a question about mechanism, because both answers "
                f"are the same mechanism."
            )
        if self.same_wiring:
            return (
                f"`{self.left}` and `{self.right}` have the same species and "
                f"the same reactions, and differ in what those reactions DO: "
                + "; ".join(self.differences)
                + ". This is the commonest shape of a mechanism question -- "
                "the wiring is agreed and the argument is about the rate "
                "law, which is exactly the case an experiment can decide."
            )
        return (
            f"`{self.left}` and `{self.right}` are not the same network under "
            f"any renaming: "
            + "; ".join(self.differences)
            + ". They differ in what is connected to what, not only in what "
            "the connections do."
        )


def structurally_identical(a: Any, b: Any) -> StructuralComparison:
    """Whether one model is the other with the names changed.

    THE SEARCH. A bijection of species is found by backtracking, refined by a
    degree signature -- how many reactions consume a species, produce it, and
    mention it in a rate law -- and pruned at every step against the
    reactions whose species are already placed. Realistic networks are
    decided in one pass because their species have distinct signatures; a
    symmetric network has many candidate bijections and is where the budget
    matters.

    TWO PASSES, BECAUSE THERE ARE TWO ANSWERS. The first requires the rate
    laws to match as well, and finding one proves `identical`. Only if that
    fails does the second run, requiring stoichiometry alone; finding one
    there proves `same_wiring`, which is a different and useful finding
    rather than a consolation prize.

    REFUSES ON SIZE rather than running. See `ComparisonTooLarge`: a search
    that never returns is indistinguishable, to a reader, from one that says
    the models differ, and that is the worst possible way to be wrong here.
    """
    left = _network_of(a)
    right = _network_of(b)
    _refuse_rules(left)
    _refuse_rules(right)
    _refuse_size(left)
    _refuse_size(right)

    left_name, right_name = _name_of(left), _name_of(right)
    shape: List[str] = []
    if len(left.species) != len(right.species):
        shape.append(
            f"{len(left.species)} species against {len(right.species)}"
        )
    if len(left.reactions) != len(right.reactions):
        shape.append(
            f"{len(left.reactions)} reactions against {len(right.reactions)}"
        )
    if shape:
        return StructuralComparison(
            left=left_name, right=right_name,
            identical=False, same_wiring=False, differences=tuple(shape),
        )

    differences: List[str] = []
    same_parameter_count = len(left.parameters) == len(right.parameters)
    if not same_parameter_count:
        # Not a wiring difference -- the stoichiometry search below still
        # runs -- but it makes an identity impossible, because a renaming is
        # a bijection and there is no bijection between sets of different
        # size.
        differences.append(
            f"{len(left.parameters)} parameters against "
            f"{len(right.parameters)}, so no renaming can pair them up"
        )

    # A BUDGET EACH, not one shared between the two searches. Sharing meant a
    # first search that finished having spent almost all of it left the second
    # to refuse on the remainder -- a `ComparisonTooLarge` about a question
    # that was never hard, which is the one message in this module that must
    # never be raised without cause.
    found = None
    if same_parameter_count:
        found = _search(
            left, right, require_laws=True,
            budget=[MAX_PARTIAL_ASSIGNMENTS],
        )

    if found is not None:
        species_map, reaction_map, parameter_map = found
        parameter_map, unconstrained = _complete_parameter_map(
            left, right, parameter_map
        )
        renaming = {**species_map, **parameter_map, **reaction_map}
        return StructuralComparison(
            left=left_name, right=right_name,
            identical=True, same_wiring=True, renaming=renaming,
            values_match=_values_match(
                left, right, species_map, parameter_map
            ),
            unconstrained=unconstrained,
        )

    wiring = _search(
        left, right, require_laws=False, budget=[MAX_PARTIAL_ASSIGNMENTS],
    )
    if wiring is None:
        return StructuralComparison(
            left=left_name, right=right_name,
            identical=False, same_wiring=False,
            differences=tuple(differences + _why_no_wiring(left, right)),
        )

    species_map, reaction_map, _ = wiring
    differences += _law_differences(left, right, species_map, reaction_map)
    return StructuralComparison(
        left=left_name, right=right_name,
        identical=False, same_wiring=True,
        renaming={**species_map, **reaction_map},
        differences=tuple(differences),
    )


def _refuse_rules(network: Any) -> None:
    """Rate rules and assignment rules are not compared, and are not ignored.

    A rate rule sets a species' derivative outside the stoichiometry, and an
    assignment rule adds a symbol that rate laws may reference. Matching them
    needs the same token alignment the reactions get plus a correspondence
    between rules, and this module does not implement it.

    Refusing is the only honest option. Comparing the two models by the part
    they happen to have in common and reporting IDENTICAL would be a false
    identity built out of the half that was examined -- which is the single
    worst answer this module could return, because it ends the inquiry.
    """
    rate_rules = tuple(getattr(network, "rate_rules", ()) or ())
    assignment_rules = tuple(getattr(network, "assignment_rules", ()) or ())
    if not rate_rules and not assignment_rules:
        return
    raise ComparisonRefused(
        f"`{_name_of(network)}` carries {len(rate_rules)} rate rule(s) and "
        f"{len(assignment_rules)} assignment rule(s), and this compares "
        f"reaction networks. Matching a rule needs a correspondence between "
        f"rules as well as between reactions, which is not implemented here. "
        f"Refusing rather than comparing the reactions alone: a model whose "
        f"dynamics are half in rate rules would be reported identical to "
        f"another on the strength of the half that was looked at. Compare "
        f"the trajectories with `simulate.run` instead, which reads the "
        f"whole model."
    )


def _refuse_size(network: Any) -> None:
    species, reactions = len(network.species), len(network.reactions)
    if species <= MAX_SPECIES_FOR_ISOMORPHISM and (
        reactions <= MAX_REACTIONS_FOR_ISOMORPHISM
    ):
        return
    raise ComparisonTooLarge(
        f"`{_name_of(network)}` has {species} species and {reactions} "
        f"reactions, above this module's limit of "
        f"{MAX_SPECIES_FOR_ISOMORPHISM} species and "
        f"{MAX_REACTIONS_FOR_ISOMORPHISM} reactions. The search is "
        f"worst-case factorial in the number of species, so above that size "
        f"it would appear to hang rather than answer. NOTHING HERE SAYS THE "
        f"MODELS DIFFER -- the question was not answered. If the two "
        f"networks come from the same builder their names already agree, and "
        f"comparing the species and reaction ids directly answers it."
    )


def _budget_exhausted(left: Any, right: Any) -> ComparisonTooLarge:
    return ComparisonTooLarge(
        f"the structural search gave up after {MAX_PARTIAL_ASSIGNMENTS} "
        f"partial assignments on networks of {len(left.species)} and "
        f"{len(right.species)} species with {len(left.reactions)} and "
        f"{len(right.reactions)} reactions. That happens when many species "
        f"are interchangeable -- N identical parallel branches admit N! "
        f"renamings and every one of them has to be tried before the answer "
        f"is no. NOTHING HERE SAYS THE MODELS DIFFER; the search ran out of "
        f"budget, which is a fact about this module."
    )


# -- the search ------------------------------------------------------------


def _species_signature(network: Any, species: str) -> Tuple[Any, ...]:
    """An invariant of a species that any renaming must preserve.

    The multiset over reactions of (how much is consumed, how much is
    produced, whether the rate law mentions it). Cheap, and it separates the
    cases that matter: a substrate from a product from an enzyme that is
    named in a law and touched by no stoichiometry.
    """
    return tuple(sorted(
        (
            int(reaction.reactants.get(species, 0)),
            int(reaction.products.get(species, 0)),
            species in _names_in(reaction.rate_law),
        )
        for reaction in network.reactions
    ))


def _reaction_species(
    reaction: Any, species: Sequence[str]
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """(species in the stoichiometry, species named in the law).

    The second is filtered against the network's own species, because a rate
    law names parameters and functions too and only the species take part in
    a renaming of species. An unfiltered version put `Ki` into the search's
    assignment order and it tried to place a parameter as though it were a
    pool.
    """
    known = set(species)
    stoichiometry = tuple(
        sorted((set(reaction.reactants) | set(reaction.products)) & known)
    )
    named = tuple(sorted(set(_names_in(reaction.rate_law)) & known))
    return stoichiometry, named


def _search(
    left: Any, right: Any, *, require_laws: bool, budget: List[int]
) -> Optional[Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]]:
    """The first renaming that works, or `None` if there is none.

    Raises `ComparisonTooLarge` when the budget runs out with the space
    unexhausted -- which is NOT the same answer as `None` and must never be
    collapsed into it.
    """
    left_species = _species_ids(left)
    right_species = _species_ids(right)
    right_parameters = set(_parameter_ids(right))
    left_parameters = set(_parameter_ids(left))

    signatures = {s: _species_signature(right, s) for s in right_species}
    candidates: Dict[str, List[str]] = {}
    for species in left_species:
        signature = _species_signature(left, species)
        candidates[species] = [
            other for other in right_species if signatures[other] == signature
        ]
        if not candidates[species]:
            return None

    order = _assignment_order(left, candidates)
    constraints = [
        (reaction, *_reaction_species(reaction, left_species))
        for reaction in left.reactions
    ]

    species_map: Dict[str, str] = {}
    used: set = set()

    def consistent(placed: str) -> bool:
        """Every reaction whose species are all placed still has a partner."""
        for reaction, stoichiometry, law_species in constraints:
            if placed not in stoichiometry and placed not in law_species:
                continue
            if any(s not in species_map for s in stoichiometry):
                continue
            check_laws = require_laws and all(
                s in species_map for s in law_species
            )
            if not _partners(
                reaction, right, species_map, left_parameters,
                right_parameters, check_laws,
            ):
                return False
        return True

    def descend(index: int):
        if index == len(order):
            return _match_reactions(
                left, right, species_map, left_parameters, right_parameters,
                require_laws, budget,
            )
        species = order[index]
        for candidate in candidates[species]:
            if candidate in used:
                continue
            budget[0] -= 1
            if budget[0] <= 0:
                raise _budget_exhausted(left, right)
            species_map[species] = candidate
            used.add(candidate)
            if consistent(species):
                found = descend(index + 1)
                if found is not None:
                    return found
            used.discard(candidate)
            del species_map[species]
        return None

    matched = descend(0)
    if matched is None:
        return None
    reaction_map, parameter_map = matched
    return dict(species_map), reaction_map, parameter_map


def _assignment_order(
    network: Any, candidates: Mapping[str, Sequence[str]]
) -> Tuple[str, ...]:
    """Species in the order the search should place them.

    Fewest candidates first, then breadth-first along shared reactions. The
    second half is what makes the pruning bite: placing a species that shares
    a reaction with one already placed immediately constrains that reaction,
    where placing an unrelated species constrains nothing and the search
    finds out only at the leaf.
    """
    species_ids = _species_ids(network)
    neighbours: Dict[str, set] = {s: set() for s in species_ids}
    for reaction in network.reactions:
        stoichiometry, law_species = _reaction_species(reaction, species_ids)
        members = set(stoichiometry) | set(law_species)
        for member in members:
            if member in neighbours:
                neighbours[member] |= members - {member}

    remaining = sorted(
        (s.id for s in network.species),
        key=lambda s: (len(candidates.get(s, ())), s),
    )
    order: List[str] = []
    placed: set = set()
    while remaining:
        seed = next(s for s in remaining if s not in placed)
        queue = [seed]
        while queue:
            current = queue.pop(0)
            if current in placed:
                continue
            placed.add(current)
            order.append(current)
            queue += sorted(
                (n for n in neighbours.get(current, ()) if n not in placed),
                key=lambda s: (len(candidates.get(s, ())), s),
            )
        remaining = [s for s in remaining if s not in placed]
    return tuple(order)


def _mapped(side: Mapping[str, int], species_map: Mapping[str, str]):
    out: Dict[str, int] = {}
    for species, count in side.items():
        target = species_map.get(species)
        if target is None:
            return None
        out[target] = int(count)
    return out


def _partners(
    reaction: Any,
    right: Any,
    species_map: Mapping[str, str],
    left_parameters: set,
    right_parameters: set,
    check_laws: bool,
) -> List[Any]:
    """Reactions of `right` this one could map onto, given the species so far."""
    reactants = _mapped(reaction.reactants, species_map)
    products = _mapped(reaction.products, species_map)
    if reactants is None or products is None:
        return list(right.reactions)
    out = []
    for other in right.reactions:
        if dict(other.reactants) != reactants or dict(other.products) != products:
            continue
        if check_laws and _align(
            reaction.rate_law, other.rate_law, species_map,
            {}, {}, left_parameters, right_parameters,
        ) is None:
            continue
        out.append(other)
    return out


def _match_reactions(
    left: Any,
    right: Any,
    species_map: Mapping[str, str],
    left_parameters: set,
    right_parameters: set,
    require_laws: bool,
    budget: List[int],
):
    """A bijection of reactions consistent with one bijection of parameters.

    The parameter map is built HERE rather than guessed, because a parameter
    has no structural signature of its own -- nothing distinguishes `Km` from
    `Ki` except the position it occupies in a rate law. Aligning the laws
    token by token is what pins it, and it has to be consistent across every
    reaction at once, which is why this is a search and not a loop.
    """
    reactions = list(left.reactions)
    targets = list(right.reactions)
    reaction_map: Dict[str, str] = {}
    used: set = set()

    def descend(index: int, parameter_map: Dict[str, str], reverse: Dict[str, str]):
        if index == len(reactions):
            return dict(reaction_map), dict(parameter_map)
        reaction = reactions[index]
        reactants = _mapped(reaction.reactants, species_map)
        products = _mapped(reaction.products, species_map)
        for other in targets:
            if other.id in used:
                continue
            if dict(other.reactants) != reactants or dict(other.products) != products:
                continue
            budget[0] -= 1
            if budget[0] <= 0:
                raise _budget_exhausted(left, right)
            extended = parameter_map
            extended_reverse = reverse
            if require_laws:
                aligned = _align(
                    reaction.rate_law, other.rate_law, species_map,
                    parameter_map, reverse, left_parameters, right_parameters,
                )
                if aligned is None:
                    continue
                extended, extended_reverse = aligned
            reaction_map[reaction.id] = other.id
            used.add(other.id)
            found = descend(index + 1, extended, extended_reverse)
            if found is not None:
                return found
            used.discard(other.id)
            del reaction_map[reaction.id]
        return None

    return descend(0, {}, {})


def _align(
    left_law: str,
    right_law: str,
    species_map: Mapping[str, str],
    parameter_map: Mapping[str, str],
    reverse: Mapping[str, str],
    left_parameters: set,
    right_parameters: set,
):
    """Extend the parameter map so one rate law becomes the other, or `None`.

    Token for token, with whitespace normalised away and numeric literals
    compared as numbers. See the module docstring for why this is not an
    algebraic comparison and which way it errs.
    """
    tokens_left = _lex(left_law)
    tokens_right = _lex(right_law)
    if len(tokens_left) != len(tokens_right):
        return None

    extended = dict(parameter_map)
    extended_reverse = dict(reverse)

    for (kind, text), (other_kind, other_text) in zip(tokens_left, tokens_right):
        if kind != other_kind:
            return None
        if kind == "symbol":
            if text != other_text:
                return None
        elif kind == "number":
            if float(text) != float(other_text):
                return None
        elif text in species_map:
            if species_map[text] != other_text:
                return None
        elif text in left_parameters:
            if other_text not in right_parameters:
                return None
            if extended.get(text, other_text) != other_text:
                return None
            if extended_reverse.get(other_text, text) != text:
                return None
            extended[text] = other_text
            extended_reverse[other_text] = text
        else:
            # A function name (`exp`, `sqrt`) or a species not yet placed.
            # Either way it has to be the same token: a renaming may not turn
            # `exp` into `ln`, and an unplaced species cannot be checked, so
            # requiring equality here is conservative rather than wrong -- the
            # caller only aligns laws whose species are all placed.
            if text != other_text:
                return None
    return extended, extended_reverse


def _complete_parameter_map(
    left: Any, right: Any, parameter_map: Mapping[str, str]
) -> Tuple[Dict[str, str], Tuple[str, ...]]:
    """Place the parameters no rate law mentions, and say that it did.

    A parameter appearing in no law cannot be located by evidence, because
    nothing in the model depends on it. It is paired off in declaration order
    so that the renaming is total, and it is listed in `unconstrained` so
    that a reader is never shown a pairing that was arrived at by
    elimination as though it had been found.
    """
    complete = dict(parameter_map)
    spare_left = [p for p in _parameter_ids(left) if p not in complete]
    taken = set(complete.values())
    spare_right = [p for p in _parameter_ids(right) if p not in taken]
    for name, other in zip(spare_left, spare_right):
        complete[name] = other
    return complete, tuple(spare_left)


def _values_match(
    left: Any,
    right: Any,
    species_map: Mapping[str, str],
    parameter_map: Mapping[str, str],
) -> bool:
    """Whether the numbers agree too, compared EXACTLY.

    No tolerance. Two constants differing in the last bit are two different
    constants, and a tolerance here would be a threshold nobody argued for
    standing between "the same model" and "a different one". Where the
    difference matters, `behavioural_difference` measures what it does to the
    predictions, which is the question a tolerance would have been a proxy
    for.
    """
    initials = {s.id: float(s.initial) for s in right.species}
    for species in left.species:
        if initials.get(species_map.get(species.id, "")) != float(species.initial):
            return False
    values = {p.id: float(p.value) for p in right.parameters}
    for parameter in left.parameters:
        if values.get(parameter_map.get(parameter.id, "")) != float(parameter.value):
            return False
    return True


def _law_differences(
    left: Any,
    right: Any,
    species_map: Mapping[str, str],
    reaction_map: Mapping[str, str],
) -> List[str]:
    """Which rate laws stop this renaming being an identity, in words."""
    laws = {reaction.id: reaction.rate_law for reaction in right.reactions}
    differences: List[str] = []
    for reaction in left.reactions:
        partner = reaction_map.get(reaction.id)
        if partner is None:
            continue
        if _align(
            reaction.rate_law, laws[partner], species_map, {}, {},
            set(_parameter_ids(left)), set(_parameter_ids(right)),
        ) is None:
            differences.append(
                f"the rate law of `{reaction.id}` (`{reaction.rate_law}`) "
                f"does not match that of `{partner}` "
                f"(`{laws[partner]}`)"
            )
    if not differences:
        # Every law aligns on its own and no single parameter renaming
        # aligns them all at once. A real and different finding: the two
        # models use the same FORMS with the constants wired to different
        # places, which is a mechanism difference that reading any one
        # reaction would miss.
        differences.append(
            "every rate law matches on its own, and no single renaming of "
            "the parameters matches them all at once -- the same forms with "
            "the constants wired differently"
        )
    return differences


def _why_no_wiring(left: Any, right: Any) -> List[str]:
    """The most specific reason the species could not be paired up."""
    signatures = {
        species: _species_signature(right, species)
        for species in _species_ids(right)
    }
    orphans = []
    for species in _species_ids(left):
        signature = _species_signature(left, species)
        if signature not in signatures.values():
            consumed = sum(1 for r in left.reactions if species in r.reactants)
            produced = sum(1 for r in left.reactions if species in r.products)
            orphans.append(
                f"`{species}` has no counterpart -- it is consumed by "
                f"{consumed} reaction(s) and produced by {produced}, and no "
                f"species of `{_name_of(right)}` is used that way"
            )
    if orphans:
        return orphans
    return [
        "every species has a counterpart by itself, but no way of pairing "
        "them all up at once carries one model's stoichiometry onto the "
        "other's -- the reactions connect the same kinds of species in "
        "different patterns"
    ]


# ---------------------------------------------------------------------------
# Conditions and readouts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Dose:
    """What is varied across an experiment, and the levels it takes.

    A SPECIES, not a parameter. A dose is something you put in the tube, and
    setting it changes the CONDITION the model is asked about. Turning a rate
    constant instead would change the model, and two models compared at
    different rate constants are not being compared -- whatever came out
    would be a statement about the constants.

    `basis` says where the levels came from, for the same reason `Precision`
    demands one: a dose range is a choice, the answer depends on it, and a
    range nobody stated cannot be argued with.
    """

    species: str
    levels: Tuple[float, ...]
    unit: str = ""
    basis: str = ""

    def __post_init__(self) -> None:
        levels = tuple(float(level) for level in self.levels)
        if not levels:
            raise ComparisonRefused(
                f"a dose series for {self.species!r} with no levels in it is "
                f"not an input range. Say which levels you would actually set."
            )
        for level in levels:
            if not math.isfinite(level) or level < 0.0:
                raise ComparisonRefused(
                    f"a dose of {level!r} for {self.species!r} is not a "
                    f"quantity anybody can add to a tube. Doses are "
                    f"non-negative and finite."
                )
        object.__setattr__(self, "levels", levels)

    def describe(self) -> str:
        return (
            f"`{self.species}` from {min(self.levels):g} to "
            f"{max(self.levels):g} {self.unit}".rstrip()
            + f" in {len(self.levels)} step(s)"
            + (f" ({self.basis})" if self.basis else "")
        )


def dose_series(
    species: str,
    centre: float,
    *,
    decades: float = DEFAULT_DOSE_DECADES,
    points: int = DEFAULT_DOSE_POINTS,
    unit: str = "",
    basis: str = "",
) -> Dose:
    """A geometric dose series around a stated amount.

    Geometric rather than linear because these mechanisms are separated by
    where a concentration sits relative to a binding constant, and that
    relationship is logarithmic: a linear series from 0 to 100 spends most of
    its points in the saturated region and has one point below the Km, which
    is the half of the curve the discrimination usually lives in.

    An odd number of points puts `centre` exactly in the series, so the
    conditions include the one the model already describes.
    """
    if centre <= 0.0:
        raise ComparisonRefused(
            f"a dose series around {centre!r} cannot be built: a geometric "
            f"range needs somewhere positive to start from. `{species}` "
            f"starts at zero in this model, so there is no amount to scale. "
            f"State the levels you mean instead."
        )
    if points < 1:
        raise ComparisonRefused(
            f"a dose series of {points} point(s) is not a range"
        )
    if points == 1:
        exponents = [0.0]
    else:
        step = (2.0 * decades) / (points - 1)
        exponents = [-decades + index * step for index in range(points)]
    return Dose(
        species=species,
        levels=tuple(centre * (10.0 ** exponent) for exponent in exponents),
        unit=unit,
        basis=basis or (
            f"illustrative: {decades:g} decades either side of the "
            f"{centre:g} this model holds, {points} points"
        ),
    )


#: What a readout reads. Named rather than implied, because the summary has
#: to say what was measured and "the value of X" is two different
#: experiments depending on which of these it means.
KIND_INITIAL_RATE = "initial rate of change"
KIND_STEADY_STATE = "steady-state level"


@dataclass(frozen=True)
class Readout:
    """One measurable quantity, and how accurately the MODEL computes it.

    `numerical_precision` is not the instrument's. It is the relative
    accuracy of the arithmetic that produced the number, and it is here for
    the same reason `sensitivity.Quantity` carries one: a difference smaller
    than the solver's own error is not a small difference between the models,
    it is the solver. The instrument's precision is a separate argument to
    the comparison, and the two are never mixed.
    """

    target: str
    kind: str
    measure: Callable[[Any, str], float]
    unit: str = ""
    numerical_precision: float = MACHINE_PRECISION

    @property
    def name(self) -> str:
        return f"{self.kind} of `{self.target}`"


def initial_rate_of(species: str, *, unit: str = "") -> Readout:
    """How fast a species is changing at t = 0 -- the initial-rate assay.

    THE DEFAULT READOUT, and deliberately not the steady state. A closed
    model's steady state is pinned by its conservation law: substrate
    inhibition, competitive inhibition and uncompetitive inhibition all end
    with every S converted to P, whatever the mechanism and whatever the
    constants. It is the one observation on which every mechanism that
    conserves the same moiety is guaranteed to agree, so an experiment
    designed against it would be designed against the place the models
    cannot differ.

    The initial rate is also what the experiment actually measures. Nobody
    runs a Lineweaver-Burk plot to completion.

    Exact to machine precision: the rate is the model's own rate laws
    evaluated once at the initial state, with no iteration behind it.
    """
    def measure(network: Any, target: str) -> float:
        rates = _derivatives(network)
        if target not in rates:
            raise ComparisonRefused(
                f"no species {target!r} in `{_name_of(network)}`. It has: "
                f"{', '.join(sorted(rates))}."
            )
        return float(rates[target])

    return Readout(
        target=species, kind=KIND_INITIAL_RATE, measure=measure, unit=unit,
        numerical_precision=MACHINE_PRECISION,
    )


def steady_state_of(species: str, *, unit: str = "") -> Readout:
    """Where a species ends up -- available, and rarely the discriminator.

    Delegates to `sensitivity.steady_state_of`, which refuses when the search
    finds no stable state or more than one. Those refusals arrive here as a
    SKIPPED condition with the reason attached rather than as a difference of
    zero, because "the models were not compared here" and "the models agree
    here" are opposite findings and only one of them is evidence.

    Costly: each evaluation is a global multistart search, so a dose series
    of nine levels is eighteen of them. Not in the default set for that
    reason and for the conservation-law reason in `initial_rate_of`.
    """
    def measure(network: Any, target: str) -> float:
        return float(_steady_state_quantity(target)(network))

    return Readout(
        target=species, kind=KIND_STEADY_STATE, measure=measure, unit=unit,
        numerical_precision=STEADY_STATE_PRECISION,
    )


def _derivatives(network: Any) -> Dict[str, float]:
    """dx/dt for every species at the amounts the network currently holds."""
    try:
        from . import analysis
    except ImportError:  # pragma: no cover - flat import
        import analysis  # type: ignore[no-redef]

    rhs, order = analysis.derivative_function(network)
    state = [float(s.initial) for s in network.species]
    return dict(zip(order, rhs(state)))


def _with_initial(network: Any, species: str, value: float) -> Any:
    return replace(
        network,
        species=tuple(
            replace(s, initial=float(value)) if s.id == species else s
            for s in network.species
        ),
    )


# ---------------------------------------------------------------------------
# One predicted measurement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Observation:
    """What the two models predict for one quantity under one condition."""

    readout: str
    target: str
    #: What was set to get here, and to what. `None` for the models as given.
    varied: Optional[str]
    level: Optional[float]
    unit: str
    left: float
    right: float
    #: The measurement error the stated precision implies at this size.
    error: float
    #: Below this a difference is the arithmetic's own rounding. A different
    #: floor with a different meaning -- see the module docstring.
    numerical_floor: float

    @property
    def difference(self) -> float:
        return self.right - self.left

    @property
    def agree(self) -> bool:
        """The two models computed the same number, bit for bit.

        Stronger than "small", and worth its own name: where this holds, no
        instrument at any precision separates the models at this condition,
        and saying so is a finding rather than a failure to find one.
        """
        return self.difference == 0.0

    @property
    def resolvable(self) -> bool:
        """The difference is bigger than the arithmetic that produced it."""
        return abs(self.difference) > self.numerical_floor

    @property
    def separation(self) -> float:
        """The difference, counted in stated measurement errors."""
        gap = abs(self.difference)
        if self.error <= 0.0:
            # Both predictions are zero and the precision has no absolute
            # term, so there is no scale to measure against. Zero rather than
            # infinity: nothing was separated.
            return 0.0 if gap == 0.0 else float("inf")
        return gap / self.error

    @property
    def measurable(self) -> bool:
        # Both floors, and `resolvable` first: a difference below the
        # arithmetic's own error must never be called measurable, however
        # good the instrument is said to be.
        return self.resolvable and self.separation >= MEASURABLE

    @property
    def decisive(self) -> bool:
        return self.resolvable and self.separation >= DECISIVE

    @property
    def condition(self) -> str:
        if self.varied is None:
            return "at the amounts both models hold"
        return f"with `{self.varied}` set to {self.level:g} {self.unit}".rstrip()

    def describe(self) -> str:
        if self.agree:
            return (
                f"{self.condition}: both models predict {self.left:.6g} "
                f"{self.unit}".rstrip()
                + " -- identical, so this observation cannot tell them apart "
                "however well it is measured"
            )
        if not self.resolvable:
            return (
                f"{self.condition}: the predictions differ by "
                f"{abs(self.difference):.2g}, below this readout's own "
                f"arithmetic floor of {self.numerical_floor:.1g}. The "
                f"difference cannot be told from rounding, which is not the "
                f"same as there being none"
            )
        verdict = (
            "decisive" if self.decisive
            else "visible" if self.measurable
            else "inside the error bar, so it separates nothing"
        )
        return (
            f"{self.condition}: {self.left:.6g} against {self.right:.6g} "
            f"{self.unit}".rstrip()
            + f", a difference of {abs(self.difference):.3g} = "
            f"{self.separation:.2g}x the stated measurement error of "
            f"{self.error:.3g} -- {verdict}"
        )


# ---------------------------------------------------------------------------
# Behaviour: where do the predictions diverge?
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DifferenceReport:
    """One readout, two models, over one stated range of one input."""

    left: str
    right: str
    readout: str
    dose: Optional[Dose]
    precision: Precision
    observations: Tuple[Observation, ...]
    #: Conditions that could not be evaluated, with the reason. Kept apart
    #: from the results because a condition that was not evaluated is not a
    #: condition where the models agreed, and folding the two together would
    #: turn a failure to look into a finding.
    skipped: Mapping[str, str] = field(default_factory=dict)

    @property
    def ranked(self) -> Tuple[Observation, ...]:
        """By separation in stated measurement errors, widest first.

        NOT by the raw difference. A difference you cannot measure is not a
        wide one, and ranking by size alone would put an enormous
        unmeasurable gap above a small decisive one -- which is precisely the
        mistake this module exists to avoid.
        """
        return tuple(
            sorted(self.observations, key=lambda o: o.separation, reverse=True)
        )

    @property
    def widest(self) -> Optional[Observation]:
        return self.ranked[0] if self.observations else None

    @property
    def measurable(self) -> Tuple[Observation, ...]:
        return tuple(o for o in self.ranked if o.measurable)

    @property
    def crossings(self) -> Tuple[Observation, ...]:
        """Conditions at which the two models predict the same thing exactly.

        Worth reporting on their own. Competitive and uncompetitive
        inhibition cross at exactly S = Km, and an assay run there separates
        them by nothing at any precision -- which is a real property of the
        pair of mechanisms and not a shortcoming of the experiment.
        """
        return tuple(o for o in self.observations if o.agree)

    @property
    def identical(self) -> bool:
        return bool(self.observations) and all(o.agree for o in self.observations)

    @property
    def indistinguishable(self) -> bool:
        return not any(o.measurable for o in self.observations)

    def summary(self) -> str:
        where = (
            f"varying {self.dose.describe()}" if self.dose
            else "at the amounts both models hold"
        )
        lines = [
            f"{self.readout}: `{self.left}` against `{self.right}`, "
            f"{len(self.observations)} condition(s), {where}. Measurement "
            f"precision assumed: {self.precision.describe()}."
        ]

        if not self.observations:
            lines.append(
                "Nothing was compared -- every condition was skipped, so this "
                "is not a finding that the models agree. Nothing was measured."
            )
        elif self.identical:
            lines.append(
                f"The two models predict the SAME value at every one of the "
                f"{len(self.observations)} conditions tried. Over this "
                f"readout and this range they are one model, and no "
                f"instrument at any precision decides between them."
            )
        else:
            lines.append("Widest: " + self.widest.describe() + ".")
            decisive = [o for o in self.observations if o.decisive]
            measurable = self.measurable
            if measurable:
                lines.append(
                    f"{len(measurable)} of {len(self.observations)} "
                    f"condition(s) separate the models by at least the stated "
                    f"precision; {len(decisive)} by {DECISIVE:g} errors or "
                    f"more."
                )
            else:
                lines.append(
                    f"NONE of the {len(self.observations)} conditions "
                    f"separates the models by as much as the stated "
                    f"precision. The differences are real and they are inside "
                    f"the error bar, which means this readout over this range "
                    f"is not an experiment."
                )
            if self.crossings:
                lines.append(
                    f"{len(self.crossings)} condition(s) give IDENTICAL "
                    f"predictions: "
                    + ", ".join(o.condition for o in self.crossings)
                    + ". An experiment run there cannot tell the models "
                    "apart however well it is measured -- the curves cross."
                )

        if self.skipped:
            lines.append(
                f"{len(self.skipped)} condition(s) were skipped: "
                + "; ".join(f"{k} ({v})" for k, v in self.skipped.items())
                + ". Not compared is not the same as found to agree."
            )

        lines.append(
            "Both models were asked at the constants they currently hold. If "
            "those are the motif library's illustrative placeholders, this "
            "says which experiment separates THESE two parameterised models "
            "-- not which separates the two mechanisms in general."
        )
        return " ".join(lines)


def behavioural_difference(
    a: Any,
    b: Any,
    readout: Any,
    doses: Optional[Dose] = None,
    *,
    precision: Precision = DEFAULT_PRECISION,
    correspondence: Optional[Mapping[str, str]] = None,
) -> DifferenceReport:
    """Where two models' predictions for one readout diverge, over one range.

    `doses` states the input range and what it is a range OF. `None` compares
    the models at the amounts they already hold, which is one condition and
    is reported as such -- a single point is a comparison, not a
    dose-response, and the summary does not let it read as one.

    `correspondence` maps names in `a` to names in `b`, for a pair related by
    a renaming; `structurally_identical(...).renaming` is exactly that map.
    Without it the two models are compared by name, and a readout missing
    from one of them is a refusal rather than a skipped condition -- a typo
    must not come back as "no difference found".
    """
    left = _network_of(a)
    right = _network_of(b)
    if isinstance(readout, str):
        readout = initial_rate_of(readout)
    if doses is not None and not isinstance(doses, Dose):
        raise ComparisonRefused(
            "a bare sequence of numbers is not a dose series: it does not say "
            "what it is a dose OF, and the same numbers mean different "
            "experiments for a substrate and for an inhibitor. Wrap them: "
            "Dose(species, levels, unit, basis)."
        )

    translate = dict(correspondence or {})

    def over_there(name: str) -> str:
        return translate.get(name, name)

    _require_species(left, readout.target, "the readout")
    _require_species(right, over_there(readout.target), "the readout")
    if doses is not None:
        _require_species(left, doses.species, "the dosed species")
        _require_species(right, over_there(doses.species), "the dosed species")

    if doses is None:
        conditions: Sequence[Tuple[Optional[str], Optional[float]]] = ((None, None),)
    else:
        conditions = tuple((doses.species, level) for level in doses.levels)

    observations: List[Observation] = []
    skipped: Dict[str, str] = {}

    for varied, level in conditions:
        if varied is None:
            here, there = left, right
            label = "at the amounts both models hold"
        else:
            here = _with_initial(left, varied, level)
            there = _with_initial(right, over_there(varied), level)
            label = f"`{varied}` = {level:g} {doses.unit}".rstrip()

        try:
            x = float(readout.measure(here, readout.target))
            y = float(readout.measure(there, over_there(readout.target)))
        except Exception as exc:  # noqa: BLE001 - the reason is the value
            skipped[label] = str(exc)
            continue
        if not (math.isfinite(x) and math.isfinite(y)):
            skipped[label] = (
                "one of the models does not produce a finite prediction here"
            )
            continue

        scale = max(abs(x), abs(y))
        observations.append(Observation(
            readout=readout.name,
            target=readout.target,
            varied=varied,
            level=level,
            unit=doses.unit if doses is not None else readout.unit,
            left=x,
            right=y,
            error=precision.error_in(x, y),
            # The same factor of ten `sensitivity.SAFETY` argues for, for the
            # same reason: the balance point is where a typical error sits,
            # not a bound on one, and four significant figures nobody reads
            # buys the difference between a floor and a wish.
            numerical_floor=SAFETY * readout.numerical_precision * scale,
        ))

    return DifferenceReport(
        left=_name_of(left), right=_name_of(right), readout=readout.name,
        dose=doses, precision=precision,
        observations=tuple(observations), skipped=skipped,
    )


def _require_species(network: Any, name: str, what: str) -> None:
    if any(s.id == name for s in network.species):
        return
    raise ComparisonRefused(
        f"{what} names {name!r}, which is not a species of "
        f"`{_name_of(network)}`. It has: "
        f"{', '.join(_species_ids(network))}. If the two models are the same "
        f"network under different names, `structurally_identical` reports the "
        f"renaming and it can be passed as `correspondence`."
    )


# ---------------------------------------------------------------------------
# The experiment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiscriminatingExperiment:
    """The one observation that separates two models best, and by how much."""

    left: str
    right: str
    observation: Observation
    precision: Precision
    #: Every report that was searched, so the runner-up conditions are
    #: readable rather than discarded.
    reports: Tuple[DifferenceReport, ...]
    #: Inputs that were varied. Named because the answer is only as broad as
    #: this list, and a reader has to be able to see what was not tried.
    varied: Tuple[str, ...]
    considered: int
    #: Observations that separate the models exactly as well. A tie is
    #: reported rather than broken silently: measuring substrate depletion
    #: and product appearance are the same experiment read two ways, and
    #: naming only one of them would make an arbitrary choice look like a
    #: finding.
    ties: Tuple[Observation, ...] = ()
    skipped: Mapping[str, str] = field(default_factory=dict)

    def protocol(self) -> str:
        """The experiment in one imperative sentence."""
        observation = self.observation
        setting = (
            f"with `{observation.varied}` set to {observation.level:g} "
            f"{observation.unit}".rstrip()
            if observation.varied is not None
            else "at the amounts both models hold"
        )
        return (
            f"Measure the {observation.readout} {setting}. "
            f"`{self.left}` predicts {observation.left:.6g}; "
            f"`{self.right}` predicts {observation.right:.6g}. That is "
            f"{observation.separation:.2g} times the measurement error you "
            f"stated ({observation.error:.3g})."
        )

    def summary(self) -> str:
        lines = [self.protocol()]
        if not self.observation.decisive:
            lines.append(
                f"Above the stated precision and below {DECISIVE:g} errors: "
                f"visible, and thin for a single measurement. Replicates, or "
                f"a better instrument, turn this into an argument."
            )
        if self.ties:
            lines.append(
                f"{len(self.ties)} other observation(s) separate them exactly "
                f"as well: "
                + "; ".join(f"{o.readout} {o.condition}" for o in self.ties)
                + ". Pick whichever is easier to measure -- nothing here "
                "prefers one."
            )
        lines.append(
            f"Searched {self.considered} observation(s) over "
            + (
                "the inputs " + ", ".join(f"`{v}`" for v in self.varied)
                if self.varied else "no varied input at all"
            )
            + ". Everything else was held where the models put it, and one "
            "input was varied at a time -- an observation that separates "
            "these models better under some other input, or under two moved "
            "together, would not have been found here."
        )
        if self.skipped:
            lines.append(
                f"{len(self.skipped)} condition(s) could not be evaluated and "
                f"were not part of the search."
            )
        lines.append(
            f"The separation is a count of stated measurement errors, not a "
            f"p-value: it assumes nothing about how the error is distributed "
            f"and it is only as good as {self.precision.describe()}. And both "
            f"models were asked at the constants they currently hold, so if "
            f"those are illustrative placeholders this separates two "
            f"parameterised models rather than two mechanisms."
        )
        return " ".join(lines)


def discriminating_experiment(
    a: Any,
    b: Any,
    *,
    readouts: Optional[Sequence[Readout]] = None,
    doses: Optional[Sequence[Dose]] = None,
    precision: Precision = DEFAULT_PRECISION,
    correspondence: Optional[Mapping[str, str]] = None,
) -> DiscriminatingExperiment:
    """The observation whose predicted values differ most, relative to what
    you can measure.

    Refuses with `ModelsIndistinguishable` when nothing tried clears the
    stated precision. That refusal is the finding, not a failure to produce
    one: two mechanisms that predict the same numbers are not two hypotheses,
    and returning the argmax anyway would send somebody to the bench to
    measure a difference their instrument cannot see.

    With nothing named, the search is the one `default_readouts` and
    `default_doses` describe -- the initial rate of every shared species,
    over a dose series of every species the models consume and never make.
    Narrow on purpose; the result says what was varied so that the narrowness
    is visible rather than implied.
    """
    left = _network_of(a)
    right = _network_of(b)
    chosen = (
        tuple(readouts) if readouts is not None
        else default_readouts(a, b, correspondence=correspondence)
    )
    if not chosen:
        raise ComparisonRefused(
            f"`{_name_of(left)}` and `{_name_of(right)}` share no species by "
            f"name, so there is no quantity both of them predict and nothing "
            f"to compare. If one is a renaming of the other, "
            f"`structurally_identical` reports the renaming; pass it as "
            f"`correspondence`."
        )
    series = (
        tuple(doses) if doses is not None
        # `a` rather than `left`, so that a composed model can still say what
        # unit its concentrations are in -- `core.network.Species` carries an
        # amount and no unit, and the composition is the only thing that
        # knows. See `_dose_unit`.
        else default_doses(a, b, correspondence=correspondence)
    )

    reports: List[DifferenceReport] = []
    for readout in chosen:
        if series:
            for dose in series:
                reports.append(behavioural_difference(
                    left, right, readout, dose,
                    precision=precision, correspondence=correspondence,
                ))
        else:
            reports.append(behavioural_difference(
                left, right, readout, None,
                precision=precision, correspondence=correspondence,
            ))

    observations = [o for report in reports for o in report.observations]
    skipped = {
        label: reason
        for report in reports
        for label, reason in report.skipped.items()
    }
    varied = tuple(dict.fromkeys(dose.species for dose in series))

    if not observations:
        raise ComparisonRefused(
            f"nothing was compared: all {len(skipped)} condition(s) failed to "
            f"evaluate, so there is no evidence either way about whether "
            f"these models differ. Reason(s): "
            + "; ".join(sorted(set(skipped.values())))
            + "."
        )

    ranked = sorted(observations, key=lambda o: o.separation, reverse=True)
    best = ranked[0]
    if not best.measurable:
        raise _indistinguishable(
            left, right, ranked, precision, varied, skipped
        )

    return DiscriminatingExperiment(
        left=_name_of(left), right=_name_of(right),
        observation=best, precision=precision, reports=tuple(reports),
        varied=varied, considered=len(observations),
        ties=tuple(
            o for o in ranked[1:] if o.separation == best.separation
        ),
        skipped=skipped,
    )


def _indistinguishable(
    left: Any,
    right: Any,
    ranked: Sequence[Observation],
    precision: Precision,
    varied: Sequence[str],
    skipped: Mapping[str, str],
) -> ModelsIndistinguishable:
    """The refusal, with the three cases that reach it kept apart.

    They call for different things. Predictions that are identical
    EVERYWHERE need no instrument at all -- there is nothing there. A
    difference below the arithmetic's own floor needs a better solver before
    anybody buys a better instrument. A real difference inside the error bar
    needs a named, computable improvement in precision, and saying what that
    number is turns a refusal into the next step.
    """
    best = ranked[0]
    scope = (
        "varying " + ", ".join(f"`{v}`" for v in varied)
        if varied else "at the amounts both models hold"
    )
    lines = [
        f"no observation among the {len(ranked)} compared separates "
        f"`{_name_of(left)}` from `{_name_of(right)}` by as much as the "
        f"stated measurement precision, so none of them is an experiment."
    ]

    if all(o.agree for o in ranked):
        lines.append(
            f"Every difference was exactly zero, at every condition tried "
            f"({scope}). No instrument, at any precision, separates them "
            f"there: within what was varied these are not two hypotheses but "
            f"one prediction written twice, and the failure is in the "
            f"question rather than in the assay. Whether the same is true of "
            f"their STRUCTURE -- and so of every condition rather than only "
            f"these -- is what `structurally_identical` answers."
        )
    elif not best.resolvable:
        lines.append(
            f"The largest difference found, {abs(best.difference):.2g} "
            f"{best.condition}, is below that readout's own arithmetic floor "
            f"of {best.numerical_floor:.1g}. That is a statement about the "
            f"solver rather than about the models: the difference could not "
            f"be told from rounding, which is not the same as there being "
            f"none, and a better instrument would not help until a better "
            f"computation showed there was something to measure."
        )
    else:
        scale = max(abs(best.left), abs(best.right))
        needed = abs(best.difference) / MEASURABLE
        fraction = (
            f", which is {needed / scale:.2%} of the value"
            if scale > 0.0 else ""
        )
        lines.append(
            f"The largest difference found is {best.condition}, where "
            f"`{_name_of(left)}` predicts {best.left:.6g} and "
            f"`{_name_of(right)}` predicts {best.right:.6g} -- a gap of "
            f"{abs(best.difference):.3g} against a stated error of "
            f"{best.error:.3g}, so {best.separation:.2g} of the one error it "
            f"would need. The difference is REAL and it is inside your error "
            f"bar. To see it you would need a measurement error below "
            f"{needed:.3g}{fraction}."
        )

    if skipped:
        lines.append(
            f"{len(skipped)} condition(s) could not be evaluated and are not "
            f"part of this: they were not compared, which is not the same as "
            f"having been found to agree."
        )
    lines.append(
        f"What was searched: {scope}, one input at a time. A different "
        f"observable, an input this call did not vary, or two varied "
        f"together may still separate them -- this says only that what was "
        f"tried does not."
    )
    return ModelsIndistinguishable(" ".join(lines))


# ---------------------------------------------------------------------------
# The default search
# ---------------------------------------------------------------------------


def default_readouts(
    a: Any, b: Any, *, correspondence: Optional[Mapping[str, str]] = None
) -> Tuple[Readout, ...]:
    """The initial rate of change of every species the models share.

    Initial rates rather than steady states, for the reason
    `initial_rate_of` argues: a closed model's steady state is fixed by its
    conservation law, so it is the one observation on which every mechanism
    conserving the same moiety is guaranteed to agree. Designing an
    experiment against it would be designing against the place two mechanisms
    cannot differ.
    """
    left, right = _network_of(a), _network_of(b)
    translate = dict(correspondence or {})
    there = set(_species_ids(right))
    return tuple(
        initial_rate_of(species)
        for species in _species_ids(left)
        if translate.get(species, species) in there
    )


def default_doses(
    a: Any, b: Any, *, correspondence: Optional[Mapping[str, str]] = None
) -> Tuple[Dose, ...]:
    """A dose series for every species the models consume and never make.

    A species a reaction eats and nothing produces is an INPUT: it is the
    thing you put in the tube, and it is the axis every one of the classical
    mechanism discriminations is drawn against. A species the model makes is
    an output and dosing it describes a different experiment.

    What this deliberately does not do is vary everything it could. An
    inhibitor is a modifier rather than a reactant, so it is not dosed here
    -- and an inhibitor dose-response is a real and sometimes better
    discrimination. It is one `Dose` away and the report names what it
    varied, because an argmax over a space nobody stated is a confident
    answer to a question nobody asked.
    """
    left, right = _network_of(a), _network_of(b)
    translate = dict(correspondence or {})
    over_there = {
        species: translate.get(species, species)
        for species in _species_ids(left)
    }
    initials = {s.id: float(s.initial) for s in left.species}
    right_inputs = _pure_inputs(right)

    out: List[Dose] = []
    for species in _pure_inputs(left):
        if over_there[species] not in right_inputs:
            continue
        if initials.get(species, 0.0) <= 0.0:
            # No amount to scale, so no geometric range. Skipped rather than
            # guessed at: a dose range invented around zero would be a number
            # this module made up.
            continue
        out.append(dose_series(
            species, initials[species],
            unit=_dose_unit(a),
        ))
    return tuple(out)


def _pure_inputs(network: Any) -> Tuple[str, ...]:
    consumed = {s for r in network.reactions for s in r.reactants}
    produced = {s for r in network.reactions for s in r.products}
    return tuple(
        species for species in _species_ids(network)
        if species in consumed and species not in produced
    )


def _dose_unit(model: Any) -> str:
    """The concentration unit the model's own composition declared.

    Recovered from the composition rather than assumed, for the reason
    `scale.units_from_model` records: `core.network.Species` carries an
    amount and no unit, so a bare network genuinely does not know what its
    numbers mean. An empty string when nothing declared one, which prints as
    a number with no unit -- honest, and visibly missing.
    """
    composition = getattr(
        getattr(model, "recognition", None), "composition", None
    )
    return str(getattr(composition, "concentration_unit", "") or "")


__all__ = [
    "ComparisonRefused", "ComparisonTooLarge", "ModelsIndistinguishable",
    "Precision", "DEFAULT_PRECISION",
    "StructuralComparison", "structurally_identical",
    "Dose", "dose_series", "Readout", "initial_rate_of", "steady_state_of",
    "KIND_INITIAL_RATE", "KIND_STEADY_STATE",
    "Observation", "DifferenceReport", "behavioural_difference",
    "DiscriminatingExperiment", "discriminating_experiment",
    "default_readouts", "default_doses",
    "MEASURABLE", "DECISIVE", "STEADY_STATE_PRECISION",
    "DEFAULT_DOSE_DECADES", "DEFAULT_DOSE_POINTS",
    "MAX_SPECIES_FOR_ISOMORPHISM", "MAX_REACTIONS_FOR_ISOMORPHISM",
    "MAX_PARTIAL_ASSIGNMENTS",
]
