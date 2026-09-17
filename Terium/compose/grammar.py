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
`library.py` is the core and is always here. Five further libraries --
`library_expression`, `library_enzymology`, `library_transport`,
`library_signaling`, `library_metabolic` -- carry the motifs for gene
expression, the harder enzyme mechanisms, membrane transport, signalling
wiring patterns, and metabolic pathway pieces. They are written
independently of this file and any of them can be absent from a checkout.

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

THE SAME TRAP, FOUR MORE TIMES
------------------------------
Adding the signalling and metabolic libraries meant asking that question
again for every new word, and it bit four times. Each is written down here
because the fix is invisible in the rule table -- a trigger chosen to avoid
a collision looks exactly like one that was not.

  * "coherent" is inside "incoherent", and the two feed-forward loops are
    opposite computations: the coherent one delays a rising input and the
    incoherent one turns a step into a pulse. Told apart in
    `_feedforward_loop` with `_has`, incoherent first, exactly as the
    inhibition family is.

  * "branched pathway" is inside "unbranched pathway", which is the phrase
    somebody reaches for when they mean a LINEAR one. Resolved by rank --
    `metabolic_pathway` (64) outranks `branch_point` (63) -- so "an
    unbranched pathway" builds a chain and not a split.

  * "transcription" is inside "transcriptional", so "a transcriptional
    oscillator" is swallowed by `gene_expression` (85). It is therefore NOT
    a trigger for the oscillator rule; "negative feedback oscillator" and
    "delayed negative feedback" are.

  * "g protein", spelled with a space, is inside "bindin(g protein)". It is
    NOT a trigger. "gpcr", "g-protein" and "g protein coupled" are, and "a
    ligand binding protein" keeps reaching `binding`.

WHAT WAS DELIBERATELY LEFT UNREACHABLE
--------------------------------------
`library_metabolic.ALLOSTERIC_FEEDBACK` and
`library_metabolic.TRANSPORTER_LIMITED_UPTAKE` have no phrase here, and
that is a decision rather than an omission. Every phrase that reaches the
first is already owned by `feedback_inhibition` (82), whose deliberate
refusal to guess WHICH step of a pathway is the committed one is pinned
behaviour; every phrase that reaches the second is already owned by
`transport` (76), which sends coupled uptake to
`library_transport.SYMPORT`. Wiring either would put two motifs behind one
phrase, and "which of the two ran" is not a question a reader of the
report could then answer.
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
    #: A pathway of one segment is a reversible enzymatic step, which the
    #: core library already builds under its own name. The thing a pathway
    #: is asked about -- where the flux control sits, whether the chain can
    #: carry the flux the free energy allows -- needs somewhere for control
    #: to be distributed, and one step has nowhere.
    "pathway": 2,
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
    "library_signaling":
        "feed-forward loops, two-component systems, GPCR cycles, scaffolds "
        "and feedback oscillators",
    "library_metabolic":
        "reversible pathway segments, branch points and conserved cofactor "
        "pools",
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


def _package_path_missing(exc: ModuleNotFoundError) -> bool:
    """Whether `exc` says the Terium package path itself is unavailable.

    Inlined for the same reason `terium_engine.py` inlines its copy: this
    guards the import machinery, so it cannot import the helper from
    `Terium/core/import_mode.py` to do its job. A flat-mode retry is only
    the right response to the package path being unavailable; any other
    missing module -- a `numpy` inside an expansion library -- must re-raise,
    or a missing dependency is reported as a missing internal module (the
    exact error `Terium/core/import_mode.py` exists to kill).
    """
    name = getattr(exc, "name", None)
    return bool(name) and (name == "Terium" or name.startswith("Terium."))


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
            # Only a package-path miss means flat mode can help. A library
            # whose own dependency is missing must surface that instead of
            # falling back to "not in this checkout"; a bare-name miss inside
            # a package candidate still falls through to the flat candidate
            # below, exactly as before.
            if not _package_path_missing(absent) and absent.name not in {
                candidate, name,
            }:
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
                "closed one. 'a bistable positive feedback loop' reaches "
                "library_signaling.BISTABLE_POSITIVE_FEEDBACK, which IS a "
                "closed positive loop -- with ONE stage rather than two, so "
                "it carries no transcript and no delay, which makes it a "
                "different model rather than this one with a sign flipped."
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


