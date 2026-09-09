"""Knockouts, overexpression, inhibitors -- the experiment, in the model.

WHY THIS IS THE SURFACE THAT MATTERS
-------------------------------------
Everything else in `compose/` speaks in the language of the model: rate
constants, eigenvalues, steady states, sensitivities. A researcher at a bench
does not have a question about a rate constant. They have a question about an
experiment:

    what happens if I knock this gene out
    what happens if I overexpress it tenfold
    what happens if I add ten micromolar of this inhibitor
    which of these three perturbations tells me the most

Those are the same questions the rest of the module can answer, phrased the
way the work is actually planned. This module is the translation, and the
translation is not cosmetic -- a knockout is NOT "set kcat to zero", and the
difference between those two is the most interesting thing here.

A KNOCKOUT REMOVES A GENE, NOT A RATE CONSTANT
------------------------------------------------
Setting kcat to zero leaves the enzyme protein in the model, still binding
substrate, still sequestering it away from competing reactions. That is a
CATALYTICALLY DEAD MUTANT, which is a real and different experiment -- and one
people deliberately build, precisely because it separates the enzyme's
catalytic role from its binding role.

A knockout removes the protein: the concentration goes to zero, the substrate
it was sequestering is released, and any moiety it belonged to loses a member.

Both are supported, they are named differently, and the module refuses to
treat them as synonyms. Reporting a dead-mutant result as a knockout would
answer a question nobody asked with a number that looks right.

WHAT AN INHIBITOR IS, AND THE ONE THIS CANNOT DO
--------------------------------------------------
Adding a competitive inhibitor at concentration I raises the apparent Km by
(1 + I/Ki). That is exact, it is what `library.COMPETITIVE_INHIBITION` already
encodes, and this module applies it to a model that does not already have an
inhibitor term.

It cannot invent Ki. If the model does not carry a Ki for that inhibitor and
the caller does not supply one, the perturbation is REFUSED -- an inhibitor
whose potency is unknown perturbs the model by an unknown amount, and choosing
a plausible Ki would be exactly the fabrication this project exists to
prevent. The refusal names Ki and says which table would hold it.

WHAT IS AND IS NOT COMPARED
----------------------------
A perturbation returns a new model. What you do with it is the rest of the
module's business: `analysis.analyse` for the new steady state, `simulate.run`
for the time course, `robustness.assess` for whether the effect survives the
placeholder values. `compare` here does the one thing that needs both models
at once -- the fold change, with the arithmetic of "the control was zero"
handled explicitly rather than producing an infinity nobody reads.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: How much of the wild-type level an "overexpression" means, when the
#: caller does not say.
#:
#: A STATED CHOICE. Ten-fold is what a strong plasmid promoter typically
#: buys over a chromosomal copy, and it is the number people mean when they
#: say "overexpressed" without qualification. It is reported in every
#: result, because a fold change is meaningless without the fold.
DEFAULT_OVEREXPRESSION_FOLD = 10.0

#: What a knockout sets a concentration to.
#:
#: Exactly zero, not a small number. A "leaky" knockout is a different
#: experiment (a knockdown), it has its own function here, and blurring
#: them would make a clean genetic result into a dose-response.
KNOCKOUT_LEVEL = 0.0

#: Below this absolute value a control level counts as zero for the purpose
#: of a fold change. Dividing by a steady state of 1e-18 produces a fold
#: change of 1e18, which is arithmetic rather than biology.
NEGLIGIBLE_CONTROL = 1e-12


class PerturbationRefused(RuntimeError):
    """The perturbation cannot be applied, and the reason says why."""


@dataclass(frozen=True)
class Perturbation:
    """One in-silico experiment, and what it did to the model.

    Carries the DESCRIPTION alongside the modified network so a result can
    never be reported without saying what was done to produce it. A fold
    change with no statement of the perturbation is a number with no
    experiment attached.
    """

    kind: str
    target: str
    description: str
    network: Any
    #: parameter or species id -> (before, after). Every change, so a reader
    #: can reconstruct the perturbed model from the control without trusting
    #: this module.
    changes: Mapping[str, Tuple[float, float]] = field(default_factory=dict)

    def summary(self) -> str:
        moves = ", ".join(
            f"{name}: {before:g} -> {after:g}"
            for name, (before, after) in sorted(self.changes.items())
        )
        return f"{self.description} ({moves})" if moves else self.description


# ---------------------------------------------------------------------------
# Applying a perturbation
# ---------------------------------------------------------------------------


def _species_ids(network: Any) -> Tuple[str, ...]:
    return tuple(s.id for s in network.species)


def _parameter_ids(network: Any) -> Tuple[str, ...]:
    return tuple(p.id for p in network.parameters)


def _require_species(network: Any, name: str) -> Any:
    for species in network.species:
        if species.id == name:
            return species
    raise PerturbationRefused(
        f"no species {name!r} in this model. It has: "
        f"{', '.join(sorted(_species_ids(network)))}."
    )


def _require_parameter(network: Any, name: str) -> Any:
    for parameter in network.parameters:
        if parameter.id == name:
            return parameter
    raise PerturbationRefused(
        f"no parameter {name!r} in this model. It has: "
        f"{', '.join(sorted(_parameter_ids(network)))}."
    )


def _with_initial(network: Any, name: str, value: float) -> Any:
    return replace(
        network,
        species=tuple(
            replace(s, initial=float(value)) if s.id == name else s
            for s in network.species
        ),
    )


def _with_parameter(network: Any, name: str, value: float) -> Any:
    return replace(
        network,
        parameters=tuple(
            replace(p, value=float(value)) if p.id == name else p
            for p in network.parameters
        ),
    )


def knockout(network: Any, species: str) -> Perturbation:
    """Remove a gene product entirely: its concentration goes to zero.

    NOT the same as setting its catalytic constant to zero -- see
    `catalytically_dead`. A knockout removes the protein, so whatever it was
    binding is released; a dead mutant leaves the protein in place, still
    sequestering its substrate. People build dead mutants on purpose to
    separate those two roles, and a module that treated them as synonyms
    would answer the wrong experiment.

    Refuses when the species is already at zero: "knocked out" and "was
    never there" produce identical models and different papers.
    """
    target = _require_species(network, species)
    before = float(target.initial)
    if before == KNOCKOUT_LEVEL:
        raise PerturbationRefused(
            f"{species} is already at {KNOCKOUT_LEVEL:g}, so knocking it out "
            f"changes nothing and the comparison would report a null result "
            f"for a perturbation that was never applied. If the model is "
            f"meant to start with some, set its initial amount first."
        )
    return Perturbation(
        kind="knockout",
        target=species,
        description=f"{species} knocked out (removed from the model)",
        network=_with_initial(network, species, KNOCKOUT_LEVEL),
        changes={species: (before, KNOCKOUT_LEVEL)},
    )


def knockdown(network: Any, species: str, remaining_fraction: float) -> Perturbation:
    """Reduce a species to a fraction of its level -- RNAi, a weak promoter.

    Distinct from a knockout because the biology is distinct: a knockdown
    leaves protein behind, and a pathway with a threshold can be entirely
    insensitive to 90% knockdown and collapse at 99%. Reporting a knockdown
    as a knockout would attribute a graded result to a clean genetic one.
    """
    if not (0.0 < remaining_fraction < 1.0):
        raise PerturbationRefused(
            f"a knockdown to {remaining_fraction:g} of wild type is not a "
            f"knockdown: the fraction must lie strictly between 0 and 1. "
            f"Use knockout() for 0 and overexpress() for more than 1."
        )
    target = _require_species(network, species)
    before = float(target.initial)
    after = before * remaining_fraction
    return Perturbation(
        kind="knockdown",
        target=species,
        description=(
            f"{species} knocked down to {remaining_fraction:.0%} of wild type"
        ),
        network=_with_initial(network, species, after),
        changes={species: (before, after)},
    )


def overexpress(
    network: Any, species: str, fold: float = DEFAULT_OVEREXPRESSION_FOLD
) -> Perturbation:
    """Raise a species' level by a stated fold.

    The fold is in the description because "overexpressed" without a number
    is not a reproducible experiment, and two labs meaning 5x and 500x will
    disagree about the result while agreeing about the word.
    """
    if fold <= 1.0:
        raise PerturbationRefused(
            f"a fold of {fold:g} is not overexpression. Use knockdown() for "
            f"less than wild type and knockout() for none."
        )
    target = _require_species(network, species)
    before = float(target.initial)
    if before == 0.0:
        raise PerturbationRefused(
            f"{species} starts at zero, and any multiple of zero is zero. "
            f"Overexpressing something the model does not have requires "
            f"saying how much to add, not how many times more -- set its "
            f"initial amount instead."
        )
    after = before * fold
    return Perturbation(
        kind="overexpression",
        target=species,
        description=f"{species} overexpressed {fold:g}-fold",
        network=_with_initial(network, species, after),
        changes={species: (before, after)},
    )


def catalytically_dead(
    network: Any, parameter: str, *, unit: Optional[str] = None
) -> Perturbation:
    """Set a turnover number to zero, leaving the protein in place.

    The dead-mutant experiment. The protein is still there, still binding
    its substrate, still competing for it with everything else -- which is
    exactly why the experiment is done, and exactly what a knockout does
    not do.

    Refuses on a parameter that is not a rate constant: setting a Km to
    zero makes an enzyme infinitely avid rather than inactive, which is the
    opposite of the intended perturbation.

    THE UNIT HAS TO COME FROM SOMEWHERE, AND THE IR DOES NOT CARRY IT.
    `core.network.Parameter` has an id and a value and no unit, so the
    network alone cannot say whether a constant is a rate or an affinity --
    the same gap `compose/scale.py` documents. Pass `unit=`, or use
    `dead_mutant` which recovers it from the model's own motifs. Guessing
    from the name would be the fabrication this project refuses: a model
    whose author called a rate constant `Kcat_app` and an affinity `k_m`
    would get the opposite perturbation, silently.
    """
    target = _require_parameter(network, parameter)
    unit = unit if unit is not None else getattr(target, "unit", None)
    if unit is None:
        raise PerturbationRefused(
            f"no unit is recorded for {parameter}, and this perturbation is "
            f"only meaningful on a rate constant -- zeroing an affinity "
            f"makes an enzyme infinitely avid, which is the opposite "
            f"experiment. core.network.Parameter carries no unit, so pass "
            f"unit= or use dead_mutant(model, {parameter!r}), which reads it "
            f"from the motif that declared it."
        )
    unit = str(unit)
    if "/s" not in unit.replace(" ", ""):
        raise PerturbationRefused(
            f"{parameter} has unit {unit!r}, which is not a rate. A "
            f"catalytically dead mutant has a turnover number of zero; "
            f"zeroing an affinity constant instead makes the enzyme "
            f"infinitely avid, which is the opposite perturbation."
        )
    before = float(target.value)
    if before == 0.0:
        raise PerturbationRefused(
            f"{parameter} is already zero, so this changes nothing."
        )
    return Perturbation(
        kind="catalytically_dead",
        target=parameter,
        description=(
            f"{parameter} set to zero -- a catalytically dead mutant, with "
            f"the protein still present and still binding"
        ),
        network=_with_parameter(network, parameter, 0.0),
        changes={parameter: (before, 0.0)},
    )


def competitive_inhibitor(
    network: Any,
    affinity_parameter: str,
    *,
    concentration: float,
    ki: Optional[float] = None,
    ki_parameter: Optional[str] = None,
) -> Perturbation:
    """Add a competitive inhibitor, raising apparent Km by (1 + I/Ki).

    Exact for competitive inhibition, which is the case where the inhibitor
    binds free enzyme only. It is the right transformation and the wrong one
    for uncompetitive or mixed inhibition, which change Vmax too -- so this
    function is named for the mechanism it implements and refuses to be a
    generic "add inhibitor".

    Ki MUST come from somewhere: the model (`ki_parameter`) or the caller
    (`ki`). It is never guessed. An inhibitor of unknown potency perturbs
    the model by an unknown amount, and picking a plausible Ki would put a
    fabricated number at the centre of the result -- which is the one thing
    this project refuses to do. The refusal names the BRENDA table that
    holds Ki values, so the reader knows where to look.
    """
    target = _require_parameter(network, affinity_parameter)
    if concentration < 0.0:
        raise PerturbationRefused(
            f"an inhibitor concentration of {concentration:g} is negative"
        )

    if ki is None and ki_parameter is None:
        raise PerturbationRefused(
            f"no Ki for this inhibitor. The apparent Km rises by "
            f"(1 + I/Ki), so without Ki the perturbation has an unknown "
            f"size and a plausible-looking guess would put an invented "
            f"number at the centre of the answer. Supply ki=, or name a "
            f"ki_parameter already in the model. BRENDA's 'ki' table holds "
            f"inhibition constants."
        )
    if ki is not None and ki_parameter is not None:
        raise PerturbationRefused(
            "both ki and ki_parameter were given, and they may disagree. "
            "Pass one."
        )
    if ki_parameter is not None:
        ki = float(_require_parameter(network, ki_parameter).value)
    assert ki is not None  # narrowed by the checks above
    if ki <= 0.0:
        raise PerturbationRefused(
            f"a Ki of {ki:g} is not a dissociation constant. The apparent "
            f"Km would be infinite or negative."
        )

    factor = 1.0 + concentration / ki
    before = float(target.value)
    after = before * factor
    return Perturbation(
        kind="competitive_inhibitor",
        target=affinity_parameter,
        description=(
            f"competitive inhibitor at {concentration:g} with Ki {ki:g}: "
            f"apparent {affinity_parameter} raised {factor:.3g}-fold, kcat "
            f"untouched"
        ),
        network=_with_parameter(network, affinity_parameter, after),
        changes={affinity_parameter: (before, after)},
    )


def dead_mutant(model: Any, parameter: str) -> Perturbation:
    """`catalytically_dead`, with the unit recovered from the model.

    The entry point worth using. `scale.units_from_model` reads what the
    motifs declared, which is the only place the unit survives -- the
    builder drops it when it constructs the network.
    """
    try:
        from .scale import units_from_model
    except ImportError:  # pragma: no cover - flat import
        from scale import units_from_model  # type: ignore[no-redef]

    units = units_from_model(model)
    if parameter not in units:
        raise PerturbationRefused(
            f"no unit could be recovered for {parameter!r} from this model's "
            f"motifs. It declares: {', '.join(sorted(units)) or 'nothing'}."
        )
    return catalytically_dead(model.network, parameter, unit=units[parameter])


def set_level(network: Any, species: str, value: float) -> Perturbation:
    """Set a species to a stated amount -- a dose, a titration point."""
    if value < 0.0:
        raise PerturbationRefused(f"a concentration of {value:g} is negative")
    target = _require_species(network, species)
    before = float(target.initial)
    return Perturbation(
        kind="set_level",
        target=species,
        description=f"{species} set to {value:g}",
        network=_with_initial(network, species, value),
        changes={species: (before, value)},
    )


# ---------------------------------------------------------------------------
# Comparing a perturbation against its control
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Effect:
    """What one perturbation did to one readout."""

    perturbation: Perturbation
    readout: str
    control: Optional[float]
    perturbed: Optional[float]
    #: `None` when a fold change is undefined -- see `PerturbationComparison`.
    fold_change: Optional[float]
    note: str = ""

    def describe(self) -> str:
        if self.control is None or self.perturbed is None:
            return f"{self.perturbation.description}: {self.note}"
        if self.fold_change is None:
            return (
                f"{self.perturbation.description}: {self.readout} "
                f"{self.control:.4g} -> {self.perturbed:.4g} ({self.note})"
            )
        direction = "up" if self.fold_change > 1.0 else "down"
        return (
            f"{self.perturbation.description}: {self.readout} "
            f"{self.control:.4g} -> {self.perturbed:.4g}, "
            f"{self.fold_change:.3g}x {direction}"
        )


def _steady_value(network: Any, readout: str) -> float:
    try:
        from . import analysis
        from .sensitivity import STARTS_PER_SPECIES
    except ImportError:  # pragma: no cover - flat import
        import analysis  # type: ignore[no-redef]
        from sensitivity import STARTS_PER_SPECIES  # type: ignore[no-redef]

    report = analysis.analyse(network, starts_per_species=STARTS_PER_SPECIES)
    stable = report.stable_points
    if not stable:
        raise PerturbationRefused(
            f"no stable steady state, so {readout!r} has no steady value to "
            f"compare. Ask for a time course instead."
        )
    if len(stable) > 1:
        raise PerturbationRefused(
            f"{len(stable)} stable states, so {readout!r} has no single "
            f"steady value -- which one is reached depends on where the "
            f"system started, not on the perturbation. Ask for a time "
            f"course instead."
        )
    if readout not in stable[0].state:
        raise PerturbationRefused(
            f"no species {readout!r} in this model. It has: "
            f"{', '.join(sorted(stable[0].state))}."
        )
    return float(stable[0].state[readout])


def effect_on(perturbation: Perturbation, control_network: Any, readout: str) -> Effect:
    """The fold change in one readout, with the awkward cases named.

    A fold change is a ratio, and ratios have two failure modes that a
    number alone hides: a control at zero makes it infinite, and both at
    zero makes it undefined. Both are reported as `fold_change=None` with a
    note saying which, because "the perturbation raised it from nothing" and
    "nothing happened to nothing" are different results and neither is a
    number.
    """
    try:
        control = _steady_value(control_network, readout)
        perturbed = _steady_value(perturbation.network, readout)
    except PerturbationRefused as exc:
        return Effect(
            perturbation=perturbation, readout=readout,
            control=None, perturbed=None, fold_change=None, note=str(exc),
        )

    if abs(control) <= NEGLIGIBLE_CONTROL and abs(perturbed) <= NEGLIGIBLE_CONTROL:
        return Effect(
            perturbation, readout, control, perturbed, None,
            note="both control and perturbed are effectively zero, so there "
                 "is no ratio and no effect to report",
        )
    if abs(control) <= NEGLIGIBLE_CONTROL:
        return Effect(
            perturbation, readout, control, perturbed, None,
            note="the control is effectively zero, so the fold change is "
                 "unbounded. The absolute values are the result here",
        )
    return Effect(
        perturbation, readout, control, perturbed, perturbed / control,
    )


@dataclass(frozen=True)
class PerturbationComparison:
    """Several perturbations, one readout, ranked by how much they moved it."""

    readout: str
    effects: Tuple[Effect, ...]

    @property
    def ranked(self) -> Tuple[Effect, ...]:
        """By the magnitude of the LOG fold change.

        Log, because a two-fold increase and a two-fold decrease are equally
        large effects and ranking by the raw ratio would put every
        suppression below every induction. Effects with no fold change sort
        last -- they were not measured to be small.
        """
        def key(effect: Effect) -> Tuple[int, float]:
            if effect.fold_change is None or effect.fold_change <= 0.0:
                return (1, 0.0)
            return (0, -abs(math.log10(effect.fold_change)))

        return tuple(sorted(self.effects, key=key))

    def summary(self) -> str:
        lines = [f"Effect on {self.readout}, {len(self.effects)} perturbation(s):"]
        for effect in self.ranked:
            lines.append("  - " + effect.describe())
        lines.append(
            "Ranked by the magnitude of the log fold change, so a two-fold "
            "suppression ranks with a two-fold induction rather than below "
            "every induction. This says what the MODEL does at its current "
            "values; whether a real cell does it depends on constants that "
            "may still be placeholders."
        )
        return "\n".join(lines)


def compare(
    control_network: Any,
    perturbations: Sequence[Perturbation],
    readout: str,
) -> PerturbationComparison:
    """Run several perturbations against one control and rank their effects.

    The in-silico screen: given a model and a readout, which intervention
    moves it most. That is the question a genetics experiment is designed
    around, and having it in one call is the point of this module.
    """
    if not perturbations:
        raise PerturbationRefused(
            "no perturbations were given, so there is nothing to compare "
            "against the control"
        )
    return PerturbationComparison(
        readout=readout,
        effects=tuple(
            effect_on(p, control_network, readout) for p in perturbations
        ),
    )


def single_knockouts(network: Any, readout: str) -> PerturbationComparison:
    """Knock out every species that has any, one at a time.

    The systematic screen. Species already at zero are skipped rather than
    refused, because a screen that stopped at the first non-expressed gene
    would be useless -- but they are absent from the results rather than
    reported as having no effect, which are different findings.
    """
    candidates = [s.id for s in network.species if float(s.initial) != 0.0]
    if not candidates:
        raise PerturbationRefused(
            "every species in this model starts at zero, so there is nothing "
            "to knock out"
        )
    return compare(
        network, [knockout(network, name) for name in candidates], readout,
    )


__all__ = [
    "PerturbationRefused", "Perturbation", "Effect", "PerturbationComparison",
    "knockout", "knockdown", "overexpress", "catalytically_dead",
    "dead_mutant",
    "competitive_inhibitor", "set_level",
    "effect_on", "compare", "single_knockouts",
    "DEFAULT_OVEREXPRESSION_FOLD", "KNOCKOUT_LEVEL", "NEGLIGIBLE_CONTROL",
]
