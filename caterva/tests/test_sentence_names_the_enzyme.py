"""A description that names an enzyme is searched for it (ADR 0181).

WHY THESE TESTS
---------------
On 2026-11-02 `caterva compose "Michaelis-Menten kinetics of human
hexokinase on glucose"` built the model on the motif library's placeholder
constants and said "no enzyme was named", and "hexokinase glucose human" was
refused as no shape at all, while the same words as flags reached BRENDA's
Km and kcat. These hold the
sentence to the flags' answer, and hold the reader to what it must never do:
read a class word, a typo, a fragment or a lower-case English word as an
enzyme, pick one of several, ground a cascade in one enzyme, or take a word
as the substrate that BRENDA does not list for that enzyme.

Offline throughout: the finder's committed index, and the committed BRENDA
page and HTTP answers for human hexokinase (studio_kinetics_offline.py). A
test that needs any other page has the network made impossible, so a live
call fails it instead of passing by luck.
"""
from __future__ import annotations

import argparse
import contextlib
import io

import pytest

from caterva.compose.organisms import normalise_organism
from caterva.enzymes.sentence import match_substrate, read_sentence
from studio_kinetics_offline import context, hexokinase_offline, run_cli

FLAGS = ["--no-simulate", "--no-analysis", "--no-ranking"]
#: The flags' answer on the recorded page: a Km and a kcat from one paper,
#: ref 739603, the one paper holding a row of each among the rows chosen
#: from (fallback_logic.resolve_kinetic_pair, ADR 0182).
KM_ROW = "| `reaction_Km` | 6.3 mM | literature (Homo sapiens) | BRENDA ref 739603 |"
KCAT_ROW = "| `reaction_kcat` | 40.1 1/s | literature (Homo sapiens) | BRENDA ref 739603 |"


def _main(argv):
    from caterva.compose.__main__ import main

    return run_cli(main, argv)


@contextlib.contextmanager
def _no_network(monkeypatch):
    """Every real send raises. Returns the URLs attempted."""
    import httpx

    attempts = []

    def refuse(self, request):
        attempts.append(str(request.url))
        raise httpx.ConnectError("network disabled in this test", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    yield attempts


# ---------------------------------------------------------------------------
# read_sentence: the enzyme
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text, ec, typed, organism, substrate", [
    ("Michaelis-Menten kinetics of human hexokinase on glucose", "2.7.1.1", "hexokinase", "Homo sapiens", "glucose"),
    ("hexokinase glucose human", "2.7.1.1", "hexokinase", "Homo sapiens", "glucose"),
    ("yeast alcohol dehydrogenase with ethanol", "1.1.1.1", "alcohol dehydrogenase",
     "Saccharomyces cerevisiae", "ethanol"),
    ("E. coli beta-galactosidase lactose", "3.2.1.23", "beta-galactosidase", "Escherichia coli", "lactose"),
    ("EC 2.7.1.1 glucose", "2.7.1.1", "EC 2.7.1.1", None, "glucose"),
    ("2.7.1.1 with glucose", "2.7.1.1", "2.7.1.1", None, "glucose"),
])
def test_the_sentences_people_type_are_read(text, ec, typed, organism, substrate):
    reading = read_sentence(text)
    assert (reading.ec, reading.enzyme_text, reading.organism) == (ec, typed, organism)
    assert reading.substrate_candidates[0] == substrate
    assert reading.ambiguity is None


def test_the_notes_say_what_was_read_as_what():
    notes = read_sentence("Michaelis-Menten kinetics of human hexokinase on glucose").notes()
    assert notes == [
        "Read 'hexokinase' in your description as EC 2.7.1.1 (hexokinase): accepted name matches exactly.",
        "Read 'human' in your description as Homo sapiens.",
    ]


