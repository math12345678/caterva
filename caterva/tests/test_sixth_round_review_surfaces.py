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


# ---------------------------------------------------------------------------
# XS5R2-03: a run in the isozymes' own organism says isozymes, and --isoform
# ---------------------------------------------------------------------------


def test_variant_withheld_of_isozymes_only_says_isozyme_and_isoform():
    from caterva.agents.adapters import to_parameter_source

    result = SimpleNamespace(found=False, source="variant_withheld",
                             variant_candidates_available=["isoenzyme A", "isoenzyme B"],
                             variant_isozymes_only=True)
    _, reason = to_parameter_source("kcat", result)
    assert "names an isozyme" in reason and "--isoform" in reason
    assert "variant" not in reason.split(" -- ")[0]
    assert "the isozymes: isoenzyme A, isoenzyme B" in reason


def test_the_step_for_isozyme_rows_is_isoform_naming_one():
    from caterva.compose import verdict

    reason = ("every row BRENDA holds for this constant names an isozyme, a wild-type protein in its "
              "own right, and a named isozyme's row is taken only when --isoform names it -- the "
              "isozymes: isoenzyme A, isoenzyme B (searched under the requirement that organism must "
              "be Vibrio tyrosinaticus, raised by your own request)")
    model = SimpleNamespace(not_found={"reaction_kcat": reason, "reaction_Km": reason})
    step = verdict._what_would_ground(model, ["reaction_Km", "reaction_kcat"])
    assert "--isoform set to one of 'isoenzyme A', 'isoenzyme B'" in step


def test_the_resolver_marks_a_withheld_set_of_isozymes():
    import fallback_logic

    iso = SimpleNamespace(variant=SimpleNamespace(kind="isozyme", evidence="isoenzyme A"))
    mut = SimpleNamespace(variant=SimpleNamespace(kind="point_mutation", evidence="K48Q"))
    assert fallback_logic._variant_withheld_result([iso], []).variant_isozymes_only is True
    assert fallback_logic._variant_withheld_result([iso, mut], []).variant_isozymes_only is False


# ---------------------------------------------------------------------------
# NEW-17: a variant-only constant names where the enzyme as found is measured
# ---------------------------------------------------------------------------

#: EC 2.1.1.45 kcat for dUMP: E. coli has only K48Q; human wild type has rows.
TS_KCAT = (
    _Row("dUMP", "Escherichia coli", "mutant K48Q, pH 7.5", 0.01, "1", None, True),
    _Row("dUMP", "Homo sapiens", "wild type, pH 7.4, 25°C", 3.11, "706625"),
    _Row("dUMP", "Homo sapiens", "wild type", 48.0, "720965"),
)


def test_a_variant_only_constant_names_the_wild_type_elsewhere(monkeypatch):
    from caterva.compose.__main__ import _wild_type_elsewhere

    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, organism=None: TS_KCAT)
    said = _wild_type_elsewhere("2.1.1.45", "kcat", "dUMP", "Escherichia coli")
    assert "available in: Homo sapiens (2 rows)" in said
    assert "Escherichia coli" not in said


# ---------------------------------------------------------------------------
# NEW-17, R5B2-02, VR2-05, VR2-06: the report's passed-over and spread notes
# ---------------------------------------------------------------------------


def test_passed_over_values_keep_their_unit_not_the_last_word():
    from caterva.compose.report import _passed_over_far

    record = SimpleNamespace(value=0.6, chosen_because=None, resolver_because=(
        "0.6 mM (BRENDA ref 712198) is the only row remaining; of the 2 candidate rows (after the "
        "organism, substrate, isoform and variant checks): 1 row(s) stating neither pH nor "
        "temperature passed over (0.07 mM, and no row states both)"))
    (said,) = _passed_over_far(record)
    assert said.endswith("(0.07 mM)")
    assert "both)" not in said


def test_a_row_passed_over_for_another_reason_is_named_with_that_reason():
    from caterva.compose.report import _passed_over_far

    record = SimpleNamespace(value=24.5, chosen_because=None, resolver_because=(
        "x; of the 6 candidate rows (after the checks): 1 row(s) of a recombinant or transgenic "
        "preparation passed over (408 1/s) for the same paper's row of the enzyme from its own "
        "source; 3 row(s) not stating both pH and temperature passed over (196, 414, 545 1/s)"))
    said = _passed_over_far(record)
    assert any("recombinant" in s and "(408 1/s)" in s and "its own source" in s for s in said)
    assert any("(196, 414, 545 1/s)" in s for s in said)


def test_the_resolver_says_the_values_of_rows_it_prefers_against():
    import fallback_logic

    src = Path(fallback_logic.__file__).read_text()
    # The values go in after "passed over", where the report reads them.
    assert 'text = f"{text[:at]} ({shown}' in src
    assert "rows left after the checks, this one among them, span" in src


def test_different_papers_are_said_with_the_other_paper_s_own_row():
    from caterva.compose.report import _other_papers

    km = SimpleNamespace(citation="BRENDA ref 712198", unit="mM", alternatives=(
        {"value": 0.07, "reference_id": "667627"}, {"value": 0.6, "reference_id": "712198"}))
    ki = SimpleNamespace(citation="BRENDA ref 667627", unit="mM", alternatives=())
    said = _other_papers("reaction_Km", km, {"reaction_Km": km, "reaction_Ki": ki})
    assert "`reaction_Ki` comes from another paper (BRENDA ref 667627)" in said
    assert "(0.07 mM) was passed over" in said
    assert _other_papers("reaction_Km", km, {"reaction_Km": km}) == ""


