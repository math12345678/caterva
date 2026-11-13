"""The fifth adversarial round of the real-values work (2026-11-12), the
advice and notes half: what a placeholder tells the reader to do, and what
each note says the row measured. Offline: BRENDA's tables are stubbed as
rows (`defaults.table_rows`), never fetched.

Each test names the review finding it holds to.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from caterva.compose import __main__ as compose_main
from caterva.compose import defaults, verdict
from caterva.compose.isoform import PAIRED_ACROSS_TIERS, select_isoform
from caterva.compose.report import _other_conditions, _wild_type_label_note
from caterva.compose.row_scope import IRREVERSIBLE, read_scope
from caterva.enzymes.isozyme import IsozymeNotice


def _stub(monkeypatch, tables, natural=()):
    """`defaults.table_rows` answering from `tables`: {(table, organism):
    [(compound, n, variant)]}; an organism of None asks for every one."""

    def table_rows(ec, table, organism):
        out = []
        for (t, org), entries in tables.items():
            if t != table or (organism is not None and org != organism):
                continue
            for name, n, variant in entries:
                out += [defaults._Row(name, org, "pH 7.5, 25°C", value=1.0, reference_id=str(700000 + i),
                                      variant=variant) for i in range(n)]
        return tuple(out)

    monkeypatch.setattr(defaults, "table_rows", table_rows)
    keyed = frozenset(defaults._key(n) for n in natural)
    monkeypatch.setattr(defaults, "_reaction_compounds", lambda ec: (keyed, keyed))


def _model(*quantities, isoform=None):
    return SimpleNamespace(
        resolvable=[SimpleNamespace(parameter_id=p, table=t, motif_name=m) for p, t, m in quantities],
        isoform=isoform, substrate="acetyl-CoA")


# -- N11: no inhibitor could fill a Ki the organism has no row for ---------------------

def test_a_ki_with_no_row_in_the_organism_names_the_organisms_not_an_inhibitor(monkeypatch):
    """Rat acetyl-CoA carboxylase: no Ki row for any inhibitor in rat. The
    reason said "Name it with --inhibitor NAME"; it now says the organism is
    what is missing, and lists first the organism where the whole model is
    measured (human), before E. coli, which has more Ki rows and no kcat."""
    _stub(monkeypatch, {
        ("ki", "Escherichia coli"): [("heparin", 6, False)],
        ("ki", "Homo sapiens"): [("palmitoyl-CoA", 2, False)],
        ("km", "Homo sapiens"): [("acetyl-CoA", 3, False)],
        ("kcat", "Homo sapiens"): [("acetyl-CoA", 3, False)],
        ("km", "Escherichia coli"): [("acetyl-CoA", 3, False)],
        ("km", "Rattus norvegicus"): [("acetyl-CoA", 5, False)],
        ("kcat", "Rattus norvegicus"): [("acetyl-CoA", 1, False)],
    })
    model = _model(("reaction_Ki", "ki", "uncompetitive"), ("reaction_Km", "km", "mm"),
                   ("reaction_kcat", "kcat", "mm"))
    skipped = {"reaction_Ki": "not looked up: this is the inhibitor's constant (port I) ... "
                              "Name it with --inhibitor NAME (or --compound I=NAME)"}
    out = compose_main._no_inhibitor_would_fill(model, skipped, "6.4.1.2", "rat")
    reason = out["reaction_Ki"]
    assert "--inhibitor NAME" not in reason
    assert "the organism is what is missing" in reason and "naming an inhibitor" in reason
    assert reason.index("Homo sapiens") < reason.index("Escherichia coli")
    assert "whole model is measured" in reason
    # The verdict's step names them, so the advice can be followed as read.
    step = verdict._what_would_ground(SimpleNamespace(not_found={"reaction_Ki": reason}), ["reaction_Ki"])
    assert "--organism set to one of Homo sapiens (2 rows)" in step


def test_a_ki_is_left_alone_where_the_organism_has_ki_rows(monkeypatch):
    _stub(monkeypatch, {("ki", "Rattus norvegicus"): [("soraphen A", 1, False)]})
    model = _model(("reaction_Ki", "ki", "uncompetitive"))
    skipped = {"reaction_Ki": "not looked up: ... Name it with --inhibitor NAME"}
    assert compose_main._no_inhibitor_would_fill(model, skipped, "6.4.1.2", "Rattus norvegicus") == {}


# -- A4-08: the verdict names the organisms and the inhibitors it offers ----------------

def test_the_verdict_names_where_a_ki_is_measured_and_the_inhibitors_here():
    reason = ("no value in the organism requested; measurements exist in other organisms, and one "
              "is never substituted for yours (ADR 0024) -- re-run with --organism set to one of them "
              "to build the model there -- available in: Mus musculus (2 rows); Tetronarce "
              "californica (1 row) (searched under the requirement that organism must be Homo "
              "sapiens, raised by your own request). In Homo sapiens, the inhibitors with Ki rows the "
              "search can use for a competitive model, best measured first: tacrine (3 rows); "
              "edrophonium (2 rows); re-run with --inhibitor set to one of them to model that "
              "inhibitor in this organism instead")
    step = verdict._what_would_ground(SimpleNamespace(not_found={"reaction_Ki": reason}), ["reaction_Ki"])
    assert "--organism set to one of Mus musculus (2 rows); Tetronarce californica (1 row)" in step
    assert "--inhibitor set to one this organism has Ki rows for (tacrine (3 rows); edrophonium" in step
    assert "one the provenance table lists" not in step


def test_the_inhibitors_offered_here_are_the_inhibitor_choices_rows(monkeypatch):
    choice = defaults.Choice("inhibitor", "tacrine", "", (defaults.Option("edrophonium", {"ki": 2}),
                                                          defaults.Option("donepezil", {"ki": 1}),
                                                          defaults.Option("unusable", {"ki": 0})),
                             4, {"ki": 3})
    seen = {}

    def choose(ec, organism, substrate=None, **kw):
        seen.update(kw)
        return choice

    monkeypatch.setattr(defaults, "choose_inhibitor", choose)
    model = _model(("reaction_Ki", "ki", "mm_competitive_inhibition"))
    text = compose_main._inhibitors_here("3.1.1.7", "Homo sapiens", model, "donepezil")
    assert "tacrine (3 rows); edrophonium (2 rows)" in text
    assert "donepezil" not in text and "unusable" not in text


# -- N10: a compound named like a binomial is not an organism ----------------------------

def test_a_compound_shaped_like_a_binomial_is_never_offered_as_an_organism():
    pytest.importorskip("bs4")
    from caterva.checkout import literature_module

    client = literature_module("brenda_client")
    rows = [["109", "Phenolphthalein diphosphate", "Homo sapiens", "-", "-", "134695"],
            ["2042", "Sodium diphosphate", "Blastobotrys adeninivorans", "-", "pH 4.5, 60°C", "677611"]]
    html = ("<html><body><div id='tab1' class='equal'>"
            + "".join("<div class='row'>" + "".join(f"<div class='cell'>{c}</div>" for c in r) + "</div>"
                      for r in rows) + "</div></body></html>")
    found = client.parse_brenda_km_html(html, "3.1.3.2", target_substrates=["diphosphate"],
                                        target_organism=None)
    assert found == []
    every = client.parse_brenda_km_html(html, "3.1.3.2", target_substrates=["Sodium diphosphate"],
                                        target_organism=None)
    assert [e.organism for e in every] == ["Blastobotrys adeninivorans"]


# -- V7-05: an irreversible inactivator's Ki is said to be one, on every surface ---------

def test_an_irreversible_inactivators_ki_is_said_even_with_no_commentary():
    scope = read_scope(None, motif="mm_competitive_inhibition", table="ki", compound="selegiline")
    assert scope is not None and scope.concerns[0].kind == IRREVERSIBLE
    assert "selegiline is an irreversible" in scope.concerns[0].plain
    plain = read_scope("pH 7.4, 37°C", motif="mm_competitive_inhibition", table="ki", compound="argatroban")
    assert all(c.kind != IRREVERSIBLE for c in getattr(plain, "concerns", ()))
    # A Km is not an inhibition constant, whatever its compound is called.
    km = read_scope("pH 7.4", table="km", compound="selegiline")
    assert all(c.kind != IRREVERSIBLE for c in getattr(km, "concerns", ()))


def test_the_studio_constants_carry_the_resolvers_irreversible_note(monkeypatch):
    import sys

    from caterva.studio.adapters import constants
    from caterva.studio.adapters.constants import measured

    # The citation's words are report_lab's; not what this test is about.
    monkeypatch.setattr(constants, "_citation_text", lambda citation: "BRENDA ref 742446")
    monkeypatch.setitem(sys.modules, "caterva_report_lab", SimpleNamespace())

    raw = {"value": 5.5e-05, "unit": "mM", "source": "brenda_exact", "commentary": "pH 7.4, 37°C",
           "row_notes": ["selegiline is an irreversible (covalent or mechanism-based) inactivator: a Ki "
                         "row describes its initial reversible complex, and a reversible inhibition "
                         "model leaves the inactivation out", "the row measured MAO-B"]}
    value = measured(raw, ident="ki", label="ki", quantity="ki")
    scope = value["provenance"]["scope"]
    assert any("irreversible" in s for s in scope) and not any("measured MAO-B" in s for s in scope)


def test_the_inhibitor_note_agrees_in_number():
    """'antithrombin III, L-Phe-L-Pro-L-Arg-chloromethylketone are an
    irreversible inactivator' (A4-07)."""
    import inspect

    source = inspect.getsource(defaults._choose_inhibitor)
    assert '" are an irreversible inactivator' not in source
    assert "are irreversible inactivators" in source


