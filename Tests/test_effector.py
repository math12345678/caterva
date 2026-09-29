"""Tests for effector.py.

Every commentary below is REAL, taken from the parsed fixtures. The
classifier is designed against the corpus, so the tests are the corpus.

PubChem is never called: `buffer_identity`'s providers are injected, in the
same shape as `test_buffer_identity.py`.
"""
from __future__ import annotations

import pytest

from effector import (
    compare_effectors,
    extract_effectors,
    resolve_effectors,
)

# ---------------------------------------------------------------------------
# Fixture providers. Real CIDs so the fixtures describe the real API.
# ---------------------------------------------------------------------------

CID_BY_NAME = {
    # Four spellings of one compound -- the reason identity is resolved.
    "fructose 1,6-bisphosphate": 172922,
    "fructose-1,6-bisphosphate": 172922,
    "fructose 1,6-diphosphate": 172922,
    "d-fructose-1,6-diphosphate": 172922,
    "nadh": 439153,
    "cacl2": 5284359,
    "glycerol": 753,
}
PARENT_BY_CID: dict[int, int] = {}


def fake_cid(name: str) -> str:
    cid = CID_BY_NAME.get(name.strip().lower())
    if cid is None:
        return '{"Fault": {"Code": "PUGREST.NotFound"}}'
    return '{"IdentifierList": {"CID": [%d]}}' % cid


def fake_parent(cid: int) -> str:
    return '{"IdentifierList": {"CID": [%d]}}' % PARENT_BY_CID.get(cid, cid)


def effectors(commentary: str):
    return resolve_effectors(extract_effectors(commentary), fake_cid, fake_parent)


# ---------------------------------------------------------------------------
# Extraction against real strings
# ---------------------------------------------------------------------------

PRESENT_CASES = [
    ("pH 6.0, 25°C, recombinant wild-type enzyme in presence of fructose 1,6-bisphosphate",
     "fructose 1,6-bisphosphate"),
    ("mutant I229A, presence of D-fructose-1,6-diphosphate, pH 5.5, 30°C",
     "D-fructose-1,6-diphosphate"),
    ("25°C, pH 8, wild-type enzyme, activated by fructose 1,6-diphosphate",
     "fructose 1,6-diphosphate"),
    ("LDHB, in the presence of 0.125 mM NADH", "NADH"),
]


@pytest.mark.parametrize("commentary,compound", PRESENT_CASES)
def test_extracts_a_present_effector(commentary, compound):
    found = extract_effectors(commentary)
    assert found, f"nothing extracted from {commentary!r}"
    assert any(e.compound_text == compound for e in found), [e.compound_text for e in found]
    assert all(e.presence == "present" for e in found)


def test_extracts_an_absent_effector():
    found = extract_effectors(
        "pH 6.0, 25°C, recombinant wild-type enzyme in absence of fructose 1,6-bisphosphate"
    )
    assert len(found) == 1
    assert found[0].presence == "absent"
    assert found[0].compound_text == "fructose 1,6-bisphosphate"


def test_keeps_the_concentration_it_does_not_compare():
    found = extract_effectors("LDHB, in the presence of 0.125 mM NADH")
    assert found[0].concentration_text == "0.125 mM"


def test_extracts_a_bare_salt_from_a_condition_list():
    # "in 10 mM Tris, 20 mM CaCl2, pH 7.4, at 37°C" -- Tris is the buffer
    # (assay_conditions.py claims it); CaCl2 is a cofactor nobody read.
    found = extract_effectors("in 10 mM Tris, 20 mM CaCl2, pH 7.4, at 37°C")
    names = [e.compound_text for e in found]
    assert "CaCl2" in names
    assert "Tris" not in names, "the buffer must not be reported as an effector"


def test_a_commentary_with_no_effector_yields_nothing():
    for commentary in (
        "pH 8.0, 30°C, native enzyme",
        "Y124C mutant",
        "pH and temperature not specified in the publication",
        None,
        "",
    ):
        assert extract_effectors(commentary) == []


