"""Tests for selection_tie.py.

The corpus-level test at the end is the one that matters: it runs the real
frontier over a real fixture and asserts a tie is found where one exists.
Hand-built rows can pass while the module is useless on the actual pool --
that failure has now happened twice in this repository (ADR 0032, ADR 0038).
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import evidence_rank
from selection_tie import find_tie


class Row:
    """Minimal stand-in for BRENDAKmEntry. Only the attributes the module
    reads are present, so a test cannot pass by accident on a field the
    module does not actually use."""

    def __init__(self, value, *, ph=7.4, temp=37.0, organism="Homo sapiens",
                 ref="740253", conditions="pH 7.4, 37°C", unit="mM"):
        self.km_value = value
        self.assay_ph = ph
        self.assay_temperature_c = temp
        self.organism = organism
        self.reference_id = ref
        self.conditions = conditions
        self.unit = unit
        self.variant = None


# ---------------------------------------------------------------------------
# When there is nothing to report
# ---------------------------------------------------------------------------

def test_a_single_row_is_not_a_tie():
    """The evidence did choose: there was one candidate."""
    row = Row(2.5)
    assert find_tie([row], row) is None


def test_identical_values_are_not_a_tie():
    """Two equally-evidenced rows reporting the same number.

    The evidence did not choose, and nothing turned on the choice. Reporting
    this would be noise, and noise is what gets a real finding skipped.
    """
    a, b = Row(2.5), Row(2.5)
    assert find_tie([a, b], a) is None


def test_an_empty_or_none_frontier_is_not_a_tie():
    assert find_tie([], None) is None
    assert find_tie(None, None) is None


# ---------------------------------------------------------------------------
# The case this exists for
# ---------------------------------------------------------------------------

def test_two_equally_evidenced_rows_with_different_values_are_a_tie():
    low, high = Row(0.03, ref="A"), Row(0.045, ref="B")
    tie = find_tie([low, high], low)
    assert tie is not None
    assert tie.is_tied
    assert len(tie.candidates) == 2


def test_the_tie_names_the_row_that_was_returned():
    # Without this a reader cannot tell which of the listed alternatives
    # they are actually looking at.
    low, high = Row(0.03, ref="A"), Row(0.045, ref="B")
    tie = find_tie([low, high], low)
    selected = [c for c in tie.candidates if c.selected]
    assert len(selected) == 1
    assert selected[0].value == 0.03


def test_the_tie_carries_the_reference_of_each_alternative():
    """A named alternative is checkable; a bare number is not."""
    tie = find_tie([Row(0.03, ref="A"), Row(0.045, ref="B")], None)
    assert {c.reference_id for c in tie.candidates} == {"A", "B"}


def test_the_tie_carries_each_row_s_commentary():
    # This is what a reader needs to make the judgement the ranking
    # declined to make.
    a = Row(0.03, conditions="pH 7.4, 37°C, native enzyme")
    b = Row(0.045, conditions="pH 7.4, 37°C, recombinant enzyme")
    tie = find_tie([a, b], a)
    got = {c.conditions for c in tie.candidates}
    assert "pH 7.4, 37°C, native enzyme" in got
    assert "pH 7.4, 37°C, recombinant enzyme" in got


def test_the_spread_is_reported_as_a_range_and_a_fold():
    tie = find_tie([Row(0.03), Row(0.045)], None)
    assert tie.low == 0.03
    assert tie.high == 0.045
    assert tie.fold_range == pytest.approx(1.5)
    assert "0.03 to 0.045" in tie.reason
    assert "1.5-fold" in tie.reason


def test_the_reason_says_the_tie_break_is_unjustified():
    """The whole point. A reader must not read the returned number as the
    one the evidence selected."""
    tie = find_tie([Row(0.03), Row(0.045)], None)
    assert "the evidence does not justify" in tie.reason


def test_the_reason_calls_the_spread_disagreement_not_uncertainty():
    # These are different claims. Literature disagreement is not a
    # measurement error bar, and presenting it as one would be the kind of
    # confident wrong framing this project treats as a defect.
    tie = find_tie([Row(0.03), Row(0.045)], None)
    assert "disagreement in the literature" in tie.reason
    assert "not a measurement uncertainty" in tie.reason


# ---------------------------------------------------------------------------
# States never collapse into a false "the evidence chose"
# ---------------------------------------------------------------------------

def test_is_tied_is_a_positive_test():
    """`SelectionTie()` empty must never read as "the evidence chose
    cleanly" -- it is also what an unpopulated field looks like."""
    from selection_tie import SelectionTie

    assert SelectionTie().is_tied is False
    assert SelectionTie(candidates=[]).is_tied is False


def test_a_zero_value_does_not_crash_or_report_infinity():
    """A zero constant is a data problem for another check. This one must
    not crash on it, and must not report an infinite fold-range as though
    it were a measurement."""
    tie = find_tie([Row(0.0), Row(0.045)], None)
    assert tie is not None
    assert tie.fold_range is None
    assert "fold" not in tie.reason


# ---------------------------------------------------------------------------
# Corpus level: the real frontier over a real fixture
# ---------------------------------------------------------------------------

def test_a_real_tie_exists_in_the_real_ldh_pool():
    """Hand-built rows can pass while the module is useless on the actual
    pool. This runs `evidence_rank.frontier` over parsed BRENDA rows.

    Asserted as "a tie is findable somewhere in the corpus" rather than
    against one enzyme's exact numbers, so a BRENDA update changes the
    figures without silently turning the test vacuous -- the assertion that
    would go quiet is `assert examined`, and it is explicit.
    """
    from brenda_client import (
        parse_brenda_km_html,
        KM_TABLE_LABEL,
        TURNOVER_TABLE_LABEL,
    )

    fixtures = pathlib.Path(__file__).parent / "fixtures"
    examined = 0
    ties = 0
    for name, label in [
        ("brenda_ldh_fixture.html", KM_TABLE_LABEL),
        ("brenda_ldh_kcat_fixture.html", TURNOVER_TABLE_LABEL),
        ("brenda_ache_fixture.html", KM_TABLE_LABEL),
        ("brenda_ache_kcat_fixture.html", TURNOVER_TABLE_LABEL),
    ]:
        path = fixtures / name
        if not path.exists():
            continue
        rows = parse_brenda_km_html(
            path.read_text(errors="replace"), "1.1.1.27", [],
            target_organism=None, require_substrate_match=False,
            table_label=label,
        )
        if len(rows) < 2:
            continue
        examined += 1
        kept = evidence_rank.frontier(rows)
        selected = min(kept, key=lambda e: e.km_value)
        if find_tie(kept, selected) is not None:
            ties += 1

    assert examined, "no fixture parsed to a comparable pool; test was vacuous"
    assert ties, (
        "no tie found anywhere in the corpus. Either every pool is resolved "
        "by the three axes -- which would be surprising and worth verifying "
        "by hand -- or find_tie is not seeing what frontier returns."
    )
