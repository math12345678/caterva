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
    # The real reader returns `_key`s; the fixtures are written as names.
    keyed = tuple(frozenset(defaults._key(n) for n in side) for side in reaction)
    monkeypatch.setattr(defaults, "_reaction_compounds", lambda ec: keyed)


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
    assert choice.chosen == "D-glucose" and choice.rows == {"km": 13, "kcat": 13}
    assert "the cosubstrate ATP set aside" in choice.why
    # Counted as the search counts: 12 of the 25 Km rows and 48 of the 61
    # kcat rows measured a mutant or an isozyme, which it withholds.
    assert "not counted, because the search cannot use them: 60 rows of a variant" in choice.why
    assert [o.name for o in choice.alternatives][:3] == ["2-deoxy-D-glucose", "D-mannose", "D-fructose"]


def test_a_model_without_a_kcat_ranks_by_km_alone(recorded):
    choice = defaults.choose_substrate("2.7.1.1", "Homo sapiens", needs_kcat=False)
    assert choice.chosen == "D-glucose" and choice.rows == {"km": 13}
    assert choice.alternatives[0].name == "D-mannose"


def test_the_inhibitor_puts_a_product_of_the_reaction_last(recorded, monkeypatch):
    """D-glucose 6-phosphate is hexokinase's product: product inhibition,
    ranked after every compound that is not part of the reaction (all of
    them listed, so the last place is seen)."""
    monkeypatch.setattr(defaults, "ALTERNATIVES_NAMED", 50)
    choice = defaults.choose_inhibitor("2.7.1.1", "Homo sapiens", "D-glucose")
    # Since the fourth round every Substrates/Products cell is read (the
    # span-wrapped ones were missed): 1,5-anhydro-D-glucitol 6-phosphate is
    # also a product of the enzyme's, and ranks last with D-glucose 6-phosphate.
    assert choice.chosen == "D-glucose 1,6-diphosphate" and choice.rows == {"ki": 2}
    assert {o.name for o in choice.alternatives[-2:]} == {
        "D-glucose 6-phosphate", "1,5-Anhydro-D-glucitol 6-phosphate"}


def test_no_organism_prefers_human_when_it_covers_every_constant(recorded):
    choice = defaults.choose_organism("2.7.1.1", substrate="D-glucose", needs=("km", "kcat"))
    assert choice.chosen == "Homo sapiens"
    assert "Homo sapiens is used when it has rows for every constant this model needs" in choice.why
    assert "Eimeria tenella" in [o.name for o in choice.alternatives] or choice.considered > 6