# ---------------------------------------------------------------------------
# The pair this module exists for
# ---------------------------------------------------------------------------

PRESENT_FBP = "pH 6.0, 25°C, recombinant wild-type enzyme in presence of fructose 1,6-bisphosphate"
ABSENT_FBP = "pH 6.0, 25°C, recombinant wild-type enzyme in absence of fructose 1,6-bisphosphate"


def test_presence_and_absence_of_the_same_compound_are_different():
    """Same enzyme, same pH, same temperature, same paper, same wild-type
    verdict. Every other check in the repository calls these identical."""
    result = compare_effectors(effectors(PRESENT_FBP), effectors(ABSENT_FBP))
    assert result.status == "different"
    assert not result.is_same


def test_the_presence_absence_reason_says_which_way_round():
    result = compare_effectors(effectors(PRESENT_FBP), effectors(ABSENT_FBP))
    assert "PRESENCE" in result.reason and "ABSENCE" in result.reason
    assert "fructose" in result.reason
    # And says why it matters, rather than only that it differs.
    assert "changes the kinetics" in result.reason


def test_four_spellings_of_one_compound_compare_as_the_same():
    """The buffer problem again. String equality reports four effectors."""
    a = effectors("in presence of fructose 1,6-bisphosphate")
    b = effectors("presence of D-fructose-1,6-diphosphate")
    assert a[0].compound_text != b[0].compound_text
    assert a[0].identity.parent_cid == b[0].identity.parent_cid
    assert compare_effectors(a, b).status == "same"


def test_identical_conditions_compare_as_same():
    result = compare_effectors(effectors(PRESENT_FBP), effectors(PRESENT_FBP))
    assert result.status == "same"
    assert result.is_same


def test_a_same_verdict_admits_it_ignored_concentration():
    a = effectors("LDHB, in the presence of 0.125 mM NADH")
    b = effectors("LDHB, in the presence of 0.25 mM NADH")
    result = compare_effectors(a, b)
    # The documented limit: concentrations differ, compounds match.
    assert result.status == "same"
    assert "NOT compared" in result.reason
    assert "0.125 mM" in result.reason and "0.25 mM" in result.reason


# ---------------------------------------------------------------------------
# States never collapse into agreement
# ---------------------------------------------------------------------------

def test_neither_reporting_an_effector_is_not_reported():
    result = compare_effectors([], [])
    assert result.status == "not_reported"
    assert not result.is_same
    assert "not a finding that the conditions agreed" in result.reason


def test_one_side_reporting_nothing_is_a_difference_not_a_match():
    result = compare_effectors(effectors(PRESENT_FBP), [])
    assert result.status == "different"
    assert not result.is_same
    # And is honest that BRENDA cannot distinguish absent from unmentioned.
    assert "unmentioned" in result.reason


def test_an_unresolvable_compound_is_unknown_not_same():
    """Matching text is not matching chemistry.

    Two rows naming "house cofactor Q" agree as strings and are not
    confirmed to be one substance. `unknown` says so.
    """
    a = effectors("in presence of housecofactorQ")
    b = effectors("in presence of housecofactorQ")
    assert a[0].identity.status == "unresolvable"
    result = compare_effectors(a, b)
    assert result.status == "unknown"
    assert not result.is_same
    assert "Matching text is not matching chemistry" in result.reason


def test_is_same_is_a_positive_test():
    for status in ("unknown", "not_reported", "different"):
        result = compare_effectors(effectors(PRESENT_FBP), effectors(PRESENT_FBP))
        result.status = status
        assert result.is_same is False, f"{status} must not read as agreement"


def test_comparison_key_never_collapses_presence():
    """The single most important invariant in this module.

    If the key ignored presence, the FBP pair -- the case that motivated
    the whole thing -- would compare as `same` and the check would report
    success while doing nothing.
    """
    present = effectors(PRESENT_FBP)[0]
    absent = effectors(ABSENT_FBP)[0]
    assert present.comparison_key != absent.comparison_key
    assert present.comparison_key[0] == absent.comparison_key[0], (
        "same compound expected; the difference must be the presence field"
    )