def test_a_name_that_is_several_enzymes_is_an_ambiguity_not_a_skip():
    reading = read_sentence("lactate dehydrogenase pyruvate")
    assert reading.ec is None
    assert reading.ambiguity is not None and reading.enzyme_text == "lactate dehydrogenase"
    ecs = [c.ec for c in reading.ambiguity.candidates]
    assert ecs[:2] == ["1.1.1.27", "1.1.1.28"]
    # Pyruvate is still a candidate substrate: the refusal is about the enzyme.
    assert reading.substrate_candidates == ("pyruvate",)


@pytest.mark.parametrize("text", [
    "three step MAP kinase cascade",
    "a kinase and a phosphatase",
    "A kinase and a phosphatase",
    "protein kinase",
    "MAP kinase",
    "a dehydrogenase",
    "an enzyme",
    "three step phosphorylation cascade",
    "a toggle switch between two repressors",
])
def test_a_class_word_is_never_an_enzyme_and_never_an_ambiguity(text):
    # "protein kinase" is an exact alternative name of histidine kinase
    # (EC 2.7.13.3) and "MAP kinase" of EC 2.7.11.24. The finder now refuses
    # the first as a family word (its rule f); the class-word guard keeps
    # both out of a sentence whatever the finder does with them.
    reading = read_sentence(text)
    assert reading.ec is None and reading.ambiguity is None and not reading.names_enzyme, reading


@pytest.mark.parametrize("text", [
    "peptidase",   # resolves to L-peptidase once the L- is set aside
    "protein",     # resolves to L-protein the same way
    "hexokinas",   # a typo: did-you-mean, never a reading
    "ace inhibitor",  # ACE is a confirmed abbreviation; "ace" in a sentence is a word
    "HK on glucose",  # an abbreviation several enzymes go by
])
def test_only_an_exact_name_or_number_is_read(text):
    reading = read_sentence(text)
    assert reading.ec is None, reading


def test_a_name_met_only_with_its_stereo_label_set_aside_is_said_not_read():
    # Not a class word, so only the exact-match rule keeps it out.
    reading = read_sentence("lysine oxidase on lysine")
    assert reading.ec is None and reading.near[1] == "1.4.3.14"
    assert reading.notes() == [
        "The words 'lysine oxidase' in your description match EC 1.4.3.14 (L-lysine oxidase) only once "
        "stereo labels or a parenthesised word are set aside, which is not taken as naming it (pass "
        "--subject 1.4.3.14 if it is the enzyme you mean)."]


def test_a_confirmed_abbreviation_typed_as_one_is_read():
    assert read_sentence("PKA with ATP").ec == "2.7.11.11"


def test_two_enzymes_named_ground_neither():
    reading = read_sentence("glucokinase and hexokinase")
    assert reading.ec is None and reading.ambiguity is None
    assert {ec for _, ec, _ in reading.other_enzymes} == {"2.7.1.2", "2.7.1.1"}
    assert "no enzyme was read from it" in " ".join(reading.notes())


def test_a_number_that_is_not_an_ec_number_is_not_read_as_one():
    reading = read_sentence("2.5 mM glucose hexokinase")
    assert reading.ec == "2.7.1.1" and reading.enzyme_text == "hexokinase"


def test_the_inhibitor_is_read_after_inhibition_words():
    reading = read_sentence("competitive inhibition of acetylcholinesterase by (-)-huperzine A in human "
                            "with acetylcholine")
    assert reading.ec == "3.1.1.7" and reading.organism == "Homo sapiens"
    assert reading.inhibitor_text == "(-)-huperzine A"
    assert reading.substrate_candidates[0] == "acetylcholine"