# ---------------------------------------------------------------------------
# Signalling wiring patterns
# ---------------------------------------------------------------------------
#
# These differ in kind from everything above them. A Michaelis-Menten motif
# is a RATE LAW and a feed-forward loop is a WIRING, which is why
# `library_signaling.py` exists separately and why the sentence that
# justifies one of these is about structure rather than about an assumption
# on an enzyme. The consequence for this file is that the interesting claim
# is almost always "what distinguishes this from the shape a reader might
# have meant instead", and the notes say it.


def _feedforward_loop(query: str, name: str) -> Recognition:
    """Coherent or incoherent -- and the query has to say which.

    The same treatment `_bi_substrate` gives ordered against ping-pong, and
    for the same reason: these are not two settings of one model, they are
    two computations. In the coherent loop X activates Y and X and Y
    together activate Z, so a rising input is DELAYED by the time Y takes to
    accumulate while a falling one passes straight through -- a
    sign-sensitive delay, which is a noise filter. In the incoherent loop X
    activates Z and also activates its repressor Y, so a step input makes a
    PULSE that comes back down. One filters and one differentiates.

    Defaulting to either would answer the other question silently, and the
    two models have the same species and the same species names, so nothing
    downstream would notice. So an unqualified "feed-forward loop" is
    refused with the distinction spelled out.

    "coherent" is a substring of "incoherent". They are separated by `_has`,
    which anchors on word boundaries, and incoherent is tested first -- the
    inhibition family's arrangement, for the inhibition family's reason.
    """
    composition = Composition(name)
    incoherent = _has(query, "incoherent", "i1-ffl", "i1 ffl", "type 1 incoherent")
    coherent = _has(query, "coherent", "c1-ffl", "c1 ffl", "type 1 coherent")

    if incoherent and coherent:
        raise UnrecognisedShape(
            query,
            "This names both the coherent and the incoherent feed-forward "
            "loop. They are opposite computations on the same three genes -- "
            "the coherent loop delays a rising input and passes a falling "
            "one straight through, the incoherent loop turns a sustained "
            "input into a pulse -- so there is no reading that covers both. "
            "Say which one you mean and this builds it; ask for each in "
            "turn to compare them.",
        )

    if incoherent:
        motif = _expansion_motif(
            query, "library_signaling", ("INCOHERENT_FEEDFORWARD",),
            shape="incoherent feed-forward loop",
            instead=(
                "'cooperative repression' builds a Hill repression term "
                "from the core library. It makes the output FALL and hold; "
                "only the loop makes it rise first and come back, which is "
                "the behaviour the shape is named for."
            ),
        )
        composition.add(motif, "loop")
        composition.note(
            "X activates the output and also activates its repressor, so "
            "the output overshoots and settles back. The pulse is a "
            "property of the WIRING and not of any rate constant: no choice "
            "of constants makes a plain repression pulse, and no choice "
            "removes the overshoot from this shape entirely"
        )
        composition.note(
            "whether the settled level returns EXACTLY to baseline -- "
            "perfect adaptation -- depends on the repression being close to "
            "saturating, which is a regime and not a structural guarantee. "
            "This model is not claimed to adapt perfectly, only to pulse"
        )
        return Recognition(
            composition, "incoherent_feedforward", "pulse-generating loop"
        )

    if coherent:
        motif = _expansion_motif(
            query, "library_signaling", ("COHERENT_FEEDFORWARD",),
            shape="coherent feed-forward loop",
            instead=(
                "'cooperative activation' builds a Hill activation term "
                "from the core library. It responds immediately in both "
                "directions; the delay on the way up, which is what this "
                "shape is for, comes from the second arm and cannot be "
                "recovered by tuning the first."
            ),
        )
        composition.add(motif, "loop")
        composition.note(
            "X activates Y, and X and Y together activate Z. The AND at the "
            "output is what makes the delay sign-sensitive: switching ON "
            "waits for Y to accumulate, switching OFF does not wait for it "
            "to decay, so a brief input is filtered out and a brief dropout "
            "is not"
        )
        composition.note(
            "the AND is written into the rate law rather than inferred, "
            "because an OR-gated coherent loop is a real and different "
            "circuit -- it delays the fall instead of the rise. Nothing "
            "here claims which gate a particular promoter uses"
        )
        return Recognition(
            composition, "coherent_feedforward", "sign-sensitive delay"
        )

    raise UnrecognisedShape(
        query,
        "A feed-forward loop is either COHERENT -- X activates Y, and X and "
        "Y together activate Z, which delays a rising input and passes a "
        "falling one straight through -- or INCOHERENT, where X activates Z "
        "and also activates its repressor, which turns a sustained input "
        "into a pulse. They are opposite computations built from the same "
        "three genes, and they are told apart by an experiment: only the "
        "incoherent loop overshoots. Say which, and this builds it.",
    )


