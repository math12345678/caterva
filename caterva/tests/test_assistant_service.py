"""The assistant service through the studio's dispatch layer: gates, consent, the five features, the audit.

REAL RESULTS, FAKE TRANSPORT
----------------------------
Every feature runs on a REAL captured engine result (assistant_support.install_run). The network is a
`FakeTransport`, so these are mechanism tests: they prove what the studio does with a reply, not what a model
would say. The replies are hand-written test inputs: faithful ones built from the real result's own words and
figures, and hostile ones that add something the result does not hold.
"""
from __future__ import annotations

import io
import json
import logging
import os
import socket
import threading
import time
import zipfile
from pathlib import Path

import pytest
from assistant_support import (
    TEST_KEY, FakeTransport, TransportResponse, anthropic_reply, call, install_run, load_fixture, make_app,
    openai_reply, prepare_and_send, switch_on,
)

from caterva.assistant.providers import AssistantError

EXPLAIN_OK = json.dumps({
    "summary": "The verdict is structural, so this run supports questions about the mechanism only.",
    "worst_thing": "Only 2 constants are measured and 1 is still a placeholder.",
    "next_step": "Re-run with an organism that holds a measurement.",
    "terms": [{"term": "placeholder", "meaning": "a stand-in value nobody has measured here"}]})
EXPLAIN_BAD = json.dumps({
    "summary": "The Km is 0.5 mM, significantly higher than the Ki.",
    "worst_thing": "Nothing.", "next_step": "Publish it.", "terms": []})
ASK_OK = json.dumps({"answerable": True, "answer": "kcat is a placeholder: it has no value in the organism requested."})
METHODS_OK = json.dumps({"text": "The Km was 0.03 mM (BRENDA ref 286469) and the Ki was 0.0014 mM (BRENDA ref 711801), "
                                 "both measured; kcat was a placeholder of 100 1/s."})
NEXT_OK = json.dumps({"narration": "The engine ranks settling_time first: it adds a new direction.",
                      "order": ["settling_time"]})
DESCRIBE_OK = json.dumps({"shape": "inhibition", "stages": None, "variant": "competitive", "substrate": "pyruvate",
                          "inhibitor": "gossypol", "organism": "human", "subject_ec": None})


def _app(tmp_path, *replies, **kw):
    ft = FakeTransport(*replies) if replies else None
    return make_app(tmp_path, ft, **kw), ft


def _compose_run(app, name="compose-ldh-gossypol-analysed"):
    return install_run(app, name)


# ---------------------------------------------------------------------------
# Off means off
# ---------------------------------------------------------------------------


def test_by_default_the_assistant_is_off_and_every_assistant_route_refuses_without_touching_anything(tmp_path, monkeypatch):
    """No transport may be created and no socket touched while the assistant is off."""
    def no_network(*a, **k):
        raise AssertionError("a socket was used while the assistant is off")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    app, _ = _app(tmp_path)          # transport None: the factory raises if it is ever called
    run_id = _compose_run(app)
    status = call(app, "GET", "/api/assistant/status").json()
    assert status["state"] == "off" and status["indicator"] == "Assistant off" and status["leaves_machine"] is False
    for feature, params in (("explain", {"run_id": run_id}), ("methods", {"run_id": run_id}),
                            ("ask", {"run_id": run_id, "question": "why?"}), ("next", {"run_id": run_id}),
                            ("describe", {"text": "a cascade"}), ("test", {})):
        response = call(app, "POST", "/api/assistant/prepare", {"feature": feature, **params})
        assert response.status == 409 and "off" in response.json()["error"]["message"].lower()
    assert call(app, "POST", "/api/assistant/send", {"call_id": "x" * 16, "payload_sha256": "0"}).status == 404
    assert not (app.ws.root / "assistant").exists() or not list((app.ws.root / "assistant").glob("*"))
    assert call(app, "GET", f"/api/runs/{run_id}").status == 200      # the rest of the studio is unaffected


def test_enabled_but_the_feature_off_refuses_that_feature_only(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(EXPLAIN_OK))
    run_id = _compose_run(app)
    switch_on(app, "explain")
    assert call(app, "POST", "/api/assistant/prepare", {"feature": "methods", "run_id": run_id}).status == 409
    assert call(app, "POST", "/api/assistant/prepare", {"feature": "explain", "run_id": run_id}).status == 200
    assert ft.calls == []


