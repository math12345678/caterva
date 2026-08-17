"""Tests for source_context.py.

Every commentary is REAL, from the AChE and LDH turnover fixtures. NCBI is
never touched: the taxon provider is injected, matching taxonomy.py.
"""
from __future__ import annotations

import pathlib

import pytest

from source_context import (
    extract_source_claims,
    find_organism_discrepancies,
    find_source_mixtures,
)


#: Real NCBI taxon ids. Organisms resolve; anatomical parts and life stages
#: do not. That asymmetry is the entire mechanism separating "from human"
#: from "from heart" without a hardcoded tissue list.
TAXON_BY_NAME = {
    "human": "9606",
    "homo sapiens": "9606",
    "eel": "7935",
    "drosophila": "7215",
    "drosophila melanogaster": "7227",
    "gallus gallus": "9031",
    "anas platyrhynchos": "8839",
    "bactrocera dorsalis": "27457",
}


def fake_taxon(name: str) -> str | None:
    return TAXON_BY_NAME.get(name.strip().lower())


def claims(commentary):
    return extract_source_claims(commentary, fake_taxon)


# ---------------------------------------------------------------------------
# Extraction, and the organism/source split
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "commentary,token,kind",
    [
        ("enzyme from heart", "heart", "source"),
        ("enzyme from muscle", "muscle", "source"),
        ("enzyme from adult, at pH 7.4 and 37°C", "adult", "source"),
        ("enzyme from pupa, at pH 7.4 and 37°C", "pupa", "source"),
        ("enzyme from larva, at pH 7.4 and 37°C", "larva", "source"),
        ("from human", "human", "organism"),
        ("from eel", "eel", "organism"),
        ("from Drosophila", "drosophila", "organism"),
    ],
)
def test_real_source_claims_are_extracted_and_classified(commentary, token, kind):
    found = claims(commentary)
    assert found, commentary
    assert found[0].token.lower() == token
    assert found[0].kind == kind, f"{found[0].token} -> {found[0].kind}"


def test_the_typo_form_for_from_is_read_through():
    # "enzyme form heart and muscle" is in the corpus. Silently correcting a
    # curator's typo would be wrong; reading through it is not.
    found = claims("enzyme form heart and muscle")
    assert found and found[0].token.lower() == "heart"


def test_every_claim_carries_its_evidence():
    # A claim with no evidence is an assertion.
    assert claims("enzyme from heart")[0].evidence


def test_an_unresolvable_token_is_not_called_a_source():
    """A failed lookup is `unresolved`, never `source`.

    Calling it a tissue would let a real organism contradiction through as
    an anatomical note -- the silent direction.
    """
    def exploding(_name):
        raise TimeoutError("NCBI unreachable")

    found = extract_source_claims("enzyme from heart", exploding)
    assert found[0].kind == "unresolved"


# ---------------------------------------------------------------------------
# The tissue disease-state pattern
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "commentary,state",
    [
        ("pH 8.0, healthy breast tissue enzyme", "healthy"),
        ("pH 8.0, breast cancer tissue enzyme", "diseased"),
    ],
)
def test_the_real_breast_tissue_rows_carry_their_state(commentary, state):
    found = claims(commentary)
    assert found, commentary
    assert found[0].token.lower() == "breast"
    assert found[0].disease_state == state


# ---------------------------------------------------------------------------
# Finding 1: the commentary contradicts the organism column
# ---------------------------------------------------------------------------

REAL_ACHE_ROWS = [
    (1780.0, "Drosophila melanogaster", "from Drosophila"),
    (6670.0, "Drosophila melanogaster", "from human"),
    (13700.0, "Drosophila melanogaster", "from eel"),
]


def test_the_real_organism_contradiction_is_found():
    found = find_organism_discrepancies(REAL_ACHE_ROWS, fake_taxon)
    said = {d.commentary_organism.lower() for d in found}
    assert "human" in said and "eel" in said, said


