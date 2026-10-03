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

import re
import sys

import pytest

from caterva.studio import contract
from caterva.studio.adapters import constants as adapter
from studio_kinetics_offline import Recorder, context, hexokinase_offline, run_cli

HEXOKINASE = {"ec": "2.7.1.1", "organism": "human", "substrate": "glucose"}

#: The document says when it was made, to the minute ("| Generated | 2026-10-03
#: 14:07 UTC |", Tests/lab_report.py). Two documents made a moment apart can
#: straddle a minute and differ in that one cell, so documents are compared
#: with the cell's time replaced by a fixed word.
_GENERATED = re.compile(r"(\| Generated \| )\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC( \|)")


def same_document(a: str, b: str) -> bool:
    """Whether two documents are the same apart from the minute they say they were generated."""
    assert _GENERATED.search(a) and _GENERATED.search(b), "the Generated row is gone: this helper is now comparing nothing special"
    return _GENERATED.sub(r"\1<minute>\2", a) == _GENERATED.sub(r"\1<minute>\2", b)


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
    assert same_document(outcome.result["document_markdown"], out)
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
    assert code == outcome.exit_code == 0 and same_document(outcome.result["document_markdown"], out)
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


def test_two_documents_a_minute_apart_compare_equal_but_a_real_difference_does_not():
    base = "x\n| Generated | 2026-10-03 14:07 UTC |\ny\n"
    assert same_document(base, base.replace("14:07", "14:08"))
    assert not same_document(base, base.replace("y\n", "z\n"))
