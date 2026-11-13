"""Find the enzyme a name means, rank what matches, and refuse to guess.

WHY THIS EXISTS
---------------
A name is not an enzyme. "lactate dehydrogenase" is EC 1.1.1.27 (L-lactate
dehydrogenase) and EC 1.1.1.28 (D-lactate dehydrogenase), and a wrong EC
number is a correctly formatted citation for the wrong protein. Refusing to
choose is right. Refusing without saying what the choices are was the
defect: the old lookup returned six bare EC numbers, in an order that put two
protein kinases that merely mention pyruvate kinase among them, and nothing
anywhere named an enzyme.

This module looks the name up in the IUBMB nomenclature (the ExPASy ENZYME
index, see index.py), ranks every enzyme whose NAME matches, says in plain
words why each one matched, and resolves only when the answer is not a
choice. Offline, deterministic, no network.

HOW MATCHES ARE RANKED
----------------------
Each enzyme is placed in the best tier any of its names reaches. A lower tier
number is a stronger match:

    0  you gave an EC number (or a class like 1.1.1.-)
    1  the accepted name equals your query
    2  another name for the enzyme equals your query, OR the curated
       gene-symbol and abbreviation table (symbols.py) lists your query for
       it (HK2 for hexokinase, ACHE for acetylcholinesterase, HIV protease
       for HIV-1 retropepsin). Table readings come first, in the table's order
    3  the accepted name equals your query once stereo labels (L-, D-, (S)-,
       (R)-, (+)-), charge marks, Greek letters and a parenthesised
       alternative word glued to a word ("glycogen(starch) synthase") are set
       aside
    4  the same, for another name for the enzyme
    5  your query is a phrase inside the accepted name, on word boundaries
    6  your query is a phrase inside another name
    7  every word of your query is in one name, in any order, with at least
       two real words in the query
       (tiers 5 to 7 are fragments of a longer name: listed, never resolved
       to on their own)
    8  your query is the UniProt entry-name MNEMONIC of the requested
       organism's own entry (ACES_HUMAN is mnemonic ACES), and the table does
       not know the symbol. Listed, never resolved, never recommended: a
       mnemonic is not a gene symbol
    9  a typo-tolerant match, offered only when nothing above matched, and
       only ever as a suggestion

"Equals" ignores case, punctuation, hyphens and spacing. Only names are
searched: the index holds no comments, so an enzyme mentioned in the comment
of another, or one whose only link to the query is a different enzyme's name,
cannot outrank one whose own name matches. A single-letter word, or a query of
three letters or fewer, must be a word of the name itself and not something
inside a parenthesis ("ribonuclease A" is not "poly(A)-specific
ribonuclease"). A typo is tolerated only in a word of six letters or more, never
in a word with a digit, never in a word that is itself a word of some enzyme
name ("ethanol" is not "methanol" mistyped).

Within a tier the order is fixed and can be explained to a reader: first,
when an organism was given and the index knows it, enzymes with a protein
from that organism; then the shorter accepted name; then the EC number in
numeric order. (Typo matches order by edit distance first.)

WHEN IT RESOLVES, AND WHEN IT NEVER DOES
----------------------------------------
`resolve` returns `Resolved` only when the answer is not a choice:

* an EC number that exists (a transferred one resolves to its replacement and
  says so);
* a unique accepted name, or a unique exact alternative name that is a full
  name ("lysozyme", "trypsin", "pyruvate kinase", "hexokinase", "lipase");
* an exact alternative name that is itself an abbreviation ("GAPDH", "ACE",
  "PKA", "PKC", "HDAC", "BACE1") only when the abbreviation table lists it
  for that enzyme and for no other.

It never resolves, and lists the candidates for the person to choose:

a. a short abbreviation or symbol, which is anything that is not an accepted
   name, an exact alternative name or an EC number (HK1, SDH, AK, ACHE, PEPC,
   COMT, SOD): it is what the table, or a name that spells it, says it can
   mean, and several enzymes go by most of them (HK is hexokinase and histidine
   kinase; AK is adenylate kinase, adenosine kinase and acetate kinase);
b. a UniProt entry-name mnemonic read as if it were a gene symbol: SYK_HUMAN is
   a lysine--tRNA ligase and the SYK gene is KSYK_HUMAN, so the part before the
   underscore is never treated as a symbol, and a mnemonic is listed only for
   the organism asked about;
c. an exact ALTERNATIVE name of an enzyme with no protein in the organism asked
   about, when another enzyme whose name also matches has one: human glycogen
   synthase is EC 2.4.1.11, not the bacterial starch synthase that lists the
   words as another name;
d. an abbreviation that is an exact alternative name of exactly one enzyme but
   that the table lists for others too (NOS is another name of D-nopaline
   dehydrogenase and means nitric-oxide synthase);
e. a one-word query that matches only once a stereo label is set aside, when
   other enzymes use the word as written: "protein" is not EC 1.8.1.4 because
   it lists 'L-protein', nor "peptidase" the viral L-peptidase;
f. an exact alternative name that is the family phrase of two or more other
   accepted names and is not in the enzyme's own: "protein kinase" is listed
   for histidine kinase and is the phrase in 'protein kinase C' and others.

A table reading is never organism-blind: a gene symbol is offered only for an
organism the table holds it for, because IDH1 is the NADP-dependent enzyme in
human and mouse (EC 1.1.1.42) and the NAD-dependent one in yeast (EC 1.1.1.41).

WHAT IS RECOMMENDED
-------------------
`recommended` is set across the WHOLE list of everything that matched, not the
best tier: an enzyme is recommended only when it is the only listed enzyme
with a protein from the organism asked about, something else is listed, and
it matched by name or EC number, never through an abbreviation, a gene symbol,
a mnemonic or a typo. ADH is therefore never recommended to be S-(hydroxymethyl)
glutathione dehydrogenase because it ranked first. A recommendation is a
pointer: nothing is picked, and a person confirms with one flag. A typo match
is never resolved, and a transferred EC number resolves to its replacement
with the transfer said in the result.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from .index import (
    ACTIVE, DELETED, TRANSFERRED, EnzymeEntry, EnzymeIndex, Protein,
    load_index, organism_code, organism_label, organism_scope,
)
from .symbols import ABBREVIATION, ALIAS, load_symbols

# Tier numbers; see the module docstring.
TIER_EC = 0
TIER_ACCEPTED_EXACT = 1
TIER_ALTERNATIVE_EXACT = 2
#: A gene symbol or lab abbreviation from the curated table (symbols.py):
#: the same strength as another name for the enzyme, and never resolved.
TIER_ABBREVIATION = 2
TIER_ACCEPTED_TOLERANT = 3
TIER_ALTERNATIVE_TOLERANT = 4
TIER_ACCEPTED_PHRASE = 5
TIER_ALTERNATIVE_PHRASE = 6
TIER_ALL_WORDS = 7
#: A UniProt entry-name mnemonic of the requested organism. Listed, never resolved.
TIER_SYMBOL = 8
TIER_TYPO = 9

DEFAULT_LIMIT = 12

# ---------------------------------------------------------------------------
# Reading what a person typed
# ---------------------------------------------------------------------------

_GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "ζ": "zeta", "η": "eta", "θ": "theta", "ι": "iota", "κ": "kappa",
    "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "π": "pi", "ρ": "rho",
    "σ": "sigma", "τ": "tau", "φ": "phi", "χ": "chi", "ψ": "psi", "ω": "omega",
}
_GREEK.update({k.upper(): v for k, v in list(_GREEK.items())})

#: Optical-rotation and charge marks: (+), (-), (±).
_SIGN_MARK = re.compile(r"\(\s*[+\-±]\s*\)")
#: CIP descriptors: (S), (2S), (R,R), (3S,4R).
_CIP_MARK = re.compile(r"\(\s*\d*[rs](?:\s*,\s*\d*[rs])*\s*\)")
#: Configuration prefixes written with a hyphen: l-, d-, dl-.
_CONFIG_PREFIX = re.compile(r"(?<![0-9a-z])(?:dl|ld|d|l)-")


def strict_key(text: str) -> str:
    """Case, punctuation, hyphens and spacing set aside, and a Greek letter
    read as its name; nothing else.

    "β-galactosidase" is "beta-galactosidase" written with the letter, not a
    near spelling of it: the letter used to survive this key, so the
    nomenclature's "beta-galactosidase" was met only at the tolerant tier
    and the sentence reader set it aside as a stereo-label match ("kinetics
    of β-galactosidase in E. coli" was refused with the grammar's list of
    shapes, 2026-11-11). A Greek letter is spelled out in every name the
    nomenclature and BRENDA list, so reading it as its name loses nothing.
    """
    folded = unicodedata.normalize("NFKC", text)
    for greek, name in _GREEK.items():
        folded = folded.replace(greek, name)
    folded = folded.lower()
    return " ".join(re.sub(r"[\W_]+", " ", folded).split())


def compact_name_key(text: str) -> str:
    """The strict key with its spaces removed: "butyrylcholine esterase" and
    "butyrylcholinesterase" are one name written two ways."""
    return strict_key(text).replace(" ", "")


def loose_key(text: str) -> str:
    """The strict key with stereo labels, charge marks and Greek letters set aside."""
    folded = unicodedata.normalize("NFKC", text)
    for greek, name in _GREEK.items():
        folded = folded.replace(greek, name)
    folded = folded.lower()
    folded = _SIGN_MARK.sub(" ", folded)
    folded = _CIP_MARK.sub(" ", folded)
    folded = _CONFIG_PREFIX.sub("", folded)
    return " ".join(re.findall(r"[0-9a-z]+", folded))


_EC_PREFIX = re.compile(r"^\s*e\.?\s?c\.?\s*[:#]?\s*", re.IGNORECASE)
_EC_BODY = re.compile(r"^\d+(?:\.(?:\d+|n\d+|-|\*))*\.?$", re.IGNORECASE)


def read_ec(query: str) -> Optional[Tuple[str, ...]]:
    """The EC parts a query gives, or None when it is not an EC number.

    `EC 1.1.1.27`, `E.C. 1.1.1.27` and `1.1.1.27` give ('1','1','1','27');
    `1.1.1.-` and `1.1.-.-` and `2.7.1` give the numbered levels only, which
    is a class of enzymes rather than one enzyme.
    """
    stripped = _EC_PREFIX.sub("", query, count=1)
    had_prefix = stripped != query
    text = stripped.strip()
    if not _EC_BODY.match(text) or ("." not in text and not had_prefix):
        return None
    parts: List[str] = []
    for part in text.rstrip(".").split("."):
        if part in ("-", "*"):
            break
        parts.append(part.lower())
    return tuple(parts) if parts else None


def _ec_key(ec: str) -> Tuple[Tuple[int, int], ...]:
    out = []
    for part in ec.split("."):
        if part.isdigit():
            out.append((0, int(part)))
        elif part.startswith("n") and part[1:].isdigit():
            out.append((1, int(part[1:])))
        else:
            out.append((2, 0))
    return tuple(out)


def _within(a: str, b: str, limit: int) -> Optional[int]:
    """Edit distance between a and b if it is at most `limit`, else None."""
    if abs(len(a) - len(b)) > limit:
        return None
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        low = i
        for j, cb in enumerate(b, 1):
            cost = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            current.append(cost)
            low = min(low, cost)
        if low > limit:
            return None
        previous = current
    return previous[-1] if previous[-1] <= limit else None


def _typo_limit(length: int) -> int:
    """Edits allowed for a query this long. None below six characters: a
    four-letter abbreviation is within one edit of unrelated abbreviations,
    and suggesting them would be noise."""
    if length < 6:
        return 0
    if length < 8:
        return 1
    if length < 15:
        return 2
    return 3


# ---------------------------------------------------------------------------
# What the finder returns
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """One enzyme that matched, and the reason it did."""

    ec: str
    name: str
    #: Plain English: why this enzyme is in the list.
    why: str
    #: Lower is stronger; see the module docstring.
    tier: int
    reaction: str
    class_path: str
    #: The alternative names that matched the query.
    alternative_names: Tuple[str, ...] = ()
    #: The requested organism's UniProt entries for this EC, when the index
    #: lists them (13 organisms). `organism_protein_count` can be larger.
    organism_proteins: Tuple[Protein, ...] = ()
    organism_protein_count: int = 0
    organism: Optional[str] = None
    status: str = ACTIVE
    superseded_by: Tuple[str, ...] = ()
    #: Edit distance, for a typo match; 0 otherwise.
    distance: int = 0
    #: For a typo match, how many words of the matched name lie outside the
    #: words the query was close to; 0 otherwise. "enolse" is one letter
    #: from 'enolase' (EC 4.2.1.11's own other name, nothing left over) and
    #: from the 'enolase' inside 'E-1 enolase-phosphatase' (EC 3.1.3.77,
    #: two words left over); the shorter accepted name used to win the tie
    #: and the refusal asked "Did you mean 'acireductone synthase'?" (fifth
    #: round of the real-values review). A whole name ranks first.
    spare: int = 0
    #: True when the query matched only a fragment of a longer name (a
    #: phrase or some words inside it) or an entry-name mnemonic. A fragment
    #: is shown but never resolved to: "LDH" is a word inside the name of an
    #: electron-bifurcating complex, and is not that enzyme.
    partial: bool = False
    #: How it matched: `name` (an enzyme name), `abbreviation` (the curated
    #: gene-symbol and abbreviation table), `mnemonic` (a UniProt entry name),
    #: `typo`, `ec` (an EC number given or its replacement) or `class`.
    via: str = "name"
    #: True when the name that matched is itself an abbreviation ("GAPDH",
    #: "RNase A", "HK2"): those are shared between enzymes and resolve only
    #: when the abbreviation table confirms them.
    abbreviation: bool = False
    #: True when the abbreviation table lists the abbreviation for this
    #: enzyme alone.
    confirmed: bool = False
    #: Position in the abbreviation table's own order (0 is the usual meaning).
    order: int = 0

    @property
    def has_organism_protein(self) -> bool:
        return self.organism_protein_count > 0

    def label(self) -> str:
        """`EC 1.1.1.27 L-lactate dehydrogenase (human: LDHA, LDHB, LDHC)`."""
        text = f"EC {self.ec} {self.name}".rstrip()
        if self.organism and self.organism_protein_count:
            text += f" ({_proteins_phrase(self)})"
        return text

    def to_dict(self) -> Dict[str, object]:
        return {
            "ec": self.ec,
            "name": self.name,
            "why": self.why,
            "tier": self.tier,
            "reaction": self.reaction,
            "class_path": self.class_path,
            "alternative_names": list(self.alternative_names),
            "organism": self.organism,
            "organism_proteins": [
                {"accession": p.accession, "entry_name": p.entry_name, "symbol": p.symbol,
                 "gene": p.gene, "label": p.label}
                for p in self.organism_proteins
            ],
            "organism_protein_count": self.organism_protein_count,
            "has_organism_protein": self.has_organism_protein,
            "status": self.status,
            "superseded_by": list(self.superseded_by),
            "partial_match": self.partial,
            "matched_by": self.via,
        }


def _proteins_phrase(candidate: Candidate, shown: int = 6) -> str:
    label = organism_label(candidate.organism or "")
    symbols = [p.label for p in candidate.organism_proteins]
    if not symbols:
        return f"{label}: {candidate.organism_protein_count} UniProt entries"
    text = ", ".join(symbols[:shown])
    if len(symbols) > shown:
        text += f", and {len(symbols) - shown} more"
    return f"{label}: {text}"


@dataclass(frozen=True)
class Resolved:
    """The name or number identifies exactly one enzyme."""

    ec: str
    #: How it was identified, in words. Says so plainly when a transferred
    #: EC number was replaced by its successor.
    how: str
    candidate: Optional[Candidate] = None
    #: Things the reader should know that do not change the answer: the
    #: enzyme has no protein from the requested organism, a number was
    #: transferred.
    cautions: Tuple[str, ...] = ()
    #: The protein of the EC number the name was (HK2 for "HK2", CYP2B6 for
    #: "CYP2B6"), for `--isoform`; None when the name is the whole enzyme.
    isoform: Optional[str] = None
    #: The organism (binomial) assumed because none was given and the name
    #: implies one: Homo sapiens for a human gene symbol, Human
    #: immunodeficiency virus 1 for HIV-1 protease. None when none was assumed.
    organism: Optional[str] = None
    #: Sentences saying what was assumed or read: the organism, the isoform,
    #: a spelling read as a name. Every automatic choice is one of these.
    notes: Tuple[str, ...] = ()
    #: True when the symbol table (a gene symbol, lab abbreviation or
    #: curated alias) read the name as this one enzyme in the organism. A
    #: sentence accepts such a reading whether or not an organism was given:
    #: "ACE2 in human" used to be dropped while "ACE2" alone was read.
    symbol_read: bool = False


@dataclass(frozen=True)
class Ambiguous:
    """The query names several enzymes, one that is only a suggestion, or none."""

    query: str
    candidates: Tuple[Candidate, ...]
    #: Set only when exactly one tied candidate has a protein from the
    #: requested organism and the others have none. Never chosen for you.
    recommended: Optional[Candidate] = None
    #: Why this is not a single answer.
    reason: str = ""
    #: True when the candidates are typo matches offered as "did you mean".
    suggestions_only: bool = False
    organism: Optional[str] = None
    release: str = ""
    #: True when the candidates are what an abbreviation or symbol can mean:
    #: they are offered for a person to confirm, even if there is only one.
    confirm_only: bool = False
    #: True when the query is a word for a kind of enzyme (rules e and f in
    #: `resolve`): the refusal gives no example EC number, because the first
    #: candidate is the misreading the rule exists to refuse.
    class_word: bool = False
    #: True for rule f: an exact other name of one enzyme that is also the
    #: family word of others' accepted names ("dihydroorotate
    #: dehydrogenase"). Unlike a bare class word, the organism can settle it
    #: when only one of the family lists its protein and has its rows.
    family: bool = False


Resolution = (Resolved, Ambiguous)


@dataclass(frozen=True)
class Isozymes:
    """An organism's UniProt entries for one EC number."""

    ec: str
    organism: Optional[str]
    proteins: Tuple[Protein, ...]
    #: The number of entries; can exceed len(proteins) for an organism the
    #: index keeps a count for and no list.
    count: int

    @property
    def symbols(self) -> Tuple[str, ...]:
        """The labels to show: the gene symbol where UniProt gives one, else the entry-name mnemonic."""
        return tuple(p.label for p in self.proteins)

    @property
    def mnemonics(self) -> Tuple[str, ...]:
        """UniProt entry-name mnemonics (HXK2), which are not gene symbols."""
        return tuple(p.symbol for p in self.proteins)


