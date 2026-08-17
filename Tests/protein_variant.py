"""
protein_variant.py

Is this row a measurement of the enzyme, or of a variant of it?

WHY THIS EXISTS
---------------
BRENDA's commentary cell carries more than assay conditions. In this
repository's own acetylcholinesterase turnover fixture, the distinct
commentaries include:

    "pH 8.0, 30°C, native enzyme"
    "wild-type enzyme"
    "Y124C mutant"
    "F295A/Y337A mutant, pH 7, 22°C"
    "pH 7.0, 25°C, mutant G122H/Y124Q/S125T"
    "pH 8.5, 25°C, isozyme H4"

ADR 0010 taught the parser to mine that string for pH, temperature and
buffer. Everything else in it was discarded -- including the part that says
the number was measured on a **different protein**.

The scale of it: 35 of 72 rows in that fixture are point mutants. The
resolver selects `min(entries, key=km_value)`, and the lowest mutant kcat in
the pool is 0.017 against 0.2 for the lowest wild-type -- twelve times
lower. Active-site substitutions land at the extremes of the distribution,
which is precisely where a minimum-selection reaches.

It is luck, not design, that today's fixtures do not select a mutant. With
half the pool mutant and the tie-break pointed at the tail, one BRENDA
update separates this from returning a point mutant's constant as the
enzyme's, with a real citation attached.

THIS IS THE CROSS-SPECIES PROBLEM AGAIN
---------------------------------------
Lisa Jeske's objection to cross-species substitution was that the value is a
real, correctly parsed, correctly cited measurement *of something else*. A
Y337A mutant is a different protein from wild-type acetylcholinesterase in
exactly that sense -- and a sharper one than a rabbit standing in for a
human, because the substitution is usually chosen *because* it changes the
kinetics.

ADR 0024 made cross-species opt-in. This applies the same rule to the same
failure: a variant measurement is withheld by default, the refusal names
what it withheld, and an opt-in exists for the user who wants it.

WHY A LEXICON HERE IS NOT A HARDCODED FACT
------------------------------------------
This module matches "mutant", "wild-type", "isozyme", and the point-mutation
form `Y337A`. That is reading BRENDA's own controlled vocabulary and the
standard one-letter substitution notation, not asserting anything about
chemistry or kinetics. The distinction matters: `buffer_identity.py` goes to
PubChem because "Tris-HCl and Tris are one buffer" is a CLAIM ABOUT THE
WORLD that needs a source. "The word 'mutant' means this row is a mutant" is
a claim about English and about BRENDA's writing conventions, and the source
is the corpus above.

Where the lexicon is genuinely a limit, it is stated: see UNSTATED below.

FOUR STATES, AND `unstated` IS THE DANGEROUS ONE
------------------------------------------------
    wild_type   the commentary says so
    variant     mutant, or a point-substitution code, or a named isozyme
    unstated    the commentary says nothing either way
    absent      there is no commentary at all

`unstated` is the majority case and it is NOT wild-type. BRENDA does not
require curators to write "wild-type" when the paper measured wild-type, so
silence is genuinely ambiguous -- and treating silence as wild-type would
quietly re-admit every unlabelled mutant row. Treating it as variant would
withhold most of the corpus.

So `unstated` is neither: it does not block selection, and it does not
certify the row. What it does is refuse to claim the row was wild-type,
which is the only honest thing available and is why the caller gets the
state rather than a boolean.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

#: BRENDA writes the mutation before or after the word: "Y124C mutant" and
#: "mutant G122H/Y124Q/S125T" both occur in the same table.
_MUTANT_WORD_RE = re.compile(r"\bmutants?\b", re.IGNORECASE)

#: Standard one-letter substitution notation: wild-type residue, position,
#: replacement residue. "Y337A", "G122H". Multiples are slash-joined.
#:
#: Anchored on word boundaries and requiring 1-4 position digits so it does
#: not fire on things like "H4" (an isozyme name, 1 digit and no trailing
#: residue) or arbitrary capitalised tokens. The residue letters are
#: restricted to the twenty proteinogenic one-letter codes -- without that,
#: "B12" or "X99Y" would match.
_AA = "ACDEFGHIKLMNPQRSTVWY"
#: The `(?:...)+` handles double mutants written WITHOUT a separator.
#: BRENDA contains "D38SC81S" -- two substitutions concatenated -- and the
#: single-code form missed it entirely, because `\b` requires a boundary
#: between S and C and there is none. A row that says it is a double mutant,
#: classified as unstated.
#:
#: Found by scripts/check_commentary_coverage.py, which reported
#: "D38SC81S activated fructose 1 6 diphosphate" as unread text. The
#: mutation-testing pass on this module had not caught it: every mutation
#: asked whether the regex could be BROKEN, and none asked what it never
#: matched in the first place.
_POINT_MUTATION_RE = re.compile(rf"\b(?:[{_AA}]\d{{1,4}}[{_AA}])+\b")

#: "wild-type", "wild type", "wildtype", "native enzyme".
#:
#: "native" ALONE is not enough -- BRENDA also writes "native gel" and
#: "native conformation", neither of which says anything about sequence. The
#: corpus form is "native enzyme", so that is what is matched.
_WILD_TYPE_RE = re.compile(
    r"\bwild[\s-]?type\b|\bnative\s+enzyme\b",
    re.IGNORECASE,
)

#: A named isozyme or isoform: "isozyme H4", "isoform 2".
#:
#: An isozyme is not a mutant -- it is a distinct gene product, wild-type in
#: its own right. It is grouped with `variant` anyway, because LDH's H4 and
#: M4 isozymes have genuinely different kinetics and a user asking for
#: "lactate dehydrogenase" did not ask for one of them specifically. The
#: verdict carries `kind` so the two are distinguishable downstream.
_ISOZYME_RE = re.compile(r"\b(?:iso(?:zyme|form|enzyme))\s*[A-Za-z0-9-]*", re.IGNORECASE)

#: Recombinant expression is NOT a variant.
#:
#: A recombinant wild-type enzyme is the same protein sequence expressed in a
#: different host. It can differ in glycosylation and folding, which is worth
#: knowing, but it is not a sequence change and calling it one would withhold
#: a large and legitimate part of the corpus. Recorded on the verdict as a
#: note rather than acted on.
_RECOMBINANT_RE = re.compile(r"\brecombinant\b", re.IGNORECASE)


class VariantVerdict(BaseModel):
    """What the commentary says about the protein this row measured."""

    #: "wild_type" | "variant" | "unstated" | "absent"
    status: str

    #: For status="variant": "mutant" | "isozyme". None otherwise.
    kind: str | None = None

    #: The exact substring that decided it. Present for every non-`unstated`
    #: verdict so a reader can check the classifier rather than trust it --
    #: a verdict with no evidence is an assertion.
    evidence: str | None = None

    #: True when the commentary says the enzyme was recombinantly expressed.
    #: Reported, never acted on: see _RECOMBINANT_RE.
    recombinant: bool = False

    reason: str

    @property
    def is_wild_type(self) -> bool:
        """True ONLY when the commentary said so.

        Deliberately not `status != "variant"`. `unstated` is the majority
        case, and with the negative form every unlabelled row would certify
        itself as wild-type -- which is exactly the silent re-admission this
        module exists to prevent.
        """
        return self.status == "wild_type"


def classify(commentary: str | None) -> VariantVerdict:
    """Classify one BRENDA commentary cell.

    Order matters. An explicit mutation code beats the word "wild-type",
    because BRENDA writes commentaries like "Y124C mutant of the wild-type
    enzyme" where both appear and the row is a mutant.
    """
    if commentary is None or not commentary.strip():
        return VariantVerdict(
            status="absent",
            reason=(
                "BRENDA reported no commentary for this row, so nothing is "
                "known about which protein was measured."
            ),
        )

    text = commentary.strip()
    recombinant = bool(_RECOMBINANT_RE.search(text))

    point = _POINT_MUTATION_RE.search(text)
    word = _MUTANT_WORD_RE.search(text)
    if point or word:
        evidence = (point or word).group(0)
        return VariantVerdict(
            status="variant",
            kind="mutant",
            evidence=evidence,
            recombinant=recombinant,
            reason=(
                f"The commentary says {evidence!r}: this value was measured "
                "on a sequence variant, not on the enzyme as found. "
                "Substitutions are usually chosen because they change the "
                "kinetics, so this number is not a property of the "
                "wild-type enzyme."
            ),
        )

    iso = _ISOZYME_RE.search(text)
    if iso:
        evidence = iso.group(0).strip()
        return VariantVerdict(
            status="variant",
            kind="isozyme",
            evidence=evidence,
            recombinant=recombinant,
            reason=(
                f"The commentary names {evidence!r}. An isozyme is a distinct "
                "gene product, wild-type in its own right, with kinetics that "
                "can differ substantially from the other isozymes of the same "
                "enzyme. A request for the enzyme did not ask for this one."
            ),
        )

    wild = _WILD_TYPE_RE.search(text)
    if wild:
        return VariantVerdict(
            status="wild_type",
            evidence=wild.group(0),
            recombinant=recombinant,
            reason=(
                f"The commentary says {wild.group(0)!r}: this value was "
                "measured on the enzyme as found."
            ),
        )

    return VariantVerdict(
        status="unstated",
        recombinant=recombinant,
        reason=(
            "The commentary does not say whether this row measured the "
            "wild-type enzyme or a variant. BRENDA does not require curators "
            "to state it, so silence is ambiguous -- this is NOT a finding "
            "that the row is wild-type."
        ),
    )
