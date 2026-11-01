"""The ENZYME parser reads the real file's quirks, and the index build is exact.

WHY THIS EXISTS
---------------
The finder is only as right as the two flat files it is built from, and the
format has quirks that a naive reader gets wrong silently: names and
reactions that wrap over several lines, a hyphen at the end of a wrapped
line that continues a word, `Transferred entry` records that list up to a
dozen successors across lines, `Deleted entry`, and preliminary numbers like
`1.1.1.n5`. A parser that mis-read any of them would not fail; it would drop
an enzyme or glue two names together, and the finder would then answer
confidently from a damaged index.

So these tests read an excerpt of the REAL `enzyme.dat` (release 02-Sep-2026,
`fixtures/enzyme_excerpt.dat`: the header and eleven records copied byte for
byte) and its `enzclass.txt`, and check the quirks one by one. Nothing here
is invented text.

The committed index is checked for what can be checked without the 9.6 MB
source: its shape, its release string, its size, and that building from the
same input twice gives the same bytes.
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from caterva.enzymes import source
from caterva.enzymes.index import INDEX_PATH, load_index

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def parsed():
    return source.parse_enzyme_dat((FIXTURES / "enzyme_excerpt.dat").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def by_ec(parsed):
    return {r.ec: r for r in parsed.records}


def test_the_release_comes_from_the_files_own_header(parsed):
    assert parsed.release == "02-Sep-2026"


def test_every_record_in_the_excerpt_is_read_and_no_line_is_skipped(parsed):
    assert [r.ec for r in parsed.records] == [
        "1.1.1.5", "1.1.1.28", "1.1.1.32", "1.1.1.34", "1.1.1.42", "1.1.1.74",
        "1.1.1.n5", "1.3.1.67", "2.7.1.1", "2.7.1.37", "3.4.21.14",
    ]
    assert parsed.skipped_lines == 0


def test_a_plain_record_has_name_alternatives_reaction_and_entries(by_ec):
    d_ldh = by_ec["1.1.1.28"]
    assert d_ldh.status == source.ACTIVE
    assert d_ldh.name == "D-lactate dehydrogenase"
    assert d_ldh.alternative_names == ["D-lactic acid dehydrogenase", "D-lactic dehydrogenase"]
    assert d_ldh.reaction == "(R)-lactate + NAD(+) = pyruvate + NADH + H(+)."
    assert d_ldh.entries
    assert all(name.count("_") >= 1 for _, name in d_ldh.entries)


def test_a_name_wrapped_over_two_lines_is_one_name(by_ec):
    assert by_ec["1.3.1.67"].name == (
        "cis-1,2-dihydroxy-4-methylcyclohexa-3,5-diene-1-carboxylate dehydrogenase"
    )


def test_a_reaction_wrapped_over_two_lines_is_one_reaction(by_ec):
    assert by_ec["1.1.1.34"].reaction == (
        "(R)-mevalonate + 2 NADP(+) + CoA = (3S)-3-hydroxy-3-methylglutaryl-CoA + "
        "2 NADPH + 2 H(+)."
    )


def test_a_hyphen_at_the_end_of_a_wrapped_alternative_name_continues_the_word(by_ec):
    names = by_ec["1.1.1.42"].alternative_names
    glued = [n for n in names if "isocitrate dehydrogenase-oxalosuccinate carboxylase" in n]
    assert glued, names
    assert not any("dehydrogenase- " in n for n in names)


def test_a_transferred_entry_has_no_name_and_says_where_it_went(by_ec):
    record = by_ec["1.1.1.5"]
    assert record.status == source.TRANSFERRED
    assert record.name == ""
    assert record.superseded_by == ["1.1.1.303", "1.1.1.304"]
    assert by_ec["1.1.1.32"].superseded_by == ["1.1.1.1"]


def test_a_transfer_to_many_enzymes_across_lines_loses_none(by_ec):
    # EC 2.7.1.37 became the whole protein-kinase family; "pyruvate kinase"
    # used to come back with two of its successors.
    assert by_ec["2.7.1.37"].superseded_by == [
        "2.7.11.1", "2.7.11.8", "2.7.11.9", "2.7.11.10", "2.7.11.11", "2.7.11.12",
        "2.7.11.13", "2.7.11.21", "2.7.11.22", "2.7.11.24", "2.7.11.25", "2.7.11.30",
        "2.7.12.1",
    ]
    assert by_ec["3.4.21.14"].superseded_by == [
        "3.4.21.62", "3.4.21.63", "3.4.21.64", "3.4.21.65", "3.4.21.67",
    ]


def test_a_deleted_entry_is_deleted_and_has_no_successor(by_ec):
    record = by_ec["1.1.1.74"]
    assert record.status == source.DELETED
    assert record.name == "" and record.superseded_by == []


def test_a_preliminary_number_is_kept_as_written(by_ec):
    record = by_ec["1.1.1.n5"]
    assert record.name == "3-methylmalate dehydrogenase"


def test_entries_are_read_as_accession_and_entry_name_pairs(by_ec):
    hexokinase = by_ec["2.7.1.1"]
    pairs = dict((name, acc) for acc, name in hexokinase.entries)
    assert pairs["HXK1_HUMAN"] == "P19367"
    assert pairs["HXK4_HUMAN"] == "P35557"


def test_the_class_names_are_keyed_by_ec_prefix():
    classes = source.parse_enzclass((FIXTURES / "enzclass_excerpt.txt").read_text(encoding="utf-8"))
    assert classes["1"] == "Oxidoreductases"
    assert classes["1.1"] == "Acting on the CH-OH group of donors"
    assert classes["1.1.1"] == "With NAD(+) or NADP(+) as acceptor"
    assert classes["1.1.98"] == "With other, known, acceptors"


def test_an_unreadable_entry_is_counted_not_dropped_silently():
    record, skipped = source.parse_record("ID   9.9.9.9\nDE   an enzyme.\nDR   not an entry;  Q1, X_HUMAN;\n")
    assert record.entries == [("Q1", "X_HUMAN")]
    assert skipped == 1


# --- the index builder -----------------------------------------------------


def _builder():
    spec = importlib.util.spec_from_file_location("build_enzyme_index", REPO / "scripts" / "build_enzyme_index.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def built():
    builder = _builder()
    dat = (FIXTURES / "enzyme_excerpt.dat").read_text(encoding="utf-8")
    classes = (FIXTURES / "enzclass_excerpt.txt").read_text(encoding="utf-8")
    return builder, builder.build_index(dat, classes)


def test_the_builder_is_deterministic_to_the_byte(built):
    builder, index = built
    dat = (FIXTURES / "enzyme_excerpt.dat").read_text(encoding="utf-8")
    classes = (FIXTURES / "enzclass_excerpt.txt").read_text(encoding="utf-8")
    again = builder.build_index(dat, classes)
    assert builder.serialise(index) == builder.serialise(again)


def test_the_gzip_carries_no_timestamp_and_no_file_name(built):
    builder, index = built
    data = builder.serialise(index)
    assert data[4:8] == b"\x00\x00\x00\x00", "the gzip header holds a modification time"
    assert data[3] == 0, "the gzip header holds a file name"


def test_the_only_date_in_the_index_is_the_release_string(built):
    _, index = built
    assert index["release"] == "02-Sep-2026"
    text = json.dumps(index)
    import re

    assert not re.search(r"20\d\d-\d\d-\d\d", text), "an ISO date, which would be a build timestamp"


def test_records_are_in_ec_order_with_preliminary_numbers_after_the_numbered(built):
    _, index = built
    order = list(index["enzymes"])
    assert order == [
        "1.1.1.5", "1.1.1.28", "1.1.1.32", "1.1.1.34", "1.1.1.42", "1.1.1.74",
        "1.1.1.n5", "1.3.1.67", "2.7.1.1", "2.7.1.37", "3.4.21.14",
    ]


def test_status_and_successors_are_recorded_without_a_name(built):
    _, index = built
    assert index["enzymes"]["1.1.1.5"] == {"s": "t", "to": ["1.1.1.303", "1.1.1.304"]}
    assert index["enzymes"]["1.1.1.74"] == {"s": "d"}


def test_every_organism_is_counted_and_thirteen_are_listed_in_full(built):
    builder, index = built
    hexokinase = index["enzymes"]["2.7.1.1"]
    assert hexokinase["c"]["HUMAN"] == 5
    assert sorted(hexokinase["p"]["HUMAN"]) == sorted(
        ["Q2TB90:HKDC1", "P19367:HXK1", "P52789:HXK2", "P52790:HXK3", "P35557:HXK4"])
    assert set(hexokinase["p"]) <= set(builder.FULL_LIST_ORGANISMS)
    assert set(hexokinase["c"]) - set(hexokinase["p"]), "organisms outside the 13 keep a count only"
    assert len(builder.FULL_LIST_ORGANISMS) == 13


def test_attribution_and_modifications_travel_inside_the_index(built):
    _, index = built
    assert index["licence"] == "CC BY 4.0"
    assert "SIB Swiss Institute of Bioinformatics" in index["creator"]
    assert index["source_uri"] == "https://enzyme.expasy.org/"
    assert "comments dropped" in index["modifications"]


def test_a_source_without_a_release_is_refused_rather_than_given_a_date():
    builder = _builder()
    with pytest.raises(SystemExit, match="Release"):
        builder.build_index("ID   1.1.1.1\nDE   alcohol dehydrogenase.\n//\n", "1. -. -.-  Oxidoreductases.\n")


# --- the committed index ---------------------------------------------------


def test_the_committed_index_is_small_and_current():
    size = INDEX_PATH.stat().st_size
    assert size < 3_000_000, f"{size:,} bytes: the index is meant to stay well under 3 MB"
    index = load_index()
    assert index.release == "02-Sep-2026"
    assert len(index.entries) > 8000
    assert len(index.classes) > 300
    raw = json.loads(gzip.decompress(INDEX_PATH.read_bytes()))
    assert raw["licence"] == "CC BY 4.0"


def test_the_committed_index_holds_the_enzymes_the_owner_complained_about():
    index = load_index()
    assert index.get("1.1.1.27").name == "L-lactate dehydrogenase"
    assert index.get("1.1.1.28").name == "D-lactate dehydrogenase"
    assert index.get("2.7.1.40").name == "pyruvate kinase"
    assert index.get("2.7.1.1").name == "hexokinase"
    assert index.get("1.1.1.5").status == "transferred"
    assert index.class_path("1.1.1.27") == (
        "Oxidoreductases > acting on the CH-OH group of donors > with NAD(+) or NADP(+) as acceptor"
    )


def test_the_index_ships_in_the_wheel_and_the_source_distribution():
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert "enzymes/data/enzyme_index.json.gz" in pyproject
    assert "enzymes/data/NOTICE.txt" in pyproject
    manifest = (REPO / "MANIFEST.in").read_text(encoding="utf-8")
    assert "caterva/enzymes/data/enzyme_index.json.gz" in manifest


def test_every_data_file_the_finder_reads_ships_in_the_wheel_and_the_source_distribution():
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    manifest = (REPO / "MANIFEST.in").read_text(encoding="utf-8")
    for path in sorted((REPO / "caterva" / "enzymes" / "data").iterdir()):
        assert f"enzymes/data/{path.name}" in pyproject, f"{path.name} is not package data"
        assert f"caterva/enzymes/data/{path.name}" in manifest, f"{path.name} is not in MANIFEST.in"


def test_the_data_notice_names_the_release_the_licence_and_the_modifications():
    text = (REPO / "caterva" / "enzymes" / "data" / "NOTICE.txt").read_text(encoding="utf-8")
    index = load_index()
    assert index.release in text
    assert "CC BY 4.0" in text and "creativecommons.org/licenses/by/4.0" in text
    assert "SIB Swiss Institute of Bioinformatics" in text
    assert "Modifications" in text
