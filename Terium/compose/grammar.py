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

THE EXPANSION LIBRARIES ARE IMPORTED LATE, ON PURPOSE
-----------------------------------------------------
`library.py` is the core and is always here. Three further libraries --
`library_expression`, `library_enzymology`, `library_transport` -- carry the
motifs for gene expression, the harder enzyme mechanisms, and membrane
transport. They are written independently of this file and any of them can
be absent from a checkout.

So every reference to them is a lazy import inside the rule that needs it.
A module-scope import would take the entire grammar down when one file is
missing -- including the twenty rules that need nothing from it -- and
"cannot import grammar" is not a sentence anybody should have to read
because a transporter library was not written yet. A missing library gives
a `MissingMotifLibrary` naming the file, the motif, and what CAN be built
instead; the shape stays recognised either way, which is the difference
between a capability that is absent and one that was never reachable.

A KEYWORD THAT SWALLOWS ANOTHER RULE'S QUERIES
----------------------------------------------
This is the defect class this file has produced twice, and it is silent
both times. `requires=("compet",)` on the competition rule made
"competitive inhibition of an enzyme by a substrate analogue" build two
enzymes sharing a substrate pool: a prefix matched a word it was not about,
competition outranked inhibition, and a query naming its own mechanism got
a completely different model with no error.

