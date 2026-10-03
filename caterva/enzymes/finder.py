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
    2  another name for the enzyme equals your query
    3  the accepted name equals your query once stereo labels (L-, D-, (S)-,
       (R)-, (+)-), charge marks and Greek letters are set aside
    4  the same, for another name for the enzyme
    5  your query is a phrase inside the accepted name, on word boundaries
    6  your query is a phrase inside another name
    7  every word of your query is in one name, in any order
       (tiers 5 to 7 are fragments of a longer name: listed, never resolved
       to on their own)
    8  your query is the symbol of a UniProt entry listed under the enzyme
       (LDHA from LDHA_HUMAN), or the start of one
    9  a typo-tolerant match, offered only when nothing above matched, and
       only ever as a suggestion

"Equals" ignores case, punctuation, hyphens and spacing. Only names are
searched: the index holds no comments, so an enzyme mentioned in the comment
of another, or one whose only link to the query is a different enzyme's name,
cannot outrank one whose own name matches.

Within a tier the order is fixed and can be explained to a reader: first,
when an organism was given and the index knows it, enzymes with a protein
from that organism; then the shorter accepted name; then the EC number in
numeric order. (Typo matches order by edit distance first.)

WHEN IT RESOLVES
----------------
`resolve` returns `Resolved` only when the best tier holds exactly one enzyme:
an EC number that exists, a unique name at the best tier. A tie is
`Ambiguous`, with a `recommended` enzyme named only when exactly one tied
enzyme has a protein from the requested organism and none of the others do.
Even then nothing is picked: a person confirms with one flag. A typo match is
never resolved, and a transferred EC number resolves to its replacement with
the transfer said in the result.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from .index import (
    ACTIVE, DELETED, TRANSFERRED, EnzymeEntry, EnzymeIndex, Protein,
    load_index, organism_code, organism_label,
)

# Tier numbers; see the module docstring.
TIER_EC = 0
TIER_ACCEPTED_EXACT = 1
TIER_ALTERNATIVE_EXACT = 2
TIER_ACCEPTED_TOLERANT = 3
TIER_ALTERNATIVE_TOLERANT = 4
TIER_ACCEPTED_PHRASE = 5
TIER_ALTERNATIVE_PHRASE = 6
TIER_ALL_WORDS = 7
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
    #: phrase or some words inside it) or a protein symbol that is not the
    #: requested organism's own. A fragment is shown but never resolved to:
    #: "LDH" is a word inside the name of an electron-bifurcating complex,
    #: and is not that enzyme.
    partial: bool = False

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
                {"accession": p.accession, "entry_name": p.entry_name, "symbol": p.symbol}
                for p in self.organism_proteins
            ],
            "organism_protein_count": self.organism_protein_count,
            "has_organism_protein": self.has_organism_protein,
            "status": self.status,
            "superseded_by": list(self.superseded_by),
            "partial_match": self.partial,
        }


def _proteins_phrase(candidate: Candidate, shown: int = 6) -> str:
    label = organism_label(candidate.organism or "")
    symbols = [p.symbol for p in candidate.organism_proteins]
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


class _Tables:
    def __init__(self, index: EnzymeIndex):
        self.names: List[_Name] = []
        self.symbols: Dict[str, List[Tuple[str, str]]] = {}
        for ec, entry in index.entries.items():
            if entry.status != ACTIVE or not entry.name:
                continue
            for accepted, text in [(True, entry.name)] + [(False, a) for a in entry.alternative_names]:
                loose = loose_key(text)
                self.names.append(_Name(ec, accepted, text, strict_key(text), loose, frozenset(loose.split())))
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
) -> Candidate:
    proteins, count = index.proteins_in(entry.ec, code)
    return Candidate(
        ec=entry.ec, name=entry.name, why=why, tier=tier, reaction=entry.reaction,
        class_path=index.class_path(entry.ec), alternative_names=tuple(matched),
        organism_proteins=proteins, organism_protein_count=count, organism=code,
        status=entry.status, superseded_by=entry.superseded_by, distance=distance, partial=partial,
    )