def test_status_says_what_is_missing(tmp_path):
    app, _ = _app(tmp_path)
    call(app, "PUT", "/api/assistant/settings", {"enabled": True, "features": {"explain": True}})
    assert call(app, "GET", "/api/assistant/status").json()["state"] == "needs_key"
    app.assistant.set_key("anthropic", TEST_KEY)
    s = call(app, "GET", "/api/assistant/status").json()
    assert s["state"] == "ready" and s["indicator"] == "Assistant active: sends to api.anthropic.com"
    assert s["leaves_machine"] is True and s["key"] == {"present": True, "needed": True, "source": "keychain",
                                                         "provider": "anthropic", "note": None}
    call(app, "PUT", "/api/assistant/settings", {"features": {"explain": False}})
    assert call(app, "GET", "/api/assistant/status").json()["state"] == "idle"


def test_the_default_model_is_claude_sonnet_5_5_and_the_list_is_editable(tmp_path):
    app, _ = _app(tmp_path)
    s = call(app, "GET", "/api/assistant/settings").json()
    assert s["models"]["anthropic"] == "claude-sonnet-5-5"
    updated = call(app, "PUT", "/api/assistant/settings",
                   {"model_lists": {"anthropic": ["claude-sonnet-5-5", "my-own-model"]}, "models": {"anthropic": "my-own-model"}})
    assert updated.json()["models"]["anthropic"] == "my-own-model"
    assert call(app, "GET", "/api/assistant/status").json()["model"] == "my-own-model"


def test_there_is_no_way_to_set_a_key_over_http(tmp_path):
    app, _ = _app(tmp_path)
    for body in ({"key": TEST_KEY}, {"api_key": TEST_KEY}, {"assistant_key": TEST_KEY}):
        response = call(app, "PUT", "/api/assistant/settings", body)
        assert response.status == 400
    assert TEST_KEY not in json.dumps(call(app, "GET", "/api/assistant/settings").json())


def test_local_only_refuses_a_remote_provider(tmp_path):
    app, _ = _app(tmp_path)
    assert call(app, "PUT", "/api/assistant/settings", {"local_only": True}).status == 400     # provider is anthropic
    ok = call(app, "PUT", "/api/assistant/settings", {"local_only": True, "provider": "local", "enabled": True,
                                                      "models": {"local": "llama3"}, "features": {"explain": True}})
    assert ok.status == 200
    s = call(app, "GET", "/api/assistant/status").json()
    assert s["state"] == "ready" and s["leaves_machine"] is False
    assert s["indicator"] == "Assistant active: local model, nothing leaves this computer"
    assert call(app, "PUT", "/api/assistant/settings", {"provider": "openai"}).status == 400


def test_offline_mode_blocks_a_provider_but_not_a_model_on_this_computer(tmp_path):
    app, ft = _app(tmp_path, openai_reply(EXPLAIN_OK), offline=True)
    run_id = _compose_run(app)
    switch_on(app, "explain")
    assert call(app, "GET", "/api/assistant/status").json()["state"] == "blocked"
    assert call(app, "POST", "/api/assistant/prepare", {"feature": "explain", "run_id": run_id}).status == 409
    switch_on(app, "explain", provider="local", model="llama3")
    preview, answer = prepare_and_send(app, "explain", run_id=run_id)
    assert answer["outcome"] == "accepted" and answer["local"] is True
    assert ft.calls[0]["url"].startswith("http://127.0.0.1")
    assert "authorization" not in ft.calls[0]["headers"]


def test_a_local_model_url_must_be_loopback(tmp_path):
    app, _ = _app(tmp_path)
    assert call(app, "PUT", "/api/assistant/settings", {"local_url": "http://example.com/v1/chat/completions"}).status == 400
    assert call(app, "PUT", "/api/assistant/settings", {"local_url": "http://127.0.0.1:8080/v1/chat/completions"}).status == 200


def test_the_key_may_come_from_the_environment_and_status_says_so(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(EXPLAIN_OK), environ={"CATERVA_ASSISTANT_KEY": TEST_KEY})
    run_id = _compose_run(app)
    switch_on(app, "explain", key=None)
    s = call(app, "GET", "/api/assistant/status").json()
    assert s["key"]["source"] == "environment" and "environment variable" in s["key"]["note"]
    assert TEST_KEY not in json.dumps(s)
    prepare_and_send(app, "explain", run_id=run_id)
    assert ft.calls[0]["headers"]["x-api-key"] == TEST_KEY


# ---------------------------------------------------------------------------
# Consent, the preview, and what is actually sent
# ---------------------------------------------------------------------------