def test_the_command_line_prints_the_contract_shape_and_exits_3_on_nothing(recorded, capsys):
    assert defaults.main(["--ec", "2.7.1.1", "--organism", "human", "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed) == {"choice", "note"}
    assert set(printed["choice"]) == {"role", "chosen", "why", "alternatives", "considered", "rows",
                                      "instead"}
    assert printed["choice"]["rows"] == {"km": 13, "kcat": 13} and printed["choice"]["instead"] is None
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
    # The counts follow the natural substrate's own description, and the
    # assay substrate is named with its own: "rank after it (11 Km, 3 kcat)"
    # read as the assay substrates' counts (fifth round's review, V7-09).
    assert ("it is the natural substrate (BRENDA's Natural Substrates table) with the most rows "
            "(11 Km, 3 kcat); better-measured assay substrates, such as hippuryl-His-Leu "
            "(18 Km, 9 kcat), rank after it") in choice.why


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
    assert choice["alternatives"][0] == {"name": "2-deoxy-D-glucose", "rows": {"km": 4, "kcat": 1}}
    assert choice["rows"] == {"km": 13, "kcat": 13} and choice["instead"] is None
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
    # The page reads both without parsing the note (round-1 review, F18).
    assert choice.to_json()["instead"] == "No word of your description ('G6P') is a substrate BRENDA lists"
    assert choice.to_json()["rows"] == {}


# ---------------------------------------------------------------------------
# Round-1 review (2026-11-12): a count is of rows the search can use
# ---------------------------------------------------------------------------
#
# Each case is the shape of a live run that ended in placeholders while
# BRENDA held usable rows. The rows are written here, each quoting the real
# BRENDA row it stands for (EC, compound, organism, commentary, reference),
# so the tests stay offline.


def _given(monkeypatch, rows, natural=(), reaction=()):
    """`defaults.table_rows` answering from `rows`: {table: [_Row, ...]}, the
    organism filter applied as the parser applies it."""

    def table_rows(ec, table, organism):
        return tuple(r for r in rows.get(table, ()) if organism is None or r.organism == organism)

    monkeypatch.setattr(defaults, "table_rows", table_rows)
    monkeypatch.setattr(defaults, "_reaction_compounds", lambda ec: (
        frozenset(defaults._key(n) for n in natural),
        frozenset(defaults._key(n) for n in (*natural, *reaction))))


def _row(compound, conditions="", *, organism="Homo sapiens", ref="1", value=1.0, variant=False,
         isozyme=False, uniprot=None):
    return defaults._Row(compound, organism, conditions, value, ref, uniprot, variant, isozyme)


def test_mutant_rows_are_not_counted_toward_the_best_measured(monkeypatch):
    """Granzyme B in human (A8): 2-aminobenzoyl-IEPDSSMEK-dnp was chosen as
    having "the most" rows, 3 Km and 3 kcat, two of each a mutant's (ref
    652110: 0.0058 wild-type, 0.0068 mutant K24A, 0.0387 mutant K27A), which
    the search withholds. Boc-Ala-Ala-Asp-SBzl's three rows (refs 649543,
    649536) are all usable."""
    iepd = "2-aminobenzoyl-IEPDSSMEK-dnp"
    boc = "Boc-Ala-Ala-Asp-SBzl"
    def rows(table):
        return [_row(iepd, "wild-type", ref="652110"),
                _row(iepd, "mutant K24A", ref="652110", variant=True),
                _row(iepd, "mutant K27A", ref="652110", variant=True),
                _row(boc, "recombinant enzyme", ref="649543"), _row(boc, "native enzyme", ref="649543"),
                _row(boc, "", ref="649536")]
    _given(monkeypatch, {"km": rows("km"), "kcat": rows("kcat")})
    choice = defaults.choose_substrate("3.4.21.79", "Homo sapiens")
    assert choice.chosen == boc and choice.rows == {"km": 3, "kcat": 3}
    assert choice.alternatives[0].name == iepd and choice.alternatives[0].rows == {"km": 1, "kcat": 1}
    assert "tied" not in choice.why


def test_the_isoform_asked_for_decides_which_substrate_rows_count(monkeypatch):
    """'CYP3A4 metabolising midazolam' (M1, F01): 7-ethoxyresorufin, BRENDA's
    natural substrate, has human rows only for CYP1A1, so its Km was withheld
    and every constant was a placeholder; fenthion has rows naming CYP3A4
    (0.089 mM, ref 706823, "CYP3A4, at pH 7.4 and 37°C")."""
    _given(monkeypatch, {
        "km": [_row("7-ethoxyresorufin", "CYP1A1, pH 7.4", ref="700001"),
               _row("7-ethoxyresorufin", "CYP1A1, 37°C", ref="700002"),
               _row("fenthion", "CYP3A4, at pH 7.4 and 37°C", ref="706823", value=0.089),
               _row("fenthion", "CYP3A4, sulfoxidation", ref="706823", value=0.131),
               _row("fenthion", "CYP2B6, desulfuration", ref="706823")],
        "kcat": []}, natural=["7-ethoxyresorufin"])
    choice = defaults.choose_substrate("1.14.14.1", "Homo sapiens", isoform="CYP3A4")
    assert choice.chosen == "fenthion" and choice.rows == {"km": 2, "kcat": 0}
    assert "counting the rows the search can use for CYP3A4" in choice.why
    assert "1 row of another isoform" in choice.why
    assert [(o.name, o.rows) for o in choice.alternatives] == [("7-ethoxyresorufin", {"km": 0, "kcat": 0})]
    assert "7-ethoxyresorufin (no usable row)" in choice.note()
    # Without an isoform the natural substrate is still the choice.
    assert defaults.choose_substrate("1.14.14.1", "Homo sapiens").chosen == "7-ethoxyresorufin"


def test_two_spellings_of_cgmp_are_one_natural_substrate_counted_together(monkeypatch):
    """'PDE5 inhibited by sildenafil' (B3, F01): "3',5'-cGMP", BRENDA's natural
    substrate, had one human row, "recombinant human cone PDE6C" (ref
    712394), and was chosen over "cGMP" with PDE5A rows (0.0029 mM, ref
    678243, "wild-type, pH 7.5, 30°C", O76074). One compound: counted
    together, searched as cGMP, the spelling the usable rows are under."""
    rows = [_row("3',5'-cGMP", "recombinant human cone PDE6C", ref="712394", value=0.065),
            _row("cGMP", "recombinant isoenzyme PDE5A1", ref="649549", value=0.0062),
            _row("cGMP", "platelet PDE5", ref="653097", value=0.001),
            _row("cGMP", "wild-type, pH 7.5, 30°C", ref="678243", value=0.0029, uniprot="O76074"),
            _row("cGMP", "PDE5A mutant F820A", ref="678243", variant=True),
            _row("2'-O-anthraniloyl-cGMP", "PDE5A1", ref="660000")]
    _given(monkeypatch, {"km": rows, "kcat": [_row("cGMP", "wild-type, pH 7.5, 30°C", ref="678243",
                                                   value=2.2, uniprot="O76074")]},
           natural=["3',5'-cGMP"])
    choice = defaults.choose_substrate("3.1.4.35", "Homo sapiens", isoform="PDE5A")
    # The rows naming PDE5 are taken, and so not the one naming no isoform
    # while they exist, as the resolver takes them (_partition_isoform).
    assert choice.chosen == "cGMP" and choice.rows == {"km": 2, "kcat": 1}
    assert choice.considered == 2
    assert "BRENDA also spells it 3',5'-cGMP, counted as the same compound" in choice.why
    assert "1 row of another isoform" in choice.why and "1 row of a variant" in choice.why


@pytest.mark.parametrize("a, b, same", [
    ("3',5'-cGMP", "cGMP", True), ("3′,5′-cAMP", "cAMP", True), ("2',3'-cGMP", "cGMP", False),
    ("acetyl thiocholine", "acetylthiocholine", True), ("Acetylthiocholine iodide", "acetylthiocholine", True),
    ("2-nitrophenyl-beta-D-galactopyranoside", "2-nitrophenyl beta-D-galactopyranoside", True),
    ("4-methylumbelliferyl-alpha-D-N-acetylneuraminic acid",
     "4-methylumbelliferyl alpha-D-N-acetylneuraminic acid", True),
    ("D-luciferin", "luciferin", False), ("2-deoxy-D-glucose", "D-glucose", False),
    # The benzyloxycarbonyl group under its names (Tests/compound_names.py,
    # third round's review: trypsin's Z-Gly-Pro-Arg-pNA was three compounds).
    ("Z-Gly-Pro", "N-benzyloxycarbonyl-Gly-Pro", True),
    ("N-carbobenzyloxy-Gly-Pro-Arg-p-nitroanilide", "Z-Gly-Pro-Arg-4-nitroanilide", True),
    ("brequinar sodium", "brequinar", True), ("GSSG", "glutathione disulfide", True),
    ("D-glucose", "L-glucose", False), ("N-benzoyl-DL-arginine 4-nitroanilide",
                                        "N-benzoyl-L-arginine 4-nitroanilide", False),
    # PTP1B in human: "p-nitrophenyl phosphate" and "4-nitrophenyl phosphate"
    # were two candidates; "O-acetyl" is oxygen, not ortho.
    ("p-nitrophenyl phosphate", "4-nitrophenyl phosphate", True),
    ("bis(p-nitrophenyl) phosphate", "bis(4-nitrophenyl) phosphate", True),
    ("o-nitrophenyl beta-D-galactoside", "2-nitrophenyl beta-D-galactoside", True),
    ("O-acetylserine", "2-acetylserine", False),
])
def test_spellings_of_one_compound_share_a_key_and_others_do_not(a, b, same):
    assert (defaults._group_key(a) == defaults._group_key(b)) is same


def test_spacing_and_hyphen_spellings_are_one_candidate(monkeypatch):
    """'acetyl thiocholine' was offered as a re-run option beside the chosen
    acetylthiocholine (spacing-variant-not-merged), and beta-galactosidase's
    ONPG was two candidates with split counts (A10)."""
    _given(monkeypatch, {"km": [_row("acetylthiocholine") for _ in range(4)]
                         + [_row("acetyl thiocholine"), _row("butyrylthiocholine"),
                            _row("2-nitrophenyl beta-D-galactopyranoside"),
                            _row("2-nitrophenyl-beta-D-galactopyranoside"),
                            _row("2-nitrophenyl-beta-D-galactopyranoside")]})
    choice = defaults.choose_substrate("3.1.1.7", "Homo sapiens", needs_kcat=False)
    assert choice.chosen == "acetylthiocholine" and choice.rows == {"km": 5}
    assert choice.considered == 3
    names = [o.name for o in choice.alternatives]
    assert "acetyl thiocholine" not in names
    assert ("2-nitrophenyl-beta-D-galactopyranoside", {"km": 3}) in [(o.name, o.rows)
                                                                     for o in choice.alternatives]


def test_a_cyclic_nucleotide_by_its_nucleosides_name_is_one_candidate():
    """PDE4 in human offered "adenosine 3',5'-cyclic phosphate (7 Km)" and
    "guanosine 3',5'-cyclic phosphate" as other substrates beside the
    chosen cAMP and cGMP (2026-11-12)."""
    key = defaults._group_key
    assert key("adenosine 3',5'-cyclic phosphate") == key("cAMP") == key("3',5'-cAMP")
    assert key("guanosine 3',5'-cyclic monophosphate") == key("cGMP")
    assert key("adenosine 5'-monophosphate") != key("cAMP")


def test_a_name_whose_search_takes_a_neighbours_rows_is_passed_over(monkeypatch):
    """'luciferase Michaelis-Menten' (F02): "Luciferin" was chosen as the
    natural substrate, the search asked for it also took D-luciferin's rows,
    and both constants were withheld as D-luciferin's (0.015 mM, ref 727075;
    0.19 1/s, ref 727009). D-luciferin, a stereo form of the natural
    substrate BRENDA names loosely, is chosen."""
    org = "Photinus pyralis"
    _given(monkeypatch, {
        "km": [_row("Luciferin", organism=org) for _ in range(3)]
        + [_row("D-luciferin", organism=org, ref="727075") for _ in range(5)],
        "kcat": [_row("Luciferin", organism=org)]
        + [_row("D-luciferin", organism=org, ref="727009") for _ in range(2)]},
        natural=["luciferin"])
    choice = defaults.choose_substrate("1.13.12.7", org)
    assert choice.chosen == "D-luciferin" and choice.rows == {"km": 5, "kcat": 2}
    assert choice.alternatives[0].name == "Luciferin"


def test_a_counter_ion_row_is_the_compound_not_its_neighbour(monkeypatch):
    """Acetylcholinesterase in Electrophorus electricus (F02): the Km
    returned for acetylthiocholine, 0.9 mM (ref 692653), was BRENDA's row for
    "acetylthiocholine iodide" and was withheld as another compound's. The
    resolver itself takes an iodide as the compound; so does this."""
    org = "Electrophorus electricus"
    _given(monkeypatch, {"km": [_row("acetylthiocholine", organism=org, ref="664328", value=0.084),
                                _row("acetylthiocholine iodide", organism=org, ref="692653", value=0.9),
                                _row("butyrylthiocholine", organism=org, ref="692653", value=0.9)]})
    assert defaults.neighbour_of("3.1.1.7", "km", "acetylthiocholine", org, 0.9, "692653") is None


def test_an_inhibitor_whose_every_row_is_a_mutants_is_not_chosen(monkeypatch):
    """'PTP1B with a competitive inhibitor' (B4): fluorescein arsenical
    hairpin binder had the most Ki rows, every one a CCPGCC-insertion
    mutant's (ref 691235), so the Ki was withheld; a compound with a row
    naming PTP1B (0.1 mM, ref 665518, "isoform PTP1B, pH 7.0, 25°C") is
    used. A row of another inhibition mode is not counted either."""
    flash = "fluorescein arsenical hairpin binder"
    thieno = ("(5R)-2-((carboxycarbonyl)amino)-5-((1,3-dioxo-1,3-dihydro-2H-isoindol-2-yl)methyl)-"
              "4,7-dihydro-5H-thieno(2,3-c)pyran-3-carboxylic acid")
    _given(monkeypatch, {"ki": [_row(flash, "CCPGCC-insertion mutant", ref="691235", variant=True)
                                for _ in range(7)]
                         + [_row(thieno, "isoform PTP1B, pH 7.0, 25°C", ref="665518", value=0.1),
                            _row("suramin", "noncompetitive, PTP1B", ref="600001"),
                            _row("suramin", "noncompetitive, PTP1B", ref="600002")]})
    choice = defaults.choose_inhibitor("3.1.3.48", "Homo sapiens", isoform="PTPN1", mode="competitive")
    assert choice.chosen == thieno and choice.rows == {"ki": 1}
    assert ("fluorescein arsenical hairpin binder has more Ki rows (7) but none the search can use "
            "-- 7 rows of a variant") in choice.why
    assert "counting the rows the search can use for PTPN1 and a competitive model" in choice.why
    assert dict((o.name, o.rows["ki"]) for o in choice.alternatives) == {"suramin": 0, flash: 0}


def test_a_row_whose_one_accession_is_another_protein_is_not_counted_for_the_isoform(monkeypatch):
    """A row naming no isoform in its commentary, filed under PDE5A's
    accession (O76074), is not counted for a PDE6C model."""
    _given(monkeypatch, {"km": [_row("cGMP", "pH 7.5", uniprot="O76074")] * 3
                         + [_row("cAMP", "pH 7.5")]})
    choice = defaults.choose_substrate("3.1.4.35", "Homo sapiens", needs_kcat=False, isoform="PDE6C")
    assert choice.chosen == "cAMP" and choice.rows == {"km": 1}
    assert choice.alternatives[0].rows == {"km": 0}


def test_a_tie_broken_by_name_is_said_to_be_one(monkeypatch):
    """Choice notes said "it has the most" of a pick tied with others and
    taken by name (m1): EEISEVNLDAEFRG and SEVNLDAEFR at 2 Km, 2 kcat each."""
    def two(name, ref):
        return [_row(name, ref=ref), _row(name, ref=ref)]
    _given(monkeypatch, {"km": two("SEVNLDAEFR", "1") + two("EEISEVNLDAEFRG", "2"),
                         "kcat": two("SEVNLDAEFR", "1") + two("EEISEVNLDAEFRG", "2")})
    choice = defaults.choose_substrate("3.4.23.46", "Homo sapiens")
    assert choice.chosen == "EEISEVNLDAEFRG"
    # "as many Km and kcat rows as any other" since the fifth round (it read
    # "as many as any other Km and kcat rows").
    assert "it has as many Km and kcat rows as any other" in choice.why
    assert ("it is tied on every count with SEVNLDAEFR, and was taken first by name (alphabetically), "
            "not by its data") in choice.why
    assert "the most" not in choice.why


def test_a_tie_on_rows_goes_to_the_better_referenced_and_says_so(monkeypatch):
    _given(monkeypatch, {"ki": [_row("A-inhibitor", ref="1"), _row("A-inhibitor", ref="1"),
                                _row("B-inhibitor", ref="2"), _row("B-inhibitor", ref="3")]})
    choice = defaults.choose_inhibitor("3.4.21.79", "Homo sapiens")
    assert choice.chosen == "B-inhibitor"
    assert ("it ties on rows with A-inhibitor, and is reported by more BRENDA references (2 against "
            "at most 1)") in choice.why
    assert "taken first by name" not in choice.why


def test_an_organism_tie_broken_by_name_is_said_to_be_one(monkeypatch):
    _given(monkeypatch, {"km": [_row("x", organism="Boops boops"), _row("x", organism="Sparus aurata")],
                         "kcat": [_row("x", organism="Boops boops"), _row("x", organism="Sparus aurata")]})
    choice = defaults.choose_organism("3.4.21.4", needs=("km", "kcat"))
    assert choice.chosen == "Boops boops"
    assert "as many rows as any other of those that do" in choice.why
    assert "tied on every count with Sparus aurata, and was taken first by name" in choice.why


#: The Ki table of EC 3.2.1.18 as BRENDA serves it (fetched 2026-11-11),
#: cut to one navigation link and three sub-rows of one aggregate row:
#: oseltamivir in an unidentified influenza virus (ref 700385), influenza A
#: virus H1N1 (ref 752324) and, for contrast, a human row the parser labels.
_NEURAMINIDASE_KI = """
<a href="javascript:showTable('tab49')">Ki Values</a>
<div id="tab49r60" class="row"><div id="tab49r60c0" class="cell"><span>0.00000032 - 0.000063
</span></div><div id="tab49r60c1" class="cell"><span>oseltamivir</span></div>
<div id="tab49r60c2" class="cell"><span>3 entries</span></div></div>
<div id="tab49r60sr0" class="hidden rgrey2">
<div id="tab49r60sr0c0" class="cell"><span>0.00000032
</span></div><div id="tab49r60sr0c1" class="cell"><span id="tab49r60sr0_span">oseltamivir
</span><a id="tab49r60sr0_a" href="javascript:hideRows('tab49r60',0);"><img src="./images/icon_minus_white.png" title="hide entries" alt=" hide"></a></div><div id="tab49r60sr0c2" class="cell"><span><a href="javascript:Org('11309')">unidentified influenza virus</a>
</span></div><div id="tab49r60sr0c3" class="cell"><span>-
</span></div><div id="tab49r60sr0c4" class="cell"><span>wild-type
</span></div><div id="tab49r60sr0c5" class="cell"><span><a href="./literature.php?e=3.2.1.18&r=700385" target="_blank">700385</a>
</span></div></div>
<div id="tab49r60sr1" class="hidden rgrey2">
<div id="tab49r60sr1c0" class="cell"><span>0.000024
</span></div><div id="tab49r60sr1c1" class="cell notopborder"><span id="tab49r60sr1_span" class="hidden">oseltamivir
</span></div><div id="tab49r60sr1c2" class="cell"><span><a href="javascript:Org('-7758')">influenza A virus H1N1</a>
</span></div><div id="tab49r60sr1c3" class="cell"><span><a href="javascript:Sequence2('C3W6G3')">C3W6G3</a>
</span></div><div id="tab49r60sr1c4" class="cell"><span>wild type enzyme, at 37°C, pH not specified in the publication
</span></div><div id="tab49r60sr1c5" class="cell"><span><a href="./literature.php?e=3.2.1.18&r=752324" target="_blank">752324</a>
</span></div></div>
<div id="tab49r60sr2" class="hidden rgrey2">
<div id="tab49r60sr2c0" class="cell"><span>0.5
</span></div><div id="tab49r60sr2c1" class="cell notopborder"><span class="hidden">oseltamivir
</span></div><div id="tab49r60sr2c2" class="cell"><span><a href="javascript:Org('9606')">Homo sapiens</a>
</span></div><div id="tab49r60sr2c3" class="cell"><span>-
</span></div><div id="tab49r60sr2c4" class="cell"><span>NEU2
</span></div><div id="tab49r60sr2c5" class="cell"><span>700001
</span></div></div>
"""


def test_rows_of_an_organism_that_is_no_binomial_are_read_under_their_own_cell():
    """'neuraminidase inhibited by oseltamivir' (F03): the every-organism
    parse drops a row whose organism cell is not a binomial, so the
    organism chooser never saw the influenza rows and chose Homo sapiens."""
    from types import SimpleNamespace

    import re as _re

    client = SimpleNamespace(GENERIC_ORGANISM_PATTERN=_re.compile(r"[A-Z][a-z]{2,}(?:\s[a-z]{2,}){1,2}"))
    rows = defaults._unlabelled_rows(_NEURAMINIDASE_KI, "3.2.1.18", "ki", client)
    assert [(r.compound, r.organism, r.value, r.reference_id, r.uniprot) for r in rows] == [
        ("oseltamivir", "unidentified influenza virus", 3.2e-07, "700385", None),
        ("oseltamivir", "influenza A virus H1N1", 2.4e-05, "752324", "C3W6G3")]


def test_an_organism_that_is_no_binomial_is_chosen_for_the_inhibitor_named(monkeypatch):
    flu = "influenza A virus H1N1"
    _given(monkeypatch, {
        "km": [_row("MUNANA", organism="Homo sapiens") for _ in range(9)]
        + [_row("MUNANA", organism=flu, ref="751926")],
        "kcat": [_row("MUNANA", organism="Homo sapiens"), _row("MUNANA", organism=flu, ref="751926")],
        "ki": [_row("oseltamivir", organism=flu, ref="752324"),
               _row("oseltamivir carboxylate", organism="Homo sapiens")]})
    choice = defaults.choose_organism("3.2.1.18", inhibitor="oseltamivir", needs=("km", "kcat", "ki"))
    assert choice.chosen == flu and choice.rows == {"km": 1, "kcat": 1, "ki": 1}


def test_table_rows_for_every_organism_include_the_unlabelled_ones(monkeypatch):
    from types import SimpleNamespace

    import re as _re

    stub = SimpleNamespace(
        GENERIC_ORGANISM_PATTERN=_re.compile(r"[A-Z][a-z]{2,}(?:\s[a-z]{2,}){1,2}"),
        parse_brenda_km_html=lambda *a, **k: [], parse_brenda_turnover_html=lambda *a, **k: [],
        parse_brenda_ki_html=lambda *a, **k: [],
        fetch_brenda_html=lambda ec: _NEURAMINIDASE_KI)
    monkeypatch.setattr(defaults, "_client", lambda: stub)
    monkeypatch.setattr(defaults, "_PARSED", {})
    assert {r.organism for r in defaults.table_rows("3.2.1.18", "ki", None)} == {
        "unidentified influenza virus", "influenza A virus H1N1"}


def test_a_malformed_ec_number_is_not_fetched_and_exits_3(monkeypatch, capsys):
    """`--ec abc` was fetched from BRENDA and answered "BRENDA holds no Km rows
    under EC abc" (F17)."""
    def no_fetch(ec):
        raise AssertionError(f"fetched {ec!r}")

    monkeypatch.setattr(defaults, "_page", no_fetch)
    for ec in ("abc", "1.1.1", "2.7.1.1.1"):
        assert defaults.main(["--ec", ec, "--json"]) == 3
        printed = json.loads(capsys.readouterr().out)
        assert printed["choice"] is None
        assert printed["note"].startswith(f"{ec!r} is not an EC number")


def test_the_contract_names_every_field_a_choice_carries():
    """The chosen option's rows and the `instead` clause reach the Studio
    (F18): the TypedDict, CONTRACT.md and the TypeScript mirror name them."""
    from caterva.studio import contract

    choice = defaults.Choice("substrate", "fenthion", "why", (defaults.Option("x", {"km": 1}),), 2,
                             {"km": 4, "kcat": 0}, instead="'midazolam' is not one")
    shape = choice.to_json()
    assert set(shape) == contract.SearchChoice.__required_keys__ | contract.SearchChoice.__optional_keys__
    assert {"rows", "instead"} <= contract.SearchChoice.__optional_keys__, "results saved before have neither"
    assert shape["rows"] == {"km": 4, "kcat": 0} and shape["instead"] == "'midazolam' is not one"
    root = Path(__file__).resolve().parents[2]
    doc = (root / "docs" / "studio" / "CONTRACT.md").read_text()
    assert "alternatives, considered, rows, instead}" in doc
    ts = (root / "Science-Agent-Pipeline" / "artifacts" / "caterva-studio" / "src" / "api" / "types.ts").read_text()
    block = ts[ts.index("export interface SearchChoice"):]
    block = block[:block.index("\n}")]
    assert "rows?: Record<string, number>;" in block and "instead?: string | null;" in block


def test_each_spelling_is_judged_as_the_search_judges_the_rows_it_reaches(monkeypatch):
    """PTP1B in human: "4-nitrophenyl phosphate" has one row naming PTP1B
    (1.4 mM, ref 663621) and "p-nitrophenyl phosphate" rows naming no
    isoform. Asked for either spelling, the search takes that spelling's own
    rows, so the one row naming PTP1B does not set aside the other
    spelling's rows; and a substrate whose searched spelling has rows naming
    PTP1B (6,8-difluoro-4-methylumbelliferyl phosphate, ref 730324) ranks
    first, since EC 3.1.3.48 is every protein-tyrosine phosphatase and a row
    naming none may be any of them."""
    difmup = "6,8-difluoro-4-methylumbelliferyl phosphate"
    km = ([_row("4-nitrophenyl phosphate", "isoform PTP1B, pH 7.0", ref="663621", value=1.4)]
          + [_row("p-nitrophenyl phosphate", "pH 7.0, 30°C", ref=str(680000 + i)) for i in range(4)]
          + [_row(difmup, "isoform PTP1B, pH 7.2", ref="730324"),
             _row(difmup, "isoform PTP1B, 25°C", ref="730325")])
    kcat = [_row(n, c, ref=r) for n, c, r in ((difmup, "isoform PTP1B", "730324"),
                                               ("p-nitrophenyl phosphate", "pH 7.0", "680000"))]
    _given(monkeypatch, {"km": km, "kcat": kcat})
    choice = defaults.choose_substrate("3.1.3.48", "Homo sapiens", isoform="PTPN1")
    assert choice.chosen == difmup
    assert "substrates whose rows do not name PTPN1 rank after it" in choice.why
    (npp,) = [o for o in choice.alternatives if "nitrophenyl" in o.name]
    assert npp.name == "p-nitrophenyl phosphate" and npp.rows == {"km": 5, "kcat": 1}


def test_an_inhibitor_tied_on_every_count_is_not_said_to_have_the_most(monkeypatch):
    """Granzyme B in human, competitive: six inhibitors at one usable Ki row
    each, one reference each; the note said "it has the most (1 Ki row)" of
    the one the name broke the tie for (m1)."""
    _given(monkeypatch, {"ki": [_row("B-inhibitor", "competitive", ref="2"),
                                _row("A-inhibitor", "competitive", ref="1")]})
    choice = defaults.choose_inhibitor("3.4.21.79", "Homo sapiens", mode="competitive")
    assert choice.chosen == "A-inhibitor"
    assert "it is reported by as many papers as any other (1 BRENDA reference, 1 Ki row)" in choice.why
    assert "the most" not in choice.why
    assert "taken first by name (alphabetically)" in choice.why


def test_a_merged_compound_says_which_spelling_the_search_takes(monkeypatch):
    """PTP1B in human: "p-nitrophenyl phosphate" and "4-nitrophenyl
    phosphate" are counted as one compound. Until the third round's review
    the search, asked for one spelling, took only that spelling's rows, and
    the note said so; it then passed over the rows naming PTP1B (P18031),
    filed under the other spelling. The search now matches every spelling
    of the compound (brenda_client.substrate_matches, compound_names), so
    the note says only that the spellings were merged."""
    km = ([_row("p-nitrophenyl phosphate", "pH 7.0", ref=str(680000 + i)) for i in range(3)]
          + [_row("4-nitrophenyl phosphate", "pH 7.0", ref="95007")])
    _given(monkeypatch, {"km": km, "kcat": [_row("p-nitrophenyl phosphate", "pH 7.0", ref="680000")]})
    choice = defaults.choose_substrate("3.1.3.48", "Homo sapiens")
    assert choice.chosen == "p-nitrophenyl phosphate" and choice.rows == {"km": 4, "kcat": 1}
    assert "BRENDA also spells it 4-nitrophenyl phosphate, counted as the same compound" in choice.why
    assert "takes the rows spelled so" not in choice.why


def test_an_organism_with_a_ki_for_the_inhibitor_named_ranks_first(monkeypatch):
    """'neuraminidase inhibited by zanamivir' was modelled as human
    neuraminidase (33 Km, 1 kcat) with the zanamivir Ki a placeholder, though
    BRENDA holds influenza zanamivir Ki rows (2026-11-12)."""
    flu = "unidentified influenza virus"
    _given(monkeypatch, {
        "km": [_row("MUNANA", organism="Homo sapiens") for _ in range(9)]
        + [_row("fetuin", organism=flu, ref="171119")],
        "kcat": [_row("MUNANA", organism="Homo sapiens")],
        "ki": [_row("zanamivir", organism=flu, ref="700385")]})
    choice = defaults.choose_organism("3.2.1.18", inhibitor="zanamivir", needs=("km", "kcat", "ki"))
    assert choice.chosen == flu
    assert "organisms with no Ki row for zanamivir, the inhibitor named, rank after" in choice.why
    assert choice.alternatives[0].name == "Homo sapiens"


def test_a_commentary_cell_read_as_a_compound_is_not_a_candidate():
    """HDAC8 offered "pH and temperature not specified in the publication"
    as an inhibitor with 3 Ki rows (2026-11-12)."""
    assert not defaults._is_compound("pH and temperature not specified in the publication", "")
    assert not defaults._is_compound("temperature not specified in the publication", "")
    assert not defaults._is_compound("pH 7.5, 25 C", "pH 7.5, 25 C")
    assert defaults._is_compound("phenyl butyric acid", "pH and temperature not specified in the publication")
    assert defaults._is_compound("pHMB", "")


def test_a_row_read_cell_by_cell_is_flagged_as_the_parser_would_flag_it():
    """The zanamivir Ki of "influenza A virus" (6e-08 mM, below the parser's
    floor) was counted for that organism, and the search then had no usable
    row (2026-11-12)."""
    from types import SimpleNamespace

    client = SimpleNamespace(KM_PLAUSIBLE_MIN_MM=1e-7, KM_PLAUSIBLE_MAX_MM=1e4, KI_PLAUSIBLE_MIN_MM=1e-12,
                             KCAT_PLAUSIBLE_MIN_PER_S=1e-6, KCAT_PLAUSIBLE_MAX_PER_S=1e7)
    # A Ki is held to the parser's Ki floor, not the Km's: the influenza A
    # zanamivir Ki (6e-08 mM) is a row the search uses (fifth round, R5V1-07).
    assert not defaults._implausible(client, "ki", 6e-08, "")
    assert defaults._implausible(client, "ki", 1e-13, "")
    assert defaults._implausible(client, "km", 6e-08, "")
    assert defaults._implausible(client, "kcat", 1e8, "")
    assert defaults._implausible(client, "km", 0.5, "kcat 5 s-1, pH 7")
    assert not defaults._implausible(client, "kcat", 0.5, "kcat 5 s-1, pH 7")


def test_an_inhibitor_tie_goes_to_the_compound_measured_more_widely(monkeypatch):
    """'neuraminidase with an inhibitor': 23 compounds of influenza A virus
    tie at one Ki row from one paper, and the first by name was a triazole
    analogue (Ki 0.06 mM) beside oseltamivir carboxylate (2026-11-12)."""
    flu = "influenza A virus"
    triazole = "(1R/S,4R,5R)-4-acetamido-5-(1-ethylpropoxy)-3-triazolyl-cyclohex-2-ene-1-carboxylic acid"
    _given(monkeypatch, {"ki": [
        _row(triazole, organism=flu, ref="717970"),
        _row("oseltamivir carboxylate", organism=flu, ref="696609"),
        _row("oseltamivir carboxylate", organism="unidentified influenza virus", ref="700385"),
        _row("oseltamivir carboxylate", organism="influenza B virus", ref="700386")]})
    choice = defaults.choose_inhibitor("3.2.1.18", flu)
    assert choice.chosen == "oseltamivir carboxylate"
    assert ("ties on rows and references with " + triazole) in choice.why
    assert "is reported more widely under EC 3.2.1.18, counting every organism, than it does (3 against at most 1)" \
        in choice.why
    assert "alphabetically" not in choice.why


def test_an_organism_that_is_no_binomial_keeps_only_its_own_rows(monkeypatch):
    """'neuraminidase with an inhibitor': the parse for "influenza A virus"
    also returned "influenza A virus H1N1" rows, oseltamivir was chosen on
    one, and the search, finding it in two organisms, settled on none
    (2026-11-12)."""
    from types import SimpleNamespace

    def parsed(substrate, organism, value, ref):
        return SimpleNamespace(substrate=substrate, organism=organism, conditions="",
                               km_value=value, reference_id=ref, uniprot=None, variant=None,
                               flagged=False)

    rows = [parsed("oseltamivir", "influenza A virus H1N1", 2.4e-05, "752324"),
            parsed("oseltamivir carboxylate", "influenza A virus", 1e-07, "696609")]
    stub = SimpleNamespace(parse_brenda_km_html=lambda *a, **k: [],
                           parse_brenda_turnover_html=lambda *a, **k: [],
                           parse_brenda_ki_html=lambda *a, **k: rows,
                           fetch_brenda_html=lambda ec: "<html></html>")
    monkeypatch.setattr(defaults, "_client", lambda: stub)
    monkeypatch.setattr(defaults, "_PARSED", {})
    assert [r.compound for r in defaults.table_rows("3.2.1.18", "ki", "influenza A virus")] == [
        "oseltamivir carboxylate"]


# ---------------------------------------------------------------------------
# Merge of the rows and chooser rounds (2026-11-12): the chooser ranks by
# the rows the resolver prefers
# ---------------------------------------------------------------------------


def test_a_row_of_a_construct_an_effector_or_a_k05_is_not_the_enzymes_own():
    """`_own` reads a row as the resolver does (row_form.construct_of,
    row_form.half_saturation, an effector named present): the resolver
    passes such rows over when the compound has a row of the native enzyme's
    own constant, so the chooser counts which compounds have one."""
    assert defaults._own("km", "wild-type, pH 7.5, 25°C")
    assert not defaults._own("km", "isolated C-domain, pH 7.5")        # ACE, ref 650001
    assert not defaults._own("km", "K0.5 value, Hill coefficient 1.8")  # GCK, ref 739603
    assert defaults._own("kcat", "K0.5 value, Hill coefficient 1.8")   # a kcat is no K0.5
    assert not defaults._own("km", "in presence of 0.02 mM activator LY-2121260")
    assert defaults._own("km", "in the presence of 100 mM K+")         # an ion is not an addition


def test_a_compound_whose_every_km_row_is_altered_ranks_after_one_with_the_enzymes_own(monkeypatch):
    """A compound with more rows, every one a construct's, does not outrank
    one measured on the native enzyme: the search would carry a construct's
    constant for the first and the enzyme's own for the second."""
    altered = [defaults._Row("Z-substrate", "Homo sapiens", "chimeric enzyme", 1.0, str(i), None,
                             own=False) for i in range(4)]
    native = [_row("Y-substrate", "wild-type", ref="2")]
    _given(monkeypatch, {"km": altered + native, "kcat": []})
    choice = defaults.choose_substrate("3.4.15.1", "Homo sapiens", needs_kcat=False)
    assert choice.chosen == "Y-substrate"
    assert "Z-substrate has more rows, but each measured a construct" in choice.why
    assert choice.alternatives[0].name == "Z-substrate"