# ---------------------------------------------------------------------------
# read_sentence: the organism, through the one normaliser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text, typed, binomial", [
    ("hexokinase in humans", "humans", "Homo sapiens"),
    ("human's hexokinase", "human's", "Homo sapiens"),
    ("hexokinase in H. sapiens", "H. sapiens", "Homo sapiens"),
    ("hexokinase (human) on glucose.", "human", "Homo sapiens"),
    ("E.coli beta-galactosidase", "E.coli", "Escherichia coli"),
    ("baker's yeast alcohol dehydrogenase", "baker's yeast", "Saccharomyces cerevisiae"),
    ("hexokinase from Homo sapiens", "Homo sapiens", "Homo sapiens"),
    ("hexokinase in Thermus thermophilus", "Thermus thermophilus", "Thermus thermophilus"),
])
def test_an_organism_is_read_the_way_the_flag_reads_it(text, typed, binomial):
    reading = read_sentence(text)
    assert (reading.organism_text, reading.organism) == (typed, binomial)


def test_two_organisms_named_give_none():
    reading = read_sentence("human and mouse hexokinase")
    assert reading.organism is None
    assert [b for _, b in reading.organisms_named] == ["Homo sapiens", "Mus musculus"]


def test_a_capitalised_sentence_start_is_not_a_binomial():
    assert read_sentence("Competitive inhibition of hexokinase").organism is None


@pytest.mark.parametrize("typed", ["H. sapiens", "h. sapiens", "S. cerevisiae", "mice"])
def test_the_flag_reads_what_the_finder_reads(typed):
    from caterva.enzymes.index import ORGANISMS, organism_code

    organism, note = normalise_organism(typed)
    assert organism == ORGANISMS[organism_code(typed)][0]
    assert note is not None and organism in note


# ---------------------------------------------------------------------------
# match_substrate: only what BRENDA lists
# ---------------------------------------------------------------------------

HUMAN_HK = ["ATP", "D-glucose", "D-mannose", "D-fructose", "2-deoxy-D-glucose", "D-glucosamine",
            "2-deoxyglucose", "CTP"]


def test_glucose_is_d_glucose_when_brenda_lists_one_glucose():
    match = match_substrate(["glucose"], HUMAN_HK)
    assert (match.name, match.typed, match.prefix_set_aside) == ("D-glucose", "glucose", True)


def test_an_exact_name_is_taken_as_written():
    match = match_substrate(["ATP"], HUMAN_HK)
    assert (match.name, match.prefix_set_aside) == ("ATP", False)


def test_two_glucoses_are_a_choice():
    match = match_substrate(["glucose"], ["alpha-D-glucose", "beta-D-glucose", "ATP"])
    assert match.name is None
    assert {n for _, n in match.rivals} == {"alpha-D-glucose", "beta-D-glucose"}


def test_two_substrates_named_are_a_choice():
    match = match_substrate(["glucose", "ATP"], HUMAN_HK)
    assert match.name is None and {n for _, n in match.rivals} == {"D-glucose", "ATP"}


def test_a_word_brenda_does_not_list_is_not_a_substrate():
    assert match_substrate(["cascade", "oscillator"], HUMAN_HK).name is None


# ---------------------------------------------------------------------------
# The command: the sentence reaches the flags' answer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("description", [
    "hexokinase glucose human",
    "Michaelis-Menten kinetics of human hexokinase on glucose",
])
def test_the_sentence_reaches_brendas_values_for_human_hexokinase(description):
    with hexokinase_offline():
        code, out, err = _main([description, *FLAGS])
    assert code == 0, err
    assert KM_ROW in out and KCAT_ROW in out
    assert "- Read 'hexokinase' in your description as EC 2.7.1.1 (hexokinase): accepted name matches exactly." in out
    assert "- Read 'human' in your description as Homo sapiens." in out
    assert ("- Read 'glucose' in your description as the substrate D-glucose, which BRENDA lists for "
            "EC 2.7.1.1 for Homo sapiens") in out
    assert "no enzyme was named" not in out.lower()


def test_a_sentence_with_no_mechanism_says_it_was_read_as_michaelis_menten():
    with hexokinase_offline():
        code, out, _ = _main(["hexokinase glucose human", *FLAGS])
    assert code == 0
    assert ("Your description named an enzyme ('hexokinase') and no mechanism this grammar recognises, "
            "so its shape was read as Michaelis-Menten") in out
    assert "Recognised as: **michaelis menten**" in out