def test_the_carried_row_is_not_said_to_be_the_only_one_left_when_rows_were_passed_over():
    src = (REPO / "caterva" / "compose" / "report.py").read_text()
    assert "the only row left after the checks; some rows" not in src


def test_the_resolver_s_row_is_not_said_to_be_for_an_isoform_it_does_not_name():
    src = (REPO / "caterva" / "compose" / "narrowed.py").read_text()
    assert "the resolver's row for {what}" not in src
    assert "the row the resolver returns when asked for {what}" in src


# ---------------------------------------------------------------------------
# NEW-17: names typed and names read
# ---------------------------------------------------------------------------


def test_a_trailing_concentration_is_not_part_of_the_compound():
    import effector

    (found,) = effector.extract_effectors("succinate with papyriferic acid 0.04 mM, pH 7.4, 25°C")
    assert found.compound_text == "papyriferic acid"
    assert found.concentration_text == "0.04 mM"
    (found,) = effector.extract_effectors("with NADH 1 mM")
    assert (found.compound_text, found.concentration_text) == ("NADH", "1 mM")


def test_an_isoform_label_not_typed_is_said_as_read_from_the_words_typed():
    src = (REPO / "caterva" / "compose" / "__main__.py").read_text()
    assert "was read as the \"" in src and "isoform\", 1)" in src


def test_a_construct_list_inside_parentheses_is_one_clause():
    from caterva.compose.report import _passed_over_far

    # ACE, live: "an isolated domain ('N-domain')) passed over" was printed,
    # the clause cut at a "; " inside its own parentheses.
    record = SimpleNamespace(value=24.5, chosen_because=None, resolver_because=(
        "x; of the 6 candidate rows (after the checks): 1 row(s) measuring a construct or altered "
        "preparation (an isolated domain ('N-domain'); a chimera) passed over (262.5 1/s) for rows "
        "of the native enzyme"))
    (said,) = _passed_over_far(record)
    assert said.startswith("1 row(s) measuring a construct or altered preparation (an isolated domain")
    assert "(262.5 1/s)" in said


def test_the_other_paper_s_own_row_is_read_from_the_table(monkeypatch):
    from caterva.compose.report import _other_papers

    rows = (_Row("(R,S)-mevalonate", "Homo sapiens", "", 0.07, "667627", "P04035"),
            _Row("(R,S)-mevalonate", "Homo sapiens", "pH 7.5", 0.6, "712198"))
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, organism=None: rows)
    q = SimpleNamespace(parameter_id="reaction_Km", table="km")
    model = SimpleNamespace(resolvable=(q,), subject="1.1.1.34", organism="Homo sapiens",
                            compound_for=lambda _q: "(R,S)-mevalonate")
    km = SimpleNamespace(citation="BRENDA ref 712198", unit="mM", alternatives=())
    ki = SimpleNamespace(citation="BRENDA ref 667627", unit="mM", alternatives=())
    said = _other_papers("reaction_Km", km, {"reaction_Km": km, "reaction_Ki": ki}, model)
    assert "whose own row for this constant (0.07 mM) was passed over" in said


def test_an_end_of_the_spread_the_reason_does_not_mention_is_explained():
    from caterva.compose.report import ModelDossier

    notes = ("`reaction_Km`: a row naming NOS1 exists (4.8 mM, BRENDA ref 659257), but no row "
             "naming NOS1 gives the kcat, so the resolver's pick, which names no isoform, is kept "
             "beside it: one evidence rule for both constants",)
    me = SimpleNamespace(model=SimpleNamespace(
        recognition=SimpleNamespace(composition=SimpleNamespace(notes=notes))))
    spread = SimpleNamespace(low=0.0022, high=4.8, unit="mM",
                             carried_as="0.0022 mM (BRENDA ref 658119) is the only row remaining")
    said = ModelDossier._end_set_aside(me, "reaction_Km", spread)
    assert said.startswith("the 4.8 mM row is not carried: a row naming NOS1 exists (4.8 mM, BRENDA ref 659257)")
    assert "0.0022 mM row" not in said


def test_a_word_of_the_chosen_organism_typed_is_not_called_no_organism():
    src = (REPO / "caterva" / "compose" / "__main__.py").read_text()
    # "influenza neuraminidase inhibited by zanamivir": the whole description
    # is searched for a word of the organism Caterva chose.
    assert 'typed = str(getattr(args, "description", None) or "")' in src
    assert "but no \"\n" in src or "names {said[0]!r} but no" in src


def test_a_para_locant_before_a_capital_is_the_same_compound():
    # DHPS listed "4-Aminobenzoate (2 Km, 1 kcat)" and "p-Aminobenzoate (1 Km)"
    # as two compounds. The chooser and the search agree they are one.
    from caterva.compose import defaults

    assert defaults._group_key("p-Aminobenzoate") == defaults._group_key("4-aminobenzoate")
    assert defaults._matches("p-Aminobenzoate", "4-Aminobenzoate")
    assert defaults._group_key("p-Nitrophenyl phosphate") == defaults._group_key("4-nitrophenyl phosphate")
    # An oxygen substituent is not an ortho locant.
    assert defaults._group_key("O-Acetylserine") != defaults._group_key("2-acetylserine")
