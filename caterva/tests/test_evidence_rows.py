"""Rows from the recorded hexokinase page, re-found by identity, certified by bytes.

Pinned against Tests/fixtures/recorded/brenda_2.7.1.1.html.gz (sha256
3a69b492..., fetched 2026-09-28), read directly: no network, no environment
variable. The parser is the literature layer's own (Tests/brenda_client.py),
so the counts below are what IT yields; a change in the parser changes them,
and the test says so rather than hiding the difference.
"""
from __future__ import annotations

import gzip
from pathlib import Path
from types import SimpleNamespace

import pytest

from caterva.evidence import rows as rows_module
from caterva.evidence.claims import PARSE_BRENDA_TABLE, make_row, make_snapshot
from caterva.evidence.rows import (
    AMBIGUITIES,
    ROW_OPENING,
    certificates_for,
    find_row,
    locator_ec,
    ordinals_from_grades,
    ordinals_from_profile,
    parsed_rows,
    rows_from_page,
    same_row,
    value_text_of,
)

REPO = Path(__file__).resolve().parents[2]
PAGE_PATH = REPO / "Tests" / "fixtures" / "recorded" / "brenda_2.7.1.1.html.gz"
PAGE = gzip.decompress(PAGE_PATH.read_bytes())
HTML = PAGE.decode("utf-8")
SNAPSHOT = make_snapshot(PAGE, source="brenda_enzyme", locator="https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1",
                         retrieved_at="2026-09-28", licence="CC BY 4.0")


# Parsed once per module, and only when a test here runs: ~2 s per table on
# this 3.7 MB page. At import they were paid by every collection of the
# suite, a `-k` that selects none of these tests included.

@pytest.fixture(scope="module")
def human_km_pairs():
    """Each human Km row beside the parser's entry it was made from. The
    rows are rows_from_page's: test_parsed_rows_keeps_the_entry_beside_its_row
    holds the two functions to the same rows."""
    return parsed_rows(HTML, ec="2.7.1.1", table="km", organism="Homo sapiens", snapshot_ref=SNAPSHOT.ref)


@pytest.fixture(scope="module")
def human_km(human_km_pairs):
    return [row for _, row in human_km_pairs]


@pytest.fixture(scope="module")
def human_kcat():
    return rows_from_page(HTML, ec="2.7.1.1", table="kcat", organism="Homo sapiens", snapshot_ref=SNAPSHOT.ref)


@pytest.fixture(scope="module")
def human_glucose_km(human_km):
    return [r for r in human_km if r.substrate == "D-glucose"]


def region_of(offset: int) -> tuple[int, int]:
    """The [start, end) of the BRENDA row holding `offset`, by the same delimiter."""
    starts = [m.start() for m in ROW_OPENING.finditer(PAGE)]
    before = [s for s in starts if s <= offset]
    start = before[-1]
    after = [s for s in starts if s > start]
    return start, after[0] if after else len(PAGE)


