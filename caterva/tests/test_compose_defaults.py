"""A named enzyme gets its best-measured substrate, said out loud (ADR 0182).

WHY THESE TESTS
---------------
On 2026-11-11, 56 descriptions a professor would type were run on main and
7 came back fully measured. 26 of the others named an enzyme and no
substrate and were refused before a table was read, though BRENDA had the
rows and the refusal listed them; a Ki whose inhibitor was unnamed was a
placeholder with nothing to name; no organism meant whatever organism a
search over all of them settled on (Eimeria tenella for human-sounding
hexokinase); and two runs crashed with a traceback.

These hold the new rule to what it promises: Caterva chooses what the user
did not name -- organism, substrate, inhibitor, and the enzyme a name is a
few of when the data singles one out -- from BRENDA's own rows; every choice
is a note naming the alternatives and their row counts; a flag or a word of
the sentence always wins; an organism the user named is never switched; and
a partly measured model's verdict names its mix and the missing piece.

Offline throughout: the committed BRENDA page for EC 2.7.1.1
(Tests/fixtures/recorded/), its recorded HTTP answers
(studio_kinetics_offline.hexokinase_offline), or `defaults.table_rows`
replaced by rows written here, with every real send made impossible.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pytest

from caterva.compose import defaults
from caterva.compose.pipeline import compose
from studio_kinetics_offline import context, hexokinase_offline, run_cli

RECORDED = Path(__file__).resolve().parents[2] / "Tests" / "fixtures" / "recorded"
COMPETITIVE = "Michaelis-Menten with a competitive inhibitor"
FLAGS = ["--no-simulate", "--no-analysis", "--no-ranking"]


@pytest.fixture
def recorded(monkeypatch):
    """BRENDA's hexokinase page from the recording, and no network at all.
    Returns the URLs a send was attempted for (held empty by the tests)."""
    import httpx

    attempts = []

    def refuse(self, request):
        attempts.append(str(request.url))
        raise httpx.ConnectError("network disabled in this test", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setenv("CATERVA_BRENDA_RECORDED", str(RECORDED))
    return attempts


def _rows(monkeypatch, tables, reaction=(frozenset(), frozenset())):
    """`defaults.table_rows` answering from `tables`: {(table, organism):
    {compound: n}}; an organism of None lists every organism's rows."""

    def table_rows(ec, table, organism):
        out = []
        for (t, org), counts in tables.items():
            if t != table or (organism is not None and org != organism):
                continue
            out += [defaults._Row(name, org, "") for name, n in counts.items() for _ in range(n)]
        return tuple(out)

    monkeypatch.setattr(defaults, "table_rows", table_rows)
    monkeypatch.setattr(defaults, "_reaction_compounds", lambda ec: reaction)


def _args(**fields):
    base = {"description": "", "subject": None, "organism": None, "substrate": None, "inhibitor": None}
    base.update(fields)
    return argparse.Namespace(**base)


# ---------------------------------------------------------------------------
# What is chosen, on the recorded page
# ---------------------------------------------------------------------------


def test_the_substrate_is_the_best_measured_with_the_cosubstrate_set_aside(recorded):
    choice = defaults.choose_substrate("2.7.1.1", "Homo sapiens")
    assert recorded == []
    assert choice.chosen == "D-glucose" and choice.rows == {"km": 25, "kcat": 61}
    assert "the cosubstrate ATP set aside" in choice.why
    assert [o.name for o in choice.alternatives][:3] == ["2-deoxy-D-glucose", "D-mannose", "D-fructose"]


def test_a_model_without_a_kcat_ranks_by_km_alone(recorded):
    choice = defaults.choose_substrate("2.7.1.1", "Homo sapiens", needs_kcat=False)
    assert choice.chosen == "D-glucose" and choice.rows == {"km": 25}
    assert choice.alternatives[0].name == "D-mannose"