# ---------------------------------------------------------------------------
# Corpus-level: the extractor must work on the real table, not just samples
# ---------------------------------------------------------------------------

def test_extractor_finds_effectors_across_the_real_ldh_fixture():
    """A unit test on hand-picked strings can pass while the extractor is
    useless on the real table.

    The fixture is `brenda_ldh_kcat_fixture.html`, not `brenda_ldh_fixture`.
    The first version of this test pointed at the latter and failed: the
    hand-picked strings above came from the kcat table and the Km table has
    no effector rows at all. Worth leaving in the record, because the test
    caught an assumption the unit tests could not -- they were all passing.
    """
    import pathlib
    from brenda_client import parse_brenda_km_html, KM_TABLE_LABEL

    html = pathlib.Path(__file__).parent.joinpath(
        "fixtures", "brenda_ldh_kcat_fixture.html"
    ).read_text(errors="replace")
    rows = parse_brenda_km_html(
        html, "1.1.1.27", [], target_organism=None,
        require_substrate_match=False, table_label=KM_TABLE_LABEL,
    )
    assert rows, "fixture parsed to nothing; this test would pass vacuously"

    with_effectors = [r for r in rows if extract_effectors(r.conditions)]
    # Not asserting an exact count -- the point is that it is not zero and
    # not everything. Zero means the extractor is blind; everything means it
    # is matching prose.
    assert with_effectors, "no effectors found in a fixture known to contain them"
    assert len(with_effectors) < len(rows), (
        "every row matched, which means the extractor is firing on ordinary "
        "commentary rather than on effector clauses"
    )


# ---------------------------------------------------------------------------
# What the compound phrase is not (BRENDA hexokinase, EC 2.7.1.1)
# ---------------------------------------------------------------------------
#
# Each of these went to PubChem as a "compound" on 2026-09-29 and came back
# 404. The strings are BRENDA's own, from the recorded hexokinase page.

def test_a_role_word_is_not_part_of_the_name():
    found = extract_effectors(
        "wild type enzyme, at 25°C, in the presence of 0.02 mM activator LY-2121260")
    assert [(e.compound_text, e.role, e.concentration_text) for e in found] == [
        ("LY-2121260", "activator", "0.02 mM")]


def test_a_role_with_no_compound_is_not_looked_up():
    found = extract_effectors("in absence of activator")
    assert len(found) == 1 and found[0].presence == "absent" and not found[0].named
    asked = []
    resolve_effectors(found, lambda name: asked.append(name) or "", lambda cid: "")
    assert asked == [], "a bare role word was sent to PubChem"


@pytest.mark.parametrize("commentary", [
    "truncated enzyme with removed helix alpha13",
    "glucokinase with C-terminal 5 alanine addition",
])
def test_a_change_to_the_protein_is_not_an_effector(commentary):
    assert extract_effectors(commentary) == []


def test_either_of_two_compounds_is_two_effectors_neither_known_present():
    found = extract_effectors(
        "wild type enzyme, at 30°C, in 100 mM Tris and 125 mM KCl, pH 7.4, "
        "in the presence of 14 mM beta-mercaptoethanol or 5 mM dithiothreitol")
    reducing = [(e.compound_text, e.concentration_text, e.presence)
                for e in found if e.compound_text != "KCl"]
    assert reducing == [("beta-mercaptoethanol", "14 mM", "unstated"),
                        ("dithiothreitol", "5 mM", "unstated")]


def test_both_of_two_compounds_are_present():
    found = extract_effectors("in the presence of 1 mM MgCl2 and 2 mM ATP")
    assert [(e.compound_text, e.presence) for e in found] == [("MgCl2", "present"), ("ATP", "present")]