def test_nothing_is_sent_before_consent_and_consent_is_per_feature(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(EXPLAIN_OK), anthropic_reply(ASK_OK))
    run_id = _compose_run(app)
    switch_on(app, "explain", "ask")
    pv = call(app, "POST", "/api/assistant/prepare", {"feature": "explain", "run_id": run_id}).json()
    assert pv["consent_required"] is True
    refused = call(app, "POST", "/api/assistant/send", {"call_id": pv["call_id"], "payload_sha256": pv["payload_sha256"]})
    assert refused.status == 409 and "confirm what will be sent" in refused.json()["error"]["message"]
    assert ft.calls == []
    ok = call(app, "POST", "/api/assistant/send", {"call_id": pv["call_id"], "payload_sha256": pv["payload_sha256"],
                                                   "consent": True})
    assert ok.status == 200 and len(ft.calls) == 1
    again = call(app, "POST", "/api/assistant/prepare", {"feature": "explain", "run_id": run_id}).json()
    assert again["consent_required"] is False
    other = call(app, "POST", "/api/assistant/prepare", {"feature": "ask", "run_id": run_id, "question": "Why is kcat a placeholder?"}).json()
    assert other["consent_required"] is True, "agreeing to one feature is not agreeing to another"
    call(app, "POST", "/api/assistant/forget-consent", {})
    assert call(app, "POST", "/api/assistant/prepare", {"feature": "explain", "run_id": run_id}).json()["consent_required"]


def test_the_preview_is_the_payload_byte_for_byte(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(EXPLAIN_OK))
    run_id = _compose_run(app)
    switch_on(app, "explain")
    preview, answer = prepare_and_send(app, "explain", run_id=run_id)
    import hashlib

    assert ft.last_body == preview["payload"].encode("utf-8")
    assert hashlib.sha256(ft.last_body).hexdigest() == preview["payload_sha256"]
    assert preview["bytes"] == len(ft.last_body)
    record = app.assistant.audit.call(preview["call_id"])
    assert record["payload"] == preview["payload"], "the audit records exactly what was sent"


def test_a_payload_other_than_the_one_shown_is_refused(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(EXPLAIN_OK))
    run_id = _compose_run(app)
    switch_on(app, "explain")
    pv = call(app, "POST", "/api/assistant/prepare", {"feature": "explain", "run_id": run_id}).json()
    bad = call(app, "POST", "/api/assistant/send", {"call_id": pv["call_id"], "payload_sha256": "0" * 64, "consent": True})
    assert bad.status == 409 and ft.calls == []
    call(app, "PUT", "/api/assistant/settings", {"models": {"anthropic": "another-model"}})
    changed = call(app, "POST", "/api/assistant/send", {"call_id": pv["call_id"], "payload_sha256": pv["payload_sha256"], "consent": True})
    assert changed.status == 409 and "changed after the preview" in changed.json()["error"]["message"]
    assert ft.calls == []


def test_the_payload_is_redacted_and_the_persons_input_is_withheld_unless_ticked(tmp_path):
    home = os.path.expanduser("~")

    def plant(record, result):
        record["title"] = f"{home}/Desktop/lab/patient_smith.csv"
        record["request"] = {**record["request"], "substrate": f"{home}/Desktop/lab/x.csv", "inhibitor": TEST_KEY}

    app, ft = _app(tmp_path, anthropic_reply(EXPLAIN_OK), anthropic_reply(EXPLAIN_OK))
    run_id = install_run(app, "compose-ldh-gossypol-analysed", plant)
    switch_on(app, "explain")
    withheld = call(app, "POST", "/api/assistant/prepare", {"feature": "explain", "run_id": run_id}).json()
    assert "patient_smith" not in withheld["payload"] and "withheld" in withheld["payload"]
    ticked = call(app, "POST", "/api/assistant/prepare", {"feature": "explain", "run_id": run_id, "include_data": True}).json()
    assert "your_input" in ticked["payload"] and "patient_smith" not in ticked["payload"]
    assert home not in ticked["payload"] and TEST_KEY not in ticked["payload"]
    assert "[path]" in ticked["payload"] and "[key]" in ticked["payload"]
    assert "ada" != getattr(os, "getlogin", lambda: "x")()  # (the login name, if long enough, is redacted below)
    assert str(app.ws.root) not in ticked["payload"]