def _two_component_system(query: str, name: str) -> Recognition:
    """A sensor kinase and its response regulator, as a phosphotransfer.

    Not a two-tier phosphorylation cascade, which is the shape a reader
    might reach for instead. A cascade tier is a kinase acting CATALYTICALLY
    on a separate substrate pool, so the phosphoryl group comes from ATP at
    every tier and the upstream kinase is not consumed. A two-component
    system hands the phosphoryl group ITSELF from the sensor to the
    regulator: the sensor is a substrate of the transfer as much as a
    catalyst of it, and the phosphorylated sensor is depleted by the
    transfer in a way a cascade's kinase never is.

    The difference shows up in the conservation laws, which the network
    derives from the stoichiometry rather than being told, and it is why
    this reaches for its own motif instead of chaining two cycles.
    """
    composition = Composition(name)
    motif = _expansion_motif(
        query, "library_signaling", ("TWO_COMPONENT_SYSTEM",),
        shape="two-component system",
        instead=(
            "'a two step phosphorylation cascade' builds two catalytic "
            "cycles from the core library. Its upper kinase is a catalyst "
            "and is not consumed, so it cannot express the phosphoryl "
            "transfer that defines this mechanism."
        ),
    )
    composition.add(motif, "system")
    composition.note(
        "autophosphorylation of the sensor followed by transfer of the "
        "phosphoryl group to the response regulator. ATP is a species and "
        "not a rate constant, so the model cannot phosphorylate forever "
        "without something regenerating it -- which is a property worth "
        "seeing rather than hiding in a parameter"
    )
    composition.note(
        "the signal enters by modulating the autophosphorylation rate. "
        "Nothing here claims WHICH stimulus a given sensor responds to, or "
        "that the sensor is bifunctional: many are also phosphatases for "
        "their own regulator, which sharpens the response, and asserting "
        "that without being told would be inventing the mechanism"
    )
    return Recognition(
        composition, "two_component_system", "sensor kinase and response regulator"
    )


def _gpcr_cycle(query: str, name: str) -> Recognition:
    """Agonist, receptor, and the G protein's nucleotide exchange cycle.

    Its own rule and not a branch of `_binding`, for the reason
    `_receptor_internalisation` is its own rule: the claim is different.
    Reversible binding gives occupancy, and occupancy is not the signal. The
    receptor is an ENZYME here -- one occupied receptor turns over many G
    proteins -- so the output is a flux and not a fraction, and the gain
    between them is the thing the model exists to show.

    "g protein" with a space is deliberately not a trigger: it is a
    substring of "binding protein". "gpcr", "g-protein" and "g protein
    coupled" are.
    """
    composition = Composition(name)
    motif = _expansion_motif(
        query, "library_signaling", ("GPCR_ACTIVATION",),
        shape="GPCR activation cycle",
        instead=(
            "'reversible binding of a ligand to a receptor' builds the "
            "occupancy step alone from the core library. Occupancy is not "
            "the signal: it saturates at one receptor per ligand, and the "
            "amplification a GPCR exists for is downstream of it."
        ),
    )
    composition.add(motif, "receptor")
    composition.note(
        "the occupied receptor acts catalytically on the G protein's "
        "nucleotide exchange, so one binding event produces many active G "
        "subunits. That gain is the reason the receptor is written as an "
        "enzyme rather than as a partner in a complex"
    )
    composition.note(
        "GTP hydrolysis is what makes this a CYCLE rather than a switch "
        "that latches. Its rate sets how fast the signal stops, which is a "
        "separate quantity from how fast it starts -- and a model with no "
        "hydrolysis term reaches a steady state only because it runs out of "
        "G protein"
    )
    composition.note(
        "no second messenger is a species here. What the active subunit "
        "goes on to do -- adenylyl cyclase, phospholipase C, an ion "
        "channel -- is a fact about the particular receptor and not about "
        "the shape, so it is left to be composed rather than assumed"
    )
    return Recognition(composition, "gpcr_activation", "receptor-catalysed G protein cycle")