class TestRowsFromPage:
    def test_the_human_km_table_yields_what_the_parser_yields(self, human_km, human_kcat, human_glucose_km):
        assert len(human_km) == 159
        assert len(human_glucose_km) == 25, "the 25 human D-glucose Km rows of the plan's labelled set"
        assert len(human_kcat) == 92

    def test_every_row_records_the_parsers_reading(self, human_km_pairs, human_kcat):
        assert len(human_km_pairs) == 159, "the loop below checks every row, so there must be rows"
        for entry, row in human_km_pairs:
            assert row.snapshot == SNAPSHOT.ref
            assert row.parser == PARSE_BRENDA_TABLE
            assert row.quantity == "km"
            assert row.unit == "mM"
            assert row.organism == "Homo sapiens"
            # value_text is the parser's float spelled by value_text_of, and
            # that spelling reads back as itself, so it names one number.
            assert row.value_text == value_text_of(entry.km_value), row.locator
            assert value_text_of(float(row.value_text)) == row.value_text, row.locator
            assert (row.substrate, row.commentary, row.reference) == (
                entry.substrate, entry.conditions, entry.reference_id), row.locator
        assert {r.unit for r in human_kcat} == {"1/s"}
        assert {r.quantity for r in human_kcat} == {"kcat"}

    def test_locators_are_unique_and_index_duplicates_in_parse_order(self, human_km, human_glucose_km):
        locators = [r.locator for r in human_km]
        assert len(set(locators)) == len(locators)
        by_key: dict[tuple, list[str]] = {}
        for r in human_km:
            by_key.setdefault((r.substrate, r.reference, r.value_text), []).append(r.locator)
        duplicated = {k: v for k, v in by_key.items() if len(v) > 1}
        assert duplicated, "the page lists one paper's value twice somewhere, or the index is untested"
        for key, found in duplicated.items():
            assert [loc.rsplit(":", 1)[1] for loc in found] == [str(i) for i in range(len(found))], key
        glucose_6 = [r for r in human_glucose_km if r.value_text == "6" and r.reference == "641068"]
        assert [r.locator for r in glucose_6] == ["brenda:2.7.1.1:km:Homo sapiens:D-glucose:641068:6:0"]

    def test_the_index_tells_apart_two_rows_the_docstring_names(self, human_km):
        """rows.py's reason for `n`: ref 721735 gives 7.1e-07 mM for ATP
        for two mutants, and only the commentary, which is not in the
        locator, tells them apart."""
        stem = "brenda:2.7.1.1:km:Homo sapiens:ATP:721735:7.1e-07:"
        pair = [r for r in human_km if r.locator.startswith(stem)]
        assert [r.locator for r in pair] == [stem + "0", stem + "1"]
        assert pair[0].commentary.startswith("mutant W167F/W257F")
        assert pair[1].commentary.startswith("mutant W99R/W167F")
        assert pair[0].id != pair[1].id

    def test_the_value_text_is_the_parsers_float_in_fifteen_digits(self, human_glucose_km):
        assert value_text_of(6.0) == "6"
        assert value_text_of(0.0732) == "0.0732"
        assert value_text_of(40.1) == "40.1"
        assert value_text_of(18.0) == "18"
        assert {r.value_text for r in human_glucose_km} >= {"6", "0.0732", "6.3", "0.032"}

    def test_organism_none_reads_every_organism_from_the_cells(self):
        every = rows_from_page(HTML, ec="2.7.1.1", table="km", organism=None, snapshot_ref=SNAPSHOT.ref)
        assert len(every) == 442
        organisms = {r.organism for r in every}
        assert {"Homo sapiens", "Saccharomyces cerevisiae", "Trypanosoma cruzi"} <= organisms
        assert all(r.locator.split(":")[3] == r.organism for r in every)

    def test_an_unknown_table_is_refused(self):
        with pytest.raises(Exception, match="not one of"):
            rows_from_page(HTML, ec="2.7.1.1", table="vmax", organism=None, snapshot_ref=SNAPSHOT.ref)

    def test_parsed_rows_keeps_the_entry_beside_its_row(self, human_kcat):
        pairs = parsed_rows(HTML, ec="2.7.1.1", table="kcat", organism="Homo sapiens", snapshot_ref=SNAPSHOT.ref)
        assert [row for _, row in pairs] == human_kcat
        entry, row = next(p for p in pairs if p[1].value_text == "40.1" and p[1].reference == "739603")
        assert entry.km_value == 40.1
        assert entry.conditions == row.commentary == "wild-type, pH 7.6, 25 °C"

    def test_locator_ec(self, human_km):
        assert locator_ec(human_km[0].locator) == "2.7.1.1"
        assert locator_ec("not a locator") is None


class TestFindRow:
    def test_the_six_mm_row_of_reference_641068_is_found(self, human_glucose_km):
        row = find_row(human_glucose_km, value=6.0, commentary="30°C, pH 7.5, wild-type", reference="641068")
        assert row is not None
        assert row.value_text == "6"
        assert row.reference == "641068"
        assert row.commentary == "30°C, pH 7.5, wild-type"
        assert row.locator == "brenda:2.7.1.1:km:Homo sapiens:D-glucose:641068:6:0"

    def test_the_kcat_row_the_page_holds_is_forty_point_one(self, human_kcat):
        row = find_row(human_kcat, value=40.1, commentary="wild-type, pH 7.6, 25 °C", reference="739603")
        assert row is not None
        assert row.substrate == "D-glucose"
        assert row.accession == "P35557"

    def test_the_identity_rule_is_value_commentary_and_reference_when_both_have_one(self, human_glucose_km):
        row = human_glucose_km[0]
        assert same_row(row, value=float(row.value_text), commentary=row.commentary, reference=None)
        assert same_row(row, value=float(row.value_text), commentary=row.commentary, reference=row.reference)
        assert not same_row(row, value=float(row.value_text), commentary=row.commentary, reference="000000")
        assert not same_row(row, value=float(row.value_text) * 2, commentary=row.commentary, reference=None)
        assert not same_row(row, value=float(row.value_text), commentary="other", reference=None)
        assert find_row(human_glucose_km, value=6.0, commentary="30°C, pH 7.5, wild-type", reference="000000") is None
        assert find_row(human_glucose_km, value=6.0, commentary=None, reference="641068") is None

    def test_an_ambiguous_match_returns_the_first_and_says_so(self):
        a = make_row(snapshot=SNAPSHOT.ref, parser=PARSE_BRENDA_TABLE, locator="brenda:x:km:o:s:1:6:0",
                     quantity="km", value_text="6", unit="mM", substrate="s", organism="o", reference="1")
        b = make_row(snapshot=SNAPSHOT.ref, parser=PARSE_BRENDA_TABLE, locator="brenda:x:km:o:s:1:6:1",
                     quantity="km", value_text="6", unit="mM", substrate="s", organism="o", reference="1")
        before = len(AMBIGUITIES)
        assert find_row([a, b], value=6, commentary=None, reference="1") == a
        assert len(AMBIGUITIES) == before + 1
        assert "2 rows match" in AMBIGUITIES[-1]
        assert "brenda:x:km:o:s:1:6:1" in AMBIGUITIES[-1]
        del AMBIGUITIES[before:]