# ---------------------------------------------------------------------------
# The name tables, built once per index
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Name:
    ec: str
    accepted: bool
    text: str
    strict: str
    loose: str
    words: frozenset
    #: The words outside every parenthesis: "poly(A)-specific ribonuclease"
    #: has `poly`, `specific`, `ribonuclease` here, and `a` only in `words`.
    outside: frozenset
    #: The loose key with the parenthesised parts that are glued to a word set
    #: aside: "glycogen(starch) synthase" is "glycogen synthase" here. A
    #: qualifier set off by a space, "L-lactate dehydrogenase (cytochrome)",
    #: names another enzyme and is kept.
    bare: str
    #: The name is itself an abbreviation ("GAPDH", "RNase A", "HK2"): no
    #: run of four lower-case letters.
    abbreviation: bool


_PAREN = re.compile(r"\([^()]*\)")
_GLUED_PAREN = re.compile(r"(?<=\w)\([^()]*\)")
_WORD_RUN = re.compile(r"[a-z]{4,}")


def is_abbreviation(text: str) -> bool:
    """Whether a name is an abbreviation or symbol rather than words.

    True when it holds no run of four lower-case letters as written: "GAPDH",
    "HK2", "RNase A", "COX-2", "CYP2C9". "lipase", "pepsin" and "ATP
    synthase" are words. The test is on the NAME the nomenclature lists, not
    on how the query was typed, so "gapdh" and "GAPDH" are read alike."""
    return _WORD_RUN.search(text) is None


