"""What `caterva compose` says, after the third round of the real-values review (2026-11-12).

The literature layer's rules are pinned on real BRENDA rows in
Tests/test_third_round_review.py. These pin the report: a search that failed
on the network is not "found nothing", a misspelt enzyme name gets "did you
mean", a tissue word is read as the tissue's isoform, a K0.5 and two proteins
in one rate law are said in the verdict, and the chooser ranks a protein
substrate after defined small molecules and breaks ties by the compound the
enzyme is named for before the alphabet.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from caterva.compose import defaults, verdict
from caterva.compose import __main__ as compose_main
from caterva.compose.grammar import _misspelt_enzyme
from caterva.enzymes.sentence import read_sentence


def test_a_scout_that_failed_on_the_network_was_not_searched():
    """Queries 10 and 24: a ReadTimeout on one constant's scout was reported
    as "searched the km table and found nothing", with advice to change the
    organism; a plain re-run filled it."""
    reason = compose_main._not_searched(
        "ReadTimeout: The read operation timed out (https://www.brenda-enzymes.org/enzyme.php)")
    assert reason.startswith("not searched:") and "BRENDA timed out" in reason
    assert "not an absence of measurements" in reason and "re-run the same command" in reason
    model = SimpleNamespace(not_found={"reaction_Km": reason})
    remedy = verdict._what_would_ground(model, ["reaction_Km"])
    assert remedy.startswith("re-run the same command") and "--organism" not in remedy


def test_a_uniprot_outage_is_named_as_uniprot_and_a_retry():
    said = compose_main._service_failed(
        "HTTPStatusError: Server error '503 Backend fetch failed' for url "
        "'https://rest.uniprot.org/uniprotkb/search?query=ec%3A1.5.1.3'")
    assert said.startswith("UniProt answered with a server error")
    assert "re-run the same command" in said


def test_a_misspelt_enzyme_name_gets_did_you_mean():
    """V18: one transposed letter got the shape refusal and the list of shapes."""
    said = _misspelt_enzyme("glyceraldehyde-3-phosphate dehydrogenaes from rabbit muscle")
    assert "Did you mean 'glyceraldehyde-3-phosphate dehydrogenase'?" in said
    assert 'caterva compose "glyceraldehyde-3-phosphate dehydrogenase from rabbit muscle"' in said
    assert _misspelt_enzyme("signalling in a cell") is None


@pytest.mark.parametrize("ec, typed, isoform", [
    ("2.7.1.40", "pyruvate kinase muscle human PEP", "PKM"),
    ("4.1.2.13", "aldolase from rabbit muscle", "ALDOA"),
    ("1.1.1.27", "lactate dehydrogenase from pig heart", "LDHB"),
])
def test_a_tissue_word_is_read_as_the_tissues_isoform(ec, typed, isoform):
    """M7: "muscle" was dropped without a word."""
    assert compose_main._tissue_isoform(ec, typed)[1] == isoform


def test_a_tissue_word_with_no_listed_isoform_is_said_to_be_unused():
    assert compose_main._tissue_isoform("1.1.1.37", "malate dehydrogenase from pig heart") is None
    assert compose_main._TISSUE_WORD.search("malate dehydrogenase from pig heart")


def test_breaking_down_ends_a_substrate_candidate():
    """V11: "liver breaking down hydrogen peroxide" was one candidate."""
    reading = read_sentence("catalase from bovine liver breaking down hydrogen peroxide")
    assert "hydrogen peroxide" in reading.substrate_candidates


@pytest.mark.parametrize("name, macro", [
    ("casein", True), ("azocasein", True), ("hemoglobin", True), ("soluble starch", True),
    ("Nalpha-benzoyl-L-Arg ethyl ester", False), ("benzyl-Phe-Val-Arg-4-nitroanilide", False),
])
def test_a_protein_or_polymer_substrate_is_recognised(name, macro):
    """V15: papain was modelled on casein, kcat rows over five orders of magnitude."""
    assert defaults.is_macromolecule(name) is macro


@pytest.mark.parametrize("ec, compound, named", [
    ("3.1.1.8", "Butyrylcholine", True), ("3.1.1.8", "acetylthiocholine", False),
    ("2.7.4.3", "AMP", True), ("2.7.4.3", "ATP", False),
    # "glutathione reductase (NADPH)" names its cofactor in parentheses.
    ("1.8.1.7", "NADPH", False), ("1.8.1.7", "GSSG", True),
])
def test_the_compound_an_enzyme_is_named_for(ec, compound, named):
    """V14 and V2: horse BChE was modelled on acetylthiocholine by the
    alphabet; E. coli adenylate kinase's AMP was set aside as a cofactor."""
    assert defaults._named_by_enzyme(ec, compound) is named


def _measured(commentary, row_isoform=None):
    return SimpleNamespace(value=6.3, unit="mM", commentary=commentary, row_isoform=row_isoform)


def test_a_k05_carried_as_a_km_is_a_concern_of_the_verdict():
    """V4-1, V4-2, A2-5: human hexokinase's Km is glucokinase's K0.5 with a
    Hill coefficient of 1.8, said only in a row note under a plain GROUNDED."""
    model = SimpleNamespace(
        measured={"reaction_Km": _measured("wild-type, K0.5 value, Hill coefficient 1.8, pH 7.6, 25 °C",
                                           "GCK")},
        resolvable=[SimpleNamespace(parameter_id="reaction_Km", table="km")],
        subject="2.7.1.1", organism="Homo sapiens")
    (concern,) = verdict._row_kind_concerns(model)
    assert concern.severity == verdict.GROUNDED
    assert "K0.5 with a Hill coefficient of 1.8 (GCK's)" in concern.detail
    assert concern.qualifier


def test_two_proteins_in_one_rate_law_are_a_concern_of_the_verdict():
    """A2-1 and V3: CA II's Km beside CA III's kcat, no isozyme-mix concern."""
    model = SimpleNamespace(
        measured={"reaction_Km": _measured("pH 7.5", "CA-II"), "reaction_kcat": _measured("pH 7.5", "CA-III")},
        resolvable=[SimpleNamespace(parameter_id="reaction_Km", table="km"),
                    SimpleNamespace(parameter_id="reaction_kcat", table="kcat")],
        subject="4.2.1.1", organism="Homo sapiens")
    (concern,) = verdict._row_kind_concerns(model)
    assert "name different proteins" in concern.detail


def test_one_protein_is_not_a_concern():
    model = SimpleNamespace(
        measured={"reaction_Km": _measured("pH 7.5", "CA-II"), "reaction_kcat": _measured("pH 7.5", "CA2")},
        resolvable=[SimpleNamespace(parameter_id="reaction_Km", table="km"),
                    SimpleNamespace(parameter_id="reaction_kcat", table="kcat")],
        subject="4.2.1.1", organism="Homo sapiens")
    assert verdict._row_kind_concerns(model) == []
