"""Reading a pasted or dropped table: `caterva.rates.ingest`.

WHAT IS REAL AND WHAT IS A FORMAT
---------------------------------
Every measurement here is a value of `examples/rates/puromycin.csv`, R's
`datasets::Puromycin` (test_rates_puromycin.py says whose). The files built
from it below are the same values in the shapes real laboratories save them
in: tabs and decimal commas from a spreadsheet's clipboard, a byte-order mark
and Windows line endings from a plate reader's export, a wide layout with one
column per replicate, a header with units in brackets. They are formats, not
data. The units written in a header that is not the file's own (the `mM` and
`uM/min` of the conversion tests) are labels put on real numbers to exercise
the unit arithmetic; no test claims them about the experiment. Rows
corrupted on purpose (a cell that says n/a, a spreadsheet error) contain no
invented number.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from caterva.rates import ingest
from caterva.rates.table import read_table

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "rates" / "puromycin.csv"
TEXT = EXAMPLE.read_text(encoding="utf-8")
ROWS = [r for r in csv.reader(io.StringIO("\n".join(l for l in TEXT.splitlines() if not l.startswith("#"))))][1:]
TREATED = [(s, v) for s, v, g in ROWS if g == "treated"]
UNTREATED = [(s, v) for s, v, g in ROWS if g == "untreated"]


def comma(x: str) -> str:
    return x.replace(".", ",")


def pasted(rows=TREATED, header="[S] (ppm)\tv0 (counts/min/min)", decimal=True, eol="\r\n", bom=True) -> str:
    body = eol.join(f"{comma(s) if decimal else s}\t{comma(v) if decimal else v}" for s, v in rows)
    return ("\ufeff" if bom else "") + header + eol + body + eol + eol


def engine_view(read):
    """The canonical text read back by the engine's own reader."""
    return read_table("dataset.csv", text=read["canonical"], group=read["group_column"], names=read["column_names"])


# ---------------------------------------------------------------------------
# The file the command reads
# ---------------------------------------------------------------------------


def test_the_real_file_is_read_as_long_form_and_its_own_comments_are_kept():
    read = ingest.inspect(TEXT, filename="puromycin.csv")
    assert read["ok"] and read["shape"] == "long"
    assert [c["role"] for c in read["columns"]] == ["substrate", "rate", "group"]
    assert read["summary"]["rows_used"] == 23 and read["summary"]["groups"] == [
        {"label": "treated", "rows": 12}, {"label": "untreated", "rows": 11}]
    assert read["group_column"] == "state"
    assert "source: Treloar MA (1974)" in read["canonical"]
    original = read_table(EXAMPLE, group="state")
    again = engine_view(read)
    assert again.substrate == original.substrate and again.rate == original.rate and again.group == original.group
    assert {k: v.text for k, v in again.units.items()} == {k: v.text for k, v in original.units.items()}


def test_each_decision_is_a_sentence_and_nothing_is_skipped_in_a_clean_file():
    read = ingest.inspect(TEXT)
    assert read["problems"] == [] and read["summary"]["rows_skipped"] == 0
    joined = " ".join(read["decisions"])
    for phrase in ("Fields are split at commas", "The first row is a header", "decimals are read with a point",
                   "'state') is the group"):
        assert phrase in joined
    assert not any("--" in d or "—" in d for d in read["decisions"])


def test_the_sigma_options_say_what_the_table_offers():
    read = ingest.inspect(TEXT)
    assert read["sigma_options"] == {"column": False, "replicate_sets": 11, "replicate_dof": 11,
                                     "replicates": True, "residuals": True}


# ---------------------------------------------------------------------------
# What a spreadsheet and a plate reader hand over
# ---------------------------------------------------------------------------


def test_a_spreadsheet_paste_with_tabs_decimal_commas_crlf_bom_and_units_in_the_header():
    read = ingest.inspect(pasted())
    assert read["ok"], read["refusal"]
    assert read["format"]["delimiter"] == "tab" and read["format"]["decimal"] == "," and read["format"]["bom"]
    assert read["format"]["line_ending"] == "CRLF" and read["format"]["blank_lines"] == 1
    assert read["shape"] == "two-column"
    assert [c["name"] for c in read["columns"]] == ["[S]", "v0"] and [c["unit"] for c in read["columns"]] == ["ppm", "counts/min/min"]
    assert read["column_names"] == {"substrate": "S", "rate": "v0"}
    data = engine_view(read)
    assert data.substrate == tuple(float(s) for s, _ in TREATED) and data.rate == tuple(float(v) for _, v in TREATED)
    text = " ".join(read["decisions"])
    for phrase in ("byte-order mark", "Windows line endings", "decimal commas", "blank line"):
        assert phrase in text