# -- N19: a row stating a cofactor stated conditions -------------------------------------

@pytest.mark.parametrize("commentary, said", [
    ("cofactor NAD+", "cofactor NAD+"),
    ("-", None),
    (None, None),
    ("pH and temperature not specified in the publication", None),
])
def test_a_row_that_states_other_conditions_is_quoted(commentary, said):
    assert _other_conditions(commentary) == said


# -- A4-04: a labelled wild-type row carried over its paper's unlabelled one is said ------

def test_the_wild_type_label_preference_is_said_where_no_spread_says_it():
    because = ("of the 2 candidate rows (after the organism, substrate, isoform and variant checks): "
               "1 unlabelled row(s) passed over for the same paper's row labelled wild-type under "
               "otherwise the same stated conditions")
    record = SimpleNamespace(spread=None, resolver_because=because, reference_id=None,
                             citation="BRENDA ref 769319")
    note = _wild_type_label_note(record)
    assert note and "BRENDA ref 769319" in note and "states no wild-type label" in note
    assert _wild_type_label_note(SimpleNamespace(spread=object(), resolver_because=because)) is None


def test_the_robustness_line_points_only_to_a_section_the_page_has():
    import inspect

    source = inspect.getsource(verdict)
    assert "value's rows spread over several values" in source


