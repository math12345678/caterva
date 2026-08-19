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
