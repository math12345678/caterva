"""A placeholder's reason, and "Do this next", name the thing actually missing.

WHY THESE TESTS
---------------
The round-1 review of ADR 0182 ran the advice the reports gave, and much of
it led nowhere:

* A Ki placeholder said "BRENDA has no row for that substrate name here ...
  Re-run with --substrate", for donepezil on human acetylcholinesterase and
  celecoxib on COX-2. A Ki is filed under the INHIBITOR; --substrate cannot
  change it, and the list printed was BRENDA's inhibitors in every organism.
* A human kcat placeholder for CYP3A4 listed Bacillus fatty acids to pass as
  --substrate, while BRENDA has no human Turnover row on that page at all:
  the organism was the blocker.
* "citrate synthase --organism mouse" was told to re-run with --subject
  2.3.3.1, which was refused again: no candidate has a mouse Km row.
* "glucokinase in human" was pointed at Zymomonas mobilis, while human
  glucokinase (GCK) is filed under EC 2.7.1.1.
* A failed read of BRENDA's substrate list dropped "mannose", and the
  chooser then modelled D-glucose under "No substrate was named".
* "pepsin with hemoglobin" was built as cooperative binding, pepsin unused.

Offline throughout: BRENDA's rows are stand-ins given to `defaults.table_rows`,
and the enzyme finder reads its committed index.
"""
from __future__ import annotations

import argparse
import io
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Dict, Optional

import pytest

import caterva.compose.__main__ as cli
from caterva.agents.adapters import name_miss_clause, to_parameter_source
from caterva.compose import defaults
from caterva.compose.verdict import _what_would_ground
from caterva.enzymes.sentence import read_sentence


def _rows(spec):
    """{(table, organism): [(compound, n)]} -> a `table_rows` stand-in."""
    def table_rows(ec, table, organism):
        out = []
        for (t, o), compounds in spec.items():
            if t != table or (organism is not None and o != organism):
                continue
            for compound, n in compounds:
                out.extend(defaults._Row(compound, o, "") for _ in range(n))
        return tuple(out)
    return table_rows


@dataclass
class _Q:
    parameter_id: str
    table: str
    primary: bool = True
    ligand_role: str = "substrate"


@dataclass
class _Model:
    resolvable: tuple
    substrate: Optional[str] = None
    inhibitor: Optional[str] = None
    isoform: Optional[str] = None
    compounds: Dict[str, str] = field(default_factory=dict)

    def compound_for(self, q):
        return self.inhibitor if q.table == "ki" else self.substrate


# ---------------------------------------------------------------------------
# The adapter's clause: a Ki names the inhibitor and --inhibitor
# ---------------------------------------------------------------------------


def test_a_ki_name_miss_names_the_inhibitor_and_its_flag():
    result = SimpleNamespace(found=False, source="literature_candidates",
                             substrates_available=["indomethacin", "nimesulide"])
    _, reason = to_parameter_source("reaction_Ki", result)
    assert "--inhibitor" in reason and "--substrate" not in reason
    assert "no Ki row for that inhibitor name" in reason
    assert "in any organism" in reason
    # The papers are what PubMed returned for the words, not papers about it.
    assert "not checked to name the compound" in reason


def test_a_km_or_kcat_name_miss_still_names_the_substrate():
    assert "--substrate" in name_miss_clause("kcat", ["D-glucose"])
    result = SimpleNamespace(found=False, source="not_found", substrates_available=["D-glucose"])
    _, reason = to_parameter_source("reaction_Km", result, "km")
    assert "no Km row for that substrate name" in reason and "--inhibitor" not in reason


# ---------------------------------------------------------------------------
# Compose says it for the organism searched
# ---------------------------------------------------------------------------


def _clause(table, compound, role):
    return name_miss_clause(table, ["somewhere-else-1", "somewhere-else-2"])


def test_an_organism_with_no_row_of_the_table_is_named_as_the_blocker(monkeypatch):
    """CYP3A4, human kcat: no human Turnover row at all on EC 1.14.14.1."""
    monkeypatch.setattr(defaults, "table_rows", _rows({
        ("kcat", "Priestia megaterium"): [("linoleic acid", 20)],
        ("kcat", "Bacillus licheniformis"): [("hexadecanoic acid", 9)],
        ("km", "Homo sapiens"): [("7-ethoxyresorufin", 2)],
    }))
    model = _Model((_Q("reaction_kcat", "kcat"),), substrate="7-ethoxyresorufin")
    reason = "nothing found in BRENDA or the literature search" + _clause("kcat", None, "substrate")
    out = cli._said_for_the_organism(model, {"reaction_kcat": reason}, "1.14.14.1", "human")
    said = out["reaction_kcat"]
    assert "holds no kcat row for EC 1.14.14.1 in Homo sapiens at all" in said
    assert "the organism is what is missing" in said
    assert "Priestia megaterium (20 rows)" in said and "--organism" in said
    # Bacillus fatty acids are no longer offered as a --substrate fix.
    assert "--substrate" not in said
    step = _what_would_ground(SimpleNamespace(not_found=out), ["reaction_kcat"])
    assert "--organism" in step and "--substrate" not in step


