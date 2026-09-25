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
"""
from __future__ import annotations

from typing import Optional, Tuple

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
}


def normalise_organism(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """(the organism to search for, a sentence saying how it was read).

    The sentence is None when the input was used exactly as typed.
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
        return canonical, f"Read --organism {typed!r} as {canonical}."
    return typed, None


__all__ = ["COMMON_NAMES", "normalise_organism"]