The same trap sits under the inhibition family. "Uncompetitive" and
"noncompetitive" both CONTAIN "competitive", and they are three different
rate laws with three different Lineweaver-Burk signatures. They are told
apart inside `_inhibition` with `_has`, which anchors on word boundaries,
and in the order most-specific-first -- and `test_compose_grammar_expansion`
exists mostly to keep that true. Anyone adding a keyword here should ask
what OTHER query now contains it as a substring, because `RULES` matching
is substring matching and will not ask on their behalf.
"""

from __future__ import annotations

import importlib
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

#: The motif libraries beyond the core, and what each one holds. Keyed by
#: module name because that is what a refusal has to print: a reader told
#: "the transport motifs are missing" cannot act, and one told
#: "Terium/compose/library_transport.py is not in this checkout" can.
EXPANSION_LIBRARIES: Dict[str, str] = {
    "library_expression":
        "transcription, translation, promoters and tagged turnover",
    "library_enzymology":
        "multi-substrate, allosteric, channelled and cycling enzymes",
    "library_transport":
        "carriers, pumps, coupled transport and receptor internalisation",
}


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


class MissingMotifLibrary(UnrecognisedShape):
    """The shape was recognised; the motifs that build it are not here.

    A SUBCLASS, so every caller that already handles a refusal keeps
    working -- `pipeline.compose` and the coverage harness both catch
    `UnrecognisedShape` and neither needs to change. A DISTINCT TYPE,
    because the two refusals send a reader to different places: "say which
    mechanism you mean" is advice to the person typing, and "this file is
    not in your checkout" is advice to the person installing. Collapsing
    them would send somebody away to rephrase a query that was already
    perfectly clear.

    The message never offers to build something adjacent. A symporter is
    not a facilitated carrier, and quietly substituting one would answer a
    different question -- the failure mode this whole module exists to
    avoid. It says what IS reachable and lets the reader decide.
    """

    def __init__(
        self,
        query: str,
        module: str,
        motif_name: str,
        shape: str,
        instead: str = "",
        *,
        module_present: bool = False,
    ):
        self.module = module
        self.motif_name = motif_name
        #: True when the FILE is here and the motif name is not. Different
        #: fix -- a rename to chase rather than a file to add -- so the two
        #: are not flattened into one sentence.
        self.module_present = module_present
        holds = EXPANSION_LIBRARIES.get(module, "further motifs")
        where = f"Terium/compose/{module}.py ({holds})"
        if module_present:
            missing = (
                f"{where} IS in this checkout and defines no {motif_name}, "
                f"so the name has drifted rather than the file being absent"
            )
        else:
            missing = f"{where} is not in this checkout"
        reason = (
            f"{shape!r} is a shape this grammar recognises, but the motif "
            f"that builds it ({motif_name}) lives in {missing}. Nothing "
            f"adjacent was substituted: a near-miss mechanism simulates "
            f"perfectly and answers a different question."
        )
        if instead:
            reason += f" {instead}"
        super().__init__(query, reason)


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
# Reaching the expansion libraries without depending on them
# ---------------------------------------------------------------------------


def _expansion_module(name: str):
    """Import one of the expansion libraries, or return None if it is absent.

    None means "not in this checkout". It does NOT mean "the library is
    broken": a `ModuleNotFoundError` naming something other than the library
    itself is re-raised, because a transport library that fails because
    `numpy` is missing must not be reported as a transport library nobody
    wrote. The two need opposite fixes and the error is the only place the
    difference survives.
    """
    package = __package__ or ""
    candidates = [f"{package}.{name}"] if package else []
    candidates.append(name)

    for candidate in candidates:
        try:
            return importlib.import_module(candidate)
        except ModuleNotFoundError as absent:
            if absent.name not in {candidate, name}:
                raise
    return None


def _expansion_motif(
    query: str,
    module: str,
    names: Sequence[str],
    *,
    shape: str,
    instead: str = "",
):
    """The first of `names` the library defines, or a refusal saying so.

    `names` is a sequence rather than one string because these libraries are
    written alongside this file rather than before it, and the same motif
    has been reasonably spelled `..._INTERNALIZATION` and
    `..._INTERNALISATION` by two people on the same afternoon. Accepting
    both spellings is not guessing at biology -- the motif either exists
    under one of them or the refusal names every spelling it looked for.
    """
    library = _expansion_module(module)
    if library is None:
        raise MissingMotifLibrary(query, module, " or ".join(names), shape, instead)
    for name in names:
        found = getattr(library, name, None)
        if found is not None:
            return found
    raise MissingMotifLibrary(
        query, module, " or ".join(names), shape, instead, module_present=True,
    )


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


def _gene_expression(query: str, name: str) -> Recognition:
    """Transcription and translation as two steps, not one.

    The core library has `synthesis_degradation`, which lumps them: protein
    appears at a constant rate and decays. That is the right model for a lot
    of questions and the wrong one for any question about TIMING, because
    the lump has no mRNA and therefore no delay -- the two-stage system's
    response is second order and the lumped one's is first order, so they
    disagree about how fast a gene can be switched on no matter how the
    constants are chosen. It also has no burst: mRNA lifetime is what sets
    protein noise, and a one-stage model cannot express it at all.

    Which is why this reaches for `library_expression` and refuses rather
    than quietly handing back the lump.
    """
    composition = Composition(name)

    if _has(query, "ssra", "clpxp", "degradation tag", "degradation tagged",
            "tagged protein", "targeted degradation", "degron"):
        motif = _expansion_motif(
            query, "library_expression", ("PROTEIN_DEGRADATION_TAGGED",),
            shape="tagged protein degradation",
            instead=(
                "'saturable degradation' builds Michaelis-Menten removal "
                "from the core library, which is the same shape without the "
                "tag being a species of its own."
            ),
        )
        composition.add(motif, "tagged")
        composition.note(
            "degradation through a protease that the tag recruits, so "
            "removal is saturable and competes with everything else "
            "carrying the tag. First-order decay assumes the protease is "
            "never busy, and a tagged system is where that assumption fails"
        )
        return Recognition(
            composition, "tagged_degradation", "tag-directed proteolysis"
        )

    if _has(query, "mrna degradation", "mrna decay", "mrna half-life",
            "mrna half life", "transcript degradation", "transcript decay"):
        motif = _expansion_motif(
            query, "library_expression", ("MRNA_DEGRADATION",),
            shape="mRNA degradation",
            instead=(
                "'a species made and removed' builds first-order turnover "
                "from the core library without naming it as mRNA."
            ),
        )
        composition.add(motif, "transcript")
        composition.note(
            "mRNA turnover on its own. Its rate constant is the one that "
            "sets how fast a gene can be switched OFF, and in bacteria it is "
            "minutes against a protein's hours, which is why the two "
            "lifetimes cannot be lumped into one"
        )
        return Recognition(composition, "mrna_degradation", "transcript turnover")

    if _has(query, "repressed promoter", "repressible promoter") or (
        _has(query, "promoter") and _has(query, "repressed", "repressor")
    ):
        motif = _expansion_motif(
            query, "library_expression", ("REPRESSED_PROMOTER",),
            shape="repressed promoter",
            instead=(
                "'cooperative repression' builds a Hill repression term "
                "from the core library, which is the same regulation "
                "without transcription and translation being separate."
            ),
        )
        composition.add(motif, "promoter")
        composition.note(
            "transcription initiation under a repressor, as a Hill term on "
            "the mRNA synthesis rate. The Hill coefficient is a modelling "
            "choice and is declared as one; it is not a measurement of this "
            "promoter"
        )
        composition.note(
        "this is transcription ALONE. Nothing here translates the transcript "
        "or degrades it, so mRNA accumulates without bound -- which is a "
        "property of a half-model rather than of a promoter, and it is said "
        "here rather than left to be discovered on the first plot. Compose "
        "it with mRNA degradation and translation, or ask for two-stage gene "
        "expression, to close the system"
    )
        return Recognition(composition, "repressed_promoter", "repressed transcription")

    if _has(query, "activated promoter", "inducible promoter") or (
        _has(query, "promoter") and _has(query, "activated", "activator", "induced")
    ):
        motif = _expansion_motif(
            query, "library_expression", ("ACTIVATED_PROMOTER",),
            shape="activated promoter",
            instead=(
                "'cooperative activation' builds a Hill activation term "
                "from the core library."
            ),
        )
        composition.add(motif, "promoter")
        composition.note(
            "transcription initiation under an activator, as a Hill term on "
            "the mRNA synthesis rate"
        )
        composition.note(
        "this is transcription ALONE. Nothing here translates the transcript "
        "or degrades it, so mRNA accumulates without bound -- which is a "
        "property of a half-model rather than of a promoter, and it is said "
        "here rather than left to be discovered on the first plot. Compose "
        "it with mRNA degradation and translation, or ask for two-stage gene "
        "expression, to close the system"
    )
        return Recognition(composition, "activated_promoter", "activated transcription")

    if _has(query, "promoter") and not _has(query, "transcription", "translation"):
        motif = _expansion_motif(
            query, "library_expression", ("CONSTITUTIVE_PROMOTER",),
            shape="constitutive promoter",
            instead=(
                "'made at a constant rate' builds zero-order synthesis with "
                "first-order turnover from the core library."
            ),
        )
        composition.add(motif, "promoter")
        composition.note(
            "an unregulated promoter: transcription at a fixed rate, with no "
            "claim that any regulator is absent -- only that none is modelled"
        )
        composition.note(
        "this is transcription ALONE. Nothing here translates the transcript "
        "or degrades it, so mRNA accumulates without bound -- which is a "
        "property of a half-model rather than of a promoter, and it is said "
        "here rather than left to be discovered on the first plot. Compose "
        "it with mRNA degradation and translation, or ask for two-stage gene "
        "expression, to close the system"
    )
        return Recognition(
            composition, "constitutive_promoter", "unregulated transcription"
        )

    if _has(query, "translation", "ribosome") and not _has(
        query, "transcription", "gene expression", "central dogma"
    ):
        motif = _expansion_motif(
            query, "library_expression", ("TRANSLATION",), shape="translation",
            instead=(
                "'two stage gene expression' builds transcription and "
                "translation together, which is usually what is wanted."
            ),
        )
        composition.add(motif, "translation")
        composition.note(
            "protein synthesis from an existing transcript. The mRNA is a "
            "species and not a parameter, so this composes with whatever "
            "makes and destroys it rather than assuming it is constant"
        )
        return Recognition(composition, "translation", "protein from transcript")

    motif = _expansion_motif(
        query, "library_expression", ("TWO_STAGE_EXPRESSION",),
        shape="two-stage gene expression",
        instead=(
            "'a species made and removed' builds the LUMPED one-stage "
            "model from the core library. It is a different model, not a "
            "rougher one: with no mRNA it has no delay and no burst, so it "
            "cannot answer a question about how fast a gene switches on or "
            "how noisy its protein is."
        ),
    )
    composition.add(motif, "gene")
    composition.note(
        "transcription and translation as separate steps, with mRNA as a "
        "species. The second stage is what gives the response its delay: a "
        "lumped one-stage model relaxes exponentially and this one does not, "
        "for any choice of constants"
    )
    return Recognition(
        composition, "two_stage_expression", "transcription then translation"
    )


def _autoregulated_gene(query: str, name: str) -> Recognition:
    """A gene whose own product regulates its promoter.

    Its own rule rather than a branch of `_gene_expression`, because
    autoregulation is a WIRING claim and not a stage count: the loop is what
    the query is about. Negative autoregulation speeds the approach to
    steady state and narrows the protein distribution (Rosenfeld, Elowitz &
    Alon 2002); positive autoregulation does the opposite and can be
    bistable. The sign therefore changes the answer, and it is read from the
    query rather than defaulted.
    """
    composition = Composition(name)
    positive = _has(query, "positive", "positively", "self-activating",
                    "activates its own", "autoactivation")
    negative = _has(query, "negative", "negatively", "self-repressing",
                    "represses its own", "autorepression", "autoinhibition")
    if positive and negative:
        raise UnrecognisedShape(
            query,
            "This names both positive and negative autoregulation. They are "
            "opposite models -- negative feedback speeds the approach to "
            "steady state and narrows the distribution, positive feedback "
            "slows it and can make the gene bistable -- so there is no "
            "reading that covers both. Say which loop you mean.",
        )

    if positive:
        # Asked for by name, so it is looked for by name. The autorepressing
        # motif is NOT substituted: it moves the response time in the
        # opposite direction, so it is the wrong answer rather than a rough
        # one, and a reader who got it would draw the reverse conclusion
        # from a model that ran perfectly.
        motif = _expansion_motif(
            query, "library_expression",
            ("POSITIVE_AUTOREGULATION", "AUTOACTIVATED_GENE",
             "AUTOACTIVATING_GENE"),
            shape="positive autoregulation",
            instead=(
                "AUTOREGULATED_GENE is the NEGATIVE loop and was not "
                "substituted: negative feedback speeds the approach to "
                "steady state and positive feedback slows it, so one is not "
                "an approximation of the other. 'cooperative activation' "
                "builds a Hill activation term from the core library, but "
                "its activator is a separate species -- an open loop, not a "
                "closed one."
            ),
        )
        composition.add(motif, "gene")
        composition.note(
            "POSITIVE autoregulation, read from the query: the product "
            "raises its own synthesis, which SLOWS the approach to steady "
            "state and, with cooperative binding, admits two stable states"
        )
        reading = "positive loop, read from the query"
    else:
        motif = _expansion_motif(
            query, "library_expression", ("AUTOREGULATED_GENE",),
            shape="autoregulated gene",
            instead=(
                "'cooperative repression' builds a Hill repression term "
                "from the core library, but its repressor is a SEPARATE "
                "species: there is no loop, so it cannot show the faster "
                "response autoregulation exists for."
            ),
        )
        composition.add(motif, "gene")
        # The motif's own words, not a restatement of them. This file does
        # not own library_expression and should not narrate what it
        # contains from memory.
        composition.note(f"the motif used is {motif.name}: {motif.summary}")
        if negative:
            composition.note(
                "NEGATIVE autoregulation, read from the query. The product "
                "shuts off its own synthesis, which speeds the approach to "
                "steady state and narrows the protein distribution "
                "(Rosenfeld, Elowitz & Alon 2002)"
            )
            reading = "negative loop, read from the query"
        else:
            composition.note(
                "the query did not say whether the loop is positive or "
                "negative, so the library's default autoregulation motif "
                "was used and its summary is quoted above. The sign is not "
                "a detail: the two move the response time in opposite "
                "directions. Say 'positive' or 'negative' to pin it"
            )
            reading = "sign not stated in the query; library default used"
    return Recognition(composition, "autoregulated_gene", reading)


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


def _mwc_allostery(query: str, name: str) -> Recognition:
    """The concerted model, which is not the same claim as a Hill exponent.

    `cooperative_catalysis` already gives a sigmoid, and for fitting a curve
    that is often enough. It is not the same model. A Hill exponent is a
    phenomenological summary with no states in it; Monod, Wyman and Changeux
    (1965) say the enzyme is an oligomer flipping as a unit between a tense
    and a relaxed conformation, that the ratio of the two at zero ligand is
    L, and that this is why an ACTIVATOR and an INHIBITOR can shift the same
    curve in opposite directions without touching the active site.

    The difference is testable rather than aesthetic: MWC forbids negative
    cooperativity, and a Hill fit with h < 1 will happily report it.
    """
    composition = Composition(name)
    motif = _expansion_motif(
        query, "library_enzymology", ("MWC_ALLOSTERY",),
        shape="MWC concerted allostery",
        instead=(
            "'sigmoidal enzyme kinetics' builds the Hill form from the core "
            "library. It reproduces the same curve and carries no R and T "
            "states, so it cannot represent an allosteric effector at all."
        ),
    )
    composition.add(motif, "enzyme")
    composition.note(
        "the concerted (Monod-Wyman-Changeux) model: every subunit flips "
        "together, so there are two conformations and no hybrids. L is the "
        "equilibrium between them with no ligand bound, and Kr and Kt are "
        "the two conformations' affinities -- three quantities where a Hill "
        "fit has one, which is why the two models are distinguishable"
    )
    composition.note(
        "no allosteric EFFECTOR is a species in this model. An effector acts "
        "by changing L, so representing one means a second binding "
        "equilibrium that this motif does not contain -- state the effector "
        "and it would need a motif that carries it, rather than L being "
        "quietly retuned"
    )
    composition.note(
        "MWC cannot produce negative cooperativity: with L > 0 and Kr < Kt "
        "the curve is sigmoid or hyperbolic and never anti-cooperative. If "
        "the data show negative cooperativity this is the wrong model, and a "
        "Hill fit would hide that by reporting h < 1 without complaint"
    )
    return Recognition(composition, "mwc_allostery", "concerted two-state allostery")


def _futile_cycle(query: str, name: str) -> Recognition:
    """Two opposing enzymes on the same interconversion.

    The name is a slander that stuck. The cycle spends ATP to go nowhere at
    steady state, and what it buys is sensitivity: when both enzymes run
    near saturation, the fraction in each form switches over a much narrower
    range of stimulus than either enzyme alone could give -- the zero-order
    ultrasensitivity of Goldbeter and Koshland (1981). That is a property of
    the CYCLE and disappears if either direction is modelled as first order.
    """
    composition = Composition(name)
    motif = _expansion_motif(
        query, "library_enzymology", ("FUTILE_CYCLE",), shape="futile cycle",
        instead=(
            "'a phosphorylation cycle' is the same shape in the core "
            "library under a different name -- ask for a two step "
            "phosphorylation cascade to get one, or for the kinase and "
            "phosphatase pair directly."
        ),
    )
    composition.add(motif, "cycle")
    composition.note(
        "two opposing enzymes interconverting one pool. At steady state the "
        "net flux is zero and the ATP is still spent, which is what the name "
        "objects to and also what is bought: near saturation the switch "
        "between the two forms is far sharper than either enzyme's own "
        "Michaelis curve (Goldbeter & Koshland 1981)"
    )
    composition.note(
        "the ultrasensitivity is a property of both steps saturating. "
        "Modelling either direction as first order removes it silently, and "
        "the model still runs"
    )
    return Recognition(composition, "futile_cycle", "two opposing enzymes, one pool")


def _substrate_channeling(query: str, name: str) -> Recognition:
    """Intermediate handed between enzymes without entering the bulk.

    A strong claim, and the reason it is a separate motif: channelling says
    the intermediate never equilibrates with the cytosolic pool, so its bulk
    concentration is NOT the concentration the second enzyme sees. Every
    ordinary two-step model assumes the opposite. Where channelling is real
    the transit time is shorter than free diffusion allows and a competing
    enzyme cannot intercept the intermediate -- both of which are
    measurable, and neither of which a chained pair of catalytic steps can
    express.
    """
    composition = Composition(name)
    motif = _expansion_motif(
        query, "library_enzymology", ("SUBSTRATE_CHANNELING",),
        shape="substrate channelling",
        instead=(
            "'a two step enzyme cascade' builds two catalytic steps sharing "
            "a bulk intermediate from the core library. That is the model "
            "channelling contradicts, so it is an alternative to consider "
            "rather than an approximation of this one."
        ),
    )
    composition.add(motif, "complex")
    composition.note(
        "the intermediate has two fates: handed straight to the second "
        "active site, or released into the bulk. Channelling is the RATIO "
        "of those two rates and not a yes-or-no property, which is why both "
        "routes are in the model -- a version with only the handover would "
        "assert perfect channelling, which almost nothing achieves"
    )
    composition.note(
        "where the handover wins, the intermediate's measured cytosolic "
        "concentration is not what the second enzyme sees. A chained pair of "
        "catalytic steps assumes the exact opposite, and the two disagree "
        "most where it matters: on whether a competing enzyme can intercept "
        "the intermediate"
    )
    return Recognition(
        composition, "substrate_channeling", "intermediate handed over directly"
    )


def _transport(query: str, name: str) -> Recognition:
    """Carriers, pumps and coupled transport -- and the refusal in the middle.

    The default is the facilitated carrier from the core library, which is
    always here. The coupled and active forms live in `library_transport`
    and refuse by name when it does not, because a symporter driven by a
    sodium gradient and a uniporter running down a concentration gradient
    are different models: one can move its solute UPHILL and the other
    cannot, which is the entire reason a cell has both.
    """
    composition = Composition(name)

    # "Cotransport" without a direction is refused, on the same grounds as
    # an unqualified two-substrate query. Symport and antiport are both
    # cotransport, they differ in the SIGN of the coupled flux, and picking
    # one would decide which way the driven solute moves.
    if _has(query, "cotransport", "co-transport", "coupled transport") and not _has(
        query, "symport", "symporter", "antiport", "antiporter", "exchanger",
        "same direction", "opposite direction", "exchange",
    ):
        raise UnrecognisedShape(
            query,
            "Coupled transport is either SYMPORT (both solutes cross the "
            "same way, as in the sodium-glucose transporter) or ANTIPORT "
            "(they cross in opposite directions, as in the "
            "sodium-calcium exchanger). They differ in the sign of one "
            "stoichiometric coefficient and therefore in which direction "
            "the driven solute is pushed, so choosing for you would decide "
            "the answer. Say symport or antiport, and this builds it.",
        )

    if _has(query, "symport", "symporter"):
        motif = _expansion_motif(
            query, "library_transport", ("SYMPORT",), shape="symport",
            instead=(
                "'facilitated diffusion' builds a carrier from the core "
                "library, but it cannot move a solute against its gradient "
                "and a symporter's whole point is that it can."
            ),
        )
        composition.add(motif, "symporter")
        composition.note(
            "two solutes crossing in the SAME direction on one carrier. The "
            "driving solute's gradient is what lets the driven one move "
            "uphill, so both concentrations are species and the coupling is "
            "in the stoichiometry rather than in a rate constant"
        )
        return Recognition(composition, "symport", "coupled transport, same direction")

    if _has(query, "antiport", "antiporter", "exchanger", "countertransport"):
        motif = _expansion_motif(
            query, "library_transport", ("ANTIPORT",), shape="antiport",
            instead=(
                "'facilitated diffusion' builds an uncoupled carrier from "
                "the core library; it moves one solute and models no "
                "exchange."
            ),
        )
        composition.add(motif, "antiporter")
        composition.note(
            "two solutes crossing in OPPOSITE directions on one carrier. The "
            "exchange stoichiometry is what makes it electrogenic or not, "
            "and that is a property of the stoichiometry rather than of any "
            "rate constant"
        )
        return Recognition(composition, "antiport", "coupled transport, opposite directions")

    if _has(query, "primary active", "active transport", "atp-driven",
            "atp driven", "pump", "atpase"):
        motif = _expansion_motif(
            query, "library_transport",
            ("PRIMARY_ACTIVE_TRANSPORT",), shape="primary active transport",
            instead=(
                "'facilitated diffusion' builds a carrier that runs only "
                "downhill, which is the one thing a pump is defined by not "
                "doing."
            ),
        )
        composition.add(motif, "pump")
        composition.note(
            "hydrolysis coupled directly to translocation. ATP appears as a "
            "species, not as a constant: a pump that never runs its fuel "
            "down would move solute uphill forever, which is the failure "
            "mode of writing the drive as a parameter"
        )
        return Recognition(
            composition, "primary_active_transport", "ATP-driven pumping"
        )

    if _has(query, "passive leak", "leak", "leakage", "leaky"):
        motif = _expansion_motif(
            query, "library_transport", ("PASSIVE_LEAK",), shape="passive leak",
            instead=(
                "'facilitated diffusion' builds the saturable carrier, "
                "which is a different claim: a leak does not saturate."
            ),
        )
        composition.add(motif, "leak")
        composition.note(
            "unsaturable, first-order flux down the gradient. A leak is what "
            "makes a pumped gradient cost something to hold, so a model with "
            "a pump and no leak reaches a steady state that no cell pays for"
        )
        return Recognition(composition, "passive_leak", "non-saturable leak")

    # The CORE motif, deliberately, even where `library_transport` is
    # present and carries a richer facilitated-diffusion motif of its own.
    # Preferring whichever library happens to be installed would make the
    # same query return two different models on two checkouts, silently --
    # strictly worse than a refusal, which at least announces itself. A
    # compartment-aware variant should be reached by a query that ASKS for
    # compartments, not by an import succeeding.
    composition.add(FACILITATED_TRANSPORT, "carrier")
    composition.note(
        "a transporter is an enzyme whose product is the same molecule "
        "somewhere else, so it saturates the same way. Modelled as two "
        "species, inside and outside, which makes the gradient a state of "
        "the model rather than a parameter of it"
    )
    composition.note(
        "the two compartments are treated as having the same volume: the "
        "solute moving is one molecule leaving Out and one arriving In. "
        "Where the volumes differ that is wrong by their ratio, and the "
        "ratio has to be in the model rather than in the reader's head"
    )
    return Recognition(composition, "facilitated_transport", "carrier-mediated transport")


def _receptor_internalisation(query: str, name: str) -> Recognition:
    """Ligand binding followed by removal of the receptor from the surface.

    Its own rule rather than a branch of `_binding`, because the two make
    different claims and the difference is the interesting one. Reversible
    binding conserves receptor: occupancy rises and falls and the total
    never changes. Internalisation does not -- the receptor leaves the
    surface pool, so the system desensitises, and that is visible in the
    conservation laws rather than in any rate law.
    """
    composition = Composition(name)
    motif = _expansion_motif(
        query, "library_transport",
        # Two spellings because two people can name the same motif on the
        # same afternoon; see `_expansion_motif`.
        ("RECEPTOR_LIGAND_INTERNALIZATION", "RECEPTOR_LIGAND_INTERNALISATION",
         "RECEPTOR_INTERNALIZATION", "RECEPTOR_INTERNALISATION"),
        shape="receptor internalisation",
        instead=(
            "'reversible binding of a ligand to a receptor' builds the "
            "binding step alone from the core library. It conserves "
            "receptor, so it cannot show desensitisation -- which is "
            "usually the reason somebody asks for internalisation."
        ),
    )
    composition.add(motif, "receptor")
    composition.note(
        "the occupied receptor is removed from the surface pool rather than "
        "only releasing its ligand, so total surface receptor is NOT "
        "conserved. That non-conservation is the mechanism of "
        "desensitisation and the network derives it from the stoichiometry"
    )
    return Recognition(
        composition, "receptor_internalisation", "ligand-induced receptor removal"
    )


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
    # Above `gene_expression` (85) because a query naming both -- "negative
    # autoregulation of gene expression" -- is asking about the LOOP, and
    # the two-stage model without the loop would answer the general question
    # instead of the specific one. None of these triggers is a bare
    # "repress": "repressilator" and "two repressors" contain it, and either
    # would have been swallowed.
    Rule("autoregulated_gene", (), ("autoregulat", "auto-regulat",
                                    "self-repressing", "self-activating",
                                    "represses its own", "activates its own",
                                    "autorepression", "autoactivation",
                                    "autoinhibition"),
         _autoregulated_gene,
         "a gene whose product regulates its own promoter", 87),
    Rule("toggle_switch", (), ("toggle switch", "bistable switch",
                               "mutual repression"), _toggle_switch,
         "two genes each repressing the other", 86),
    # "gene expression" and not "expression": `turnover` (72) already owns
    # "constitutive expression", and a bare "expression" would take it.
    Rule("gene_expression", (), ("gene expression", "transcription",
                                 "translation", "central dogma", "promoter",
                                 "mrna", "messenger rna", "ribosome",
                                 "ssra", "clpxp", "degron",
                                 "degradation tag", "tagged protein"),
         _gene_expression,
         "transcription and translation as separate stages", 85),
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
    # Above `binding` (60), which triggers on "receptor" and "ligand" and
    # would otherwise take every internalisation query. Note that none of
    # these triggers is a bare "receptor": "reversible binding of a ligand
    # to a receptor" must keep reaching `binding`, and "an allosteric
    # inhibitor binding to a receptor" must keep reaching `inhibition`.
    Rule("receptor_internalisation", (), ("internalis", "internaliz",
                                          "endocytosis", "endocytic",
                                          "receptor downregulation",
                                          "receptor down-regulation"),
         _receptor_internalisation,
         "ligand-bound receptor removed from the surface pool", 81),
    Rule("enzyme_cascade", (), ("enzyme cascade", "catalytic cascade",
                                "reaction cascade"), _enzyme_cascade,
         "N catalytic steps, product to substrate", 80),
    # "futile cycle" and "substrate cycle", never a bare "cycle": "cell
    # cycle oscillator dynamics" belongs to the catalogue and this path must
    # keep refusing it, and "a phosphorylation cycle" is a different motif.
    Rule("futile_cycle", (), ("futile cycle", "futile", "substrate cycle",
                              "opposing kinase", "kinase and phosphatase"),
         _futile_cycle,
         "two opposing enzymes turning one pool over", 79),
    Rule("open_system", (), ("constant inflow", "constant supply", "chemostat",
                             "open system", "continuous feed", "substrate inflow"),
         _open_system, "a fed reactor with no conservation over the fed species", 78),
    Rule("bi_substrate", (), ("two substrate", "two-substrate", "bi-bi", "bi bi",
                              "ping pong", "ping-pong", "ordered sequential"),
         _bi_substrate, "an enzyme with two substrates, ordered or ping-pong", 77),
    Rule("transport", (), ("transport", "transporter", "carrier", "uptake",
                           "across the membrane", "facilitated diffusion",
                           "symport", "antiport", "exchanger",
                           "countertransport", "cotransport", "co-transport",
                           "coupled transport", "pump", "atpase",
                           "passive leak", "leak"),
         _transport,
         "a carrier, pump or coupled transporter across a boundary", 76),
    Rule("autocatalysis", (), ("autocataly", "self-amplif", "self amplif",
                               "catalyses its own", "catalyzes its own", "prion"),
         _autocatalysis, "a product that catalyses its own formation", 75),
    Rule("reversible_step", (), ("reversible reaction", "runs both ways",
                                 "reversible enzymatic", "reversible michaelis",
                                 "near equilibrium"),
         _reversible_step, "an enzymatic step that runs in both directions", 74),
    # "channeling"/"channelling" and never "channel": an ion channel is a
    # different mechanism in a different library, and the prefix would take
    # every query about one.
    Rule("substrate_channeling", (), ("channeling", "channelling",
                                      "metabolon", "handed directly"),
         _substrate_channeling,
         "an intermediate passed between enzymes, never entering the bulk", 73),
    Rule("turnover", (), ("saturable degradation", "zero order degradation",
                          "zero-order degradation", "synthesis and degradation",
                          "constitutive expression", "made and degraded",
                          "turnover of"),
         _turnover, "a species made and removed, first-order or saturable", 72),
    # Above `cooperative_enzyme` (69) and `allosteric` (68), both of which
    # trigger on words an MWC query contains -- "allosteric" and
    # "cooperative" are in almost every phrasing of one. The Hill form fits
    # the same curve with one exponent where MWC has L, Kr and Kt, so
    # answering an MWC query with it would silently discard the two-state
    # structure that was the question.
    Rule("mwc_allostery", (), ("mwc", "monod-wyman-changeux",
                               "monod wyman changeux", "concerted allosteric",
                               "concerted transition", "concerted model",
                               "tense and relaxed", "relaxed and tense",
                               "two-state allosteric"),
         _mwc_allostery,
         "the concerted two-state model of an allosteric enzyme", 71),
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
    "recognise", "shapes", "Recognition", "UnrecognisedShape",
    "MissingMotifLibrary", "Rule", "RULES", "NAMED_PATHWAYS",
    "MAX_INFERRED_STAGES", "EXPANSION_LIBRARIES",
]