def test_the_sentence_and_the_flags_give_the_same_constants():
    with hexokinase_offline():
        _, by_sentence, _ = _main(["Michaelis Menten of human hexokinase on glucose", *FLAGS])
        _, by_flags, _ = _main(["Michaelis Menten", "--subject", "2.7.1.1", "--organism", "human",
                                "--substrate", "D-glucose", *FLAGS])
    rows = lambda text: [l for l in text.splitlines() if l.startswith("| `reaction_K") or l.startswith("| `reaction_k")]
    assert rows(by_sentence) == rows(by_flags) and KM_ROW in rows(by_flags)


def _km_rows_per_ec(monkeypatch, rows_by_ec):
    """`defaults.table_rows` answering `rows_by_ec[ec]` Km rows for any
    organism, so which EC the data singles out is decided offline."""
    from caterva.compose import defaults

    def table_rows(ec, table, organism):
        n = rows_by_ec.get(ec, 0) if table == "km" else 0
        return tuple(defaults._Row("pyruvate", organism, "") for _ in range(n))

    monkeypatch.setattr(defaults, "table_rows", table_rows)


def test_a_name_that_is_several_enzymes_with_rows_for_both_refuses_with_the_command_to_type(
        monkeypatch):
    """Both readings of the name have measurements in the organism: that is a
    question only the user can answer, refused as before (ADR 0181), even
    though ADR 0182 lets the data break a tie it can break."""
    _km_rows_per_ec(monkeypatch, {"1.1.1.27": 40, "1.1.1.28": 2})
    with _no_network(monkeypatch) as attempts:
        code, out, err = _main(["lactate dehydrogenase pyruvate human", *FLAGS])
    assert attempts == [], "an ambiguous name must not be searched for"
    assert code == 3 and "refusal(s)" in err
    assert "EC 1.1.1.27 L-lactate dehydrogenase" in out and "EC 1.1.1.28 D-lactate dehydrogenase" in out
    assert 'caterva compose "lactate dehydrogenase pyruvate human" --subject 1.1.1.27' in out
    assert "no enzyme was named" not in out.lower()
    assert "Caterva used EC" not in out


def test_a_name_the_data_singles_out_is_taken_and_the_others_named(monkeypatch):
    """ADR 0182: of the two enzymes 'lactate dehydrogenase' matches best,
    only one has Km rows in the organism, so it is the subject, as a choice
    the report states with the other candidate and its rows."""
    import caterva.compose.__main__ as cli

    _km_rows_per_ec(monkeypatch, {"1.1.1.27": 12})
    monkeypatch.setattr(cli, "brenda_km_substrates", lambda ec, org: {"pyruvate": 12})
    args = _args(description="lactate dehydrogenase with pyruvate in human")
    read = cli.read_description(args, err=io.StringIO())
    assert read.name_refusal is None
    assert (args.subject, args.organism, args.substrate) == ("1.1.1.27", "Homo sapiens", "pyruvate")
    (choice,) = read.choices
    assert choice.role == "enzyme" and choice.chosen == "1.1.1.27"
    assert choice.note() == (
        "Caterva used EC 1.1.1.27: your description names 'lactate dehydrogenase', which is not one "
        "enzyme; L-lactate dehydrogenase is used because it is the only one of the 2 enzymes the "
        "name matches best with Km rows in Homo sapiens (12 Km rows). Others: EC 1.1.1.28 (D-lactate "
        "dehydrogenase) (no rows). Pass --subject EC to model another.")


def test_a_class_word_is_never_settled_by_the_data(monkeypatch):
    """'kinase' is not a few readings of one name; nothing is looked up."""
    from caterva.compose import defaults

    looked = []
    monkeypatch.setattr(defaults, "table_rows", lambda *a: looked.append(a) or ())
    import caterva.compose.__main__ as cli

    read = cli.read_description(_args(description="Michaelis-Menten kinetics of a kinase"),
                                err=io.StringIO())
    assert looked == [] and read.choices == []