def _outside_parentheses(text: str) -> str:
    previous = None
    while previous != text:
        previous, text = text, _PAREN.sub(" ", text)
    return text


def _glued_aside(text: str) -> str:
    previous = None
    while previous != text:
        previous, text = text, _GLUED_PAREN.sub(" ", text)
    return text


class _Tables:
    def __init__(self, index: EnzymeIndex):
        self.names: List[_Name] = []
        #: Every word of every name: a word that is one of these is a word,
        #: not a misspelling of another ("ethanol" is not "methanol" mistyped).
        self.vocabulary: set = set()
        self.symbols: Dict[str, List[Tuple[str, str]]] = {}
        #: compact_name_key -> the names written that way once spaces are set aside.
        self.compact: Dict[str, List[_Name]] = {}
        for ec, entry in index.entries.items():
            if entry.status != ACTIVE or not entry.name:
                continue
            for accepted, text in [(True, entry.name)] + [(False, a) for a in entry.alternative_names]:
                loose = loose_key(text)
                self.vocabulary.update(loose.split())
                self.names.append(_Name(
                    ec, accepted, text, strict_key(text), loose, frozenset(loose.split()),
                    frozenset(loose_key(_outside_parentheses(text)).split()),
                    loose_key(_glued_aside(text)), is_abbreviation(text)))
                self.compact.setdefault(compact_name_key(text), []).append(self.names[-1])
            for proteins in entry.proteins.values():
                for protein in proteins:
                    self.symbols.setdefault(strict_key(protein.symbol), []).append((ec, protein.entry_name))


@lru_cache(maxsize=4)
def _tables(index: EnzymeIndex) -> _Tables:
    return _Tables(index)


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


def _candidate(
    index: EnzymeIndex, entry: EnzymeEntry, tier: int, why: str, code: Optional[str],
    matched: Sequence[str] = (), distance: int = 0, partial: bool = False,
    via: str = "name", abbreviation: bool = False, confirmed: bool = False, order: int = 0,
    spare: int = 0,
) -> Candidate:
    proteins, count = index.proteins_in(entry.ec, code)
    return Candidate(
        ec=entry.ec, name=entry.name, why=why, tier=tier, reaction=entry.reaction,
        class_path=index.class_path(entry.ec), alternative_names=tuple(matched),
        organism_proteins=proteins, organism_protein_count=count, organism=code,
        status=entry.status, superseded_by=entry.superseded_by, distance=distance, partial=partial,
        via=via, abbreviation=abbreviation, confirmed=confirmed, order=order, spare=spare,
    )


def _order(candidate: Candidate, organism_known: bool) -> tuple:
    return (
        candidate.tier,
        candidate.distance,
        candidate.spare,
        # Inside a tier the abbreviation table's own readings come first, in its order.
        0 if candidate.via == "abbreviation" else 1,
        candidate.order if candidate.via == "abbreviation" else 0,
        0 if (candidate.has_organism_protein or not organism_known) else 1,
        len(candidate.name),
        _ec_key(candidate.ec),
    )


def _by_ec(index: EnzymeIndex, query: str, parts: Tuple[str, ...], code: Optional[str]) -> List[Candidate]:
    """Candidates for an EC number or a class, following transfers."""
    out: List[Candidate] = []
    if len(parts) == 4:
        ec = ".".join(parts)
        entry = index.get(ec)
        if entry is None:
            return out
        seen = {ec}
        if entry.status == ACTIVE:
            return [_candidate(index, entry, TIER_EC, "you gave this EC number", code, via="ec")]
        if entry.status == DELETED:
            return [_candidate(index, entry, TIER_EC, "you gave this EC number, which the nomenclature has deleted",
                               code, via="ec")]
        out.append(_candidate(
            index, entry, TIER_EC,
            "you gave this EC number, which was transferred: " + "; ".join(
                f"EC {new}" for new in entry.superseded_by), code, via="ec"))
        frontier = list(entry.superseded_by)
        for _ in range(5):
            following: List[str] = []
            for new in frontier:
                if new in seen:
                    continue
                seen.add(new)
                target = index.get(new)
                if target is None:
                    continue
                if target.status == TRANSFERRED:
                    following.extend(target.superseded_by)
                elif target.status == ACTIVE:
                    out.append(_candidate(
                        index, target, TIER_EC,
                        f"replaces EC {ec}, which was transferred to it", code, via="ec"))
            frontier = following
        return out
    prefix = ".".join(parts)
    label = prefix + ".-" * (4 - len(parts))
    class_name = index.class_name(prefix)
    for ec, entry in index.entries.items():
        if entry.status == ACTIVE and (ec == prefix or ec.startswith(prefix + ".")):
            why = f"a member of EC {label}" + (f" ({class_name})" if class_name else "")
            out.append(_candidate(index, entry, TIER_EC, why, code, via="class"))
    return out


class _Hit:
    """The best reading of one enzyme while a query is being matched."""

    __slots__ = ("tier", "why", "alt", "partial", "via", "abbreviation", "confirmed", "order")

    def __init__(self, tier, why, alt, partial, via="name", abbreviation=False, confirmed=False, order=0):
        self.tier, self.why, self.alt, self.partial = tier, why, alt, partial
        self.via, self.abbreviation, self.confirmed, self.order = via, abbreviation, confirmed, order


def _typo_distance(q_tokens: Sequence[str], window: Sequence[str], limit: int, vocabulary: frozenset = frozenset(),
                   memo: Optional[Dict[Tuple[str, str], Optional[int]]] = None) -> Optional[int]:
    """Total edits between a query and a run of a name's words, or None.

    Only a word of six letters or more may carry an edit (`_typo_limit`), and
    a word with a digit never: "CYP2C9" is within one edit of other
    cytochromes' symbols and is not a misspelling of any of them, and in
    "HIV protease" the HIV is not what was mistyped. A word that is itself a
    word of some enzyme name is a word, not a typo ("ethanol" is not
    "methanol" mistyped). The words must pair up one to one.

    `memo` holds the per-word answers for one query: the same name words
    recur across thousands of names, and the typo tier runs over all of them,
    so without it one misspelling costs seconds (the studio's finder endpoint
    gives up after four)."""
    if len(q_tokens) != len(window):
        return None
    total = 0
    for q, w in zip(q_tokens, window):
        if q == w:
            continue
        key = (q, w)
        if memo is not None and key in memo:
            d = memo[key]
        else:
            per_word = _typo_limit(len(q))
            if not per_word or any(ch.isdigit() for ch in q + w) or q in vocabulary:
                d = None
            else:
                d = _within(q, w, per_word)
            if memo is not None:
                memo[key] = d
        if d is None:
            return None
        total += d
    return total if 0 < total <= limit else None


