"""
pytest suite for hexokinase (2.7.1.1), trypsin (3.4.21.4), and
chymotrypsin (3.4.21.1). These three enzymes originally lived in a
hardcoded ENZYME_REGISTRY that has since been removed - substrate names
and UniProt accessions are now resolved dynamically per EC number via
enzyme_lookup.py (KEGG + UniProt APIs) in production use.

These tests exercise parse_brenda_km_html directly with explicit
substrate lists and fallback UniProt values, exactly the shape any
caller (including the dynamic resolver in fetch_and_parse_brenda_km)
passes in. This is normal test input, not a hidden hardcoded registry.
"""

import os

import pytest

from brenda_client import parse_brenda_km_html

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Real substrate spellings, as previously verified against live BRENDA
# (trypsin) or built from documented BRENDA formatting conventions
# (hexokinase, chymotrypsin). In production these come from
# enzyme_lookup.parse_kegg_substrates(); passed explicitly here since
# these tests exercise the pure parser in isolation.
#
# Real substrate strings, confirmed live 2026-07 via
# brenda_hexokinase_realrows_debug.py - a prior version of this list used
# "D-glucose"/"glucose"/"fructose"/"mannose", none of which are the real
# substrate strings BRENDA actually renders for this enzyme (same class
# of error already caught and fixed for trypsin/chymotrypsin). No real
# ordering conflict exists between "2-deoxy-D-glucose" and "ATP", but the
# longer/more specific name is still listed first as a defensive habit.
HEXOKINASE_SUBSTRATES = ["2-deoxy-D-glucose", "ATP"]
# fallback_uniprot is exercised with a hand-supplied value since every
# real row in this fixture carries "-" in the UniProt cell (confirmed
# live) - there's no real accession captured for hexokinase this session,
# so this value is NOT claimed to be verified live, only used to test the
# fallback mechanism itself.
HEXOKINASE_UNIPROT = "P19367"

TRYPSIN_SUBSTRATES = [
    "benzoyl-DL-Arg-7-amido-4-methylcoumarin",
    "benzoyl-DL-Arg-p-nitroanilide",
    "Glu-Gly-Arg-4-nitroanilide",
    "tert-butoxycarbonyl-L-Gln-L-Ala-L-Arg-7-amido-4-methylcoumarin",
    "enhanced green fluorescent protein-T1",
]
TRYPSIN_UNIPROT = "P07477"

CHYMOTRYPSIN_SUBSTRATES = [
    # Real substrate strings, confirmed live 2026-07 via
    # brenda_chymotrypsin_debug.py - a prior version of this list used
    # "ATEE"/"BTEE" textbook acronyms, which never appear in real BRENDA
    # text (same class of error already caught and fixed for trypsin's
    # BAPNA/TAME earlier this session).
    #
    # Order matters: "L-alanyl-L-alanyl-L-prolyl-L-phenylalanine
    # p-nitroanilide" is a literal substring of "N-succinyl-L-alanyl-
    # L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide" (they are
    # genuinely different molecules - one succinylated, one not).
    # parse_brenda_km_html matches substrings in list order and stops at
    # the first hit, so the longer/more specific name must be checked
    # first, or every succinylated-substrate row gets mislabeled with the
    # shorter name. Caught by test_chymotrypsin_matches_real_substrates
    # failing when this was in the wrong order - same class of bug as the
    # earlier "glucose before D-glucose" hexokinase ordering issue.
    "N-succinyl-L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide",
    "L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide",
]
# Real multi-accession UniProt cell confirmed live (isozyme-sharing row,
# same pattern as LDH's) - not a single guessed accession.
CHYMOTRYPSIN_UNIPROT = "Q6GPI1,P17538"


def load_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Hexokinase (EC 2.7.1.1)
# ---------------------------------------------------------------------------

@pytest.fixture
def hexokinase_html():
    return load_fixture("brenda_hexokinase_fixture.html")


def test_hexokinase_matches_real_substrates(hexokinase_html):
    """Real substrate strings, confirmed live 2026-07 - replaces an
    earlier test built around 'D-glucose'/'glucose', neither of which
    BRENDA actually renders for this enzyme."""
    entries = parse_brenda_km_html(hexokinase_html, "2.7.1.1", HEXOKINASE_SUBSTRATES)
    substrates = {e.substrate for e in entries}
    assert "2-deoxy-D-glucose" in substrates
    assert "ATP" in substrates


def test_hexokinase_deoxyglucose_rows_carry_real_km_values(hexokinase_html):
    """Locks in the three real 2-deoxy-D-glucose rows (different
    isoforms/conditions, all ref 640230/640237) captured live."""
    entries = parse_brenda_km_html(hexokinase_html, "2.7.1.1", HEXOKINASE_SUBSTRATES)
    deoxyglucose_kms = sorted(
        e.km_value for e in entries if e.substrate == "2-deoxy-D-glucose"
    )
    assert deoxyglucose_kms == [0.5, 0.56, 0.77]


