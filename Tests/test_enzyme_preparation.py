"""How the enzyme was prepared, and whether that reaches the reader.

The commentary-residue baseline marks covalent modification, affinity tags
and immobilisation as an OPEN FINDING. ADR 0029's variant filter cannot see
them — none is a sequence change — so 18 rows in the corpus were classified
`unstated` and were fully eligible for selection as ordinary enzyme.

Measured before this existed: `resolve_kinetic_value("1.1.1.27",
"Homo sapiens", "NADH", quantity="ki")` returned 0.00059, whose commentary
reads "competitive versus NADH, pH 7.5, 37 C, recombinant His-tagged
enzyme". Nothing in the result said so.
"""

from __future__ import annotations

import pytest

from enzyme_preparation import classify, describe
from fallback_logic import resolve_kinetic_value
from fixture_lineages import fixture_lineage_provider
from test_fallback_logic import (
    fake_taxon_id_provider,
    fake_uniprot_provider,
    load_fixture,
    make_html_provider,
)


# ---------------------------------------------------------------------------
# Reading the commentary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "commentary,expected",
    [
        ("competitive versus NADH, pH 7.5, 37°C, recombinant His-tagged enzyme", "tagged"),
        ("immobiized recombinant enzyme, pH 7.0, 25°C", "immobilised"),
        ("pH 8, 27°C, attachment of polyethylene glycol side chains to lysine residues", "modified"),
        ("Y124C-acrylodan mutant", "modified"),
        ("pH 8.0, 30°C, native enzyme", "native"),
        ("pH 8.5, 25°C, isozyme H4", "unstated"),
        ("", "absent"),
        (None, "absent"),
    ],
)
def test_the_corpus_commentaries_classify(commentary, expected) -> None:
    """Every string here is real BRENDA commentary from this repository's
    own fixtures, not an invented example."""
    assert classify(commentary).status == expected


def test_recombinant_alone_is_not_a_modification() -> None:
    """The distinction most likely to be got wrong, in either direction.

    Recombinant expression is how most enzyme is produced; the protein is
    the protein. Only the TAG changes it.

    Treating every `recombinant` row as modified would exclude most of the
    corpus and train a reader to skip the warning — ADR 0028's cry-wolf
    reasoning. Treating a His-tagged row as native is the defect this
    module exists for.
    """
    assert classify("recombinant enzyme, pH 7.4, 25°C").status == "unstated"
    assert classify("recombinant His-tagged enzyme").status == "tagged"


def test_immobilisation_wins_when_a_row_carries_two_markers() -> None:
    """Order is a decision, so it is asserted rather than left to the
    regexes' declaration order. Immobilisation dominates the kinetics it
    touches."""
    verdict = classify("immobilized His-tagged enzyme, pH 7")
    assert verdict.status == "immobilised"
    assert "immobilized" in (verdict.evidence or "").lower()


def test_the_evidence_names_the_words_that_decided_it() -> None:
    """A verdict nobody can check is a verdict nobody can argue with."""
    assert classify("recombinant His-tagged enzyme").evidence == "His-tagged"


# ---------------------------------------------------------------------------
# Three states, not two
# ---------------------------------------------------------------------------


def test_unstated_is_neither_native_nor_altered() -> None:
    """Not a contradiction — an admission. Neither question was answered,
    and `is_as_isolated` is a POSITIVE test for exactly this reason."""
    verdict = classify("pH 7.4, 25°C")
    assert verdict.status == "unstated"
    assert not verdict.is_as_isolated
    assert not verdict.differs_from_the_free_enzyme


def test_is_as_isolated_is_a_positive_test() -> None:
    """`status != "modified"` would call a tagged, immobilised, unstated or
    absent row 'as isolated'. Silence is not a clean bill of health."""
    for commentary in ("recombinant His-tagged enzyme", "immobilized enzyme",
                       "pH 7.4", "", None):
        assert not classify(commentary).is_as_isolated
    assert classify("pH 8.0, native enzyme").is_as_isolated


def test_describe_is_silent_for_unstated_and_absent() -> None:
    """A line reading "preparation not stated" on every row in the corpus is
    noise, and noise is how the lines that matter stop being read."""
    assert describe(classify("pH 7.4, 25°C")) is None
    assert describe(classify(None)) is None
    assert describe(classify("recombinant His-tagged enzyme")) is not None


# ---------------------------------------------------------------------------
# Does it reach the reader?
# ---------------------------------------------------------------------------


