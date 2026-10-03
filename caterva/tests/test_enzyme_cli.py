"""`caterva enzyme`: what it prints, what it exits with, and that it is registered.

Every command here runs against the real shipped index; nothing is mocked.
The contract under test: exit 0 when the name resolved or candidates were
listed to choose from, 3 when nothing matched (suggestions still printed),
2 for a malformed command line; every flag explains itself; the output names
each candidate, why it matched, its reaction, its class, the organism's
proteins and the `caterva compose ... --subject EC` line to use.
"""
from __future__ import annotations

import json

import pytest

from caterva.enzymes.__main__ import build_parser, compose_line, main


def run(capsys, *argv):
    code = main(list(argv))
    return code, capsys.readouterr().out


def test_the_command_is_registered_with_a_one_line_description():
    from caterva.app import COMMANDS, _usage

    module, description = COMMANDS["enzyme"]
    assert module == "caterva.enzymes.__main__"
    assert description and "\n" not in description
    assert "enzyme" in _usage() and description in _usage()


def test_it_runs_through_the_one_executable(capsys):
    from caterva.app import main as app_main

    assert app_main(["enzyme", "pyruvate kinase", "--limit", "1"]) == 0
    out = capsys.readouterr().out
    assert "Resolved: EC 2.7.1.40 (pyruvate kinase)" in out


def test_a_resolved_name_prints_the_card_and_the_compose_line(capsys):
    code, out = run(capsys, "pyruvate kinase", "--organism", "human", "--limit", "1")
    assert code == 0
    assert "Resolved: EC 2.7.1.40 (pyruvate kinase) -- accepted name matches exactly." in out
    assert "why: accepted name matches exactly" in out
    assert "reaction: pyruvate + ATP = phosphoenolpyruvate + ADP + H(+)." in out
    assert "class: Transferases > transferring phosphorus-containing groups" in out
    assert "human proteins (2): PKM (P14618), PKLR (P30613)" in out
    assert 'use: caterva compose "Michaelis Menten" --subject 2.7.1.40 --organism human --substrate <substrate>' in out
    assert "ExPASy ENZYME release 02-Sep-2026, human" in out


def test_an_ambiguous_name_exits_zero_lists_the_choices_and_recommends_without_picking(capsys):
    code, out = run(capsys, "lactate dehydrogenase", "--organism", "human", "--limit", "3")
    assert code == 0
    assert "Not resolved:" in out and "will not pick one for you" in out
    assert "Recommended: EC 1.1.1.27 (L-lactate dehydrogenase)" in out
    assert "Confirm it with --subject 1.1.1.27" in out
    assert "1. EC 1.1.1.27  L-lactate dehydrogenase   <- recommended" in out
    assert "2. EC 1.1.1.28  D-lactate dehydrogenase" in out
    assert "human proteins: none listed" in out
    assert "more; raise --limit to see them." in out


def test_a_misspelling_prints_did_you_mean_and_exits_three(capsys):
    code, out = run(capsys, "hexokinse", "--organism", "human")
    assert code == 3
    assert "no enzyme is named 'hexokinse'" in out and "Did you mean" in out
    assert "EC 2.7.1.1  hexokinase" in out and "why: close to the accepted name: did you mean?" in out


def test_nothing_matching_exits_three_and_says_how_to_continue(capsys):
    code, out = run(capsys, "xyzzy plugh")
    assert code == 3
    assert "Nothing matched" in out and "Check the spelling" in out


def test_a_deleted_ec_number_exits_three(capsys):
    code, out = run(capsys, "1.1.1.74")
    assert code == 3 and "was deleted" in out


def test_a_transferred_ec_number_names_the_replacement(capsys):
    code, out = run(capsys, "1.1.1.32")
    assert code == 0
    assert "Resolved: EC 1.1.1.1 (alcohol dehydrogenase)" in out
    assert "was transferred" in out and "Caution:" in out


def test_a_class_lists_members_and_exits_zero(capsys):
    code, out = run(capsys, "1.1.1.-", "--limit", "2")
    assert code == 0 and "class of enzymes" in out and "a member of EC 1.1.1.-" in out