def _ultrasensitive_cycle(query: str, name: str) -> Recognition:
    """Goldbeter-Koshland: the CORE phosphorylation cycle, under its own name.

    This deliberately does not reach for `library_signaling`, and the reason
    is worth stating because it looks like an oversight. The zero-order
    ultrasensitive cycle IS the phosphorylation cycle -- two opposing
    Michaelis-Menten arms on one protein pool -- and
    `library_signaling.ULTRASENSITIVE_CYCLE` is a NAME BOUND TO
    `library.PHOSPHORYLATION_CYCLE`, not a second definition of it. Reaching
    through the library would add an import this shape does not need and
    return the identical object, so the shape would refuse on a checkout
    without the library for no reason a reader could act on.

    That the alias really is an alias is a claim about another file, so it
    is pinned by a test rather than asserted here. If it ever became a
    separate motif, this rule would keep building the core one silently,
    which is exactly the kind of drift that test exists to catch.

    What is NOT claimed: that this model is ultrasensitive. The sharpness
    comes from both converter enzymes running SATURATED -- substrate well
    above Km on both arms -- and that is a regime set by the caller's
    concentrations, not by the structure. Outside it the same model is a
    graded, hyperbolic response.
    """
    composition = Composition(name)
    composition.add(PHOSPHORYLATION_CYCLE, "cycle")
    composition.note(
        "a kinase and a phosphatase acting on one protein pool. The total "
        "is conserved and the network derives that from the stoichiometry, "
        "so the state of the system is the FRACTION modified rather than an "
        "amount"
    )
    composition.note(
        "zero-order ultrasensitivity is a REGIME, not a structure. It "
        "appears when both converters are saturated, and then the modified "
        "fraction switches over a far narrower range of kinase activity "
        "than either Michaelis curve alone allows (Goldbeter & Koshland "
        "1981). With the pool small compared with either Km the very same "
        "model is graded, and nothing in it announces which side it is on"
    )
    composition.note(
        "the motif used is library.PHOSPHORYLATION_CYCLE, which "
        "library_signaling names ULTRASENSITIVE_CYCLE. One mechanism, one "
        "definition, two names -- a second copy of these rate laws would be "
        "two answers to one question"
    )
    return Recognition(
        composition, "ultrasensitive_cycle", "zero-order covalent modification cycle"
    )


def _scaffold_assembly(query: str, name: str) -> Recognition:
    """A scaffold holding two partners, and the reason more of it is worse.

    The non-monotonic part is the whole point. A scaffold raises the
    effective concentration of two partners for each other, so activity
    rises with scaffold -- until there is enough scaffold that most
    molecules of each partner sit on a scaffold of their OWN, and the
    ternary complex that actually does the work becomes rarer. Activity
    falls again. Nothing about a rate law predicts that; it comes out of the
    binding stoichiometry, which is why the binary complexes are species
    here rather than being assumed away.
    """
    composition = Composition(name)
    motif = _expansion_motif(
        query, "library_signaling", ("SCAFFOLD_ASSEMBLY",),
        shape="scaffold assembly",
        instead=(
            "'reversible binding' builds one two-partner complex from the "
            "core library. With only one binding event there is no ternary "
            "complex and therefore no optimum, so it cannot show the "
            "behaviour a scaffold is asked about."
        ),
    )
    composition.add(motif, "scaffold")
    composition.note(
        "the ternary complex is the active species and the two binary "
        "complexes are dead ends. Both are species, which is what lets the "
        "model show activity falling at high scaffold -- the prozone "
        "effect -- instead of rising forever"
    )
    composition.note(
        "no claim is made that a scaffold changes the CHEMISTRY of the "
        "reaction it holds. Here it changes only how often the partners "
        "meet. Scaffolds that also allosterically activate their partners "
        "exist, and that is a second mechanism this shape does not contain"
    )
    return Recognition(composition, "scaffold_assembly", "scaffold with an optimum")


