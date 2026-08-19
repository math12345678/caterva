"""What an enzyme reports, asked before the first query.

The friction this addresses, measured through the real resolver:

    substrate="lactate"    -> found, 10.73
    substrate="L-lactate"  -> found=False

ADR 0118 makes the MISS name the labels that exist. That helps after a
student has already failed, and only about the substrate — they still guess
the organism, and guess whether the enzyme has a Ki table at all. So the
first query is a guess, and a wrong guess is indistinguishable from "the
literature has nothing".
"""
from __future__ import annotations

import pytest

from brenda_client import KI_TABLE_LABEL, KM_TABLE_LABEL, TURNOVER_TABLE_LABEL
from enzyme_catalog import QUANTITIES, catalog
from test_fallback_logic import load_fixture, make_html_provider

LDH = "1.1.1.27"


def provider_for(fixture: str, ec: str = LDH):
    return make_html_provider({ec: load_fixture(fixture)})


def km_only():
    """The LDH page carrying a KM table and neither of the others."""
    return catalog(LDH, provider_for("brenda_ldh_fixture.html"))


# ---------------------------------------------------------------------------
# What it reports
# ---------------------------------------------------------------------------


def test_it_names_the_labels_a_query_would_have_to_use():
    result = km_only()
    km = next(q for q in result.quantities if q.quantity == "km")
    assert km.is_usable
    assert "(S)-lactate" in km.substrates, (
        "the label that a student typing 'L-lactate' would need is not shown"
    )


def test_it_names_the_organisms_that_have_data():
    """The other field a student has to guess. An organism with no rows
    produces a `cross_species_withheld` refusal that looks like a wall."""
    assert km_only().organisms == ["Homo sapiens", "Sus scrofa"]


def test_it_counts_the_rows():
    """Where the data is thick, and where one paper carries a quantity."""
    km = next(q for q in km_only().quantities if q.quantity == "km")
    assert km.rows == 8


def test_every_quantity_the_resolver_accepts_is_covered():
    """A catalog that silently omitted a quantity would send a reader to a
    dead end while looking complete."""
    from fallback_logic import QUANTITY_TABLE_LABELS

    assert set(QUANTITIES) == set(QUANTITY_TABLE_LABELS), (
        "the catalog and the resolver disagree about which quantities exist"
    )
    assert {q.quantity for q in km_only().quantities} == set(QUANTITIES)


# ---------------------------------------------------------------------------
# The distinction ADR 0120 was written about
# ---------------------------------------------------------------------------


def test_a_missing_table_is_reported_as_missing_not_as_empty():
    """`substrates == []` cannot carry this on its own.

    ADR 0120: the parser falls back to whole-page scanning when a label is
    absent, so parsing anyway reports another table's contents under this
    quantity's name. `reported` is the field that keeps "BRENDA has no Ki
    table" apart from "the table is there and empty".
    """
    result = km_only()
    ki = next(q for q in result.quantities if q.quantity == "ki")

    assert ki.reported is False
    assert ki.substrates == []
    assert not ki.is_usable


def test_no_substrate_from_another_table_leaks_into_a_missing_one():
    """The defect ADR 0120 corrected, asserted at this level too."""
    result = km_only()
    for quantity in ("ki", "kcat"):
        inventory = next(q for q in result.quantities if q.quantity == quantity)
        assert "(S)-lactate" not in inventory.substrates, (
            f"a Km-table substrate was reported under {quantity}"
        )


def test_the_fixtures_really_differ_in_which_tables_they_carry():
    """The premise, asserted rather than assumed.

    ADR 0120's lesson: the mutations behind ADR 0118 all probed the new
    code and none probed its input. If someone enriches these fixtures
    later, these tests must fail rather than quietly stop testing anything.
    """
    from brenda_client import has_data_table

    km_page = load_fixture("brenda_ldh_fixture.html")
    assert has_data_table(km_page, KM_TABLE_LABEL)
    assert not has_data_table(km_page, KI_TABLE_LABEL)

    kcat_page = load_fixture("brenda_ldh_kcat_fixture.html")
    assert has_data_table(kcat_page, TURNOVER_TABLE_LABEL)
    assert not has_data_table(kcat_page, KM_TABLE_LABEL)


def test_a_page_of_turnover_numbers_reports_kcat_and_not_km():
    result = catalog(LDH, provider_for("brenda_ldh_kcat_fixture.html"))
    assert result.usable == ["kcat"]
    kcat = next(q for q in result.quantities if q.quantity == "kcat")
    assert kcat.rows > 50
    # This table names BOTH spellings, which is exactly what a student
    # guessing between them needs to see.
    assert "L-lactate" in kcat.substrates
    assert "(S)-lactate" in kcat.substrates


# ---------------------------------------------------------------------------
# One page, one request
# ---------------------------------------------------------------------------


def test_the_page_is_fetched_exactly_once():
    """Three tables, one page.

    Jeske asked that tools be gentle with DSMZ's servers — it is why the
    bulk-download route was adopted at all. A discovery command that made
    three requests to answer one question would be a poor way to honour
    that, and nothing in the output would reveal it.
    """
    calls = {"n": 0}
    page = load_fixture("brenda_ldh_fixture.html")

    def counting(_ec: str) -> str:
        calls["n"] += 1
        return page

    catalog(LDH, counting)
    assert calls["n"] == 1, f"fetched the same page {calls['n']} times"


