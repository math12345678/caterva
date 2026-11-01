"""
enzyme_preparation.py

Was this constant measured on the enzyme, or on a *preparation* of it?

WHY THIS EXISTS
---------------
`docs/commentary-residue-baseline.txt` — the record of BRENDA commentary
Caterva cannot read — carries one group marked **OPEN FINDING**:

    acrylodan
    attachment polyethylene glycol side chains lysine residues does not
        alter Kcat
    benzyl
    competitive versus His tagged
    immobiized
    noncompetitive versus pyruvate His tagged
    soluble

Covalent modification, affinity tags and immobilisation change kinetics, and
none of them is a sequence change — so ADR 0029's variant filter does not
see them. Measured across the corpus: **18 rows** carry such a marker, and
ADR 0029 classifies every one of them `unstated`, which is to say eligible
for selection as ordinary enzyme.

IT IS NOT HYPOTHETICAL
----------------------
Through the real resolver, for human LDH:

    resolve_kinetic_value("1.1.1.27", "Homo sapiens", "NADH", quantity="ki")
      -> value 0.00059
      -> citation notes: None
      -> search log: "BRENDA exact: 1.1.1.27, Homo sapiens, NADH (ki)"

That row's commentary reads *"competitive versus NADH, pH 7.5, 37°C,
**recombinant His-tagged enzyme**"*. Caterva returns a His-tagged enzyme's
inhibition constant as the human LDH inhibition constant, and nothing
anywhere says so. The fact is parsed — it sits in `conditions` — and never
reaches the reader. The same "computed and not delivered" shape as ADR 0027
and ADR 0038, on a fact about what the number measures.

THIS IS ADR 0029 ONE CATEGORY OVER
----------------------------------
ADR 0029: *a mutant's constant is not the enzyme's*. Equally, an immobilised
enzyme's is not a free enzyme's — immobilisation imposes diffusional
limitation and altered microenvironment; a PEGylated enzyme's is not an
unmodified one's; and a His-tagged construct is not the native protein,
however often the tag is assumed innocuous.

And it is Jeske's point in her own words: *"Reaction conditions: pH value,
temperature, cofactors, and buffers play a huge role in the reactions… If
you simply mix these together, the simulation will end up calculating with
'fantasy numbers'."* Preparation belongs in that list.

WHAT "RECOMBINANT" IS NOT
-------------------------
`recombinant` alone is **not** a modification and is deliberately not
matched. Recombinant expression is how most enzyme is produced; the protein
is the protein. Only the *tag* changes it, which is why
`"recombinant His-tagged enzyme"` classifies as `tagged` and
`"recombinant enzyme"` as `unstated`.

Getting that wrong in either direction is costly. Treating every
`recombinant` row as modified would exclude most of the corpus and train a
reader to ignore the warning (ADR 0028's cry-wolf reasoning). Treating a
His-tagged row as native is the defect above.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

#: Immobilisation. `immobiized` is BRENDA's own typo, present in the LDH
#: turnover fixture; it is matched because the corpus contains it, not to be
#: charitable about spelling.
_IMMOBILISED_RE = re.compile(
    r"\bimmobi(?:li[sz]|iz)ed\b|\bimmobilisation\b|\bimmobilization\b"
    r"|\bcross[- ]?linked\s+(?:enzyme|crystal)",
    re.IGNORECASE,
)

#: Affinity tags and fusion constructs. The tag is a peptide the native
#: protein does not have.
_TAGGED_RE = re.compile(
    r"\bhis[- ]?tag(?:ged)?\b|\b(?:6x|hexa)[- ]?his\b|\bgst[- ]?(?:tag|fusion)"
    r"|\bmbp[- ]?fusion\b|\bstrep[- ]?tag\b|\bflag[- ]?tag\b"
    r"|\bfusion\s+protein\b",
    re.IGNORECASE,
)

#: Covalent modification of the protein itself.
_MODIFIED_RE = re.compile(
    r"\bpegylat(?:ed|ion)\b|\bpolyethylene\s+glycol\b|\bacrylodan\b"
    r"|\bbiotinylat(?:ed|ion)\b|\bconjugat(?:ed|e)\s+(?:to|with)\b"
    r"|\bchemically\s+modified\b|\bcarbamylat(?:ed|ion)\b"
    r"|\bglycosylat(?:ed|ion)\b",
    re.IGNORECASE,
)

#: An explicit statement that the enzyme was NOT modified. Worth its own
#: state for the reason ADR 0029 separates `wild_type` from `unstated`: a
#: curator saying "native enzyme" is strictly more informative than silence.
_NATIVE_RE = re.compile(
    r"\bnative\s+enzyme\b|\bfree\s+enzyme\b|\bsoluble\s+enzyme\b"
    r"|\bunmodified\b|\buntagged\b",
    re.IGNORECASE,
)


#: The curator saying the modification made no difference to a named
#: quantity: "attachment of polyethylene glycol side chains to lysine
#: residues does not alter the Km value".
#:
#: QUANTITY-SPECIFIC, and that is the whole point. The AChE fixture carries
#: this clause twice on the same PEGylation -- once for Km, once for Kcat --
#: which means the statement is about a measurement, not about the protein.
#: A row saying "does not alter the Km value" says nothing about its Ki.
_NO_EFFECT_RE = re.compile(
    r"does not (?:alter|affect|change)\s+(?:the\s+)?(\w+)", re.IGNORECASE
)


class PreparationVerdict(BaseModel):
    """How the enzyme was prepared, and the words that decided it.

    FIVE STATES, NOT TWO. `unstated` and `native` are different facts: the
    first is silence, the second is a curator saying the enzyme was free and
    unmodified. Collapsing them would let "we were not told" read as "it was
    the plain enzyme" — the inversion this project has found more often than
    any other defect.
    """

    #: "native" | "immobilised" | "tagged" | "modified" | "unstated" | "absent"
    status: str
    #: The substring that decided it. A verdict nobody can check is a verdict
    #: nobody can argue with.
    evidence: str | None = None

    #: The quantity the curator explicitly says the preparation did NOT
    #: change, upper-cased ("KM", "KCAT"), or None.
    #:
    #: Kept SEPARATE from `status` rather than collapsed into it. Two facts:
    #: the enzyme was modified, and the curator states the modification did
    #: not move this particular number. Folding them together would lose the
    #: first, and the first is what a reader needs to judge the second.
    stated_not_to_affect: str | None = None

    @property
    def is_as_isolated(self) -> bool:
        """True only for `native`.

        A POSITIVE test, deliberately — `status != "modified"` would return
        True for `unstated`, `absent`, `tagged` and `immobilised` alike, and
        the whole point is that silence is not a clean bill of health. The
        same reasoning as `protein_variant.is_wild_type`.
        """
        return self.status == "native"

    def differs_for(self, quantity: str | None) -> bool:
        """Whether this preparation should worry a reader resolving
        `quantity`.

        False when the commentary explicitly says the preparation did not
        alter THIS quantity. That exception is narrow on purpose: the clause
        names one measurement, and the same PEGylated AChE row carries it
        for Km in one table and Kcat in another. Treating it as a general
        "this modification is harmless" would read a statement about one
        number as a statement about the protein.
        """
        if not self.differs_from_the_free_enzyme:
            return False
        if quantity and self.stated_not_to_affect:
            return self.stated_not_to_affect.upper() != quantity.upper()
        return True

    @property
    def differs_from_the_free_enzyme(self) -> bool:
        """True when the commentary says the protein was altered or fixed.

        `unstated` is False here and False for `is_as_isolated` too: not a
        contradiction, an admission. Neither question was answered.
        """
        return self.status in {"immobilised", "tagged", "modified"}


def classify(commentary: str | None) -> PreparationVerdict:
    """Read a BRENDA commentary for how the enzyme was prepared.

    Order matters where a row carries more than one marker. Immobilisation
    is checked first because it dominates the kinetics it touches: an
    immobilised His-tagged enzyme is reported as immobilised, and the
    evidence string keeps the word that decided it so a reader can see why.
    """
    if commentary is None or not commentary.strip():
        # `absent` is not `unstated`. There is a difference between a
        # curator who wrote nothing about preparation in a full commentary
        # and a row with no commentary at all.
        return PreparationVerdict(status="absent")

    no_effect = _NO_EFFECT_RE.search(commentary)
    unaffected = no_effect.group(1).upper() if no_effect else None

    for status, pattern in (
        ("immobilised", _IMMOBILISED_RE),
        ("tagged", _TAGGED_RE),
        ("modified", _MODIFIED_RE),
        ("native", _NATIVE_RE),
    ):
        match = pattern.search(commentary)
        if match:
            return PreparationVerdict(
                status=status,
                evidence=match.group(0),
                stated_not_to_affect=unaffected,
            )

    return PreparationVerdict(status="unstated")


def describe(verdict: PreparationVerdict, quantity: str | None = None) -> str | None:
    """A sentence for the search log, or None when there is nothing to say.

    Returns None for `unstated` and `absent` on purpose. A line reading
    "preparation not stated" on every row in the corpus is noise, and noise
    is how the lines that matter stop being read.
    """
    if not verdict.differs_for(quantity):
        # Either nothing was altered, or the curator states the alteration
        # did not move THIS quantity. The second is a real fact from the
        # source and is why the AChE golden tuple G2 (Km 0.09, a PEGylated
        # row) is legitimate rather than a defect: the commentary says
        # "does not alter the Km value".
        return None

    what = {
        "immobilised": (
            "measured on an IMMOBILISED enzyme, which imposes diffusional "
            "limitation and an altered microenvironment"
        ),
        "tagged": (
            "measured on a TAGGED construct, which carries peptide the "
            "native protein does not. Whether that matters depends on WHERE "
            "the tag sits, and BRENDA's commentary does not say: Miskovic "
            "et al. (2024) put the same His-tag on both termini of one "
            "enzyme and found the C-terminal tag had negligible effect "
            "while the N-terminal tag reduced activity -- though it "
            "preserved substrate affinity "
            "(Int J Mol Sci 25(14), 7613; doi:10.3390/ijms25147613)"
        ),
        "modified": (
            "measured on a COVALENTLY MODIFIED enzyme"
        ),
    }[verdict.status]

    return (
        f"This value was {what} "
        f"(commentary: {verdict.evidence!r}). It is a real, correctly cited "
        "measurement of a preparation of the enzyme, and not of the free "
        "enzyme."
    )
