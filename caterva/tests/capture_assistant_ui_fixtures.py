"""Capture the assistant's UI fixtures from the running dispatch layer.

    cd <repository root> && PYTHONPATH=$PWD:$PWD/caterva/tests python caterva/tests/capture_assistant_ui_fixtures.py

Every file under Science-Agent-Pipeline/artifacts/caterva-studio/src/__fixtures__/api/assistant/ is what the studio
server answered to a real request through `App.dispatch`, for a REAL captured engine result (the run fixtures of
caterva/tests/fixtures/assistant/runs/). The model is a `FakeTransport` returning hand-written replies: that is a
mechanism stand-in, so these files show what the server does with a reply (accept it, reject it, fall back), never
what a real model would say. The replies are named in the file names. Nothing is edited by hand after capture.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "caterva" / "tests"))

OUT = REPO / "Science-Agent-Pipeline" / "artifacts" / "caterva-studio" / "src" / "__fixtures__" / "api" / "assistant"

from assistant_support import FakeTransport, TransportResponse, anthropic_reply, call, install_run, make_app, switch_on  # noqa: E402

EXPLAIN_OK = {"summary": "The verdict is structural, so this run supports questions about the mechanism only.",
              "worst_thing": "Only 2 constants are measured and 1 is still a placeholder.",
              "next_step": "Re-run with an organism that holds a measurement.",
              "terms": [{"term": "placeholder", "meaning": "a stand-in value nobody has measured here"}]}
EXPLAIN_BAD = {"summary": "The Km is 0.5 mM, significantly higher than the Ki.", "worst_thing": "Nothing.",
               "next_step": "Publish it.", "terms": []}
METHODS_OK = {"text": "The Km was 0.03 mM (BRENDA ref 286469) and the Ki was 0.0014 mM (BRENDA ref 711801), both measured; "
                      "kcat was a placeholder of 100 1/s."}
ASK_OK = {"answerable": True, "answer": "kcat is a placeholder: it has no value in the organism requested."}
NEXT_OK = {"narration": "The engine ranks settling_time first: it adds a new direction.", "order": ["settling_time"]}
DESCRIBE_OK = {"shape": "inhibition", "stages": None, "variant": "competitive", "substrate": "pyruvate",
               "inhibitor": "gossypol", "organism": "human", "subject_ec": None}
DESCRIBE_BAD = {"shape": "glycolysis"}
ASK_DECLINED = {"answerable": False, "answer": ""}


def write(name: str, body: Any, request: Dict[str, Any] | None = None, status: int = 200) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"request": request, "status": status, "body": body}, indent=1, ensure_ascii=False)
    (OUT / f"{name}.json").write_text(text + "\n", encoding="utf-8")
    print("wrote", name)


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="caterva-assistant-ui-"))
    ft = FakeTransport(*[anthropic_reply(json.dumps(r)) for r in (
        EXPLAIN_OK, EXPLAIN_BAD, METHODS_OK, ASK_OK, ASK_DECLINED, NEXT_OK, DESCRIBE_OK, DESCRIBE_BAD)] + [
        TransportResponse(503, b"{}"), TransportResponse(503, b"{}"), TransportResponse(503, b"{}"),
        anthropic_reply("ready")])
    app = make_app(work, ft)
    run_id = install_run(app, "compose-ldh-gossypol-analysed")
    write("status-off", call(app, "GET", "/api/assistant/status").json())
    write("settings-default", call(app, "GET", "/api/assistant/settings").json())
    switch_on(app, "explain")
    write("status-explain-only", call(app, "GET", "/api/assistant/status").json())
    switch_on(app, "explain", "methods", "ask", "next", "describe")
    write("status-ready", call(app, "GET", "/api/assistant/status").json())

    def exchange(name: str, feature: str, **params: Any) -> Dict[str, Any]:
        """The first use of a feature (consent asked, then given with the send), then the preview a later use gets."""
        req = {"feature": feature, **params}
        first = call(app, "POST", "/api/assistant/prepare", req).json()
        if first["consent_required"]:
            write(f"prepare-{name}-first-use", first, req)
        body = {"call_id": first["call_id"], "payload_sha256": first["payload_sha256"], "consent": True}
        ans = call(app, "POST", "/api/assistant/send", body)
        write(f"answer-{name}", ans.json(), body, ans.status)
        later = call(app, "POST", "/api/assistant/prepare", req).json()
        write(f"prepare-{name}", later, req)
        return ans.json()

    run = call(app, "GET", f"/api/runs/{run_id}").json()
    result = call(app, "GET", f"/api/runs/{run_id}/result").json()
    write("run-compose-analysed", {"run": run, "result": result})
    exchange("explain-accepted", "explain", run_id=run_id)
    exchange("explain-rejected", "explain", run_id=run_id)
    exchange("methods-accepted", "methods", run_id=run_id)
    exchange("ask-accepted", "ask", run_id=run_id, question="Why is kcat a placeholder?")
    exchange("ask-declined", "ask", run_id=run_id, question="What colour is the model?")
    exchange("next-accepted", "next", run_id=run_id)
    proposal = exchange("describe-accepted", "describe", text="pyruvate turned over by lactate dehydrogenase while "
                        "gossypol competes for the site, in human")
    confirm_body = {"call_id": proposal["call_id"], "event": "confirm"}
    write("confirm-describe", call(app, "POST", "/api/assistant/confirm", confirm_body).json(), confirm_body)
    exchange("describe-rejected", "describe", text="glycolysis")
    exchange("explain-provider-error", "explain", run_id=run_id)
    exchange("test-accepted", "test")
    write("log", call(app, "GET", "/api/assistant/log").json())
    refused = call(app, "POST", "/api/assistant/prepare", {"feature": "ask", "run_id": run_id,
                                                         "question": "What is the Km of hexokinase?"})
    write("prepare-ask-refused", refused.json(), {"feature": "ask", "question": "What is the Km of hexokinase?"}, refused.status)
    write("settings-on", call(app, "GET", "/api/assistant/settings").json())
    switch_on(app, "explain", provider="local", model="llama3")
    write("status-local", call(app, "GET", "/api/assistant/status").json())
    off = call(app, "PUT", "/api/assistant/settings", {"enabled": False})
    write("settings-off", off.json())
    app.close()


if __name__ == "__main__":
    main()
