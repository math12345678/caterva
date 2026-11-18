"""The sixth adversarial round of the real-values work (2026-11-13), the
parts that are caterva's: which substrate and which organism the choosers
rank first, and what the report says of the row it carries. Offline:
`defaults.table_rows` is replaced by rows written here (values, compounds,
organisms, conditions and references as BRENDA writes them).

- aldolase B's "D-Fructose 1-phosphate" row was withheld as another
  compound's when the model named "fructose 1-phosphate";
- sheep 6PGD was modelled on 6-phosphono-D-gluconate, a synthetic analogue,
  over 6-phosphogluconate's 14 Km rows;
- influenza neuraminidase was modelled on fetuin, a glycoprotein;
- "RNase A", "lysozyme" and "beta-galactosidase" were modelled in the
  organism with the most rows, not the one the name means;
- an organism won on one paper's temperature series;
- DPP4's isoform row, which states no conditions, replaced a pick that does,
  with no word;
- a refolded His-tagged CES1 kcat and a chymotrypsin row 10-fold from the
  carried one were carried or passed over without a word.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from caterva.compose import defaults
from caterva.compose.export import Measurement
from caterva.compose.isoform import ASKED_BY_WORDS, select_isoform
from caterva.compose.report import _construct_note, _wild_type_label_note


def _given(monkeypatch, rows, natural=()):
    def table_rows(ec, table, organism):
        return tuple(r for r in rows.get(table, ()) if organism is None or r.organism == organism)

    monkeypatch.setattr(defaults, "table_rows", table_rows)
    monkeypatch.setattr(defaults, "_reaction_compounds", lambda ec: (
        frozenset(defaults._key(n) for n in natural), frozenset(defaults._key(n) for n in natural)))


def _row(compound, conditions="", ref="1", organism="Homo sapiens", value=1.0):
    return defaults._Row(compound, organism, conditions, value, ref, None, False, False)


# -- NEW-03: a stereo descriptor the model's name leaves out is the same compound ----------

def test_a_d_prefix_is_the_same_compound_when_no_other_form_is_listed():
    listed = ["D-Fructose 1-phosphate", "fructose 1-phosphate"]
    assert defaults.stereo_twin("D-Fructose 1-phosphate", "fructose 1-phosphate", listed)
    # Another configuration listed: the bare name could mean either.
    assert not defaults.stereo_twin("D-Fructose 1-phosphate", "fructose 1-phosphate",
                                    listed + ["L-fructose 1-phosphate"])
    # A name inside a longer name is not the compound.
    assert not defaults.stereo_twin("2-deoxy-D-glucose", "glucose", ["2-deoxy-D-glucose"])
    assert not defaults.stereo_twin("D-glucose 6-phosphate", "glucose", ["D-glucose 6-phosphate"])


# -- NEW-12: a synthetic analogue ranks after the natural substrate ---------------------------

def test_a_phosphonate_analogue_is_read_as_one():
    assert defaults.analogue_of("6-phosphono-D-gluconate", ["6-phosphogluconate"]) == "6-phosphogluconate"
    assert defaults.analogue_of("2-deoxy-6-phosphogluconate", ["6-phosphogluconate"]) == "6-phosphogluconate"
    assert defaults.analogue_of("6-phosphogluconate", ["6-phosphono-D-gluconate"]) is None
    assert defaults.analogue_of("NADP+", ["6-phosphogluconate"]) is None


def test_sheep_6pgd_is_modelled_on_its_natural_substrate(monkeypatch):
    km = ([_row("6-phosphogluconate", f"pH 7.5, 25°C, wild type", str(286829 + i), "Ovis aries", 0.02)
           for i in range(12)]
          + [_row("6-phospho-D-gluconate", "wild type, pH 7.5", "669487", "Ovis aries", 0.028)]
          + [_row("6-phosphono-D-gluconate", "pH 8.0, 20°C", "654952", "Ovis aries", 0.03)])
    kcat = [_row("6-phosphono-D-gluconate", "pH 8.0, 20°C", "654952", "Ovis aries", 9.0)]
    _given(monkeypatch, {"km": km, "kcat": kcat},
           natural=["6-phosphogluconate", "6-phospho-D-gluconate", "6-phosphono-D-gluconate"])
    choice = defaults.choose_substrate("1.1.1.44", "Ovis aries")
    assert defaults._group_key(choice.chosen) == defaults._group_key("6-phosphogluconate")
    assert "synthetic analogue" in choice.why
    assert "kcat stays a placeholder" in choice.why


# -- NEW-11: a glycoprotein ranks after a defined natural substrate ---------------------------

def test_fetuin_is_ill_defined_and_ranks_after_sialyllactose(monkeypatch):
    assert defaults.is_ill_defined("fetuin") and defaults.is_macromolecule("fetuin")
    assert defaults.is_ill_defined("bovine submaxillary mucin")
    assert not defaults.is_ill_defined("alpha-(2-3)-sialyllactose")
    org = "influenza A virus"
    km = [_row("fetuin", "pH 7.5, 22°C", "773097", org, 0.00051),
          _row("alpha-(2-3)-sialyllactose", "pH 6.0, 37°C", "655754", org, 0.18)]
    kcat = [_row("fetuin", "pH 7.5, 22°C", "773097", org, 8.76)]
    _given(monkeypatch, {"km": km, "kcat": kcat}, natural=["fetuin", "alpha-(2-3)-sialyllactose"])
    choice = defaults.choose_substrate("3.2.1.18", org)
    assert choice.chosen == "alpha-(2-3)-sialyllactose"
    assert "glycoprotein" in choice.why


# -- NEW-13, XS5R2-10, NEW-16: the organism a name means --------------------------------------

def test_names_that_mean_one_organism():
    assert defaults.implied_organism("4.6.1.18", "ribonuclease A")[0] == "Bos taurus"
    assert defaults.implied_organism("4.6.1.18", "RNase A H12A")[0] == "Bos taurus"
    assert defaults.implied_organism("3.2.1.17", "lysozyme")[0] == "Gallus gallus"
    assert defaults.implied_organism("3.2.1.23", "beta-galactosidase")[0] == "Escherichia coli"
    assert defaults.implied_organism("3.2.1.17", "human lysozyme") is None
    assert defaults.implied_organism("4.6.1.18", "ribonuclease T1") is None
    assert defaults.implied_organism("3.2.1.23", None) is None


def test_rnase_a_is_modelled_in_cow_though_human_covers_both(monkeypatch):
    km = ([_row("cytidine 2',3'-cyclic phosphate", "pH 5.5, 25°C", "655910", "Bos taurus", 0.46)]
          + [_row("cytidine 2',3'-cyclic phosphate", "pH 5.0, 25°C", str(679735 + i), "Homo sapiens", 0.44)
             for i in range(3)])
    kcat = [_row("cytidine 2',3'-cyclic phosphate", "pH 5.5, 25°C", "655910", "Bos taurus", 2.0),
            _row("cytidine 2',3'-cyclic phosphate", "pH 5.0, 25°C", "679735", "Homo sapiens", 0.36)]
    _given(monkeypatch, {"km": km, "kcat": kcat})
    chosen = defaults.choose_organism("4.6.1.18", needs=("km", "kcat"), named_as="ribonuclease A")
    assert chosen.chosen == "Bos taurus"
    assert "bovine pancreatic ribonuclease" in chosen.why
    plain = defaults.choose_organism("4.6.1.18", needs=("km", "kcat"), named_as="ribonuclease")
    assert plain.chosen == "Homo sapiens"


def test_lysozyme_counts_every_organism_and_names_hen_egg_white(monkeypatch):
    km = [_row("4-MU-chitotrioside", "pH 5.0, 25°C", "718362", "Gallus gallus", 0.001),
          _row("4-MU-chitotrioside", "pH 5.0, 25°C", "718363", "Gallus gallus", 0.002),
          _row("peptidoglycan", "pH 6, 25°C", "679934", "Liolophura japonica", 8.33)]
    kcat = [_row("peptidoglycan", "pH 6, 25°C", "679934", "Liolophura japonica", 0.076),
            _row("peptidoglycan", "pH 6, 25°C", "696869", "Homo sapiens", 0.015)]
    _given(monkeypatch, {"km": km, "kcat": kcat})
    chosen = defaults.choose_organism("3.2.1.17", needs=("km", "kcat"), named_as="lysozyme")
    # Hen egg-white lysozyme has no kcat row: the organism that measures both
    # constants is kept (a placeholder is not a better answer), and the hen
    # enzyme is named, first among the others, with how to model it.
    assert chosen.chosen == "Liolophura japonica"
    assert "hen egg-white lysozyme" in chosen.why
    assert '--organism "Gallus gallus"' in chosen.why and "2 Km, 0 kcat" in chosen.why
    assert chosen.alternatives[0].name == "Gallus gallus"
    assert "Homo sapiens (1 kcat)" in chosen.why


def test_hen_egg_white_lysozyme_is_used_once_it_covers_as_much(monkeypatch):
    km = [_row("4-MU-chitotrioside", "pH 5.0, 25°C", "718362", "Gallus gallus", 0.001),
          _row("peptidoglycan", "pH 6, 25°C", "679934", "Liolophura japonica", 8.33),
          _row("peptidoglycan", "pH 6, 25°C", "679935", "Liolophura japonica", 8.0)]
    kcat = [_row("peptidoglycan", "pH 6, 25°C", "679934", "Liolophura japonica", 0.076),
            _row("4-MU-chitotrioside", "pH 5.0, 25°C", "718362", "Gallus gallus", 0.5)]
    _given(monkeypatch, {"km": km, "kcat": kcat})
    chosen = defaults.choose_organism("3.2.1.17", needs=("km", "kcat"), named_as="lysozyme")
    assert chosen.chosen == "Gallus gallus"
    assert "hen egg-white lysozyme" in chosen.why


# -- XS5R2-02: organisms are ranked by papers, not one paper's series ------------------------

def test_one_papers_temperature_series_does_not_win_the_organism(monkeypatch):
    onpg = "o-nitrophenyl-beta-D-galactoside"
    series = [_row(onpg, f"at {t}°C", "702907", "Arthrobacter sp.", v)
              for t, v in ((10, 5.75), (20, 4.86), (30, 3.46), (40, 3.15), (50, 2.62), (55, 5.11))]
    series += [_row(onpg, f"at {t}°C", "655860", "Arthrobacter sp.", 0.7) for t in (5, 10, 20)]
    coli = [_row(onpg, "pH 7.0, 25°C", ref, "Escherichia coli", v)
            for ref, v in (("706624", 0.04), ("682849", 0.093), ("706614", 0.12), ("703289", 0.122))]
    kcat = ([_row(onpg, "at 30°C", "702907", "Arthrobacter sp.", 124.0)] * 10
            + [_row(onpg, "pH 7.0, 25°C", ref, "Escherichia coli", v)
               for ref, v in (("706624", 90.0), ("682849", 400.0), ("706614", 620.0))])
    _given(monkeypatch, {"km": series + coli, "kcat": kcat})
    # No name that means an organism: the papers decide.
    chosen = defaults.choose_organism("3.2.1.23", onpg, needs=("km", "kcat"))
    assert chosen.chosen == "Escherichia coli"
    assert "the most papers" in chosen.why
    assert "Arthrobacter sp. has more rows" in chosen.why


def test_subtype_organisms_are_named_under_the_virus():
    per = {"influenza A virus": {"km": 11, "kcat": 1},
           "influenza A virus H1N1": {"km": 3, "kcat": 2},
           "Homo sapiens": {"km": 33, "kcat": 1}}
    said = defaults._subtypes_clause("influenza A virus", per)
    assert "influenza A virus H1N1: 3 Km, 2 kcat" in said and "--organism" in said
    assert defaults._subtypes_clause("Homo sapiens", per) == ""


# -- XS5R2-06: an isoform row that states no conditions is said to ---------------------------

def _dpp4(identifier):
    km = identifier.endswith("_Km")
    rows = (
        [{"value": 0.09, "unit": "mM", "reference_id": "678195", "conditions": "dimeric rDPP-IV",
          "isoform": "DPP4"},
         {"value": 0.165, "unit": "mM", "reference_id": "649281", "conditions": "pH 7.6, 30°C"}]
        if km else
        [{"value": 87.0, "unit": "1/s", "reference_id": "678195", "conditions": "dimeric rDPP-IV",
          "isoform": "DPP4"},
         {"value": 20.3, "unit": "1/s", "reference_id": "695876", "conditions": "wild type, pH 8.0"}])
    value, ref = (0.165, "649281") if km else (20.3, "695876")
    return Measurement(value, "mM" if km else "1/s", f"BRENDA ref {ref}", organism="Homo sapiens",
                       commentary=rows[1]["conditions"], alternatives=tuple(rows))


def test_an_isoform_row_stating_no_conditions_is_said_to_lose_them():
    out = select_isoform({"reaction_Km": _dpp4("reaction_Km"), "reaction_kcat": _dpp4("reaction_kcat")},
                         "DPP4", ASKED_BY_WORDS)
    km_note = next(n for n in out.notes if n.startswith("`reaction_Km`"))
    kcat_note = next(n for n in out.notes if n.startswith("`reaction_kcat`"))
    assert "states no pH or temperature" in km_note and "pH 7.6, 30°C" in km_note
    # The kcat pick states a pH only: nothing better-described was lost.
    assert "states no pH or temperature" not in kcat_note


# -- NEW-08, NEW-18: what the carried row is, and what its paper's other row is ---------------

def test_a_carried_construct_row_is_said():
    m = SimpleNamespace(commentary="recombinant refolded His-taggged wild-type enzyme, pH 7.5, 37°C")
    note = _construct_note(m)
    assert note and "tagged construct" in note and "not the native enzyme" in note
    assert _construct_note(SimpleNamespace(commentary="wild-type, pH 8.0, 37°C")) is None


def test_the_unlabelled_rows_value_and_distance_are_said():
    because = ("1 unlabelled row(s) passed over for the same paper's row labelled wild-type under "
               "otherwise the same stated conditions (0.0204 mM)")
    record = SimpleNamespace(spread=None, resolver_because=because, reference_id="769319",
                             citation="BRENDA ref 769319", value=0.219)
    note = _wild_type_label_note(record)
    assert "0.0204 mM" in note and "11-fold from the value carried" in note


# -- R5A2-03: a range the carried paper gives is said -----------------------------------------

def test_a_range_of_the_carried_paper_is_found(monkeypatch):
    html = ('<a onclick="showTable(\'tab7\')">Turnover Numbers</a>'
            '<div id="tab7r1c0">88.2</div><div id="tab7r1c1">Z-Gly-Pro-Arg-p-nitroanilide</div>'
            '<div id="tab7r1c2">Homo sapiens</div><div id="tab7r1c3">-</div>'
            '<div id="tab7r1c4">wild type enzyme, at pH 8.0 and 20°C</div><div id="tab7r1c5">678332</div>'
            '<div id="tab7r2c0">20 - 50</div><div id="tab7r2c1">Z-Gly-Pro-Arg-p-nitroanilide</div>'
            '<div id="tab7r2c2">Homo sapiens</div><div id="tab7r2c3">-</div>'
            '<div id="tab7r2c4">wild type enzyme, at pH 8.0 and 20°C</div><div id="tab7r2c5">678332</div>')
    html = html.replace('<a onclick="showTable(\'tab7\')">', "showTable('tab7')\">")
    monkeypatch.setattr(defaults, "_page", lambda ec: html)
    found = defaults.ranges_of_paper("3.4.21.4", "kcat", "Homo sapiens", "678332")
    assert found == (("20 - 50", "Z-Gly-Pro-Arg-p-nitroanilide", "wild type enzyme, at pH 8.0 and 20°C"),)
    assert defaults.ranges_of_paper("3.4.21.4", "kcat", "Homo sapiens", "682760") == ()


# -- NEW-03: a paper set aside as a probable error is said ------------------------------------

def test_a_paper_set_aside_on_the_way_to_the_carried_row_is_said():
    from caterva.compose.narrowed import Narrowed, _row_of, carry

    clause = ("BRENDA ref 651313's row was not used: its Km (0.0022) lies 1.52e+03-fold from the "
              "median (3.35) of the 12 rows 6 other papers give, and only BRENDA ref 651985 comes "
              "near it: a probable error (a unit slip in the database, such as mM written for µM, "
              "looks like this), so that paper supplies neither constant")
    answer = Measurement(3.7, "mM", "BRENDA ref 4945", organism="Homo sapiens", commentary="aldolase B",
                         chosen_because="3.7 mM (BRENDA ref 4945) is the row ...; " + clause
                                        + "; the Km and kcat are one measurement")
    carried = Measurement(3.7, "mM", "BRENDA ref 4945", organism="Homo sapiens",
                          commentary="aldolase B",
                          chosen_because="the row for ALDOB, as your description asked")
    narrowed = Narrowed(measured={"reaction_Km": carried}, chosen={"reaction_Km": _row_of(answer)},
                        answers={"reaction_Km": answer})
    _, _, notes = carry({"reaction_Km": carried}, {}, narrowed, {}, "ALDOB")
    assert notes == [f"`reaction_Km`: {clause}"]


# -- NEW-09: organisms with no such protein listed are said apart in the advice ---------------

def test_organisms_with_no_listed_ortholog_are_said_apart(monkeypatch):
    from caterva.compose import __main__ as cli

    kcat = [_row("NAD+", "pH 8, 25°C", "1", "Rattus norvegicus", 2.0),
            _row("NAD+", "pH 8, 25°C", "2", "Aeromonas hydrophila", 30.0),
            _row("NAD+", "pH 8, 25°C", "3", "Streptomyces scabiei", 40.0)]
    _given(monkeypatch, {"kcat": kcat})
    monkeypatch.setattr(defaults, "organisms_with_isoform",
                        lambda ec, isoform: ("Homo sapiens", "Rattus norvegicus"))
    reason = ("no value in the organism requested -- available in: Rattus norvegicus, "
              "Aeromonas hydrophila, Streptomyces scabiei (searched under ...)")
    said = cli._available_elsewhere("2.4.2.30", "kcat", "NAD+", reason, isoform="PARP1")
    near, far = said.split("in organisms Caterva lists no PARP1 for")
    assert "Rattus norvegicus (1 row)" in near
    assert "Aeromonas hydrophila (1 row)" in far and "may be another protein altogether" in far


def test_a_range_of_any_paper_the_spread_counts_is_quoted(monkeypatch):
    from caterva.compose import __main__ as cli

    compound = "Z-Gly-Pro-Arg-p-nitroanilide"
    monkeypatch.setattr(defaults, "ranges_of_paper", lambda ec, table, organism, ref: (
        (("20 - 50", compound, "wild type enzyme, at pH 8.0 and 20°C"),) if ref == "678332" else ()))
    q = SimpleNamespace(parameter_id="reaction_kcat", table="kcat")
    model = SimpleNamespace(resolvable=(q,), compound_for=lambda _q: compound)
    m = Measurement(154.0, "1/s", "BRENDA ref 772843", organism="Homo sapiens",
                    alternatives=({"value": 154.0, "reference_id": "772843"},
                                  {"value": 88.2, "reference_id": "678332"}))
    (note,) = cli._ranges_left_out(model, {"reaction_kcat": m}, "3.4.21.4", "Homo sapiens")
    assert "BRENDA ref 678332, one of the papers whose values are counted above" in note
    assert "20 - 50 1/s" in note


# -- Review of the merge: what the analogue rule must not catch ---------------------------------

@pytest.mark.parametrize("name, parent", [
    ("2'-deoxycytidine", "cytidine"),          # deoxycytidine kinase's own substrate
    ("deoxythymidine", "thymidine"),
    ("2'-deoxyguanosine 5'-triphosphate", "guanosine 5'-triphosphate"),
    ("2-deoxy-D-ribose 5-phosphate", "D-ribose 5-phosphate"),
    ("carbamoyl phosphate", "acetyl phosphate"),  # "carba" inside a word is no carba analogue
])
def test_a_natural_deoxy_compound_is_no_synthetic_analogue(name, parent):
    assert defaults.analogue_of(name, [parent]) is None


@pytest.mark.parametrize("name, parent", [
    ("2-deoxy-D-glucose", "D-glucose"),
    ("6-phosphono-D-gluconate", "6-phospho-D-gluconate"),
    ("5a-carba-D-glucose", "D-glucose"),
    ("3'-fluoro-2'-deoxythymidine", "thymidine"),
])
def test_a_synthetic_analogue_is_still_read(name, parent):
    assert defaults.analogue_of(name, [parent]) == parent


def test_a_compound_of_the_enzymes_own_reaction_is_exempt():
    # Phosphoenolpyruvate mutase makes 3-phosphonopyruvate: by its name a
    # phosphonate copy of phosphoenolpyruvate, and the enzyme's own compound.
    own = defaults._own_reaction_compounds("5.4.2.9")
    assert defaults._group_key("3-phosphonopyruvate") in own
    assert defaults._group_key("6-phosphono-D-gluconate") not in defaults._own_reaction_compounds("1.1.1.44")