def _search(query: str, code: Optional[str], index: EnzymeIndex) -> List[Candidate]:
    """Every match, best first, with no limit applied."""
    text = " ".join(query.split())
    if not text:
        return []
    organism_known = code is not None
    parts = read_ec(text)
    if parts is not None:
        found = _by_ec(index, text, parts, code)
        # A full EC number keeps the order it was built in: the number
        # given, then what replaced it. A class is ordered like any tier.
        return found if len(parts) == 4 else sorted(found, key=lambda c: _order(c, organism_known))

    tables = _tables(index)
    q_strict = strict_key(text)
    q_loose = loose_key(text)
    q_words = frozenset(q_loose.split())
    best: Dict[str, _Hit] = {}

    def note(ec: str, tier: int, why: str, alt: Optional[str] = None, partial: bool = False,
             abbreviation: bool = False) -> None:
        held = best.get(ec)
        if held is None or tier < held.tier:
            best[ec] = _Hit(tier, why, [alt] if alt else [], partial, abbreviation=abbreviation)
        elif tier == held.tier:
            if alt and alt not in held.alt:
                held.alt.append(alt)
            held.partial = held.partial and partial
            held.abbreviation = held.abbreviation or abbreviation

    # A one-letter word, or a query of at most three letters, has to be a
    # word of the name itself and not something inside a parenthesis:
    # "ribonuclease A" is not "poly(A)-specific ribonuclease", and "PK" is
    # not the (PK) in a longer name.
    need_outside = frozenset(w for w in q_words if len(w) == 1)
    if len(q_words) == 1 and len(q_loose) <= 3:
        need_outside = q_words

    # A phrase inside a longer name, or words spread over one, is by
    # construction a fragment of that name. "angiotensin converting enzyme"
    # is the start of "angiotensin-converting enzyme 2", a different enzyme
    # from the one anybody means by it, and "PFK" is half of "ADP-PFK". So
    # these tiers are listed and ranked but never resolved to on their own.
    # Words spread over a name are evidence only when there are at least two
    # real words among them: "CA II" is not in "Ca(2+)/calmodulin-dependent
    # protein kinase II" because a "ca" and an "ii" are somewhere in it.
    enough_words = sum(1 for w in q_words if len(w) >= 3) >= 2
    phrase = f" {q_loose} "
    for name in tables.names:
        if name.strict == q_strict:
            if name.accepted:
                note(name.ec, TIER_ACCEPTED_EXACT, "accepted name matches exactly")
            else:
                note(name.ec, TIER_ALTERNATIVE_EXACT,
                     f"listed as another name for this enzyme: '{name.text}'", name.text,
                     abbreviation=name.abbreviation)
            continue
        if not q_loose:
            continue
        if name.loose == q_loose:
            if name.accepted:
                note(name.ec, TIER_ACCEPTED_TOLERANT,
                     "accepted name matches once stereo labels (L-, D-, (S)-) and Greek letters are set aside")
            else:
                note(name.ec, TIER_ALTERNATIVE_TOLERANT,
                     f"another name for this enzyme matches once stereo labels and Greek letters are set aside: '{name.text}'",
                     name.text, abbreviation=name.abbreviation)
        elif name.bare == q_loose and q_loose:
            if name.accepted:
                note(name.ec, TIER_ACCEPTED_TOLERANT,
                     "accepted name matches once a parenthesised alternative word in it is set aside")
            else:
                note(name.ec, TIER_ALTERNATIVE_TOLERANT,
                     f"another name for this enzyme matches once a parenthesised alternative word in it is set aside: '{name.text}'",
                     name.text, abbreviation=name.abbreviation)
        elif need_outside and not need_outside <= name.outside:
            continue
        elif phrase in f" {name.loose} ":
            if name.accepted:
                note(name.ec, TIER_ACCEPTED_PHRASE, "your query is a phrase inside the accepted name",
                     partial=True)
            else:
                note(name.ec, TIER_ALTERNATIVE_PHRASE,
                     f"your query is a phrase inside another name for this enzyme: '{name.text}'", name.text,
                     partial=True)
        elif q_words <= name.words and enough_words:
            if name.accepted:
                note(name.ec, TIER_ALL_WORDS, "every word of your query is in the accepted name", partial=True)
            else:
                note(name.ec, TIER_ALL_WORDS,
                     f"every word of your query is in another name for this enzyme: '{name.text}'", name.text,
                     partial=True)

    # The curated table of gene symbols and lab abbreviations (symbols.py).
    # Its readings are candidates and never resolve on their own, with one
    # exception made in `resolve`: an abbreviation that is also an exact
    # alternative name of one enzyme, which the table lists for that enzyme
    # alone, is confirmed twice over.
    table = load_symbols()
    table_hits = [h for h in table.lookup(text, code)
                  if h.ec in index.entries and index.entries[h.ec].status == ACTIVE]
    if table_hits:
        listed = {h.ec for h in table_hits}
        # An abbreviation row is independent of organism and is what can
        # confirm a name; a gene row is one organism's symbol and cannot.
        confirmers = {h.ec for h in table_hits if h.kind in (ABBREVIATION, ALIAS)}
        for ec, held in best.items():
            if held.tier == TIER_ALTERNATIVE_EXACT and held.abbreviation and ec not in listed:
                # The abbreviation table lists the query for other enzymes: this
                # enzyme's name that spells the same is a lesser reading of it.
                held.tier = TIER_ALTERNATIVE_PHRASE
                held.partial = True
                held.why = (f"another name for this enzyme is written '{held.alt[0]}', but the abbreviation "
                            f"table lists {text!r} for other enzymes")
        by_ec: Dict[str, list] = {}
        for hit in table_hits:
            by_ec.setdefault(hit.ec, []).append(hit)
        for ec, hits in by_ec.items():
            hit = hits[0]
            why = table.combine(hits)
            held = best.get(ec)
            if held is not None and held.tier == TIER_ALTERNATIVE_EXACT and held.abbreviation:
                held.confirmed = confirmers == {ec} and listed == {ec}
                held.order = hit.order
                held.why += f"; {why}"
            elif held is not None and held.tier < TIER_ABBREVIATION:
                continue
            else:
                best[ec] = _Hit(TIER_ABBREVIATION, why, [], False, via="abbreviation", order=hit.order)

    if len(q_strict) >= 3 and " " not in q_strict and code and not table.knows(text):
        # An entry-name mnemonic is a UniProt label, not a gene symbol, and
        # means a different protein in each organism. Only the requested
        # organism's own is listed, and only as a reading for a person to
        # confirm: no prefix is read as a symbol, and no other organism's
        # entry is offered.
        for ec, entry_name in tables.symbols.get(q_strict, ()):
            if not entry_name.endswith("_" + code):
                continue
            held = best.get(ec)
            if held is None or held.tier > TIER_SYMBOL:
                best[ec] = _Hit(
                    TIER_SYMBOL,
                    f"UniProt entry name {entry_name} is listed under this enzyme (an entry name, which is "
                    "not always the gene symbol)", [], True, via="mnemonic")

    found = [
        _candidate(index, index.entries[ec], h.tier, h.why, code, h.alt, partial=h.partial, via=h.via,
                   abbreviation=h.abbreviation, confirmed=h.confirmed, order=h.order)
        for ec, h in best.items()
    ]
    if found:
        return sorted(found, key=lambda c: _order(c, organism_known))

    limit = _typo_limit(len(q_loose))
    if not limit:
        return []
    q_tokens = q_loose.split()
    n_words = len(q_tokens)
    typo: Dict[str, Tuple[int, str, List[str]]] = {}
    memo: Dict[Tuple[str, str], Optional[int]] = {}
    # Each query word is compared once with each distinct word of every name;
    # a name none of whose words is near one of the query's cannot match.
    near: List[frozenset] = []
    for q in q_tokens:
        close = {q}
        for w in tables.vocabulary:
            if w != q and _typo_distance((q,), (w,), _typo_limit(len(q)), tables.vocabulary, memo) is not None:
                close.add(w)
        near.append(frozenset(close))
    for name in tables.names:
        if any(not (name.words & close) for close in near):
            continue
        tokens = name.loose.split()
        if len(tokens) < n_words:
            continue
        distance = None
        for i in range(len(tokens) - n_words + 1):
            d = _typo_distance(q_tokens, tokens[i:i + n_words], limit, tables.vocabulary, memo)
            if d is not None and (distance is None or d < distance):
                distance = d
        if distance is None:
            continue
        spare = len(tokens) - n_words
        held_typo = typo.get(name.ec)
        if held_typo is None or (distance, spare) < held_typo[:2]:
            if name.accepted:
                typo[name.ec] = (distance, spare, "close to the accepted name: did you mean?", [])
            else:
                typo[name.ec] = (distance, spare,
                                 f"close to another name for this enzyme, '{name.text}': did you mean?",
                                 [name.text])
    found = [
        _candidate(index, index.entries[ec], TIER_TYPO, why, code, matched, distance=distance, via="typo",
                   spare=spare)
        for ec, (distance, spare, why, matched) in typo.items()
    ]
    return sorted(found, key=lambda c: _order(c, organism_known))


def find(
    query: str, organism: Optional[str] = None, limit: Optional[int] = DEFAULT_LIMIT,
    *, index: Optional[EnzymeIndex] = None,
) -> List[Candidate]:
    """Ranked candidates for a name, an EC number or a partial EC number.

    See the module docstring for the tiers and the order within a tier.
    `organism` is anything `organism_code` reads; an organism it does not
    recognise ranks nothing differently.
    """
    index = index or load_index()
    found = _search(query, organism_code(organism), index)
    return found if limit is None else found[:limit]


def isozymes(ec: str, organism: Optional[str], *, index: Optional[EnzymeIndex] = None) -> Isozymes:
    """The organism's UniProt entries for this EC number, from the index.

    An organism the index does not recognise gives zero entries and
    organism None, which a caller must read as "not known", not "none".
    """
    index = index or load_index()
    code = organism_code(organism)
    proteins, count = index.proteins_in(ec, code)
    return Isozymes(ec=ec, organism=code, proteins=proteins, count=count)


def recommend(listed: Sequence[Candidate]) -> Optional[Candidate]:
    """The one listed enzyme with a protein from the organism, when no other has one.

    `listed` is EVERYTHING the query matched, not the best tier: an enzyme
    ranked lower can be the one the organism actually has (ADH matches
    S-(hydroxymethyl)glutathione dehydrogenase as a name and alcohol
    dehydrogenase, which five human proteins are, as an abbreviation). It
    is recommended only when

    * it is the only listed enzyme with a protein from the organism,
    * something else is listed (a lone match has nothing to be preferred
      over), and
    * it matched by NAME or EC number: never through an abbreviation, a gene
      symbol, an entry-name mnemonic or a typo, none of which is evidence
      about which enzyme was meant.

    A recommendation is a pointer for a person, never a resolution."""
    with_protein = [c for c in listed if c.has_organism_protein]
    if len(listed) > 1 and len(with_protein) == 1:
        only = with_protein[0]
        if only.via in ("name", "ec") and not only.abbreviation and only.tier != TIER_TYPO:
            return only
    return None


def _cautions(index: EnzymeIndex, chosen: Candidate, ranked: Sequence[Candidate]) -> Tuple[str, ...]:
    out: List[str] = []
    code = chosen.organism
    if code and not chosen.has_organism_protein:
        scope = organism_scope(code)
        label = organism_label(code)
        absent = f"{label} protein" if scope == label else f"protein from {scope}"
        text = f"EC {chosen.ec} ({chosen.name}) lists no {absent} in the nomenclature"
        others = [c for c in ranked if c.ec != chosen.ec and c.has_organism_protein][:3]
        if others:
            text += "; " + "; ".join(
                f"EC {c.ec} ({c.name}), which lists {organism_label(code)} "
                f"{', '.join(p.label for p in c.organism_proteins[:6])}, "
                f"also matches your words" + (f" through '{c.alternative_names[0]}'" if c.alternative_names else "")
                for c in others)
        out.append(text + ". Check this is the enzyme you mean.")
    return tuple(out)


