"""The polish pass after the sixth adversarial round of the real-values work
(2026-11-14), the parts that are caterva's. Offline: rows are written here as
BRENDA writes them, and `defaults.table_rows` is replaced by them.

- the spread line said the row the model carries "is not carried";
- "tryptophan synthase from Salmonella typhimurium" was refused, then
  offered the same organism under its serovar name;
- ADH1B was read as retinol dehydrogenase and modelled on androsterone;
- "carboxylesterase 1", "beta-hexosaminidase A", "placental alkaline
  phosphatase", "nattokinase", "alcalase" and "MurA" (no organism) were not
  read;
- E. coli catalase's kcat was called a possible unit slip against one
  paper's 15 peroxidase-donor rows;
- bovine succinate dehydrogenase's malonate Ki, 70-fold below every other
  row and stating no conditions, was carried without a word.
"""
from __future__ import annotations

from types import SimpleNamespace

from caterva.bind.core import read_isoform, same_isoform
from caterva.compose import __main__ as main
from caterva.compose import defaults
from caterva.compose.organisms import normalise_organism
from caterva.compose.report import ModelDossier, _named_variant_notes, _passed_over_far, _stands_apart
from caterva.enzymes import finder


# -- The carried row is never called "not carried" ----------------------------------------

def _dossier(notes):
    return SimpleNamespace(model=SimpleNamespace(
        recognition=SimpleNamespace(composition=SimpleNamespace(notes=notes))))


def _spread(low, high, unit, carried_as):
    return SimpleNamespace(low=low, high=high, unit=unit, carried_as=carried_as)


def test_the_end_of_the_spread_that_is_carried_is_not_said_to_be_set_aside():
    # "CYP3A4 metabolising midazolam": carried 0.089 mM, the low end.
    notes = ["`reaction_Km`: the resolver's pick (0.008 mM) measured CYP1A1; the row for CYP3A4 "
             "(0.089 mM, BRENDA ref 706823) is used instead, as your description asked"]
    said = ModelDossier._end_set_aside(
        _dossier(notes), "reaction_Km",
        _spread(0.089, 0.131, "mM", "the row for CYP3A4, as your description asked"), 0.089)
    assert "is not carried" not in said
    # Aldolase B, carried 3.7 mM, the high end of 0.24 to 3.7.
    notes = ["`reaction_Km`: the resolver's pick (0.24 mM) named no isoform; the row for ALDOB "
             "(3.7 mM, BRENDA ref 4945) is used instead"]
    said = ModelDossier._end_set_aside(
        _dossier(notes), "reaction_Km",
        _spread(0.24, 3.7, "mM", "the row for ALDOB, as your description asked"), 3.7)
    assert "3.7 mM row is not carried" not in said


def test_the_end_that_was_set_aside_is_explained_once():
    notes = ["`reaction_Ki`: the resolver's pick (0.00035 mM, BRENDA ref 742064) states another mode; "
             "a row stating no inhibition mode (5.5e-05 mM, BRENDA ref 742446) is used instead"]
    said = ModelDossier._end_set_aside(
        _dossier(notes), "reaction_Ki", _spread(5.5e-05, 0.00035, "mM", "a row stating no mode"), 5.5e-05)
    assert said.count("is not carried") == 1
    assert said.startswith("the 0.00035 mM row is not carried")
    assert "5.5e-05 mM row is not carried" not in said


def test_passed_over_values_are_said_once_when_every_one_is_far():
    record = SimpleNamespace(value=0.219, unit="mM", chosen_because=None, resolver_because=(
        "0.219 mM is the row; of the 3 candidate rows (after the checks): 1 unlabelled row(s) passed "
        "over for the same paper's row labelled wild-type under otherwise the same stated conditions "
        "(0.0204 mM)"))
    for line in _passed_over_far(record):
        assert line.count("0.0204") <= 1, line


def test_a_carried_row_below_every_far_row_is_said_to_stand_apart():
    record = SimpleNamespace(value=90.0, unit="1/s")
    said = _stands_apart(record, ["3 row(s) not stating both pH and temperature passed over, 2 of "
                                 "them more than 3-fold from it (400, 620 1/s)"])
    assert "higher than the carried value" in said and "stands apart" in said
    assert _stands_apart(record, ["2 row(s) passed over, all more than 3-fold from it (12, 620 1/s)"]) == ""
    assert _stands_apart(record, ["1 row(s) passed over, all more than 3-fold from it (620 1/s)"]) == ""


# -- An organism under its current name ---------------------------------------------------

