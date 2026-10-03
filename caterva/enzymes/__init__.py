"""Find an enzyme from a name, offline, in the IUBMB nomenclature.

    from caterva.enzymes import find, resolve, isozymes

    resolve("pyruvate kinase")            # Resolved(ec='2.7.1.40', ...)
    resolve("lactate dehydrogenase")      # Ambiguous: 1.1.1.27 and 1.1.1.28, named
    find("hexokinase", organism="human")  # ranked Candidates, with the human entries
    isozymes("2.7.1.1", "human")          # HXK1, HXK2, HXK3, HXK4, HKDC1

See finder.py for why this exists and how matches are ranked.
"""
from .finder import (
    Ambiguous, Candidate, Isozymes, Resolution, Resolved,
    find, isozymes, read_ec, recommend, refusal_text, resolve,
)
from .policy import NameNotResolved, NameResolution, resolve_enzyme_name
from .index import EnzymeIndex, Protein, load_index, organism_code, organism_label

__all__ = [
    "Ambiguous", "Candidate", "Isozymes", "Resolution", "Resolved",
    "EnzymeIndex", "Protein",
    "find", "isozymes", "resolve", "read_ec", "refusal_text", "recommend",
    "NameNotResolved", "NameResolution", "resolve_enzyme_name",
    "load_index", "organism_code", "organism_label",
]
