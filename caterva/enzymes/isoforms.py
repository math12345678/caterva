"""Which names mean one protein, for the engine that reads papers' isoform names.

WHY THIS EXISTS
---------------
`caterva compose --isoform HK2` leaves the BRENDA rows unchanged, because the
engine reads a row's commentary ("hexokinase II") and compares the isoform
asked for with it, and "HK2" is not "hexokinase II" to a comparison that
ignores only case and separators. The notice and the Studio chooser offered
UniProt entry-name mnemonics (HXK2, AOFA, LDH6A) that no paper writes, so
choosing one of the offered names did nothing, and said nothing.

This file says which names are one protein. For every protein the enzyme
index lists with the others of its EC number in human, mouse, yeast and
E. coli K-12, it gathers the names UniProtKB gives that protein
(protein_names.py): the gene symbol, the short names, the entry-name stem and
the names ending in a number or letter ("Hexokinase type II"). Two names are
one isoform when some protein carries both, read the way `bind.core.read_isoform`
reads a row: "HK2", "HXK2", "HK II", "hexokinase type II" and
"hexokinase-2" are human hexokinase 2; "HK-I" is human hexokinase 1.

WHAT IT DOES NOT SAY
--------------------
That a paper's "hexokinase II" is the protein it names here: that is UniProtKB's
naming of the protein, not a claim about the paper, and the comparison is only
between rows BRENDA files under one EC number for one organism. A name no
protein carries is compared as before, by spelling alone, and a request the
engine cannot match to anything is said so by `can_match`.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from .index import load_index
from .protein_names import NAMES_PATH, info

#: Words that are not part of an isoform's name.
_FILLER = re.compile(r"\b(?:type|isozyme|isoenzyme|isoform|form)\b", re.IGNORECASE)
_NUMBERED = re.compile(r"(?:\s|-)(?:[IVX]{1,4}|\d{1,2}[A-Za-z]?|[A-Z])$")
_MAX_NAME = 45


def _variants(text: str) -> List[str]:
    out = [text]
    stripped = " ".join(_FILLER.sub(" ", text).split())
    if stripped != text:
        out.append(stripped)
    for base in list(out):
        spaced = re.sub(r"-(?=[A-Za-z0-9]{1,3}$)", " ", base)
        if spaced != base:
            out.append(spaced)
    return out


def keys_of(name: str) -> Set[str]:
    """The comparison keys one name gives: its own and every isoform name the reader finds in it."""
    from caterva.bind.core import isoform_key, isoform_names, read_isoform

    keys: Set[str] = set()
    for variant in _variants(name):
        keys.add(isoform_key(variant))
        reading = read_isoform(variant)
        for part in isoform_names(reading):
            keys.add(isoform_key(part))
    return {k for k in keys if k}


def _protein_names(accession: str, entry_stem: str) -> List[str]:
    found = info(accession)
    names: List[str] = []
    if found is not None and found.gene:
        names.append(found.gene)
    names.append(entry_stem)
    if found is None:
        return names
    for text in found.names:
        if text == found.gene:
            continue
        if len(text) <= _MAX_NAME and (len(text) <= 20 or _NUMBERED.search(text)):
            names.append(text)
    if found.name and len(found.name) <= _MAX_NAME and _NUMBERED.search(found.name):
        names.append(found.name)
    return names


@lru_cache(maxsize=1)
def _classes() -> Dict[str, FrozenSet[str]]:
    """key -> the proteins (accessions) that carry a name with that key."""
    if not NAMES_PATH.exists():
        return {}
    index = load_index()
    codes = ("HUMAN", "MOUSE", "YEAST", "ECOLI")
    gathered: Dict[str, Set[str]] = {}
    seen: Set[str] = set()
    for entry in index.entries.values():
        for code in codes:
            proteins = entry.proteins.get(code, ())
            if len(proteins) < 2:
                continue
            for protein in proteins:
                if protein.accession in seen:
                    continue
                seen.add(protein.accession)
                for name in _protein_names(protein.accession, protein.symbol):
                    for key in keys_of(name):
                        gathered.setdefault(key, set()).add(protein.accession)
    return {key: frozenset(value) for key, value in gathered.items()}


def equivalent(key_a: str, key_b: str) -> bool:
    """Whether two comparison keys (`bind.core.isoform_key`) belong to one protein."""
    classes = _classes()
    a, b = classes.get(key_a), classes.get(key_b)
    return bool(a and b and (a & b))


def can_match(label: str) -> bool:
    """Whether `label` names some isozyme the engine knows, beyond spelling."""
    classes = _classes()
    return any(key in classes for key in keys_of(label))


def names_for(accession: str, entry_stem: str) -> Tuple[str, ...]:
    """The names of one protein the engine will match, gene symbol first."""
    seen: List[str] = []
    for name in _protein_names(accession, entry_stem):
        if name not in seen:
            seen.append(name)
    return tuple(seen)


__all__ = ["equivalent", "can_match", "keys_of", "names_for"]