# ---------------------------------------------------------------------------
# The sentence a reader gets
# ---------------------------------------------------------------------------


def test_the_summary_gives_a_reader_what_they_need_to_type():
    text = km_only().summary()
    assert "(S)-lactate" in text
    assert "Homo sapiens" in text
    assert "no 'Ki Values' table on this page" in text
    assert "does not substitute a similar name" in text


def test_an_enzyme_with_no_kinetic_tables_says_so_plainly():
    """Not an empty listing. A reader must be able to tell "this enzyme has
    no kinetic data on BRENDA" from "the command failed"."""
    empty = make_html_provider({LDH: "<html><body>nothing here</body></html>"})
    result = catalog(LDH, empty)

    assert result.usable == []
    text = result.summary()
    assert "reports none of" in text
    assert "not about the question you asked" in text


def test_a_present_but_empty_table_is_not_called_usable():
    """`reported` alone would call it usable.

    A positive test, for the same reason `is_tied` and `is_wild_type` are:
    the empty case must not read as a clean answer.
    """
    from enzyme_catalog import QuantityInventory

    inventory = QuantityInventory(
        quantity="km", table_label=KM_TABLE_LABEL, reported=True, rows=0
    )
    assert inventory.reported
    assert not inventory.is_usable


# ---------------------------------------------------------------------------
# A name is not an enzyme
# ---------------------------------------------------------------------------


class TestTheNameToECStepRefusesToPick:
    """The first step of the workflow, and the one where a silent choice
    costs the most.

    An EC number is not a parameter — it is the identity of the protein
    everything downstream is about. A wrong Km is a wrong number; a wrong
    EC is a real citation for a different enzyme.

    Measured before `parse_ec_number_candidates` existed:
    `parse_ec_number_search` took `results[0]` then `ec_numbers[0]` and the
    UniProt query asked for `size=1`, so BOTH ambiguity shapes returned one
    string with nothing saying a choice had been made.
    """

    #: One protein carrying two EC numbers — bifunctional enzymes are real.
    TWO_ON_ONE_PROTEIN = {
        "results": [
            {
                "proteinDescription": {
                    "recommendedName": {
                        "ecNumbers": [{"value": "1.1.1.27"}, {"value": "1.1.1.28"}]
                    }
                }
            }
        ]
    }

    #: Two proteins matching one name. EC 1.1.1.27 is L-lactate
    #: dehydrogenase and EC 1.1.1.28 is D-lactate dehydrogenase: different
    #: enzymes, different stereoisomers, one common name.
    TWO_PROTEINS = {
        "results": [
            {"proteinDescription": {"recommendedName": {"ecNumbers": [{"value": "1.1.1.27"}]}}},
            {"proteinDescription": {"recommendedName": {"ecNumbers": [{"value": "1.1.1.28"}]}}},
        ]
    }

    def test_both_candidates_are_reported_not_just_the_first(self):
        from enzyme_lookup import parse_ec_number_candidates

        assert parse_ec_number_candidates(self.TWO_ON_ONE_PROTEIN) == [
            "1.1.1.27",
            "1.1.1.28",
        ]
        assert parse_ec_number_candidates(self.TWO_PROTEINS) == [
            "1.1.1.27",
            "1.1.1.28",
        ]

    def test_relevance_order_is_kept(self):
        """UniProt's ordering is information. Sorting would discard it and
        make the first candidate arbitrary."""
        from enzyme_lookup import parse_ec_number_candidates

        reversed_hits = {"results": list(reversed(self.TWO_PROTEINS["results"]))}
        assert parse_ec_number_candidates(reversed_hits) == ["1.1.1.28", "1.1.1.27"]

    def test_the_same_ec_on_two_entries_is_one_candidate(self):
        """Two entries for one enzyme is not an ambiguity, and reporting it
        as one would make the command refuse a question it can answer."""
        from enzyme_lookup import parse_ec_number_candidates

        duplicated = {
            "results": [
                {"proteinDescription": {"recommendedName": {"ecNumbers": [{"value": "1.1.1.27"}]}}},
                {"proteinDescription": {"recommendedName": {"ecNumbers": [{"value": "1.1.1.27"}]}}},
            ]
        }
        assert parse_ec_number_candidates(duplicated) == ["1.1.1.27"]

    def test_alternative_names_are_read_too(self):
        """Some UniProt entries carry the EC only under an alternative
        name. The single-value parser already handled this and the plural
        one must not lose it."""
        from enzyme_lookup import parse_ec_number_candidates

        alt_only = {
            "results": [
                {
                    "proteinDescription": {
                        "alternativeNames": [{"ecNumbers": [{"value": "3.2.1.1"}]}]
                    }
                }
            ]
        }
        assert parse_ec_number_candidates(alt_only) == ["3.2.1.1"]

    def test_nothing_indexed_is_an_empty_list_not_a_guess(self):
        from enzyme_lookup import parse_ec_number_candidates

        assert parse_ec_number_candidates({"results": []}) == []

    def test_the_single_value_parser_still_agrees_with_the_plural_one(self):
        """One derivation, so the two cannot disagree about what UniProt's
        response contains (ADR 0003)."""
        from enzyme_lookup import parse_ec_number_candidates, parse_ec_number_search

        for data in (self.TWO_ON_ONE_PROTEIN, self.TWO_PROTEINS, {"results": []}):
            candidates = parse_ec_number_candidates(data)
            assert parse_ec_number_search(data) == (candidates[0] if candidates else None)