def _count_reason(text: str, ranked: Sequence[Candidate], tied: Sequence[Candidate]) -> str:
    """How many enzymes match, and how many of them match best."""
    if len(ranked) == len(tied):
        return f"{text!r} names {len(tied)} enzymes"
    return f"{len(ranked)} enzymes match {text!r}; these {len(tied)} match best"


def resolve(
    query: str, organism: Optional[str] = None, *, index: Optional[EnzymeIndex] = None,
) -> Resolution:
    """One enzyme, or the list a person must choose from. Never a guess.

    `_resolve` holds the nomenclature's rules (below). On top of them, two
    readings that are not choices resolve, each with a sentence in `notes`
    (ADR 0182):

    * a gene symbol, lab abbreviation or curated alias that the symbol table
      maps to exactly ONE enzyme in the organism (`SymbolTable.read`): "HK2"
      is hexokinase, isoform HK2, read for Homo sapiens when no organism was
      given and it is written as a human gene symbol. A symbol several
      enzymes go by (HK, LDH, NOS, SDH, PEPCK with no organism) is still a
      choice;
    * a spelling with ONE close enzyme name (`spelling_match`):
      "acetylcholinestrase" is acetylcholinesterase.

    A symbol written the two other ways people write it is read as the
    symbol, and the note says so (`_symbol_spelling`): "P450 3A4" is CYP3A4,
    and "hCA II" is CA II in human.
    """
    index = index or load_index()
    respelt = _symbol_spelling(query, organism, index)
    if respelt is not None:
        return respelt
    result = _resolve(query, organism, index=index)
    text = " ".join(query.split())
    code = organism_code(organism)
    table = load_symbols()
    if table.knows(text) and read_ec(text) is None:
        reading = table.read(text, code)
        if reading is not None and reading.ec in index.entries and index.entries[reading.ec].status == ACTIVE:
            if isinstance(result, Resolved) and result.ec == reading.ec:
                return Resolved(ec=result.ec, how=result.how, candidate=result.candidate, cautions=result.cautions,
                                isoform=reading.isoform, organism=reading.assumed_organism,
                                notes=_reading_notes(text, reading), symbol_read=True)
            if isinstance(result, Ambiguous) and (result.confirm_only or not result.candidates
                                                  or _only_rivals_by_abbreviation(result, reading.ec)):
                ranked = _search(text, reading.organism or code, index)
                head = next((c for c in ranked if c.ec == reading.ec), None)
                if head is None:
                    head = _candidate(index, index.entries[reading.ec], TIER_ABBREVIATION, reading.why,
                                      reading.organism or code, via="abbreviation")
                head = Candidate(**{**head.__dict__, "why": reading.why})
                others = [c for c in ranked if c.ec != reading.ec and c.tier <= TIER_ALTERNATIVE_EXACT]
                cautions = list(_cautions(index, head, ranked))
                if others:
                    cautions.append("The same letters are also listed for " + "; ".join(
                        f"EC {c.ec} ({c.name})" for c in others[:3])
                        + f", which is not what {text!r} usually means; pass --subject with that EC number "
                        "if it is the one you mean.")
                return Resolved(ec=reading.ec, how=reading.why, candidate=head, cautions=tuple(cautions),
                                isoform=reading.isoform, organism=reading.assumed_organism,
                                notes=_reading_notes(text, reading), symbol_read=True)
        return result
    if isinstance(result, Ambiguous) and read_ec(text) is None and not result.confirm_only and not result.class_word:
        spaced = _spacing_variant(text, code, index)
        if spaced is not None:
            return spaced
    if isinstance(result, Ambiguous) and read_ec(text) is None and (
            not result.candidates or result.suggestions_only and all(c.tier == TIER_TYPO for c in result.candidates)):
        spelled = spelling_match(text, index=index)
        if spelled is not None:
            ec, name, _ = spelled
            ranked = _search(name, code, index)
            head = next((c for c in ranked if c.ec == ec), None) or _candidate(
                index, index.entries[ec], TIER_TYPO, "close spelling", code, via="typo")
            closest = _closest_listed_name(text, ec, index)
            if closest is not None and strict_key(closest) != strict_key(name):
                how = (f"read as {name} (spelling): {text!r} is within a letter or two of {closest!r}, a name "
                       "the nomenclature lists for it, and no other enzyme's name comes close")
            else:
                how = (f"read as {name} (spelling): it is the one enzyme name within a letter or two of what "
                       "was typed, and no other comes close")
            head = Candidate(**{**head.__dict__, "why": how, "via": "typo"})
            return Resolved(ec=ec, how=how, candidate=head, cautions=_cautions(index, head, ranked),
                            notes=(f"Read {text!r} as {name} (spelling); pass --subject with an EC number "
                                   "if you meant another enzyme.",))
    gene = _mnemonic_is_the_gene(result, text, code, index)
    if gene is not None:
        return gene
    sibling = _qualified_sibling(result, text, code, index)
    if sibling is not None:
        return sibling
    if isinstance(result, Ambiguous):
        prefixed = _cofactor_prefixed(text, code, index)
        if prefixed is not None:
            return prefixed
    return result


def _unqualified(name: str) -> str:
    """A name with a trailing cofactor qualifier set aside: "isocitrate
    dehydrogenase (NADP(+))" is "isocitrate dehydrogenase"."""
    return strict_key(re.sub(r"\s*(?:\[[^\]]*\]|\((?:[^()]|\([^()]*\))*\))\s*$", "", name))


_COFACTOR_FIRST = re.compile(r"^(NADP|NAD|NADPH|NADH|NAD\(P\))\+?[- ](?:dependent[- ]|specific[- ]|linked[- ])?(.+)$",
                             re.IGNORECASE)


def _cofactor_prefixed(text: str, code: Optional[str], index: EnzymeIndex) -> Optional[Resolved]:
    """"NADP-isocitrate dehydrogenase" as the one enzyme of that name whose
    qualifier is that cofactor: EC 1.1.1.42 (isocitrate dehydrogenase
    (NADP(+))). The cofactor was read as part of a substrate and the
    sentence refused as naming no enzyme (fourth round of the review)."""
    m = _COFACTOR_FIRST.match(text)
    if not m:
        return None
    cofactor = m.group(1).upper().replace("H", "")
    base = strict_key(m.group(2))
    ranked = _search(m.group(2), code, index)

    def qualified_by(name: str) -> bool:
        tail = name[len(re.sub(r"\s*(?:\[[^\]]*\]|\((?:[^()]|\([^()]*\))*\))\s*$", "", name)):]
        low = tail.upper()
        if cofactor == "NAD(P)":
            return "NAD(P)" in low
        if cofactor == "NADP":
            return "NADP" in low and "NAD(P)" not in low
        return "NAD" in low and "NADP" not in low and "NAD(P)" not in low

    matching = [c for c in ranked if _unqualified(c.name) == base and qualified_by(c.name)
                and c.status == ACTIVE]
    if len(matching) != 1:
        return None
    chosen = matching[0]
    how = (f"{text!r} names the cofactor first: EC {chosen.ec} ({chosen.name}) is the one enzyme of "
           f"that name whose stated cofactor it is")
    # The accepted name with its qualifier written as a prefix: read as
    # that name, tolerantly (not a phrase inside a longer name).
    head = Candidate(**{**chosen.__dict__, "why": how, "partial": False,
                        "tier": TIER_ACCEPTED_EXACT})
    return Resolved(ec=chosen.ec, how=how, candidate=head, cautions=_cautions(index, head, ranked))


def _mnemonic_is_the_gene(result: Resolution, text: str, code: Optional[str],
                          index: EnzymeIndex) -> Optional[Resolved]:
    """The enzyme an entry-name mnemonic of the organism names, when UniProt
    gives that very entry the typed word as its gene symbol and the
    nomenclature lists the entry under one EC number only.

    A mnemonic alone is not a gene symbol (ACES_HUMAN is ACHE, KSYK_HUMAN is
    SYK), so it stays a choice. But NQO1_HUMAN's gene IS NQO1, and "NQO1 with
    menadione in human" was refused as "not always the gene symbol" while
    ALDH2, FAAH and CYP2D6 were read through the symbol table (fifth round of
    the real-values review). The protein names file says which entries'
    mnemonic and gene agree; only those are read, with the gene as the
    isoform, and the note says so."""
    if not isinstance(result, Ambiguous) or not code or not result.candidates:
        return None
    if result.candidates[0].via != "mnemonic":
        return None
    symbol = [c for c in result.candidates if c.via == "mnemonic"]
    if len({c.ec for c in symbol}) != 1:
        return None
    if any(c.via in ("name", "abbreviation") and c.tier < TIER_SYMBOL for c in result.candidates):
        return None
    chosen = symbol[0]
    entry = f"{strict_key(text).upper()}_{code}"
    protein = next((p for p in chosen.organism_proteins if p.entry_name.upper() == entry), None)
    if protein is None:
        return None
    from .protein_names import info

    found = info(protein.accession)
    if found is None or not found.gene or found.gene.casefold() != text.strip().casefold():
        return None
    label = organism_label(code)
    how = (f"{text!r} is the gene symbol UniProt gives {protein.entry_name} (UniProtKB "
           f"{protein.accession}), the {label} protein the enzyme nomenclature lists under this "
           "enzyme and no other")
    head = Candidate(**{**chosen.__dict__, "why": how, "partial": False})
    return Resolved(ec=chosen.ec, how=how, candidate=head, cautions=(), isoform=found.gene,
                    notes=(f"The constants are taken from rows that name {found.gene} where there are any; "
                           "pass --subject with an EC number if you meant another enzyme.",),
                    symbol_read=True)