def test_a_ki_for_an_inhibitor_without_a_row_lists_the_inhibitors_there(monkeypatch):
    """donepezil on human AChE: tacrine and others have human Ki rows; donepezil none anywhere."""
    monkeypatch.setattr(defaults, "table_rows", _rows({
        ("ki", "Homo sapiens"): [("tacrine", 3), ("edrophonium", 2)],
        ("ki", "Mus musculus"): [("huperzine A", 1)],
    }))
    model = _Model((_Q("reaction_Ki", "ki", primary=False, ligand_role="regulator"),),
                   substrate="acetylthiocholine", inhibitor="donepezil")
    reason = "no database value" + _clause("ki", "donepezil", "inhibitor")
    out = cli._said_for_the_organism(model, {"reaction_Ki": reason}, "3.1.1.7", "Homo sapiens")
    said = out["reaction_Ki"]
    assert "no Ki row for donepezil under EC 3.1.1.7 in Homo sapiens" in said
    assert "tacrine (3 rows); edrophonium (2 rows)" in said
    assert "Re-run with --inhibitor set to one of them" in said
    assert "--substrate" not in said
    assert "in any organism under that name" in said
    step = _what_would_ground(SimpleNamespace(not_found=out), ["reaction_Ki"])
    assert "--inhibitor set to one the provenance table lists" in step
    # It WAS looked up; the old step said "so reaction_Ki is looked up".
    assert "is looked up" not in step


def test_an_inhibitor_measured_only_elsewhere_is_labelled_as_elsewhere(monkeypatch):
    monkeypatch.setattr(defaults, "table_rows", _rows({
        ("ki", "Homo sapiens"): [("nimesulide", 3)],
        ("ki", "Mus musculus"): [("celecoxib", 2)],
    }))
    model = _Model((_Q("reaction_Ki", "ki"),), inhibitor="celecoxib")
    out = cli._said_for_the_organism(model, {"reaction_Ki": "x" + _clause("ki", "celecoxib", "inhibitor")},
                                     "1.14.99.1", "Homo sapiens")
    said = out["reaction_Ki"]
    assert "celecoxib has Ki rows in other organisms only: Mus musculus (2 rows)" in said
    assert "never substituted for yours" in said


def test_with_no_organism_the_resolvers_clause_stands():
    reason = "x" + _clause("ki", "donepezil", "inhibitor")
    model = _Model((_Q("reaction_Ki", "ki"),), inhibitor="donepezil")
    assert cli._said_for_the_organism(model, {"reaction_Ki": reason}, "3.1.1.7", None) == {"reaction_Ki": reason}


def test_an_isoform_refusal_names_the_compounds_measured_on_that_isoform(monkeypatch):
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, organism: (
        defaults._Row("fenthion", organism, "CYP3A4, recombinant"),
        defaults._Row("7-ethoxyresorufin", organism, "CYP1A1"),
    ))
    model = _Model((_Q("reaction_Km", "km"),), substrate="7-ethoxyresorufin", isoform="CYP3A4")
    reason = ("every row BRENDA holds for this constant measured another isoform than the one asked "
              "for -- the rows measured: CYP1A1")
    out = cli._said_for_the_organism(model, {"reaction_Km": reason}, "1.14.14.1", "Homo sapiens")
    assert "with Km rows naming CYP3A4 under EC 1.14.14.1 in Homo sapiens: fenthion (1 row)" in out["reaction_Km"]
    step = _what_would_ground(SimpleNamespace(not_found=out), ["reaction_Km"])
    assert "another isoform" in step and "--organism" not in step


def test_an_all_placeholder_model_gets_the_remedy_its_reasons_name():
    """CYP3A4 and luciferase: nothing measured, and the step was "--organism" for both."""
    from caterva.compose.verdict import _provenance_concerns

    model = SimpleNamespace(
        subject="1.14.14.1", measured={}, unmeasured=("reaction_Km",), placeholders=("reaction_Km",),
        resolvable=(SimpleNamespace(table="km"),), searched=True,
        not_found={"reaction_Km": "withheld: the value the search returned is BRENDA's row for "
                                  "D-luciferin -- another compound's value is never carried under this one's"})
    concerns, _ = _provenance_concerns(model)
    remedy = " ".join(c.remedy for c in concerns)
    assert "--organism" not in remedy and "another compound's" in remedy


