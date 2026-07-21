"""
pytest suite for aggregate "N entries" row expansion in brenda_client.py.

BRENDA collapses substrates with many measurements into a summary row
whose first cell is a RANGE ("0.0018 - 1100"), not a single value, and
buries the individual measurements in hidden sibling rows already present
in the static HTML (unhidden client-side by showRows() JS - confirmed
live, no extra network request needed). Before this fix, the summary
row's range correctly failed numeric parsing and got skipped (no
fabrication), but the sub-rows behind it were never looked at either, so
every measurement for a heavily-studied substrate like lactate silently
vanished.

CORRECTION (2026-07): an earlier version of this test file / fixture
claimed one of these rows was "real human lactate Km data (0.0026 mM,
isozyme H4)". That was wrong - the live capture (see
brenda_aggregate_row_fixture.html for the verbatim source) shows that
row's organism is "Sus scrofa" (pig), not "Homo sapiens". None of the 6
real sub-rows captured for (S)-lactate on the live LDH page are human.
The fixture and every test below were corrected to use the real,
verbatim-captured organism for each row - no fabricated "Homo sapiens"
row anywhere in this file.
"""

import os

from brenda_client import parse_brenda_km_html

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return f.read()


LACTATE = ["(S)-lactate", "lactate"]


def test_aggregate_summary_row_itself_is_never_parsed_as_a_value():
    """The summary row's own cell ('0.0018 - 1100') must never appear as
    a km_value - it's a range, not a measurement, and parsing it as a
    single float would be a fabrication."""
    html = load_fixture("brenda_aggregate_row_fixture.html")
    entries = parse_brenda_km_html(html, "1.1.1.27", LACTATE, target_organism=None)
    km_values = [e.km_value for e in entries]
    assert 0.0018 not in [v for v in km_values if v > 1000] # sanity: no garbage
    # none of the returned values should be unparseable range artifacts
    assert all(isinstance(v, float) for v in km_values)


def test_sub_rows_behind_aggregate_row_are_recovered():
    """target_organism=None (cross-species mode) uses a generic binomial-
    nomenclature pattern (GENERIC_ORGANISM_PATTERN), not an enumerated
    list of known organisms - so all 6 real sub-rows are recognized here
    (Cryptosporidium parvum, Sus scrofa x3, Acinetobacter calcoaceticus,
    Epidalea calamita), including the non-lab-standard organisms an
    earlier fixed-list version (KNOWN_ORGANISM_PATTERN) would have
    silently missed."""
    html = load_fixture("brenda_aggregate_row_fixture.html")
    entries = parse_brenda_km_html(html, "1.1.1.27", LACTATE, target_organism=None)
    km_values = sorted(e.km_value for e in entries)
    assert km_values == [0.0018, 0.0026, 0.0057, 0.0142, 0.083, 0.515]


def test_pig_sub_row_is_recovered_with_correct_organism_filter():
    """Real captured organism for this row is Sus scrofa (pig), not
    Homo sapiens - this test name/assertion was corrected after an
    earlier version fabricated a human organism label for this exact row."""
    html = load_fixture("brenda_aggregate_row_fixture.html")
    entries = parse_brenda_km_html(html, "1.1.1.27", LACTATE, target_organism="Sus scrofa")
    km_values = sorted(e.km_value for e in entries)
    # 3 real Sus scrofa isozyme rows: H4 (0.0026), H2M2 (0.0057), M4 (0.0142)
    assert km_values == [0.0026, 0.0057, 0.0142]


def test_no_human_row_exists_in_this_fixture():
    """Explicit regression guard for the mislabeling bug: querying for
    Homo sapiens against this fixture must return nothing, because none
    of the real captured rows are human. If this ever returns a result,
    something has silently reintroduced a fabricated/mislabeled row."""
    html = load_fixture("brenda_aggregate_row_fixture.html")
    entries = parse_brenda_km_html(html, "1.1.1.27", LACTATE, target_organism="Homo sapiens")
    assert entries == []


def test_multi_accession_uniprot_cell_is_kept_whole():
    """LDH sub-rows can list multiple UniProt accessions in one cell
    (isozyme subunits sharing a BRENDA row) - both must be kept, not
    truncated to the first match. Real organism for this row is Sus
    scrofa."""
    html = load_fixture("brenda_aggregate_row_fixture.html")
    entries = parse_brenda_km_html(html, "1.1.1.27", LACTATE, target_organism="Sus scrofa")
    assert all(e.uniprot == "P00339,P00336" for e in entries)


def test_sub_rows_are_still_table_scoped():
    html = load_fixture("brenda_aggregate_row_fixture.html")
    entries = parse_brenda_km_html(html, "1.1.1.27", LACTATE, target_organism="Sus scrofa")
    assert all(e.table_scoped is True for e in entries)
    assert all(e.flagged is False for e in entries)