def _ldh_ki(substrate: str):
    return resolve_kinetic_value(
        "1.1.1.27",
        "Homo sapiens",
        substrate,
        html_provider=make_html_provider(
            {"1.1.1.27": load_fixture("brenda_ldh_ki_fixture.html")}
        ),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        allow_cross_species=False,
        quantity="ki",
        lineage_provider=fixture_lineage_provider,
    )


def test_the_his_tagged_row_that_motivated_this_is_reported() -> None:
    """The measured case. 0.00059 is a His-tagged construct's Ki, and it was
    returned as the human enzyme's with nothing saying so."""
    result = _ldh_ki("NADH")
    assert result.found
    assert result.value == 0.00059
    assert result.preparation is not None
    assert result.preparation.status == "tagged"
    assert result.preparation.differs_from_the_free_enzyme


def test_it_travels_as_a_FIELD_not_only_a_log_line() -> None:
    """`provenance.flags` is what the CLI and web UI render; the resolver's
    diagnostic log is not. `queryResolver.ts` records four ADRs whose
    findings "reached only the logs, which is the same as reaching nobody",
    and the first version of this change would have been the fifth.

    So the assertion is on the RESULT OBJECT, not on `search_log`.
    """
    result = _ldh_ki("NADH")
    assert result.preparation is not None, (
        "the preparation verdict reached the log but not the result; a "
        "finding that only reaches the log reaches nobody"
    )


def test_the_search_log_says_it_too() -> None:
    """Belt and braces: the log is not the delivery mechanism, but a reader
    reading it should not have to infer this from the value."""
    joined = " ".join(_ldh_ki("NADH").search_log)
    assert "TAGGED" in joined
    assert "His-tagged" in joined


# ---------------------------------------------------------------------------
# When the curator says the modification did not matter
#
# Golden tuple G2 pins Km 0.09 for human AChE / acetyl thiocholine. That row
# is PEGylated — so a blanket exclusion would have deleted a hand-verified
# golden value. Its commentary reads:
#
#   "pH 8, 27°C, attachment of polyethylene glycol side chains to lysine
#    residues does not alter the Km value"
#
# The curator states the modification had no effect ON KM. The residue
# baseline predicted this would be the one case where the commentary says a
# difference does not matter.
# ---------------------------------------------------------------------------


def test_the_no_effect_clause_is_read() -> None:
    verdict = classify(
        "pH 8, 27°C, attachment of polyethylene glycol side chains to "
        "lysine residues does not alter the Km value"
    )
    # BOTH facts are kept. The enzyme WAS modified; the curator says it did
    # not move this number. Collapsing them would lose the first, and the
    # first is what lets a reader judge the second.
    assert verdict.status == "modified"
    assert verdict.stated_not_to_affect == "KM"


def test_the_exception_is_quantity_specific() -> None:
    """The whole point. The same PEGylated AChE row carries this clause for
    Km in one table and for Kcat in another, so the statement is about a
    MEASUREMENT, not about the protein. Reading it as "this modification is
    harmless" would generalise a claim the curator did not make.
    """
    km_row = classify("polyethylene glycol ... does not alter the Km value")
    assert km_row.differs_for("km") is False
    assert km_row.differs_for("ki") is True, (
        "a statement about Km says nothing about Ki"
    )
    assert km_row.differs_for("kcat") is True
    # With no quantity in hand, the honest answer is that it differs.
    assert km_row.differs_for(None) is True


def test_a_modification_with_no_such_clause_still_warns() -> None:
    tagged = classify("recombinant His-tagged enzyme")
    assert tagged.stated_not_to_affect is None
    for quantity in ("km", "ki", "kcat", None):
        assert tagged.differs_for(quantity) is True


def test_the_golden_g2_row_does_not_warn_for_km() -> None:
    """End to end. G2 is a real golden tuple and its row is PEGylated; the
    resolver must not warn, because the source says Km is unaffected."""
    result = resolve_kinetic_value(
        "3.1.1.7",
        "Homo sapiens",
        "acetyl thiocholine",
        html_provider=make_html_provider(
            {"3.1.1.7": load_fixture("brenda_ache_fixture.html")}
        ),
        uniprot_provider=fake_uniprot_provider,
        taxon_id_provider=fake_taxon_id_provider,
        search_literature=False,
        allow_cross_species=False,
        quantity="km",
        lineage_provider=fixture_lineage_provider,
    )
    assert result.value == 0.09, "G2's pinned value"
    assert result.preparation is not None
    assert result.preparation.status == "modified"
    assert result.preparation.stated_not_to_affect == "KM"
    assert not any("free enzyme" in line for line in result.search_log), (
        "warned about a modification the source says did not alter this value"
    )