def test_the_inhibitor_puts_a_product_of_the_reaction_last(recorded):
    """D-glucose 6-phosphate is hexokinase's product: product inhibition,
    ranked after every compound that is not part of the reaction."""
    choice = defaults.choose_inhibitor("2.7.1.1", "Homo sapiens", "D-glucose")
    assert choice.chosen == "1,5-Anhydro-D-glucitol 6-phosphate" and choice.rows == {"ki": 5}
    assert choice.alternatives[-1].name == "D-glucose 6-phosphate"


def test_no_organism_prefers_human_when_it_covers_every_constant(recorded):
    choice = defaults.choose_organism("2.7.1.1", substrate="D-glucose", needs=("km", "kcat"))
    assert choice.chosen == "Homo sapiens"
    assert "Homo sapiens is used when it has rows for every constant this model needs" in choice.why
    assert "Eimeria tenella" in [o.name for o in choice.alternatives] or choice.considered > 6


def test_the_command_line_prints_the_contract_shape_and_exits_3_on_nothing(recorded, capsys):
    assert defaults.main(["--ec", "2.7.1.1", "--organism", "human", "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed) == {"choice", "note"}
    assert set(printed["choice"]) == {"role", "chosen", "why", "alternatives", "considered"}
    assert printed["choice"]["chosen"] == "D-glucose"
    assert printed["note"].startswith("No substrate was named, so Caterva used D-glucose:")
    assert defaults.main(["--ec", "2.7.1.1", "--organism", "zebrafish", "--json"]) == 3
    printed = json.loads(capsys.readouterr().out)
    assert printed["choice"] is None
    assert printed["note"] == ("BRENDA holds no Km rows under EC 2.7.1.1 in Danio rerio, so there "
                               "is no substrate to choose.")


@pytest.mark.parametrize("name, cofactor", [
    ("ATP", True), ("beta-NAD+", True), ("NADPH", True), ("Mg2+", True), ("CoA", True),
    ("H2O", True), ("D-glucose", False), ("CO2", False), ("acetyl-CoA", False), ("pyruvate", False),
    # The respiratory quinones are succinate dehydrogenase's electron acceptor,
    # as NAD+ is a dehydrogenase's: live, "competitive inhibition of succinate
    # dehydrogenase by malonate" chose ubiquinone, and paired malonate's Ki
    # (competitive versus succinate) with ubiquinone's Km (review, 2026-11-12).
    ("ubiquinone", True), ("ubiquinone-2", True), ("ubiquinone 9", True), ("menaquinol", True),
    ("decylubiquinone", True), ("coenzyme Q10", True), ("plastoquinone-9", True),
    # A phenol oxidase's or quinone reductase's own substrate is not set aside.
    ("hydroquinone", False), ("1,4-benzoquinone", False), ("succinate", False),
])
def test_cofactors_are_recognised_and_substrates_are_not(name, cofactor):
    assert defaults.is_cofactor(name) is cofactor


# ---------------------------------------------------------------------------
# The rules, on rows written here
# ---------------------------------------------------------------------------


def test_an_inhibitor_that_is_a_product_is_set_aside_and_the_note_says_so(monkeypatch):
    _rows(monkeypatch, {("ki", "Homo sapiens"): {"D-glucose 6-phosphate": 9, "atorvastatin": 1}},
          reaction=(frozenset({"d-glucose"}), frozenset({"d-glucose", "d-glucose 6-phosphate"})))
    choice = defaults.choose_inhibitor("2.7.1.1", "Homo sapiens", "D-glucose")
    assert choice.chosen == "atorvastatin"
    assert ("D-glucose 6-phosphate (9 Ki rows) is a substrate or product of the reaction (product "
            "inhibition), so it was set aside") in choice.why


def test_only_a_product_inhibitor_is_used_and_called_product_inhibition(monkeypatch):
    _rows(monkeypatch, {("ki", "Homo sapiens"): {"D-glucose 6-phosphate": 3}},
          reaction=(frozenset(), frozenset({"d-glucose 6-phosphate"})))
    choice = defaults.choose_inhibitor("2.7.1.1", "Homo sapiens")
    assert choice.chosen == "D-glucose 6-phosphate"
    assert "so this is product or substrate inhibition" in choice.why


def test_an_organism_is_chosen_for_the_inhibitor_named(monkeypatch):
    """'xanthine oxidase inhibited by allopurinol', no organism: the human
    rows cover Km and kcat, only Bos taurus has an allopurinol Ki row, so the
    model is of Bos taurus, and the note says why human was not used."""
    _rows(monkeypatch, {
        ("km", "Homo sapiens"): {"xanthine": 6}, ("kcat", "Homo sapiens"): {"xanthine": 3},
        ("km", "Bos taurus"): {"xanthine": 4}, ("kcat", "Bos taurus"): {"xanthine": 2},
        ("ki", "Bos taurus"): {"allopurinol": 1}, ("ki", "Homo sapiens"): {"febuxostat": 2},
    })
    choice = defaults.choose_organism("1.17.3.2", "xanthine", "allopurinol",
                                      needs=("km", "kcat", "ki"))
    assert choice.chosen == "Bos taurus"
    assert "it has rows for 3 of the 3 constant(s) this model needs" in choice.why
    assert "Homo sapiens, preferred when it covers them all, does not" in choice.why
    assert choice.alternatives[0].name == "Homo sapiens"


def test_the_command_line_chooses_the_organism_for_the_constants_asked_for(monkeypatch, capsys):
    """`resolve "xanthine oxidase" --quantity ki` names no inhibitor and no
    organism. Counted for Km and kcat the organism was Homo sapiens, which
    has no Ki row at all, and the run was refused "no inhibitor to choose"
    (review of 2026-11-12). `--needs ki` counts the Ki rows."""
    _rows(monkeypatch, {
        ("km", "Homo sapiens"): {"xanthine": 6}, ("kcat", "Homo sapiens"): {"xanthine": 3},
        ("km", "Bos taurus"): {"xanthine": 4}, ("kcat", "Bos taurus"): {"xanthine": 2},
        ("ki", "Bos taurus"): {"allopurinol": 3, "febuxostat": 2},
    })
    assert defaults.main(["--ec", "1.17.3.2", "--role", "organism", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["choice"]["chosen"] == "Homo sapiens"
    assert defaults.main(["--ec", "1.17.3.2", "--role", "organism", "--needs", "ki", "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["choice"]["chosen"] == "Bos taurus"
    assert "(Ki)" in printed["choice"]["why"] and "5 Ki" in printed["choice"]["why"]


def test_the_command_line_refuses_a_constant_it_does_not_know(monkeypatch, capsys):
    _rows(monkeypatch, {("ki", "Bos taurus"): {"allopurinol": 1}})
    assert defaults.main(["--ec", "1.17.3.2", "--role", "organism", "--needs", "vmax", "--json"]) == 2
    assert "--needs takes km, kcat and ki" in capsys.readouterr().err
    _rows(monkeypatch, {("km", "Bos taurus"): {"xanthine": 1}})
    assert defaults.main(["--ec", "1.17.3.2", "--role", "organism", "--needs", "ki", "--json"]) == 3
    assert json.loads(capsys.readouterr().out)["note"] == (
        "BRENDA holds no Ki rows under EC 1.17.3.2 (every organism), so there is no organism to choose.")


def test_an_organism_with_a_km_for_one_substrate_and_a_kcat_for_another_covers_one(monkeypatch):
    _rows(monkeypatch, {
        ("km", "Mus musculus"): {"A": 50}, ("kcat", "Mus musculus"): {"B": 50},
        ("km", "Rattus norvegicus"): {"A": 2}, ("kcat", "Rattus norvegicus"): {"A": 1},
    })
    assert defaults.choose_organism("1.1.1.1", needs=("km", "kcat")).chosen == "Rattus norvegicus"


def test_a_natural_substrate_outranks_a_better_measured_assay_substrate(monkeypatch):
    """ACE: angiotensin I (BRENDA's Natural Substrates) over hippuryl-His-Leu,
    the assay substrate with more rows, both having a Km and a kcat."""
    _rows(monkeypatch, {("km", "Homo sapiens"): {"angiotensin I": 11, "hippuryl-His-Leu": 18},
                        ("kcat", "Homo sapiens"): {"angiotensin I": 3, "hippuryl-His-Leu": 9}},
          reaction=(frozenset({"angiotensin i"}), frozenset({"angiotensin i"})))
    choice = defaults.choose_substrate("3.4.15.1", "Homo sapiens")
    assert choice.chosen == "angiotensin I"
    assert ("it is the natural substrate (BRENDA's Natural Substrates table) with the most rows; "
            "better-measured assay substrates rank after it (11 Km, 3 kcat)") in choice.why


def test_an_organism_that_is_not_a_binomial_is_still_found(monkeypatch):
    """EC 3.4.23.16's rows are all "Human immunodeficiency virus 1", which
    the every-organism parse cannot label: with no organism named the page
    read as having no substrate at all (2026-11-11)."""
    virus = "Human immunodeficiency virus 1"
    _rows(monkeypatch, {("km", virus): {"Lys-Ala-Arg-Val-Nle-Phe(4-NO2)-Glu-Ala-Nle-Gly": 14},
                        ("kcat", virus): {"Lys-Ala-Arg-Val-Nle-Phe(4-NO2)-Glu-Ala-Nle-Gly": 9}})
    real = defaults.table_rows
    monkeypatch.setattr(defaults, "table_rows",
                        lambda ec, t, org: () if org is None else real(ec, t, org))
    from collections import Counter

    monkeypatch.setattr(defaults, "_organisms_on_page", lambda ec, table: Counter({virus: 164}))
    choice = defaults.choose_organism("3.4.23.16", needs=("km", "kcat"))
    assert choice.chosen == virus and choice.rows == {"km": 14, "kcat": 9}


def test_a_spelling_that_differs_only_in_case_is_one_compound(monkeypatch):
    _rows(monkeypatch, {("km", "Homo sapiens"): {"Acetylcholine": 1, "acetylcholine": 3,
                                                  "acetylthiocholine": 3}})
    choice = defaults.choose_substrate("3.1.1.7", "Homo sapiens", needs_kcat=False)
    assert choice.chosen == "acetylcholine" and choice.rows == {"km": 4}


def test_a_page_without_the_table_chooses_nothing(monkeypatch):
    _rows(monkeypatch, {})
    assert defaults.choose_substrate("2.7.10.1", "Homo sapiens") is None
    assert defaults.choose_inhibitor("2.7.10.1", "Homo sapiens") is None
    assert defaults.choose_organism("2.7.10.1") is None


@pytest.mark.parametrize("rows, organism, chosen", [
    ({"2.3.3.1": 28, "2.3.3.3": 2}, None, "2.3.3.1"),
    ({"2.3.3.1": 28, "2.3.3.3": 9}, None, None),
    ({"2.3.3.1": 8, "2.3.3.3": 0}, "Homo sapiens", "2.3.3.1"),
    ({"2.3.3.1": 0, "2.3.3.3": 0}, "Mus musculus", None),
])
def test_an_enzyme_name_is_settled_only_when_the_data_singles_one_out(monkeypatch, rows, organism, chosen):
    monkeypatch.setattr(defaults, "table_rows", lambda ec, table, org: tuple(
        defaults._Row("x", org, "") for _ in range(rows.get(ec, 0))))
    choice = defaults.choose_enzyme("citrate synthase", [("2.3.3.1", "citrate (Si)-synthase"),
                                                          ("2.3.3.3", "citrate (Re)-synthase")],
                                    organism)
    assert (choice.chosen if choice else None) == chosen


# ---------------------------------------------------------------------------
# In compose: the order, the flags, the notes
# ---------------------------------------------------------------------------


def _searched_for(monkeypatch):
    """Replace the search; return the kwargs it is called with."""
    from caterva.compose import pipeline

    asked = {}

    def search(query, **kwargs):
        asked.update(kwargs)
        return None, None

    monkeypatch.setattr(pipeline, "compose_and_parameterise", search)
    return asked


def test_no_organism_is_chosen_before_the_search_so_the_search_is_held_to_it(recorded, monkeypatch):
    """Hexokinase and D-glucose with no organism came from Eimeria tenella,
    a chicken parasite, because the search chose among everything; the
    organism is now chosen first, from the page, and said."""
    from caterva.compose.__main__ import search_the_literature

    asked = _searched_for(monkeypatch)
    model = compose("Michaelis Menten", subject="2.7.1.1")
    found, _, refused = search_the_literature(model, _args(subject="2.7.1.1", substrate="D-glucose"))
    assert refused is False and recorded == []
    assert asked["organism"] == "Homo sapiens" and asked["substrate"] == "D-glucose"
    assert [c.role for c in found.choices] == ["organism"]
    assert found.choices[0].note().startswith("No organism was named, so Caterva used Homo sapiens:")


def test_a_flag_is_never_replaced_by_a_choice(recorded, monkeypatch):
    from caterva.compose.__main__ import search_the_literature

    asked = _searched_for(monkeypatch)
    model = compose(COMPETITIVE, subject="2.7.1.1")
    found, _, _ = search_the_literature(model, _args(
        subject="2.7.1.1", organism="Homo sapiens", substrate="D-mannose", inhibitor="atorvastatin"))
    assert found.choices == ()
    assert asked["substrate"] == "D-mannose" and asked["compounds"] == {"@inhibitor": "atorvastatin"}


def test_a_search_that_settles_on_no_organism_is_a_report_not_a_traceback(monkeypatch):
    """'pepsin with hemoglobin', no organism, raised ExportRefused out of
    the CLI (2026-11-11). Reached now only when no organism could be chosen."""
    from types import SimpleNamespace

    from caterva.compose import narrowed, pipeline
    from caterva.compose.__main__ import search_the_literature
    from caterva.compose.export import ExportRefused

    monkeypatch.setattr(defaults, "choose_organism", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "compose_and_parameterise", lambda query, **kw: (
        None, SimpleNamespace(build=None, branches=(), undecided=("Sus scrofa", "Bos taurus"))))

    def unsettled(*a, **k):
        raise ExportRefused("this search settled on no single model")

    monkeypatch.setattr(narrowed, "select_for_model", unsettled)
    model = compose("Michaelis Menten", subject="3.4.23.1")
    found, note, refused = search_the_literature(model, _args(subject="3.4.23.1", substrate="hemoglobin"))
    assert refused is True
    assert ("settled on no single one: Sus scrofa, Bos taurus each give a whole model, and nothing "
            "separates them. Re-run with --organism NAME") in note
    assert found.search_refused


def test_a_word_brenda_lists_as_an_inhibitor_is_read_as_one_and_the_model_built_with_it(monkeypatch):
    """'dihydrofolate reductase with methotrexate in E. coli' was plain
    Michaelis-Menten with methotrexate dropped without a word."""
    from collections import Counter

    import caterva.compose.__main__ as cli

    monkeypatch.setattr(cli, "brenda_km_substrates", lambda ec, org: {"7,8-dihydrofolate": 86})
    monkeypatch.setattr(defaults, "ki_compounds", lambda ec, org: {"methotrexate": 1, "trimethoprim": 4})
    monkeypatch.setattr(defaults, "ki_modes", lambda ec, org, name: Counter({"competitive": 1}))
    args = _args(description="dihydrofolate reductase with methotrexate in E. coli")
    read = cli.read_description(args, err=io.StringIO())
    assert (args.subject, args.organism, args.inhibitor) == ("1.5.1.3", "Escherichia coli", "methotrexate")
    assert args.substrate is None
    assert read.description == cli.INHIBITED_ENZYME_SHAPE
    assert compose(read.description).recognition.rule == "competitive_inhibition"
    text = " ".join(read.notes)
    assert ("Read 'methotrexate' in your description as the inhibitor methotrexate, which BRENDA "
            "lists Ki rows for under EC 1.5.1.3 for Escherichia coli") in text
    assert ("so the model is competitive inhibition; BRENDA's Ki rows for methotrexate under EC "
            "1.5.1.3 in Escherichia coli state: competitive (1 row)") in text


# ---------------------------------------------------------------------------
# The report: a partly grounded model says its mix and its missing piece
# ---------------------------------------------------------------------------


def test_a_partly_measured_model_names_its_mix_and_the_piece_that_is_missing(monkeypatch):
    """Granzyme B with a substrate and no inhibitor read STRUCTURAL, "the
    constants are the library's illustrative values", over a table with two
    of three cited, and "Do this next" said to change the organism; the
    note said the Ki search "ran and returned nothing" beside a table row
    saying it was not looked up. Here the inhibitor cannot be chosen, so the
    Ki is the one placeholder, and every line has to say so."""
    monkeypatch.setattr(defaults, "choose_inhibitor", lambda *a, **k: None)
    with hexokinase_offline():
        code, out, err = run_cli(_main(), [COMPETITIVE, "--subject", "2.7.1.1", "--organism", "human",
                                           "--substrate", "D-glucose", "--no-ranking"])
    assert code == 0, err
    assert "VERDICT: STRUCTURAL (partly grounded: 2 of 3 constants measured)" in out
    assert ("2 of its 3 constants are measured, with citations (reaction_Km, reaction_kcat), and 1 "
            "is still the library's illustrative value (reaction_Ki)") in out
    assert "the constants are the library's illustrative values" not in out
    assert "Do this next: name the inhibitor with --inhibitor NAME, so reaction_Ki is looked up" in out
    assert "re-run with --organism" not in out.split("Do this next:")[1].split("\n")[0]
    assert "1 not looked up (reaction_Ki)" in out
    assert "still the motif library's placeholder (reaction_Ki)" not in out


def _main():
    from caterva.compose.__main__ import main

    return main


def test_the_studio_result_carries_each_choice_in_order(tmp_path):
    from caterva.studio.adapters import compose as adapter

    with hexokinase_offline():
        outcome = adapter.run({"description": "hexokinase Michaelis-Menten kinetics",
                               "organism": "human"}, context(tmp_path))
    assert outcome.exit_code == 0, outcome.refusal
    search = outcome.result["search"]
    assert [c["role"] for c in search["choices"]] == ["substrate"]
    (choice,) = search["choices"]
    assert choice["chosen"] == "D-glucose" and choice["considered"] == 10
    assert choice["alternatives"][0] == {"name": "2-deoxy-D-glucose", "rows": {"km": 5, "kcat": 1}}
    assert search["substrate"] == "D-glucose" and search["measured"] == 2
    assert any(n.startswith("No substrate was named, so Caterva used D-glucose:")
               for n in outcome.result["notes"])


# ---------------------------------------------------------------------------
# Review of ADR 0182: a value is never carried under a neighbour's name
# ---------------------------------------------------------------------------


def test_a_value_whose_row_is_a_longer_named_compound_is_traced_to_it(recorded):
    """The resolver finds "D-glucose" inside "2-deoxy-D-glucose". On the
    recorded page 1.9 mM (ref 641068) is a 2-deoxy-D-glucose row and 6.0 mM
    (same ref) a D-glucose row: the first is the neighbour, the second is
    not, and a name BRENDA does not list exactly is never judged."""
    assert defaults.neighbour_of("2.7.1.1", "km", "D-glucose", "Homo sapiens", 1.9, "641068") == (
        "2-deoxy-D-glucose",)
    assert defaults.neighbour_of("2.7.1.1", "km", "D-glucose", "Homo sapiens", 6.0, "641068") is None
    assert defaults.neighbour_of("2.7.1.1", "km", "glucose", "Homo sapiens", 1.9, "641068") is None
    assert defaults.neighbour_of("2.7.1.1", "km", "D-glucose", "Homo sapiens", 1.9, "999999") is None
    assert recorded == []


def test_a_neighbours_value_returned_by_the_search_is_withheld_and_said(recorded, monkeypatch):
    """Chymotrypsin, 2026-11-11: the substrate chosen was L-alanyl-...-
    p-nitroanilide and the Km carried (0.219 mM, ref 769319) was the
    N-succinyl compound's row. Here the same shape on the recorded page: a
    search that hands back 2-deoxy-D-glucose's 1.9 mM as D-glucose's Km.
    It is withheld, the other compound is named, and the kcat (D-glucose's
    own row) is still carried."""
    from types import SimpleNamespace

    from caterva.compose import narrowed, pipeline
    from caterva.compose.__main__ import search_the_literature
    from caterva.compose.export import Measurement

    monkeypatch.setattr(pipeline, "compose_and_parameterise", lambda query, **kw: (
        None, SimpleNamespace(build=None, branches=(), undecided=())))
    returned = {
        # As the search builds it: the reference in the citation only.
        "reaction_Km": Measurement(value=1.9, unit="mM", citation="BRENDA ref 641068",
                                   organism="Homo sapiens"),
        "reaction_kcat": Measurement(value=40.1, unit="1/s", citation="BRENDA ref 739603",
                                     organism="Homo sapiens", reference_id="739603"),
    }
    monkeypatch.setattr(narrowed, "select_for_model",
                        lambda *a, **k: narrowed.Selection(measured=dict(returned)))
    model = compose("Michaelis Menten", subject="2.7.1.1")
    found, note, refused = search_the_literature(
        model, _args(subject="2.7.1.1", organism="Homo sapiens", substrate="D-glucose"))
    assert refused is False and recorded == []
    assert set(found.measured) == {"reaction_kcat"}
    reason = found.not_found["reaction_Km"]
    assert "is BRENDA's row for 2-deoxy-D-glucose, not for D-glucose" in reason
    assert "1.9 mM, BRENDA ref 641068" in reason
    assert "returned by the search and not used (reaction_Km)" in note


def test_a_word_that_matches_several_substrates_is_chosen_among_them_only(monkeypatch):
    """'glucose' matched D-glucose and beta-D-glucose; the choice is made
    between those two by their rows, never D-mannose for having more."""
    _rows(monkeypatch, {("km", "Homo sapiens"): {"D-mannose": 30, "D-glucose": 4, "beta-D-glucose": 2},
                        ("kcat", "Homo sapiens"): {"D-mannose": 30, "D-glucose": 1}})
    choice = defaults.choose_substrate("2.7.1.1", "Homo sapiens",
                                       among=("D-glucose", "beta-D-glucose"))
    assert choice.chosen == "D-glucose" and choice.considered == 2
    assert "of the 2 substrates that your word matches" in choice.why
    assert [o.name for o in choice.alternatives] == ["beta-D-glucose"]


def test_a_choice_made_instead_of_a_named_word_does_not_say_nothing_was_named():
    choice = defaults.Choice("substrate", "D-glucose", "of the 10 substrates ...",
                             instead="No word of your description ('G6P') is a substrate BRENDA lists")
    assert choice.note().startswith("No word of your description ('G6P') is a substrate BRENDA "
                                    "lists, so Caterva used D-glucose:")
    assert "No substrate was named" not in choice.note()
    assert "instead" not in choice.to_json(), "the Studio contract's shape is unchanged"