# ---------------------------------------------------------------------------
# A name refused as several enzymes, with an organism none of them has
# ---------------------------------------------------------------------------


def test_a_refused_name_says_when_no_candidate_has_the_organism(monkeypatch):
    monkeypatch.setattr(defaults, "table_rows", _rows({("km", "Homo sapiens"): [("acetyl-CoA", 8)]}))
    monkeypatch.setattr(defaults, "km_organisms", lambda ec, substrate=None: {"Homo sapiens": 8})
    reading = read_sentence("citrate synthase Michaelis-Menten", organism="Mus musculus")
    assert reading.ambiguity is not None
    said = cli._no_candidate_in_the_organism(reading.ambiguity, "mouse")
    assert "has a Km row in Mus musculus" in said and "the organism, not the enzyme name" in said
    assert "Homo sapiens (8 rows)" in said


def test_a_refused_name_names_the_candidates_that_have_the_organism(monkeypatch):
    def rows(ec, table, organism):
        return (defaults._Row("acetyl-CoA", organism, ""),) if ec == "2.3.3.1" else ()
    monkeypatch.setattr(defaults, "table_rows", rows)
    reading = read_sentence("citrate synthase Michaelis-Menten", organism="Mus musculus")
    said = cli._no_candidate_in_the_organism(reading.ambiguity, "Mus musculus")
    assert said.startswith("Of these, the ones with Km rows in Mus musculus are EC 2.3.3.1 (1 row)")


# ---------------------------------------------------------------------------
# glucokinase: the human protein is filed under another EC number
# ---------------------------------------------------------------------------


def test_the_organisms_protein_under_another_ec_is_the_first_remedy(monkeypatch):
    def rows(ec, table, organism):
        return (defaults._Row("D-glucose", organism, ""),) * 159 if ec == "2.7.1.1" else ()
    monkeypatch.setattr(defaults, "table_rows", rows)
    monkeypatch.setattr(defaults, "km_organisms", lambda ec, substrate=None: {"Zymomonas mobilis": 21})
    said = cli._organism_has_no_rows("2.7.1.2", "Homo sapiens", "glucokinase")
    assert "'glucokinase' is the protein GCK" in said
    assert "re-run with --subject 2.7.1.1 --isoform GCK" in said
    assert said.index("--subject 2.7.1.1") < said.index("Zymomonas mobilis")


def test_a_word_inside_a_longer_protein_name_is_not_that_protein(monkeypatch):
    """ADPGK is "ADP-dependent glucokinase": not what "glucokinase" names."""
    monkeypatch.setattr(defaults, "table_rows",
                        lambda ec, table, organism: (defaults._Row("x", organism, ""),) if ec == "2.7.1.147" else ())
    assert cli._filed_under_another_ec("2.7.1.2", "Homo sapiens", "glucokinase") is None


# ---------------------------------------------------------------------------
# A substrate word survives a failed read of BRENDA's list
# ---------------------------------------------------------------------------


def _args(**fields):
    base = {"description": "", "subject": None, "organism": None, "substrate": None, "inhibitor": None}
    base.update(fields)
    return argparse.Namespace(**base)


def test_a_failed_read_is_retried_before_a_word_is_given_up(monkeypatch):
    answers = [None, {"D-mannose": 9, "D-glucose": 25}]
    monkeypatch.setattr(cli, "brenda_km_substrates", lambda ec, org: answers.pop(0))
    monkeypatch.setattr(cli, "SUBSTRATE_LIST_PAUSE", 0)
    args = _args(description="hexokinase with mannose in human")
    cli.read_description(args, err=io.StringIO())
    assert args.substrate == "D-mannose"


