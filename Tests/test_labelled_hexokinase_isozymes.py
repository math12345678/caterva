"""The labelled hexokinase set agrees with the recorded page it was read from.

WHY THIS EXISTS
---------------
`Tests/fixtures/labelled/ec_2.7.1.1_homo_sapiens_glucose_km_isozymes.tsv`
is a hand-labelled answer key: which human isozyme each D-glucose Km row on
the recorded hexokinase page belongs to. A future isozyme rule (ADR 0179,
plan milestone M3) is to be scored against it. An answer key that has
drifted from the page it describes scores the rule against a fiction, so
this holds the table to the page in both directions, through the literature
layer's own parser, offline.

The parser is reached the way the product reaches it, `fetch_brenda_html`,
with the recorded-page variable set here and nowhere else
(`Tests/test_recorded_env_is_test_only.py`).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

import brenda_client

HERE = Path(__file__).resolve().parent
RECORDED = HERE / "fixtures" / "recorded"
LABELLED = HERE / "fixtures" / "labelled"
TSV = LABELLED / "ec_2.7.1.1_homo_sapiens_glucose_km_isozymes.tsv"
README = LABELLED / "README.md"

COLUMNS = ["reference_id", "pmid", "km_mM", "isozyme", "how_known", "commentary", "paper_title"]
HOW_KNOWN = {"row_text", "reference_title", "accession", "not_checked"}
ISOZYMES = {"hexokinase I", "hexokinase II", "hexokinase III", "glucokinase", "unlabelled"}

#: What the parser yielded on 2026-10-17. If the page or the parser changes
#: this number, the README's "25" is wrong until somebody re-reads the page.
EXPECTED_ROWS = 25

#: The grouping the README states, so the two cannot drift apart.
EXPECTED_GROUPING = {
    "hexokinase I": 5,
    "hexokinase II": 1,
    "hexokinase III": 2,
    "glucokinase": 15,
    "unlabelled": 2,
}

#: References whose label rests on the plan's 2026-09-30 reading of the
#: paper title, with no literature page fetched since; the README names them.
TITLE_NOT_RE_READ = {"641067", "663393", "672188"}


def _labelled() -> list[dict[str, str]]:
    with TSV.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


@pytest.fixture(scope="module")
def page_rows():
    """The human D-glucose Km rows, parsed from the recorded page offline."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("CATERVA_BRENDA_RECORDED", str(RECORDED))
        html = brenda_client.fetch_brenda_html("2.7.1.1")
    rows = brenda_client.parse_brenda_km_html(
        html, "2.7.1.1", [], "Homo sapiens", require_substrate_match=False,
    )
    return [row for row in rows if row.substrate == "D-glucose"]


def _pair(value: float, reference: str | None) -> tuple[float, str]:
    return (float(value), reference or "")


def test_the_table_has_the_documented_shape():
    rows = _labelled()
    assert len(rows) == EXPECTED_ROWS
    assert list(rows[0].keys()) == COLUMNS
    for row in rows:
        assert re.fullmatch(r"\d{6}", row["reference_id"]), row
        assert row["how_known"] in HOW_KNOWN, row
        assert row["isozyme"] in ISOZYMES, row
        assert float(row["km_mM"]) > 0, row
        assert row["commentary"].strip() == row["commentary"] and row["commentary"], row
        assert row["pmid"] == "" or re.fullmatch(r"\d{7,8}", row["pmid"]), row


def test_every_labelled_row_is_on_the_page_and_every_page_row_is_labelled(page_rows):
    labelled = sorted(_pair(r["km_mM"], r["reference_id"]) for r in _labelled())
    parsed = sorted(_pair(r.km_value, r.reference_id) for r in page_rows)
    assert len(parsed) == EXPECTED_ROWS, (
        f"the parser yields {len(parsed)} human D-glucose Km rows, not "
        f"{EXPECTED_ROWS}; re-read the page and update the table and its README"
    )
    assert labelled == parsed


def test_the_commentary_column_is_the_rows_own_words(page_rows):
    by_pair = {_pair(r.km_value, r.reference_id): r for r in page_rows}
    assert len(by_pair) == EXPECTED_ROWS, "a (value, reference) pair occurs twice on the page"
    for row in _labelled():
        parsed = by_pair[_pair(row["km_mM"], row["reference_id"])]
        assert row["commentary"] == parsed.conditions, row["reference_id"]


def test_a_row_text_label_is_in_the_row_and_an_accession_label_is_on_the_row(page_rows):
    by_pair = {_pair(r.km_value, r.reference_id): r for r in page_rows}
    seen = {"row_text": 0, "accession": 0}
    for row in _labelled():
        parsed = by_pair[_pair(row["km_mM"], row["reference_id"])]
        if row["how_known"] == "row_text":
            seen["row_text"] += 1
            assert re.search(rf"\b{re.escape(row['isozyme'])}\b", row["commentary"]), row
        elif row["how_known"] == "accession":
            seen["accession"] += 1
            assert parsed.uniprot == "P35557", row
            assert row["isozyme"] == "glucokinase", row
        else:
            assert parsed.uniprot is None, row
    assert seen == {"row_text": 5, "accession": 7}


def test_not_checked_rows_are_exactly_the_unlabelled_ones():
    rows = _labelled()
    not_checked = {(r["reference_id"], r["km_mM"]) for r in rows if r["how_known"] == "not_checked"}
    unlabelled = {(r["reference_id"], r["km_mM"]) for r in rows if r["isozyme"] == "unlabelled"}
    assert not_checked == unlabelled == {("702314", "0.63"), ("702314", "0.76")}
    for row in rows:
        assert (row["pmid"] == "") == (row["how_known"] == "not_checked"), row


def test_the_grouping_matches_the_readme():
    counts: dict[str, int] = {}
    for row in _labelled():
        counts[row["isozyme"]] = counts.get(row["isozyme"], 0) + 1
    assert counts == EXPECTED_GROUPING
    text = README.read_text(encoding="utf-8")
    assert f"{EXPECTED_ROWS} rows" in text
    assert "2026-09-30" in text and "2026-10-17" in text
    assert "M3" in text
    for isozyme, count in EXPECTED_GROUPING.items():
        assert f"**{isozyme}**, {count} row" in text, isozyme


def test_a_title_label_names_the_title_or_the_readme_says_why_not():
    rows = _labelled()
    untitled = {r["reference_id"] for r in rows if r["how_known"] == "reference_title" and not r["paper_title"]}
    assert untitled == TITLE_NOT_RE_READ
    text = README.read_text(encoding="utf-8")
    for reference in TITLE_NOT_RE_READ:
        assert reference in text
    titled = {r["reference_id"]: r["paper_title"] for r in rows if r["paper_title"]}
    assert titled["641068"] == (
        "Human beta-cell glucokinase. Dual role of Ser-151 in catalysis and hexose affinity"
    )
    assert "human brain hexokinase" in titled["674942"]
    assert "human glucokinase" in titled["739603"]
    assert {r["pmid"] for r in rows if r["reference_id"] == "641068"} == {"7730377"}
