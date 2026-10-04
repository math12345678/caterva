"""Shared helpers for the assistant's tests.

REAL results, FAKE transport
----------------------------
`install_run` puts one of the REAL captured run results
(caterva/tests/fixtures/assistant/runs/, produced by capture_assistant_fixtures.py
through the studio's own dispatch layer on recorded literature answers) into a
workspace, so every feature is tested against what the engine really answered.

`FakeTransport` stands in for the network. It is a MECHANISM test double: it
proves that the provider layer retries, builds bodies and headers, and that the
service gates, checks and records correctly. It says nothing about what a real
model would answer. The "model replies" tests hand it are hand-written strings,
labelled as test inputs where they appear.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from caterva.assistant.providers import AssistantError, TransportResponse

HERE = Path(__file__).resolve().parent
RUN_FIXTURES = HERE / "fixtures" / "assistant" / "runs"
PORT = 18775
TOKEN = "c" * 43
#: A key-shaped test secret. It appears in no fixture and must appear in no output.
TEST_KEY = "sk-ant-" "api03-TESTKEYdoNotUse01234" "56789abcdefghijklmnop"


def load_fixture(name: str) -> Dict[str, Any]:
    return json.loads((RUN_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def attacks() -> List[Dict[str, Any]]:
    """The injection corpus, each fragmented string joined (see the corpus file's _README for why it is fragmented)."""
    raw = json.loads((HERE / "fixtures" / "assistant" / "injection_corpus.json").read_text(encoding="utf-8"))
    out = []
    for entry in raw["attacks"]:
        joined = dict(entry)
        joined["payload"] = "".join(entry["payload"])
        joined["model_output"] = "".join(entry["model_output"]) if entry["model_output"] is not None else None
        out.append(joined)
    return out


def echoes() -> List[str]:
    """Replies that talk about the assistant's own instructions (from the corpus, joined)."""
    raw = json.loads((HERE / "fixtures" / "assistant" / "injection_corpus.json").read_text(encoding="utf-8"))
    return ["".join(parts) for parts in raw["echoes"]]


def anthropic_reply(text: str, *, input_tokens: int = 100, output_tokens: int = 50) -> TransportResponse:
    body = {"id": "msg_test", "type": "message", "role": "assistant", "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}}
    return TransportResponse(200, json.dumps(body).encode(), {})


def openai_reply(text: str) -> TransportResponse:
    body = {"choices": [{"message": {"role": "assistant", "content": text}}], "usage": {"total_tokens": 80}}
    return TransportResponse(200, json.dumps(body).encode(), {})


Scripted = Union[TransportResponse, Exception, Callable[["FakeTransport", Dict[str, Any]], TransportResponse]]


class FakeTransport:
    """Records every request and answers from a script (one entry per request; the last repeats)."""

    def __init__(self, *script: Scripted, wire: str = "anthropic") -> None:
        self.script: List[Scripted] = list(script)
        self.calls: List[Dict[str, Any]] = []
        self.wire = wire
        self.on_post: Optional[Callable[[], None]] = None

    def post(self, url: str, headers: Any, body: bytes, timeout: float) -> TransportResponse:
        call = {"url": url, "headers": dict(headers), "body": body, "timeout": timeout}
        self.calls.append(call)
        if self.on_post:
            self.on_post()
        item = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(self, call)
        return item

    @property
    def last_body(self) -> bytes:
        return self.calls[-1]["body"]


def make_app(tmp_path: Path, transport: Optional[Any] = None, *, environ: Optional[Dict[str, str]] = None,
             offline: bool = False, **service_options: Any):
    """An App on a temporary workspace whose assistant sends through `transport` (or fails if it is touched)."""
    from caterva.studio.adapters import load_registry
    from caterva.studio.dispatch import App
    from caterva.studio.static_files import StaticSite
    from caterva.studio.workspace import Workspace

    def factory() -> Any:
        if transport is None:
            raise AssertionError("a transport was created, but this test says no network may be touched")
        return transport

    options = {"transport_factory": factory, "environ": environ if environ is not None else {},
               "sleep": lambda s: None, **service_options}
    app = App(workspace=Workspace(tmp_path / "data"), port=PORT, token=TOKEN, static_site=StaticSite(tmp_path / "nobuild"),
              registry=load_registry(), assistant_options=options,
              capability_options=dict(head=lambda h, t: None, which=lambda n: None, is_executable=lambda p: False))
    app.start(apply_environment=False)
    if offline:
        app._settings["offline"] = True
    return app


def call(app: Any, method: str, target: str, body: Any = None):
    from caterva.studio.contract import SESSION_HEADER
    from caterva.studio.dispatch import Request

    headers = [("Host", f"127.0.0.1:{PORT}"), (SESSION_HEADER, TOKEN)]
    raw = None
    if body is not None:
        raw = json.dumps(body).encode()
        headers += [("Content-Type", "application/json"), ("Content-Length", str(len(raw)))]
    return app.dispatch(Request(method, target, headers, raw))


def install_run(app: Any, name: str, mutate: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None) -> str:
    """Write a captured real run into the app's workspace; returns its run id.

    `mutate(record, result)` may alter the copies before they are written: the injection tests use it to plant
    hostile text in a field of a REAL result (a BRENDA row's commentary, a title) and nothing else."""
    data = json.loads(json.dumps(load_fixture(name)))
    if mutate:
        mutate(data["run"], data["result"])
    record = dict(data["run"])
    app.ws.create_run(record, record["request"], owner=None)
    if data.get("result") is not None:
        app.ws.write_result(record["id"], data["result"])
    for artifact_name, text in (data.get("artifact_files") or {}).items():
        app.ws.write_artifact(record["id"], artifact_name, text.encode("utf-8"))
    app.ws.write_record(record)
    return record["id"]


def switch_on(app: Any, *features: str, provider: str = "anthropic", model: Optional[str] = None,
              key: Optional[str] = TEST_KEY, **settings: Any) -> None:
    """The person's steps in Settings: assistant on, features on, key set."""
    body: Dict[str, Any] = {"enabled": True, "provider": provider,
                            "features": {f: True for f in features}, **settings}
    if model:
        body["models"] = {provider: model}
    response = call(app, "PUT", "/api/assistant/settings", body)
    assert response.status == 200, response.json()
    if key and provider != "local":
        assert app.assistant.set_key(provider, key)


def prepare_and_send(app: Any, feature: str, *, consent: bool = True, **params: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(preview, answer) through the HTTP layer, as the page does it."""
    prep = call(app, "POST", "/api/assistant/prepare", {"feature": feature, **params})
    assert prep.status == 200, prep.json()
    preview = prep.json()
    sent = call(app, "POST", "/api/assistant/send", {"call_id": preview["call_id"],
                                                     "payload_sha256": preview["payload_sha256"], "consent": consent})
    assert sent.status == 200, sent.json()
    return preview, sent.json()


__all__ = ["AssistantError", "FakeTransport", "TEST_KEY", "anthropic_reply", "call", "install_run", "attacks", "echoes", "load_fixture",
           "make_app", "openai_reply", "prepare_and_send", "switch_on"]