def test_the_connection_test_sends_one_fixed_harmless_line_and_nothing_of_the_work(tmp_path):
    from caterva.assistant.service import FIXED_TEST_PROMPT

    app, ft = _app(tmp_path, anthropic_reply("ready"))
    _compose_run(app)
    switch_on(app)                            # assistant on, no feature on: the test needs none
    preview, answer = prepare_and_send(app, "test")
    body = json.loads(ft.last_body)
    assert body["messages"] == [{"role": "user", "content": FIXED_TEST_PROMPT}]
    assert answer["outcome"] == "accepted" and answer["content"]["reply"] == "ready"


# ---------------------------------------------------------------------------
# Spend guard, errors, cancel, one at a time
# ---------------------------------------------------------------------------


def test_the_spend_guard_is_a_hard_stop_and_retries_count(tmp_path):
    clock = {"t": 1_000_000.0}
    ft = FakeTransport(TransportResponse(500, b"{}"), TransportResponse(500, b"{}"), anthropic_reply(EXPLAIN_OK),
                       anthropic_reply(EXPLAIN_OK))
    app = make_app(tmp_path, ft, clock=lambda: clock["t"])
    run_id = _compose_run(app)
    switch_on(app, "explain", max_calls_per_hour=3)
    first = prepare_and_send(app, "explain", run_id=run_id)[1]          # 500, 500, then success: 3 requests
    assert first["outcome"] == "accepted" and len(ft.calls) == 3
    assert call(app, "GET", "/api/assistant/status").json()["spend"]["remaining"] == 0
    second = prepare_and_send(app, "explain", run_id=run_id)[1]
    assert second["outcome"] == "error" and second["error"]["code"] == "spend"
    assert len(ft.calls) == 3, "the limit stopped the request before it was sent"
    assert "per hour" in second["error"]["message"] and second["fallback"]["text"]
    clock["t"] += 3601
    assert call(app, "GET", "/api/assistant/status").json()["spend"]["remaining"] == 3


def test_max_tokens_per_call_is_in_the_request(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(EXPLAIN_OK))
    run_id = _compose_run(app)
    switch_on(app, "explain", max_tokens=222)
    prepare_and_send(app, "explain", run_id=run_id)
    assert json.loads(ft.last_body)["max_tokens"] == 222


def test_a_provider_failure_is_an_inline_outcome_with_the_engine_text_and_never_the_key(tmp_path):
    echoed = TransportResponse(401, json.dumps({"error": {"message": f"bad key {TEST_KEY}"}}).encode())
    app, ft = _app(tmp_path, echoed)
    run_id = _compose_run(app)
    switch_on(app, "explain")
    _, answer = prepare_and_send(app, "explain", run_id=run_id)
    assert answer["outcome"] == "error" and answer["error"]["code"] == "auth" and answer["content"] is None
    assert answer["fallback"]["text"].startswith("VERDICT: STRUCTURAL")
    assert TEST_KEY not in json.dumps(answer)
    assert TEST_KEY not in (app.ws.root / "assistant" / "calls.jsonl").read_text()


def test_cancel_stops_the_wait_and_discards_the_reply_and_one_at_a_time_holds(tmp_path):
    release = threading.Event()
    entered = threading.Event()
    ft = FakeTransport(anthropic_reply(EXPLAIN_OK))

    def block():
        entered.set()
        release.wait(5)

    ft.on_post = block
    app = make_app(tmp_path, ft)
    run_id = _compose_run(app)
    switch_on(app, "explain")
    preview = call(app, "POST", "/api/assistant/prepare", {"feature": "explain", "run_id": run_id}).json()
    box = {}
    worker = threading.Thread(target=lambda: box.update(r=call(app, "POST", "/api/assistant/send", {
        "call_id": preview["call_id"], "payload_sha256": preview["payload_sha256"], "consent": True})))
    worker.start()
    assert entered.wait(5)
    second = call(app, "POST", "/api/assistant/prepare", {"feature": "explain", "run_id": run_id}).json()
    busy = call(app, "POST", "/api/assistant/send", {"call_id": second["call_id"], "payload_sha256": second["payload_sha256"]})
    assert busy.status == 409 and "in flight" in busy.json()["error"]["message"]
    assert call(app, "POST", "/api/assistant/cancel", {"call_id": preview["call_id"]}).status == 200
    worker.join(5)
    release.set()
    answer = box["r"].json()
    assert answer["outcome"] == "cancelled" and answer["content"] is None
    record = app.assistant.audit.call(preview["call_id"])
    assert record["outcome"] == "cancelled"
    # the feature is free again
    ft.on_post = None
    ok = call(app, "POST", "/api/assistant/send", {"call_id": second["call_id"], "payload_sha256": second["payload_sha256"]})
    assert ok.status == 200 and ok.json()["outcome"] == "accepted"