def _row(compound, organism, conditions="", value=1.0, ref="1", **more):
    return defaults._Row(compound, organism, conditions, value=value, reference_id=ref, **more)


def test_salmonella_typhimurium_is_read_as_the_serovar(monkeypatch):
    serovar = "Salmonella enterica subsp. enterica serovar Typhimurium"
    assert normalise_organism("S. typhimurium")[0] == serovar
    rows = (_row("L-serine", serovar), _row("indole", serovar), _row("L-serine", "Escherichia coli"))
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, organism: tuple(
        r for r in rows if organism is None or r.organism == organism))
    monkeypatch.setattr(defaults, "km_organisms", lambda ec, substrate=None: {serovar: 2, "Escherichia coli": 1})
    choice = main._filed_under_longer_name("4.2.1.20", "Salmonella typhimurium")
    assert choice is not None and choice.chosen == serovar
    assert "Salmonella typhimurium" in choice.note() and serovar in choice.note()
    # An organism with rows of its own, or with no longer name on the page, is left alone.
    assert main._filed_under_longer_name("4.2.1.20", "Escherichia coli") is None
    assert main._filed_under_longer_name("4.2.1.20", "Bacillus subtilis") is None


# -- Names people type ---------------------------------------------------------------------

def test_adh1b_is_alcohol_dehydrogenase_and_its_rows_are_beta1():
    for typed in ("ADH1B", "alcohol dehydrogenase 1B"):
        found = finder.resolve(typed)
        assert getattr(found, "ec", None) == "1.1.1.1", typed
        assert found.isoform == "ADH1B"
    assert same_isoform(read_isoform("isoenzyme beta1,beta1, 0.1 M sodium phosphate buffer, pH 7.5"), "ADH1B")
    # The allelic variants and a heterodimer are not the reference enzyme.
    assert not same_isoform(read_isoform("isoenzyme beta2,beta2"), "ADH1B")
    assert read_isoform("isoenzyme alpha,gamma1") == "alpha,gamma1"
    assert not same_isoform(read_isoform("isoenzyme beta1,gamma1"), "ADH1B")


def test_isozymes_and_trade_names_written_in_words_are_read():
    for typed, ec, isoform in (("carboxylesterase 1", "3.1.1.1", "CES1"),
                               ("beta-hexosaminidase A", "3.2.1.52", "HEXA"),
                               ("placental alkaline phosphatase", "3.1.3.1", "ALPP"),
                               ("creatine kinase MB", "2.7.3.2", None),
                               ("nattokinase", "3.4.21.62", None),
                               ("alcalase", "3.4.21.62", None)):
        found = finder.resolve(typed)
        assert getattr(found, "ec", None) == ec, typed
        assert found.isoform == isoform, typed


def test_a_gene_one_organism_has_is_read_without_the_organism():
    found = finder.resolve("MurA")
    assert getattr(found, "ec", None) == "2.5.1.7"
    assert found.organism == "Escherichia coli"
    assert any("Escherichia coli" in note for note in found.notes)


# -- A mutant's rows ------------------------------------------------------------------------

def test_the_allelic_combination_is_not_counted_as_the_mutant(monkeypatch):
    allelic = "allelic combination wild-type/mutant R408W, Vmax: 0.7 micromol/min/mg, pH 6.8, 37°C"
    rows = (_row("L-Phe", "Homo sapiens", allelic, value=3.0, ref="712843"),
            _row("(6R)-L-erythro-5,6,7,8-tetrahydrobiopterin", "Homo sapiens", "mutant R408W, pH 7.0",
                 value=0.035, ref="699374"),
            _row("L-Phe", "Homo sapiens", "wild-type, pH 6.8", value=0.3, ref="712843"))
    kept, left = defaults._of_mutant(rows, "R408W")
    assert [r.value for r in kept] == [0.035] and left == 2
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, organism: rows if table == "km" else ())
    mixed = defaults.mixed_rows_of_mutant("1.14.16.1", "Homo sapiens", "R408W")
    assert [r.value for r in mixed] == [3.0]
    args = SimpleNamespace(mutation="R408W", organism="Homo sapiens")
    note = main._mixed_mutant_note("1.14.16.1", args, ("km", "kcat"))
    assert note and "together with the wild type" in note and "712843" in note
    # The advice for the mutant's missing kcat offers nothing a run would refuse.
    said = main._what_the_mutant_holds("1.14.16.1", "kcat", "L-Phe", "Homo sapiens", "R408W")
    assert "supply it yourself" in said and "--organism" not in said and "--substrate" not in said