def test_a_semicolon_table_with_decimal_commas():
    text = "substrate (ppm);rate (counts/min/min)\n" + "\n".join(f"{comma(s)};{comma(v)}" for s, v in UNTREATED) + "\n"
    read = ingest.inspect(text)
    assert read["ok"] and read["format"]["delimiter"] == "semicolon" and read["format"]["decimal"] == ","
    assert engine_view(read).substrate == tuple(float(s) for s, _ in UNTREATED)


def test_wide_form_becomes_one_row_per_replicate_and_replicates_are_identical_conditions():
    by_s = {}
    for s, v in TREATED:
        by_s.setdefault(s, []).append(v)
    text = "[S] (ppm)\trep1 (counts/min/min)\trep2 (counts/min/min)\n" + "\n".join(
        f"{s}\t{vs[0]}\t{vs[1]}" for s, vs in by_s.items()) + "\n"
    read = ingest.inspect(text)
    assert read["ok"] and read["shape"] == "wide"
    assert [c["role"] for c in read["columns"]] == ["substrate", "rate", "rate"]
    assert read["mapping"]["roles"]["rates"] == [1, 2] and read["mapping"]["roles"]["rate"] is None
    data = engine_view(read)
    assert len(data) == 12 and data.substrate == tuple(float(s) for s, _ in TREATED)
    assert sorted(data.rate) == sorted(float(v) for _, v in TREATED)
    assert read["sigma_options"]["replicate_sets"] == 6
    assert "Wide layout" in " ".join(read["decisions"])


def test_wide_form_with_a_missing_replicate_says_so_and_keeps_the_others():
    text = "S (ppm)\tr1 (counts/min/min)\tr2 (counts/min/min)\n0.02\t76\t47\n0.06\t97\t\n0.11\t123\t139\n"
    read = ingest.inspect(text)
    assert read["ok"] and read["summary"]["rows_used"] == 5
    assert any(p["severity"] == "note" and "blank replicate" in p["message"] and p["line"] == 3 for p in read["problems"])


def test_a_headerless_pair_of_numbers_is_two_columns_and_needs_its_units_named():
    text = "\n".join(f"{s}\t{v}" for s, v in TREATED) + "\n"
    read = ingest.inspect(text)
    assert not read["ok"] and read["units_needed"] and read["shape"] == "two-column"
    assert any("has no unit" in p["message"] for p in read["problems"])
    assert read["format"]["header"] is False
    named = ingest.inspect(text, mapping={"units": {"substrate": "ppm", "rate": "counts/min/min"}})
    assert named["ok"] and named["summary"]["rows_used"] == 12
    assert named["canonical"].splitlines()[-13].startswith("substrate (ppm),rate (counts/min/min)")


def test_unit_spellings_are_normalised_and_the_change_is_stated():
    for given in ("µM/min", "μM/min", "uM/min", "µM·min⁻¹", "µM min-1", "uM min^-1"):
        read = ingest.inspect(f"S (mM)\tv ({given})\n1\t2\n2\t3\n3\t3.5\n")
        assert read["ok"], (given, read["refusal"])
        assert read["units"]["rate"]["read_as"] == "uM/min", given


def test_header_names_with_brackets_keep_their_unit_and_axis_name():
    assert ingest.split_header("[S] (mM)") == ("[S]", "mM")
    assert ingest.split_header("v0 (µM/min)") == ("v0", "µM/min")
    assert ingest.split_header("[S]") == ("[S]", None)
    assert ingest.split_header("[S] [mM]") == ("[S]", "mM")
    assert ingest.split_header("group") == ("group", None)


# ---------------------------------------------------------------------------
# Units, converted by exact multiplication and said in a sentence
# ---------------------------------------------------------------------------


