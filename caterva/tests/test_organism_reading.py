"""`--organism` is read the way people type it, and the reading is stated.

Found 2026-09-25: `--organism human` and `--organism "homo sapiens"` found
nothing for human hexokinase, whose Km and kcat are both in BRENDA under
"Homo sapiens". The report blamed the literature for a spelling.
"""
from __future__ import annotations

import pytest

from caterva.compose.organisms import normalise_organism


@pytest.mark.parametrize("typed, searched", [
    ("human", "Homo sapiens"),
    ("Human", "Homo sapiens"),
    ("homo sapiens", "Homo sapiens"),
    ("HOMO SAPIENS", "Homo sapiens"),
    ("yeast", "Saccharomyces cerevisiae"),
    ("E. coli", "Escherichia coli"),
    ("rabbit", "Oryctolagus cuniculus"),
])
def test_common_spellings_reach_the_binomial(typed: str, searched: str) -> None:
    organism, note = normalise_organism(typed)
    assert organism == searched
    assert note is not None and searched in note


def test_stray_spaces_are_dropped_silently() -> None:
    assert normalise_organism("  Homo   sapiens ") == ("Homo sapiens", None)


def test_an_exact_binomial_is_used_as_typed_and_says_nothing() -> None:
    assert normalise_organism("Homo sapiens") == ("Homo sapiens", None)


def test_a_strain_after_the_binomial_is_left_alone() -> None:
    organism, _ = normalise_organism("escherichia coli K-12")
    assert organism == "Escherichia coli K-12"


@pytest.mark.parametrize("vague", ["monkey", "fish", "bacteria"])
def test_a_name_for_many_species_is_not_guessed(vague: str) -> None:
    organism, _ = normalise_organism(vague)
    # Capitalised as a genus would be, never mapped to a species.
    assert organism == vague.capitalize()


def test_nothing_in_nothing_out() -> None:
    assert normalise_organism(None) == (None, None)
    assert normalise_organism("   ") == (None, None)