def test_hexokinase_atp_rows_carry_real_ultra_low_km_values(hexokinase_html):
    """Locks in the two real ultra-low ATP Km values (ref 721735),
    already cross-verified live via hexokinase_low_km_debug.py earlier
    this session as genuine (not a unit-conversion artifact)."""
    entries = parse_brenda_km_html(hexokinase_html, "2.7.1.1", HEXOKINASE_SUBSTRATES)
    atp_kms = sorted(e.km_value for e in entries if e.substrate == "ATP")
    assert atp_kms == [0.00000023, 0.00000046]


def test_hexokinase_excludes_non_human_row(hexokinase_html):
    """The real captured non-human row is Saccharomyces cerevisiae, not a
    yeast 'D-glucose' row as an earlier version of this fixture assumed -
    it uses a different substrate name ('1,5-anhydro-D-glucitol') that
    isn't even in HEXOKINASE_SUBSTRATES, so it wouldn't match regardless;
    this test locks in that every returned entry is still human."""
    entries = parse_brenda_km_html(hexokinase_html, "2.7.1.1", HEXOKINASE_SUBSTRATES)
    assert all(e.organism == "Homo sapiens" for e in entries)
    assert all(e.km_value != 20.0 for e in entries)  # the yeast row


def test_hexokinase_uniprot_fallback_applied(hexokinase_html):
    """Every real captured row has '-' in the UniProt cell, so the
    fallback path is the only way any of these rows get a UniProt value -
    this exercises that mechanism, not a claim that P19367 was itself
    re-verified live this session (see HEXOKINASE_UNIPROT comment)."""
    entries = parse_brenda_km_html(
        hexokinase_html, "2.7.1.1", HEXOKINASE_SUBSTRATES,
        fallback_uniprot=HEXOKINASE_UNIPROT,
    )
    atp_row = next(e for e in entries if e.substrate == "ATP")
    assert atp_row.uniprot == "P19367"  # no per-row cell, comes from fallback


def test_hexokinase_uniprot_is_none_without_fallback(hexokinase_html):
    entries = parse_brenda_km_html(hexokinase_html, "2.7.1.1", HEXOKINASE_SUBSTRATES)
    atp_row = next(e for e in entries if e.substrate == "ATP")
    assert atp_row.uniprot is None


def test_hexokinase_no_entries_flagged(hexokinase_html):
    """All 5 real human rows are genuine captured measurements - none of
    the earlier fixture's fabricated implausible-value rows (Km=15000)
    remain, so nothing should be flagged."""
    entries = parse_brenda_km_html(hexokinase_html, "2.7.1.1", HEXOKINASE_SUBSTRATES)
    assert len(entries) == 5
    assert all(not e.flagged for e in entries)


# ---------------------------------------------------------------------------
# Trypsin (EC 3.4.21.4)
# ---------------------------------------------------------------------------

@pytest.fixture
def trypsin_html():
    return load_fixture("brenda_trypsin_fixture.html")


def test_trypsin_matches_real_brenda_substrate_names(trypsin_html):
    """Regression guard: an earlier version of this substrate list used
    textbook acronyms (BAPNA, TAME, BAEE, casein) that do not appear
    anywhere on BRENDA's actual page - live BRENDA returned 0 results
    because of it, the same failure mode as the original AChE bug. These
    are the real strings, confirmed against a live BRENDA fetch."""
    entries = parse_brenda_km_html(trypsin_html, "3.4.21.4", TRYPSIN_SUBSTRATES)
    substrates = {e.substrate for e in entries}
    assert "benzoyl-DL-Arg-7-amido-4-methylcoumarin" in substrates
    assert "benzoyl-DL-Arg-p-nitroanilide" in substrates
    assert "Glu-Gly-Arg-4-nitroanilide" in substrates


def test_trypsin_does_not_return_zero_results(trypsin_html):
    entries = parse_brenda_km_html(trypsin_html, "3.4.21.4", TRYPSIN_SUBSTRATES)
    assert len(entries) > 0, (
        "Regression: trypsin parser returned 0 results, the exact failure "
        "mode caused by substrate string mismatches (BAPNA/TAME/BAEE never "
        "matched real BRENDA text)."
    )


def test_trypsin_excludes_inhibitors_and_non_substrate_rows(trypsin_html):
    """leupeptin (inhibitor) and fulvic acid (not a real trypsin substrate)
    must never be mistaken for genuine substrate rows."""
    entries = parse_brenda_km_html(trypsin_html, "3.4.21.4", TRYPSIN_SUBSTRATES)
    substrates = {e.substrate for e in entries}
    assert "leupeptin" not in substrates
    assert "fulvic acid" not in substrates