def test_a_word_that_could_not_be_checked_is_never_replaced_by_a_choice(monkeypatch):
    """The chooser read the page a moment later and modelled D-glucose,
    saying "No substrate was named"; now the search refuses instead."""
    monkeypatch.setattr(cli, "brenda_km_substrates", lambda ec, org: None)
    monkeypatch.setattr(cli, "SUBSTRATE_LIST_PAUSE", 0)
    monkeypatch.setattr(cli, "_organism_has_no_rows", lambda *a, **k: None)
    chose = []
    monkeypatch.setattr(defaults, "choose_substrate", lambda *a, **k: chose.append(a))
    args = _args(description="hexokinase with mannose in human")
    read = cli.read_description(args, err=io.StringIO())
    assert args.substrate is None
    assert any("could not be read" in n and "'mannose'" in n for n in read.notes)
    from caterva.compose.pipeline import compose

    model = compose(read.description, subject=args.subject, organism=args.organism)
    _, refusal = cli._choose_what_was_not_named(model, args)
    assert refusal and "'mannose'" in refusal and "no other substrate is chosen" in refusal
    assert chose == []


# ---------------------------------------------------------------------------
# "pepsin with hemoglobin" is an enzyme and its substrate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("description, rule", [
    ("pepsin with hemoglobin", "michaelis_menten"),
    ("pepsin with haemoglobin in pig", "michaelis_menten"),
    # A mechanism said in other words stands.
    ("hexokinase with glucose with a competitive inhibitor", "competitive_inhibition"),
    # No enzyme named: hemoglobin is the cooperative protein.
    ("cooperative binding of oxygen to hemoglobin", "cooperative_binding"),
])
def test_a_compound_beside_a_named_enzyme_is_not_a_mechanism(description, rule):
    reading = read_sentence(description)
    _, got, note = cli._shape_from(description, reading)
    assert got == rule
    if rule == "michaelis_menten":
        assert "read as a compound the enzyme acts on" in note


# ---------------------------------------------------------------------------
# An organism or compound is offered only when the search would use its rows
# ---------------------------------------------------------------------------


def _variant_rows(spec):
    """{(table, organism): [(compound, n, conditions)]} -> a `table_rows` stand-in."""
    def table_rows(ec, table, organism):
        out = []
        for (t, o), compounds in spec.items():
            if t != table or (organism is not None and o != organism):
                continue
            for compound, n, conditions in compounds:
                out.extend(defaults._Row(compound, o, conditions) for _ in range(n))
        return tuple(out)
    return table_rows


def test_an_organism_whose_rows_are_all_variants_is_not_offered(monkeypatch):
    """PTGS2, human kcat: the three mouse rows on EC 1.14.99.1 all measured
    COX-2 N580A, and "re-run with --organism Mus musculus" came back with
    placeholders again."""
    monkeypatch.setattr(defaults, "table_rows", _variant_rows({
        ("kcat", "Mus musculus"): [("arachidonate", 3, "pH 8.0, 25°C, COX-2 mutant N580A")],
        ("km", "Homo sapiens"): [("arachidonic acid", 9, "")],
    }))
    model = _Model((_Q("reaction_kcat", "kcat"),), substrate="arachidonic acid")
    reason = "nothing found in BRENDA or the literature search" + _clause("kcat", None, "substrate")
    out = cli._said_for_the_organism(model, {"reaction_kcat": reason}, "1.14.99.1", "Homo sapiens")
    said = out["reaction_kcat"]
    assert "Mus musculus" not in said and "--organism" not in said
    assert "measured a protein variant" in said and "supply it yourself" in said
    step = _what_would_ground(SimpleNamespace(not_found=out), ["reaction_kcat"])
    assert "--organism" not in step and "another organism" not in step
    assert step.startswith("supply reaction_kcat yourself")


def test_variant_rows_are_left_out_of_the_organisms_listed(monkeypatch):
    monkeypatch.setattr(defaults, "table_rows", _variant_rows({
        ("kcat", "Priestia megaterium"): [("linoleic acid", 19, "mutant F87A"), ("linoleic acid", 1, "")],
        ("kcat", "Bacillus subtilis"): [("hexadecanoic acid", 3, "wild-type")],
        ("kcat", "Streptomyces sp."): [("avermectin", 2, "mutant R73A")],
    }))
    model = _Model((_Q("reaction_kcat", "kcat"),), substrate="7-ethoxyresorufin")
    reason = "x" + _clause("kcat", None, "substrate")
    said = cli._said_for_the_organism(model, {"reaction_kcat": reason}, "1.14.14.1", "Homo sapiens")["reaction_kcat"]
    assert "Bacillus subtilis (3 rows); Priestia megaterium (1 row)" in said
    assert "Streptomyces" not in said
    assert "the organism is what is missing" in said


