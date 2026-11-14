"""Read an organism the way a person types it, and say how it was read.

WHY THIS EXISTS
---------------
BRENDA names organisms by binomial with exact case. `--organism human` and
`--organism "homo sapiens"` both searched for an organism no row carries,
and the report said "no value in the organism requested" -- which reads
as a fact about the science when it was a fact about spelling. Found
2026-09-25 by running the queries a new user types.

WHAT IT REFUSES TO DO
---------------------
Guess. The common names are a short explicit table of model organisms,
each of which means one species in a biochemistry lab. "Monkey", "fish"
or "bacteria" are not in it, because each is many species, and they pass
through unchanged so the search reports what it found for them. Every
rewrite is returned as a sentence for the report, so the reader sees what
was actually searched.

`caterva.enzymes.index.organism_code` is consulted after the table, so every
spelling the enzyme finder reads ("H. sapiens", "S. cerevisiae") reaches the
same binomial here; the plain-language reader (`caterva.enzymes.sentence`)
uses that same function, so a description and a flag are read alike.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

#: Common name -> the binomial BRENDA uses. One species each, on purpose.
COMMON_NAMES = {
    "human": "Homo sapiens",
    "humans": "Homo sapiens",
    "mouse": "Mus musculus",
    "rat": "Rattus norvegicus",
    "yeast": "Saccharomyces cerevisiae",
    "baker's yeast": "Saccharomyces cerevisiae",
    "budding yeast": "Saccharomyces cerevisiae",
    "fission yeast": "Schizosaccharomyces pombe",
    "e. coli": "Escherichia coli",
    "e.coli": "Escherichia coli",
    "ecoli": "Escherichia coli",
    "rabbit": "Oryctolagus cuniculus",
    "cow": "Bos taurus",
    "cattle": "Bos taurus",
    "bovine": "Bos taurus",
    "pig": "Sus scrofa",
    "porcine": "Sus scrofa",
    "chicken": "Gallus gallus",
    "zebrafish": "Danio rerio",
    "fruit fly": "Drosophila melanogaster",
    "drosophila": "Drosophila melanogaster",
    "arabidopsis": "Arabidopsis thaliana",
    "c. elegans": "Caenorhabditis elegans",
    "b. subtilis": "Bacillus subtilis",
    # One species, and not a pig: "guinea pig" must never reach "pig".
    "guinea pig": "Cavia porcellus",
    "guinea pigs": "Cavia porcellus",
    # BRENDA's organism for HIV-1 protease and reverse transcriptase rows
    # (checked on the page for 3.4.23.16, 2026-11-11). Not plain "HIV",
    # which is HIV-1 or HIV-2.
    "hiv-1": "Human immunodeficiency virus 1",
    "hiv 1": "Human immunodeficiency virus 1",
    "hiv1": "Human immunodeficiency virus 1",
    # BRENDA's organism for herpes thymidine kinase rows (EC 2.7.1.21):
    # "herpes simplex virus thymidine kinase with ganciclovir" was told no
    # organism was named (fourth round of the real-values review).
    "herpes simplex virus": "Herpes simplex virus",
    "hsv": "Herpes simplex virus",
    "hsv-1": "Herpes simplex virus",
    "hsv1": "Herpes simplex virus",
    # The name every textbook uses for the source of tryptophan synthase;
    # BRENDA files it under the serovar name (EC 4.2.1.20, 31 Km rows, read
    # 2026-11-14). The abbreviations are read here; the name written out is
    # read against the page's own organisms in caterva.compose.__main__.
    "s. typhimurium": "Salmonella enterica subsp. enterica serovar Typhimurium",
    "s typhimurium": "Salmonella enterica subsp. enterica serovar Typhimurium",
}


#: A genus written alone that means one species in a biochemistry lab: only
#: Homo, whose one extant species is ours. "Mus", "Bacillus" or
#: "Saccharomyces" alone are each many species, and are not read as the one
#: this table happens to hold.
GENUS_ALONE = {"homo": "Homo sapiens"}


def known_binomials() -> Tuple[str, ...]:
    """Every binomial the readers know, from the enzyme index and the table above."""
    from caterva.enzymes.index import ORGANISMS

    found = {binomial for binomial, _, _ in ORGANISMS.values()} | set(COMMON_NAMES.values())
    # Two words each: "Human immunodeficiency virus 1" is a name, not a
    # binomial, and is read only through the common names above.
    return tuple(sorted(b for b in found if len(b.split()) == 2))


def _words(typed: str) -> List[str]:
    """"H. sapiens", "H.sapiens" and "H sapiens" are the words H and sapiens."""
    return [w for w in re.split(r"[\s.]+", typed) if w]


def _abbreviation_matches(typed: str) -> Optional[List[str]]:
    """The known binomials a short or abbreviated spelling can be, or None
    when the spelling is not that kind of thing.

    "Homo S", "homo sap", "H sapiens", "E coli" and "S cerevisiae" are a
    genus and an epithet each written as a prefix of the real one; at least
    one of the two must be written in full, so "S c" is never read. The
    match ignores case, and is a list so that a caller can tell one reading
    from several.
    """
    words = _words(typed)
    if len(words) != 2 or not all(w.isalpha() for w in words):
        return None
    genus, epithet = (w.lower() for w in words)
    found = []
    for binomial in known_binomials():
        g, e = binomial.lower().split(" ", 1)
        if " " in e:
            continue
        if g.startswith(genus) and e.startswith(epithet) and (genus == g or epithet == e):
            found.append(binomial)
    return found


def _close_to(typed: str) -> List[str]:
    """The known binomials that share a genus initial or a genus prefix with
    `typed`, for the note that says a spelling was not recognised."""
    words = _words(typed)
    if not words:
        return []
    head = words[0].lower()
    return [b for b in known_binomials() if b.lower().startswith(head) or b.lower().split()[0].startswith(head)]


def normalise_organism(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """(the organism to search for, a sentence saying how it was read).

    The sentence is None when the input was used exactly as typed.

    What it reads, in order: the common names above ("human", "yeast",
    "guinea pig" -- which is never "pig"); every spelling the enzyme index
    reads ("H. sapiens", "S. cerevisiae", "mice"); a genus and epithet
    written as prefixes of a known binomial with one of the two in full
    ("Homo S", "homo sap", "H sapiens", "E coli"); "Homo" alone. A spelling
    that could be several known organisms ("S.", "S. c") or none is
    returned EXACTLY as typed, with a note naming the closest known
    binomials: it is never case-mangled into something that looks like an
    organism. `--organism "Homo S"` used to come back as "Homo s", which
    matched every human BRENDA row by substring and printed "literature
    (Homo s)" in a cited table (found 2026-11-11). A two-word name written
    out in full that no table holds ("thermus thermophilus") only has its
    case fixed, genus capital and epithet lower, because that is how BRENDA
    files it and both words are the reader's own.
    """
    if text is None:
        return None, None
    typed = " ".join(text.split())
    if not typed:
        return None, None
    common = COMMON_NAMES.get(typed.lower())
    if common is not None:
        return common, f"Read --organism {typed!r} as {common}."
    words = typed.split(" ")
    # The enzyme index's `organism_code` is the normaliser every caller
    # shares, and it reads "H. sapiens", "S. cerevisiae", "mice" and
    # "porcine", which the table above does not: `--organism "H. sapiens"`
    # was passed to BRENDA as typed and matched no row, while the enzyme
    # finder in the same run read it as human. A binomial already written
    # out is left to the path below, so a strain after it is kept.
    from caterva.enzymes.index import ORGANISMS, organism_code

    code = organism_code(typed)
    if code is not None:
        binomial = ORGANISMS[code][0]
        if " ".join(words[:2]).lower() != binomial.lower():
            return binomial, f"Read --organism {typed!r} as {binomial}."
    else:
        genus_alone = GENUS_ALONE.get(typed.lower().rstrip("."))
        if genus_alone is not None:
            return genus_alone, f"Read --organism {typed!r} as {genus_alone}."
        matches = _abbreviation_matches(typed)
        if matches is not None and len(matches) == 1:
            return matches[0], f"Read --organism {typed!r} as {matches[0]}."
        head = re.match(r"^(\S+\.?\s*\S+?)\s+(\S.*)$", typed)
        if matches is None and head is not None:
            # "E. coli BL21", "S cerevisiae S288C": an abbreviated binomial
            # and a strain. The binomial is read as above; the strain after
            # it is kept exactly as typed, as for "Escherichia coli K-12".
            first = _abbreviation_matches(head.group(1))
            if first is not None and len(first) == 1:
                read = f"{first[0]} {head.group(2)}"
                return read, (None if read == typed else f"Read --organism {typed!r} as {read}.")
        if matches or not _full_binomial(typed):
            return typed, _not_recognised(typed, matches or _close_to(typed))
    # A binomial is "Genus species": capital genus, lower-case epithet.
    # Only the first two words are touched, and only when alphabetic, so a
    # strain or serovar after them is left exactly as written.
    fixed = list(words)
    if fixed[0].isalpha():
        fixed[0] = fixed[0][:1].upper() + fixed[0][1:].lower()
    if len(fixed) > 1 and fixed[1].isalpha():
        fixed[1] = fixed[1].lower()
    canonical = " ".join(fixed)
    if canonical != typed:
        # Not "Read ... as": nothing was recognised. "electric eel" came back
        # "Read --organism 'electric eel' as Electric eel", which a reader
        # takes for a match, and the search then said BRENDA held no row "in
        # Electric eel" (round-1 finding F04).
        return canonical, (f"--organism {typed!r} is not an organism Caterva knows; it was searched as "
                           f"{canonical!r}, written as BRENDA writes a binomial (genus capitalised, epithet "
                           "lower case). If it is a common name, pass the binomial instead (for example "
                           "--organism \"Electrophorus electricus\" for electric eel).")
    return typed, None


def _full_binomial(typed: str) -> bool:
    """Two or more words, the first two alphabetic and at least three letters
    each: a name written out, whose case may be fixed. "Homo s", "S. c" and
    a single word are not."""
    words = typed.split(" ")
    return len(words) >= 2 and all(w.isalpha() and len(w) >= 3 for w in words[:2])


def _not_recognised(typed: str, close: List[str]) -> str:
    text = (f"--organism {typed!r} was not recognised as one organism, so it was used exactly as typed; "
            "BRENDA rows are matched on the organism's text, so part of a name can match several organisms")
    if close:
        shown = close[:6]
        text += (". The closest organisms Caterva knows are " + ", ".join(shown)
                 + (f", and {len(close) - len(shown)} more" if len(close) > len(shown) else ""))
    return text + ". Pass the full binomial (for example --organism \"Homo sapiens\") to search one."


__all__ = ["COMMON_NAMES", "GENUS_ALONE", "known_binomials", "normalise_organism"]