class TestCertificates:
    def test_the_spans_decode_to_the_matched_text_and_sit_in_one_row(self, human_glucose_km):
        row = find_row(human_glucose_km, value=6.0, commentary="30°C, pH 7.5, wild-type", reference="641068")
        certificates = certificates_for(row, PAGE)
        matched = [c.matched for c in certificates]
        assert matched == ["641068", "6", "30°C, pH 7.5, wild-type", "D-glucose", "Homo sapiens"]
        for c in certificates:
            assert c.snapshot == SNAPSHOT.ref
            assert PAGE[c.span[0]:c.span[1]].decode("utf-8") == c.matched
        regions = {region_of(c.span[0]) for c in certificates}
        assert len(regions) == 1, "every certificate lies within one BRENDA table row"
        start, end = regions.pop()
        assert all(start <= c.span[0] and c.span[1] <= end for c in certificates)
        assert PAGE[start:end].startswith(b'<div id="tab')

    def test_the_kcat_row_is_certified_too(self, human_kcat):
        row = find_row(human_kcat, value=40.1, commentary="wild-type, pH 7.6, 25 °C", reference="739603")
        certificates = certificates_for(row, PAGE)
        assert [c.matched for c in certificates][:3] == ["739603", "40.1", "wild-type, pH 7.6, 25 °C"]
        assert len({region_of(c.span[0]) for c in certificates}) == 1

    def test_every_human_glucose_km_row_is_certified_in_one_row_each(self, human_glucose_km):
        assert len(human_glucose_km) == 25, "the loop below checks every row, so there must be rows"
        for row in human_glucose_km:
            certificates = certificates_for(row, PAGE)
            assert len(certificates) >= 3, row.locator
            assert len({region_of(c.span[0]) for c in certificates}) == 1, row.locator
            for c in certificates:
                assert PAGE[c.span[0]:c.span[1]].decode("utf-8") == c.matched

    @pytest.mark.parametrize("table", ["km", "kcat"])
    def test_every_row_of_every_organism_is_certified_in_its_own_table_row(self, table):
        # A neighbour row can share the reference, value and commentary; the
        # substrate and organism are what keep the certificate on this row.
        rows = rows_from_page(HTML, ec="2.7.1.1", table=table, organism=None, snapshot_ref=SNAPSHOT.ref)
        assert len(rows) == {"km": 442, "kcat": 125}[table]
        for row in rows:
            certificates = certificates_for(row, PAGE)
            matched = [c.matched for c in certificates]
            assert row.substrate in matched and row.organism in matched, row.locator
            assert len({region_of(c.span[0]) for c in certificates}) == 1, row.locator

    def test_a_row_the_page_does_not_hold_gets_no_certificate(self, human_glucose_km):
        row = make_row(snapshot=SNAPSHOT.ref, parser=PARSE_BRENDA_TABLE,
                       locator="brenda:2.7.1.1:km:Homo sapiens:D-glucose:999999:6:0", quantity="km",
                       value_text="6", unit="mM", substrate="D-glucose", organism="Homo sapiens",
                       commentary="30°C, pH 7.5, wild-type", reference="999999")
        assert certificates_for(row, PAGE) == ()
        real = find_row(human_glucose_km, value=6.0, commentary="30°C, pH 7.5, wild-type", reference="641068")
        wrong_value = make_row(snapshot=real.snapshot, parser=real.parser, locator=real.locator,
                               quantity="km", value_text="6.0001", unit="mM", substrate=real.substrate,
                               organism=real.organism, commentary=real.commentary, reference=real.reference)
        assert certificates_for(wrong_value, PAGE) == (), "the reference is on the page; the value is not in its row"

    def test_a_cell_spelling_the_same_number_otherwise_is_certified_by_its_own_text(self):
        page = (b'<div id="tab1r0" class="row rgrey1"><div class="cell"><span>0.30\n</span></div>'
                b'<div class="cell"><span>x\n</span></div><div class="cell"><span>o\n</span></div>'
                b'<div class="cell"><span><a>111111</a>\n</span></div></div>')
        snap = make_snapshot(page, source="brenda_enzyme", locator="u", retrieved_at="t", licence="l")
        row = make_row(snapshot=snap.ref, parser=PARSE_BRENDA_TABLE, locator="brenda:1:km:o:x:111111:0.3:0",
                       quantity="km", value_text="0.3", unit="mM", substrate="x", organism="o", reference="111111")
        certificates = certificates_for(row, page)
        assert [c.matched for c in certificates] == ["111111", "0.30", "x", "o"]
        assert page[certificates[1].span[0]:certificates[1].span[1]] == b"0.30"

    def test_the_row_delimiter_matches_the_four_shapes_and_not_a_cell(self):
        assert ROW_OPENING.match(b'<div id="tab12_head" class="row">')
        assert ROW_OPENING.match(b'<div id="tab12r3" class="row rgrey1">')
        assert ROW_OPENING.match(b'<div id="tab12r4sr0" class="row rgrey2">')
        assert ROW_OPENING.match(b'<div id="tab12r13sr112" class="hidden rgrey1">')
        assert not ROW_OPENING.match(b'<div id="tab12r4sr0c5" class="cell">')
        assert not ROW_OPENING.match(b'<a class="rowpreview" href="x">')
        assert len(ROW_OPENING.findall(PAGE)) == 4615


