"""Caterva Studio's `constants` kind against `scripts/cite.py` (`make cite`).

The command runs report_lab in a subprocess; the studio runs the same
`run_payload` in-process (a frozen app has no Python to start). For the
same request, on human hexokinase answered from Tests/fixtures/recorded/:
the document is what cite.py prints, the exit code is cite.py's, and the
constant's value, citation, organism and assay conditions are read from
the resolver's KineticResult the document was written from. A refusal is
cite.py's stderr, word for word.
"""
from __future__ import annotations

import sys

import pytest

from caterva.studio import contract
from caterva.studio.adapters import constants as adapter
from studio_kinetics_offline import Recorder, context, hexokinase_offline, run_cli

HEXOKINASE = {"ec": "2.7.1.1", "organism": "human", "substrate": "glucose"}


def cite_main():
    return adapter.cite_module().main


@pytest.fixture(scope="module")
def hexokinase(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("constants")
    progress = Recorder()
    with hexokinase_offline():
        code, out, err = run_cli(cite_main(), adapter.argv(HEXOKINASE))
        outcome = adapter.run(HEXOKINASE, context(tmp, progress))
    return code, out, err, outcome, progress


def test_the_kind_is_available_in_a_source_checkout():
    assert adapter.unavailable() is None


def test_the_document_is_what_cite_prints(hexokinase):
    code, out, err, outcome, _ = hexokinase
    assert code == outcome.exit_code == 0
    assert outcome.result["document_markdown"] == out
    # cite.py tells stderr how it read "human"; the studio keeps the note.
    assert outcome.result["organism_note"] == err.strip()


def test_the_km_is_the_resolvers_with_its_citation(hexokinase):
    _, out, _, outcome, progress = hexokinase
    (row,) = outcome.result["constants"]
    assert row["name"] == "km" and row["found"] is True and row["source"] == "brenda_exact"
    km = row["value"]
    assert km["value"] == row["raw"]["value"] == 6.0 and km["unit"] == "mM"
    prov = km["provenance"]
    assert prov["kind"] == "measured" and prov["organism"] == "Homo sapiens"
    assert prov["citation"]["text"] == "BRENDA ref 641068"
    assert prov["citation"]["registry"] == "BRENDA" and prov["citation"]["reference_id"] == "641068"
    assert prov["citation"]["url"] == "https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1"
    assert prov["conditions"]["ph"] == row["raw"]["assay_ph"]
    assert prov["conditions"]["temperature_c"] == row["raw"]["assay_temperature_c"]
    assert prov["commentary"] == row["raw"]["commentary"]
    assert "BRENDA ref 641068" in out
    assert outcome.result["sourced"] == ["km"]
    assert progress.stages() == ["resolve", "document"]


def test_the_engines_tie_explanation_reaches_the_row_and_the_ui_can_show_it(hexokinase):
    """Human hexokinase's glucose Km is 3 equally evidenced rows, 6 to 18 mM. The engine says so ("taking the lowest,
    which the evidence does not justify"); the adapter used to drop it (`scope: []`, `chosen_because: None`)."""
    _, _, _, outcome, _ = hexokinase
    (row,) = outcome.result["constants"]
    prov = row["value"]["provenance"]
    tie = row["raw"]["selection_tie"]
    assert prov["chosen_because"] == tie["reason"]
    assert "3 rows were equally well evidenced" in prov["chosen_because"]
    assert "taking the lowest, which the evidence does not justify" in prov["chosen_because"]
    spread = prov["spread"]
    assert (spread["low"], spread["high"], spread["carried"], spread["n_values"], spread["unit"]) == (6.0, 18.0, 6.0, 3, "mM")
    assert spread["references"] == ["641068", "739603"] and "spanning 6 to 18 mM (3-fold)" in spread["sentence"]
    # The rows it ranked equal are the alternatives, each as measured.
    assert sorted(a["value"] for a in row["alternatives"]) == [6.3, 18.0]


def test_the_engines_scope_concerns_reach_the_row(hexokinase):
    """The candidate rows name 6 different forms of hexokinase; the engine says returning the lowest would pick a
    form rather than answer the question. That is a scope concern of the value, and it was `[]`."""
    _, _, _, outcome, _ = hexokinase
    prov = outcome.result["constants"][0]["value"]["provenance"]
    assert any("name 6 different forms of hexokinase" in c and "would pick a form rather than answer" in c
               for c in prov["scope"])


def test_the_isozyme_notice_is_shown_for_an_ec_with_several_proteins_in_the_organism(hexokinase):
    _, _, _, outcome, _ = hexokinase
    notice = outcome.result["isozyme_notice"]
    assert (notice["ec"], notice["count"], notice["broad"]) == ("2.7.1.1", 5, False)
    assert notice["symbols"] == ["HKDC1", "HK1", "HK2", "HK3", "GCK"]
    assert notice["detail"].startswith("EC 2.7.1.1 has 5 human isozymes") and "this lookup returns may belong to any of them" in notice["detail"]
    assert "--isoform" not in notice["detail"], "a lookup has no isoform field to have left empty"
    assert "Isoform field of Compose" in notice["remedy"]


def test_a_one_protein_ec_or_an_unresolved_name_carries_no_isozyme_notice():
    from types import SimpleNamespace

    assert adapter.isozyme_view({"ec": "5.3.1.1", "organism": "human"}, SimpleNamespace(organism="human")) is None
    assert adapter.isozyme_view({"enzyme": "lactate dehydrogenase", "organism": "human"}, SimpleNamespace()) is None
    named = adapter.isozyme_view({"enzyme": "hexokinase", "organism": "human"}, SimpleNamespace())
    assert named["ec"] == "2.7.1.1"


def test_the_supplied_values_are_chosen_by_cites_defaults(hexokinase):
    _, _, _, outcome, _ = hexokinase
    supplied = {v["id"]: v for v in outcome.result["supplied"]}
    defaults = adapter.cite_module().build_parser().parse_args(["--ec", "1", "--substrate", "x"])
    assert supplied["s0"]["value"] == defaults.s0 and supplied["vmax"]["value"] == defaults.vmax
    for value in supplied.values():
        assert value["provenance"]["kind"] == "chosen" and value["provenance"]["by"] == "default"


def test_a_supplied_value_is_chosen_by_the_user(tmp_path):
    request = {**HEXOKINASE, "s0": 2.5, "basis": "the tube held 2.5 mM"}
    with hexokinase_offline():
        code, out, _ = run_cli(cite_main(), adapter.argv(request))
        outcome = adapter.run(request, context(tmp_path))
    assert code == outcome.exit_code == 0 and outcome.result["document_markdown"] == out
    supplied = {v["id"]: v for v in outcome.result["supplied"]}
    assert supplied["s0"]["value"] == 2.5
    assert supplied["s0"]["provenance"] == {"kind": "chosen", "by": "user", "reason": "the tube held 2.5 mM"}
    assert supplied["vmax"]["provenance"]["by"] == "default"


def test_a_question_report_lab_refuses_is_refused_in_cites_words(tmp_path):
    request = {"ec": "2.7.1.1", "substrate": "glucose"}  # no organism
    with hexokinase_offline():
        code, out, err = run_cli(cite_main(), adapter.argv(request))
        outcome = adapter.run(request, context(tmp_path))
    assert code == outcome.exit_code == 3 and out == ""
    assert outcome.result is None
    assert outcome.refusal == err.rstrip("\n")
    assert outcome.refusal.startswith("Not produced.\n\nA report needs an enzyme and an organism.")


def test_report_labs_json_now_carries_the_resolved_results(hexokinase):
    _, _, _, outcome, _ = hexokinase
    raw = outcome.result["constants"][0]["raw"]
    assert raw["citation"]["reference_id"] == "641068" and raw["found"] is True


@pytest.mark.parametrize("request_, field", [
    ({"ec": "2.7.1.1"}, None),  # no substrate: cite.py's parser refuses
    ({"ec": "2.7.1.1", "enzyme": "hexokinase", "substrate": "glucose"}, None),
    ({"ec": "2.7.1.1", "substrate": "glucose", "json": True}, "json"),
    ({"ec": "2.7.1.1", "substrate": "glucose", "fixture": "x.html"}, "fixture"),
    ({"ec": "2.7.1.1", "substrate": "glucose", "quantities": "km"}, "quantities"),
    ({"ec": "2.7.1.1", "substrate": "glucose", "s0": "ten"}, "s0"),
])
def test_a_malformed_request_is_refused_before_it_runs(request_, field):
    with pytest.raises(contract.Malformed) as caught:
        adapter.argv(request_)
    assert caught.value.field == field


def test_an_unknown_quantity_is_refused_by_cites_parser():
    with pytest.raises(contract.Malformed) as caught:
        adapter.argv({**HEXOKINASE, "quantities": ["vmax"]})
    assert "invalid choice: 'vmax'" in str(caught.value)


def test_argv_is_one_flag_per_key_and_reproduces_with_cite():
    argv = adapter.argv({**HEXOKINASE, "quantities": ["km", "kcat"], "seed": 3})
    assert argv == ["--ec=2.7.1.1", "--organism=human", "--substrate=glucose", "--seed=3",
                    "--quantity=km", "--quantity=kcat"]
    assert adapter.SPEC.cli_prefix == ("python3", "scripts/cite.py")


def test_cite_is_imported_by_path_once():
    module = adapter.cite_module()
    assert module is sys.modules["caterva_cite"] and module is adapter.cite_module()
    assert module.__file__ == str(adapter.CITE)


def test_a_name_that_is_several_enzymes_is_refused_with_named_candidates(tmp_path):
    """cite.py's refusal, and the same refusal as data from the one name policy."""
    request = {"enzyme": "lactate dehydrogenase", "organism": "human", "substrate": "pyruvate"}
    with hexokinase_offline():
        code, out, err = run_cli(cite_main(), adapter.argv(request))
        outcome = adapter.run(request, context(tmp_path))
    assert code == outcome.exit_code == 3 and outcome.result is None
    assert err.rstrip("\n").endswith(outcome.refusal)  # the organism note comes first on stderr
    refusal = outcome.name_refusal
    assert refusal["kind"] == "ambiguous" and refusal["recommended"] == "1.1.1.27"
    assert refusal["rerun_flag"] == "--ec {ec}"
    assert refusal["message"] in outcome.refusal
    assert {"1.1.1.27", "1.1.1.28"} <= {c["ec"] for c in refusal["named_candidates"]}
    assert all(c["name"] for c in refusal["named_candidates"])


def test_a_refusal_that_is_not_a_name_carries_no_name_refusal(tmp_path):
    request = {"ec": "2.7.1.1", "substrate": "glucose"}
    with hexokinase_offline():
        outcome = adapter.run(request, context(tmp_path))
    assert outcome.exit_code == 3 and outcome.name_refusal is None
