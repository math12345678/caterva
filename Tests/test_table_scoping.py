"""
pytest suite for the structural table-scoping fix in brenda_client.py.

BRENDA reuses the same div.row/div.cell markup for every table on an
enzyme page - Synonyms, Reactions, Substrates, Inhibitors, Km Values,
Turnover Numbers, Ki Values, IC50 Values, etc. all look identical at the
row level. Before this fix, parse_brenda_km_html scanned the whole page
for "div.row", which meant Ki/Turnover Number/IC50 rows could leak into
"Km" results and only be caught (unreliably) by a numeric-range heuristic.

_find_table_container locates the real "KM Values" table by following the
same nav-link mechanism a person clicking the page would use - by label
text, not a hardcoded tab id - so this works for any enzyme's page. These
tests prove that mechanism directly, using a fixture with two structurally
identical tables (Km Values and Ki Values) containing a row for the same
substrate, which is exactly the scenario that could previously slip
through undetected.
"""

import os

import pytest

from brenda_client import BRENDAKmEntry, parse_brenda_km_html

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def mixed_tables_html():
    return load_fixture("brenda_mixed_tables_fixture.html")


@pytest.fixture
def ldh_html():
    return load_fixture("brenda_ldh_fixture.html")


@pytest.fixture
def ldh_no_tab_html():
    return load_fixture("brenda_ldh_no_tab_structure_fixture.html")


LACTATE = ["lactate"]
LDH_SUBSTRATES = ["lactate", "L-lactate", "pyruvate", "NADH", "NAD+", "NAD"]


# ---------------------------------------------------------------------------
# The core proof: a Ki-table row with the same substrate name and a
# perfectly plausible numeric value must NEVER appear in results.
# ---------------------------------------------------------------------------

def test_ki_table_row_never_appears_in_results(mixed_tables_html):
    entries = parse_brenda_km_html(mixed_tables_html, "1.1.1.27", LACTATE)
    # Only the genuine Km row (0.5) should come back - the Ki row (0.3),
    # despite matching the substrate name and having a perfectly plausible
    # numeric value, must be structurally excluded because it's not inside
    # the KM Values container at all.
    assert len(entries) == 1
    assert entries[0].km_value == 0.5
    assert entries[0].reference_id == "111111"


def test_ki_table_row_excluded_even_with_permissive_matching(mixed_tables_html):
    """Table scoping happens before substrate matching, so even permissive
    mode (which would otherwise accept any substrate name) must not pull
    in the Ki row - it's simply not part of the search space."""
    entries = parse_brenda_km_html(
        mixed_tables_html, "1.1.1.27", ["some-unrelated-compound"],
        require_substrate_match=False,
    )
    ref_ids = [e.reference_id for e in entries]
    assert "222222" not in ref_ids  # the Ki row's reference id


def test_km_row_from_mixed_fixture_is_table_scoped(mixed_tables_html):
    entries = parse_brenda_km_html(mixed_tables_html, "1.1.1.27", LACTATE)
    assert entries[0].table_scoped is True
    assert entries[0].flagged is False


# ---------------------------------------------------------------------------
# Structural confirmation on the (now tab-wrapped) LDH fixture
# ---------------------------------------------------------------------------

def test_ldh_entries_are_table_scoped_when_nav_structure_present(ldh_html):
    entries = parse_brenda_km_html(ldh_html, "1.1.1.27", LDH_SUBSTRATES)
    assert all(e.table_scoped is True for e in entries)
    assert all(not e.flagged for e in entries)


# ---------------------------------------------------------------------------
# Fallback path: no nav/tab structure present at all
# ---------------------------------------------------------------------------

def test_falls_back_to_whole_page_scan_when_no_tab_structure(ldh_no_tab_html):
    entries = parse_brenda_km_html(ldh_no_tab_html, "1.1.1.27", LDH_SUBSTRATES)
    assert len(entries) == 1
    assert entries[0].km_value == 10.73


def test_fallback_entries_are_marked_not_table_scoped(ldh_no_tab_html):
    entries = parse_brenda_km_html(ldh_no_tab_html, "1.1.1.27", LDH_SUBSTRATES)
    assert all(e.table_scoped is False for e in entries)


def test_fallback_entries_are_flagged_as_lower_confidence(ldh_no_tab_html):
    """Even a numerically plausible, correctly-matched row must be flagged
    when we couldn't structurally confirm it came from the KM Values
    table - the whole point is that a whole-page scan can't rule out that
    it's secretly a Ki/Turnover Number/IC50 row instead."""
    entries = parse_brenda_km_html(ldh_no_tab_html, "1.1.1.27", LDH_SUBSTRATES)
    assert entries[0].flagged is True
    assert "KM Values" in entries[0].flag_reason


def test_table_scoped_default_is_true():
    """A BRENDAKmEntry constructed without specifying table_scoped
    defaults to True - this matters because any code path that forgets to
    set it explicitly should default to the "trust it" state matching
    normal successful parsing, not silently imply distrust."""
    entry = BRENDAKmEntry(
        km_value=1.0, substrate="test", organism="Homo sapiens"
    )
    assert entry.table_scoped is True
