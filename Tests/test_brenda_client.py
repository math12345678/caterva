"""
pytest suite for brenda_client.py

Runs entirely offline against saved fixture HTML in Tests/fixtures/ - no
network access needed. This is deliberate: the original AChE bug (substrate
string "acetylthiocholine" vs BRENDA's actual "acetyl thiocholine") was
invisible until someone happened to run the scraper and notice 0 results.
These tests pin down the exact scenarios that caused that bug and others
found during review, so a future edit to substrate handling or parsing
logic can't silently reintroduce them.

brenda_client.py no longer hardcodes any per-enzyme data (no
ENZYME_REGISTRY) - substrate names and UniProt fallbacks are resolved
dynamically via enzyme_lookup.py (KEGG + UniProt APIs) in production use.
These tests pass explicit substrate lists directly to parse_brenda_km_html,
which is exactly how any caller (including the dynamic resolver) uses it -
this is normal test input, not a hidden hardcoded registry.

Run with:  pytest test_brenda_client.py -v
"""

import os

import pytest

from brenda_client import (
    KM_PLAUSIBLE_MAX_MM,
    KM_PLAUSIBLE_MIN_MM,
    parse_brenda_km_html,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Real substrate spellings for the fixtures below, as resolved from live
# BRENDA output earlier in this project. In production these come from
# enzyme_lookup.parse_kegg_substrates(); here they're passed explicitly
# since these tests exercise parse_brenda_km_html in isolation.
LDH_SUBSTRATES = ["lactate", "L-lactate", "pyruvate", "NADH", "NAD+", "NAD"]
# Real substrate strings, confirmed live 2026-07 via
# brenda_ache_realrows_debug.py. "propionylthiocholine" was dropped from
# this list - the earlier version included it but no real captured row
# for it turned up in this session's live capture (unlike the other
# four, each backed by an actual captured row below).
ACHE_SUBSTRATES = [
    "acetylcholine", "acetylthiocholine", "acetyl thiocholine",
    "2,6-dichlorophenolindophenol",
]
ACHE_UNIPROT = "P22303"  # real accession, confirmed live on the 2,6-dichlorophenolindophenol row


def load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def ldh_html():
    return load_fixture("brenda_ldh_fixture.html")


@pytest.fixture
def ache_html():
    return load_fixture("brenda_ache_fixture.html")


# ---------------------------------------------------------------------------
# LDH: baseline correctness
# ---------------------------------------------------------------------------

def test_ldh_returns_only_human_rows_with_real_substrates(ldh_html):
    entries = parse_brenda_km_html(ldh_html, "1.1.1.27", LDH_SUBSTRATES)
    # 6 real human rows captured live (2 x (S)-lactate, 2 x NAD+, 2 x
    # pyruvate); the non-human row, no-substrate row, and malformed row
    # must all be excluded.
    assert len(entries) == 6
    assert all(e.organism == "Homo sapiens" for e in entries)


def test_ldh_excludes_non_human_organism(ldh_html):
    entries = parse_brenda_km_html(ldh_html, "1.1.1.27", LDH_SUBSTRATES)
    km_values = [e.km_value for e in entries]
    assert 0.0026 not in km_values  # the Sus scrofa (S)-lactate row


def test_ldh_excludes_rows_without_a_matched_substrate(ldh_html):
    entries = parse_brenda_km_html(ldh_html, "1.1.1.27", LDH_SUBSTRATES)
    km_values = [e.km_value for e in entries]
    assert 0.045 not in km_values  # oxamate inhibition row, no real substrate


def test_ldh_uniprot_extracted_per_row(ldh_html):
    """The lactate/NAD+ rows carry a real per-row accession (P07864); the
    pyruvate rows carry '-' in that cell (confirmed live) and so have no
    uniprot without a fallback - this locks in both, rather than assuming
    every row has the same accession."""
    entries = parse_brenda_km_html(ldh_html, "1.1.1.27", LDH_SUBSTRATES)
    # Substrate label is the matched target string, not necessarily the
    # fixture's verbatim cell text - "lactate" is a substring of the real
    # cell text "(S)-lactate" and is what LDH_SUBSTRATES lists, so matched
    # entries are labeled "lactate" here (confirmed by the failing
    # assertion this replaced, which expected the verbatim cell text).
    with_accession = [e for e in entries if e.substrate in ("lactate", "NAD+")]
    without_accession = [e for e in entries if e.substrate == "pyruvate"]
    assert len(with_accession) == 4
    assert len(without_accession) == 2
    assert all(e.uniprot == "P07864" for e in with_accession)
    assert all(e.uniprot is None for e in without_accession)


def test_ldh_no_entries_flagged(ldh_html):
    entries = parse_brenda_km_html(ldh_html, "1.1.1.27", LDH_SUBSTRATES)
    assert all(not e.flagged for e in entries)


def test_ldh_pyruvate_rows_use_fallback_uniprot(ldh_html):
    """Unlike the lactate/NAD+ rows (which carry their own accession),
    the real pyruvate rows have no per-row UniProt cell - this is the one
    case in this fixture where fallback_uniprot actually matters."""
    entries = parse_brenda_km_html(
        ldh_html, "1.1.1.27", LDH_SUBSTRATES, fallback_uniprot="P00338"
    )
    pyruvate_rows = [e for e in entries if e.substrate == "pyruvate"]
    assert len(pyruvate_rows) == 2
    assert all(e.uniprot == "P00338" for e in pyruvate_rows)


# ---------------------------------------------------------------------------
# AChE: the regression this whole suite exists to prevent
# ---------------------------------------------------------------------------

def test_ache_matches_spaced_substrate_name(ache_html):
    """This is the exact bug: BRENDA renders 'acetyl thiocholine' with a
    space. If the substrate list only contains the concatenated
    'acetylthiocholine', these rows silently vanish. Must not regress."""
    entries = parse_brenda_km_html(ache_html, "3.1.1.7", ACHE_SUBSTRATES)
    substrates = [e.substrate for e in entries]
    assert "acetylthiocholine" in substrates or "acetyl thiocholine" in substrates
    assert len(entries) >= 1


def test_ache_does_not_return_zero_results(ache_html):
    entries = parse_brenda_km_html(ache_html, "3.1.1.7", ACHE_SUBSTRATES)
    assert len(entries) > 0, (
        "Regression: AChE parser returned 0 results. This is the exact "
        "failure mode caused by substrate string mismatches."
    )


def test_ache_finds_genuine_low_km_row(ache_html):
    entries = parse_brenda_km_html(ache_html, "3.1.1.7", ACHE_SUBSTRATES)
    km_values = [e.km_value for e in entries]
    assert 0.09 in km_values


# Synthetic HTML fragment, explicitly NOT claimed as real BRENDA data.
# brenda_ache_fixture.html previously carried a "km=6500, mentions Kcat"
# row that an earlier part of this project claimed reproduced a real
# BRENDA shape; a targeted live re-check this session
# (brenda_ache_edgecases_debug.py) found zero live rows matching that
# shape, so it was removed from the real-data fixture rather than kept
# there unconfirmed. The underlying code path (flagging an implausibly
# large Km / a row whose conditions text mentions "Kcat") is still real
# production logic in brenda_client.py and still needs a test - this
# small hand-built HTML snippet exercises it directly without pretending
# to be captured BRENDA content.
_SYNTHETIC_IMPLAUSIBLE_KCAT_HTML = """
<html><body>
<a href="javascript:showTable('tab1')">KM Values</a>
<div id="tab1">
<div class="row">
  <div class="cell">6500</div>
  <div class="cell">acetyl thiocholine</div>
  <div class="cell">Homo sapiens</div>
  <div class="cell">-</div>
  <div class="cell">synthetic test row: conditions text mentions Kcat, not Km</div>
  <div class="cell">000001</div>
</div>
</div>
</body></html>
"""


def test_ache_flags_implausible_kcat_row():
    entries = parse_brenda_km_html(
        _SYNTHETIC_IMPLAUSIBLE_KCAT_HTML, "3.1.1.7", ACHE_SUBSTRATES
    )
    bad_row = next(e for e in entries if e.km_value == 6500.0)
    assert bad_row.flagged is True
    assert "Kcat" in bad_row.flag_reason or "outside plausible range" in bad_row.flag_reason


def test_ache_does_not_flag_genuine_low_km_row(ache_html):
    entries = parse_brenda_km_html(ache_html, "3.1.1.7", ACHE_SUBSTRATES)
    good_row = next(e for e in entries if e.km_value == 0.09)
    assert good_row.flagged is False


def test_ache_excludes_non_human_organism(ache_html):
    entries = parse_brenda_km_html(ache_html, "3.1.1.7", ACHE_SUBSTRATES)
    assert all(e.organism == "Homo sapiens" for e in entries)
    # real Macroptilium atropurpureum row (km=0.08, "acetylcholine
    # chloride") must not leak through
    assert all(e.km_value != 0.08 for e in entries)


def test_ache_uniprot_fallback_applied_when_row_has_no_accession(ache_html):
    entries = parse_brenda_km_html(
        ache_html, "3.1.1.7", ACHE_SUBSTRATES, fallback_uniprot=ACHE_UNIPROT
    )
    row_without_accession = next(e for e in entries if e.km_value == 0.09)
    assert row_without_accession.uniprot == "P22303"


def test_ache_uniprot_is_none_without_fallback_when_row_has_no_accession(ache_html):
    """No fallback supplied -> no guessed UniProt. Must not silently
    fabricate an accession for a row that doesn't have one."""
    entries = parse_brenda_km_html(ache_html, "3.1.1.7", ACHE_SUBSTRATES)
    row_without_accession = next(e for e in entries if e.km_value == 0.09)
    assert row_without_accession.uniprot is None


def test_ache_uniprot_extracted_directly_when_present(ache_html):
    entries = parse_brenda_km_html(ache_html, "3.1.1.7", ACHE_SUBSTRATES)
    row_with_accession = next(e for e in entries if e.km_value == 0.038)
    assert row_with_accession.uniprot == "P22303"


# ---------------------------------------------------------------------------
# General config sanity (no more registry to check - just the generic
# heuristics that remain in this module)
# ---------------------------------------------------------------------------

def test_km_plausible_range_is_sane():
    assert KM_PLAUSIBLE_MIN_MM > 0
    assert KM_PLAUSIBLE_MAX_MM > KM_PLAUSIBLE_MIN_MM


def test_parse_requires_explicit_substrate_list(ldh_html):
    """target_substrates has no default - parse_brenda_km_html must not
    silently fall back to any built-in list. Calling without it is a
    TypeError, which is the point: there is no hidden default to regress."""
    with pytest.raises(TypeError):
        parse_brenda_km_html(ldh_html, "1.1.1.27")


# ---------------------------------------------------------------------------
# Cross-species mode (target_organism=None)
# ---------------------------------------------------------------------------

def test_cross_species_mode_includes_non_human_rows(ldh_html):
    entries = parse_brenda_km_html(
        ldh_html, "1.1.1.27", LDH_SUBSTRATES, target_organism=None
    )
    organisms = {e.organism for e in entries}
    assert "Sus scrofa" in organisms  # real (S)-lactate row, ref 740001
    assert "Homo sapiens" in organisms


def test_cross_species_mode_labels_organism_correctly(ache_html):
    entries = parse_brenda_km_html(
        ache_html, "3.1.1.7", ACHE_SUBSTRATES, target_organism=None
    )
    non_human_row = next(e for e in entries if e.km_value == 0.08)
    assert non_human_row.organism == "Macroptilium atropurpureum"


def test_default_organism_mode_still_excludes_non_human(ldh_html):
    entries = parse_brenda_km_html(ldh_html, "1.1.1.27", LDH_SUBSTRATES)
    assert all(e.organism == "Homo sapiens" for e in entries)


# ---------------------------------------------------------------------------
# Permissive mode (require_substrate_match=False): the unfiltered fallback
# used when neither the strict substrate list nor its PubChem-expanded
# version matches anything (broad-specificity enzymes, assay-surrogate
# substrates - see brenda_client.fetch_and_parse_brenda_km).
# ---------------------------------------------------------------------------

def test_strict_mode_returns_nothing_for_substrate_not_in_list(ldh_html):
    """Baseline: with a substrate list that matches nothing in the
    fixture, strict mode returns zero rows."""
    entries = parse_brenda_km_html(ldh_html, "1.1.1.27", ["some-unrelated-compound"])
    assert entries == []


def test_permissive_mode_returns_rows_when_strict_match_fails(ldh_html):
    entries = parse_brenda_km_html(
        ldh_html, "1.1.1.27", ["some-unrelated-compound"],
        require_substrate_match=False,
    )
    assert len(entries) > 0


def test_permissive_mode_marks_entries_unverified(ldh_html):
    entries = parse_brenda_km_html(
        ldh_html, "1.1.1.27", ["some-unrelated-compound"],
        require_substrate_match=False,
    )
    assert all(e.substrate_verified is False for e in entries)


def test_permissive_mode_still_marks_real_matches_verified(ldh_html):
    """Permissive mode only affects rows that didn't match anything via
    the substrate list - rows that DO match (the 6 real human LDH rows)
    must still come back verified=True, not get swept into "unverified"
    just because permissive mode is on. The fixture's disclosed
    'oxamate' edge-case row has no real substrate name, which strict mode
    excludes entirely but permissive mode includes as unverified - that
    row is expected here, and expected to be the only unverified one."""
    entries = parse_brenda_km_html(
        ldh_html, "1.1.1.27", LDH_SUBSTRATES,
        require_substrate_match=False,
    )
    verified = [e for e in entries if e.substrate_verified]
    unverified = [e for e in entries if not e.substrate_verified]
    assert len(verified) == 6
    assert all(
        e.km_value in (10.73, 21.78, 0.5, 0.99, 0.03, 0.398) for e in verified
    )
    assert len(unverified) == 1
    assert unverified[0].km_value == 0.045  # the disclosed oxamate edge case


def test_strict_mode_entries_are_always_verified(ldh_html):
    entries = parse_brenda_km_html(ldh_html, "1.1.1.27", LDH_SUBSTRATES)
    assert all(e.substrate_verified is True for e in entries)


# Synthetic HTML fragment, explicitly NOT claimed as real BRENDA data.
# brenda_ache_fixture.html previously carried a "km=0.0146, organism in
# the compound-name slot, no separate substrate cell" row that an earlier
# part of this project claimed reproduced a real BRENDA shape; a targeted
# live re-check this session (brenda_ache_edgecases_debug.py, searching
# for exactly this 5-cell/organism-in-position shape across all ~409
# human+non-human rows) found zero live matches, so it was removed from
# the real-data fixture rather than kept there unconfirmed. The
# underlying code path (permissive-mode fallback labeling must skip
# organism-shaped cells rather than mislabeling a row substrate='Homo
# sapiens') is still real production logic in brenda_client.py and still
# needs a test - this hand-built HTML snippet exercises it directly
# without pretending to be captured BRENDA content.
_SYNTHETIC_ORGANISM_IN_COMPOUND_POSITION_HTML = """
<html><body>
<a href="javascript:showTable('tab1')">KM Values</a>
<div id="tab1">
<div class="row">
  <div class="cell">0.0146</div>
  <div class="cell">Homo sapiens</div>
  <div class="cell">-</div>
  <div class="cell">synthetic test row: no substrate cell, organism sits where compound name usually does</div>
  <div class="cell">000002</div>
</div>
</div>
</body></html>
"""


def test_permissive_mode_does_not_mislabel_organism_as_substrate():
    """Regression guard for a code path (not a claim about real BRENDA
    data - see the synthetic-HTML comment above): if a row has no real
    substrate cell and the organism name sits where the compound name
    usually would, permissive mode's fallback label picker must skip
    organism-looking cells rather than labeling the row
    substrate='Homo sapiens', which would be meaningless."""
    entries = parse_brenda_km_html(
        _SYNTHETIC_ORGANISM_IN_COMPOUND_POSITION_HTML, "3.1.1.7",
        ["some-unrelated-compound"],
        require_substrate_match=False,
    )
    hemolysate_row = next(e for e in entries if e.km_value == 0.0146)
    assert hemolysate_row.substrate != "Homo sapiens"
    assert hemolysate_row.substrate_verified is False