class TestOrdinals:
    def test_profile_ordinals_are_the_resolvers_three_axes(self):
        profile = SimpleNamespace(ordinals=lambda: (2, 2, 1, None))
        assert ordinals_from_profile(profile) == {
            "assay_completeness": "2", "variant_statement": "2", "organism_match": "1",
        }
        assert ordinals_from_profile(SimpleNamespace(ordinals=lambda: (0, None, 0, 3))) == {
            "assay_completeness": "0", "variant_statement": None, "organism_match": "0",
        }

    def test_grade_ordinals_follow_the_reliability_vocabulary(self):
        assert ordinals_from_grades({"assay_completeness": "complete", "condition_proximity": "not_assessed",
                                     "organism_match": "exact"}) == {
            "assay_completeness": "2", "condition_proximity": None, "organism_match": "2",
        }
        assert ordinals_from_grades({"assay_completeness": "absent", "condition_proximity": "far",
                                     "organism_match": "unknown"}) == {
            "assay_completeness": "0", "condition_proximity": "0", "organism_match": "0",
        }
        assert ordinals_from_grades({})["organism_match"] is None
        scales = rows_module.GRADE_SCALES
        assert scales["assay_completeness"]["partial"] < scales["assay_completeness"]["complete"]
        assert scales["condition_proximity"]["far"] < scales["condition_proximity"]["near"]
        assert scales["organism_match"]["related"] < scales["organism_match"]["exact"]
        assert scales["organism_match"]["unknown"] == scales["organism_match"]["distant"]

    def test_the_grades_on_the_resolvers_frontier_dicts_are_in_the_scales(self):
        """The vocabulary the frontier dicts carry (Tests/reliability.py) is the one GRADE_SCALES knows."""
        from caterva.checkout import literature_module

        reliability = literature_module("reliability")
        score = reliability.score_reliability(ph=7.5, temperature_c=30.0, unreported=[], reference=None,
                                              requested_organism="Homo sapiens", measured_organism="Homo sapiens",
                                              cross_species=False, relatedness=None)
        grades = {"assay_completeness": score.assay_completeness.grade,
                  "condition_proximity": score.condition_proximity.grade,
                  "organism_match": score.organism_match.grade}
        assert grades == {"assay_completeness": "complete", "condition_proximity": "not_assessed",
                          "organism_match": "exact"}
        assert ordinals_from_grades(grades) == {"assay_completeness": "2", "condition_proximity": None,
                                                "organism_match": "2"}