def test_trypsin_excludes_row_with_no_substrate_cell(trypsin_html):
    entries = parse_brenda_km_html(trypsin_html, "3.4.21.4", TRYPSIN_SUBSTRATES)
    km_values = [e.km_value for e in entries]
    assert 7.5 not in km_values


def test_trypsin_excludes_bovine_row(trypsin_html):
    entries = parse_brenda_km_html(trypsin_html, "3.4.21.4", TRYPSIN_SUBSTRATES)
    assert all(e.organism == "Homo sapiens" for e in entries)
    assert len(entries) == 4


def test_trypsin_egfp_reporter_row_typed_as_engineered(trypsin_html):
    entries = parse_brenda_km_html(trypsin_html, "3.4.21.4", TRYPSIN_SUBSTRATES)
    egfp_row = next(
        e for e in entries if e.substrate == "enhanced green fluorescent protein-T1"
    )
    assert egfp_row.substrate_type == "engineered_reporter"


def test_trypsin_uniprot_fallback_applied(trypsin_html):
    entries = parse_brenda_km_html(
        trypsin_html, "3.4.21.4", TRYPSIN_SUBSTRATES,
        fallback_uniprot=TRYPSIN_UNIPROT,
    )
    bz_arg_row = next(
        e for e in entries if e.substrate == "benzoyl-DL-Arg-p-nitroanilide"
    )
    assert bz_arg_row.uniprot == "P07477"


def test_trypsin_classic_substrates_are_typed_classic(trypsin_html):
    entries = parse_brenda_km_html(trypsin_html, "3.4.21.4", TRYPSIN_SUBSTRATES)
    classic_names = {
        "benzoyl-DL-Arg-7-amido-4-methylcoumarin",
        "benzoyl-DL-Arg-p-nitroanilide",
        "Glu-Gly-Arg-4-nitroanilide",
    }
    for e in entries:
        if e.substrate in classic_names:
            assert e.substrate_type == "classic"


def test_trypsin_no_entries_flagged(trypsin_html):
    entries = parse_brenda_km_html(trypsin_html, "3.4.21.4", TRYPSIN_SUBSTRATES)
    assert all(not e.flagged for e in entries)


# ---------------------------------------------------------------------------
# Chymotrypsin (EC 3.4.21.1)
# ---------------------------------------------------------------------------

@pytest.fixture
def chymotrypsin_html():
    return load_fixture("brenda_chymotrypsin_fixture.html")


def test_chymotrypsin_matches_real_substrates(chymotrypsin_html):
    """Real substrate strings, confirmed live 2026-07 - replaces an
    earlier test that asserted textbook acronyms ("ATEE"/"BTEE") which
    never appear in real BRENDA text."""
    entries = parse_brenda_km_html(
        chymotrypsin_html, "3.4.21.1", CHYMOTRYPSIN_SUBSTRATES
    )
    substrates = {e.substrate for e in entries}
    assert "L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide" in substrates
    assert "N-succinyl-L-alanyl-L-alanyl-L-prolyl-L-phenylalanine p-nitroanilide" in substrates


def test_chymotrypsin_excludes_bovine_row(chymotrypsin_html):
    entries = parse_brenda_km_html(
        chymotrypsin_html, "3.4.21.1", CHYMOTRYPSIN_SUBSTRATES
    )
    assert all(e.organism == "Homo sapiens" for e in entries)
    # 8 real human rows captured live (2 substrates x wild-type/D236R/
    # S242T/unlabeled conditions); the 1 real Bos taurus row must be
    # excluded.
    assert len(entries) == 8


def test_chymotrypsin_uniprot_present_on_every_real_row(chymotrypsin_html):
    """Every real captured human row carries its own multi-accession
    UniProt cell ("Q6GPI1,P17538") - there's no real row in this fixture
    that needs the fallback_uniprot path, so (unlike the LDH/AChE
    fixtures, which do exercise that path with real missing-accession
    rows) this just confirms the real per-row value is read correctly,
    kept whole, and not truncated to a single accession."""
    entries = parse_brenda_km_html(
        chymotrypsin_html, "3.4.21.1", CHYMOTRYPSIN_SUBSTRATES,
    )
    assert all(e.uniprot == "Q6GPI1,P17538" for e in entries)


def test_chymotrypsin_no_entries_flagged(chymotrypsin_html):
    entries = parse_brenda_km_html(
        chymotrypsin_html, "3.4.21.1", CHYMOTRYPSIN_SUBSTRATES
    )
    assert all(not e.flagged for e in entries)