def test_a_conversion_is_multiplied_stated_and_the_unit_is_the_target():
    text = "S (nM)\tv (nM/s)\n" + "\n".join(f"{float(s) * 1000:g}\t{v}" for s, v in TREATED) + "\n"
    read = ingest.inspect(text, mapping={"target": {"substrate": "uM", "rate": "uM/min"}})
    assert read["ok"], read["refusal"]
    assert read["units"]["substrate"]["factor"] == 0.001 and read["units"]["rate"]["target"] == "uM/min"
    assert abs(read["units"]["rate"]["factor"] - 0.06) < 1e-15
    data = engine_view(read)
    assert data.units["substrate"].text == "uM" and data.units["rate"].text == "uM/min"
    for got, (s, v) in zip(zip(data.substrate, data.rate), TREATED):
        assert got[0] == pytest.approx(float(s)) and got[1] == pytest.approx(float(v) * 0.06, rel=1e-12)
    sentences = " ".join(read["decisions"])
    assert "substrate: nM to uM, every value multiplied by 0.001" in sentences
    assert "rate: nM/s to uM/min, every value multiplied by 0.06" in sentences


def test_an_arbitrary_unit_cannot_be_converted_and_is_fitted_as_given():
    read = ingest.inspect(TEXT, mapping={"target": {"rate": "uM/min"}})
    assert read["ok"] and read["units"]["rate"]["factor"] == 1.0
    assert any("cannot be converted" in p["message"] for p in read["problems"])
    assert engine_view(read).units["rate"].text == "counts/min/min"


def test_an_unreadable_unit_is_refused_in_the_engines_words_under_its_column():
    read = ingest.inspect("S (mM)\tv (umol/L/min)\n1\t2\n2\t3\n")
    assert not read["ok"]
    blocking = [p for p in read["problems"] if p["severity"] == "blocking"]
    assert blocking and blocking[0]["column"] == "v" and "molar concentration" in blocking[0]["message"]


def test_a_sigma_without_a_unit_is_read_in_the_rate_unit_and_says_so():
    text = "S (mM)\tv (uM/min)\tsd\n1\t10\t1\n2\t15\t1\n3\t18\t1\n"
    read = ingest.inspect(text)
    assert read["ok"] and engine_view(read).sigma == (1.0, 1.0, 1.0)
    assert any("sigma column" in d and "rate's unit" in d for d in read["decisions"])
    assert read["sigma_options"]["column"] is True


def test_a_standard_error_column_is_not_taken_for_a_standard_deviation():
    read = ingest.inspect("S (mM)\tv (uM/min)\tsem (uM/min)\n1\t10\t1\n2\t15\t1\n3\t18\t1\n")
    assert read["ok"] and read["sigma_options"]["column"] is False
    sem = read["columns"][2]
    assert sem["role"] is None and "standard error of the mean" in sem["role_reason"]


# ---------------------------------------------------------------------------
# Problems are located, and nothing is dropped or coerced silently
# ---------------------------------------------------------------------------


def messy():
    lines = ["substrate (ppm)\trate (counts/min/min)\tstate"]
    rows = [(s, v, "treated") for s, v in TREATED]
    for k, (s, v, g) in enumerate(rows):
        lines.append(f"{s}\t{v}\t{g}")
        if k == 1:
            lines.append("0.06\tn/a\ttreated")        # line 4: not a number
        if k == 3:
            lines.append("0.11\t\ttreated")           # blank rate
        if k == 5:
            lines.append("0.22\t#DIV/0!\ttreated")    # a spreadsheet error
        if k == 7:
            lines.append("0,56\t200\ttreated")        # a comma in a table of points
    lines.insert(3, "")
    return "\n".join(lines) + "\n"


def test_bad_rows_are_skipped_listed_by_line_and_column_and_never_coerced():
    read = ingest.inspect(messy())
    assert read["ok"], read["refusal"]
    s = read["summary"]
    assert s["rows_read"] == 16 and s["rows_used"] == 12 and s["rows_skipped"] == 4
    skipped = [p for p in read["problems"] if p["severity"] == "skipped"]
    numbered = {i: line for i, line in enumerate(messy().split("\n"), start=1)}
    lines_of = lambda text: next(i for i, line in numbered.items() if line.startswith(text))
    expected = [(lines_of("0.06\tn/a"), "rate"), (lines_of("0.11\t\ttreated"), "rate"),
                (lines_of("0.22\t#DIV"), "rate"), (lines_of("0,56"), "substrate")]
    assert [(p["line"], p["column"]) for p in skipped] == expected
    assert "'n/a' is not a number" in skipped[0]["message"]
    assert "the rate is blank" in skipped[1]["message"]
    assert "spreadsheet error value" in skipped[2]["message"]
    assert "comma where this table's decimal point would be" in skipped[3]["message"]
    data = engine_view(read)
    assert data.substrate == tuple(float(s) for s, _ in TREATED)
    assert f"# skipped line {expected[0][0]}: " in read["canonical"]
    flags = {r["line"]: r["flags"] for r in read["preview"]["rows"] if r["flags"]}
    assert set(flags) == {e[0] for e in expected} and all(not r["used"] for r in read["preview"]["rows"] if r["line"] in flags)