# ---------------------------------------------------------------------------
# The five features, on real results
# ---------------------------------------------------------------------------


def test_explain_accepted_is_ai_marked_and_recorded_in_the_run(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(EXPLAIN_OK))
    run_id = _compose_run(app)
    switch_on(app, "explain")
    _, answer = prepare_and_send(app, "explain", run_id=run_id)
    assert answer["outcome"] == "accepted" and answer["content"]["kind"] == "ai"
    reply = answer["content"]["reply"]
    assert reply["worst_thing"].startswith("Only 2 constants") and reply["terms"][0]["term"] == "placeholder"
    assert answer["grounding"]["ok"] is True
    assert answer["fallback"]["text"].startswith("VERDICT: STRUCTURAL"), "the engine's own text rides along"
    log = call(app, "GET", f"/api/assistant/log?run_id={run_id}").json()
    assert len(log["records"]) == 1 and "generated a plain-language explanation" in log["methods"][0]


def test_explain_rejected_is_not_shown_and_says_which_figure_failed(tmp_path):
    app, _ = _app(tmp_path, anthropic_reply(EXPLAIN_BAD))
    run_id = _compose_run(app)
    switch_on(app, "explain")
    _, answer = prepare_and_send(app, "explain", run_id=run_id)
    assert answer["outcome"] == "rejected" and answer["content"] is None
    assert answer["rejection"]["kind"] == "grounding"
    assert "wording was rejected because it contained a figure that is not in your results" in answer["rejection"]["message"]
    tokens = {f["token"] for f in answer["rejection"]["failures"]}
    assert "0.5 mM" in tokens or "0.5" in tokens
    assert any(f["kind"] == "significance" for f in answer["rejection"]["failures"])
    assert "0.5 mM" in answer["rejection"]["rejected_text"], "the rejected text is available in the disclosure"
    assert answer["fallback"]["text"].startswith("VERDICT: STRUCTURAL")
    record = app.assistant.audit.call(answer["call_id"])
    assert record["outcome"] == "rejected" and record["grounding"]["ok"] is False


def test_explain_works_on_a_refusal_with_no_result(tmp_path):
    reply = json.dumps({"summary": "Caterva did not build this: glycolysis is a named pathway, not a shape.",
                        "worst_thing": "It needs a pathway database such as KEGG or Reactome, which Caterva does not yet read.",
                        "next_step": "You can describe the steps you want, or supply SBML.", "terms": []})
    app, _ = _app(tmp_path, anthropic_reply(reply))
    run_id = install_run(app, "compose-glycolysis-refused")
    switch_on(app, "explain")
    _, answer = prepare_and_send(app, "explain", run_id=run_id)
    assert answer["outcome"] == "accepted", answer["rejection"]


def test_methods_polishes_the_engine_text_and_is_checked(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(METHODS_OK), anthropic_reply(json.dumps({"text": "The Km was 0.3 mM."})))
    run_id = _compose_run(app)
    switch_on(app, "methods")
    preview, answer = prepare_and_send(app, "methods", run_id=run_id)
    assert "engine_methods_text" in preview["payload"] and "BRENDA ref 286469" in preview["payload"]
    assert answer["outcome"] == "accepted" and "BRENDA ref 286469" in answer["content"]["reply"]["text"]
    assert answer["fallback"]["text"], "the engine's own methods text is the default"
    _, bad = prepare_and_send(app, "methods", run_id=run_id)
    assert bad["outcome"] == "rejected"


def test_ask_answers_from_the_result_refuses_before_sending_and_declines(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(ASK_OK), anthropic_reply(json.dumps({"answerable": False, "answer": ""})))
    run_id = _compose_run(app)
    switch_on(app, "ask")
    _, answer = prepare_and_send(app, "ask", run_id=run_id, question="Why is kcat a placeholder?")
    assert answer["outcome"] == "accepted" and "placeholder" in answer["content"]["reply"]["answer"]
    for question, needle in (("What is the Km of hexokinase?", "Constants"), ("What dose should I use?", "clinical"),
                             ("Delete this run", "can't run or change")):
        refused = call(app, "POST", "/api/assistant/prepare", {"feature": "ask", "run_id": run_id, "question": question})
        assert refused.status == 409 and needle in refused.json()["error"]["message"]
    assert len(ft.calls) == 1
    _, declined = prepare_and_send(app, "ask", run_id=run_id, question="What colour is the model?")
    assert declined["outcome"] == "declined" and "only answer about this run" in declined["content"]["text"]