def _negative_feedback_oscillator(query: str, name: str) -> Recognition:
    """A delayed negative feedback loop, as the general form of a clock.

    A SHAPE and not a subject, which is the line this grammar holds. The
    circadian clock of a particular organism is a subject -- it has named
    genes, measured periods and a pathway database behind it -- and is
    refused like any other named system. "Delayed negative feedback that
    oscillates" is a shape, and the shape is what has the property:
    negative feedback plus enough delay plus enough nonlinearity gives a
    limit cycle, whoever's genes are in it.

    "transcriptional oscillator" is NOT a trigger. "Transcription" is a
    substring of "transcriptional", so `gene_expression` (85) would take
    that phrase before this rule ever saw it.
    """
    composition = Composition(name)
    motif = _expansion_motif(
        query, "library_signaling", ("NEGATIVE_FEEDBACK_OSCILLATOR",),
        shape="delayed negative feedback oscillator",
        instead=(
            "'a negatively autoregulated gene' builds the same loop with "
            "ONE stage from library_expression. It settles rather than "
            "oscillating: the delay that a limit cycle needs comes from the "
            "extra stages, and no choice of constants puts it back."
        ),
    )
    composition.add(motif, "clock")
    composition.note(
        "three stages in series with the last repressing the first. The "
        "stages are the delay, and the delay is what turns negative "
        "feedback from a stabiliser into an oscillator -- the same loop "
        "with one stage has a stable steady state for every parameter set"
    )
    composition.note(
        "whether THIS parameter set oscillates is not claimed. A limit "
        "cycle needs the loop gain above a threshold that depends on the "
        "repression exponent and on the three rate constants together; the "
        "library's own description says the exponent default was chosen so "
        "the shape can exhibit what it is named for, and that is a property "
        "of a placeholder rather than a measurement of any clock"
    )
    return Recognition(
        composition, "negative_feedback_oscillator", "three-stage delayed loop"
    )


def _bistable_positive_feedback(query: str, name: str) -> Recognition:
    """One species driving its own production, with two stable levels.

    Distinct from `_toggle_switch`, which gets bistability from two genes
    repressing each other. This gets it from ONE species and cooperativity,
    which is a weaker structural claim and a different experiment: a toggle
    has two species whose levels anticorrelate, and this has one whose
    history you can read off its level.

    The signature that separates bistability from a very steep graded
    response is hysteresis, and it is a measurement rather than a picture:
    the dose-response curve taken upward does not lie on the one taken
    downward. A model that cannot be asked that question has not
    demonstrated bistability, and neither has a single simulation from a
    single initial condition.
    """
    composition = Composition(name)
    motif = _expansion_motif(
        query, "library_signaling", ("BISTABLE_POSITIVE_FEEDBACK",),
        shape="bistable positive feedback",
        instead=(
            "'cooperative activation' builds a Hill activation term from "
            "the core library, but its activator is a SEPARATE species: "
            "there is no loop, so the curve is steep and single-valued "
            "rather than bistable."
        ),
    )
    composition.add(motif, "loop")
    composition.note(
        "a protein that cooperatively raises its own production, with a "
        "basal leak so the off state is not an absorbing zero. Two stable "
        "levels with an unstable one between them"
    )
    composition.note(
        "bistability is not asserted for these constants. It requires the "
        "cooperativity and the ratio of production to removal to sit inside "
        "a region, and outside it the same model is monostable. The test "
        "is hysteresis -- sweep the input up and then down and compare -- "
        "which `continuation` can do and a single trajectory cannot"
    )
    return Recognition(
        composition, "bistable_positive_feedback", "one-species bistable loop"
    )


# ---------------------------------------------------------------------------
# Metabolic pieces
# ---------------------------------------------------------------------------