def test_a_zero_standard_deviation_stops_the_fit_instead_of_dropping_the_row():
    read = ingest.inspect("S (mM)\tv (uM/min)\tsd (uM/min)\n1\t10\t1\n2\t15\t0\n3\t18\t1\n")
    assert not read["ok"] and read["canonical"] is None
    assert any(p["severity"] == "blocking" and "infinite weight" in p["message"] and p["line"] == 3 for p in read["problems"])


def test_a_negative_concentration_is_skipped_and_a_negative_rate_is_kept():
    read = ingest.inspect("S (mM)\tv (uM/min)\n-1\t10\n1\t-0.5\n2\t3\n3\t4\n")
    assert read["ok"] and read["summary"]["rows_used"] == 3
    assert any(p["line"] == 2 and "negative" in p["message"] for p in read["problems"])
    assert engine_view(read).rate[0] == -0.5


def test_a_mixed_decimal_table_uses_the_majority_and_lists_the_rest():
    read = ingest.inspect("S (mM)\tv (uM/min)\n1,5\t10\n2,5\t15\n3.5\t18\n4,5\t20\n")
    assert read["format"]["decimal"] == "," and read["summary"]["rows_used"] == 3
    assert any(p["line"] == 4 and "has a point where this table's decimal comma would be" in p["message"] for p in read["problems"])
    assert "mixes decimal commas" in " ".join(read["decisions"])


def test_a_thousands_separator_is_named_not_guessed():
    read = ingest.inspect("S (mM)\tv (uM/min)\n1\t1,234.5\n2\t3\n3\t4\n4\t5\n")
    assert any("thousands separator" in p["message"] for p in read["problems"])


def test_a_typographic_minus_is_read_and_said():
    read = ingest.inspect("S (mM)\tv (uM/min)\n1\t−0.5\n2\t3\n3\t4\n")
    assert engine_view(read).rate[0] == -0.5
    assert any("typographic minus" in d for d in read["decisions"])


def test_the_roles_can_be_changed_and_the_change_is_reflected():
    read = ingest.inspect(TEXT)
    swapped = ingest.inspect(TEXT, mapping={"roles": {"substrate": 1, "rate": 0, "group": 2}, "units": {"substrate": "counts/min/min", "rate": "ppm"}})
    assert not swapped["ok"] or swapped["mapping"]["roles"]["substrate"] == 1
    off = ingest.inspect(TEXT, mapping={"roles": {"group": None}})
    assert off["ok"] and off["group_column"] is None and off["summary"]["groups"] == []
    assert read["summary"]["groups"] and "not used" not in " ".join(off["decisions"])


def test_one_column_given_two_roles_is_refused_by_name():
    read = ingest.inspect(TEXT, mapping={"roles": {"substrate": 0, "rate": 0}})
    assert not read["ok"] and "one role" in read["refusal"].lower() or "two roles" in read["refusal"]


def test_a_delimiter_can_be_chosen_over_the_detected_one():
    read = ingest.inspect("S (mM);v (uM/min)\n1;2\n2;3\n3;4\n", mapping={"delimiter": "comma"})
    assert not read["ok"]
    read = ingest.inspect("S (mM);v (uM/min)\n1;2\n2;3\n3;4\n")
    assert read["format"]["delimiter"] == "semicolon" and read["ok"]


# ---------------------------------------------------------------------------
# Refusals and hostile input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,phrase", [
    ("", "no table"),
    ("\n\n  \n", "no table"),
    ("# only a comment\n", "no table"),
    ("substrate (mM),rate (uM/min)\n", "no rows of data"),
    ("one column\n1\n2\n", "only one column"),
    ("PK\x03\x04\x00\x00binary", "NUL byte"),
    ("S (mM)\tv (uM/min)\n1\t2\x07\n", "control character"),
    ("S (mM)\tv (uM/min)\n" + "1\t" + "9" * (ingest.MAX_CELL_CHARS + 1) + "\n", "cell is longer"),
    ("S (mM)\tv (uM/min)\n" + "1\t2" + " " * (ingest.MAX_LINE_CHARS + 5) + "\n", "longer than"),
    ("\t".join(f"c{i}" for i in range(ingest.MAX_COLUMNS + 1)) + "\n" + "\t".join("1" for _ in range(ingest.MAX_COLUMNS + 1)) + "\n", "columns"),
])
def test_text_that_is_not_a_table_is_refused_with_a_plain_reason(text, phrase):
    read = ingest.inspect(text)
    assert read["ok"] is False and read["canonical"] is None
    assert phrase in read["refusal"], read["refusal"]
    assert read["problems"][0]["severity"] == "blocking"