def test_the_studio_reads_the_sentence_the_way_the_terminal_does(tmp_path):
    from caterva.studio.adapters import compose as adapter

    with hexokinase_offline():
        outcome = adapter.run({"description": "hexokinase glucose human"}, context(tmp_path))
    assert outcome.exit_code == 0
    assert KM_ROW in outcome.result["report_markdown"]
    km = next(p for p in outcome.result["model"]["parameters"] if p["id"] == "reaction_Km")
    assert km["value"] == 6.3 and km["provenance"]["citation"]["reference_id"] == "739603"


def test_the_export_carries_the_values_the_report_carries():
    with hexokinase_offline():
        code, out, err = _main(["hexokinase glucose human", "--export", "csv"])
    assert code == 0, err
    assert "reaction_Km" in out and "739603" in out


def test_antimony_compiles_the_shape_the_report_shows_with_the_values_it_carries():
    """`--antimony` searched nothing and printed the library's placeholders
    with no comment, while the report beside it carried BRENDA's values
    (2026-11-11). It now carries the report's numbers, each origin said."""
    with hexokinase_offline():
        code, out, _ = _main(["hexokinase glucose human", "--antimony"])
    assert code == 0 and "reaction_Km" in out
    assert "#   reaction_Km = 6.3 mM: BRENDA ref 739603 (Homo sapiens)" in out
    assert "#   reaction_kcat = 40.1 1/s: BRENDA ref 739603 (Homo sapiens)" in out
    assert "  reaction_Km = 6.3;" in out and "  reaction_kcat = 40.1;" in out, \
        "the compiled source carries the measured values, not the library's 0.1 and 100"


def test_antimony_without_an_enzyme_says_every_constant_is_a_placeholder(monkeypatch):
    with _no_network(monkeypatch) as attempts:
        code, out, _ = _main(["Michaelis-Menten with a competitive inhibitor", "--antimony"])
    assert code == 0 and attempts == []
    assert "#   reaction_Ki: PLACEHOLDER, the motif library's illustrative value -- no enzyme was " \
           "named, so nothing was searched" in out


# ---------------------------------------------------------------------------
# What does not change, and what is no longer dropped
# ---------------------------------------------------------------------------


def test_a_cascade_is_not_grounded_in_the_enzyme_a_sentence_names(monkeypatch):
    with _no_network(monkeypatch) as attempts:
        code, out, _ = _main(["three step phosphorylation cascade of hexokinase", *FLAGS])
    assert attempts == [] and code == 0
    assert "The enzyme your description names ('hexokinase', EC 2.7.1.1) was not applied" in out
    assert "ADR 0076" in out
    assert "no enzyme was named" not in out.lower()
    assert "Subject named" not in out


@pytest.mark.parametrize("description, placeholders", [
    ("three step phosphorylation cascade", "all 12 rate constant(s) are the motif library's illustrative values"),
    ("a toggle switch between two repressors", "all 6 rate constant(s) are the motif library's illustrative values"),
])
def test_a_mechanism_with_no_enzyme_named_is_unchanged(monkeypatch, description, placeholders):
    with _no_network(monkeypatch) as attempts:
        code, out, err = _main([description, *FLAGS])
    assert attempts == [] and code == 0 and err == ""
    assert placeholders in out
    assert "**Nothing was searched for.** No enzyme was named" in out
    assert "in your description" not in out


def test_an_organism_and_substrate_with_no_enzyme_are_said_to_be_unused(monkeypatch):
    with _no_network(monkeypatch):
        code, out, err = _main(["three step phosphorylation cascade", "--organism", "human",
                                "--substrate", "glucose", *FLAGS])
    assert code == 0
    text = ("--organism Homo sapiens and --substrate glucose were given, but no enzyme was named, by "
            "--subject or in the description, so nothing was searched for and they were not used.")
    assert f"Not used: {text}" in err
    assert text in out