def test_the_matching_row_is_not_flagged():
    # "from Drosophila" on a Drosophila row is agreement, not a discrepancy.
    # Without this, the test above would pass because everything is flagged.
    found = find_organism_discrepancies(
        [(1780.0, "Drosophila melanogaster", "from Drosophila")], fake_taxon
    )
    assert found == [] or all(
        d.commentary_organism.lower() != "drosophila" for d in found
    )


def test_the_discrepancy_explains_why_it_matters():
    # A flag saying "these differ" is unactionable. The reader needs to know
    # the cross-species gate reads the column.
    found = find_organism_discrepancies(REAL_ACHE_ROWS, fake_taxon)
    reason = found[0].reason
    assert "cross-species gate" in reason
    assert "cannot tell which" in reason


def test_a_tissue_never_produces_an_organism_discrepancy():
    # "from heart" on any row must not read as a contradicting organism.
    rows = [(60.0, "Gallus gallus", "enzyme from heart")]
    assert find_organism_discrepancies(rows, fake_taxon) == []


def test_an_unresolvable_column_organism_yields_no_discrepancy():
    # Both sides must resolve before a contradiction is claimed.
    rows = [(1.0, "Unknownus fictitious", "from human")]
    assert find_organism_discrepancies(rows, fake_taxon) == []


# ---------------------------------------------------------------------------
# Finding 2: one organism, several sources
# ---------------------------------------------------------------------------

REAL_LDH_ROWS = [
    (60.0, "Gallus gallus", "enzyme from heart"),
    (1.1, "Gallus gallus", "enzyme from muscle"),
    (3.3, "Gallus gallus", "enzyme from muscle"),
    (6.2, "Anas platyrhynchos", "enzyme from heart"),
]


def test_heart_and_muscle_in_one_species_is_a_mixture():
    found = find_source_mixtures(REAL_LDH_ROWS, fake_taxon)
    chicken = [m for m in found if m.organism == "Gallus gallus"]
    assert chicken, [m.organism for m in found]
    assert set(chicken[0].values_by_source) == {"heart", "muscle"}


def test_the_mixture_reports_the_fifty_four_fold_span():
    chicken = [
        m for m in find_source_mixtures(REAL_LDH_ROWS, fake_taxon)
        if m.organism == "Gallus gallus"
    ][0]
    assert chicken.fold_difference == pytest.approx(60.0 / 1.1, rel=1e-6)
    assert "factor of" in chicken.reason


def test_one_source_in_a_species_is_not_a_mixture():
    # The duck has only heart rows.
    found = find_source_mixtures(REAL_LDH_ROWS, fake_taxon)
    assert [m for m in found if m.organism == "Anas platyrhynchos"] == []


def test_mixtures_are_grouped_by_organism_not_across_them():
    """Heart in a chicken and muscle in a duck is not a mixture.

    Across species it is two ordinary cross-species rows, already governed
    by ADR 0024. Grouping across organisms would report that gate's normal
    operation as a finding, and the warning would fire on every multi-species
    pool.
    """
    rows = [
        (60.0, "Gallus gallus", "enzyme from heart"),
        (1.1, "Anas platyrhynchos", "enzyme from muscle"),
    ]
    assert find_source_mixtures(rows, fake_taxon) == []


def test_the_healthy_versus_cancer_pair_is_a_mixture():
    rows = [
        (10.73, "Homo sapiens", "pH 8.0, healthy breast tissue enzyme"),
        (21.78, "Homo sapiens", "pH 8.0, breast cancer tissue enzyme"),
    ]
    found = find_source_mixtures(rows, fake_taxon)
    assert found
    assert set(found[0].values_by_source) == {"healthy breast", "diseased breast"}


def test_the_reason_names_each_source_and_its_values():
    chicken = [
        m for m in find_source_mixtures(REAL_LDH_ROWS, fake_taxon)
        if m.organism == "Gallus gallus"
    ][0]
    assert "heart" in chicken.reason and "muscle" in chicken.reason
    assert "60" in chicken.reason and "1.1" in chicken.reason