def test_a_file_over_the_byte_limit_is_refused_before_it_is_parsed():
    big = "S (mM)\tv (uM/min)\n" + "1\t2\n" * (ingest.MAX_BYTES // 4 + 10)
    read = ingest.inspect(big)
    assert not read["ok"] and f"limited to {ingest.MAX_BYTES:,} bytes" in read["refusal"] and read["bytes"] > ingest.MAX_BYTES


def test_a_table_over_the_row_limit_is_refused_with_the_limit():
    rows = "S (mM)\tv (uM/min)\n" + "1\t2\n" * (ingest.MAX_ROWS + 1)
    assert len(rows) < ingest.MAX_BYTES
    read = ingest.inspect(rows)
    assert not read["ok"] and f"limited to {ingest.MAX_ROWS:,}" in read["refusal"]
    assert ingest.inspect("S (mM)\tv (uM/min)\n" + "1\t2\n" * ingest.MAX_ROWS)["summary"]["rows_used"] == ingest.MAX_ROWS


def test_a_mapping_that_is_not_a_question_is_refused_not_ignored():
    for bad in ({"nope": 1}, {"delimiter": "slash"}, {"decimal": ";"}, {"header": "yes"}, {"roles": {"substrate": -1}},
                {"roles": {"substrate": True}}, {"roles": {"rates": "1"}}, {"roles": {"colour": 1}}, {"units": {"substrate": 5}},
                {"units": {"nothing": "mM"}}, {"target": {"substrate": "x" * 41}}, [], "text"):
        with pytest.raises(ingest.IngestRefused):
            ingest.inspect(TEXT, mapping=bad)
    with pytest.raises(ingest.IngestRefused):
        ingest.inspect(b"bytes", mapping=None)  # type: ignore[arg-type]


def test_text_in_a_group_label_cannot_become_a_formula_in_an_export():
    text = "S (mM)\tv (uM/min)\tgroup\n1\t2\t=SUM(A1)\n2\t3\t=SUM(A1)\n1\t2.5\t+puro\n2\t3.5\t+puro\n"
    read = ingest.inspect(text)
    assert read["ok"] and engine_view(read).group[0] == "=SUM(A1)"
    assert ingest.neutralise_cell("=SUM(A1)") == "'=SUM(A1)"
    assert ingest.neutralise_cell("+puro") == "'+puro"
    assert ingest.neutralise_cell("@x") == "'@x" and ingest.neutralise_cell("-cmd|' /C calc'!A0") == "'-cmd|' /C calc'!A0"
    assert ingest.neutralise_cell("\tx") == "'\tx"
    assert ingest.neutralise_cell("-0.5") == "-0.5" and ingest.neutralise_cell("1e-3") == "1e-3"
    assert ingest.neutralise_cell("treated") == "treated" and ingest.neutralise_cell("") == ""


def test_the_filename_is_cleaned_of_control_characters_and_length():
    read = ingest.inspect(TEXT, filename="a\nb\x00c" + "x" * 300)
    assert "\n" not in read["filename"] and "\x00" not in read["filename"] and len(read["filename"]) <= 200
    assert "\n" not in read["canonical"].split("\n")[0]


def test_the_methods_sentence_names_the_conversions_and_the_skips():
    read = ingest.inspect(messy())
    sentence = ingest.methods_sentence(read)
    assert "12 measurements used" in sentence and "4 row(s) skipped" in sentence and "pasted text" in sentence
    converted = ingest.inspect("S (nM)\tv (nM/s)\n1000\t1\n2000\t2\n3000\t2.5\n", mapping={"target": {"substrate": "uM"}})
    assert "substrate from nM to uM" in ingest.methods_sentence(converted)


def test_the_limits_in_the_contract_are_the_modules():
    from caterva.studio import contract

    assert contract.RATES_MAX_BYTES == ingest.MAX_BYTES and contract.RATES_MAX_ROWS == ingest.MAX_ROWS
    assert ingest.MAX_BYTES * 2 <= contract.MAX_BODY_BYTES