def _metabolic_pathway(query: str, name: str) -> Recognition:
    """N reversible segments in series, parameterised so they run downhill.

    Not `_enzyme_cascade`, which chains the IRREVERSIBLE catalytic step. The
    difference is the one `library_metabolic.py` is written around: an
    irreversible chain cannot approach equilibrium, cannot carry a back
    flux, and cannot be wrong about thermodynamics because it makes no
    thermodynamic claim at all. A chain of reversible steps CAN be wrong
    about it, and wrong in the worst way -- it runs, it is smooth, and it
    has quietly moved a metabolite uphill for free.

    The segment motif is parameterised by Keq rather than by a reverse kcat
    precisely so that cannot happen: the flux carries the sign of
    (S - P/Keq) for every value of every parameter. That is the library's
    property and not this file's, and the reason this reaches for that motif
    rather than chaining a reversible Michaelis-Menten from the core.

    The wiring is done by the library's own `linear_pathway`, not by a
    `chain` call here. Which port of a segment is the upstream one is the
    library's business, and writing it down in two files is how the two
    drift.
    """
    count = _count_before(query, "pathway", "segment", "step")
    if count is None:
        raise UnrecognisedShape(
            query,
            "A pathway needs a number of steps. 'A linear metabolic pathway "
            "of four steps' builds; 'a metabolic pathway' does not, because "
            "the length is the model -- it sets how many enzymes there are, "
            "how the flux control is distributed between them, and how far "
            "the chain's overall free energy drop is spread. Terrium will "
            "not pick a length for you.",
        )
    if count < MINIMUM_COPIES["pathway"]:
        raise UnrecognisedShape(
            query,
            f"A pathway of {count} is a single reversible enzymatic step, "
            f"not a pathway. Ask for 'a reversible enzymatic reaction' if "
            f"that is what you want; a pathway needs at least "
            f"{MINIMUM_COPIES['pathway']} steps for there to be anything to "
            f"distribute control over.",
        )

    composition = Composition(name)
    segment = _expansion_motif(
        query, "library_metabolic", ("LINEAR_PATHWAY_SEGMENT",),
        shape="linear metabolic pathway",
        instead=(
            "'a three step enzyme cascade' chains the IRREVERSIBLE "
            "catalytic step from the core library. It cannot run backwards "
            "and so cannot approach equilibrium, which is a different model "
            "rather than a rougher one."
        ),
    )
    place = _expansion_motif(
        query, "library_metabolic", ("linear_pathway",),
        shape="linear metabolic pathway",
        instead=(
            "the segment motif is present but the helper that chains it is "
            "not, and this file deliberately does not hard-code which of "
            "its ports is upstream."
        ),
    )
    place(composition, count, prefix="step", head_initial=1.0)
    composition.note(
        f"{count} reversible segments head to tail, each with its own "
        f"enzyme. Consecutive steps of a pathway are catalysed by different "
        f"enzymes, so nothing is shared between them unless asked for"
    )
    composition.note(
        f"each segment is written in the Keq form, so its flux carries the "
        f"sign of (S - P/Keq) whatever the constants are and no step can "
        f"run uphill. That is enforced by the algebra rather than by a "
        f"check somebody has to remember: {segment.name} has no independent "
        f"reverse kcat to be given a value that contradicts its Keq"
    )
    composition.note(
        "what is NOT enforced is that the chain's overall free energy drop "
        "is big enough to carry the flux a caller wants, or that the "
        "pathway is open at either end. With no source and no sink this "
        "settles to equilibrium, which is the correct behaviour of a closed "
        "chain and is not what a pathway in a cell does -- compose an "
        "inflow and an outflow to ask that question"
    )
    return Recognition(
        composition, "linear_metabolic_pathway", f"{count} reversible segments"
    )


def _branch_point(query: str, name: str) -> Recognition:
    """One metabolite, two enzymes, and the split that follows from their Km.

    The overlap with `_competition` is real and is not hidden: two catalytic
    steps sharing a substrate is the same network, and `library_metabolic`
    says so about its own motif. What this adds is named product ports and a
    basis about flux partitioning; what `_competition` adds is a step count.
    They are ranked so that a query saying "competing" gets the older rule
    and a query saying "branch point" gets this one, because those are the
    words each was written for.

    "branched pathway" is a substring of "unbranched pathway", which is what
    somebody writes when they mean a LINEAR one. `metabolic_pathway` (64)
    therefore outranks this rule (63), and "an unbranched pathway of four
    steps" builds a chain.
    """
    composition = Composition(name)
    motif = _expansion_motif(
        query, "library_metabolic", ("BRANCH_POINT",), shape="branch point",
        instead=(
            "'two enzymes competing for the same substrate' builds the same "
            "network from the core library, with unnamed products and no "
            "basis about how the flux divides."
        ),
    )
    composition.add(motif, "branch")
    composition.note(
        "one metabolite drawn on by two enzymes with different kinetics. "
        "The split is not a parameter: it falls out of the two rate laws at "
        "whatever substrate concentration the system is at, which is why "
        "the ratio changes as the branch point fills"
    )
    composition.note(
        "at low substrate the enzyme with the lower Km takes most of the "
        "flux and at high substrate the one with the higher kcat catches "
        "up, so a branch that is committed one way under starvation can run "
        "the other way when fed. A model that wrote the split as a fixed "
        "fraction would lose exactly that, and would still simulate"
    )
    composition.note(
        "nothing here claims either branch is regulated. Real branch points "
        "usually are -- an end product inhibiting its own branch is the "
        "commonest arrangement -- and adding that means saying which "
        "product inhibits which enzyme, which is a fact about the pathway "
        "rather than about the words"
    )
    return Recognition(composition, "branch_point", "one substrate, two fates")


