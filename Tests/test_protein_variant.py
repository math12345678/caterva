"""Tests for protein_variant.py.

Every commentary string below is REAL — taken from the distinct commentaries
in `fixtures/brenda_ache_kcat_fixture.html` and `brenda_ldh_fixture.html`.
The classifier is designed against the corpus rather than against imagined
inputs, so the tests are the corpus.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

from protein_variant import classify

sys.path.insert(0, str(pathlib.Path(__file__).parent))


# ---------------------------------------------------------------------------
# Real commentaries, real verdicts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "commentary",
    [
        "Y124C mutant",
        "A262C mutant",
        "E81C mutant",
        "F295A/Y337A mutant, pH 7, 22°C",
        "F295L/Y337A mutant, pH 7, 22°C",
        "F297I/Y337A mutant, pH 7, 22°C",
        "Y337A/E202Q/F295A mutant, pH 7, 22°C",
        "Y337A/F295A/F297A mutant, pH 7, 22°C",
        "H287C mutant",
        "E84C mutant",
        # The word comes AFTER the code here, and BEFORE it in the next case.
        "pH 7.0, 25°C, mutant G122H/Y124Q/S125T",
        "Y124C-benzyl mutant",
        "Y124C-SO3- mutant",
    ],
)
def test_real_mutant_commentaries_are_variants(commentary):
    verdict = classify(commentary)
    assert verdict.status == "variant"
    assert verdict.kind == "mutant"
    assert not verdict.is_wild_type
    # A verdict with no evidence is an assertion. The reader must be able to
    # check the classifier rather than trust it.
    assert verdict.evidence


@pytest.mark.parametrize(
    "commentary",
    ["pH 8.0, 30°C, native enzyme", "wild-type", "wild-type enzyme"],
)
def test_real_wild_type_commentaries(commentary):
    verdict = classify(commentary)
    assert verdict.status == "wild_type"
    assert verdict.is_wild_type
    assert verdict.evidence


@pytest.mark.parametrize(
    "commentary",
    [
        "pH and temperature not specified in the publication",
        "in 0.5 M Tris-HCl buffer, pH 8.0, temperature not specified in the publication",
        "25°C",
        "25°C, pH not specified in the publication",
        "at pH 7.4 and 37°C",
        "pH 8, 27°C, attachment of polyethylene glycol side chains to lysine "
        "residues does not alter the Kcat value",
    ],
)
def test_commentaries_that_say_nothing_are_unstated(commentary):
    verdict = classify(commentary)
    assert verdict.status == "unstated"
    assert not verdict.is_wild_type


def test_the_ldh_isozyme_row_is_a_variant():
    # "pH 8.5, 25°C, isozyme H4" is the row the LDH resolver currently
    # selects. H4 and M4 have genuinely different kinetics, and a request
    # for "lactate dehydrogenase" did not ask for one of them.
    verdict = classify("pH 8.5, 25°C, isozyme H4")
    assert verdict.status == "variant"
    assert verdict.kind == "isozyme"
    assert "isozyme H4" in (verdict.evidence or "")


# ---------------------------------------------------------------------------
# The distinctions that are easy to get wrong
# ---------------------------------------------------------------------------

def test_unstated_is_not_wild_type():
    """The single most important assertion in this file.

    `unstated` is the majority case. If it certified rows as wild-type,
    every unlabelled mutant in BRENDA would re-enter through the gap, and
    the check would report success while doing nothing.
    """
    verdict = classify("25°C")
    assert verdict.status == "unstated"
    assert verdict.is_wild_type is False
    assert "NOT a finding" in verdict.reason


def test_is_wild_type_is_a_positive_test():
    for status in ("unstated", "absent", "variant"):
        verdict = classify("wild-type enzyme")
        verdict.status = status
        assert verdict.is_wild_type is False, f"{status} must not certify wild-type"


def test_a_mutation_code_beats_the_word_wild_type():
    # BRENDA writes both in one cell. The row is a mutant.
    verdict = classify("Y124C mutant of the wild-type enzyme")
    assert verdict.status == "variant"


def test_recombinant_is_reported_but_is_not_a_variant():
    """A recombinant wild-type is the same sequence in a different host.

    Treating it as a variant would withhold a large and legitimate part of
    the corpus -- 28 rows in the fixtures. It is recorded so a reader can
    weigh glycosylation and folding differences themselves.
    """
    verdict = classify("recombinant enzyme, pH 7.4, 37°C")
    assert verdict.status == "unstated"
    assert verdict.recombinant is True


def test_recombinant_wild_type_is_wild_type_and_flagged_recombinant():
    verdict = classify("recombinant wild-type enzyme, pH 8.0, 22°C")
    assert verdict.status == "wild_type"
    assert verdict.recombinant is True


def test_no_commentary_is_absent_not_unstated():
    # "BRENDA reported no commentary" and "the commentary did not say" are
    # different facts about the source, and only one of them means a curator
    # wrote something.
    for empty in (None, "", "   "):
        assert classify(empty).status == "absent"


# ---------------------------------------------------------------------------
# The point-mutation regex, where false positives would live
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "commentary",
    [
        "isozyme H4",          # 1 digit, no trailing residue
        "pH 7.0, 25°C",        # digits everywhere, no substitution
        "in 0.5 M Tris-HCl buffer",
        "vitamin B12 supplementation",  # B and 12, but B is not a residue code
        "assay at 37°C for 10 min",
    ],
)
def test_point_mutation_regex_does_not_fire_on_ordinary_text(commentary):
    assert classify(commentary).kind != "mutant"


@pytest.mark.parametrize("code", ["Y337A", "G122H", "A262C", "E81C", "S125T"])
def test_point_mutation_regex_fires_on_real_codes(code):
    verdict = classify(f"{code}, pH 7, 22°C")
    assert verdict.status == "variant"
    assert verdict.evidence == code


def test_non_residue_letters_are_rejected():
    # X and B are not proteinogenic one-letter codes. Without the residue
    # alphabet this regex would match arbitrary capitalised tokens.
    assert classify("X99Y treatment").kind != "mutant"
    assert classify("B12 cofactor").kind != "mutant"


# ---------------------------------------------------------------------------
# Corpus-level: the classifier must actually see the fixture's mutants
# ---------------------------------------------------------------------------

def test_classifier_finds_the_mutants_in_the_real_fixture():
    """A unit test on hand-picked strings can pass while the classifier is
    useless on the real table. This asserts against the parsed fixture.

    The numbers are the ones that motivated the module: 72 rows, 35 mutants.
    If a BRENDA update changes them the test should be re-verified, not
    loosened -- the point is that the proportion is large.
    """
    from brenda_client import parse_brenda_km_html, TURNOVER_TABLE_LABEL

    html = pathlib.Path(__file__).parent.joinpath(
        "fixtures", "brenda_ache_kcat_fixture.html"
    ).read_text(errors="replace")
    rows = parse_brenda_km_html(
        html, "3.1.1.7", [], target_organism=None,
        require_substrate_match=False, table_label=TURNOVER_TABLE_LABEL,
    )
    assert rows, "fixture parsed to nothing; this test would pass vacuously"

    verdicts = [classify(r.conditions) for r in rows]
    variants = [v for v in verdicts if v.status == "variant"]
    wild = [v for v in verdicts if v.status == "wild_type"]

    assert len(variants) >= 30, (
        f"only {len(variants)} of {len(rows)} rows classified as variants; "
        "the classifier is not seeing the mutants it was built for"
    )
    assert wild, "no wild-type rows found; the classifier is over-matching"
    # And the thing that makes this dangerous: the variants are cheaper.
    variant_rows = [r for r, v in zip(rows, verdicts) if v.status == "variant"]
    wild_rows = [r for r, v in zip(rows, verdicts) if v.status == "wild_type"]
    assert min(r.km_value for r in variant_rows) < min(r.km_value for r in wild_rows), (
        "the fixture no longer demonstrates that min() selection reaches "
        "into the mutant tail; re-verify before relaxing this"
    )


def test_a_double_mutant_written_without_a_separator_is_caught():
    """BRENDA writes "D38SC81S" -- two substitutions, no slash.

    The single-code regex missed it: `\\b` requires a boundary between the
    S of D38S and the C of C81S, and there is none. The row said it was a
    double mutant and was classified `unstated`.

    The mutation-testing pass on this module did not find it, and that is
    the lesson worth keeping: every mutation asked whether the regex could
    be BROKEN. None asked what it had never matched. Mutation testing
    proves a check can fail; it says nothing about a case the check never
    sees.

    Found by scripts/check_commentary_coverage.py.
    """
    verdict = classify("D38S/C81S mutant, activated by D-fructose 1,6-diphosphate")
    assert verdict.status == "variant"

    concatenated = classify("D38SC81S, activated by D-fructose 1,6-diphosphate")
    assert concatenated.status == "variant"
    assert concatenated.kind == "mutant"
    assert concatenated.evidence == "D38SC81S"


def test_widening_the_regex_did_not_widen_the_false_positives():
    # The `+` must not turn ordinary text into mutations.
    for benign in ["isozyme H4", "vitamin B12", "X99Y", "LDH B", "hexokinase Ia"]:
        assert classify(benign).kind != "mutant", benign