def _qualified_sibling(result: Resolution, text: str, code: Optional[str],
                       index: EnzymeIndex) -> Optional[Resolved]:
    """The enzyme a name read as one EC number with no protein in the
    organism means, when exactly one other EC number of the same name with a
    cofactor qualifier ("glutamate dehydrogenase [NAD(P)(+)]") has one.

    "glutamate dehydrogenase from bovine liver" was read as EC 1.4.1.2,
    NAD-specific and with no cow protein, beside a caution naming EC
    1.4.1.3, bovine liver GDH (DHE3); the typed 2-oxoglutarate was then
    dropped (fourth round of the real-values review)."""
    if not isinstance(result, Resolved) or not code or read_ec(text) is not None:
        return None
    chosen = result.candidate
    if chosen is None or chosen.has_organism_protein:
        return None
    base = strict_key(chosen.name)

    def unqualified(name: str) -> str:
        return strict_key(re.sub(r"\s*(?:\[[^\]]*\]|\((?:[^()]|\([^()]*\))*\))\s*$", "", name))

    ranked = _search(text, code, index)
    # A cofactor qualifier only ("[NAD(P)(+)]", "(NADP(+))"): "L-lactate
    # dehydrogenase (cytochrome)" is another enzyme with another acceptor.
    siblings = [c for c in ranked if c.ec != chosen.ec and unqualified(c.name) == base
                and c.via == "name" and c.tier != TIER_TYPO
                and re.search(r"NAD", c.name[len(base):] if c.name.lower().startswith(base) else c.name)]
    with_protein = [c for c in siblings if c.has_organism_protein]
    if len(with_protein) != 1:
        return None
    other = with_protein[0]
    label = organism_label(code)
    proteins = ", ".join(p.label for p in other.organism_proteins[:4])
    how = (f"{text!r} is the name of EC {chosen.ec} ({chosen.name}), which lists no {label} protein in "
           f"the nomenclature; EC {other.ec} ({other.name}), the same name with its cofactor stated, "
           f"lists {label} {proteins}, so it is the enzyme of the organism named")
    head = Candidate(**{**other.__dict__, "why": how})
    return Resolved(ec=other.ec, how=how, candidate=head, cautions=(),
                    notes=(f"Read {text!r} as EC {other.ec} ({other.name}), not EC {chosen.ec}: only "
                           f"the former lists a {label} protein ({proteins}); pass --subject {chosen.ec} "
                           "to model the other.",))


def _closest_listed_name(text: str, ec: str, index: EnzymeIndex) -> Optional[str]:
    """The name listed for `ec` closest to `text`, as the nomenclature writes it.

    The spelling note quotes it, so a reader sees which listed name the
    typed word was close to: "butyrylcholinesterase" is one letter and a
    space from 'butyrylcholine esterase', and the note used to name only the
    accepted name 'cholinesterase', seven letters shorter (round-1 F15)."""
    import difflib

    key = strict_key(text)
    names = [n for n in _tables(index).names if n.ec == ec]
    if not names:
        return None
    return max(names, key=lambda n: difflib.SequenceMatcher(None, n.strict, key, autojunk=False).ratio()).text


#: The shortest name, in letters, read through a spacing difference alone.
SPACING_MIN_LENGTH = 8


def _spacing_variant(text: str, code: Optional[str], index: EnzymeIndex) -> Optional[Resolved]:
    """ONE enzyme whose listed name is `text` with spaces or hyphens moved, else None.

    "butyrylcholinesterase" is the nomenclature's "butyrylcholine esterase"
    (EC 3.1.1.8) written as one word. It used to be read through the
    spelling tier, and the report said it was "within a letter or two of
    what was typed", which a reader takes for a typo Caterva corrected
    (round-1 finding F15). Nothing was misspelt: the name is listed, and the
    note now quotes it. Read only when every name written that way belongs
    to one enzyme, the name is a word and not an abbreviation, and it is at
    least SPACING_MIN_LENGTH letters.
    """
    key = compact_name_key(text)
    if len(re.sub(r"[^a-z]", "", key)) < SPACING_MIN_LENGTH:
        return None
    elided = ""
    if key not in _tables(index).compact:
        # "acetylcholine esterase" is the listed "acetylcholinesterase" with
        # the space written and the letter the two words share at the join
        # written twice. Read as the listed name, not as a spelling
        # correction (review of the names stream, 2026-11-12).
        words = strict_key(text).split()
        for i in range(len(words) - 1):
            if words[i] and words[i + 1] and words[i][-1] == words[i + 1][0] and words[i][-1].isalpha():
                joined = "".join(words[:i + 1]) + "".join(words[i + 1:])[1:]
                if joined in _tables(index).compact:
                    key, elided = joined, words[i][-1]
                    break
    names = [n for n in _tables(index).compact.get(key, ()) if not n.abbreviation]
    if any(n.strict == strict_key(text) for n in names):
        # Typed exactly as listed: `_resolve` has already decided it, and a
        # refusal there ("protein kinase", a class word) stands.
        return None
    ecs = {n.ec for n in names}
    if len(ecs) != 1 or len(names) != len(_tables(index).compact.get(key, ())):
        return None
    name = sorted(names, key=lambda n: (not n.accepted, n.text))[0]
    ranked = _search(name.text, code, index)
    head = next((c for c in ranked if c.ec == name.ec and not c.partial), None)
    if head is None:
        return None
    how = (f"listed as {'the accepted name' if name.accepted else 'another name for this enzyme'}: "
           f"'{name.text}', which is what was typed with the spacing or hyphens written differently"
           + (f" and the '{elided}' the two words share at the join written once" if elided else ""))
    head = Candidate(**{**head.__dict__, "why": how})
    return Resolved(ec=name.ec, how=how, candidate=head, cautions=_cautions(index, head, ranked))


def _only_rivals_by_abbreviation(result: "Ambiguous", ec: str) -> bool:
    """The best-tier candidates other than `ec` matched only as abbreviations
    or table readings, never by a full enzyme name: "angiotensin-converting
    enzyme" ties EC 3.4.15.1 (the table's reading) with a phrase inside
    'angiotensin-converting enzyme 2', and the table's reading decides."""
    if not result.candidates or result.class_word:
        return False
    best = result.candidates[0].tier
    tied = [c for c in result.candidates if c.tier == best]
    if ec not in {c.ec for c in tied} and best < TIER_ABBREVIATION:
        return False
    return all(c.ec == ec or c.via != "name" or c.abbreviation or c.partial for c in tied)


_P450 = re.compile(r"^(?:cytochrome\s+)?(?:P-?450|CYP)[\s-]*(\d{1,2}[A-Za-z]{1,2}\d{0,2})$", re.IGNORECASE)
_HUMAN_PREFIX = re.compile(r"^h(?=[A-Z])(\S.*)$")


def respelt_symbol(text: str) -> Optional[str]:
    """The symbol the table holds that `text` writes another way ("P450 3A4"
    is CYP3A4, "hCA II" is CA II), or None. See `_symbol_spelling`."""
    text = " ".join(text.split())
    table = load_symbols()
    if table.knows(text):
        return None
    match = _P450.match(text)
    if match is not None:
        symbol = "CYP" + match.group(1).upper()
        return symbol if table.knows(symbol) else None
    match = _HUMAN_PREFIX.match(text)
    if match is not None and table.knows(match.group(1)):
        return match.group(1)
    return None


def _symbol_spelling(query: str, organism: Optional[str], index: EnzymeIndex) -> Optional[Resolution]:
    """A gene symbol written as "P450 3A4" / "CYP 2D6", or with the "h" that
    marks a human protein ("hCA II", "hAChE", "hMAO-B"), read as the symbol
    the table holds, with a note; None for anything else.

    Both were passed over in a sentence (round-1 finding F12): "hCA II" was
    taken for a substrate, and "cytochrome P450 3A4" read as the whole
    P450 EC number with no isoform. The "h" is read only when the rest is a
    symbol the table holds, the whole is not, and no organism other than
    human was given."""
    text = " ".join(query.split())
    table = load_symbols()
    if table.knows(text) or read_ec(text) is not None:
        return None
    human = False
    match = _P450.match(text)
    if match is not None:
        symbol = "CYP" + match.group(1).upper()
        if not table.knows(symbol):
            return None
        result = resolve(symbol, organism, index=index)
        note = f"Read {text!r} as {symbol}, the gene symbol it spells out."
    else:
        match = _HUMAN_PREFIX.match(text)
        code = organism_code(organism)
        if match is None or not table.knows(match.group(1)) or code not in (None, "HUMAN"):
            return None
        symbol = match.group(1)
        result = resolve(symbol, "Homo sapiens", index=index)
        human = organism is None
        note = f"Read {text!r} as {symbol} in Homo sapiens: the leading 'h' marks the human protein."
    if isinstance(result, Resolved):
        return Resolved(ec=result.ec, how=result.how, candidate=result.candidate, cautions=result.cautions,
                        isoform=result.isoform, organism="Homo sapiens" if human else result.organism,
                        notes=(note, *result.notes), symbol_read=True)
    return result


def _reading_notes(text: str, reading) -> Tuple[str, ...]:
    out = list(reading.notes)
    if reading.isoform:
        out.append(f"Read {text!r} as the isoform {reading.isoform} of EC {reading.ec}; the constants are "
                   "taken from BRENDA rows that name it where there are any (pass --isoform to change it).")
    return tuple(out)


