"""The live re-verification, exercised without a network.

The fetch is injected, so every outcome this script can reach is tested
here: matched, drifted, and the two distinct ways a check can fail to run.

The three-outcome discipline is the point. "The value changed" and "we could
not look" are different facts, and a script that conflated them would either
send someone rewriting correct golden values or leave a wrong number in
place believing the network was at fault.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from verify_golden_against_live import check_one, render, run  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

G1 = {
    "id": "G1: LDH/lactate/Homo sapiens",
    "ec": "1.1.1.27",
    "substrate": "lactate",
    "organism": "Homo sapiens",
    "fixture": "brenda_ldh_fixture.html",
    "expected": {
        "km": 10.73,
        "unit": "mM",
        "organism": "Homo sapiens",
        "source": "brenda_exact",
        "ref": "740253",
        "cross_species_flag": False,
    },
}


def fixture_resolver(entry: dict):
    """Re-resolve through the REAL resolver, fed the captured fixture.

    Deliberately `resolve_kinetic_value` rather than the parser: the script
    under test must ask the resolver rather than reimplement its selection
    policy, and a test that stubbed the parser instead would not notice if
    it went back to doing so.
    """
    import fallback_logic

    from test_golden_set import (  # the same doubles the golden suite uses
        fake_taxon_id_provider,
        fake_uniprot_provider,
        make_html_provider,
    )

    return fallback_logic.resolve_kinetic_value(
        enzyme_ec=entry["ec"],
        organism=entry["organism"],
        substrate=entry["substrate"],
        html_provider=make_html_provider(entry["fixture"]),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        quantity=entry.get("quantity", "km"),
        allow_cross_species=bool(entry.get("allow_cross_species")),
    )


def unreachable_resolver(_entry: dict):
    raise ConnectionError("proxy refused the connection")


def moved_markup_resolver(_entry: dict):
    """Markup the parser reads nothing out of -- BRENDA redesigned."""
    import fallback_logic

    from test_golden_set import fake_taxon_id_provider, fake_uniprot_provider

    return fallback_logic.resolve_kinetic_value(
        enzyme_ec="1.1.1.27",
        organism="Homo sapiens",
        substrate="lactate",
        html_provider=lambda _url: "<html><body>BRENDA has been redesigned</body></html>",
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
    )


# ---------------------------------------------------------------------------
# The three outcomes
# ---------------------------------------------------------------------------

def test_a_pinned_value_that_still_holds_is_matched():
    outcome = check_one(G1, fixture_resolver)
    assert outcome.status == "matched"
    assert outcome.observed == 10.73
    assert outcome.expected == 10.73


def test_a_changed_value_is_drift_and_names_both_numbers():
    """The reader needs the old number and the new one. A verdict of
    "drifted" with no figures cannot be acted on without redoing the work."""
    moved = {**G1, "expected": {**G1["expected"], "km": 99.9}}
    outcome = check_one(moved, fixture_resolver)

    assert outcome.status == "drifted"
    assert "99.9" in outcome.detail
    assert "10.73" in outcome.detail
    assert outcome.expected == 99.9
    assert outcome.observed == 10.73


def test_a_network_failure_is_unreachable_and_never_drift():
    """Reporting a network failure as drift would send someone rewriting
    correct golden values. This is the assertion that prevents it."""
    outcome = check_one(G1, unreachable_resolver)
    assert outcome.status == "unreachable"
    assert outcome.status != "drifted"
    assert "ConnectionError" in outcome.detail


def test_markup_the_parser_reads_nothing_from_is_drift_naming_both_causes():
    """An empty resolve means either BRENDA dropped the row or the markup
    moved. Both mean the golden set no longer describes the live database,
    and the message must not pick one cause and hide the other."""
    outcome = check_one(G1, moved_markup_resolver)
    assert outcome.status == "drifted"
    assert "BRENDA changed" in outcome.detail
    assert "markup moved" in outcome.detail


def test_every_failure_mode_of_the_fetch_reads_as_unreachable():
    """Deliberately broad. DNS, TLS, proxy, timeout and 500 all mean the
    same thing here, and none of them mean the value changed."""
    for error in (TimeoutError, OSError, ValueError, RuntimeError):
        def failing(_entry: dict, exc=error):
            raise exc("boom")

        assert check_one(G1, failing).status == "unreachable"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def test_the_report_does_not_call_an_unreachable_check_a_pass():
    """The most tempting summary line to get wrong."""
    outcomes = run([G1], unreachable_resolver)
    text = render(outcomes)
    assert "could NOT be checked" in text
    assert "That is not a" in text and "pass" in text
    assert "still matches what BRENDA reports" not in text


def test_the_report_says_so_plainly_when_everything_matches():
    text = render(run([G1], fixture_resolver))
    assert "Every pinned value still matches" in text
    assert "DRIFTED" not in text


def test_drift_tells_the_reader_to_check_what_was_published():
    """A stale golden value may already have been quoted somewhere. Fixing
    the repository is only half of it."""
    moved = {**G1, "expected": {**G1["expected"], "km": 99.9}}
    text = render(run([moved], fixture_resolver))
    assert "quoted the old number" in text


def test_mixed_results_report_both_categories_separately():
    moved = {**G1, "id": "G-moved", "expected": {**G1["expected"], "km": 99.9}}
    outcomes = run([G1], fixture_resolver) + run([moved], fixture_resolver) + run(
        [{**G1, "id": "G-unreachable"}], unreachable_resolver
    )
    text = render(outcomes)
    assert "DRIFTED" in text
    assert "could NOT be checked" in text


# ---------------------------------------------------------------------------
# It reads the real golden set, not a copy of it
# ---------------------------------------------------------------------------

def test_it_loads_the_same_golden_set_the_tests_assert():
    """A second copy of the golden set would be the duplicate source of
    truth this project keeps finding. It imports the real one."""
    from verify_golden_against_live import _load_golden

    golden = _load_golden()
    assert len(golden) >= 5
    ids = {entry["id"] for entry in golden}
    assert any(name.startswith("G1:") for name in ids)
    for entry in golden:
        assert "expected" in entry and "ec" in entry and "substrate" in entry
