"""Caterva Studio's `compose` kind against `caterva compose`, on real inputs.

The adapter (caterva/studio/adapters/compose.py) and the command share one
function, `compose_report`, so the parity asked of them is strict: the
same exit code, the report the studio returns is the command's stdout byte
for byte, the refusal is the command's stderr, each export artefact is
what `--export FORMAT` prints, and every number in the result is the
library's own (compared on the library objects, and where the report
prints a number, the printed string is the result's value formatted the
way the report formats it).

Inputs are real and offline (studio_kinetics_offline.py): human
hexokinase from the API tests' recordings, and lactate dehydrogenase from
the committed BRENDA page behind the Ki-mode tests: the README's
pyruvate Km, the quinoline sulfonamide of BRENDA ref 739793 (0.00059 mM
competitive versus NADH, carried by a competitive model; 0.00252 mM
noncompetitive versus pyruvate, carried by a noncompetitive one) and the
README's gossypol example (ref 711801).
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List

import pytest

from caterva.compose.__main__ import main
from caterva.studio import contract
from caterva.studio.adapters import Cancelled, EndpointRequest, compose as adapter
from studio_kinetics_offline import (
    QUINOLINE, Recorder, context, hexokinase_offline, ldh_offline, run_cli,
)

BINDING = "reversible binding of a ligand to a receptor"
LDH = {"subject": "1.1.1.27", "organism": "human", "substrate": "pyruvate"}


def both(request: Dict[str, Any], tmp_path, progress: Recorder = None):
    """(cli code, stdout, stderr, adapter outcome) for one request."""
    argv = adapter.argv(request)
    code, out, err = run_cli(main, argv)
    outcome = adapter.run(request, context(tmp_path, progress))
    return code, out, err, outcome


def parameter(result: Dict[str, Any], ident: str) -> Dict[str, Any]:
    return next(p for p in result["model"]["parameters"] if p["id"] == ident)


def assert_parity(code, out, err, outcome) -> None:
    assert outcome.exit_code == code
    assert outcome.result["report_markdown"] == out
    if code == 3:
        assert outcome.refusal == err.rstrip("\n")
    else:
        assert outcome.refusal is None


# ---------------------------------------------------------------------------
# request -> argv, through the command's own parser
# ---------------------------------------------------------------------------


def test_every_request_key_becomes_the_flag_the_cli_reads():
    request = {
        "description": "Michaelis-Menten with a competitive inhibitor",
        "subject": "1.1.1.27", "organism": "human", "substrate": "pyruvate",
        "inhibitor": "gossypol", "isoform": "LDH-A", "any_mode": True,
        "compounds": {"@inhibitor": "gossypol"}, "rank_against": "P",
        "sweep": {"parameters": ["reaction_Km"], "low": 0.5, "high": 2.0, "steps": 5},
        "no_ranking": True,
        "analyses": {"crnt": True, "validate": True, "knockout": ["E"],
                     "robustness": {"samples": 12},
                     "stochastic": {"volume_l": 1e-15, "end_s": 10.0, "seed": 3}},
    }
    argv = adapter.argv(request)
    assert argv[0] == request["description"]
    for pair in (["--subject", "1.1.1.27"], ["--isoform", "LDH-A"], ["--compound", "@inhibitor=gossypol"],
                 ["--sweep", "reaction_Km"], ["--sweep-from", "0.5"], ["--sweep-steps", "5"],
                 ["--knockout", "E"], ["--robustness", "12"], ["--stochastic", "1e-15"],
                 ["--stochastic-end", "10.0"], ["--stochastic-seed", "3"]):
        i = argv.index(pair[0])
        assert argv[i:i + 2] == pair
    for flag in ("--any-mode", "--no-ranking", "--crnt", "--validate"):
        assert flag in argv
    for never in ("--export", "--antimony", "--shapes"):
        assert never not in argv


def test_bare_robustness_is_the_clis_bare_flag():
    argv = adapter.argv({"description": BINDING, "analyses": {"robustness": {"samples": None}}})
    assert argv == [BINDING, "--robustness"]
    assert adapter._parsed(argv).robustness == adapter._parsed([BINDING, "--robustness"]).robustness


@pytest.mark.parametrize("request_, field, words", [
    ({"description": ""}, "description", "description is required"),
    ({"description": BINDING, "colour": "red"}, "colour", "not a compose request key"),
    ({"description": BINDING, "subject": 7}, "subject", "must be a string"),
    ({"description": BINDING, "analyses": {"crnt": "yes"}}, "analyses.crnt", "true or false"),
    ({"description": BINDING, "analyses": {"stochastic": {"seed": 1}}},
     "analyses.stochastic.volume_l", "volume_l"),
    ({"description": BINDING, "sweep": {"parameters": []}}, "sweep.parameters", "list of parameter"),
    ({"description": BINDING, "compounds": {"a=b": "x"}}, "compounds.a=b", "without '='"),
])
def test_a_malformed_request_names_its_field(request_, field, words):
    with pytest.raises(contract.Malformed) as caught:
        adapter.argv(request_)
    assert caught.value.field == field and words in str(caught.value)


def test_the_clis_post_parse_refusal_arrives_in_its_own_words():
    with pytest.raises(contract.Malformed) as caught:
        adapter.argv({"description": BINDING, "analyses": {"robustness": {"samples": 0}}})
    assert str(caught.value).startswith("caterva compose: error: --robustness needs at least one sample; got 0.")
    with pytest.raises(SystemExit) as exited:
        run_cli(main, ["--robustness", "0", BINDING])
    assert exited.value.code == 2


def test_a_description_that_starts_with_a_dash_is_not_read_as_a_flag():
    argv = adapter.argv({"description": "-x", "subject": "-y"})
    assert argv == ["--subject=-y", "--", "-x"]


# ---------------------------------------------------------------------------
# no search: every analysis, the exports, the progress
# ---------------------------------------------------------------------------

EVERY_ANALYSIS = {
    "description": BINDING,
    "sweep": {"parameters": ["complex_kon"]},
    "analyses": {"crnt": True, "scale": True, "predictions": True, "reduction": True,
                 "identifiability": True, "design": True, "validate": True, "screen": True,
                 "robustness": {"samples": 5},
                 "stochastic": {"volume_l": 1e-15, "seed": 7}},
}


@pytest.fixture(scope="module")
def every_analysis(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("compose")
    progress = Recorder()
    return (*both(EVERY_ANALYSIS, tmp, progress), progress)


def test_every_analysis_matches_the_cli_byte_for_byte(every_analysis):
    code, out, err, outcome, _ = every_analysis
    # One section (timescale separation) declines this model: exit 3 with
    # the command's own stderr line, and the report still produced.
    assert code == 3
    assert_parity(code, out, err, outcome)
    assert outcome.refusal.endswith("Timescale separation.")


def test_each_section_is_the_text_printed_under_its_heading(every_analysis):
    _, out, _, outcome, _ = every_analysis
    sections = outcome.result["sections"]
    assert [s["key"] for s in sections] == [
        "crnt", "scale", "predictions", "reduction", "identifiability", "design",
        "robustness", "perturbations", "stochastic", "validate"]
    for section in sections:
        assert f"\n## {section['title']}\n\n{section['text']}\n" in out
    reduction = next(s for s in sections if s["key"] == "reduction")
    assert reduction["status"] == "refused" and reduction["refusals"]
    assert all(s["status"] == "answered" for s in sections if s["key"] != "reduction")


def test_each_sections_numbers_are_its_report_objects(every_analysis):
    from caterva.compose.pipeline import compose
    from caterva.compose.scale import check_model

    _, _, _, outcome, _ = every_analysis
    by_key = {s["key"]: s for s in outcome.result["sections"]}
    assert by_key["scale"]["data"]["report"] == contract.jsonable(check_model(compose(BINDING)))
    robustness = by_key["robustness"]["data"]
    assert robustness["conclusion"] and robustness["report"]
    stochastic = by_key["stochastic"]["data"]
    assert stochastic["seed"] == 7 and stochastic["volume_l"] == 1e-15
    run = stochastic["run"]
    # Far more events than the page can draw: every n-th row and the last,
    # each a row the run held, and the result says so.
    assert run["seed"] == 7 and run["rows"] > contract.SERIES_ROW_LIMIT
    assert len(run["times"]) <= contract.SERIES_ROW_LIMIT and run["every"] > 1
    assert run["events"] == run["rows"] - 2
    for name, final in run["final_counts"].items():
        assert run["counts"][name][-1] == final
    assert by_key["validate"]["data"]["report"]


def test_the_dossiers_numbers_are_the_dossiers(every_analysis):
    from caterva.compose.report import dossier

    _, out, _, outcome, _ = every_analysis
    result = outcome.result
    fresh = dossier(BINDING, sweep_parameters=["complex_kon"])
    assert result["trajectory"]["times"] == contract.jsonable(list(fresh.trajectory.times))
    assert result["trajectory"]["columns"] == {
        k: contract.jsonable(list(v)) for k, v in fresh.trajectory.columns.items()}
    assert result["stability"]["text"] == fresh.stability.summary()
    assert [fp["state"] for fp in result["stability"]["fixed_points"]] == [
        {k: contract.jsonable(v) for k, v in p.state.items()} for p in fresh.stability.fixed_points]
    assert result["sensitivity"]["base_value"] == contract.jsonable(fresh.sensitivity.base_value)
    assert result["sweeps"] == [contract.jsonable(s) for s in fresh.sweeps]
    assert result["stability"]["text"] in out and result["trajectory"]["text"] in out


def test_the_parameters_are_the_exports_origins(every_analysis):
    from caterva.compose.export import provenance_of
    from caterva.compose.pipeline import compose

    _, _, _, outcome, _ = every_analysis
    origins = {o.identifier: o for o in provenance_of(compose(BINDING)).origins}
    params = outcome.result["model"]["parameters"]
    assert {p["id"] for p in params} == {i for i, o in origins.items() if o.role == "parameter"}
    for p in params:
        origin = origins[p["id"]]
        assert p["value"] == origin.value and p["unit"] == str(origin.unit or "")
        assert p["provenance"]["kind"] == "placeholder"
        assert p["provenance"]["reason"] == origin.sentence()
    for row in outcome.result["model"]["species"]:
        assert row["initial"]["value"] == origins[row["id"]].value


def test_every_export_is_what_export_prints(every_analysis, tmp_path):
    _, _, _, outcome, _ = every_analysis
    artifacts = {a.name: a for a in outcome.artifacts}
    assert artifacts["report.md"].content.decode("utf-8") == outcome.result["report_markdown"]
    for fmt, info in outcome.result["exports"].items():
        code, out, err = run_cli(main, ["--export", fmt, BINDING])
        if code == 0:
            assert info == {"available": True, "artifact": adapter.EXPORT_ARTIFACTS[fmt][0], "refused": None}
            assert artifacts[info["artifact"]].content.decode("utf-8") == out
        else:
            assert info["available"] is False
            assert err == f"Not exported.\n\n{info['refused']}\n"


def test_progress_reports_each_stage_then_each_section(every_analysis):
    _, _, err, _, progress = every_analysis
    stages = progress.stages()
    assert stages[0] == "compose" and stages[-1] == "exports"
    assert stages.index("precompute") < stages.index("dossier") < stages.index("section:crnt")
    sections = [c for c in progress.calls if c[0] == "stage" and c[1].startswith("section:")]
    assert [c[3] for c in sections] == [i / len(sections) for i in range(len(sections))]
    # What the command wrote to stderr reaches the page as log lines.
    assert progress.logs() == [line for line in err.splitlines() if line.strip()]


def test_a_cancel_at_a_section_stops_the_run(tmp_path):
    with pytest.raises(Cancelled):
        adapter.run(EVERY_ANALYSIS, context(tmp_path, Recorder(cancel_at="section:scale")))


# ---------------------------------------------------------------------------
# refusals
# ---------------------------------------------------------------------------


def test_an_unrecognised_shape_is_a_refusal_with_the_clis_words_and_no_result(tmp_path):
    code, out, err, outcome = both({"description": "glycolysis"}, tmp_path)
    assert code == outcome.exit_code == 3
    assert out == "" and outcome.result is None
    assert outcome.refusal == err.rstrip("\n")
    assert outcome.refusal.startswith("Not built.")


def test_a_search_with_no_literature_answer_is_refused_and_still_reported(tmp_path):
    # EC 2.7.1.1 for an organism no recording covers: the search cannot run
    # offline, the command says so, and the report is still the command's.
    with hexokinase_offline():
        code, out, err, outcome = both(
            {"description": "Michaelis Menten", "subject": "2.7.1.1",
             "organism": "Thermus thermophilus", "substrate": "glucose"}, tmp_path)
    assert_parity(code, out, err, outcome)
    assert code == 3 and outcome.result["search"]["refused"] is True


def test_a_name_that_is_several_enzymes_is_refused_with_named_candidates(tmp_path):
    """The compose search reads --subject with the one name policy, and the outcome carries what it named."""
    code, out, err, outcome = both(
        {"description": "Michaelis Menten", "subject": "lactate dehydrogenase", "organism": "human",
         "substrate": "pyruvate"}, tmp_path)
    assert_parity(code, out, err, outcome)
    assert code == outcome.exit_code == 3 and outcome.result["search"]["refused"] is True
    refusal = outcome.name_refusal
    assert refusal["kind"] == "ambiguous" and refusal["recommended"] == "1.1.1.27"
    assert refusal["rerun_flag"] == "--subject {ec}" and refusal["message"] in outcome.result["search"]["note"]
    named = {c["ec"]: c for c in refusal["named_candidates"]}
    assert named["1.1.1.27"]["name"] == "L-lactate dehydrogenase"
    assert {"LDHA", "LDHB", "LDHC"} <= {p["symbol"] for p in named["1.1.1.27"]["organism_proteins"]}
    assert contract.outcome_for("compose", 3, outcome.summary, outcome.refusal, refusal)["name_refusal"] == refusal


def test_a_name_goes_through_the_one_policy_not_a_copy_in_the_adapter():
    from pathlib import Path

    source = Path(adapter.__file__).read_text(encoding="utf-8")
    assert "resolve_enzyme_name" not in source and "uniprot" not in source.lower().replace("uniprot's", "")


# ---------------------------------------------------------------------------
# with a literature search
# ---------------------------------------------------------------------------


def test_human_hexokinase_carries_brenda_ref_641068(tmp_path):
    progress = Recorder()
    with hexokinase_offline():
        code, out, err, outcome = both(
            {"description": "Michaelis Menten", "subject": "2.7.1.1", "organism": "human",
             "substrate": "glucose"}, tmp_path, progress)
    assert_parity(code, out, err, outcome)
    assert code == 0
    km = parameter(outcome.result, "reaction_Km")
    assert km["value"] == 6.0 and km["unit"] == "mM"
    cite = km["provenance"]["citation"]
    assert cite == {"text": "BRENDA ref 641068", "registry": "BRENDA", "reference_id": "641068",
                    "url": "https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1", "via": "literature"}
    assert km["provenance"]["organism"] == "Homo sapiens"
    assert "| `reaction_Km` | 6.0 mM | literature (Homo sapiens) | BRENDA ref 641068 |" in out
    looked_up = [c[2] for c in progress.calls if c[0] == "stage" and c[1] == "search"]
    assert "Looking up reaction_Km in BRENDA's km table for EC 2.7.1.1" in looked_up


@pytest.fixture(scope="module")
def ldh(tmp_path_factory):
    """The four LDH runs, each by the command and by the adapter."""
    tmp = tmp_path_factory.mktemp("ldh")
    requests = {
        "pyruvate": {"description": "Michaelis Menten", **LDH},
        "competitive": {"description": "Michaelis-Menten with a competitive inhibitor",
                        "inhibitor": QUINOLINE, **LDH},
        "noncompetitive": {"description": "Michaelis-Menten with a noncompetitive inhibitor",
                           "inhibitor": QUINOLINE, **LDH},
        "gossypol": {"description": "Michaelis-Menten with a competitive inhibitor",
                     "inhibitor": "gossypol", **LDH},
    }
    with ldh_offline():
        return {name: both(request, tmp) for name, request in requests.items()}


@pytest.mark.parametrize("case", ["pyruvate", "competitive", "noncompetitive", "gossypol"])
def test_ldh_matches_the_cli(ldh, case):
    code, out, err, outcome = ldh[case]
    assert_parity(code, out, err, outcome)
    assert code == 0 and outcome.result["search"]["refused"] is False


def test_the_readmes_pyruvate_km(ldh):
    km = parameter(ldh["pyruvate"][3].result, "reaction_Km")
    assert km["value"] == 0.03 and km["unit"] == "mM"
    prov = km["provenance"]
    assert prov["kind"] == "measured" and prov["citation"]["reference_id"] == "286469"
    assert prov["citation"]["url"] == "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27"
    assert prov["spread"]["low"] == 0.03 and prov["spread"]["high"] == 0.398
    assert prov["spread"]["references"] == ["286442", "286469"]


def test_a_competitive_model_carries_the_competitive_row(ldh):
    ki = parameter(ldh["competitive"][3].result, "reaction_Ki")
    assert ki["value"] == 0.00059
    assert ki["provenance"]["citation"]["text"] == "BRENDA ref 739793"
    assert ki["provenance"]["chosen_because"] is None
    assert "competitive" in ki["provenance"]["commentary"]


def test_a_noncompetitive_model_carries_the_noncompetitive_row_and_says_why(ldh):
    code, out, _, outcome = ldh["noncompetitive"]
    ki = parameter(outcome.result, "reaction_Ki")
    assert ki["value"] == 0.00252
    prov = ki["provenance"]
    assert prov["citation"]["reference_id"] == "739793"
    assert prov["chosen_because"] and "noncompetitive inhibition versus pyruvate" in prov["chosen_because"]
    assert prov["spread"]["carried"] == 0.00252
    assert (prov["spread"]["low"], prov["spread"]["high"]) == (0.00059, 0.00252)
    assert "spanning **0.00059 to 0.00252 mM**" in out
    assert "| `reaction_Ki` | 0.00252 mM | literature (Homo sapiens) | BRENDA ref 739793 |" in out


def test_the_readmes_gossypol_example(ldh):
    result = ldh["gossypol"][3].result
    ki = parameter(result, "reaction_Ki")
    assert ki["value"] == 0.0014 and ki["provenance"]["citation"]["reference_id"] == "711801"
    assert "LDH-B" in ki["provenance"]["commentary"]
    kcat = parameter(result, "reaction_kcat")
    assert kcat["provenance"]["kind"] == "placeholder"
    assert kcat["provenance"]["reason"]  # the resolver's words for a value not found
    assert result["search"]["measured"] == 2 and result["search"]["placeholders"] == 1


def test_the_csv_export_carries_the_same_row_as_the_result(ldh):
    _, _, _, outcome = ldh["noncompetitive"]
    csv_text = next(a for a in outcome.artifacts if a.name == "parameters.csv").content.decode("utf-8")
    row = next(r for r in csv.DictReader(io.StringIO(csv_text)) if r["identifier"] == "reaction_Ki")
    assert float(row["value"]) == parameter(outcome.result, "reaction_Ki")["value"]


# ---------------------------------------------------------------------------
# the endpoints
# ---------------------------------------------------------------------------


def _endpoint(body: Any = None, query: Dict[str, str] = None, tmp=None) -> EndpointRequest:
    return EndpointRequest(params={}, query=query or {}, body=body, data_dir=tmp)


def test_the_shapes_are_the_ones_compose_lists(tmp_path):
    from caterva.compose.grammar import shapes

    answer = adapter.shapes_endpoint(_endpoint(tmp=tmp_path))
    assert answer == {"shapes": list(shapes())}
    _, out, _ = run_cli(main, ["--shapes"])
    listed: List[str] = [line[2:] for line in out.splitlines() if line.startswith("  ")]
    assert answer["shapes"] == listed and len(listed) == len(answer["shapes"])


def test_the_shapes_endpoint_refuses_a_query(tmp_path):
    with pytest.raises(contract.Malformed):
        adapter.shapes_endpoint(_endpoint(query={"x": "1"}, tmp=tmp_path))


def test_normalise_is_composes_reading(tmp_path):
    from caterva.compose.organisms import normalise_organism

    organism, note = normalise_organism("human")
    assert adapter.normalise_endpoint(_endpoint({"name": "human"}, tmp=tmp_path)) == {
        "organism": organism, "note": note}
    with pytest.raises(contract.Malformed):
        adapter.normalise_endpoint(_endpoint({"name": 3}, tmp=tmp_path))


def test_the_kind_is_registered_with_its_endpoints():
    from caterva.studio.adapters import Registry

    registry = Registry()
    adapter.register(registry)
    spec = registry.get("compose")
    assert spec.serial and spec.cli_prefix == ("caterva", "compose")
    assert registry.endpoint("compose_shapes") is adapter.shapes_endpoint
    assert registry.endpoint("normalise_organism") is adapter.normalise_endpoint


def test_a_long_event_table_is_thinned_to_rows_it_held():
    limit = contract.SERIES_ROW_LIMIT
    assert adapter.thinned_indices(10) == list(range(10))
    indices = adapter.thinned_indices(limit * 3 + 7)
    assert len(indices) <= limit and indices[-1] == limit * 3 + 6
    every = adapter.every_for(limit * 3 + 7)
    assert all(b - a == every for a, b in zip(indices[:-2], indices[1:-1]))