#: How close a typed name must be to an enzyme name to be read as it.
SPELLING_RATIO = 0.92
#: How far ahead of every other enzyme the closest one must be.
SPELLING_MARGIN = 0.03
#: The shortest typed name a spelling is ever forgiven in: shorter words are
#: within a letter of too many others ("lipase", "kinase").
SPELLING_MIN_LENGTH = 8
#: The endings of an enzyme's name. A word ending otherwise is a compound,
#: and "glucose 6-phosphate" is within a few letters of glucose-6-phosphatase.
_ENZYME_ENDING = re.compile(r"(?:ase|ases|zyme|in)$")


@lru_cache(maxsize=4)
def _names_by_length(index: EnzymeIndex) -> Dict[int, List[Tuple[str, str, str]]]:
    out: Dict[int, List[Tuple[str, str, str]]] = {}
    for name in _tables(index).names:
        out.setdefault(len(name.strict), []).append((name.strict, name.ec, index.entries[name.ec].name))
    return out


def spelling_match(text: str, *, index: Optional[EnzymeIndex] = None) -> Optional[Tuple[str, str, float]]:
    """(EC, accepted name, ratio) when `text` is a misspelling of ONE enzyme name, else None.

    "acetylcholinestrase" is acetylcholinesterase: one enzyme name is within
    a letter or two of it, and no other comes close. It is read only when

    * the typed text is at least SPELLING_MIN_LENGTH letters, has no digit,
      ends the way an enzyme name ends (-ase, -zyme, -in) and is not itself
      a word of any enzyme name;
    * its difflib ratio to the closest name is at least SPELLING_RATIO; and
    * every name of every OTHER enzyme is at least SPELLING_MARGIN further
      away and below SPELLING_RATIO.

    So "hexokinas" (no -ase), "lipse" (short) and "glucose 6-phosphate"
    (a digit, and a compound's ending) are never read as an enzyme.
    """
    import difflib

    index = index or load_index()
    key = strict_key(text)
    letters = re.sub(r"[^a-z]", "", key)
    if len(letters) < SPELLING_MIN_LENGTH or any(ch.isdigit() for ch in key):
        return None
    if not _ENZYME_ENDING.search(key.split()[-1]) if key else True:
        return None
    tables = _tables(index)
    if all(w in tables.vocabulary for w in key.split()):
        return None
    low = int(len(key) * SPELLING_RATIO / (2 - SPELLING_RATIO)) - 1
    high = int(len(key) * (2 - SPELLING_RATIO) / SPELLING_RATIO) + 1
    best: Dict[str, Tuple[float, str]] = {}
    matcher = difflib.SequenceMatcher(None, "", key, autojunk=False)
    buckets = _names_by_length(index)
    for length in range(max(1, low), high + 1):
        for strict, ec, accepted in buckets.get(length, ()):
            matcher.set_seq1(strict)
            if matcher.real_quick_ratio() < SPELLING_RATIO - SPELLING_MARGIN or \
                    matcher.quick_ratio() < SPELLING_RATIO - SPELLING_MARGIN:
                continue
            ratio = matcher.ratio()
            if ratio > best.get(ec, (0.0, ""))[0]:
                best[ec] = (ratio, accepted)
    if not best:
        return None
    ranked = sorted(best.items(), key=lambda item: -item[1][0])
    ec, (ratio, accepted) = ranked[0]
    if ratio < SPELLING_RATIO or ratio >= 1.0:
        return None
    if len(ranked) > 1:
        runner = ranked[1][1][0]
        if runner >= SPELLING_RATIO or ratio - runner < SPELLING_MARGIN:
            return None
    return ec, accepted, ratio


def _resolve(
    query: str, organism: Optional[str] = None, *, index: Optional[EnzymeIndex] = None,
) -> Resolution:
    """The nomenclature's own rules; `resolve` adds the symbol and spelling readings.

    WHEN IT RESOLVES. Only for what is not a choice:

    * an EC number that exists, a transferred number (to its replacement,
      said so) and nothing else numeric;
    * a unique accepted name, or a unique exact alternative name that is a
      full name ("lysozyme", "lipase", "pyruvate kinase");
    * an exact alternative name that is itself an abbreviation ("GAPDH",
      "ACE", "PKA") only when the abbreviation table (symbols.py) lists it
      for that enzyme and for no other. Where the table lists it for
      another enzyme too, or the nomenclature's name is the only thing
      saying so (NOS is an alternative name of D-nopaline dehydrogenase,
      and everyone means nitric-oxide synthase), it is a choice.

    WHEN IT NEVER RESOLVES.

    a. A short abbreviation or symbol (anything that is not an accepted
       name, an exact alternative name or an EC number) is listed as a
       candidate and the person chooses: HK1, SDH, AK, PEPC, ACHE.
    b. A UniProt entry-name mnemonic (HXK1_HUMAN style) is not a gene
       symbol: the part before the underscore is never read as one, so SYK
       is not the lysine--tRNA ligase whose mnemonic is SYK_HUMAN. A
       mnemonic is listed, for the requested organism only, as a reading to
       confirm.
    c. A unique match that is another name of an enzyme with NO protein in
       the organism asked about, while another enzyme whose name also
       matches has one, is not resolved: the glycogen synthase of human
       cells is EC 2.4.1.11, not the bacterial starch synthase that lists
       the words as an alternative name. Both are listed, and the one with
       the organism's protein is named as the recommendation.
    d. An abbreviation that is an exact alternative name of exactly one
       enzyme but that is shared with other enzymes in the abbreviation
       table still needs confirmation.
    e. A one-word query matched only once a stereo label was set aside
       ('L-protein', 'D-enzyme', 'L-peptidase') is a choice when other
       enzymes use the word as written.
    f. An exact alternative name that is the family phrase inside two or
       more other enzymes' accepted names, and not in its own enzyme's
       accepted name ("protein kinase", "threonine aldolase"), is a choice.

    `recommended` is set across the WHOLE listed set (see `recommend`).
    A typo match is never resolved. A transferred EC number resolves to its
    replacement and says so; a deleted one resolves to nothing and says so.
    """
    index = index or load_index()
    code = organism_code(organism)
    ranked = _search(query, code, index)
    text = " ".join(query.split())
    release = index.release

    if not ranked:
        parts = read_ec(text)
        if parts is not None and len(parts) == 4:
            reason = (f"EC {'.'.join(parts)} is not in the enzyme nomenclature "
                      f"(ExPASy ENZYME release {release}). Check the number.")
        elif parts is not None:
            reason = f"no enzyme in the nomenclature has an EC number starting {'.'.join(parts)}."
        else:
            reason = f"no enzyme name in the nomenclature (ExPASy ENZYME release {release}) matches {text!r}."
            table = load_symbols()
            elsewhere = table.organisms_for(text)
            restricted = table.alias_organisms(text)
            if code and elsewhere and code not in elsewhere:
                reason += (f" The gene-symbol table lists {text!r} for "
                           + ", ".join(organism_label(o) for o in elsewhere)
                           + f" but not for {organism_label(code)}, and a symbol is a different protein in "
                           "each organism, so none is offered.")
            elif code and restricted and code not in restricted:
                # CYP2D6 in rat: the curated row reads it for human only
                # (P450 families are not one-to-one between species).
                reason += (f" The curated table reads {text!r} for "
                           + ", ".join(organism_label(o) for o in restricted)
                           + f" only, not for {organism_label(code)}: it is another organism's gene, so none is "
                           f"offered. Name the {organism_label(code)} enzyme, or pass --subject with its EC number.")
        return Ambiguous(query=text, candidates=(), reason=reason, organism=code, release=release)

    parts = read_ec(text)
    if parts is not None and len(parts) == 4:
        given = ".".join(parts)
        head = ranked[0]
        if head.ec == given and head.status == ACTIVE:
            return Resolved(ec=given, how="you gave this EC number", candidate=head)
        if head.ec == given and head.status == DELETED:
            return Ambiguous(
                query=text, candidates=(),
                reason=(f"EC {given} was deleted from the enzyme nomenclature and has no replacement "
                        f"(ExPASy ENZYME release {release}). Check the number."),
                organism=code, release=release)
        replacements = [c for c in ranked if c.ec != given]
        if len(replacements) == 1:
            new = replacements[0]
            how = (f"EC {given} was transferred in the enzyme nomenclature; it is now EC {new.ec} "
                   f"({new.name}), so EC {new.ec} is used")
            return Resolved(ec=new.ec, how=how, candidate=new, cautions=(how[0].upper() + how[1:] + ".",))
        return Ambiguous(
            query=text, candidates=tuple(replacements),
            recommended=recommend(replacements),
            reason=(f"EC {given} was transferred to " + (
                "no active enzyme" if not replacements else f"{len(replacements)} enzymes")
                + " in the enzyme nomenclature, so it no longer names one enzyme."),
            organism=code, release=release)

    best_tier = ranked[0].tier
    tied = [c for c in ranked if c.tier == best_tier]
    recommended = recommend(ranked)
    if best_tier == TIER_TYPO:
        return Ambiguous(
            query=text, candidates=tuple(ranked), reason=f"no enzyme is named {text!r}; these are close",
            suggestions_only=True, organism=code, release=release)

    only = tied[0] if len(tied) == 1 else None
    table_reading = any(c.via == "abbreviation" for c in tied)
    unconfirmed_abbreviation = only is not None and only.abbreviation and not only.confirmed
    if table_reading or unconfirmed_abbreviation:
        # Rules a, b and d. A confirmed abbreviation is the one case that resolves.
        if only is not None and only.confirmed and only.via == "name" and not only.partial:
            return Resolved(ec=only.ec, how=only.why, candidate=only, cautions=_cautions(index, only, ranked))
        many = len(tied) > 1
        return Ambiguous(
            query=text, candidates=tuple(ranked), recommended=None, confirm_only=True,
            reason=((f"{text!r} is a name {len(tied)} enzymes go by (a short form of each one's name), "
                     "and Caterva does not choose between them by itself"
                     if many and " " in text else
                     f"{text!r} is an abbreviation or symbol, not an enzyme name, and Caterva does not "
                     "resolve one by itself" + (f"; {len(tied)} enzymes go by it" if many else ""))),
            organism=code, release=release)
    if only is not None and only.partial:
        if only.tier == TIER_SYMBOL:
            reason = (f"{text!r} is the entry-name mnemonic of a protein, not an enzyme name and not "
                      "necessarily a gene symbol, and a symbol can mean a different enzyme in each organism")
        else:
            # One enzyme matches best, others less well: "thioredoxin
            # reductase" is a phrase inside eight names, and "matches only
            # part of one enzyme's name" was said above a list of eight
            # (fifth round of the real-values review).
            reason = (f"{text!r} matches only part of one enzyme's name, which is not enough to say it is "
                      "that enzyme" if len(ranked) == 1 else
                      f"{text!r} is only part of an enzyme's name: it is a phrase inside, or some words of, "
                      f"the names of {len(ranked)} enzymes, which is not enough to say it is any one of them")
        return Ambiguous(
            query=text, candidates=tuple(ranked), suggestions_only=True, organism=code, release=release,
            reason=reason)
    if only is not None:
        # Rule e. A one-word query that met this enzyme only once a label was
        # set aside, while other enzymes carry the word as written. "protein"
        # read as EC 1.8.1.4 through its other name 'L-protein', "enzyme" as
        # EC 2.4.1.25 through 'D-enzyme', "peptidase" as the viral L-peptidase
        # (EC 3.4.22.46) and "glutamyltransferase" as D-glutamyltransferase
        # while gamma-glutamyltransferase is listed beside it: `caterva bind
        # --ec protein --organism pig` then printed seven cited Ki rows of
        # dihydrolipoyl dehydrogenase as the answer. In "L-lactate" the label
        # qualifies a substrate and the rest of the name still says which
        # enzyme; on a bare word the label was the whole of what told this
        # enzyme apart, so the reading is a choice. A one-word name no other
        # enzyme uses ("fuculokinase", "iduronidase") still resolves.
        if only.tier in (TIER_ACCEPTED_TOLERANT, TIER_ALTERNATIVE_TOLERANT) and len(loose_key(text).split()) == 1:
            others = [c for c in ranked if c.ec != only.ec and c.via == "name" and c.tier <= TIER_ALL_WORDS]
            if others:
                written = only.alternative_names[0] if only.alternative_names else only.name
                return Ambiguous(
                    query=text, candidates=tuple(ranked), recommended=None, organism=code, release=release,
                    class_word=True,
                    reason=(f"{text!r} matches EC {only.ec} ({only.name}) only once the label in '{written}' is "
                            f"set aside, and {len(others)} other enzyme{'s' if len(others) != 1 else ''} "
                            f"use{'s' if len(others) == 1 else ''} the word as written: on its own it names "
                            "none of them"))
        # Rule f. An exact OTHER name that is also the family word of other
        # enzymes' accepted names, and is not in this enzyme's own accepted
        # name. "protein kinase" is listed as another name of histidine kinase
        # (EC 2.7.13.3) and is the phrase inside 'protein kinase C', 'cAMP-
        # dependent protein kinase' and fourteen more; "threonine aldolase"
        # resolved to serine hydroxymethyltransferase (EC 2.1.2.1) beside
        # L-threonine aldolase. Two or more accepted names using the words
        # make them a family the nomenclature names; one may be a qualified
        # variant ("sorbitol dehydrogenase" is still L-iditol 2-dehydrogenase).
        # An accepted name that holds the words is the enzyme they name, so
        # "lipase" (triacylglycerol lipase) and "pepsin" (pepsin A) resolve.
        if only.tier == TIER_ALTERNATIVE_EXACT and not only.abbreviation \
                and f" {loose_key(text)} " not in f" {loose_key(only.name)} ":
            family = [c for c in ranked if c.ec != only.ec and c.tier == TIER_ACCEPTED_PHRASE]
            if len(family) >= 2:
                return Ambiguous(
                    query=text, candidates=tuple(ranked), recommended=None, organism=code, release=release,
                    class_word=True, family=True,
                    reason=(f"{text!r} is listed as another name of EC {only.ec} ({only.name}), and is also "
                            f"the family name inside the accepted names of {len(family)} other enzymes, such as "
                            + ", ".join(f"EC {c.ec} ({c.name})" for c in family[:2])
                            + ": it names a kind of enzyme, not one"))
        if code and not only.has_organism_protein and only.tier in (TIER_ALTERNATIVE_EXACT, TIER_ALTERNATIVE_TOLERANT):
            # Rule c. Another name of an enzyme the organism does not have,
            # while an enzyme whose own name matches has one. An ACCEPTED
            # name is not held to this: "subtilisin" is the bacterial enzyme
            # whatever else mentions the word, and the caution says so.
            rivals = [c for c in ranked if c.ec != only.ec and c.has_organism_protein
                      and c.via == "name" and c.tier <= TIER_ALL_WORDS]
            if rivals:
                label = organism_label(code)
                return Ambiguous(
                    query=text, candidates=tuple(ranked), recommended=recommended,
                    reason=(f"{text!r} is a name of EC {only.ec} ({only.name}), which lists no "
                            + (f"{label} protein" if organism_scope(code) == label else f"protein from {organism_scope(code)}")
                            + ", and also matches "
                            + ", ".join(f"EC {c.ec} ({c.name}), which lists {label} "
                                        f"{', '.join(p.label for p in c.organism_proteins[:4])}" for c in rivals[:2])
                            + (f", and {len(rivals) - 2} more" if len(rivals) > 2 else "")),
                    organism=code, release=release)
        return Resolved(ec=only.ec, how=only.why, candidate=only, cautions=_cautions(index, only, ranked))
    kind = "a class of enzymes, not one enzyme" if best_tier == TIER_EC else None
    return Ambiguous(
        query=text, candidates=tuple(ranked), recommended=recommended,
        reason=f"{text!r} is {kind}" if kind else _count_reason(text, ranked, tied),
        organism=code, release=release)


