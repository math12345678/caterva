"""BRENDA bulk download parser, against a real captured excerpt.

The most important test in this file is
`test_a_bulk_row_refuses_to_be_used_for_resolution`. Everything else parses
data; that one enforces the finding that made this module a corpus reader
instead of a replacement resolution path.
"""
from __future__ import annotations

import pathlib

import pytest

from brenda_bulk import (
    ABSENT,
    EXPECTED_FIELDS,
    BulkRow,
    parse_rows,
    read_bytes,
    strenda_completeness,
)

FIXTURE = (
    pathlib.Path(__file__).parent
    / "fixtures"
    / "brenda_bulk"
    / "brenda_km_bulk_excerpt.tsv"
)


@pytest.fixture(scope="module")
def parsed():
    return parse_rows(FIXTURE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The finding
# ---------------------------------------------------------------------------

def test_no_row_carries_an_organism(parsed):
    """The whole reason this is not the resolution path.

    BRENDA's bulk KM export has no organism column -- verified across all
    623 rows of a real capture. Caterva's resolver is organism-specific by
    policy (ADR 0024, on Jeske's own recommendation), so these rows cannot
    answer the question the resolver asks.
    """
    rows, _ = parsed
    assert rows
    assert all(row.organism is None for row in rows)


def test_a_bulk_row_refuses_to_be_used_for_resolution(parsed):
    """Raising, not returning None.

    A None would be checked at one call site and forgotten at the next, and
    the failure would be a cross-species substitution with no warning --
    ADR 0024's exact prohibition, reintroduced through a side door.
    """
    rows, _ = parsed
    with pytest.raises(TypeError) as excinfo:
        rows[0].for_resolution()
    assert "no organism" in str(excinfo.value)
    assert "per-enzyme page path" in str(excinfo.value)


def test_an_expression_host_in_prose_is_not_read_as_the_organism(parsed):
    """About 2.5% of rows mention an organism inside the commentary, and
    almost always as an EXPRESSION HOST -- "recombinant enzyme expressed
    from Saccharomyces cerevisiae". Reading that as the source organism
    would be worse than having none: it would be confidently wrong.
    """
    rows, _ = parsed
    host_row = next(
        row for row in rows if row.commentary and "expressed from" in row.commentary
    )
    assert "Saccharomyces cerevisiae" in host_row.commentary
    assert host_row.organism is None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_the_trailing_empty_field_is_part_of_the_schema():
    """Every row ends in a tab producing a ninth, always-empty field.

    A reader that rstrip()s sees eight fields and reads every column
    correctly -- right up until it does not. This pins the count so the two
    readings cannot silently coexist.
    """
    assert EXPECTED_FIELDS == 9
    data_lines = [
        line
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    complete = [line for line in data_lines if len(line.split("\t")) == 9]
    assert complete, "fixture has no complete rows"
    for line in complete:
        assert line.endswith("\t")
        assert line.split("\t")[-1] == ""


def test_a_truncated_final_line_is_reported_not_silently_dropped(parsed):
    """The real capture ended mid-record. A download cut short is a fact
    the caller needs -- a parser that quietly skips it makes a truncated
    file look like a small one."""
    _, report = parsed
    assert report.malformed
    line_number, excerpt = report.malformed[0]
    assert excerpt.startswith("1.1.1.1")
    assert line_number > 0


def test_the_report_accounts_for_every_line(parsed):
    """A reader that returns rows without saying what it skipped lets a
    caller check a denominator it cannot see."""
    _, report = parsed
    total_lines = len(FIXTURE.read_text(encoding="utf-8").splitlines())
    assert report.total_lines_considered == total_lines


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def test_additional_information_rows_are_not_values(parsed):
    """21 of 623 rows in the capture describe kinetics in prose. They are
    records ABOUT measurements, not measurements."""
    rows, report = parsed
    assert report.additional_information == 2
    extra = [row for row in rows if row.is_additional_information]
    assert len(extra) == 2
    assert all(row.value is None for row in extra)


def test_numeric_values_parse(parsed):
    rows, _ = parsed
    values = [row.value for row in rows if row.value is not None]
    assert 0.000035 in values
    assert 1.5 in values


def test_absent_commentary_is_none_not_the_sentinel(parsed):
    """`-` is a real sentinel BRENDA writes, never an empty string. It must
    not reach a consumer as the literal text."""
    rows, _ = parsed
    assert ABSENT == "-"
    assert any(row.commentary is None for row in rows)
    assert all(row.commentary != ABSENT for row in rows)


def test_multi_reference_lists_split(parsed):
    rows, _ = parsed
    multi = next(row for row in rows if len(row.reference_ids) > 1)
    assert multi.reference_ids == ("285577", "285578", "285630", "285638")


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

def test_ph_and_temperature_are_read_in_either_order(parsed):
    """`pH 8.0, 60 C` and `45 C, pH 8.8` both occur in the real data."""
    rows, _ = parsed
    ph_first = next(r for r in rows if r.commentary and r.commentary.startswith("pH 8.0"))
    assert ph_first.assay_ph == 8.0
    assert ph_first.assay_temperature_c == 60.0

    temp_first = next(r for r in rows if r.commentary and r.commentary.startswith("45"))
    assert temp_first.assay_ph == 8.8
    assert temp_first.assay_temperature_c == 45.0


def test_a_temperature_range_is_reported_as_its_midpoint(parsed):
    """`21-23 C`. Reporting the low end would understate a temperature the
    source states as a range; the raw commentary travels on the row so the
    range is not lost."""
    rows, _ = parsed
    ranged = next(r for r in rows if r.commentary and "21-23" in r.commentary)
    assert ranged.assay_temperature_c == 22.0


def test_explicitly_unreported_conditions_are_a_fact_about_the_publication(parsed):
    """"pH and temperature not specified in the publication" is BRENDA
    telling us the paper omitted them. That is different from our parser
    failing to find them, and ADR 0010 depends on the distinction."""
    rows, _ = parsed

    both = next(
        r for r in rows if r.commentary == "pH and temperature not specified in the publication"
    )
    assert set(both.assay_unreported) == {"pH", "temperature"}
    assert both.assay_ph is None and both.assay_temperature_c is None

    temp_only = next(
        r for r in rows if r.commentary and r.commentary.startswith("pH 6.0, temperature not")
    )
    assert temp_only.assay_unreported == ("temperature",)
    assert temp_only.assay_ph == 6.0
    assert temp_only.assay_temperature_c is None


def test_a_stated_missing_ph_is_not_then_parsed_from_elsewhere(parsed):
    """`mutant ..., 30 C, pH not specified in the publication` contains the
    letters "pH" twice. A naive regex would pull a pH out of the very
    sentence saying there isn't one."""
    rows, _ = parsed
    row = next(r for r in rows if r.commentary and "Y25A/W49F/W167Y" in r.commentary)
    assert row.assay_ph is None
    assert row.assay_unreported == ("pH",)
    assert row.assay_temperature_c == 30.0


def test_a_ph_in_parentheses_is_found():
    """`in 0.1 M glycine-NaOH buffer (pH 10.5), at 65 C`"""
    rows, _ = parse_rows(FIXTURE.read_text(encoding="utf-8"))
    row = next(r for r in rows if r.commentary and "(pH 10.5)" in r.commentary)
    assert row.assay_ph == 10.5
    assert row.assay_temperature_c == 65.0


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def test_a_utf8_file_is_not_mangled_by_assuming_latin1():
    """The bug two passes of unit tests missed.

    The first `read_bytes` assumed Latin-1 unconditionally. That is right
    for a live BRENDA download and wrong for anything already re-encoded: a
    UTF-8 file containing a real degree sign decodes as Latin-1 into "A°",
    the temperature regex stops matching, and every row silently loses its
    temperature.

    The corpus statistics then reported "0 rows report both pH and
    temperature" for a file where six of eleven do. A confidently wrong
    number, produced by a decoder that could not fail.

    The earlier tests fed the decoder BYTES they had just encoded. This one
    feeds it a FILE, which is what the failure needed.
    """
    utf8_file = "pH 7.0, 25\u00b0C".encode("utf-8")
    decoded = read_bytes(utf8_file)
    assert decoded == "pH 7.0, 25°C"
    assert "Â" not in decoded


def test_the_real_fixture_yields_temperatures_when_read_as_a_file():
    """End of the same story: the fixture on disk, read the way the corpus
    script reads it, must produce temperatures."""
    rows, _ = parse_rows(read_bytes(FIXTURE.read_bytes()))
    with_both = [
        row
        for row in rows
        if row.assay_ph is not None and row.assay_temperature_c is not None
    ]
    assert len(with_both) >= 5, (
        "a decoder that mangles the file makes this zero while every unit "
        "test still passes"
    )


def test_latin1_bytes_decode_rather_than_raising():
    """BRENDA declares UTF-8 and sends ISO-8859-1. The degree sign arrives
    as 0xB0, which is not valid UTF-8 -- decoding by the header either
    raises or, worse, silently corrupts every temperature."""
    raw = "pH 7.0, 25\xb0C".encode("iso-8859-1")
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")
    assert read_bytes(raw) == "pH 7.0, 25°C"


def test_a_utf8_mangled_degree_sign_still_yields_a_temperature(parsed):
    """The fixture preserves U+FFFD where a capture decoded 0xB0 as UTF-8.
    Silently losing those temperatures would be worse than a documented
    repair, because the row would look like one with no reported
    temperature -- a claim about the publication that is false."""
    rows, _ = parsed
    mangled = next(r for r in rows if r.commentary and "�" in r.commentary)
    assert mangled.assay_temperature_c is not None


# ---------------------------------------------------------------------------
# The aggregate question this file makes answerable
# ---------------------------------------------------------------------------

def test_strenda_completeness_counts_only_real_measurements(parsed):
    """`additional information` rows have no value, so including them would
    understate completeness by counting rows that never had conditions to
    report."""
    rows, _ = parsed
    stats = strenda_completeness(rows)

    measured = [r for r in rows if not r.is_additional_information]
    assert stats["measured_rows"] == len(measured)
    assert (
        stats["both_conditions"] + stats["one_condition"] + stats["neither_condition"]
        == stats["measured_rows"]
    )
    assert stats["both_conditions"] > 0
    assert stats["neither_condition"] > 0


def test_empty_input_reports_zero_rather_than_looking_like_success():
    rows, report = parse_rows("")
    assert rows == []
    assert report.rows == 0
    assert report.total_lines_considered == 0


# ---------------------------------------------------------------------------
# Defensive guards, tested on SYNTHETIC input
#
# The strings below were NOT observed in the capture. They are constructed
# to exercise guards in the condition parser that real data has not yet hit.
# Labelled as synthetic because a fixture that looks captured and is not is
# the worst kind of test data -- it would let someone conclude BRENDA writes
# something it does not.
#
# The guards exist because a mutation pass showed that removing one changed
# no test outcome. An untested guard is indistinguishable from a guard that
# does not work, so it gets a test or it gets deleted.
# ---------------------------------------------------------------------------

from brenda_bulk import _parse_conditions  # noqa: E402


def test_a_ph_stated_unreported_is_not_then_taken_from_the_same_sentence():
    """SYNTHETIC. If BRENDA ever writes both "pH not specified" and a
    numeric pH in one commentary, the explicit statement about the
    publication wins.

    Without the guard the parser would report a pH for a row whose own
    commentary says the publication did not give one -- inventing a fact
    about a paper, which is the failure this project is entirely about.
    """
    ph, temperature, unreported = _parse_conditions(
        "pH not specified in the publication, buffer adjusted to pH 8.0, 30°C"
    )
    assert ph is None, "the stated absence must win over a number elsewhere"
    assert unreported == ("pH",)
    assert temperature == 30.0


def test_a_temperature_stated_unreported_is_not_then_taken_from_the_same_sentence():
    """SYNTHETIC, same reasoning for the other axis."""
    ph, temperature, unreported = _parse_conditions(
        "temperature not specified in the publication, water bath set to 37°C, pH 7.2"
    )
    assert temperature is None
    assert unreported == ("temperature",)
    assert ph == 7.2


def test_both_stated_unreported_suppresses_both():
    """SYNTHETIC."""
    ph, temperature, unreported = _parse_conditions(
        "pH and temperature not specified in the publication (pH 7.4, 37°C assumed)"
    )
    assert ph is None and temperature is None
    assert set(unreported) == {"pH", "temperature"}