def test_the_limit_bounds_the_list(capsys):
    _, out = run(capsys, "kinase", "--limit", "2")
    assert " 1. EC " in out and " 2. EC " in out and " 3. EC " not in out


def test_json_is_machine_readable_and_complete(capsys):
    code, out = run(capsys, "glucokinase", "--organism", "human", "--limit", "2", "--json")
    assert code == 0
    data = json.loads(out)
    assert data["outcome"] == "resolved" and data["resolved_ec"] == "2.7.1.2"
    assert data["release"] == "02-Sep-2026" and data["organism_code"] == "HUMAN"
    assert data["candidates_total"] >= 2 and len(data["candidates"]) == 2
    first = data["candidates"][0]
    assert {"ec", "name", "why", "tier", "reaction", "class_path", "organism_proteins", "compose"} <= set(first)
    assert data["cautions"] and "lists no human protein" in data["cautions"][0]


def test_json_for_a_tie_carries_the_recommendation_and_resolves_nothing(capsys):
    code, out = run(capsys, "lactate dehydrogenase", "--organism", "human", "--json", "--limit", "2")
    data = json.loads(out)
    assert code == 0 and data["outcome"] == "ambiguous"
    assert data["recommended_ec"] == "1.1.1.27" and "resolved_ec" not in data


def test_json_for_nothing_matched_exits_three(capsys):
    code, out = run(capsys, "xyzzy plugh", "--json")
    assert code == 3 and json.loads(out)["outcome"] == "none"


def test_an_unrecognised_organism_is_said_not_assumed(capsys):
    _, out = run(capsys, "hexokinase", "--organism", "Thermus aquaticus", "--limit", "1")
    assert "is not an organism the index knows" in out


def test_a_bad_limit_or_empty_query_is_a_malformed_command(capsys):
    assert main(["hexokinase", "--limit", "0"]) == 2
    assert main(["   "]) == 2
    with pytest.raises(SystemExit) as raised:
        main(["--no-such-flag", "x"])
    assert raised.value.code == 2


def test_every_argument_explains_itself():
    parser = build_parser()
    for action in parser._actions:
        assert action.help, f"{action.dest} has no help text"
    flags = {opt for action in parser._actions for opt in action.option_strings}
    assert {"--organism", "--limit", "--json"} <= flags


def test_the_compose_line_quotes_an_organism_with_spaces():
    assert compose_line("1.1.1.27", "Homo sapiens") == (
        "caterva compose \"Michaelis Menten\" --subject 1.1.1.27 --organism 'Homo sapiens' --substrate <substrate>")
    assert compose_line("1.1.1.27", None).endswith("--subject 1.1.1.27 --substrate <substrate>")


def test_fragments_of_longer_names_are_listed_with_exit_zero_and_called_partial(capsys):
    code, out = run(capsys, "glucose isomerase", "--organism", "human", "--json")
    data = json.loads(out)
    assert data["outcome"] == "partial" and code == 0
    assert [c["ec"] for c in data["candidates"]] == ["5.3.1.9"]
    assert all(c["partial_match"] for c in data["candidates"])
    code, text = run(capsys, "glucose isomerase", "--organism", "human")
    assert code == 0 and "Did you mean one of these?" in text and "only part of one enzyme's name" in text


def test_an_abbreviation_lists_what_it_can_mean_and_never_resolves(capsys):
    code, out = run(capsys, "LDH", "--organism", "human", "--json", "--limit", "2")
    data = json.loads(out)
    assert code == 0 and data["outcome"] == "ambiguous" and data["confirm_only"] is True
    assert [c["ec"] for c in data["candidates"]] == ["1.1.1.27", "1.1.1.28"]
    assert data["recommended_ec"] is None and all(c["matched_by"] == "abbreviation" for c in data["candidates"])
    code, text = run(capsys, "LDH", "--organism", "human", "--limit", "2")
    assert "abbreviation or symbol, not an enzyme name" in text and "Recommended:" not in text