def test_an_enzyme_and_a_mechanism_the_grammar_lacks_is_refused_with_the_way_out(monkeypatch):
    with _no_network(monkeypatch):
        code, out, err = _main(["hexokinase oscillator", *FLAGS])
    assert code == 3 and out == ""
    assert "also 'oscillator', which is not a mechanism this grammar builds" in err
    assert 'caterva compose "Michaelis Menten" --subject 2.7.1.1' in err


def test_a_named_pathway_is_still_refused_as_one(monkeypatch):
    with _no_network(monkeypatch):
        code, _, err = _main(["glycolysis with hexokinase", *FLAGS])
    assert code == 3 and "is a named pathway, not a shape" in err


# ---------------------------------------------------------------------------
# Flags win
# ---------------------------------------------------------------------------


def _args(**fields):
    base = {"description": "", "subject": None, "organism": None, "substrate": None, "inhibitor": None}
    base.update(fields)
    return argparse.Namespace(**base)


def test_every_flag_wins_over_the_sentence(monkeypatch):
    import caterva.compose.__main__ as cli

    looked_up = []
    monkeypatch.setattr(cli, "brenda_km_substrates", lambda ec, org: looked_up.append(ec) or {"D-glucose": 1})
    args = _args(description="competitive inhibition of human hexokinase by mannose on glucose",
                 subject="2.7.1.2", organism="Mus musculus", substrate="D-fructose", inhibitor="ADP")
    read = cli.read_description(args, err=io.StringIO())
    assert (args.subject, args.organism, args.substrate, args.inhibitor) == (
        "2.7.1.2", "Mus musculus", "D-fructose", "ADP")
    assert looked_up == [], "a substrate flag means the description's words are not looked up"
    text = " ".join(read.notes)
    assert "--subject 2.7.1.2 was used, because a flag wins over the description" in text
    assert "--organism Mus musculus was used, because a flag wins over the description" in text


def test_the_sentence_fills_only_what_no_flag_set(monkeypatch):
    import caterva.compose.__main__ as cli

    monkeypatch.setattr(cli, "brenda_km_substrates", lambda ec, org: {"D-glucose": 25, "ATP": 106})
    args = _args(description="hexokinase on glucose", organism="Mus musculus")
    read = cli.read_description(args, err=io.StringIO())
    assert (args.subject, args.organism, args.substrate) == ("2.7.1.1", "Mus musculus", "D-glucose")
    assert any("as the substrate D-glucose" in n for n in read.notes)


def test_with_subject_and_no_substrate_the_description_supplies_it(monkeypatch):
    """The task's last case: --subject given, the description says glucose."""
    import caterva.compose.__main__ as cli

    monkeypatch.setattr(cli, "brenda_km_substrates", lambda ec, org: {"D-glucose": 25})
    args = _args(description="Michaelis Menten on glucose", subject="2.7.1.1", organism="Homo sapiens")
    cli.read_description(args, err=io.StringIO())
    assert args.substrate == "D-glucose"


def test_an_unreadable_substrate_list_takes_nothing_and_says_so(monkeypatch):
    import caterva.compose.__main__ as cli

    monkeypatch.setattr(cli, "brenda_km_substrates", lambda ec, org: None)
    args = _args(description="hexokinase on glucose")
    read = cli.read_description(args, err=io.StringIO())
    assert args.substrate is None
    assert any("could not be read, so no word of your description" in n for n in read.notes)


# ---------------------------------------------------------------------------
# Review of 2026-11-03: a word out of a compound's name, a "by" that is not
# an inhibitor, an organism misspelt
# ---------------------------------------------------------------------------

