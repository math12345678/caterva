"""`--organism "Homo S"` is Homo sapiens, never "Homo s" (ADR 0182).

WHY THESE TESTS
---------------
The baseline of 2026-11-11 typed `--organism "Homo S"`. The normaliser found no
table entry and fell back to a case fix that lower-cased the epithet, giving
"Homo s". BRENDA rows are matched on the organism's text, so "Homo s" matched
all 159 human Km rows and relabelled them: the cited table printed
"literature (Homo s)" in a report meant for professors. These hold the
normaliser to reading a short or abbreviated binomial as the one known
organism it can be, to returning anything else exactly as typed with a note
that says so, and to never turning "guinea pig" into a pig.
"""
from __future__ import annotations

import pytest

from caterva.compose.organisms import known_binomials, normalise_organism


@pytest.mark.parametrize("typed, binomial", [
    ("Homo S", "Homo sapiens"),
    ("homo s", "Homo sapiens"),
    ("homo sap", "Homo sapiens"),
    ("Homo sapien", "Homo sapiens"),
    ("H sapiens", "Homo sapiens"),
    ("H. sapiens", "Homo sapiens"),
    ("Homo", "Homo sapiens"),
    ("E coli", "Escherichia coli"),
    ("E. coli", "Escherichia coli"),
    ("S cerevisiae", "Saccharomyces cerevisiae"),
    ("S. cerevisiae", "Saccharomyces cerevisiae"),
    ("Mus m", "Mus musculus"),
    ("R norvegicus", "Rattus norvegicus"),
    ("yeast", "Saccharomyces cerevisiae"),
    ("mouse", "Mus musculus"),
    ("rat", "Rattus norvegicus"),
    ("cow", "Bos taurus"),
    ("bovine", "Bos taurus"),
    ("pig", "Sus scrofa"),
    ("human", "Homo sapiens"),
    ("humans", "Homo sapiens"),
    ("guinea pig", "Cavia porcellus"),
])
def test_a_short_or_common_spelling_is_read_as_the_one_organism_it_can_be(typed, binomial):
    organism, note = normalise_organism(typed)
    assert organism == binomial
    assert note == f"Read --organism {typed!r} as {binomial}."


def test_the_note_the_report_prints_for_homo_s():
    assert normalise_organism("Homo S") == ("Homo sapiens", "Read --organism 'Homo S' as Homo sapiens.")


def test_guinea_pig_is_never_a_pig():
    assert normalise_organism("guinea pig")[0] == "Cavia porcellus"
    assert normalise_organism("Guinea pig")[0] == "Cavia porcellus"


@pytest.mark.parametrize("typed", ["S.", "S. c", "S c", "Mus", "Bacillus", "Sac"])
def test_a_spelling_that_could_be_several_organisms_or_a_whole_genus_is_kept_as_typed_and_said(typed):
    organism, note = normalise_organism(typed)
    assert organism == typed, "never case-mangled into something that looks like an organism"
    assert note is not None and "was not recognised as one organism" in note
    assert "Pass the full binomial" in note


def test_the_note_for_an_ambiguous_initial_names_the_closest_organisms():
    _, note = normalise_organism("S.")
    for binomial in ("Saccharomyces cerevisiae", "Schizosaccharomyces pombe", "Sus scrofa"):
        assert binomial in note


def test_a_binomial_no_table_holds_only_has_its_case_fixed():
    # Case fixed, and said to be unrecognised: "Read ... as" claimed a match
    # ("electric eel" came back "Read as Electric eel", round-1 F04).
    searched, note = normalise_organism("thermus thermophilus")
    assert searched == "Thermus thermophilus"
    assert note.startswith("--organism 'thermus thermophilus' is not an organism Caterva knows")
    assert "Read --organism" not in note
    assert normalise_organism("Human immunodeficiency virus 1") == ("Human immunodeficiency virus 1", None)
    assert normalise_organism("Escherichia coli K-12")[0] == "Escherichia coli K-12"


def test_no_reading_ever_produces_a_name_that_is_not_a_known_binomial_or_what_was_typed():
    """Every spelling of every prefix of every known binomial: the answer is a known binomial, or the text
    exactly as typed (or, for a full two-word name, the same words with the case fixed). Never "Homo s"."""
    known = set(known_binomials())
    for binomial in known:
        genus, epithet = binomial.split(" ", 1)
        for g in (genus[:1], genus[:3], genus, genus.lower(), genus.upper()):
            for e in (epithet[:1], epithet[:3], epithet, epithet.upper()):
                for sep in (" ", ". "):
                    typed = f"{g}{sep}{e}" if len(g) == 1 else f"{g} {e}"
                    organism, _ = normalise_organism(typed)
                    fixed = " ".join(typed.split()).split(" ")
                    case_fixed = " ".join([fixed[0].capitalize(), *[w.lower() for w in fixed[1:]]])
                    assert organism in known or organism == " ".join(typed.split()) or (
                        organism == case_fixed and all(len(w) >= 3 for w in fixed)), (typed, organism)


def test_the_sentence_reads_guinea_pig_as_cavia_porcellus():
    from caterva.enzymes.sentence import read_sentence

    reading = read_sentence("trypsin from guinea pig")
    assert reading.organism == "Cavia porcellus"