# -- V5-4 and V5-5: which constant, and what asked for the isoform ----------------------

def _m(**kw):
    base = dict(value=1.0, unit="mM", commentary="pH 7.4", row_isoform=None, alternatives=(),
                chosen_because=f"the Km {PAIRED_ACROSS_TIERS} PKM2", resolver_because=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_the_paired_note_says_which_constant_was_measured_with_which():
    out = select_isoform({"reaction_Km": _m(), "reaction_kcat": _m(unit="1/s")}, "PKM2")
    kcat = next(n for n in out.notes if n.startswith("`reaction_kcat`"))
    km = next(n for n in out.notes if n.startswith("`reaction_Km`"))
    assert "it is the kcat measured with the Km the model carries" in kcat
    assert "it is the Km measured with the kcat the model carries" in km


def test_an_isoform_read_from_the_sentence_is_not_said_to_be_the_flags():
    row = {"value": 1.43, "unit": "mM", "conditions": "pH 7.5", "isoform": "DPP4", "reference_id": "665551"}
    from caterva.compose.export import Measurement

    m = Measurement(value=0.165, unit="mM", citation="BRENDA ref 649281", commentary="pH 7.5",
                    alternatives=(row,))
    said = select_isoform({"reaction_Km": m}, "DPP4", asked="your description")
    assert "as your description asked" in said.notes[0] and "--isoform" not in said.notes[0]
    flag = select_isoform({"reaction_Km": m}, "DPP4")
    assert "as --isoform asked" in flag.notes[0]
    notice = IsozymeNotice(ec="2.7.1.40", organism="HUMAN", count=2, symbols=("PKM", "PKLR"),
                           isoform="PKM2", unstated=("reaction_Km",), asked="your description")
    assert notice.detail.startswith("PKM2 was read from your description for EC 2.7.1.40")
    assert compose_main._isoform_asked(SimpleNamespace(isoform="DPP4")) == "--isoform"


# -- V7-09: the natural substrate's counts follow its own name ---------------------------

def test_the_natural_substrates_counts_and_its_tie_are_said_beside_it(monkeypatch):
    _stub(monkeypatch, {
        ("km", "Homo sapiens"): [("fibrinogen", 1, False), ("fibrinogen", 3, True),
                                 ("Fibrinopeptide A", 1, False),
                                 ("D-Phe-Pip-Arg-4-nitroanilide", 8, False)],
        ("kcat", "Homo sapiens"): [("fibrinogen", 1, False), ("fibrinogen", 3, True),
                                   ("Fibrinopeptide A", 1, False),
                                   ("D-Phe-Pip-Arg-4-nitroanilide", 8, False)],
    }, natural=("fibrinogen", "Fibrinopeptide A"))
    choice = defaults.choose_substrate("3.4.21.5", "Homo sapiens", strict=True)
    assert choice.chosen == "fibrinogen"
    assert "with as many rows the search can use as any other natural substrate (1 Km, 1 kcat" in choice.why
    assert "it ties on those rows with Fibrinopeptide A" in choice.why
    assert ("better-measured assay substrates, such as D-Phe-Pip-Arg-4-nitroanilide (8 Km, 8 kcat), "
            "rank after it") in choice.why
    # The chosen substrate's counts are not printed after the assay substrates.
    assert not choice.why.rstrip(". ").endswith("rank after it (1 Km, 1 kcat)")


def test_the_verdict_counts_every_organism_the_list_holds():
    reason = ("no value in the organism requested -- available in: Plasmodium falciparum (4 rows); "
              "Rhizopus delemar (4 rows); Enterococcus mundtii (3 rows); Oryctolagus cuniculus (2 rows) "
              "and 9 more (rows of a protein variant only, withheld: Escherichia coli (1 row)) "
              "(searched under the requirement that organism must be Homo sapiens)")
    step = verdict._what_would_ground(SimpleNamespace(not_found={"reaction_kcat": reason}), ["reaction_kcat"])
    assert "Enterococcus mundtii (3 rows) and 10 more" in step


def test_the_verdict_names_the_inhibitors_the_organism_has_rows_for():
    """Human COX-2 and celecoxib: the step named no inhibitor; nimesulide
    is the one with a human Ki row (V7-08's compose side)."""
    reason = ("no database value -- BRENDA has no Ki row for celecoxib under EC 1.14.99.1 in Homo "
              "sapiens; the inhibitors it lists Ki rows for there: nimesulide (1 row). Re-run with "
              "--inhibitor set to one of them, or supply it yourself.")
    step = verdict._what_would_ground(SimpleNamespace(not_found={"reaction_Ki": reason}), ["reaction_Ki"])
    assert "re-run with --inhibitor set to one of nimesulide (1 row)" in step