def test_ask_keeps_no_history_beyond_the_run(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(ASK_OK), anthropic_reply(ASK_OK))
    run_id = _compose_run(app)
    switch_on(app, "ask")
    prepare_and_send(app, "ask", run_id=run_id, question="Why is kcat a placeholder?")
    prepare_and_send(app, "ask", run_id=run_id, question="Which row did the Km come from?")
    second = json.loads(ft.calls[1]["body"])["messages"][0]["content"]
    assert "Why is kcat a placeholder?" not in second, "each question is its own request: no chat history is sent"


def test_next_narrates_only_what_the_engine_ranked(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(NEXT_OK),
                   anthropic_reply(json.dumps({"narration": "Measure the pH optimum.", "order": ["ph_optimum"]})),
                   anthropic_reply(json.dumps({"narration": "Measure settling_time and then steady_state:reaction_S.",
                                               "order": ["steady_state:reaction_S", "settling_time"]})))
    run_id = _compose_run(app)
    switch_on(app, "next")
    preview, answer = prepare_and_send(app, "next", run_id=run_id)
    assert "ranked_experiments" in preview["payload"] and answer["outcome"] == "accepted"
    assert answer["content"]["reply"]["order"] == ["settling_time"]
    assert answer["fallback"]["text"].startswith("The engine's own ranking, best first:\n1. settling_time")
    _, invented = prepare_and_send(app, "next", run_id=run_id)
    assert invented["outcome"] == "rejected" and invented["rejection"]["kind"] == "unranked"
    assert "ph_optimum" in invented["rejection"]["detail"]
    _, fine = prepare_and_send(app, "next", run_id=run_id)
    assert fine["outcome"] == "accepted"


def test_next_needs_a_run_the_engine_ranked(tmp_path):
    app, _ = _app(tmp_path)
    run_id = install_run(app, "constants-hexokinase")
    switch_on(app, "next")
    refused = call(app, "POST", "/api/assistant/prepare", {"feature": "next", "run_id": run_id})
    assert refused.status == 409 and "no ranked measurements" in refused.json()["error"]["message"]


def test_describe_proposes_confirm_builds_the_engine_request_and_names_the_assistant(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(DESCRIBE_OK))
    switch_on(app, "describe")
    text = "pyruvate turned over by lactate dehydrogenase while gossypol competes for the site, in human"
    preview, answer = prepare_and_send(app, "describe", text=text)
    assert "shapes" in preview["payload"] and len(json.loads(json.loads(ft.last_body)["messages"][0]["content"].split("\n")[1])["data"]["shapes"]) == 36
    proposal = answer["content"]["proposal"]
    assert proposal["shape"] == "inhibition" and proposal["reading"] == "competitive inhibition"
    assert proposal["request"] == {"description": "Michaelis-Menten with a competitive inhibitor",
                                   "substrate": "pyruvate", "inhibitor": "gossypol", "organism": "human"}
    # nothing has run: the person has not clicked
    assert app.ws.run_ids() == []
    confirmed = call(app, "POST", "/api/assistant/confirm", {"call_id": answer["call_id"], "event": "confirm"}).json()
    assert confirmed["request"] == proposal["request"]
    prov = confirmed["provenance"]
    assert prov["kind"] == "chosen" and prov["by"] == "user" and prov["suggested_by"]["assistant"] == "claude-sonnet-5-5"
    assert "suggested by an assistant" in prov["reason"] and "confirmed by you" in prov["reason"]
    # the page then submits the ordinary run and attaches the call
    run = call(app, "POST", "/api/runs", {"kind": "compose", "request": {**confirmed["request"], "no_analysis": True}})
    assert run.status == 202
    run_id = run.json()["run"]["id"]
    assert call(app, "POST", "/api/assistant/attach", {"run_id": run_id, "call_ids": [answer["call_id"]]}).json()["attached"] == 2
    log = call(app, "GET", f"/api/assistant/log?run_id={run_id}").json()
    assert "suggested the mechanism description" in log["methods"][0] and "the person confirmed it" in log["methods"][0]
    assert call(app, "GET", "/api/assistant/runs").json()["run_ids"] == [run_id]


def test_describe_confirm_with_the_persons_edits_is_revalidated(tmp_path):
    app, _ = _app(tmp_path, anthropic_reply(DESCRIBE_OK))
    switch_on(app, "describe")
    _, answer = prepare_and_send(app, "describe", text="pyruvate and gossypol in human")
    ok = call(app, "POST", "/api/assistant/confirm", {"call_id": answer["call_id"], "event": "confirm",
                                                       "choices": {"variant": "uncompetitive"}})
    assert ok.status == 200 and ok.json()["request"]["description"].endswith("uncompetitive inhibitor")
    bad = call(app, "POST", "/api/assistant/confirm", {"call_id": answer["call_id"], "event": "confirm",
                                                        "choices": {"shape": "glycolysis"}})
    assert bad.status == 400