#: Every one of these grounded the model in another substrate's BRENDA row,
#: citation and all, because one word of the compound's name matched it:
#: D-glucose's Km 6.0 mM (ref 641068, the pick then) for glucose 6-phosphate, 2-deoxy
#: glucose and "glucose analogues"; D-fructose's 11.4 mM (ref 640237) for
#: fructose 1,6-bisphosphate; D-glucosamine's 0.5 mM (ref 640230) for
#: N-acetyl glucosamine.
COMPOUND_NAMES = [
    "glucose 6-phosphate", "2 deoxy glucose", "glucose analogues", "fructose 1,6-bisphosphate",
    "N-acetyl glucosamine",
]


@pytest.mark.parametrize("compound", COMPOUND_NAMES)
def test_a_word_out_of_a_longer_compound_name_is_not_a_candidate(compound):
    reading = read_sentence(f"Michaelis-Menten kinetics of human hexokinase on {compound}")
    assert reading.substrate_candidates == (compound,)
    assert match_substrate(reading.substrate_candidates, HUMAN_HK).name is None


@pytest.mark.parametrize("compound", COMPOUND_NAMES)
def test_a_compound_brenda_does_not_list_is_never_relabelled_as_its_neighbour(compound):
    """The word is not read as D-glucose: the report says it was not used
    and that the model is not of it, and the search runs for the
    best-measured substrate BRENDA lists, named as such (ADR 0182). Each
    cited row is D-glucose's, and nothing calls it the typed compound's.
    (Before ADR 0182 this was a refusal, exit 3.)"""
    with hexokinase_offline():
        code, out, err = _main([f"Michaelis-Menten kinetics of human hexokinase on {compound}", *FLAGS])
    assert code == 0, err
    assert "in your description as the substrate" not in out
    assert f"No word of your description ({compound!r}) is a substrate BRENDA lists for EC 2.7.1.1" in out
    assert "it was not used: the model is not of it" in out
    # The choice's note must not say "No substrate was named": one was,
    # and BRENDA does not list it. It says that, then what was used.
    assert "No substrate was named" not in out
    assert (f"No substrate BRENDA lists Km rows for under EC 2.7.1.1 in Homo sapiens was named (no "
            f"word of your description, {compound!r}, is one), so Caterva used D-glucose:") in out
    assert KM_ROW in out
    assert f"as the substrate {compound}" not in out and f"Km of {compound}" not in out


def test_a_filler_word_still_separates_the_compound_from_the_request():
    assert read_sentence("hexokinase on glucose kinetics").substrate_candidates == ("glucose",)


def test_by_after_a_word_that_is_not_the_inhibition_or_the_enzyme_is_not_an_inhibitor():
    reading = read_sentence("competitive inhibition of human hexokinase on glucose measured by fluorescence")
    assert reading.ec == "2.7.1.1" and reading.inhibitor_text is None
    assert not any("inhibitor" in n for n in reading.notes())


def test_inhibited_by_still_reads_the_inhibitor():
    assert read_sentence("hexokinase inhibited by mannoheptulose").inhibitor_text == "mannoheptulose"


def test_a_misspelt_organism_is_said_not_read():
    reading = read_sentence("Michaelis-Menten kinetics of humna hexokinase on glucose")
    assert reading.organism is None
    assert reading.unread_organism == ("humna", "human")
    assert any("'humna' in your description was not read as an organism" in n for n in reading.notes())


def test_a_misspelt_organism_reaches_the_report(monkeypatch):
    import caterva.compose.__main__ as cli

    monkeypatch.setattr(cli, "brenda_km_substrates", lambda ec, org: {"D-glucose": 25})
    args = _args(description="Michaelis-Menten kinetics of humna hexokinase on glucose")
    read = cli.read_description(args, err=io.StringIO())
    assert args.organism is None
    assert any("'humna' in your description was not read as an organism" in n for n in read.notes)


def test_a_word_that_only_sits_before_the_enzyme_is_not_called_an_organism():
    assert read_sentence("Michaelis-Menten kinetics of muscle hexokinase on glucose").unread_organism is None
    assert read_sentence("Michaelis-Menten kinetics of human hexokinase on glucose").unread_organism is None
