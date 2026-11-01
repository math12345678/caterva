"""Each BRENDA table's values carry the unit of THAT table.

`parse_brenda_km_html` serves three tables through one code path, selected
by `table_label`. It derived `_unit` correctly -- "1/s" for Turnover
Numbers, "mM" for Km and Ki -- and then constructed every entry with a
hardcoded ``unit="mM"``. `_unit` reached only the plausibility-flag
message, never the returned object.

So every kcat BRENDA ever returned was labelled a millimolar
concentration. The real acetylcholinesterase turnover number, 6500 s^-1,
was emitted as ``6500 mM``. The wrong unit then travelled through
``KineticResult.unit`` and ``science_agent_runner.py`` into the API
response, and any downstream unit check reading ``.unit`` could not fail,
because the field was a constant.

The existing kcat coverage in test_fallback_logic.py asserts value,
source, organism and citation -- but never the unit, which is why this
survived. These tests assert exactly that field.
"""

import pathlib

import pytest

import brenda_client as bc

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="replace")


def test_turnover_entries_are_per_second_not_millimolar():
    entries = bc.parse_brenda_turnover_html(
        _fixture("brenda_ache_kcat_fixture.html"),
        "acetyl thiocholine",
        "Homo sapiens",
    )
    assert entries, "fixture parsed no turnover entries"

    for entry in entries:
        assert entry.unit == "1/s", (
            f"kcat {entry.km_value} labelled {entry.unit!r}; a turnover "
            "number is a rate (s^-1), not a concentration"
        )
        assert entry.unit != "mM"


def test_the_golden_ache_turnover_number_is_labelled_correctly():
    # ADR 0019's golden case: AChE (EC 3.1.1.7) + acetyl thiocholine +
    # Homo sapiens, kcat = 6500 s^-1, BRENDA reference 649716.
    entries = bc.parse_brenda_turnover_html(
        _fixture("brenda_ache_kcat_fixture.html"),
        "acetyl thiocholine",
        "Homo sapiens",
    )
    golden = [e for e in entries if e.km_value == 6500.0]
    assert golden, "the 6500 s^-1 golden value is not in the fixture"
    assert golden[0].unit == "1/s"


def test_ki_entries_are_still_millimolar():
    # The fix must not flip Km/Ki, which ARE concentrations.
    entries = bc.parse_brenda_ki_html(
        _fixture("brenda_ldh_ki_fixture.html"), "pyruvate", "Homo sapiens"
    )
    assert entries, "fixture parsed no Ki entries"
    assert all(e.unit == "mM" for e in entries)


@pytest.mark.parametrize(
    "table_label,expected_unit",
    [
        (bc.TURNOVER_TABLE_LABEL, "1/s"),
        (bc.KI_TABLE_LABEL, "mM"),
    ],
)
def test_unit_follows_the_table_label(table_label, expected_unit):
    """The property directly: the unit is a function of the table, not a
    constant. A hardcoded unit passes exactly one of these cases."""
    fixture = (
        "brenda_ache_kcat_fixture.html"
        if table_label == bc.TURNOVER_TABLE_LABEL
        else "brenda_ldh_ki_fixture.html"
    )
    substrate = (
        "acetyl thiocholine"
        if table_label == bc.TURNOVER_TABLE_LABEL
        else "pyruvate"
    )
    entries = bc.parse_brenda_km_html(
        _fixture(fixture), substrate, "Homo sapiens", table_label=table_label
    )
    assert entries
    assert {e.unit for e in entries} == {expected_unit}