# ---------------------------------------------------------------------------
# Saying it
# ---------------------------------------------------------------------------

#: How many candidates a refusal lists before pointing at `caterva enzyme`.
REFUSAL_SHOWN = 6


def refusal_text(ambiguous: Ambiguous, rerun: str = "--subject {ec}", shown: int = REFUSAL_SHOWN) -> str:
    """The refusal a person reads: the candidates by name, then the flag to re-run with.

    `rerun` is the instruction ending the message, with `{ec}` for the
    enzyme; a command with another spelling for the flag passes its own.
    """
    candidates = list(ambiguous.candidates)
    reason = ambiguous.reason.rstrip(".")
    reason = f"{reason[:1].upper()}{reason[1:]}"
    if not candidates:
        return reason + "."
    lines: List[str] = []
    best = candidates[0].tier
    if ambiguous.suggestions_only:
        lines.append(f"{reason}. Did you mean:" if candidates[0].tier != TIER_TYPO
                     else f"No enzyme is named {ambiguous.query!r}. Did you mean:")
    elif ambiguous.confirm_only:
        lines.append(f"{reason}. It can mean:")
    else:
        lines.append(f"{reason}. Best matches first:")
    shown_candidates = candidates[:shown]
    weaker_started = False
    for candidate in shown_candidates:
        if candidate.tier != best and not weaker_started and not ambiguous.suggestions_only:
            lines.append("Weaker matches:")
            weaker_started = True
        mark = "  <- recommended: the only enzyme matched with a protein from the organism you gave" \
            if ambiguous.recommended is not None and candidate.ec == ambiguous.recommended.ec else ""
        lines.append(f"  {candidate.label()}{mark}")
    if len(candidates) > shown:
        lines.append(f"  and {len(candidates) - shown} more: `caterva enzyme {ambiguous.query!r}` lists them all")
    pick = ambiguous.recommended or candidates[0]
    if ambiguous.confirm_only:
        lines.append(
            "Caterva will not choose for you: a wrong EC number is a citation for the wrong enzyme, not merely a "
            "wrong value. If " + ("this is" if len(candidates) == 1 else "one of these is")
            + " the enzyme you mean, re-run with " + rerun.format(ec=pick.ec))
    elif ambiguous.suggestions_only:
        # A command that runs: "urokinse" was answered with a command that
        # kept the misspelling and a "<its EC number>" to fill in, while
        # "enolse" got one ready to run (fifth round, R5V1-25).
        spelled = _outside_parentheses(
            (pick.alternative_names[0] if pick.alternative_names and not pick.spare else pick.name)).strip()
        lines.append(f"Check the spelling; if you meant {spelled!r} (EC {pick.ec}), re-run with "
                     + rerun.format(ec=pick.ec))
    elif ambiguous.class_word:
        lines.append("Name the enzyme itself: a wrong EC number is a citation for the wrong enzyme, not merely "
                     "a wrong value. Re-run with " + rerun.format(ec="<its EC number>"))
    else:
        lines.append(
            "These are different enzymes, so Caterva will not pick one for you: a wrong EC number is a "
            "citation for the wrong enzyme, not merely a wrong value. "
            + ("To accept the recommendation, re-run with " if ambiguous.recommended is not None
               else "Re-run with the one you meant, for example ")
            + rerun.format(ec=pick.ec))
    return "\n".join(lines)


__all__ = [
    "Candidate", "Resolved", "Ambiguous", "Resolution", "Isozymes",
    "find", "resolve", "isozymes", "refusal_text", "read_ec", "recommend", "spelling_match",
    "strict_key", "loose_key", "DEFAULT_LIMIT", "REFUSAL_SHOWN",
]
