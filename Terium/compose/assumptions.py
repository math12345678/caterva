"""The assumptions a composed model inherits, and where they fight.

THE PROBLEM COMPOSITION CREATES
--------------------------------
Every motif in the library carries a `basis`: the assumption that licenses its
rate law, and the condition under which it fails. `CATALYTIC_STEP` says
Michaelis-Menten under the quasi-steady-state approximation, valid while
[E]0 << [S]. `ZERO_ORDER_DEGRADATION` says the saturated limit, and that the
species reaches zero in finite time after which the law is wrong.

Each of those is true of the motif alone. Composition is where it stops being
enough, because the conditions are about the SYSTEM, and the system is now
several motifs deep.

Chain two catalytic steps and the first one's product is the second one's
substrate. The second step's QSSA needs [E]0 << [S] -- but S here is an
intermediate, and an intermediate's whole job is to stay small. The assumption
that was safe in isolation is the one most likely to fail in the chain, and
nothing in the package noticed, because each motif was asked about itself.

WHAT THIS DOES
--------------
Collects every motif instance's stated conditions, turns the ones that can be
checked into checks against the composed model's own numbers and structure,
and reports which hold, which fail, and -- the important category -- which
cannot be decided from what is available.

WHAT IT CANNOT DO, STATED UP FRONT
-----------------------------------
The `basis` strings are PROSE. They were written for a human reader and they
carry more than any parser can extract: "it fails for a tightly-binding enzyme
at low substrate" is a real and useful sentence that this module cannot turn
into an inequality.

So this does NOT parse the basis text. It carries a small set of
machine-checkable conditions, declared separately and attached to motifs by
name, and it reports the prose alongside rather than instead. A module that
claimed to have checked an assumption it had only pattern-matched would be
worse than one that checked nothing, because the reader would stop looking.

The honest summary is: a handful of conditions are checked arithmetically, the
rest are surfaced for a human, and the report says which is which every time.

WHY THE UNDECIDABLE CATEGORY IS NOT A FAILURE
----------------------------------------------
A QSSA check needs both [E]0 and a characteristic [S]. In a structure-only
model both are the library's illustrative values, so the check runs against
numbers nobody measured -- and reporting "the QSSA holds" from placeholder
values would be exactly the laundering this project exists to prevent.

Those come back UNDECIDED, with the reason, and the reason names what would
decide it. That is the same discipline `scale.py` applies to a parameter with
no recorded unit and `analysis.py` applies to a search that found nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple,
)

#: How much smaller the enzyme has to be than its substrate for the
#: quasi-steady-state approximation to be comfortable.
#:
#: A STATED JUDGEMENT with a real derivation behind it. The QSSA's error is
#: of order [E]0 / ([S] + Km) (Segel & Slemrod's analysis of the validity
#: condition), so a ratio of 1/100 buys about a percent. Ten would buy ten
#: percent, which is larger than most of the effects these models are built
#: to show; a thousand would refuse nearly every real enzyme assay, where
#: micromolar enzyme meets millimolar substrate.
QSSA_RATIO = 100.0

#: Below this fraction of its initial amount, a substrate has been consumed
#: rather than merely drawn down, and any approximation that assumed a
#: roughly constant substrate pool has stopped applying.
#:
#: A JUDGEMENT. At 10% remaining the free-substrate approximation is wrong
#: by an order of magnitude in the denominator of every saturable rate law
#: in the model.
DEPLETION_FRACTION = 0.1

#: Verdicts, ordered worst-first.
VIOLATED = "violated"
UNDECIDED = "undecided"
HELD = "held"
NOT_CHECKABLE = "not_checkable"

VERDICTS = (VIOLATED, UNDECIDED, HELD, NOT_CHECKABLE)


class AssumptionError(RuntimeError):
    """The assumption check could not be set up, as distinct from failing."""


@dataclass(frozen=True)
class Condition:
    """One machine-checkable validity condition, attached to a motif.

    Declared here rather than parsed out of the motif's prose. The prose
    says more than any parser could extract, and a module that claimed to
    have checked an assumption it had only pattern-matched would be worse
    than one that checked nothing -- the reader would stop looking.
    """

    #: The motif this belongs to, by `Motif.name`.
    motif: str
    name: str
    #: What must be true, in words a reader can check by hand.
    statement: str
    #: (instance, network) -> (verdict, detail). Takes the INSTANCE, not a
    #: prefix, because a chained port resolves to another instance's species
    #: and only the instance's bindings know that.
    check: Callable[[Any, Any], Tuple[str, str]]
    #: Why it matters -- what goes wrong when it fails.
    consequence: str = ""


@dataclass(frozen=True)
class Finding:
    """One condition, evaluated against one instance in one model."""

    instance: str
    motif: str
    condition: str
    verdict: str
    statement: str
    detail: str
    consequence: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise AssumptionError(
                f"verdict {self.verdict!r} is not one of {VERDICTS}. The "
                f"difference between 'fails', 'could not be decided' and "
                f"'was never checkable' is the whole content of this module."
            )

    def describe(self) -> str:
        text = f"[{self.verdict}] {self.instance} ({self.motif}): {self.statement}"
        if self.detail:
            text += f" -- {self.detail}"
        if self.verdict == VIOLATED and self.consequence:
            text += f". {self.consequence}"
        return text


@dataclass(frozen=True)
class AssumptionReport:
    findings: Tuple[Finding, ...]
    #: Motif instances with no machine-checkable condition at all, and their
    #: stated basis prose. Reported because a model whose every assumption is
    #: unparseable must not look like a model with no assumptions.
    prose_only: Mapping[str, str] = field(default_factory=dict)

    @property
    def violated(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.verdict == VIOLATED)

    @property
    def undecided(self) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.verdict == UNDECIDED)

    @property
    def sound(self) -> bool:
        """No checked condition failed.

        Deliberately NOT "every assumption holds": most assumptions here are
        prose that nothing checked, and a property claiming otherwise would
        be the overclaim this module is built to avoid.
        """
        return not self.violated

    def summary(self) -> str:
        lines: List[str] = []

        if self.violated:
            lines.append(
                f"{len(self.violated)} stated condition(s) FAIL in this "
                f"composition. The rate laws still integrate; they are "
                f"describing something other than what the motif claims:"
            )
            for finding in self.violated:
                lines.append("  - " + finding.describe())

        if self.undecided:
            lines.append(
                f"{len(self.undecided)} condition(s) could not be decided "
                f"from what this model carries. Reporting them as holding "
                f"would mean reading a conclusion off placeholder values:"
            )
            for finding in self.undecided:
                lines.append("  - " + finding.describe())

        held = [f for f in self.findings if f.verdict == HELD]
        if held:
            lines.append(
                f"{len(held)} condition(s) hold: "
                + ", ".join(f"{f.instance}.{f.condition}" for f in held)
                + "."
            )

        if self.prose_only:
            lines.append(
                f"{len(self.prose_only)} motif instance(s) state their "
                f"assumptions in prose that nothing here can check. They are "
                f"listed rather than omitted, because a model whose "
                f"assumptions are unparseable must not read as a model "
                f"without any:"
            )
            for instance, basis in sorted(self.prose_only.items()):
                lines.append(f"  - {instance}: {basis}")

        if not lines:
            lines.append("No stated condition was checkable for this model.")

        lines.append(
            "Checked arithmetically where a condition could be written as "
            "one; surfaced for a human reader otherwise. The basis strings "
            "carry more than any parser can extract, and this module does "
            "not pretend to have read them."
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# The checkable conditions
# ---------------------------------------------------------------------------


def _species_named(network: Any, instance: Any, port: str) -> Optional[Any]:
    """The species this instance's port actually resolves to.

    THROUGH THE INSTANCE'S BINDINGS, not by building `prefix_port`. Chaining
    binds one instance's substrate port to another's product species, so the
    constructed name does not exist -- and an earlier version returned
    NOT_CHECKABLE for every chained step, which is precisely the case this
    module was written for. The check quietly did not apply where it
    mattered most, and reported that as "nothing to check".
    """
    try:
        wanted = instance.species_for(port)
    except Exception:  # noqa: BLE001 - an unbound port is not an error here
        return None
    for species in network.species:
        if species.id == wanted:
            return species
    return None


def _parameter_named(network: Any, instance: Any, name: str) -> Optional[float]:
    wanted = instance.parameter_id(name)
    for parameter in network.parameters:
        if parameter.id == wanted:
            return float(parameter.value)
    return None


def _qssa(instance: Any, network: Any) -> Tuple[str, str]:
    """[E]0 << [S]: the condition Briggs and Haldane's derivation needs.

    Returns UNDECIDED rather than a verdict when the substrate starts at
    zero, which is the case for every intermediate in a chain -- and is
    exactly where the assumption is most likely to be in trouble. Saying so
    is the useful answer; computing a ratio against zero is not.
    """
    enzyme = _species_named(network, instance, "E")
    substrate = _species_named(network, instance, "S")
    if enzyme is None or substrate is None:
        return NOT_CHECKABLE, "this instance has no E and S pair to compare"

    e0 = float(enzyme.initial)
    s0 = float(substrate.initial)
    if e0 <= 0.0:
        return UNDECIDED, (
            f"{enzyme.id} starts at {e0:g}, so there is no enzyme "
            f"concentration to compare against"
        )
    if s0 <= 0.0:
        return UNDECIDED, (
            f"{substrate.id} starts at {s0:g} -- it is produced rather than "
            f"supplied, which is what an INTERMEDIATE in a chain looks like. "
            f"The QSSA needs a characteristic substrate concentration and "
            f"this model does not state one; simulate and compare "
            f"{enzyme.id} against the concentration {substrate.id} actually "
            f"reaches"
        )

    ratio = s0 / e0
    if ratio >= QSSA_RATIO:
        return HELD, f"{substrate.id}/{enzyme.id} = {ratio:.3g}, at least {QSSA_RATIO:g}"
    return VIOLATED, (
        f"{substrate.id}/{enzyme.id} = {ratio:.3g}, under the {QSSA_RATIO:g} "
        f"this condition asks for"
    )


def _substrate_not_exhausted(instance: Any, network: Any) -> Tuple[str, str]:
    """A saturable law assumes its substrate pool is not being emptied.

    Checked structurally rather than dynamically: if the substrate is
    consumed and nothing replenishes it, the pool empties in finite time
    whatever the constants are, and every saturable denominator in the model
    is wrong near the end of that.
    """
    substrate = _species_named(network, instance, "S")
    if substrate is None:
        return NOT_CHECKABLE, "this instance has no S port"

    produced = consumed = False
    for reaction in network.reactions:
        if substrate.id in reaction.products:
            produced = True
        if substrate.id in reaction.reactants:
            consumed = True

    if consumed and not produced:
        # UNDECIDED, NOT VIOLATED, AND THE DIFFERENCE MATTERS.
        #
        # A substrate that is consumed and never replenished is what a
        # CLOSED BATCH ASSAY is -- a tube with enzyme and substrate in it,
        # which is how most kinetics is measured. The saturable law is
        # perfectly good while substrate remains and wrong only near
        # exhaustion, so whether the assumption holds depends entirely on
        # the window being simulated.
        #
        # An earlier version returned VIOLATED here and the verdict page
        # duly called every batch reaction in the library BROKEN. That is
        # ADR 0028's failure exactly: a check that fires on the normal case
        # stops being read, and the one time it fires on something real
        # nobody looks.
        return UNDECIDED, (
            f"{substrate.id} is consumed and never replenished, which is "
            f"what a closed batch assay is. The saturable form is good "
            f"while substrate remains and wrong near exhaustion, so this "
            f"depends on the window: simulate and check whether "
            f"{substrate.id} is still well above its Km at the end"
        )
    if consumed and produced:
        return UNDECIDED, (
            f"{substrate.id} is both produced and consumed, so whether the "
            f"pool holds up depends on the rates -- simulate and look"
        )
    return HELD, f"{substrate.id} is not consumed by this instance"


def _finite_time_to_zero(instance: Any, network: Any) -> Tuple[str, str]:
    """Zero-order removal drives its species negative.

    Not a maybe. A constant removal rate applied to a finite pool reaches
    zero at t = X0/v_max and keeps going, and every integrator will happily
    follow it. The motif's own basis says a model using it needs a floor;
    this says whether this model has one.
    """
    target = _species_named(network, instance, "X")
    if target is None:
        return NOT_CHECKABLE, "this instance has no X port"

    replenished = any(
        target.id in reaction.products for reaction in network.reactions
    )
    rate = _parameter_named(network, instance, "v_max")
    if replenished:
        return UNDECIDED, (
            f"{target.id} is produced by another reaction, so whether it "
            f"survives depends on whether production keeps up with "
            f"{rate:g} per unit time -- simulate and look"
            if rate is not None else
            f"{target.id} is produced by another reaction; simulate and look"
        )
    if rate is None or rate <= 0.0:
        return UNDECIDED, "no positive removal rate is recorded"
    return VIOLATED, (
        f"{target.id} is removed at a constant {rate:g} and nothing "
        f"replenishes it, so it reaches zero at t = {target.initial:g}/"
        f"{rate:g} = {float(target.initial) / rate:.4g} and goes negative "
        f"after"
    )


#: Conditions, by motif name. Declared rather than parsed -- see the module
#: docstring on why the prose is left to a human.
CONDITIONS: Tuple[Condition, ...] = (
    Condition(
        motif="catalytic_step",
        name="qssa_enzyme_excess",
        statement="[E]0 << [S], which Briggs-Haldane's derivation requires",
        check=_qssa,
        consequence=(
            "Outside it the enzyme-substrate complex is not a small, fast "
            "pool and the Michaelis-Menten form overestimates the rate"
        ),
    ),
    Condition(
        motif="catalytic_step",
        name="substrate_pool_holds",
        statement="the substrate pool is not emptied within the window simulated",
        check=_substrate_not_exhausted,
        consequence=(
            "Every saturable denominator in this model is wrong as the pool "
            "runs out, and the error is largest exactly where the "
            "interesting dynamics are"
        ),
    ),
    Condition(
        motif="zero_order_degradation",
        name="needs_a_floor",
        statement="the species does not reach zero within the simulated window",
        check=_finite_time_to_zero,
        consequence=(
            "The integrator will drive it negative and keep going, and a "
            "negative concentration propagates into every rate law that "
            "reads it"
        ),
    ),
)


def _conditions_for(motif_name: str) -> Tuple[Condition, ...]:
    return tuple(c for c in CONDITIONS if c.motif == motif_name)


def check(model: Any) -> AssumptionReport:
    """Every instance's stated conditions, against this composed model.

    Reads the composition's instances rather than the network, because the
    conditions belong to MOTIFS and the network has forgotten which motif
    produced which reaction -- the same information loss `scale.py` works
    around for units.
    """
    composition = getattr(
        getattr(model, "recognition", None), "composition", None
    )
    instances = list(getattr(composition, "instances", ()))
    if not instances:
        raise AssumptionError(
            "this model carries no motif instances, so there are no stated "
            "conditions to check. A network built outside the composer has "
            "no basis strings attached to it."
        )

    network = model.network
    findings: List[Finding] = []
    prose_only: Dict[str, str] = {}

    for instance in instances:
        motif = instance.motif
        conditions = _conditions_for(motif.name)
        if not conditions:
            prose_only[instance.prefix] = (motif.basis or "").strip()
            continue
        for condition in conditions:
            verdict, detail = condition.check(instance, network)
            findings.append(Finding(
                instance=instance.prefix,
                motif=motif.name,
                condition=condition.name,
                verdict=verdict,
                statement=condition.statement,
                detail=detail,
                consequence=condition.consequence,
            ))

    return AssumptionReport(findings=tuple(findings), prose_only=prose_only)


__all__ = [
    "VIOLATED", "UNDECIDED", "HELD", "NOT_CHECKABLE", "VERDICTS",
    "QSSA_RATIO", "DEPLETION_FRACTION",
    "AssumptionError", "AssumptionReport", "Condition", "Finding",
    "CONDITIONS", "check",
]