def test_an_organism_with_only_variant_rows_is_named_as_the_blocker_truthfully(monkeypatch):
    monkeypatch.setattr(defaults, "table_rows", _variant_rows({
        ("kcat", "Homo sapiens"): [("arachidonate", 2, "mutant L531A")],
        ("kcat", "Ovis aries"): [("arachidonate", 4, "")],
    }))
    model = _Model((_Q("reaction_kcat", "kcat"),), substrate="arachidonate")
    said = cli._said_for_the_organism(model, {"reaction_kcat": "x" + _clause("kcat", None, "substrate")},
                                      "1.14.99.1", "Homo sapiens")["reaction_kcat"]
    # Not "holds no kcat row ... at all": it holds two, of a mutant.
    assert "at all" not in said and "all measured a protein variant" in said
    assert "Ovis aries (4 rows)" in said


def test_a_cross_species_list_of_variant_rows_only_is_not_advice(monkeypatch):
    """COX-2 and celecoxib, human: the arachidonate kcat was "available in:
    Mus musculus", whose one row is the N580A mutant's."""
    monkeypatch.setattr(defaults, "table_rows", _variant_rows({
        ("kcat", "Mus musculus"): [("arachidonate", 1, "COX-2 mutant N580A")],
    }))
    model = _Model((_Q("reaction_kcat", "kcat"),), substrate="arachidonate")
    reason = ("no value in the organism requested; measurements exist in other organisms, and one is "
              "never substituted for yours (ADR 0024) -- re-run with --organism set to one of them to "
              "build the model there -- available in: Mus musculus (searched under the requirement that "
              "organism must be Homo sapiens, raised by your own request)")
    said = cli._said_for_the_organism(model, {"reaction_kcat": reason}, "1.14.99.1", "Homo sapiens")["reaction_kcat"]
    assert "--organism" not in said and "measured a protein variant" in said
    assert said.endswith("(searched under the requirement that organism must be Homo sapiens, raised by "
                         "your own request)")
    step = _what_would_ground(SimpleNamespace(not_found={"reaction_kcat": said}), ["reaction_kcat"])
    assert "--organism" not in step


def test_a_cross_species_list_keeps_only_the_organisms_with_usable_rows(monkeypatch):
    monkeypatch.setattr(defaults, "table_rows", _variant_rows({
        ("kcat", "Mus musculus"): [("arachidonate", 1, "mutant N580A")],
        ("kcat", "Ovis aries"): [("arachidonate", 2, "")],
    }))
    model = _Model((_Q("reaction_kcat", "kcat"),), substrate="arachidonate")
    reason = "no value in the organism requested -- available in: Mus musculus, Ovis aries"
    said = cli._said_for_the_organism(model, {"reaction_kcat": reason}, "1.14.99.1", "Homo sapiens")["reaction_kcat"]
    assert "available in: Ovis aries (2 rows)" in said
    assert "withheld: Mus musculus (1 row)" in said


def test_a_cross_species_list_with_usable_rows_everywhere_stands(monkeypatch):
    monkeypatch.setattr(defaults, "table_rows", _variant_rows({
        ("kcat", "Ovis aries"): [("arachidonate", 2, "")],
    }))
    model = _Model((_Q("reaction_kcat", "kcat"),), substrate="arachidonate")
    reason = "no value in the organism requested -- available in: Ovis aries"
    assert cli._said_for_the_organism(model, {"reaction_kcat": reason}, "1.14.99.1",
                                      "Homo sapiens") == {"reaction_kcat": reason}


def test_an_organism_refusal_lists_only_organisms_with_usable_km_rows(monkeypatch):
    monkeypatch.setattr(defaults, "table_rows", _variant_rows({
        ("km", "Zymomonas mobilis"): [("D-glucose", 2, "")],
        ("km", "Escherichia coli"): [("D-glucose", 3, "mutant D72A")],
    }))
    monkeypatch.setattr(defaults, "km_organisms",
                        lambda ec, substrate=None: {"Zymomonas mobilis": 2, "Escherichia coli": 3})
    said = cli._organism_has_no_rows("2.7.1.2", "Homo sapiens")
    assert "Zymomonas mobilis (2 rows)" in said and "Escherichia coli" not in said


def test_the_ambiguity_refusal_and_the_organism_sentence_are_two_sentences(monkeypatch):
    """The refusal ends on its example command; "... --subject 2.3.3.1 None of ..." ran on."""
    monkeypatch.setattr(cli, "_no_candidate_in_the_organism", lambda *a, **k: "None of them has a row.")
    args = _args(description="citrate synthase Michaelis-Menten", organism="mouse")
    read = cli.read_description(args, err=io.StringIO())
    refusal = str(getattr(read, "name_refusal", "") or "")
    assert "None of them has a row." in refusal
    before = refusal[:refusal.index("None of them")].rstrip()
    assert before.endswith((".", "!", "?", ")"))
