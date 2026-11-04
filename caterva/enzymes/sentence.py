"""Read the enzyme, organism, substrate and inhibitor a description names.

WHY THIS EXISTS
---------------
`caterva compose "Michaelis-Menten kinetics of human hexokinase on glucose"`
built a model with the motif library's placeholder constants and said "no
enzyme was named", in a report about hexokinase. "hexokinase glucose human",
"yeast alcohol dehydrogenase with ethanol" and "EC 2.7.1.1 glucose" were
refused outright ("No shape in this grammar matches"), although the same
words as `--subject/--organism/--substrate` flags reach BRENDA's Km 6.0 mM
(ref 641068) and kcat 40.1 1/s (ref 739603) for human hexokinase. The
measured value was one flag away and the report pointed the reader at the
wrong place. Found 2026-11-02 by typing the sentences a biochemist types
(ADR 0181).

WHAT IT READS, AND WHAT IT NEVER GUESSES
----------------------------------------
* The ENZYME only through `finder.resolve`, and only when that resolution
  is not a choice and not a stretch: an EC number, an accepted name typed
  exactly, a full alternative name typed exactly, or an abbreviation the
  curated table confirms for one enzyme alone, typed with a capital letter
  and at least three characters long ("PKA", never "ace" in a sentence).
  Never a typo match, a phrase inside a longer name, a stereo-tolerant match
  ("peptidase" is not "L-peptidase") or a gene symbol. A window of words
  that are all class words ("kinase", "protein kinase", "MAP kinase",
  "phosphatase", "dehydrogenase", "enzyme") is not read at all: the
  nomenclature lists "protein kinase" as another name of histidine kinase
  and "MAP kinase" as one of EC 2.7.11.24, and "three step MAP kinase
  cascade" grounded in one of them would be the adjacent-paper miscitation
  of ADR 0076. A name that is several enzymes ("lactate dehydrogenase") is
  returned as `ambiguity` for the caller to refuse with the candidates named,
  never skipped and never picked.
* The ORGANISM through `index.organism_code`, the one normaliser every caller
  shares, so "human", "humans", "human's", "H. sapiens", "E. coli" and
  "yeast" are read the same way here as `--organism` reads them; and a
  binomial written after "in" or "from" ("in Thermus thermophilus"). A near
  spelling where an organism goes ("humna hexokinase") is never read as one,
  and is said (`unread_organism`).
* The SUBSTRATE only as CANDIDATES (`substrate_candidates`). Whether one is
  the substrate is decided by `match_substrate` against the substrates BRENDA
  lists for the resolved enzyme, never here: "glucose" is a substrate of
  hexokinase because BRENDA has Km rows for D-glucose, not because it looks
  like a sugar.
* The INHIBITOR from "inhibited by X", "inhibitor X" and "<enzyme> by X"
  in a sentence about inhibition, as typed; never from a "by" after any
  other word ("measured by fluorescence"). The Ki search then looks it up
  as it looks up `--inhibitor`.
* The SUBSTRATE candidates are whole runs of words, never one word of a
  longer compound name ("glucose" out of "glucose 6-phosphate").

Everything inferred is said, in `notes()`, so the report shows what was read
and a reader can see a wrong reading instead of trusting it. Offline and
deterministic: the finder's committed index, no network.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .finder import (
    TIER_ACCEPTED_EXACT, TIER_ACCEPTED_TOLERANT, TIER_ALTERNATIVE_EXACT, TIER_ALTERNATIVE_TOLERANT,
    TIER_EC,
    Ambiguous, Resolved, _tables, loose_key, read_ec, resolve, strict_key,
)
from .index import ORGANISMS, load_index, organism_code

#: Class words. A window made only of these names a family of enzymes, never
#: one, whatever the nomenclature lists it as another name of: "protein
#: kinase" resolves to histidine kinase (EC 2.7.13.3) and "MAP kinase" to
#: EC 2.7.11.24 by exact alternative name, and "enzyme" to D-enzyme once the
#: D- is set aside. So these windows are neither resolved nor reported as
#: ambiguous: "a kinase and a phosphatase" is a mechanism, not two enzymes.
CLASS_WORDS = frozenset({
    "enzyme", "enzymes", "protein", "proteins", "kinase", "kinases", "phosphatase", "phosphatases",
    "dehydrogenase", "dehydrogenases", "reductase", "oxidase", "synthase", "synthetase", "ligase",
    "isomerase", "mutase", "transferase", "hydrolase", "lyase", "protease", "proteinase", "peptidase",
    "esterase", "nuclease", "polymerase", "atpase", "gtpase", "map", "mapk", "mapkk", "mapkkk",
    "map2k", "map3k", "mitogen", "activated", "serine", "threonine", "tyrosine", "receptor",
    "catalyst", "catalytic", "subunit", "domain", "regulatory", "first", "second", "third",
    "upstream", "downstream", "two", "three", "four", "five", "one", "step", "steps", "tier",
})

#: Words that join phrases. A window never starts or ends on one, and a
#: substrate or inhibitor phrase stops at one.
STOPWORDS = frozenset({
    "a", "an", "the", "of", "on", "with", "for", "and", "using", "by", "in", "from", "at", "to",
    "its", "their", "as", "into", "onto", "via", "under", "over", "or", "between", "that", "which",
    "is", "are", "be", "this", "these", "each", "per", "it", "than",
})

#: Words that describe the model or the request rather than a compound.
#: They are never substrate candidates.
FILLER = frozenset({
    "kinetics", "kinetic", "model", "modelling", "modeling", "simulate", "simulation", "rate",
    "rates", "constant", "constants", "reaction", "reactions", "activity", "michaelis", "menten",
    "michaelis-menten", "turnover", "catalysis", "substrate", "substrates", "measured", "real",
    "values", "value", "km", "kcat", "vmax", "inhibition", "inhibited", "inhibitor", "inhibitors",
    "competitive", "noncompetitive", "non-competitive", "uncompetitive", "mixed", "converting",
    "conversion", "turning", "human", "humans", "cell", "cells", "enzyme", "enzymes",
}) | CLASS_WORDS

#: Organism-table aliases that are also ordinary English words and are
#: therefore not read from a sentence ("man" is an alias of Homo sapiens in
#: the index, for `--organism man`; "a man-made substrate" is not human).
_NOT_IN_A_SENTENCE = frozenset({"man"})

_EC_FULL = re.compile(r"^(?:e\.?c\.?[:#]?)?\d+\.\d+\.\d+\.n?\d+$", re.IGNORECASE)
_EC_WORD = re.compile(r"^e\.?c\.?[:#]?$", re.IGNORECASE)
_EC_PARTIAL = re.compile(r"^\d+(?:\.(?:\d+|-))*\.?$")
_POSSESSIVE = re.compile(r"(?:'s|’s|s'|’)$", re.IGNORECASE)
_EDGE = "\"'“”‘’()[]{}<>,;:!?"
_BINOMIAL = re.compile(r"^[A-Z][a-z]{2,}$")
_EPITHET = re.compile(r"^[a-z]{3,}$")

#: The longest enzyme name, in words, a window is tried at.
MAX_WINDOW = 6


@dataclass(frozen=True)
class SentenceReading:
    """What a description named, each part as typed and as read."""

    text: str
    #: The enzyme span exactly as typed ("human hexokinase" gives "hexokinase").
    enzyme_text: Optional[str] = None
    ec: Optional[str] = None
    enzyme_name: Optional[str] = None
    #: The finder's own reason ("accepted name matches exactly").
    how: Optional[str] = None
    #: The finder's cautions (an enzyme with no protein from the organism).
    cautions: Tuple[str, ...] = ()
    #: The binomial BRENDA files the organism under, and the words read as it.
    organism: Optional[str] = None
    organism_text: Optional[str] = None
    #: The first substrate candidate, and all of them in the order tried.
    substrate_text: Optional[str] = None
    substrate_candidates: Tuple[str, ...] = ()
    inhibitor_text: Optional[str] = None
    #: The finder's `Ambiguous` when the enzyme span names several enzymes.
    ambiguity: Optional[Ambiguous] = None
    #: Other enzymes the description names, beside `ec` (a sentence naming
    #: two is not grounded in either).
    other_enzymes: Tuple[Tuple[str, str, str], ...] = ()
    #: (typed, EC, name, how) for words that name one enzyme only once its
    #: stereo labels are set aside ("lysine oxidase", L-lysine oxidase):
    #: not read as naming it, and said.
    near: Optional[Tuple[str, str, str, str]] = None
    #: Organisms the description names when it names more than one.
    organisms_named: Tuple[Tuple[str, str], ...] = ()
    #: (typed, organism name it is close to) for a word placed where an
    #: organism goes that is a near spelling of one ("humna"), when no
    #: organism was read. Never read as that organism: said.
    unread_organism: Optional[Tuple[str, str]] = None
    #: The description with the enzyme, organism and inhibitor spans removed.
    remainder: str = ""

    @property
    def names_enzyme(self) -> bool:
        """True when the description names an enzyme, resolved or ambiguous."""
        return self.ec is not None or self.ambiguity is not None

    def enzyme_note(self) -> Optional[str]:
        if self.ec is None:
            return None
        name = f" ({self.enzyme_name})" if self.enzyme_name else ""
        how = self.how or "read from your description"
        text = f"Read {self.enzyme_text!r} in your description as EC {self.ec}{name}: {how}."
        if self.cautions:
            text += " " + " ".join(self.cautions)
        return text

    def near_note(self) -> str:
        typed, ec, name, _ = self.near
        return (f"The words {typed!r} in your description match EC {ec} ({name}) only once stereo labels "
                f"or a parenthesised word are set aside, which is not taken as naming it (pass --subject "
                f"{ec} if it is the enzyme you mean).")

    def organism_note(self) -> Optional[str]:
        if self.organism is None:
            return None
        if self.organism_text == self.organism:
            return f"Read the organism {self.organism} from your description."
        return f"Read {self.organism_text!r} in your description as {self.organism}."

    def unread_organism_note(self) -> str:
        typed, close = self.unread_organism
        return (f"{typed!r} in your description was not read as an organism: it is close to {close!r}, "
                f"but a near spelling is never taken as one, so no organism was read from your "
                f"description (pass --organism if you mean one).")

    def notes(self) -> List[str]:
        """The sentences a report prints: what was read, as what."""
        out = [n for n in (self.enzyme_note(), self.organism_note()) if n]
        if self.inhibitor_text:
            out.append(f"Read {self.inhibitor_text!r} in your description as the inhibitor.")
        if len(self.organisms_named) > 1:
            out.append("Your description names " + " and ".join(
                f"{typed!r} ({binomial})" for typed, binomial in self.organisms_named)
                + "; no organism was read from it, because choosing one would be a guess.")
        if self.unread_organism is not None:
            out.append(self.unread_organism_note())
        if self.near is not None and self.ec is None:
            out.append(self.near_note())
        if self.other_enzymes:
            out.append("Your description also names " + "; ".join(
                f"{typed!r} (EC {ec}, {name})" for typed, ec, name in self.other_enzymes)
                + ", so no enzyme was read from it: a model grounded in one of several named enzymes "
                "would carry constants for a protein the sentence did not single out.")
        return out


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------


@dataclass
class _Token:
    raw: str       # as typed, edges stripped
    low: str       # lower case
    start: int
    end: int
    used: bool = False


def _tokens(text: str) -> List[_Token]:
    out: List[_Token] = []
    for match in re.finditer(r"\S+", text):
        raw = match.group(0)
        start, end = match.start(), match.end()
        # A bracket is an edge only when it is unmatched in the word:
        # "(-)-huperzine" and "Na(+)/K(+)-ATPase" keep theirs, "(human)"
        # loses both.
        while raw and raw[0] in _EDGE and not _balanced_open(raw):
            raw, start = raw[1:], start + 1
        while raw and (
                (raw[-1] in _EDGE and not _balanced_close(raw))
                or (raw[-1] == "." and not _keeps_dot(raw))):
            raw, end = raw[:-1], end - 1
        if raw:
            out.append(_Token(raw, raw.lower(), start, end))
    return out


_PAIRS = {"(": ")", "[": "]", "{": "}"}


def _balanced_open(raw: str) -> bool:
    """A leading bracket closed inside the word ("(-)-huperzine")."""
    close = _PAIRS.get(raw[0])
    return close is not None and raw.count(raw[0]) <= raw.count(close) and raw.find(close) < len(raw) - 1


def _balanced_close(raw: str) -> bool:
    """A trailing bracket opened inside the word ("Na(+)")."""
    opening = {v: k for k, v in _PAIRS.items()}.get(raw[-1])
    return opening is not None and raw.count(raw[-1]) <= raw.count(opening)


def _joins(token: "_Token") -> bool:
    """A joining word. A capital letter on its own is a name's ("huperzine A",
    "pepsin A"), not the article."""
    return token.low in STOPWORDS and not (len(token.raw) == 1 and token.raw.isupper())


def _keeps_dot(raw: str) -> bool:
    """A trailing dot that belongs to the word: "E." of "E. coli", "e.c.", "2.7.1.-"."""
    return bool(re.fullmatch(r"[A-Za-z]\.|e\.c\.|\d[\d.\-]*\.", raw, re.IGNORECASE))


def _organism_key(words: Sequence[_Token]) -> str:
    joined = " ".join(w.raw for w in words)
    return _POSSESSIVE.sub("", joined)


# ---------------------------------------------------------------------------
# The three readings
# ---------------------------------------------------------------------------


def _read_organism(tokens: List[_Token]) -> List[Tuple[int, int, str, str]]:
    """(first, last+1, typed, binomial) for every organism named, longest first."""
    found: List[Tuple[int, int, str, str]] = []
    taken = [False] * len(tokens)
    for size in range(4, 0, -1):
        for i in range(len(tokens) - size + 1):
            if any(taken[i:i + size]):
                continue
            words = tokens[i:i + size]
            key = _organism_key(words)
            if key.lower() in _NOT_IN_A_SENTENCE or key.lower() in STOPWORDS:
                continue
            code = organism_code(key)
            if code is None:
                continue
            found.append((i, i + size, " ".join(w.raw for w in words), ORGANISMS[code][0]))
            for k in range(i, i + size):
                taken[k] = True
    # A binomial the table does not hold, written where an organism goes:
    # "in Thermus thermophilus". Only after "in" or "from", because a
    # capitalised word and a lower-case one are also how a sentence starts
    # ("Competitive inhibition of ...").
    for i in range(1, len(tokens) - 1):
        if taken[i] or taken[i + 1] or tokens[i - 1].low not in ("in", "from"):
            continue
        genus, epithet = tokens[i].raw, _POSSESSIVE.sub("", tokens[i + 1].raw)
        if _BINOMIAL.match(genus) and _EPITHET.match(epithet) and epithet not in STOPWORDS | FILLER:
            found.append((i, i + 2, f"{genus} {epithet}", f"{genus} {epithet}"))
            taken[i] = taken[i + 1] = True
    return sorted(found)


def _organism_words() -> List[str]:
    """Every one-word name the organism table reads, lower case."""
    out = set()
    for binomial, common, aliases in ORGANISMS.values():
        for name in (binomial, common, *aliases):
            if " " not in name and "." not in name and len(name) >= 3:
                out.add(name.lower())
    return sorted(out)


def _misspelt_organism(tokens: List[_Token]) -> Optional[Tuple[str, str]]:
    """(typed, close name) for an unread word where an organism goes -- just
    before a word read as the enzyme, or after "in"/"from" -- that is a near
    spelling of a one-word organism name.

    "Michaelis-Menten kinetics of humna hexokinase on glucose" read no
    organism and said nothing about 'humna': the search then ranked without
    one and the report never showed that a word meant as the organism had
    gone unread. It is still never READ as human: a near spelling is a
    guess, and the organism decides whose constants are cited. It is said.
    """
    import difflib

    names = _organism_words()
    for i, token in enumerate(tokens):
        if token.used or token.low in STOPWORDS or token.low in FILLER or len(token.low) < 3:
            continue
        before_enzyme = i + 1 < len(tokens) and tokens[i + 1].used
        after_in = i > 0 and tokens[i - 1].low in ("in", "from")
        if not (before_enzyme or after_in):
            continue
        close = difflib.get_close_matches(token.low, names, n=1, cutoff=0.8)
        if close:
            return token.raw, close[0]
    return None


def _is_class_window(words: Sequence[_Token]) -> bool:
    return all(w.low.strip("-") in CLASS_WORDS or w.low in STOPWORDS for w in words)


def _acceptable(result: Resolved, typed: str) -> bool:
    """A resolution that is not a stretch: see the module docstring."""
    candidate = result.candidate
    if candidate is None:
        return False
    if candidate.tier == TIER_EC:
        return True
    if candidate.partial or candidate.via != "name":
        return False
    if candidate.tier not in (TIER_ACCEPTED_EXACT, TIER_ALTERNATIVE_EXACT):
        return False
    if candidate.abbreviation:
        # "ACE" and "PKA" are confirmed abbreviations; "ace" in a sentence is
        # a word. Two letters are never enough.
        letters = re.sub(r"[^0-9A-Za-z]", "", typed)
        return candidate.confirmed and len(letters) >= 3 and any(ch.isupper() for ch in typed)
    return True


def _near(result: object) -> bool:
    """A unique resolution the reader does not accept: an accepted or other
    name met only once stereo labels or a glued parenthesis are set aside."""
    candidate = getattr(result, "candidate", None)
    return (isinstance(result, Resolved) and candidate is not None and not candidate.partial
            and candidate.via == "name" and candidate.tier in (TIER_ACCEPTED_TOLERANT, TIER_ALTERNATIVE_TOLERANT))


def _reportable(result: Ambiguous) -> bool:
    """An ambiguity worth refusing over: several enzymes whose NAMES the words
    are, not a phrase inside many names or a did-you-mean."""
    if result.suggestions_only or result.confirm_only or not result.candidates:
        return False
    best = result.candidates[0]
    tied = [c for c in result.candidates if c.tier == best.tier]
    if best.tier == TIER_EC:
        return True
    return (best.tier <= TIER_ALTERNATIVE_TOLERANT and all(not c.partial and c.via == "name" for c in tied))


def _name_keys() -> frozenset:
    """Every key an enzyme name can be met by: strict, loose and bare.

    `resolve` scans the whole nomenclature on each call (about 0.2 s), so a
    window is resolved only when some name has its key: a sentence of ten
    words has some forty windows, and every one of them going to the finder
    made a plain-language compose seconds slower than a flag.
    """
    tables = _tables(load_index())
    keys = set()
    for name in tables.names:
        keys.update((name.strict, name.loose, name.bare))
    return frozenset(keys)


_KEYS: Optional[frozenset] = None


def _could_be_a_name(text: str) -> bool:
    global _KEYS
    if _KEYS is None:
        _KEYS = _name_keys()
    return strict_key(text) in _KEYS or loose_key(text) in _KEYS


def _read_ec(tokens: List[_Token]) -> List[Tuple[int, int, str]]:
    """(first, last+1, typed) of every EC number written: "EC 2.7.1.1", "2.7.1.1",
    "EC:2.7.1.1". A bare number needs four parts ("2.5" is a concentration);
    a class needs the EC in front of it ("EC 2.7.1")."""
    out: List[Tuple[int, int, str]] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if _EC_FULL.match(token.raw):
            out.append((i, i + 1, token.raw))
        elif _EC_WORD.match(token.raw) and i + 1 < len(tokens) and _EC_PARTIAL.match(tokens[i + 1].raw):
            out.append((i, i + 2, f"{token.raw} {tokens[i + 1].raw}"))
            i += 1
        i += 1
    return out


def _windows(tokens: List[_Token]):
    """Unconsumed word windows, longest first, never starting or ending on a
    joining word."""
    for size in range(min(MAX_WINDOW, len(tokens)), 0, -1):
        for i in range(len(tokens) - size + 1):
            words = tokens[i:i + size]
            if any(w.used for w in words):
                continue
            if _joins(words[0]) or _joins(words[-1]):
                continue
            yield i, i + size, words


def _phrase_after(tokens: List[_Token], i: int) -> Optional[Tuple[int, int]]:
    """The run of unconsumed, non-joining words starting at i."""
    j = i
    while j < len(tokens) and not tokens[j].used and not _joins(tokens[j]):
        j += 1
    return (i, j) if j > i else None


def _read_inhibitor(tokens: List[_Token]) -> Optional[Tuple[int, int]]:
    lows = [t.low for t in tokens]
    about_inhibition = any(w.startswith("inhibit") for w in lows)
    for i, word in enumerate(lows):
        start = None
        if word in ("inhibitor", "inhibitors") and i + 1 < len(tokens) and not _joins(tokens[i + 1]):
            start = i + 1
        elif (word == "by" and about_inhibition and i > 0
              and (lows[i - 1].startswith("inhibit") or tokens[i - 1].used)):
            # Only "inhibited by X", "inhibition by X" or "<enzyme or
            # organism> by X". Any "by" after an inhibition word read
            # "competitive inhibition of hexokinase on glucose measured by
            # fluorescence" as inhibited by fluorescence, and the report said
            # so; the Ki stayed a placeholder only because BRENDA has no
            # "fluorescence" row.
            start = i + 1
        if start is None:
            continue
        span = _phrase_after(tokens, start)
        if span is not None:
            words = [t.low for t in tokens[span[0]:span[1]]]
            if not all(w in FILLER for w in words):
                return span
    return None


def read_sentence(text: str, organism: Optional[str] = None) -> SentenceReading:
    """What `text` names. `organism` (anything `organism_code` reads) ranks the
    enzyme candidates, as `--organism` does; the sentence's own organism is
    used when none is given."""
    text = " ".join((text or "").split())
    tokens = _tokens(text)
    if not tokens:
        return SentenceReading(text=text, remainder=text)

    organisms = _read_organism(tokens)
    distinct = {binomial for _, _, _, binomial in organisms}
    read_organism: Optional[Tuple[str, str]] = None
    for first, last, typed, binomial in organisms:
        for k in range(first, last):
            tokens[k].used = True
    if len(distinct) == 1:
        _, _, typed, binomial = organisms[0]
        read_organism = (typed, binomial)
    rank_by = organism or (read_organism[1] if read_organism else None)

    hits: List[Tuple[int, int, str, Resolved]] = []
    ambiguity: Optional[Ambiguous] = None
    ambiguity_text: Optional[str] = None
    near: Optional[Tuple[str, str, str, str]] = None
    for first, last, typed in _read_ec(tokens):
        result = resolve(typed, rank_by)
        if isinstance(result, Resolved) and _acceptable(result, typed):
            hits.append((first, last, typed, result))
        elif isinstance(result, Ambiguous) and result.candidates and ambiguity is None:
            ambiguity, ambiguity_text = result, typed
        for k in range(first, last):
            tokens[k].used = True

    for first, last, words in _windows(tokens):
        if any(w.used for w in words):
            continue  # consumed by a longer window found earlier at this size
        if _is_class_window(words):
            continue
        typed = text[words[0].start:words[-1].end]
        if not _could_be_a_name(typed):
            continue
        result = resolve(typed, rank_by)
        if isinstance(result, Resolved) and _acceptable(result, typed):
            hits.append((first, last, typed, result))
        elif isinstance(result, Ambiguous) and _reportable(result):
            if ambiguity is None:
                ambiguity, ambiguity_text = result, typed
        elif _near(result):
            # "lysine oxidase" is L-lysine oxidase only once the L- is set
            # aside. Not read as naming it, and not silently passed over:
            # the report says which enzyme it is close to and the flag
            # that takes it.
            if near is None:
                near = (typed, result.ec, result.candidate.name, result.how)
        else:
            continue
        for k in range(first, last):
            tokens[k].used = True

    enzyme: Optional[Tuple[str, Resolved]] = None
    others: List[Tuple[str, str, str]] = []
    distinct_ecs = []
    for _, _, typed, result in sorted(hits, key=lambda hit: hit[0]):
        if result.ec not in [ec for ec, _ in distinct_ecs]:
            distinct_ecs.append((result.ec, (typed, result)))
    if len(distinct_ecs) == 1 and ambiguity is None:
        enzyme = distinct_ecs[0][1]
    elif distinct_ecs:
        # Two enzymes named, or one named and another ambiguous: neither is
        # the subject. The ambiguity, if any, is still reported.
        for ec, (typed, result) in distinct_ecs:
            name = result.candidate.name if result.candidate else ""
            others.append((typed, ec, name))

    unread_organism = _misspelt_organism(tokens) if not organisms and (hits or ambiguity) else None
    inhibitor_span = _read_inhibitor(tokens)
    inhibitor_text = None
    if inhibitor_span is not None:
        inhibitor_text = text[tokens[inhibitor_span[0]].start:tokens[inhibitor_span[1] - 1].end]
        for k in range(*inhibitor_span):
            tokens[k].used = True

    candidates: List[str] = []

    def add(span: Optional[Tuple[int, int]]) -> None:
        if span is None:
            return
        # A candidate is a whole run of non-filler words, never one word
        # taken out of a longer run. Each kept word used to be tried on its
        # own after the phrase, so "glucose 6-phosphate", "2 deoxy glucose"
        # and "glucose analogues" matched nothing whole and then 'glucose'
        # matched D-glucose: the report carried D-glucose's Km 6.0 mM (ref
        # 641068) as the answer for a different compound, and "fructose
        # 1,6-bisphosphate" and "N-acetyl glucosamine" got D-fructose's and
        # D-glucosamine's. A filler word ("kinetics", "rate") does separate
        # runs, because it describes the request, not the compound: "glucose
        # kinetics" is "glucose". A run that matches nothing whole takes no
        # substrate, and the refusal that lists BRENDA's substrates runs.
        run: List[_Token] = []
        for w in list(tokens[span[0]:span[1]]) + [None]:
            if w is not None and w.low not in FILLER:
                run.append(w)
                continue
            if run:
                phrase = text[run[0].start:run[-1].end]
                if phrase not in candidates:
                    candidates.append(phrase)
            run = []

    for i, token in enumerate(tokens):
        if token.low in ("with", "on", "for", "of", "and", "using") and not token.used:
            add(_phrase_after(tokens, i + 1))
    i = 0
    while i < len(tokens):
        span = _phrase_after(tokens, i)
        if span is None:
            i += 1
            continue
        add(span)
        i = span[1]

    remainder = " ".join(t.raw for t in tokens if not t.used)
    if enzyme is not None:
        typed, result = enzyme
        return SentenceReading(
            text=text, enzyme_text=typed, ec=result.ec,
            enzyme_name=result.candidate.name if result.candidate else None,
            how=result.how, cautions=tuple(result.cautions),
            organism=read_organism[1] if read_organism else None,
            organism_text=read_organism[0] if read_organism else None,
            substrate_text=candidates[0] if candidates else None,
            substrate_candidates=tuple(candidates), inhibitor_text=inhibitor_text,
            organisms_named=tuple((t, b) for _, _, t, b in organisms) if len(distinct) > 1 else (),
            unread_organism=unread_organism, remainder=remainder)
    return SentenceReading(near=near if ambiguity is None and not others else None,
        text=text, enzyme_text=ambiguity_text if ambiguity is not None else None,
        organism=read_organism[1] if read_organism else None,
        organism_text=read_organism[0] if read_organism else None,
        substrate_text=candidates[0] if candidates else None,
        substrate_candidates=tuple(candidates), inhibitor_text=inhibitor_text,
        ambiguity=ambiguity, other_enzymes=tuple(others) if ambiguity is None else (),
        organisms_named=tuple((t, b) for _, _, t, b in organisms) if len(distinct) > 1 else (),
        unread_organism=unread_organism, remainder=remainder)


# ---------------------------------------------------------------------------
# The substrate, against what BRENDA lists
# ---------------------------------------------------------------------------

#: Stereo and anomer prefixes set aside when the typed word is compared with
#: BRENDA's name: "glucose" against "D-glucose", "lactose" against
#: "beta-lactose". Only at the start, and only these.
_STEREO_PREFIX = re.compile(
    r"^(?:d|l|dl|alpha|beta|α|β|\(s\)|\(r\)|\(\+\)|\(-\)|\(±\)|meso)-", re.IGNORECASE)


def _without_stereo(name: str) -> str:
    previous = None
    while previous != name:
        previous, name = name, _STEREO_PREFIX.sub("", name.strip())
    return strict_key(name)


@dataclass(frozen=True)
class SubstrateMatch:
    """What `match_substrate` made of the candidates."""

    #: BRENDA's name for the substrate, when exactly one matched.
    name: Optional[str] = None
    #: The words of the description it was read from.
    typed: Optional[str] = None
    #: True when the match needed a stereo or anomer prefix set aside.
    prefix_set_aside: bool = False
    #: (typed, BRENDA name) for every match, when there was more than one.
    rivals: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)


def match_substrate(candidates: Sequence[str], listed: Sequence[str]) -> SubstrateMatch:
    """The one substrate BRENDA lists that the description's words name, or nothing.

    A candidate is accepted when it IS a name BRENDA lists, case and spacing
    aside; failing that, when exactly one listed name is the candidate with
    a D-/L-/alpha-/beta-/(S)-/(R)- prefix set aside ("glucose" is
    "D-glucose" for hexokinase, where BRENDA lists no other glucose). Two
    listed names that both fit ("alpha-D-glucose" and "beta-D-glucose" for
    "glucose") are a choice, and so are two candidates that each name a
    different substrate ("glucose and ATP"): either returns no name and the
    rivals, so the caller's refusal, which lists BRENDA's substrates, runs.
    """
    by_key: Dict[str, List[str]] = {}
    stripped: Dict[str, List[str]] = {}
    for name in listed:
        by_key.setdefault(strict_key(name), []).append(name)
        stripped.setdefault(_without_stereo(name), []).append(name)
    found: List[Tuple[str, str, bool]] = []
    for typed in candidates:
        key = strict_key(typed)
        if not key:
            continue
        exact = by_key.get(key)
        if exact:
            if len(set(exact)) == 1:
                found.append((typed, exact[0], False))
            continue
        loose = sorted(set(stripped.get(_without_stereo(typed), [])))
        if len(loose) == 1:
            found.append((typed, loose[0], True))
        elif len(loose) > 1:
            found.extend((typed, name, True) for name in loose)
    names = sorted({name for _, name, _ in found})
    if len(names) == 1:
        typed, name, prefix = next(f for f in found if f[1] == names[0])
        return SubstrateMatch(name=name, typed=typed, prefix_set_aside=prefix)
    return SubstrateMatch(rivals=tuple((t, n) for t, n, _ in found))


__all__ = [
    "CLASS_WORDS", "SentenceReading", "SubstrateMatch", "match_substrate", "read_sentence",
]