def test_an_empty_pool_yields_nothing():
    assert find_source_mixtures([], fake_taxon) == []
    assert find_organism_discrepancies([], fake_taxon) == []


# ---------------------------------------------------------------------------
# Corpus level
# ---------------------------------------------------------------------------

def test_both_findings_are_present_in_the_real_fixtures():
    """Hand-copied strings can differ from what the parser produces."""
    from brenda_client import TURNOVER_TABLE_LABEL, parse_brenda_km_html

    here = pathlib.Path(__file__).parent

    ache = parse_brenda_km_html(
        (here / "fixtures" / "brenda_ache_kcat_fixture.html").read_text(errors="replace"),
        "3.1.1.7", [], target_organism=None, require_substrate_match=False,
        table_label=TURNOVER_TABLE_LABEL,
    )
    assert ache, "AChE fixture parsed to nothing; this would pass vacuously"
    discrepancies = find_organism_discrepancies(
        [(r.km_value, r.organism, r.conditions) for r in ache], fake_taxon
    )
    assert discrepancies, (
        "no organism discrepancy found in the AChE turnover table, which "
        "contains Drosophila-column rows whose commentary says 'from human' "
        "and 'from eel'"
    )

    ldh = parse_brenda_km_html(
        (here / "fixtures" / "brenda_ldh_kcat_fixture.html").read_text(errors="replace"),
        "1.1.1.27", [], target_organism=None, require_substrate_match=False,
        table_label=TURNOVER_TABLE_LABEL,
    )
    assert ldh, "LDH fixture parsed to nothing; this would pass vacuously"
    mixtures = find_source_mixtures(
        [(r.km_value, r.organism, r.conditions) for r in ldh], fake_taxon
    )
    chicken = [m for m in mixtures if m.organism == "Gallus gallus"]
    assert chicken, [m.organism for m in mixtures]
    assert chicken[0].fold_difference and chicken[0].fold_difference > 10, (
        "the fixture no longer demonstrates a large within-species span; "
        "re-verify before relaxing this"
    )


# ---------------------------------------------------------------------------
# "Nothing found" must not mean "nothing checked"
# ---------------------------------------------------------------------------

def test_an_unreachable_classifier_is_reported_not_silent():
    """Found by running the real resolution path, not a fixture.

    With the network blocked, `(Gallus gallus, NAD+)` -- a pool genuinely
    holding heart 60.0 and muscle 3.3 -- reported no mixture at all. Every
    token classified `unresolved`, every one was skipped, and the result was
    indistinguishable from a clean pool.

    An empty result that can mean "nothing found" OR "nothing checked" is
    the conflation this project spends most of its effort on, and this
    module shipped it.
    """
    from source_context import source_check_status

    def exploding(_name):
        raise TimeoutError("NCBI unreachable")

    rows = [
        (60.0, "Gallus gallus", "enzyme from heart"),
        (3.3, "Gallus gallus", "enzyme from muscle"),
    ]
    assert find_source_mixtures(rows, exploding) == []
    status = source_check_status(rows, exploding)
    assert status is not None
    assert set(status.tokens) == {"heart", "muscle"}
    assert "NOT checked" in status.reason


def test_a_working_classifier_reports_no_unavailability():
    # The counterpart. Without it, the test above passes for a module that
    # always reports unavailable.
    from source_context import source_check_status

    rows = [
        (60.0, "Gallus gallus", "enzyme from heart"),
        (3.3, "Gallus gallus", "enzyme from muscle"),
    ]
    assert source_check_status(rows, fake_taxon) is None
    assert find_source_mixtures(rows, fake_taxon)


def test_a_pool_naming_no_source_is_not_unavailable():
    # No tokens extracted is not a failed check -- there was nothing to
    # check. Reporting unavailability here would fire on almost every pool.
    from source_context import source_check_status

    def exploding(_name):
        raise TimeoutError("NCBI unreachable")

    rows = [(1.0, "Gallus gallus", "pH 7.4, 37°C")]
    assert source_check_status(rows, exploding) is None