def test_a_rejected_proposal_cannot_be_confirmed(tmp_path):
    app, _ = _app(tmp_path, anthropic_reply(json.dumps({"shape": "glycolysis"})))
    switch_on(app, "describe")
    _, answer = prepare_and_send(app, "describe", text="glycolysis")
    assert answer["outcome"] == "rejected"
    assert call(app, "POST", "/api/assistant/confirm", {"call_id": answer["call_id"], "event": "confirm"}).status in (404, 409)


# ---------------------------------------------------------------------------
# The audit, the bundle, and the key
# ---------------------------------------------------------------------------


def test_the_audit_record_is_complete_and_travels_in_the_bundle(tmp_path):
    app, ft = _app(tmp_path, anthropic_reply(EXPLAIN_OK))
    run_id = _compose_run(app)
    switch_on(app, "explain")
    preview, answer = prepare_and_send(app, "explain", run_id=run_id)
    record = call(app, "GET", f"/api/assistant/log?run_id={run_id}").json()["records"][0]
    for field in ("id", "ts", "run_id", "feature", "provider", "model", "local", "destination", "payload", "payload_sha256",
                  "response", "grounding", "outcome", "latency_ms", "attempts", "usage", "include_data"):
        assert field in record, field
    assert record["provider"] == "anthropic" and record["model"] == "claude-sonnet-5-5" and record["feature"] == "explain"
    assert record["response"] == EXPLAIN_OK and record["grounding"]["ok"] and record["outcome"] == "accepted"
    assert record["ts"].endswith("Z") and record["usage"] == {"input_tokens": 100, "output_tokens": 50}
    bundle = call(app, "GET", f"/api/runs/{run_id}/bundle")
    names = zipfile.ZipFile(io.BytesIO(bundle.body)).namelist()
    assert "assistant.jsonl" in names and "assistant-methods.txt" in names
    assert json.loads(zipfile.ZipFile(io.BytesIO(bundle.body)).read("assistant.jsonl").decode().splitlines()[0])["id"] == record["id"]


def test_a_run_without_the_assistant_has_no_assistant_files(tmp_path):
    app, _ = _app(tmp_path)
    run_id = _compose_run(app)
    names = zipfile.ZipFile(io.BytesIO(call(app, "GET", f"/api/runs/{run_id}/bundle").body)).namelist()
    assert "assistant.jsonl" not in names and "assistant-methods.txt" not in names
    assert call(app, "GET", "/api/assistant/runs").json()["run_ids"] == []


def test_the_key_is_in_no_file_log_bundle_response_or_error_of_a_full_session(tmp_path, caplog):
    """A whole fake-transport session (every feature, an echoing auth failure, a rejection), then a search of everything."""
    caplog.set_level(logging.DEBUG)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.DEBUG)
    echoed = TransportResponse(403, json.dumps({"error": {"message": f"Invalid key: {TEST_KEY}"}}).encode())
    ft = FakeTransport(anthropic_reply(EXPLAIN_OK), anthropic_reply(METHODS_OK), anthropic_reply(ASK_OK),
                       anthropic_reply(NEXT_OK), anthropic_reply(DESCRIBE_OK), anthropic_reply(EXPLAIN_BAD), echoed,
                       anthropic_reply("ready"))
    app = make_app(tmp_path, ft)
    run_id = _compose_run(app)
    switch_on(app, "explain", "methods", "ask", "next", "describe")
    seen = []
    for feature, params in (("explain", {"run_id": run_id}), ("methods", {"run_id": run_id}),
                            ("ask", {"run_id": run_id, "question": "Why is kcat a placeholder?"}),
                            ("next", {"run_id": run_id}), ("describe", {"text": "pyruvate and gossypol in human"}),
                            ("explain", {"run_id": run_id}), ("explain", {"run_id": run_id}), ("test", {})):
        preview, answer = prepare_and_send(app, feature, **params)
        seen += [json.dumps(preview), json.dumps(answer)]
    seen.append(json.dumps(call(app, "GET", "/api/assistant/status").json()))
    seen.append(json.dumps(call(app, "GET", "/api/assistant/settings").json()))
    seen.append(json.dumps(call(app, "GET", f"/api/assistant/log?run_id={run_id}").json()))
    seen.append(json.dumps(call(app, "GET", "/api/assistant/log").json()))
    seen.append(call(app, "GET", f"/api/runs/{run_id}/bundle").body.decode("latin-1"))
    zipped = zipfile.ZipFile(io.BytesIO(call(app, "GET", f"/api/runs/{run_id}/bundle?diagnostics=true&redact_paths=false").body))
    seen += [zipped.read(n).decode("utf-8", "replace") for n in zipped.namelist()]
    on_disk = ""
    for path in Path(app.ws.root).rglob("*"):
        if path.is_file():
            on_disk += path.read_text(errors="replace") if path.suffix not in (".zip",) else ""
    logs = caplog.text + stream.getvalue()
    haystack = "\n".join(seen) + on_disk + logs
    assert TEST_KEY not in haystack
    assert TEST_KEY[:24] not in haystack
    assert len(ft.calls) == 8
    assert "kcat" in haystack     # the search covered real content
    logging.getLogger().removeHandler(handler)


