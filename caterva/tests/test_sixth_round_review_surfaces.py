"""Sixth round of the real-values review: surfaces and advice (ADR 0182).

Offline: BRENDA's rows are recorded here as `defaults._Row`s, with the
values and references the review quoted, and `defaults.table_rows` is
patched to return them. Each test names the finding it holds.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from caterva.compose import defaults
from caterva.compose.defaults import _Row
from caterva.enzymes.isozyme import IsozymeNotice

REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# R5A2-01, R5A2-02, R5B2-03, XS5R2-08: the isozyme example and its outcome
# ---------------------------------------------------------------------------


def _notice(**kw):
    base = dict(ec="3.4.21.4", organism="Homo sapiens", count=5,
                symbols=("PRSS58", "PRSS1", "PRSS2", "PRSS3", "PRSS3P2"),
                measured_as="PRSS3", measured_pairs=(), substrate="Z-Gly-Pro-Arg-p-nitroanilide")
    base.update(kw)
    return IsozymeNotice(**base)


def test_trypsin_example_is_prss1_not_prss58_and_not_the_modelled_prss3():
    remedy = _notice().remedy
    # PRSS58 has no BRENDA rows; it was offered only because it came first.
    assert "--isoform PRSS1 (or another of the rest)" in remedy
    assert "PRSS58 (or another" not in remedy
    # The sentence tells the user to pass PRSS3, so PRSS3 is not "the rest".
    tail = remedy.split("so --isoform", 1)[1]
    assert "PRSS3 " not in tail.split("gives no pair")[0]


def test_hexokinase_example_is_the_best_measured_other_protein():
    notice = _notice(ec="2.7.1.1", symbols=("HKDC1", "HK1", "HK2", "HK3", "GCK"),
                     measured_as="GCK", measured_pairs=("GCK",), substrate="D-glucose",
                     named_rows=(("HKDC1", 0), ("HK1", 3), ("HK2", 1), ("HK3", 0), ("GCK", 13)))
    remedy = notice.remedy
    assert "--isoform HK1 (or another of the rest)" in remedy
    assert "HKDC1 (or another" not in remedy


def test_the_example_falls_back_to_the_lowest_number_with_no_counts():
    notice = _notice(ec="2.7.1.1", symbols=("HKDC1", "HK1", "HK2", "HK3", "GCK"),
                     measured_as="GCK", measured_pairs=("GCK",), substrate="D-glucose")
    assert "--isoform HK1 (or another" in notice.remedy


def test_the_outcome_is_not_promised_as_an_unnamed_row():
    # HK1's run leaves kcat a placeholder (no human kcat row names it), and
    # trypsin with PRSS1 takes rows naming no isozyme. Both are said.
    remedy = _notice().remedy
    assert "its kcat would come from a row naming no isozyme" not in remedy
    assert "stays a placeholder" in remedy
    assert "comes from a row naming no isozyme" in remedy


# ---------------------------------------------------------------------------
# XS5R2-08, VR2-05: one wording for an isoform read off the cell or paper
# ---------------------------------------------------------------------------


def test_an_isoform_from_the_cell_or_paper_is_not_said_to_be_measured_in_words():
    from caterva.compose.row_scope import read_scope as scope_of

    scope = scope_of("wild type enzyme, in 20 mM Tricine", motif="michaelis_menten", table="km",
                     row_isoform="PRSS3")
    text = " ".join(c.text for c in scope.concerns)
    assert "the row names no isoform itself" in text
    assert "ties it to isoform PRSS3" in text
    assert "the row measured isoform PRSS3" not in text


def test_an_isoform_in_the_row_words_is_still_measured():
    from caterva.compose.row_scope import read_scope as scope_of

    scope = scope_of("isozyme LDH-B, pH 7.4", motif="michaelis_menten", table="km")
    assert any("the row measured isoform LDH-B" in c.text for c in scope.concerns)


# ---------------------------------------------------------------------------
# VR2-02, VR2-04: TEM-1's rows list several proteins and name none
# ---------------------------------------------------------------------------

#: BRENDA EC 3.5.2.6, Escherichia coli, ref 696728: every TEM-1 accession row
#: also lists OXA-1's (P13661) and names neither in words.
TEM_KM = [
    _Row("nitrocefin", "Escherichia coli", "pH 7.0, 25°C", 0.0076, "696728", "P13661 , P62593"),
    _Row("nitrocefin", "Escherichia coli", "pH 7.0, 25°C", 0.0226, "696728", "P13661 , P62593"),
    _Row("nitrocefin", "Escherichia coli", "pH 7.0, 25°C", 0.086, "696728", "P13661 , P62593"),
    _Row("cephalothin", "Escherichia coli", "pH 7.0, 25°C", 0.12, "696728", "P13661 , P62593"),
    # ref 696228: benzylpenicillin, naming no protein at all.
    _Row("benzylpenicillin", "Escherichia coli", "pH 7.0, 30°C", 0.026, "696228", None),
]


def test_tem1_advice_does_not_offer_rows_the_search_withholds(monkeypatch):
    from caterva.compose.protein_rows import _where_rows_are

    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, organism=None: TEM_KM)
    said = _where_rows_are("3.5.2.6", "km", {"P62593"})
    assert "re-run with --substrate nitrocefin" not in said
    assert "list it among other proteins' accessions and name none of them" in said
    assert "696728" in said and "no re-run fills it" in said


def test_tem1_advice_still_offers_rows_naming_it_alone(monkeypatch):
    from caterva.compose.protein_rows import _where_rows_are

    rows = TEM_KM + [_Row("ampicillin", "Escherichia coli", "TEM-1, pH 7", 0.02, "1", "P62593")]
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, organism=None: rows)
    said = _where_rows_are("3.5.2.6", "km", {"P62593"})
    assert "re-run with --substrate ampicillin" in said
    assert "nitrocefin" not in said


def test_the_chooser_does_not_count_rows_that_do_not_name_tem1():
    from caterva.compose.protein_rows import strict_alias

    strict = strict_alias("3.5.2.6", "TEM-1")
    assert strict is not None
    usable = defaults._usable([TEM_KM[4]], "TEM-1", strict=strict)
    assert usable.rows == []
    assert any("does not name TEM-1" in why for why in usable.set_aside)
    # A row with TEM-1's accession alone is its row.
    alone = _Row("ampicillin", "Escherichia coli", "pH 7", 0.02, "1", "P62593")
    assert defaults._usable([alone], "TEM-1", strict=strict).rows == [alone]
    # Without the strict alias, the old rule (rows naming none) stands.
    assert defaults._usable([TEM_KM[4]], "TEM-1").rows == [TEM_KM[4]]


# ---------------------------------------------------------------------------
# XS5R2-03, NEW-17: organisms offered for a re-run
# ---------------------------------------------------------------------------

#: BRENDA EC 1.14.18.1 kcat for L-Dopa (the values the review quoted).
TYR_KCAT = {
    "Vibrio tyrosinaticus": [
        _Row("L-Dopa", "Vibrio tyrosinaticus", "isoenzyme A", 75.0, "636408", None, True, True),
        _Row("L-Dopa", "Vibrio tyrosinaticus", "isoenzyme B", 90.0, "636408", None, True, True),
    ],
    "Streptomyces antibioticus": [
        _Row("L-Dopa", "Streptomyces antibioticus", "pH 6.8", 100.0 + i, str(i), None)
        for i in range(5)],
    "Homo sapiens": [_Row("L-Dopa", "Homo sapiens", "native enzyme, pH 7.2, 37°C", 38.1, "745746")],
}


def _patch_tyr(monkeypatch):
    monkeypatch.setattr(defaults, "table_rows",
                        lambda ec, table, organism=None: TYR_KCAT.get(organism, []))


def test_isozyme_only_organisms_are_not_offered_as_a_rerun(monkeypatch):
    from caterva.compose.__main__ import _available_elsewhere

    _patch_tyr(monkeypatch)
    reason = ("no value in the organism requested -- available in: Homo sapiens, "
              "Streptomyces antibioticus, Vibrio tyrosinaticus")
    said = _available_elsewhere("1.14.18.1", "kcat", "L-Dopa", reason, asked="Mus musculus")
    offered = said.split("available in: ", 1)[1].split(" (rows of a named isozyme", 1)[0]
    assert "Vibrio" not in offered
    assert "named isozyme only" in said and "Vibrio tyrosinaticus (2 rows)" in said
    assert "variant" not in said


def test_a_mammal_is_named_first_for_a_mammal(monkeypatch):
    from caterva.compose.__main__ import _available_elsewhere

    _patch_tyr(monkeypatch)
    reason = "x -- available in: Homo sapiens, Streptomyces antibioticus"
    said = _available_elsewhere("1.14.18.1", "kcat", "L-Dopa", reason, asked="Mus musculus")
    assert said.index("Homo sapiens") < said.index("Streptomyces")
    # For a bacterium, rows decide, as before.
    said = _available_elsewhere("1.14.18.1", "kcat", "L-Dopa", reason, asked="Escherichia coli")
    assert said.index("Streptomyces") < said.index("Homo sapiens")


def test_isozyme_rows_only_says_isoform_not_organism(monkeypatch):
    from caterva.compose.__main__ import _available_elsewhere

    _patch_tyr(monkeypatch)
    said = _available_elsewhere("1.14.18.1", "kcat", "L-Dopa", "x -- available in: Vibrio tyrosinaticus",
                                asked="Mus musculus")
    assert said.startswith("no usable value")
    assert "--isoform" in said and "variant" not in said


# ---------------------------------------------------------------------------
# XS5R2-04, XS5R2-05: what the API runner hands the TypeScript surfaces
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner(monkeypatch):
    lib = REPO / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib"
    monkeypatch.syspath_prepend(str(REPO / "Tests"))
    monkeypatch.syspath_prepend(str(lib))
    sys.modules.pop("science_agent_runner", None)
    import science_agent_runner

    return science_agent_runner


def test_the_runner_says_which_protein_hexokinase_was_modelled_as(runner, monkeypatch):
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, organism=None: [])
    km = SimpleNamespace(found=True, commentary="wild-type, K0.5 value, Hill coefficient 1.8",
                         row_isoform="GCK", chosen_because=None)
    kcat = SimpleNamespace(found=True, commentary="wild-type", row_isoform="GCK", chosen_because=None)
    notice = runner._isozyme_notice("2.7.1.1", "Homo sapiens", None, "D-glucose", km, kcat)
    assert notice is not None
    assert "5 human proteins" in notice["detail"]
    assert "the model is of GCK" in notice["detail"]
    assert "GCK's constants" in notice["headline"]


def test_the_runner_says_nothing_without_a_found_km(runner):
    assert runner._isozyme_notice("2.7.1.1", "Homo sapiens", None, "D-glucose",
                                  SimpleNamespace(found=False), None) is None


def test_the_paired_kcat_summary_carries_the_withheld_reason(runner):
    kcat = SimpleNamespace(found=False, value=None, source="cross_species_withheld",
                           cross_species_organisms_available=["Homo sapiens", "Vibrio tyrosinaticus"],
                           cross_species_variant_only=["Vibrio tyrosinaticus"],
                           variant_candidates_available=None, implausible_values=None,
                           isoforms_available=None)
    out = runner._paired_kcat_summary(kcat)
    assert out["found"] is False and out["source"] == "cross_species_withheld"
    assert out["crossSpeciesVariantOnly"] == ["Vibrio tyrosinaticus"]
    found = runner._paired_kcat_summary(SimpleNamespace(found=True, value=40.1, source="brenda_exact",
                                                        citation=None))
    assert found == {"found": True, "source": "brenda_exact", "kcat": 40.1, "citation": None}
    assert runner._paired_kcat_summary(None) is None
