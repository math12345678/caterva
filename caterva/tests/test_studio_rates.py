"""Caterva Studio's `rates` kind against `caterva rates`, on the real Puromycin table.

The adapter calls the command's own functions (`ingest.inspect` for the
table, `run.execute` for the fit, `report` for the text, JSON and CSV), so
for the same table and choices: the report is the command's stdout, the
`analysis` in the result is the command's `--json` to the byte, the
parameters and curves files are the command's `--export` output, and the
numbers are R 4.6.0's `nls` on `datasets::Puromycin` (test_rates_puromycin.py
holds the reference values). The command is run on `dataset.csv`, the file
the run itself wrote, in a directory of its own, as the run's recorded
command line says to.

Every measurement is a value of examples/rates/puromycin.csv, or a subset of
its rows (the lowest two substrate concentrations, for the table that cannot
bound Km). The units written on real numbers for the kcat arithmetic are
labels, not claims about the experiment (test_rates_ingest.py says the same).
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
import time
from pathlib import Path

import pytest

from caterva.rates import ingest, report
from caterva.rates.__main__ import main as rates_main
from caterva.studio import contract
from caterva.studio.adapters import Cancelled, EndpointRequest, load_registry
from caterva.studio.adapters import rates as adapter
from studio_kinetics_offline import Recorder, context, run_cli

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "rates" / "puromycin.csv"
TEXT = EXAMPLE.read_text(encoding="utf-8")
HEAD = [l for l in TEXT.splitlines() if l and not l.startswith("#")]
ROWS = [r for r in csv.reader(io.StringIO("\n".join(HEAD)))][1:]

REQUEST = {"dataset": {"text": TEXT, "filename": "puromycin.csv"}, "sigma_from": "residuals"}
#: R 4.6.0 nls on the treated rows (test_rates_puromycin.R_NLS).
R_TREATED = {"Vmax": 212.68358, "Km": 0.06412102739}


def lines_where(keep) -> str:
    return "\n".join([HEAD[0]] + [",".join(r) for r in ROWS if keep(r)]) + "\n"


NEVER_SATURATES = lines_where(lambda r: r[2] == "treated" and float(r[0]) <= 0.06)
ONE_GROUP = lines_where(lambda r: r[2] == "treated")


def cli_in(directory: Path, argv, *flags):
    """The command, run on `dataset.csv` in `directory` as the recorded command line does."""
    old = os.getcwd()
    os.chdir(directory)
    try:
        return run_cli(rates_main, [*argv, *flags])
    finally:
        os.chdir(old)


@pytest.fixture(scope="module")
def puromycin(tmp_path_factory):
    work = tmp_path_factory.mktemp("rates")
    recorder = Recorder()
    outcome = adapter.run(REQUEST, context(work, recorder))
    for artifact in outcome.artifacts:
        (work / artifact.name).write_bytes(artifact.content)
    return outcome, work, recorder, adapter.argv(REQUEST)


# ---------------------------------------------------------------------------
# Parity with the command
# ---------------------------------------------------------------------------


def test_the_run_is_registered_and_its_command_line_is_the_commands(puromycin):
    outcome, _work, _recorder, argv = puromycin
    registry = load_registry()
    spec = registry.get("rates")
    assert spec is not None and spec.cli_prefix == ("caterva", "rates") and "rates" in registry.kinds()
    assert argv == ["dataset.csv", "--sigma-from", "residuals", "--group", "state"]
    assert outcome.exit_code == 0 and outcome.refusal is None


def test_the_report_is_the_commands_stdout(puromycin):
    outcome, work, _r, argv = puromycin
    code, out, err = cli_in(work, argv)
    assert code == 0 and err == ""
    assert outcome.result["report_text"] == out


def test_the_analysis_is_the_commands_json_to_the_byte(puromycin):
    outcome, work, _r, argv = puromycin
    code, out, _err = cli_in(work, argv, "--json")
    assert code == 0
    assert json.dumps(outcome.result["analysis"], indent=2) + "\n" == out


def test_the_files_are_the_commands_exports(puromycin):
    outcome, work, _r, argv = puromycin
    files = {a.name: a.content.decode("utf-8") for a in outcome.artifacts}
    assert set(files) == {"dataset.csv", "parameters.csv", "curves.csv", "report.md", "methods.txt"}
    assert files["parameters.csv"] == cli_in(work, argv, "--export", "csv")[1]
    assert files["curves.csv"] == cli_in(work, argv, "--export", "curves")[1]
    assert files["report.md"] == outcome.result["report_text"]
    engine_methods = cli_in(work, argv, "--export", "methods")[1]
    sentence = ingest.methods_sentence(ingest.inspect(TEXT, filename="puromycin.csv"))
    assert files["methods.txt"] == outcome.result["methods"]
    assert outcome.result["methods"].replace(" " + sentence, "") == engine_methods
    assert "dataset.csv" not in outcome.result["methods"] and "puromycin.csv" in sentence


def test_the_numbers_are_rs_nls_on_the_puromycin_table(puromycin):
    outcome, *_ = puromycin
    rows = {(p["group"], p["constant"]): p for p in outcome.result["parameters"] if p["law"] == "michaelis-menten"}
    for constant, expected in R_TREATED.items():
        row = rows[("treated", constant)]
        assert row["estimate"] == pytest.approx(expected, rel=2e-3)
        assert row["determined"] and row["value"]["value"] == row["estimate"]
        assert row["value"]["provenance"]["kind"] == "fitted"
        assert row["value"]["provenance"]["fit"]["n_points"] == 12
        assert row["interval_method"] == "profile likelihood"
    assert rows[("treated", "Vmax")]["low"] == pytest.approx(197.30212847588, rel=2e-3)
    assert rows[("treated", "Km")]["high"] == pytest.approx(0.08615995299, rel=2e-3)


def test_the_studio_and_the_command_give_the_same_numbers_for_every_constant(puromycin):
    outcome, work, _r, argv = puromycin
    code, out, _ = cli_in(work, argv, "--json")
    engine = json.loads(out)
    theirs = {}
    for group in engine["results"]:
        for law in group["laws"]:
            for c in law["constants"]:
                theirs[(group["group"], law["law"], c["constant"])] = (c["estimate"], c["low"], c["high"], c["standard_error"])
    mine = {(p["group"], p["law"], p["constant"]): (p["estimate"], p["low"], p["high"], p["standard_error"])
            for p in outcome.result["parameters"] if not p["product"]}
    assert len(mine) == 5 and set(mine) <= set(theirs)
    assert all(mine[k] == theirs[k] for k in mine)


def test_dataset_csv_is_the_table_the_engine_read_and_keeps_the_files_own_comments(puromycin):
    outcome, *_ = puromycin
    text = next(a for a in outcome.artifacts if a.name == "dataset.csv").content.decode("utf-8")
    assert "# source: Treloar MA (1974)" in text
    assert text.splitlines().count("substrate (ppm),rate (counts/min/min),state") == 1
    assert text.count(",treated") == 12 and text.count(",untreated") == 11


# ---------------------------------------------------------------------------
# What the page draws is the engine's
# ---------------------------------------------------------------------------


def test_the_figure_is_the_fit_it_draws(puromycin):
    outcome, *_ = puromycin
    fig = outcome.result["figure"]
    assert [s["label"] for s in fig["series"]] == ["treated", "untreated"]
    assert fig["x"] == {"name": "substrate concentration", "unit": "ppm", "column": "substrate"}
    assert fig["bars"]["source"] == "residuals" and "residual standard error" in fig["bars"]["text"]
    treated, untreated = fig["series"]
    assert (treated["law"], untreated["law"]) == ("michaelis-menten", "hill")
    assert len(treated["points"]["s"]) == 12 and len(untreated["points"]["s"]) == 11
    p = treated["points"]
    for v, f, r in zip(p["v"], p["fitted"], p["residual"]):
        assert r == pytest.approx(v - f, rel=1e-12, abs=1e-12)
    km, vmax = R_TREATED["Km"], R_TREATED["Vmax"]
    for s, f in zip(p["s"], p["fitted"]):
        assert f == pytest.approx(vmax * s / (km + s), rel=2e-3)
    c = treated["curve"]
    assert all(lo < v < hi for lo, v, hi in zip(c["low"], c["v"], c["high"]))
    assert c["s"] == sorted(c["s"]) and c["s"][0] > 0
    assert "asymptotic, pointwise" in treated["band"]
    assert fig["notes"] == []  # each group's verdict names one law, so there is no second curve to explain


def test_the_laws_compared_carry_aicc_and_the_engines_verdict(puromycin):
    outcome, *_ = puromycin
    by_group = {c["group"]: c for c in outcome.result["comparison"]}
    untreated = by_group["untreated"]
    status = {l["law"]: l["status"] for l in untreated["laws"]}
    assert status["hill"] == "reported" and status["michaelis-menten"] == "ruled out"
    assert any("reject Michaelis-Menten in favour of the Hill law" in s for s in untreated["verdict"])
    for c in by_group.values():
        deltas = [l["delta_aicc"] for l in c["laws"] if l["fitted"]]
        assert min(deltas) == 0.0 and all(d >= 0 for d in deltas)
    treated = by_group["treated"]
    assert treated["decided"] and not any(t["ruled_out"] for t in treated["tests"])
    assert {t["general"] for t in treated["tests"]} == {"substrate-inhibition", "hill"}


def test_the_lack_of_fit_is_one_sentence_with_its_p_and_what_it_means(puromycin):
    outcome, *_ = puromycin
    first = outcome.result["lack_of_fit"][0]
    assert first["tested"] and first["failed"] is False and first["p"] == pytest.approx(0.447, abs=1e-3)
    assert first["sentence"].startswith("Lack of fit F = 1.07 on 4 and 6 degrees of freedom, p = 0.447")
    assert "could not show it wrong" in first["trust"]


def test_groups_are_compared_in_the_engines_words(puromycin):
    outcome, *_ = puromycin
    groups = outcome.result["groups"]
    assert groups["groups"] == ["treated", "untreated"] and groups["law"] == "michaelis-menten"
    vm = next(t for t in groups["tests"] if t["constant"] == "Vmax")
    assert vm["differs"] and vm["statistic"].startswith("F(1, 19) = 25.5") and vm["p"] == pytest.approx(7.08e-05, rel=1e-2)
    assert any("Not detected is not the same as equal" in s for s in groups["sentences"])


def test_the_uncertainty_is_named_with_the_sentence_that_says_why_it_matters(puromycin):
    outcome, *_ = puromycin
    sigma = outcome.result["sigma"]
    assert sigma["source"] == "residuals" and "assumes the model is right" in sigma["description"]
    assert "assumes the rate law is right" in sigma["why"]
    assert outcome.result["interval_basis"]["method"].startswith("95% profile-likelihood interval")


def test_the_cite_line_names_the_version_and_the_repository_and_nothing_invented(puromycin):
    outcome, *_ = puromycin
    cite = outcome.result["cite"]
    assert report._version() in cite and "https://github.com/math12345678/caterva" in cite and "caterva.app" not in cite
    assert "doi" not in cite.lower()


# ---------------------------------------------------------------------------
# Honest progress, cancel, refusals
# ---------------------------------------------------------------------------


def test_progress_names_every_law_fitted_and_its_fraction_rises_to_the_end(puromycin):
    _outcome, _w, recorder, _argv = puromycin
    stages = [c for c in recorder.calls if c[0] == "stage"]
    keys = [s[1] for s in stages]
    assert keys[0] == "read" and keys[-1] == "report"
    fits = [s for s in stages if s[1].startswith("fit-")]
    assert [s[1] for s in fits] == ["fit-michaelis-menten", "fit-substrate-inhibition", "fit-hill"] * 2
    fractions = [s[3] for s in fits]
    assert fractions == [0 / 6, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6]
    assert "treated" in fits[0][2] and "untreated" in fits[3][2]


def test_a_cancel_stops_the_fit_between_laws_and_raises_cancelled(tmp_path):
    recorder = Recorder(cancel_at="fit-substrate-inhibition")
    with pytest.raises(Cancelled):
        adapter.run(REQUEST, context(tmp_path, recorder))
    assert "fit-hill" not in [c[1] for c in recorder.calls if c[0] == "stage"]


def test_the_per_kind_time_limit_stops_a_real_run_and_says_whether_it_stopped(tmp_path):
    from caterva.studio.jobs import JobManager
    from caterva.studio.workspace import Workspace

    ws = Workspace(tmp_path / "data")
    ws.ensure()
    ws.claim("0123456789abcdef")
    manager = JobManager(ws, load_registry(("rates",)), instance_id="0123456789abcdef", timeout_s=0.2,
                         cancel_grace_s=60.0, keepalive_s=0.2, poll_s=0.05, tick_s=0.02)
    try:
        run_id = manager.submit("rates", REQUEST)["id"]
        deadline = time.monotonic() + 120
        while manager.record(run_id)["status"] not in ("failed", "cancelled", "abandoned", "done") and time.monotonic() < deadline:
            time.sleep(0.05)
        record = manager.record(run_id)
        assert record["status"] == "failed" and record["error"]["type"] == "TimedOut"
        assert "stopped at its next check" in record["error"]["message"]
    finally:
        manager.shutdown()


def test_the_kind_has_a_time_limit_in_the_jobs_table():
    from caterva.studio.jobs import KIND_TIMEOUTS_S

    assert KIND_TIMEOUTS_S["rates"] == 30 * 60.0


def test_a_table_that_cannot_bound_km_is_said_so_and_shows_no_confident_number(tmp_path):
    request = {"dataset": {"text": NEVER_SATURATES, "filename": "low.csv"}, "sigma_from": "residuals"}
    outcome = adapter.run(request, context(tmp_path))
    assert outcome.exit_code == 0
    rows = {p["constant"]: p for p in outcome.result["parameters"]}
    assert rows["Km"]["determined"] is False and rows["Km"]["estimate"] is None and rows["Km"]["value"] is None
    assert rows["Vmax"]["estimate"] is None and rows["Vmax"]["interval"].startswith("> ")
    assert rows["Vmax/Km"]["determined"] and rows["Vmax/Km"]["product"] and rows["Vmax/Km"]["value"]["provenance"]["kind"] == "fitted"
    kinds = {c["kind"] for c in outcome.result["cautions"]}
    assert "undetermined" in kinds
    caution = next(c for c in outcome.result["cautions"] if c["kind"] == "undetermined")
    assert "Every substrate concentration is well below Km" in caution["text"]
    assert "measure at higher concentrations" in caution["change"] and "the highest is 0.06 ppm" in caution["change"]
    # What to change is said once: under the caution, not again in the list below it.
    assert caution["change"] not in outcome.result["better"]
    # Cautions are shown once each.
    texts = [c["text"] for c in outcome.result["cautions"]]
    assert len(texts) == len(set(texts))
    lof = outcome.result["lack_of_fit"][0]
    assert lof["tested"] is False and "needs replicates" in lof["sentence"]


def test_a_single_group_is_fitted_and_named_and_not_compared(tmp_path):
    request = {"dataset": {"text": ONE_GROUP}, "sigma_from": "residuals"}
    outcome = adapter.run(request, context(tmp_path))
    assert outcome.exit_code == 0 and outcome.result["groups"] is None
    assert [s["label"] for s in outcome.result["figure"]["series"]] == ["treated"]


def test_the_engine_refuses_stay_exit_3_in_the_commands_words(tmp_path):
    with_sigma = "substrate (ppm),rate (counts/min/min),sigma (counts/min/min)\n0.02,76,5\n0.06,97,5\n0.11,123,5\n0.22,159,5\n"
    outcome = adapter.run({"dataset": {"text": with_sigma}, "sigma_from": "column"}, context(tmp_path))
    assert outcome.exit_code == 0 and outcome.result["sigma"]["source"] == "column"
    single = "\n".join([HEAD[0]] + [",".join(r) for r in ROWS if r[2] == "treated"][::2])
    refused = adapter.run({"dataset": {"text": single}, "sigma_from": "replicates"}, context(tmp_path))
    assert refused.exit_code == 3 and refused.result is None
    assert refused.refusal.startswith("caterva rates: ") and "measured more than once" in refused.refusal
    two = adapter.run({"dataset": {"text": with_sigma}, "sigma_from": "residuals"}, context(tmp_path))
    assert two.exit_code == 3 and "Exactly one source of uncertainty" in two.refusal
    forced = adapter.run({**REQUEST, "model": "competitive"}, context(tmp_path))
    assert forced.exit_code == 3 and "needs rates measured with an inhibitor" in forced.refusal


def test_a_literature_comparison_the_command_declines_keeps_the_report_and_is_exit_3(tmp_path):
    request = {**REQUEST, "ec": "2.4.1.22", "organism": "human", "substrate": "galactose"}
    outcome = adapter.run(request, context(tmp_path))
    assert outcome.exit_code == 3 and outcome.result is not None
    assert outcome.refusal.startswith("caterva rates: a literature comparison was not made: Km [treated]: the substrate column is in 'ppm'")
    declined = outcome.result["literature"]
    assert declined and all(not row["found"] and row["cited"] is None for row in declined)
    assert "cannot be converted to a molar concentration" in declined[0]["sentence"]
    assert outcome.result["parameters"], "the fit is still there"
    assert adapter.needs_for(request) == ("network", "literature") and adapter.needs_for(REQUEST) == ()


def test_kcat_is_vmax_over_the_enzyme_concentration_and_never_from_an_arbitrary_unit(tmp_path):
    refused = adapter.run({**REQUEST, "enzyme_concentration": 1.0, "enzyme_unit": "uM"}, context(tmp_path))
    assert refused.exit_code == 0 and refused.result["turnover"] == []
    assert "not a molar concentration per time" in refused.result["turnover_refused"]
    labelled = ONE_GROUP.replace("(ppm)", "(mM)").replace("(counts/min/min)", "(uM/min)")
    request = {"dataset": {"text": labelled}, "sigma_from": "residuals", "enzyme_concentration": 0.5, "enzyme_unit": "uM",
               "model": "michaelis-menten"}
    outcome = adapter.run(request, context(tmp_path))
    vmax = next(p for p in outcome.result["parameters"] if p["constant"] == "Vmax")
    per_s = {t["unit"]: t for t in outcome.result["turnover"]}
    # 212.68 uM/min over 0.5 uM is 425.4 per minute, 7.09 per second.
    assert per_s["1/min"]["estimate"] == pytest.approx(vmax["estimate"] / 0.5, rel=1e-12)
    assert per_s["1/s"]["estimate"] == pytest.approx(vmax["estimate"] / 0.5 / 60.0, rel=1e-12)
    assert per_s["1/s"]["low"] == pytest.approx(vmax["low"] / 0.5 / 60.0, rel=1e-12)
    assert per_s["1/s"]["value"]["provenance"]["kind"] == "computed"
    assert "taken as exact" in outcome.result["methods"]


def test_cancel_and_artifacts_are_the_adapters_and_the_result_is_json():
    # The result must survive the studio's own serialisation unchanged.
    outcome = adapter.run(REQUEST, context(Path(os.environ.get("TMPDIR", "/tmp"))))
    assert json.loads(json.dumps(outcome.result, allow_nan=False)) == outcome.result


# ---------------------------------------------------------------------------
# The request is validated before any run exists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("request_,field,phrase", [
    ({}, "dataset", "dataset is required"),
    ({"dataset": "puromycin.csv", "sigma_from": "residuals"}, "dataset", "dataset is required"),
    ({"dataset": {"text": 5}, "sigma_from": "residuals"}, "dataset", "must be the table as a string"),
    ({"dataset": {"path": "/etc/passwd"}, "sigma_from": "residuals"}, "dataset", "is not a dataset key"),
    ({"dataset": {"text": TEXT}}, "sigma_from", "sigma_from is required"),
    ({"dataset": {"text": TEXT}, "sigma_from": "guess"}, "sigma_from", "sigma_from is required"),
    ({"dataset": {"text": TEXT}, "sigma_from": "column"}, "sigma_from", "no standard-deviation column"),
    ({"dataset": {"text": TEXT}, "sigma_from": "residuals", "colour": "red"}, "colour", "is not a rates request key"),
    ({"dataset": {"text": TEXT}, "sigma_from": "residuals", "level": "high"}, "level", "must be a number"),
    ({"dataset": {"text": TEXT}, "sigma_from": "residuals", "ec": ""}, "ec", "non-empty text"),
    ({"dataset": {"text": "x\x00y"}, "sigma_from": "residuals"}, "dataset", "NUL byte"),
    ({"dataset": {"text": "S (mM)\tv (uM/min)\n" + "1\t2\n" * (ingest.MAX_ROWS + 1)}, "sigma_from": "residuals"}, "dataset", "limited to 2,000"),
    ({"dataset": {"text": TEXT, "mapping": {"roles": {"substrate": 99}}}, "sigma_from": "residuals"}, "dataset", "roles.substrate"),
    ({"dataset": {"text": TEXT}, "sigma_from": "residuals", "enzyme_concentration": 1.0}, "enzyme_concentration", "needs its unit"),
    ({"dataset": {"text": TEXT}, "sigma_from": "residuals", "enzyme_concentration": -1.0, "enzyme_unit": "uM"}, "enzyme_concentration", "positive"),
    ({"dataset": {"text": TEXT}, "sigma_from": "residuals", "enzyme_concentration": 1.0, "enzyme_unit": "ppm"}, "enzyme_concentration", "not a molar unit"),
])
def test_a_request_that_is_not_a_question_is_refused_under_the_field_it_names(request_, field, phrase):
    with pytest.raises(contract.Malformed) as refused:
        adapter.argv(request_)
    assert refused.value.field == field and phrase in str(refused.value)


def test_the_commands_own_parser_refuses_what_it_would_refuse():
    for extra, phrase in (({"level": 95}, "--level is a probability"),
                          ({"significance": 2}, "--significance is a probability"),
                          ({"ec": "1.1.1.27", "substrate": "pyruvate"}, "--ec needs --organism"),
                          ({"substrate": "pyruvate"}, "need --ec"),
                          ({"model": "linear"}, "invalid choice")):
        with pytest.raises(contract.Malformed) as refused:
            adapter.argv({**REQUEST, **extra})
        assert phrase in str(refused.value), extra


def test_a_table_over_the_byte_limit_is_refused_naming_the_limit():
    big = "S (mM)\tv (uM/min)\n" + "1\t2\n" * (ingest.MAX_BYTES // 4 + 5)
    with pytest.raises(contract.Malformed) as refused:
        adapter.argv({"dataset": {"text": big}, "sigma_from": "residuals"})
    assert f"{ingest.MAX_BYTES:,} bytes" in str(refused.value)


# ---------------------------------------------------------------------------
# The endpoint, and exports
# ---------------------------------------------------------------------------


def preview(body):
    return adapter.preview_endpoint(EndpointRequest(params={}, query={}, body=body, data_dir=Path(".")))


def test_the_preview_endpoint_is_ingest_inspect_and_a_bad_table_is_an_answer_not_a_400():
    answer = preview({"text": TEXT, "filename": "puromycin.csv"})
    assert answer == ingest.inspect(TEXT, filename="puromycin.csv")
    bad = preview({"text": "a\x00b"})
    assert bad["ok"] is False and "NUL" in bad["refusal"]
    with pytest.raises(contract.Malformed):
        preview({"text": 5})
    with pytest.raises(contract.Malformed):
        preview({"text": "x", "path": "/etc/passwd"})
    with pytest.raises(contract.Malformed):
        preview({"text": "x", "mapping": {"roles": {"substrate": "zero"}}})
    with pytest.raises(contract.Malformed):
        preview(None)


def test_the_route_is_owned_by_the_adapter_and_documented():
    from caterva.studio import routes

    route = next(r for r in routes.ROUTES if r.handler == "rates_preview")
    assert (route.method, route.path, route.owner) == ("POST", "/api/rates/preview", "rates")
    registry = load_registry(("rates",))
    assert registry.endpoint("rates_preview") is adapter.preview_endpoint


def test_a_formula_in_a_group_label_is_inert_in_the_exported_csv_and_numbers_are_not_touched(tmp_path):
    labels = "substrate (ppm),rate (counts/min/min),group\n" + "\n".join(
        f"{r[0]},{r[1]},{'=cmd' if r[2] == 'treated' else '+puro'}" for r in ROWS) + "\n"
    outcome = adapter.run({"dataset": {"text": labels}, "sigma_from": "residuals"}, context(tmp_path))
    files = {a.name: a.content.decode() for a in outcome.artifacts}
    for name in ("parameters.csv", "curves.csv"):
        cells = [c for row in csv.reader(io.StringIO(files[name])) for c in row]
        assert "'=cmd" in cells and "'+puro" in cells, name
        assert "=cmd" not in cells and "+puro" not in cells
    negative = adapter.neutralised_csv("a,b\n-0.5,-x\n")
    assert negative == "a,b\n-0.5,'-x\n"


def test_the_law_list_on_the_page_is_the_engines():
    from caterva.rates.models import LAWS

    source = (REPO / "Science-Agent-Pipeline" / "artifacts" / "caterva-studio" / "src" / "screens" / "rates" / "model.ts").read_text()
    block = source[source.index("export const RATE_LAWS"):source.index("export type Origin")]
    found = re.findall(r'\{ name: "([a-z-]+)", title: "([^"]+)", equation: "([^"]+)", inhibitor: (true|false) \}', block)
    assert [f[0] for f in found] == list(LAWS)
    for name, title, equation, inhibitor in found:
        law = LAWS[name]
        assert title.lower() == law.title.lower() and equation == law.equation.replace("Ki'", "Ki'")
        assert (inhibitor == "true") == law.needs_inhibitor