def _moiety_cycle(query: str, name: str) -> Recognition:
    """A conserved cofactor pool, or a step that spends one.

    Two branches because they answer two questions. The CYCLE is the pool
    itself -- regeneration against demand, with the ratio settling where the
    two arms balance -- and is what somebody asking about energy charge or
    the NAD+/NADH ratio means. The COUPLED STEP is one reaction that cannot
    proceed without spending from such a pool, and is what somebody asking
    how a reaction is driven means.

    The thing neither branch has is a pool TOTAL. The total is the sum of
    two initial concentrations, both of them CHOSEN -- no paper reports how
    much NAD is in your model -- and a `C_total` parameter would be a lumped
    scenario quantity that could contradict the initials it duplicates. What
    controls a coupled step is the RATIO, and the ratio is set by the two
    arms rather than by the total.
    """
    composition = Composition(name)

    if _has(query, "cofactor coupled", "cofactor-coupled", "spends",
            "spending", "consumes", "consuming", "coupled step",
            "driven by a cofactor"):
        motif = _expansion_motif(
            query, "library_metabolic", ("COFACTOR_COUPLED_STEP",),
            shape="cofactor-coupled step",
            instead=(
                "'an ordered bi-bi mechanism' builds a two-substrate enzyme "
                "from the core library. It has two substrates and two "
                "products but no conserved pool, so it cannot express the "
                "spent cofactor coming back."
            ),
        )
        composition.add(motif, "step")
        composition.note(
            "the reaction consumes the active form of a cofactor and "
            "returns the spent form, so the two are linked by the "
            "stoichiometry and the network derives the conservation law "
            "from it. Writing the cofactor as a constant instead would let "
            "the step run forever on a pool that never empties"
        )
        composition.note(
            "no regeneration arm is included here. On its own this step "
            "runs the pool down and stops, which is the honest behaviour of "
            "an uncoupled demand -- compose it with a moiety-conserved "
            "cycle to close the loop"
        )
        return Recognition(
            composition, "cofactor_coupled_step", "a step spending a conserved cofactor"
        )

    motif = _expansion_motif(
        query, "library_metabolic", ("MOIETY_CONSERVED_CYCLE",),
        shape="moiety-conserved cycle",
        instead=(
            "'a futile cycle' from library_enzymology is two opposing "
            "enzymes on one pool and is the same algebra. It is written "
            "about a protein being modified and back, not about a cofactor "
            "being spent and regenerated, and its basis says the former."
        ),
    )
    composition.add(motif, "pool")
    composition.note(
        "a cofactor pool cycling between an active and a spent form, with "
        "one enzyme regenerating and one spending. The total is conserved "
        "and the network derives that from the stoichiometry -- it is not a "
        "parameter here, and must not become one"
    )
    composition.note(
        "the quantity that matters downstream is the RATIO of the two "
        "forms, not the total. Doubling the pool at a fixed ratio does not "
        "double the flux through a step that is saturated in its cofactor, "
        "so a model tuned by raising the total has changed something other "
        "than what it meant to"
    )
    composition.note(
        "the two initial amounts are the pool total and are CHOSEN, not "
        "resolvable: no paper reports how much adenine nucleotide is in "
        "your model. Nothing here attaches a citation to either"
    )
    return Recognition(
        composition, "moiety_conserved_cycle", "a conserved cofactor pool"
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
    # 89, and it has to be above `gene_expression` (85). The feed-forward
    # loops were catalogued in TRANSCRIPTION networks, so "an incoherent
    # feed-forward loop in a transcription network" is an ordinary way to
    # ask for one -- and the word "transcription" in it would otherwise
    # hand the query to the two-stage gene model, which has no loop in it
    # at all. None of these triggers is a bare "feed": `open_system` owns
    # "continuous feed", and "feedback" contains it too.
    Rule("feedforward_loop", (), ("feedforward", "feed-forward", "feed forward",
                                  "ffl"),
         _feedforward_loop,
         "a three-node feed-forward loop, coherent or incoherent", 89),
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
    # 67. "phosphorelay" is NOT a trigger even though a two-component system
    # is one: `phosphorylation_cascade` (90) already owns that word, and
    # taking it would need this rule above 90 and would change what an
    # existing query builds. "histidine kinase" and "response regulator"
    # name this mechanism and nothing else.
    Rule("two_component_system", (), ("two-component", "two component system",
                                      "histidine kinase", "response regulator",
                                      "sensor kinase", "phosphotransfer"),
         _two_component_system,
         "a sensor kinase handing a phosphoryl group to a regulator", 67),
    # 66, above `binding` (60), which triggers on "receptor" and would
    # otherwise take every GPCR query. "g protein" with a SPACE is not a
    # trigger: it is a substring of "binding protein", and "a ligand
    # binding protein" must keep reaching `binding`.
    Rule("gpcr_cycle", (), ("gpcr", "g-protein", "g protein coupled",
                            "heterotrimeric", "gtpase cycle",
                            "guanine nucleotide exchange"),
         _gpcr_cycle,
         "an agonist-occupied receptor driving a G protein cycle", 66),
    # 65, BELOW `futile_cycle` (79) on purpose. The two shapes overlap --
    # zero-order ultrasensitivity is what a futile cycle buys -- and a
    # query that says "futile cycle" or "kinase and phosphatase" should
    # keep reaching the rule written for those words. Never a bare "cycle":
    # the catalogue owns the cell cycle.
    Rule("ultrasensitive_cycle", (), ("ultrasensitiv", "zero order cycle",
                                      "zero-order cycle", "goldbeter",
                                      "phosphorylation cycle",
                                      "covalent modification cycle"),
         _ultrasensitive_cycle,
         "a covalent modification cycle, sharp when both arms saturate", 65),
    # 64, and it must outrank `branch_point` (63): "branched pathway" is a
    # substring of "unbranched pathway", so an unbranched query matches
    # both rules and this one has to win it.
    Rule("metabolic_pathway", (), ("linear pathway", "metabolic pathway",
                                   "unbranched pathway", "pathway segment",
                                   "steps in series", "reversible steps"),
         _metabolic_pathway,
         "N reversible segments in series, none able to run uphill", 64),
    Rule("branch_point", (), ("branch point", "branch-point", "branchpoint",
                              "branched pathway", "branches into",
                              "flux split", "two branches"),
         _branch_point, "one metabolite drawn on by two enzymes", 63),
    # 62. Never a bare "atp": `transport` (76) owns "atpase" and
    # "atp-driven", and a pump query must keep reaching it.
    Rule("moiety_cycle", (), ("moiety", "conserved pool", "cofactor cycle",
                              "cofactor regeneration", "cofactor coupled",
                              "cofactor-coupled", "spends a cofactor",
                              "consumes a cofactor", "atp/adp", "adp/atp",
                              "nad+/nadh", "nadh/nad", "adenylate pool",
                              "energy charge"),
         _moiety_cycle,
         "a conserved cofactor pool, or a step that spends one", 62),
    # 61, above `binding` (60): "a scaffold protein and the binding of two
    # kinases" matches both, and the scaffold is what the query is about.
    Rule("scaffold_assembly", (), ("scaffold",), _scaffold_assembly,
         "a scaffold whose activity has an optimum, not a maximum", 61),
    Rule("binding", (), ("reversible binding", "binds to", "binding of",
                         "association", "ligand", "receptor", "dimeris",
                         "dimeriz"), _binding,
         "two partners forming a complex", 60),
    # 59. "transcriptional oscillator" is NOT a trigger: "transcription" is
    # a substring of "transcriptional", so `gene_expression` (85) takes the
    # phrase before this rule is ever a candidate. And no bare "oscillator"
    # -- "cell cycle oscillator dynamics" belongs to the catalogue and this
    # path must keep matching nothing for it.
    Rule("signalling_oscillator", (), ("negative feedback oscillator",
                                       "delayed negative feedback",
                                       "goodwin oscillator", "goodwin model"),
         _negative_feedback_oscillator,
         "a delayed negative feedback loop, the general form of a clock", 59),
    # 58, below `toggle_switch` (86), which owns "bistable switch". "a
    # bistable switch between two repressors" is two genes repressing each
    # other and must keep reaching that rule; this one is the ONE-species
    # loop.
    Rule("bistable_feedback", (), ("bistable", "bistability",
                                   "positive feedback loop"),
         _bistable_positive_feedback,
         "one species driving its own production, with two stable levels", 58),
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