def test_the_shells_control_line_sets_and_clears_the_key_and_is_not_logged(tmp_path, caplog):
    from caterva.studio.__main__ import watch_parent

    caplog.set_level(logging.DEBUG)
    app, _ = _app(tmp_path)
    r, w = os.pipe()
    stop = threading.Event()
    watch_parent(stop, stdin_fd=r, on_control=app.assistant.on_control, poll_s=60)
    os.write(w, b"noise that is not a control line\n")
    os.write(w, (json.dumps({"caterva_control": "assistant_key", "provider": "anthropic", "key": TEST_KEY}) + "\n").encode())
    deadline = time.time() + 5
    while time.time() < deadline and not app.assistant.keys.status("anthropic")["present"]:
        time.sleep(0.02)
    assert app.assistant.keys.status("anthropic") == {"present": True, "needed": True, "source": "keychain"}
    os.write(w, (json.dumps({"caterva_control": "assistant_key_clear", "provider": "anthropic"}) + "\n").encode())
    deadline = time.time() + 5
    while time.time() < deadline and app.assistant.keys.status("anthropic")["present"]:
        time.sleep(0.02)
    assert app.assistant.keys.status("anthropic")["present"] is False
    os.close(w)
    assert stop.wait(5), "closing the pipe still stops the studio"
    assert TEST_KEY not in caplog.text
    os.close(r)


def test_a_malformed_or_foreign_control_line_is_ignored(tmp_path):
    app, _ = _app(tmp_path)
    for message in ({"caterva_control": "assistant_key", "provider": "nobody", "key": TEST_KEY},
                    {"caterva_control": "assistant_key", "provider": "anthropic", "key": "short"},
                    {"caterva_control": "assistant_key", "provider": "local", "key": TEST_KEY},
                    {"caterva_control": "something_else"}, {"other": 1}):
        app.assistant.on_control(message)
    assert app.assistant.keys.status("anthropic")["present"] is False
    assert app.assistant.keys.status("local")["needed"] is False


def test_the_assistant_settings_file_holds_no_key_and_is_private(tmp_path):
    app, _ = _app(tmp_path)
    switch_on(app, "explain")
    path = app.ws.root / "assistant.json"
    assert path.is_file() and (path.stat().st_mode & 0o777) == 0o600
    assert TEST_KEY not in path.read_text()
    assert set(json.loads(path.read_text())) == {"enabled", "provider", "models", "model_lists", "local_url",
                                                 "local_only", "features", "max_calls_per_hour", "max_tokens", "consent"}


def test_a_corrupt_settings_file_leaves_the_assistant_off(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "assistant.json").write_text("{not json")
    app, _ = _app(tmp_path)
    s = call(app, "GET", "/api/assistant/status").json()
    assert s["state"] == "off" and "was not used" in s["note"]


def test_unknown_routes_and_methods_and_odd_bodies_are_refused_in_the_contracts_words(tmp_path):
    app, _ = _app(tmp_path)
    assert call(app, "GET", "/api/assistant/prepare").status == 405
    assert call(app, "POST", "/api/assistant/status", {}).status == 405
    assert call(app, "POST", "/api/assistant/prepare", {"feature": "nope"}).status == 400
    assert call(app, "POST", "/api/assistant/prepare", []).status == 400
    assert call(app, "GET", "/api/assistant/log?bogus=1").status == 400
    assert call(app, "POST", "/api/assistant/send", {"call_id": "a", "bogus": 1}).status == 400
