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
   dehydrogenase and means nitric-oxide synthase).

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
from .symbols import ABBREVIATION, load_symbols

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
    """Case, punctuation, hyphens and spacing set aside; nothing else."""
    folded = unicodedata.normalize("NFKC", text).lower()
    return " ".join(re.sub(r"[\W_]+", " ", folded).split())


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
) -> Candidate:
    proteins, count = index.proteins_in(entry.ec, code)
    return Candidate(
        ec=entry.ec, name=entry.name, why=why, tier=tier, reaction=entry.reaction,
        class_path=index.class_path(entry.ec), alternative_names=tuple(matched),
        organism_proteins=proteins, organism_protein_count=count, organism=code,
        status=entry.status, superseded_by=entry.superseded_by, distance=distance, partial=partial,
        via=via, abbreviation=abbreviation, confirmed=confirmed, order=order,
    )


def _order(candidate: Candidate, organism_known: bool) -> tuple:
    return (
        candidate.tier,
        candidate.distance,
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


def _typo_distance(q_tokens: Sequence[str], window: Sequence[str], limit: int, vocabulary: frozenset = frozenset()) -> Optional[int]:
    """Total edits between a query and a run of a name's words, or None.

    Only a word of six letters or more may carry an edit (`_typo_limit`), and
    a word with a digit never: "CYP2C9" is within one edit of other
    cytochromes' symbols and is not a misspelling of any of them, and in
    "HIV protease" the HIV is not what was mistyped. A word that is itself a
    word of some enzyme name is a word, not a typo ("ethanol" is not
    "methanol" mistyped). The words must pair up one to one."""
    if len(q_tokens) != len(window):
        return None
    total = 0
    for q, w in zip(q_tokens, window):
        if q == w:
            continue
        per_word = _typo_limit(len(q))
        if not per_word or any(ch.isdigit() for ch in q + w) or q in vocabulary:
            return None
        d = _within(q, w, per_word)
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
        confirmers = {h.ec for h in table_hits if h.kind == ABBREVIATION}
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
    for name in tables.names:
        tokens = name.loose.split()
        if len(tokens) < n_words:
            continue
        distance = None
        for i in range(len(tokens) - n_words + 1):
            d = _typo_distance(q_tokens, tokens[i:i + n_words], limit, tables.vocabulary)
            if d is not None and (distance is None or d < distance):
                distance = d
        if distance is None:
            continue
        held_typo = typo.get(name.ec)
        if held_typo is None or distance < held_typo[0]:
            if name.accepted:
                typo[name.ec] = (distance, "close to the accepted name: did you mean?", [])
            else:
                typo[name.ec] = (distance, f"close to another name for this enzyme, '{name.text}': did you mean?",
                                 [name.text])
    found = [
        _candidate(index, index.entries[ec], TIER_TYPO, why, code, matched, distance=distance, via="typo")
        for ec, (distance, why, matched) in typo.items()
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
            elsewhere = load_symbols().organisms_for(text)
            if code and elsewhere and code not in elsewhere:
                reason += (f" The gene-symbol table lists {text!r} for "
                           + ", ".join(organism_label(o) for o in elsewhere)
                           + f" but not for {organism_label(code)}, and a symbol is a different protein in "
                           "each organism, so none is offered.")
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
            reason=(f"{text!r} is an abbreviation or symbol, not an enzyme name, and Caterva does not resolve "
                    "one by itself" + (f"; {len(tied)} enzymes go by it" if many else "")),
            organism=code, release=release)
    if only is not None and only.partial:
        if only.tier == TIER_SYMBOL:
            reason = (f"{text!r} is the entry-name mnemonic of a protein, not an enzyme name and not "
                      "necessarily a gene symbol, and a symbol can mean a different enzyme in each organism")
        else:
            reason = (f"{text!r} matches only part of one enzyme's name, which is not enough to say it is "
                      "that enzyme")
        return Ambiguous(
            query=text, candidates=tuple(ranked), suggestions_only=True, organism=code, release=release,
            reason=reason)
    if only is not None:
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
                                        f"{', '.join(p.label for p in c.organism_proteins[:4])}" for c in rivals[:3])),
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
        lines.append("Check the spelling; if one of these is the enzyme, re-run with "
                     + rerun.format(ec="<its EC number>"))
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
    "find", "resolve", "isozymes", "refusal_text", "read_ec", "recommend",
    "strict_key", "loose_key", "DEFAULT_LIMIT", "REFUSAL_SHOWN",
]
