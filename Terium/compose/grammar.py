"""English to a composition, deterministically and without a language model.

WHY DETERMINISTIC
-----------------
The compositional path exists because the catalogue cannot answer "three
step phosphorylation cascade" and never will. The obvious way to close that
is to ask a language model for the structure -- and Terrium already has that
path, in `networkResolver.ts`. It returns null without an API key, which is
the state of this checkout and of any deployment nobody has configured, so
the capability is unavailable exactly when a lab tries the tool for the
first time.

The motifs a teaching lab asks about are not a long tail. A cascade, a
toggle switch, competition for a substrate, an open system with inflow,
feedback inhibition -- these have canonical structures that have not changed
since the 1970s, and recognising them is pattern matching, not inference.
So this recognises what it can recognise, deterministically, and REFUSES
what it cannot rather than guessing. A model resolver reached through this
path gives the same answer on Tuesday as on Monday, offline, with no key.

WHAT IT REFUSES, AND WHY THAT IS THE INTERESTING PART
-----------------------------------------------------
"Glycolysis in yeast" is not matched. It is a named pathway with ten enzymes
and a specific stoichiometry, and a grammar that produced *something* for it
would produce a plausible wrong pathway -- the failure mode that is worse
than a refusal, and the reason `UnrecognizedQueryError` exists at all. Named
pathways need a pathway database (KEGG, Reactome), which is a different
capability and is named as such in the refusal.

The rule is: recognise a SHAPE, never a SUBJECT. "Cascade" is a shape.
"Glycolysis" is a subject.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

try:
    from .builder import Composition, CompositionError, chain, compete, couple
    from .library import (
        AUTOCATALYSIS, CATALYTIC_STEP, COMPETITIVE_INHIBITION,
        CONSTANT_INFLOW, COOPERATIVE_BINDING, COOPERATIVE_CATALYSIS,
        DIMERISATION, FACILITATED_TRANSPORT, FIRST_ORDER_OUTFLOW,
        HILL_ACTIVATION, HILL_REPRESSION, MASS_ACTION_CONVERSION,
        MIXED_INHIBITION, NONCOMPETITIVE_INHIBITION, ORDERED_BI_BI,
        PHOSPHORYLATION_CYCLE, PING_PONG_BI_BI, PRODUCT_INHIBITION,
        REVERSIBLE_BINDING, REVERSIBLE_CATALYSIS, SATURABLE_DEGRADATION,
        SUBSTRATE_INHIBITION, SYNTHESIS_DEGRADATION,
        UNCOMPETITIVE_INHIBITION, ZERO_ORDER_DEGRADATION,
    )
except ImportError:  # pragma: no cover - flat import
    from builder import Composition, CompositionError, chain, compete, couple  # type: ignore[no-redef]
    from library import (  # type: ignore[no-redef]
        AUTOCATALYSIS, CATALYTIC_STEP, COMPETITIVE_INHIBITION,
        CONSTANT_INFLOW, COOPERATIVE_BINDING, COOPERATIVE_CATALYSIS,
        DIMERISATION, FACILITATED_TRANSPORT, FIRST_ORDER_OUTFLOW,
        HILL_ACTIVATION, HILL_REPRESSION, MASS_ACTION_CONVERSION,
        MIXED_INHIBITION, NONCOMPETITIVE_INHIBITION, ORDERED_BI_BI,
        PHOSPHORYLATION_CYCLE, PING_PONG_BI_BI, PRODUCT_INHIBITION,
        REVERSIBLE_BINDING, REVERSIBLE_CATALYSIS, SATURABLE_DEGRADATION,
        SUBSTRATE_INHIBITION, SYNTHESIS_DEGRADATION,
        UNCOMPETITIVE_INHIBITION, ZERO_ORDER_DEGRADATION,
    )

#: Written numbers a query might use for a stage count. Deliberately small:
#: past about six the phrase is almost always figurative ("a hundred steps"),
#: and a model with a hundred unresolvable rate constants is not a model
#: anybody wanted.
NUMBER_WORDS: Dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "single": 1, "double": 2, "triple": 3,
}
#: "a" and "an" are DELIBERATELY absent. They were here, and "a
#: phosphorylation cascade" parsed as a one-tier cascade -- an indefinite
#: article read as a count, producing a model that is not a cascade at all
#: while looking like a successful match. Caught by
#: `test_a_cascade_with_no_number_is_refused`. "single" survives because it
#: is only ever a count.

#: Shapes for which one copy is not the shape. A one-tier cascade is a
#: phosphorylation cycle; a one-member competition is a reaction. Building
#: them under the name asked for would answer a different question.
MINIMUM_COPIES: Dict[str, int] = {
    "cascade": 2,
    "competition": 2,
}

#: The most stages this will build without being told a number explicitly.
#: A cascade whose length was inferred rather than stated should not run
#: away; a query that means more can say so.
MAX_INFERRED_STAGES = 10

#: Subjects that name a specific biological pathway rather than a shape.
#: Matching one is a REFUSAL with a reason, not a failure to understand --
#: the difference matters, because "I do not know that word" and "that needs
#: a pathway database I do not have" send a user to different places.
NAMED_PATHWAYS = (
    "glycolysis", "gluconeogenesis", "krebs", "tca cycle",
    "citric acid cycle", "pentose phosphate", "urea cycle",
    "beta oxidation", "calvin cycle", "electron transport",
    "oxidative phosphorylation", "fatty acid synthesis",
    "purine biosynthesis", "pyrimidine biosynthesis",
)


class UnrecognisedShape(ValueError):
    """The query does not describe a shape this grammar can build."""

    def __init__(self, query: str, reason: str, suggestions: Sequence[str] = ()):
        self.query = query
        self.reason = reason
        self.suggestions = tuple(suggestions)
        message = reason
        if suggestions:
            message += " Shapes this can build: " + ", ".join(suggestions) + "."
        super().__init__(message)


@dataclass(frozen=True)
class Recognition:
    """What the grammar made of a query."""

    composition: Composition
    #: The rule that fired, for the report. A model whose shape nobody can
    #: explain is not better than no model.
    rule: str
    #: What the rule read out of the query -- the stage count, say.
    reading: str

    def network(self):
        return self.composition.to_network()


def _count_before(text: str, *keywords: str) -> Optional[int]:
    """A number appearing shortly before any of `keywords`.

    Matches "three step cascade", "3-step cascade", "cascade of four steps".
    Returns None when no number is stated, which the caller must handle --
    inventing a stage count would invent the model.
    """
    for keyword in keywords:
        pattern = re.compile(
            r"(?P<n>\d+|" + "|".join(NUMBER_WORDS) + r")"
            r"[\s\-]*(?:step|stage|tier|level)?s?[\s\-]*" + re.escape(keyword),
            re.IGNORECASE,
        )
        found = pattern.search(text)
        if found:
            return _as_int(found.group("n"))
        trailing = re.compile(
            re.escape(keyword) + r"\s+of\s+(?P<n>\d+|" +
            "|".join(NUMBER_WORDS) + r")",
            re.IGNORECASE,
        )
        found = trailing.search(text)
        if found:
            return _as_int(found.group("n"))
    return None


def _as_int(token: str) -> Optional[int]:
    token = token.strip().lower()
    if token.isdigit():
        value = int(token)
        return value if 1 <= value <= MAX_INFERRED_STAGES else None
    return NUMBER_WORDS.get(token)


def _has(text: str, *words: str) -> bool:
    return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


def _phosphorylation_cascade(query: str, name: str) -> Recognition:
    count = _count_before(query, "cascade", "phosphorylation")
    if count is None:
        # MAP kinase cascades are three-tiered by definition (Raf/MEK/ERK,
        # and the same architecture in yeast and Drosophila), so the number
        # IS stated -- by the name. Anything else has to say.
        if _has(query, "mapk", "map kinase", "mitogen"):
            count = 3
            reading = "MAP kinase cascade: three tiers by definition"
        else:
            raise UnrecognisedShape(
                query,
                "A cascade needs a number of stages. 'Three step "
                "phosphorylation cascade' builds; 'phosphorylation cascade' "
                "does not, because the number of tiers changes the model and "
                "Terrium will not pick one for you.",
            )
    else:
        reading = f"{count} tiers, read from the query"

    if count < MINIMUM_COPIES["cascade"]:
        raise UnrecognisedShape(
            query,
            f"A cascade of {count} is a single phosphorylation cycle, not a "
            f"cascade. Ask for that if it is what you want; a cascade needs "
            f"at least {MINIMUM_COPIES['cascade']} tiers to be one.",
        )

    composition = Composition(name)
    tiers = chain(
        composition, PHOSPHORYLATION_CYCLE, count,
        prefix="tier", upstream_port="Xp", downstream_port="kinase",
        shared=("phosphatase",),
    )
    for tier in tiers:
        composition.set_initial(tier.species_for("X"), 1.0)
    composition.note(
        "each tier's phosphorylated form is the kinase for the tier below, "
        "which is what makes this a cascade rather than a chain of "
        "conversions"
    )

    if _has(query, "negative feedback", "feedback inhibition", "feedback"):
        # The last tier's active form inhibiting the first is the canonical
        # negative feedback in MAPK signalling (ERK on Raf/SOS). Modelled as
        # competitive inhibition of the top tier rather than by editing its
        # rate law, so the mechanism stays visible in the stoichiometry.
        composition.note(
            "negative feedback requested: the bottom tier's active form was "
            "NOT wired back, because the mechanism is specific -- ERK acts on "
            "SOS and on Raf by different routes -- and guessing which would "
            "be inventing biology. State the target and it can be added."
        )

    return Recognition(composition, "phosphorylation_cascade", reading)


def _enzyme_cascade(query: str, name: str) -> Recognition:
    count = _count_before(query, "cascade", "cascade") or 0
    if not count:
        raise UnrecognisedShape(
            query,
            "An enzyme cascade needs a number of steps; the length changes "
            "the model.",
        )
    if count < MINIMUM_COPIES["cascade"]:
        raise UnrecognisedShape(
            query,
            f"A cascade of {count} is a single catalytic step. Ask for that "
            f"directly if it is what you meant.",
        )
    composition = Composition(name)
    steps = chain(
        composition, CATALYTIC_STEP, count,
        prefix="step", upstream_port="P", downstream_port="S",
        head_initial=1.0,
    )
    composition.note(
        "each step's product is the next step's substrate; each step has its "
        "own enzyme"
    )
    return Recognition(composition, "enzyme_cascade", f"{count} steps")


def _competition(query: str, name: str) -> Recognition:
    count = _count_before(query, "enzymes", "enzyme") or 2
    composition = Composition(name)
    compete(
        composition, CATALYTIC_STEP, max(count, 2),
        prefix="enzyme", shared_port="S", shared_initial=1.0,
    )
    composition.note(
        "the competition is the shared substrate pool, not a term in a rate "
        "law: each enzyme draws on the same species and the outcome falls "
        "out of the stoichiometry"
    )
    return Recognition(composition, "enzyme_competition", f"{max(count, 2)} enzymes")


def _toggle_switch(query: str, name: str) -> Recognition:
    composition = Composition(name)
    first = composition.add(HILL_REPRESSION, "geneA")
    second = composition.add(HILL_REPRESSION, "geneB")
    # Mutual repression: each gene's product is the other's repressor.
    couple(composition, first, "X", second, "R")
    couple(composition, second, "X", first, "R")
    composition.set_initial(first.species_for("X"), 1.0)
    composition.set_initial(second.species_for("X"), 0.1)
    composition.note(
        "two genes each repressing the other (Gardner, Cantor & Collins "
        "2000). Bistability needs cooperative repression -- with Hill "
        "coefficient n = 1 this settles to a single mixed state instead of "
        "switching, which is why n is a declared parameter and not a 1"
    )
    composition.note(
        "the two initial amounts are deliberately unequal: from a perfectly "
        "symmetric start the system sits on the unstable separatrix and "
        "neither gene wins, which is a real property of the model and a "
        "confusing first plot"
    )
    return Recognition(composition, "toggle_switch", "two mutually repressing genes")


def _repressilator(query: str, name: str) -> Recognition:
    composition = Composition(name)
    genes = [composition.add(HILL_REPRESSION, f"gene{i + 1}") for i in range(3)]
    for index, gene in enumerate(genes):
        upstream = genes[index - 1]
        couple(composition, upstream, "X", gene, "R")
    for index, gene in enumerate(genes):
        composition.set_initial(gene.species_for("X"), 1.0 if index == 0 else 0.0)
    composition.note(
        "three genes repressing each other in a ring (Elowitz & Leibler "
        "2000). An odd number is required: an even ring settles into a "
        "stable pattern instead of oscillating"
    )
    return Recognition(composition, "repressilator", "three-gene ring")


def _open_system(query: str, name: str) -> Recognition:
    composition = Composition(name)
    inflow = composition.add(CONSTANT_INFLOW, "feed")
    step = composition.add(
        CATALYTIC_STEP, "reaction", {"S": inflow.species_for("S")},
    )
    if _has(query, "washout", "outflow", "chemostat", "dilution"):
        composition.add(
            FIRST_ORDER_OUTFLOW, "drain", {"S": step.species_for("P")},
        )
        composition.note("product removed by first-order washout")
    composition.note(
        "constant inflow makes this an open system: there is no conservation "
        "law over the fed species, and the steady state it reaches is not an "
        "equilibrium"
    )
    return Recognition(composition, "open_system", "inflow feeding a catalytic step")


def _binding(query: str, name: str) -> Recognition:
    composition = Composition(name)
    if _has(query, "dimer", "dimerise", "dimerize", "homodimer", "itself"):
        composition.add(DIMERISATION, "complex")
        composition.note("a molecule binding a copy of itself, so 2 M -> D")
        return Recognition(composition, "dimerisation", "homodimerisation")
    composition.add(REVERSIBLE_BINDING, "complex")
    composition.note(
        "association and dissociation as mass action in both directions. Kd "
        "is koff/kon, so a published Kd constrains the pair but neither rate "
        "alone"
    )
    return Recognition(composition, "reversible_binding", "two partners and a complex")


def _inhibition(query: str, name: str) -> Recognition:
    composition = Composition(name)
    if _has(query, "substrate inhibition") or (
        _has(query, "substrate") and _has(query, "high")
    ):
        composition.add(SUBSTRATE_INHIBITION, "reaction")
        composition.note(
            "a second substrate molecule binding the ES complex "
            "non-productively; the rate curve rises to a maximum and falls"
        )
        return Recognition(composition, "substrate_inhibition", "substrate inhibition")
    if _has(query, "uncompetitive"):
        composition.add(UNCOMPETITIVE_INHIBITION, "reaction")
        composition.note("inhibitor binds the ES complex, not free enzyme")
        return Recognition(
            composition, "uncompetitive_inhibition", "uncompetitive inhibition"
        )
    if _has(query, "noncompetitive", "non-competitive"):
        composition.add(NONCOMPETITIVE_INHIBITION, "reaction")
        composition.note(
            "inhibitor binds free enzyme and ES complex equally: apparent "
            "Vmax falls, apparent Km is untouched, and more substrate cannot "
            "rescue the rate"
        )
        return Recognition(
            composition, "noncompetitive_inhibition", "non-competitive inhibition"
        )
    if _has(query, "mixed"):
        composition.add(MIXED_INHIBITION, "reaction")
        composition.note(
            "two dissociation constants, because there are two binding "
            "events. Competitive, uncompetitive and non-competitive are its "
            "limits, and reporting one constant would hide which limit the "
            "data supports"
        )
        return Recognition(composition, "mixed_inhibition", "mixed inhibition")
    if _has(query, "product inhibition", "inhibited by its product",
            "end product inhibition"):
        composition.add(PRODUCT_INHIBITION, "reaction")
        composition.note(
            "the product competes with the substrate for free enzyme, "
            "raising apparent Km exactly as a competitive inhibitor does"
        )
        return Recognition(
            composition, "product_inhibition", "product inhibition"
        )
    composition.add(COMPETITIVE_INHIBITION, "reaction")
    composition.note(
        "inhibitor competing for the active site: apparent Km rises by "
        "(1 + I/Ki), kcat is untouched"
    )
    return Recognition(composition, "competitive_inhibition", "competitive inhibition")


def _allosteric(query: str, name: str) -> Recognition:
    composition = Composition(name)
    if _has(query, "activation", "activator", "activate"):
        composition.add(HILL_ACTIVATION, "regulated")
        composition.note(
            "cooperative activation of synthesis, as a Hill function. "
            "Modelled on the SYNTHESIS of the regulated species rather than "
            "on a catalytic rate, because that is what a Hill term describes"
        )
        return Recognition(composition, "allosteric_activation", "Hill activation")
    composition.add(HILL_REPRESSION, "regulated")
    composition.note("cooperative repression of synthesis, as a Hill function")
    return Recognition(composition, "allosteric_repression", "Hill repression")


def _feedback_inhibition(query: str, name: str) -> Recognition:
    count = _count_before(query, "step", "steps", "reactions") or 3
    composition = Composition(name)
    steps = chain(
        composition, CATALYTIC_STEP, count,
        prefix="step", upstream_port="P", downstream_port="S",
        head_initial=1.0,
    )
    composition.note(
        f"{count} catalytic steps in sequence. The end product inhibiting "
        f"the first committed step is the canonical pattern (Umbarger 1956, "
        f"threonine deaminase), but the INHIBITION ITSELF was not wired: "
        f"that needs the first step to be competitive rather than plain, and "
        f"which step is 'committed' is a fact about the pathway rather than "
        f"about the words. Say which step to inhibit and it can be added."
    )
    return Recognition(
        composition, "sequential_pathway", f"{count} steps, feedback noted not wired"
    )


def _synthesis(query: str, name: str) -> Recognition:
    composition = Composition(name)
    composition.add(SYNTHESIS_DEGRADATION, "species")
    composition.note(
        "constitutive synthesis with first-order turnover. Steady state is "
        "ks/kd; the degradation constant sets how fast it gets there"
    )
    return Recognition(composition, "synthesis_degradation", "one species, made and removed")


def _simple_conversion(query: str, name: str) -> Recognition:
    composition = Composition(name)
    composition.add(MASS_ACTION_CONVERSION, "reaction")
    composition.note("a first-order conversion with no catalyst claimed")
    return Recognition(composition, "mass_action_conversion", "A -> B, first order")




def _bi_substrate(query: str, name: str) -> Recognition:
    """Ordered or ping-pong -- and the query has to say which.

    They are distinguishable from steady-state kinetics alone: the ordered
    mechanism's double-reciprocal lines intersect, the ping-pong's are
    parallel. Choosing between them by default would fit data with the wrong
    mechanism, so an unqualified "two substrate" query is refused with the
    distinction spelled out.
    """
    composition = Composition(name)
    if _has(query, "ping pong", "ping-pong", "pingpong", "transaminase",
            "double displacement"):
        composition.add(PING_PONG_BI_BI, "reaction")
        composition.note(
            "no ternary complex: the enzyme is modified by the first "
            "substrate and releases the first product before the second "
            "binds. Parallel lines on a double-reciprocal plot"
        )
        return Recognition(composition, "ping_pong_bi_bi", "ping-pong mechanism")
    if _has(query, "ordered", "sequential", "ternary", "dehydrogenase"):
        composition.add(ORDERED_BI_BI, "reaction")
        composition.note(
            "ordered sequential: A binds, then B, and catalysis happens on "
            "the ternary complex. Intersecting lines on a double-reciprocal "
            "plot"
        )
        return Recognition(composition, "ordered_bi_bi", "ordered mechanism")
    raise UnrecognisedShape(
        query,
        "A two-substrate enzyme follows either an ORDERED sequential "
        "mechanism or a PING-PONG one, and they are different models with "
        "different rate laws -- distinguishable from steady-state kinetics, "
        "which is how generations of biochemists have told them apart. Say "
        "which, and this builds it.",
    )


def _transport(query: str, name: str) -> Recognition:
    composition = Composition(name)
    composition.add(FACILITATED_TRANSPORT, "carrier")
    composition.note(
        "a transporter is an enzyme whose product is the same molecule "
        "somewhere else, so it saturates the same way. Modelled as two "
        "species, inside and outside, which makes the gradient a state of "
        "the model rather than a parameter of it"
    )
    return Recognition(composition, "facilitated_transport", "carrier-mediated transport")


def _autocatalysis(query: str, name: str) -> Recognition:
    composition = Composition(name)
    composition.add(AUTOCATALYSIS, "reaction")
    composition.note(
        "S + X -> 2X: the product catalyses its own formation. The "
        "stoichiometric 2 is load-bearing -- it is what makes the "
        "conservation law S + X. A seed of X is required; from exactly zero "
        "nothing ever happens, which is a real property and a confusing "
        "first plot"
    )
    return Recognition(composition, "autocatalysis", "self-amplifying conversion")


def _reversible_step(query: str, name: str) -> Recognition:
    composition = Composition(name)
    composition.add(REVERSIBLE_CATALYSIS, "reaction")
    composition.note(
        "the reversible Michaelis-Menten form. Every enzymatic reaction is "
        "reversible; the irreversible form is the approximation that holds "
        "while product is scarce, and it stops holding exactly when a "
        "pathway approaches equilibrium. The Haldane relationship ties the "
        "four constants to the equilibrium constant, so a set resolved "
        "independently should be checked against it"
    )
    return Recognition(composition, "reversible_catalysis", "a step that runs both ways")


def _cooperative_enzyme(query: str, name: str) -> Recognition:
    composition = Composition(name)
    if _has(query, "receptor", "ligand", "haemoglobin", "hemoglobin", "occupancy"):
        composition.add(COOPERATIVE_BINDING, "site")
        composition.note(
            "the Hill equation as Hill wrote it in 1910, for haemoglobin. h "
            "is NOT the number of sites -- it cannot exceed it, and for "
            "haemoglobin's four sites it is about 2.8. Reporting h as a site "
            "count is a common and specific error"
        )
        return Recognition(composition, "cooperative_binding", "cooperative ligand binding")
    composition.add(COOPERATIVE_CATALYSIS, "reaction")
    composition.note(
        "the Hill form applied to catalysis: substrate binding at one site "
        "raises the affinity of the others, giving the sigmoid that makes "
        "an enzyme behave like a threshold detector. Phosphofructokinase is "
        "the canonical case"
    )
    return Recognition(composition, "cooperative_catalysis", "sigmoidal enzyme kinetics")


def _turnover(query: str, name: str) -> Recognition:
    composition = Composition(name)
    if _has(query, "saturable", "saturating", "swamped", "protease",
            "proteasome", "saturated"):
        composition.add(SATURABLE_DEGRADATION, "removal")
        composition.note(
            "removal by machinery that can be swamped. First-order "
            "degradation assumes the protease is never saturated, and the "
            "failure matters: a system whose removal saturates can "
            "accumulate without bound while the first-order model says it "
            "reaches a steady state"
        )
        return Recognition(composition, "saturable_degradation", "Michaelis-Menten removal")
    if _has(query, "constant rate", "zero order", "zero-order"):
        composition.add(ZERO_ORDER_DEGRADATION, "removal")
        composition.note(
            "removal at a constant rate. Reaches zero in FINITE time, after "
            "which the rate law would drive the species negative -- a model "
            "using it needs a floor"
        )
        return Recognition(composition, "zero_order_degradation", "constant-rate removal")
    composition.add(SYNTHESIS_DEGRADATION, "species")
    composition.note(
        "constitutive synthesis with first-order turnover. Steady state is "
        "ks/kd; the degradation constant sets how fast it gets there"
    )
    return Recognition(composition, "synthesis_degradation", "one species, made and removed")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    name: str
    #: Words that must ALL appear for this rule to be considered.
    requires: Tuple[str, ...]
    #: Any one of these is enough, when `requires` is empty.
    triggers: Tuple[str, ...]
    build: Callable[[str, str], Recognition]
    describes: str
    #: Higher wins when several rules match. Set explicitly rather than by
    #: list order, so adding a rule cannot silently re-rank the others --
    #: the defect ADR 0170 describes in the domain matcher.
    priority: int = 0


RULES: Tuple[Rule, ...] = (
    Rule("phosphorylation_cascade", (), ("phosphorylation cascade", "kinase cascade",
                                         "mapk", "map kinase", "phosphorelay"),
         _phosphorylation_cascade,
         "N phosphorylation cycles, each tier activating the next", 90),
    Rule("repressilator", (), ("repressilator",), _repressilator,
         "three genes repressing each other in a ring", 88),
    Rule("toggle_switch", (), ("toggle switch", "bistable switch",
                               "mutual repression"), _toggle_switch,
         "two genes each repressing the other", 86),
    # `requires` is the full word, not the prefix "compet".
    #
    # It WAS the prefix, and "competitive inhibition of an enzyme by a
    # substrate analogue" therefore built an enzyme-COMPETITION model: the
    # prefix matched "competitive", the trigger matched "substrate", and
    # priority 84 beat the inhibition rule's 70. A completely wrong model,
    # silently, from a query that names its mechanism exactly. Found by
    # writing the test that proves priority decides between two matching
    # rules -- the ordering was right and the matching was not.
    Rule("competition", ("competing",), ("substrate", "enzyme"), _competition,
         "several enzymes drawing on one substrate pool", 84),
    Rule("competition_noun", ("competition",), ("substrate", "enzyme"),
         _competition, "several enzymes drawing on one substrate pool", 83),
    Rule("feedback_inhibition", (), ("feedback inhibition", "end product inhibition",
                                     "sequential feedback"), _feedback_inhibition,
         "a linear pathway, with the feedback point named not guessed", 82),
    Rule("enzyme_cascade", (), ("enzyme cascade", "catalytic cascade",
                                "reaction cascade"), _enzyme_cascade,
         "N catalytic steps, product to substrate", 80),
    Rule("open_system", (), ("constant inflow", "constant supply", "chemostat",
                             "open system", "continuous feed", "substrate inflow"),
         _open_system, "a fed reactor with no conservation over the fed species", 78),
    Rule("bi_substrate", (), ("two substrate", "two-substrate", "bi-bi", "bi bi",
                              "ping pong", "ping-pong", "ordered sequential"),
         _bi_substrate, "an enzyme with two substrates, ordered or ping-pong", 77),
    Rule("transport", (), ("transport", "transporter", "carrier", "uptake",
                           "across the membrane", "facilitated diffusion"),
         _transport, "a saturable carrier moving a solute across a boundary", 76),
    Rule("autocatalysis", (), ("autocataly", "self-amplif", "self amplif",
                               "catalyses its own", "catalyzes its own", "prion"),
         _autocatalysis, "a product that catalyses its own formation", 75),
    Rule("reversible_step", (), ("reversible reaction", "runs both ways",
                                 "reversible enzymatic", "reversible michaelis",
                                 "near equilibrium"),
         _reversible_step, "an enzymatic step that runs in both directions", 74),
    Rule("turnover", (), ("saturable degradation", "zero order degradation",
                          "zero-order degradation", "synthesis and degradation",
                          "constitutive expression", "made and degraded",
                          "turnover of"),
         _turnover, "a species made and removed, first-order or saturable", 72),
    Rule("inhibition", (), ("competitive inhibit", "uncompetitive inhibit",
                            "noncompetitive inhibit", "non-competitive inhibit",
                            "mixed inhibition", "product inhibition",
                            "substrate inhibition", "inhibitor",
                            "inhibited by"),
         _inhibition, "Michaelis-Menten with an inhibitor", 70),
    Rule("cooperative_enzyme", (), ("cooperative binding", "cooperative enzyme",
                                    "sigmoidal", "positive cooperativity",
                                    "haemoglobin", "hemoglobin",
                                    "phosphofructokinase"),
         _cooperative_enzyme, "sigmoidal kinetics or cooperative ligand binding", 69),
    Rule("allosteric", (), ("allosteric", "cooperative", "hill"),
         _allosteric, "cooperative regulation as a Hill function", 68),
    Rule("binding", (), ("reversible binding", "binds to", "binding of",
                         "association", "ligand", "receptor", "dimeris",
                         "dimeriz"), _binding,
         "two partners forming a complex", 60),
    Rule("synthesis", (), ("expressed and removed", "made at a constant rate"),
         _synthesis, "one species, made and removed", 50),
    Rule("conversion", (), ("first order conversion", "converts to",
                            "uncatalysed"), _simple_conversion,
         "A -> B with no catalyst", 40),
)


def _named_pathway_in(query: str) -> Optional[str]:
    lowered = query.lower()
    for pathway in NAMED_PATHWAYS:
        if pathway in lowered:
            return pathway
    return None


def recognise(query: str, *, name: Optional[str] = None) -> Recognition:
    """Turn a query into a composition, or refuse and say why.

    Refusal is a first-class outcome and carries a different message for the
    two different reasons. A named pathway needs a pathway database; an
    unrecognised shape needs different words. Collapsing them would send a
    user asking about glycolysis away to rephrase, forever.
    """
    lowered = query.lower().strip()
    if not lowered:
        raise UnrecognisedShape(query, "An empty query describes nothing.")

    pathway = _named_pathway_in(lowered)
    if pathway is not None:
        raise UnrecognisedShape(
            query,
            f"{pathway!r} is a named pathway, not a shape. Building it means "
            f"its actual enzymes and stoichiometry, which needs a pathway "
            f"database (KEGG or Reactome) that Terrium does not yet read. "
            f"Guessing a plausible pathway would be worse than saying so. "
            f"You can describe the steps you want, or supply SBML.",
        )

    candidates = [
        rule for rule in RULES
        if (
            all(word in lowered for word in rule.requires)
            and (not rule.triggers or any(t in lowered for t in rule.triggers))
        )
    ]
    if not candidates:
        raise UnrecognisedShape(
            query,
            "No shape in this grammar matches. It recognises mechanisms, not "
            "subjects: 'three step phosphorylation cascade' builds, "
            "'signalling in a cell' does not.",
            suggestions=sorted({rule.describes for rule in RULES}),
        )

    best = max(candidates, key=lambda rule: rule.priority)
    model_name = name or re.sub(r"[^a-z0-9]+", "_", lowered)[:48].strip("_")
    return best.build(lowered, model_name or "composed_model")


def shapes() -> Tuple[str, ...]:
    """Everything this grammar can build, for a refusal to list."""
    return tuple(sorted(f"{rule.name}: {rule.describes}" for rule in RULES))


__all__ = [
    "recognise", "shapes", "Recognition", "UnrecognisedShape", "Rule", "RULES",
    "NAMED_PATHWAYS", "MAX_INFERRED_STAGES",
]
