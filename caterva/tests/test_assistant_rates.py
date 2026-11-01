"""The assistant on a Rates run: the digest, the grounding and the five features, on the REAL Rates results.

SOURCES ARE REAL; WORDING IS HAND-WRITTEN
-----------------------------------------
Every source here is a real captured Caterva Studio Rates run, the fixtures the Rates screen's own tests use
(Science-Agent-Pipeline/artifacts/caterva-studio/src/__fixtures__/api/rates/): Puromycin's treated and untreated
groups fitted with replicate-based error bars, a table that never reaches saturation (Vmax has only a lower
bound), and a run whose BRENDA comparison was declined. The replies are hand-written test inputs: faithful
ones that quote the result's own figures, and hostile ones that change a figure, a unit or add a claim. The
network is a `FakeTransport`: these are mechanism tests of what the studio does with a reply.

WHAT THIS PROVES, AND NOT
-------------------------
It proves the assistant reads the Rates result JSON (not a rewritten one), that a Rates digest never carries
the figure's drawn points or the reading of the person's file unless they ticked "include my data", that the
constants' numbers are grounded and altered ones are rejected, and that "What to measure next" says plainly
that it does not apply. It does not prove a model's wording is good.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest
from assistant_support import FakeTransport, anthropic_reply, call, make_app, prepare_and_send, switch_on

from caterva.assistant import grounding
from caterva.assistant.digest import digest, engine_text

RATES = (Path(__file__).resolve().parents[2] / "Science-Agent-Pipeline" / "artifacts" / "caterva-studio"
         / "src" / "__fixtures__" / "api" / "rates")


def _fixture(name: str) -> Dict[str, Any]:
    return json.loads((RATES / f"{name}.json").read_text(encoding="utf-8"))


def _install(app, name: str) -> str:
    data = _fixture(name)
    record = dict(data["run"])
    app.ws.create_run(record, record["request"], owner=None)
    app.ws.write_result(record["id"], data["result"])
    for artifact in record.get("artifacts") or []:
        app.ws.write_artifact(record["id"], artifact["name"], f"(test body of {artifact['name']})".encode())
    # methods.txt is the engine's own paragraph: write what the result says, as the adapter does.
    app.ws.write_artifact(record["id"], "methods.txt", data["result"]["methods"].encode("utf-8"))
    app.ws.write_record(record)
    return record["id"]


def _source(name: str, include_input: bool = False) -> Dict[str, Any]:
    run = _fixture(name)
    return digest(run["run"]["kind"], run["result"], run["run"], include_input=include_input)


REPLICATES = "run-puromycin-replicates"
NEVER = "run-never-saturates"
DECLINED = "run-literature-declined"
FULL = [REPLICATES, "run-puromycin-residuals", NEVER, DECLINED]


def _numbers(value: Any, out: List[float]) -> List[float]:
    if isinstance(value, dict):
        for v in value.values():
            _numbers(v, out)
    elif isinstance(value, list):
        for v in value:
            _numbers(v, out)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        out.append(float(value))
    return out


# ---------------------------------------------------------------------------
# The digest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", FULL)
def test_a_rates_digest_is_kept_whole_and_comes_from_the_result_json(name):
    run = _fixture(name)
    dg = _source(name)
    assert dg["run_kind"] == "rates"
    assert "too large" not in json.dumps(dg), "a real Rates result must not be reduced to its outcome alone"
    assert len(json.dumps(dg, ensure_ascii=False)) <= 28_000
    # Every number the assistant may quote is a number of the result, unchanged: a subset, never a rewrite.
    in_result = set(_numbers(run["result"], []))
    assert set(_numbers(dg["result"], [])) <= in_result
    for p in run["result"]["parameters"]:
        if p["estimate"] is not None:
            assert p["estimate"] in set(_numbers(dg["result"]["parameters"], []))


def test_the_digest_holds_the_constants_intervals_and_tests():
    result = _source(REPLICATES)["result"]
    treated_vmax = next(p for p in result["parameters"] if p["group"] == "treated" and p["constant"] == "Vmax")
    assert treated_vmax["value"]["provenance"]["kind"] == "fitted"
    assert treated_vmax["interval"] == "174.2 to 232.6" and treated_vmax["unit"] == "counts/min/min"
    assert any(row["tested"] and row["p"] == pytest.approx(0.7235904633842318) for row in result["lack_of_fit"])
    assert any("Vmax" in line and "201.7" in line for line in result["verdict"])
    declined = _source(DECLINED)["result"]
    assert any(row["found"] is False and row["refused"] for row in declined["literature"])


def test_the_figure_points_and_the_reading_of_the_file_are_not_sent_unless_asked():
    name = REPLICATES
    run = _fixture(name)
    withheld = _source(name)
    text = json.dumps(withheld["result"])
    assert "figure" not in withheld["result"] and "report_text" not in withheld["result"]
    assert "data_reading" not in withheld["result"], "the decisions quote the person's file"
    assert withheld["your_input"].startswith("withheld")
    assert "comment line(s)" not in text and "(long layout)" not in text
    included = _source(name, include_input=True)
    assert included["result"]["data_reading"]["decisions"] == run["result"]["dataset"]["decisions"]
    assert included["your_input"]["dataset"]["filename"] == "puromycin.csv"
    assert "text" in included["your_input"]["dataset"]


def test_the_page_falls_back_to_the_engines_own_report_for_a_rates_run():
    run = _fixture(REPLICATES)
    text = engine_text("rates", run["result"], run["run"])
    assert text.startswith("# Initial rates") and "Vmax" in text


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------

FAITHFUL = [
    (REPLICATES, "For the treated group Vmax is 201.7 counts/min/min (95% profile interval 174.2 to 232.6 "
                 "counts/min/min) and Km is 0.05127 ppm (0.03421 to 0.0754 ppm)."),
    (REPLICATES, "Lack of fit F = 0.523 on 4 and 6 degrees of freedom, p = 0.724: no departure from this law's shape."),
    (NEVER, "Vmax is at least 55.7 counts/min/min: the data do not determine an upper bound."),
    (DECLINED, "Vmax differs between treated and untreated (F(1, 19) = 25.5, p = 7.08e-05); Km does not (p = 0.206)."),
    (REPLICATES, "The intervals are profile-likelihood intervals (Bates and Watts 1988), and the error bars come from "
                 "11 replicate sets."),
]

HOSTILE = [
    (REPLICATES, "The treated Km is 0.083 ppm.", "number"),
    (REPLICATES, "The treated Vmax is 201.7 mM.", "unit"),
    (REPLICATES, "The treated Vmax is 210.7 counts/min/min.", "number"),
    (REPLICATES, "Lack of fit gave p = 0.61.", "number"),
    (REPLICATES, "The treated Km is 51.27 ppb.", "number"),
    (REPLICATES, "Vmax is 201.7 counts/min/min, significantly higher than reported in the literature.", "comparison"),
    (REPLICATES, "The treated Km is 0.0754 ppm, in agreement with BRENDA.", "name"),
    (NEVER, "Vmax is 55.7 counts/min/min, with an upper bound of 120 counts/min/min.", "number"),
    (NEVER, "Vmax is greater than 55.7 counts/min/min.", "comparison"),
    (DECLINED, "The treated Km agrees with the literature value of 0.0617 ppm.", "number"),
]


@pytest.mark.parametrize("name,text", FAITHFUL)
def test_faithful_wording_about_a_rates_result_is_accepted(name, text):
    result = grounding.check(text, _source(name))
    assert result.ok, [(f.kind, f.token) for f in result.failures]


@pytest.mark.parametrize("name,text,kind", HOSTILE)
def test_altered_or_invented_wording_about_a_rates_result_is_rejected(name, text, kind):
    result = grounding.check(text, _source(name))
    assert not result.ok and kind in {f.kind for f in result.failures}, [(f.kind, f.token) for f in result.failures]


def test_a_bound_is_written_at_least_and_the_prompt_says_so():
    from caterva.assistant.prompts import COMMON_RULES

    assert "at least" in COMMON_RULES and "at most" in COMMON_RULES
    # the engine writes the bound as ">": "greater than" is a comparison the result does not state, so it is
    # refused (the safe direction: the page then shows the engine's own text) and "at least" is not.
    source = _source(NEVER)
    assert "> 55.7" in json.dumps(source)
    assert grounding.check("Vmax is at least 55.7 counts/min/min.", source).ok
    assert not grounding.check("Vmax is greater than 55.7 counts/min/min.", source).ok


# ---------------------------------------------------------------------------
# The features, through the studio's dispatch, on a Rates run
# ---------------------------------------------------------------------------

EXPLAIN_RATES = json.dumps({
    "summary": "Treated Vmax is 201.7 counts/min/min (174.2 to 232.6 counts/min/min).",
    "worst_thing": "The treated Km interval, 0.03421 to 0.0754 ppm, is wide.",
    "next_step": "Measure rates at more concentrations.",
    "terms": [{"term": "profile likelihood", "meaning": "an interval found by refitting at fixed values"}]})
EXPLAIN_RATES_BAD = json.dumps({
    "summary": "Treated Vmax is 210.7 counts/min/min.", "worst_thing": "None.", "next_step": "Publish.", "terms": []})
ASK_RATES = json.dumps({"answerable": True, "answer": "The lack of fit test gave p = 0.724 for the treated group."})
METHODS_RATES = json.dumps({"text": "Initial rates (23 measurements at 12 distinct conditions, in 2 groups) were "
                                    "fitted by nonlinear least squares; 95% confidence intervals are "
                                    "profile-likelihood intervals (Bates & Watts 1988)."})


def _app(tmp_path, *replies):
    ft = FakeTransport(*replies)
    return make_app(tmp_path, ft), ft


def test_explain_works_on_a_rates_run_and_what_the_assistant_was_sent_is_the_rates_digest(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(EXPLAIN_RATES))
    run_id = _install(app, REPLICATES)
    switch_on(app, "explain")
    preview, answer = prepare_and_send(app, "explain", run_id=run_id)
    assert answer["outcome"] == "accepted" and answer["grounding"]["ok"] is True
    assert answer["content"]["kind"] == "ai" and answer["content"]["reply"]["summary"].startswith("Treated Vmax")
    assert answer["fallback"]["text"].startswith("# Initial rates"), "the engine's own report rides along"
    sent = ft.last_body.decode("utf-8")
    assert "201.67400350707237" in sent and "profile likelihood" in sent
    assert "comment line(s)" not in sent and '"series"' not in sent, "the figure's points and the file reading stay home"
    assert re.search(r"withheld", sent)


def test_explain_with_a_changed_figure_is_rejected_on_a_rates_run(tmp_path):
    app, _ = _app(tmp_path, anthropic_reply(EXPLAIN_RATES_BAD))
    run_id = _install(app, REPLICATES)
    switch_on(app, "explain")
    _, answer = prepare_and_send(app, "explain", run_id=run_id)
    assert answer["outcome"] == "rejected" and answer["content"] is None
    assert {f["kind"] for f in answer["rejection"]["failures"]} >= {"number"}
    assert answer["fallback"]["text"].startswith("# Initial rates")


def test_ask_works_on_a_rates_run_and_its_fallback_names_the_nearest_facts(tmp_path):
    app, _ = _app(tmp_path, anthropic_reply(ASK_RATES))
    run_id = _install(app, REPLICATES)
    switch_on(app, "ask")
    _, answer = prepare_and_send(app, "ask", run_id=run_id, question="Did the lack of fit test pass for the treated group?")
    assert answer["outcome"] == "accepted" and answer["grounding"]["ok"] is True
    assert "p = 0.724" in answer["content"]["reply"]["answer"]
    assert "lack_of_fit" in answer["fallback"]["text"]


def test_methods_on_a_rates_run_starts_from_the_engines_own_paragraph(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(METHODS_RATES))
    run_id = _install(app, REPLICATES)
    switch_on(app, "methods")
    _, answer = prepare_and_send(app, "methods", run_id=run_id)
    assert answer["outcome"] == "accepted" and answer["grounding"]["ok"] is True
    engine = _fixture(REPLICATES)["result"]["methods"]
    assert answer["fallback"]["text"] == engine[:3000], "the fallback is the engine's paragraph, not a placeholder"
    assert "engine_methods_text" in ft.last_body.decode("utf-8")


def test_next_says_it_does_not_apply_to_a_rates_run(tmp_path):
    app, ft = _app(tmp_path)
    run_id = _install(app, REPLICATES)
    switch_on(app, "next")
    response = call(app, "POST", "/api/assistant/prepare", {"feature": "next", "run_id": run_id})
    assert response.status == 409
    message = response.json()["error"]["message"]
    assert "Rates" in message and "Compose" not in message
    assert ft.calls == []


def test_a_rates_run_with_no_result_is_prepared_from_its_outcome_alone(tmp_path):
    app, _ = _app(tmp_path, anthropic_reply(EXPLAIN_RATES))
    data = _fixture("run-refused-law-needs-inhibitor")
    record = dict(data["run"])
    app.ws.create_run(record, record["request"], owner=None)
    app.ws.write_record(record)
    switch_on(app, "explain")
    response = call(app, "POST", "/api/assistant/prepare", {"feature": "explain", "run_id": record["id"]})
    assert response.status == 200
    payload = response.json()["payload"]
    assert "run_kind" in payload and "rates" in payload and "result" in payload