# -- Outliers: who is compared with whom ----------------------------------------------------

def _model(table, compound, parameter="reaction_kcat", isoform=None):
    q = SimpleNamespace(parameter_id=parameter, table=table)
    return SimpleNamespace(resolvable=(q,), compound_for=lambda _q: compound, isoform=isoform)


def test_catalase_is_not_an_outlier_among_one_papers_peroxidase_rows(monkeypatch):
    organism = "Escherichia coli"
    rows = [_row("H2O2", organism, "wild-type, pH 7.0, 23°C", value=11000.0, ref="688196")]
    rows += [_row("H2O2", organism, f"presence of ABTS, pH {4 + i * 0.1:.1f}", value=11.0 + 10 * i, ref="685401")
             for i in range(15)]
    rows += [_row("H2O2", organism, "", value=16300.0, ref="439802"),
             _row("H2O2", organism, "catalase activity, pH 7.0, 22°C", value=18000.0, ref="654365"),
             _row("H2O2", organism, "", value=200.0, ref="726446")]
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, org: tuple(rows))
    measured = {"reaction_kcat": SimpleNamespace(value=11000.0, unit="1/s", reference_id="688196",
                                                 citation="BRENDA ref 688196")}
    assert main._far_from_other_papers(_model("kcat", "H2O2"), measured, "1.11.1.6", organism) == []


def test_a_lone_row_far_from_papers_that_agree_with_each_other_is_still_said(monkeypatch):
    organism = "Homo sapiens"
    rows = [_row("fructose 1-phosphate", organism, "wild-type enzyme, 22°C", value=0.0022, ref="651313"),
            _row("fructose 1-phosphate", organism, "", value=0.24, ref="649476"),
            _row("fructose 1-phosphate", organism, "aldolase B", value=3.7, ref="4945"),
            _row("fructose 1-phosphate", organism, "", value=2.0, ref="4946")]
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, org: tuple(rows))
    measured = {"reaction_Km": SimpleNamespace(value=0.0022, unit="mM", reference_id="651313",
                                               citation="BRENDA ref 651313")}
    notes = main._far_from_other_papers(_model("km", "fructose 1-phosphate", "reaction_Km"), measured,
                                        "4.1.2.13", organism)
    assert len(notes) == 1 and "over the 3 other papers" in notes[0]


def test_the_only_ki_row_stating_nothing_and_far_outside_the_range_is_said(monkeypatch):
    rows = (_row("malonate", "Bos taurus", "", value=0.00025, ref="391123"),
            _row("malonate", "Escherichia coli", "mutant E49A, pH 7.0, 30°C", value=0.005, ref="674532"),
            _row("malonate", "Vigna radiata", "", value=0.0218, ref="391114"),
            _row("malonate", "Glycine max", "", value=0.0246, ref="391114"),
            _row("malonate", "Escherichia coli", "wild-type, pH 7.0, 30°C", value=0.025, ref="674532"),
            _row("malonate", "Bacillus cereus", "pH 7.6, 30°C", value=0.088, ref="707949"),
            _row("malonate", "Mammalia", "", value=0.018, ref="391153"))
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, org: tuple(
        r for r in rows if org is None or r.organism == org))
    measured = {"reaction_Ki": SimpleNamespace(value=0.00025, unit="mM")}
    notes = main._far_from_other_organisms(_model("ki", "malonate", "reaction_Ki"), measured,
                                           "1.3.5.1", "Bos taurus")
    assert len(notes) == 1
    assert "the only Ki row" in notes[0] and "outside the whole range" in notes[0]
    assert "difference between species" in notes[0]
    # The same row with its conditions stated, or nearer the range, is not flagged this way.
    near = {"reaction_Ki": SimpleNamespace(value=0.004, unit="mM")}
    assert main._far_from_other_organisms(_model("ki", "malonate", "reaction_Ki"), near,
                                          "1.3.5.1", "Bos taurus") == []


def test_an_allozyme_or_a_single_product_is_said_of_the_carried_row():
    row = SimpleNamespace(commentary="allozyme D, pH 7.5, 37°C, in presence of Mg2+ and Zn2+")
    assert any("allozyme D" in n for n in _named_variant_notes(row))
    row = SimpleNamespace(commentary="pH 7.5, 25°C, HPLC analysis, 8-HETE formation")
    assert any("8-HETE" in n for n in _named_variant_notes(row))
    assert _named_variant_notes(SimpleNamespace(commentary="wild-type, pH 7.5")) == []