def _order(candidate: Candidate, organism_known: bool) -> tuple:
    return (
        candidate.tier,
        candidate.distance,
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
            return [_candidate(index, entry, TIER_EC, "you gave this EC number", code)]
        if entry.status == DELETED:
            return [_candidate(index, entry, TIER_EC, "you gave this EC number, which the nomenclature has deleted", code)]
        out.append(_candidate(
            index, entry, TIER_EC,
            "you gave this EC number, which was transferred: " + "; ".join(
                f"EC {new}" for new in entry.superseded_by), code))
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
                        f"replaces EC {ec}, which was transferred to it", code))
            frontier = following
        return out
    prefix = ".".join(parts)
    label = prefix + ".-" * (4 - len(parts))
    class_name = index.class_name(prefix)
    for ec, entry in index.entries.items():
        if entry.status == ACTIVE and (ec == prefix or ec.startswith(prefix + ".")):
            why = f"a member of EC {label}" + (f" ({class_name})" if class_name else "")
            out.append(_candidate(index, entry, TIER_EC, why, code))
    return out


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
    best: Dict[str, list] = {}

    def note(ec: str, tier: int, why: str, alt: Optional[str] = None, partial: bool = False) -> None:
        held = best.get(ec)
        if held is None or tier < held[0]:
            best[ec] = [tier, why, [alt] if alt else [], partial]
        elif tier == held[0]:
            if alt and alt not in held[2]:
                held[2].append(alt)
            held[3] = held[3] and partial

    # A phrase inside a longer name, or words spread over one, is by
    # construction a fragment of that name. "angiotensin converting enzyme"
    # is the start of "angiotensin-converting enzyme 2", a different enzyme
    # from the one anybody means by it, and "PFK" is half of "ADP-PFK". So
    # these tiers are listed and ranked but never resolved to on their own.
    def fragment(name: _Name) -> bool:
        return True

    phrase = f" {q_loose} "
    for name in tables.names:
        if name.strict == q_strict:
            if name.accepted:
                note(name.ec, TIER_ACCEPTED_EXACT, "accepted name matches exactly")
            else:
                note(name.ec, TIER_ALTERNATIVE_EXACT,
                     f"listed as another name for this enzyme: '{name.text}'", name.text)
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
                     name.text)
        elif phrase in f" {name.loose} ":
            if name.accepted:
                note(name.ec, TIER_ACCEPTED_PHRASE, "your query is a phrase inside the accepted name",
                     partial=fragment(name))
            else:
                note(name.ec, TIER_ALTERNATIVE_PHRASE,
                     f"your query is a phrase inside another name for this enzyme: '{name.text}'", name.text,
                     partial=fragment(name))
        elif q_words <= name.words:
            if name.accepted:
                note(name.ec, TIER_ALL_WORDS, "every word of your query is in the accepted name",
                     partial=fragment(name))
            else:
                note(name.ec, TIER_ALL_WORDS,
                     f"every word of your query is in another name for this enzyme: '{name.text}'", name.text,
                     partial=fragment(name))

    if len(q_strict) >= 3 and " " not in q_strict:
        # The requested organism's entry is quoted first when there is one.
        def own_first(hit: Tuple[str, str]) -> int:
            return 0 if code and hit[1].endswith("_" + code) else 1

        exact = sorted(tables.symbols.get(q_strict, ()), key=own_first)
        for ec, entry_name in exact:
            held = best.get(ec)
            if held is None or held[0] > TIER_SYMBOL:
                # A symbol names a protein only within one organism: LDH1 is
                # a lactate dehydrogenase in bacteria and a lipase in yeast.
                # So it resolves only when it is the requested organism's own.
                own = bool(code) and entry_name.endswith("_" + code)
                best[ec] = [TIER_SYMBOL, f"UniProt entry {entry_name} is listed under this enzyme", [], not own]
        if not exact:
            starting = sorted(
                (hit for symbol, hits in tables.symbols.items() if symbol.startswith(q_strict) for hit in hits),
                key=own_first)
            for ec, entry_name in starting:
                if ec not in best:
                    best[ec] = [
                        TIER_SYMBOL,
                        f"UniProt entries with symbols starting {q_strict.upper()}, such as {entry_name}, "
                        "are listed under this enzyme", [], True]

    found = [
        _candidate(index, index.entries[ec], tier, why, code, matched, partial=partial)
        for ec, (tier, why, matched, partial) in best.items()
    ]
    if found:
        return sorted(found, key=lambda c: _order(c, organism_known))

    limit = _typo_limit(len(q_loose))
    if not limit:
        return []
    n_words = len(q_loose.split())
    for name in tables.names:
        tokens = name.loose.split()
        windows = [name.loose] if len(tokens) <= n_words else [
            " ".join(tokens[i:i + n_words]) for i in range(len(tokens) - n_words + 1)
        ]
        distance = None
        for window in windows:
            d = _within(q_loose, window, limit)
            if d is not None and (distance is None or d < distance):
                distance = d
        if distance is None:
            continue
        held = best.get(name.ec)
        if held is None or distance < held[0]:
            if name.accepted:
                best[name.ec] = [distance, "close to the accepted name: did you mean?", [], False]
            else:
                best[name.ec] = [distance, f"close to another name for this enzyme, '{name.text}': did you mean?",
                                 [name.text], False]
    found = [
        _candidate(index, index.entries[ec], TIER_TYPO, why, code, matched, distance=distance)
        for ec, (distance, why, matched, _partial) in best.items()
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


def recommend(tied: Sequence[Candidate]) -> Optional[Candidate]:
    """The one tied candidate with a protein from the organism, when the others have none."""
    with_protein = [c for c in tied if c.has_organism_protein]
    if len(with_protein) == 1 and len(tied) > 1:
        return with_protein[0]
    return None


def _cautions(index: EnzymeIndex, chosen: Candidate, ranked: Sequence[Candidate]) -> Tuple[str, ...]:
    out: List[str] = []
    code = chosen.organism
    if code and not chosen.has_organism_protein:
        label = organism_label(code)
        text = f"EC {chosen.ec} ({chosen.name}) lists no {label} protein in the nomenclature"
        others = [c for c in ranked if c.ec != chosen.ec and c.has_organism_protein][:3]
        if others:
            text += "; " + "; ".join(
                f"EC {c.ec} ({c.name}), which lists {label} {', '.join(p.symbol for p in c.organism_proteins[:6])}, "
                f"also matches your words" + (f" through '{c.alternative_names[0]}'" if c.alternative_names else "")
                for c in others)
        out.append(text + ". Check this is the enzyme you mean.")
    return tuple(out)


def resolve(
    query: str, organism: Optional[str] = None, *, index: Optional[EnzymeIndex] = None,
) -> Resolution:
    """One enzyme, or the list a person must choose from. Never a guess.

    Resolves only when the best tier holds exactly one enzyme. A tie is
    Ambiguous; `recommended` is set only when exactly one tied enzyme has a
    protein from the requested organism and the others have none. A typo
    match is never resolved. A transferred EC number resolves to its
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
    if best_tier == TIER_TYPO:
        return Ambiguous(
            query=text, candidates=tuple(ranked), reason=f"no enzyme is named {text!r}; these are close",
            suggestions_only=True, organism=code, release=release)
    if len(tied) == 1 and tied[0].partial:
        if tied[0].tier == TIER_SYMBOL:
            reason = (f"{text!r} is the symbol of a protein, not an enzyme name, and a symbol can mean "
                      "a different enzyme in each organism")
        else:
            reason = (f"{text!r} matches only part of one enzyme's name, which is not enough to say it is "
                      "that enzyme")
        return Ambiguous(
            query=text, candidates=tuple(ranked), suggestions_only=True, organism=code, release=release,
            reason=reason)
    if len(tied) == 1:
        only = tied[0]
        return Resolved(ec=only.ec, how=only.why, candidate=only, cautions=_cautions(index, only, ranked))
    kind = "a class of enzymes, not one enzyme" if best_tier == TIER_EC else f"{len(tied)} enzymes"
    return Ambiguous(
        query=text, candidates=tuple(ranked), recommended=recommend(tied),
        reason=f"{text!r} names {kind}" if best_tier != TIER_EC else f"{text!r} is {kind}",
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
    else:
        lines.append(f"{reason}. Best matches first:")
    shown_candidates = candidates[:shown]
    weaker_started = False
    for candidate in shown_candidates:
        if candidate.tier != best and not weaker_started and not ambiguous.suggestions_only:
            lines.append("Weaker matches:")
            weaker_started = True
        mark = "  <- recommended: the only one with a protein from the organism you gave" \
            if ambiguous.recommended is not None and candidate.ec == ambiguous.recommended.ec else ""
        lines.append(f"  {candidate.label()}{mark}")
    if len(candidates) > shown:
        lines.append(f"  and {len(candidates) - shown} more: `caterva enzyme {ambiguous.query!r}` lists them all")
    pick = ambiguous.recommended or candidates[0]
    if ambiguous.suggestions_only:
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
