"""The assistant service: the one place a model call is decided, made, checked and recorded.

THE LIFE OF A CALL
------------------
 1. `prepare` builds the whole request (the redacted payload) and returns it
    to the page as the PREVIEW. Nothing has been sent.
 2. `send` sends exactly those bytes, only if: the assistant and the feature
    are on, a key (or a local model) is set, offline mode allows it, the
    person has agreed to what this feature sends (first use) and the page
    echoes the preview's hash (it displayed what will be sent), and the spend
    guard has room. One request at a time per feature; cancel works.
 3. The reply is parsed against a strict schema, then checked: an intent
    against the engine's own grammar, a choice against the candidates the
    engine produced, wording against the run's own result
    (`grounding.check`). Anything that fails is NOT shown as the
    assistant's wording; the page falls back to the engine's text and says why.
 4. The call is recorded (`audit.py`): payload, response, grounding result,
    outcome. A person's confirmation is a second record.

WHAT THE MODEL CAN CAUSE
------------------------
It can return a schema-valid object or text. It cannot call anything, run
anything or write anything; this module does, after a click. A confirmed
proposal becomes an ordinary engine request the PAGE submits through the
ordinary runs route, and its values are recorded as chosen by the person with
the assistant named as the source of the suggestion.

DISABLED MEANS DISABLED
-----------------------
With the assistant off (the default) `prepare` and `send` raise before any
payload is built or any transport is created; `transport_factory` is never
called. A test holds that to account with a factory that fails if touched.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets as _secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from caterva.assistant import digest as digestmod
from caterva.assistant import grounding, intents, policy, prompts
from caterva.assistant.audit import AuditLog, methods_sentences
from caterva.assistant.config import ConfigError, ConfigStore, KeyStore
from caterva.assistant.providers import (
    PROVIDERS, AssistantError, HttpxTransport, Provider, Transport, build_request,
)
from caterva.assistant.redact import redact_text, scrub

log = logging.getLogger("caterva.assistant")

CONSENT_KEYS = prompts.FEATURES + ("test",)
PREPARED_TTL_S = 15 * 60
MAX_PREPARED = 50
MAX_DESCRIBE_CHARS = 600
FIXED_TEST_PROMPT = "Reply with the single word: ready"
TEST_SYSTEM = "You are a connectivity check inside a desktop app. Reply with the single word the user asks for."

FEATURE_LABELS = {
    "describe": "Describe it (Compose)",
    "explain": "Explain this result",
    "methods": "Draft my methods",
    "ask": "Ask this run",
    "next": "What should I measure next",
    "test": "Test the connection",
}
#: What each feature sends, in the words the consent panel shows.
FEATURE_SENDS = {
    "describe": "The sentence you typed, the list of mechanism shapes Caterva can build, and enzyme names the "
                "finder matched.",
    "explain": "The run's result (its figures, units, verdict, concerns, and where each figure came from).",
    "methods": "The run's result and Caterva's own methods text for it.",
    "ask": "Your question and the run's result.",
    "next": "The run's ranked next measurements, with their figures.",
    "test": "One fixed line of text: nothing from your work.",
}


class _SecretFilter(logging.Filter):
    """Removes key shapes and held secrets from every record the assistant logs."""

    def __init__(self, secrets: Callable[[], Sequence[str]]) -> None:
        super().__init__()
        self._secrets = secrets

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001
            message = str(record.msg)
        record.msg = scrub(message, self._secrets())
        record.args = None
        if record.exc_info:
            record.exc_text = scrub("".join(logging.Formatter().formatException(record.exc_info)), self._secrets())
            record.exc_info = None
        return True


class SpendGuard:
    """A hard stop on provider requests per hour (retries count: each is a request that costs)."""

    def __init__(self, limit: Callable[[], int], clock: Callable[[], float] = time.time) -> None:
        self._limit = limit
        self._clock = clock
        self._times: List[float] = []
        self._lock = threading.Lock()

    def _trim(self) -> None:
        cutoff = self._clock() - 3600
        self._times = [t for t in self._times if t > cutoff]

    def remaining(self) -> int:
        with self._lock:
            self._trim()
            return max(0, self._limit() - len(self._times))

    def take(self) -> None:
        with self._lock:
            self._trim()
            if len(self._times) >= self._limit():
                oldest = min(self._times) if self._times else self._clock()
                wait = max(1, int(oldest + 3600 - self._clock()))
                raise AssistantError("spend", f"the limit of {self._limit()} assistant requests per hour is reached; "
                                              f"it frees up in about {max(1, wait // 60)} minute(s). Raise it in "
                                              "Settings if you want.", status=429, retry_after_s=wait)
            self._times.append(self._clock())


@dataclass
class Prepared:
    id: str
    feature: str
    run_id: Optional[str]
    request: Any                    # BuiltRequest
    sha256: str
    source: Any                     # what grounding checks wording against
    ctx: Dict[str, Any]
    fingerprint: str
    created: float
    include_data: bool
    fallback: Dict[str, Any]
    local: bool
    cancel: threading.Event = field(default_factory=threading.Event)
    state: str = "prepared"         # prepared | sending | done


class AssistantService:
    def __init__(self, *, workspace: Any, offline: Callable[[], bool] = lambda: False,
                 transport_factory: Callable[[], Transport] = HttpxTransport,
                 environ: Optional[Mapping[str, str]] = None, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep, timeout_s: float = 45.0) -> None:
        self.ws = workspace
        self.offline = offline
        self.transport_factory = transport_factory
        self.clock = clock
        self.sleep = sleep
        self.timeout_s = timeout_s
        self.config = ConfigStore(workspace.root)
        self.keys = KeyStore(environ)
        self.audit = AuditLog(workspace.root, workspace.run_dir, self.keys.secrets)
        self.spend = SpendGuard(lambda: self.config.get()["max_calls_per_hour"], clock)
        self._prepared: Dict[str, Prepared] = {}
        self._proposals: Dict[str, Dict[str, Any]] = {}
        self._busy: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._filter = _SecretFilter(self.keys.secrets)
        log.addFilter(self._filter)
        for name in ("caterva.studio.dispatch", "caterva.studio.jobs"):
            logging.getLogger(name).addFilter(self._filter)

    # -- keys, from the shell's control channel -----------------------------------

    def set_key(self, provider: str, key: str) -> bool:
        try:
            self.keys.set(provider, key)
        except ValueError:
            return False
        return True

    def clear_key(self, provider: Optional[str] = None) -> None:
        self.keys.clear(provider)

    def on_control(self, message: Mapping[str, Any]) -> bool:
        """One control message from the shell (never logged). True when it was an assistant message."""
        kind = message.get("caterva_control")
        if kind == "assistant_key" and isinstance(message.get("provider"), str) and isinstance(message.get("key"), str):
            self.set_key(message["provider"], message["key"])
            return True
        if kind == "assistant_key_clear":
            self.clear_key(message.get("provider") if isinstance(message.get("provider"), str) else None)
            return True
        return False

    # -- status ------------------------------------------------------------------

    def _destination(self, settings: Mapping[str, Any]) -> Dict[str, Any]:
        spec = PROVIDERS[settings["provider"]]
        host = "this computer" if spec.local else spec.base_url.split("/")[2]
        return {"host": host, "local": spec.local, "label": spec.label}

    def status(self) -> Dict[str, Any]:
        s = self.config.get()
        provider = s["provider"]
        dest = self._destination(s)
        key = self.keys.status(provider)
        model = (s["models"].get(provider) or "").strip()
        on = bool(s["enabled"])
        any_feature = any(s["features"].values())
        if not on:
            state, indicator = "off", "Assistant off"
        elif self.offline() and not dest["local"]:
            state, indicator = "blocked", "Assistant paused: offline mode is on"
        elif key["needed"] and not key["present"]:
            state, indicator = "needs_key", "Assistant on, no key set"
        elif not model:
            state, indicator = "needs_model", "Assistant on, no model chosen"
        elif not any_feature:
            state, indicator = "idle", "Assistant on, no feature switched on"
        else:
            state = "ready"
            indicator = ("Assistant active: local model, nothing leaves this computer" if dest["local"]
                         else f"Assistant active: sends to {dest['host']}")
        return {
            "state": state, "indicator": indicator, "leaves_machine": on and not dest["local"],
            "destination": dest, "provider": provider, "model": model,
            "providers": [{"name": p.name, "label": p.label, "local": p.local, "needs_key": p.needs_key}
                          for p in PROVIDERS.values()],
            "key": {**key, "provider": provider,
                    "note": ("The key is read from the CATERVA_ASSISTANT_KEY environment variable (a browser or "
                             "development run); the Caterva app keeps it in the macOS Keychain."
                             if key.get("source") == "environment" else None)},
            "features": {f: {"label": FEATURE_LABELS[f], "on": bool(s["features"].get(f)),
                             "sends": FEATURE_SENDS[f], "consented_at": self.config.consented(f)}
                         for f in CONSENT_KEYS if f != "test"},
            "spend": {"remaining": self.spend.remaining(), "max_calls_per_hour": s["max_calls_per_hour"],
                      "max_tokens": s["max_tokens"]},
            "note": self.config.note,
        }

    def settings(self) -> Dict[str, Any]:
        return {**self.config.get(), "consent": self.config.consent()}

    def put_settings(self, body: Any) -> Dict[str, Any]:
        self.config.update(body)
        return self.settings()

    # -- the gates --------------------------------------------------------------------

    def _gate(self, feature: str) -> Dict[str, Any]:
        s = self.config.get()
        if not s["enabled"]:
            raise AssistantError("off", "The assistant is off. Switch it on in Settings to use it.", status=409)
        if feature != "test" and not s["features"].get(feature):
            raise AssistantError("off", f"{FEATURE_LABELS[feature]} is switched off in Settings.", status=409)
        provider = s["provider"]
        spec = PROVIDERS[provider]
        if s["local_only"] and not spec.local:
            raise AssistantError("off", "Local only is on, and the chosen provider is not on this computer.", status=409)
        if self.offline() and not spec.local:
            raise AssistantError("offline", "Offline mode is on, so nothing can be sent to a provider. A model on "
                                            "this computer still works.", status=409)
        if spec.needs_key and not self.keys.get(provider):
            raise AssistantError("no_key", "No key is set for this provider (Settings, Assistant).", status=409)
        if not (s["models"].get(provider) or "").strip():
            raise AssistantError("no_model", "Choose a model name in Settings first.", status=409)
        return s

    @staticmethod
    def _fingerprint(s: Mapping[str, Any]) -> str:
        return hashlib.sha256(json.dumps([s["provider"], s["models"].get(s["provider"]), s["local_url"],
                                          s["max_tokens"], s["local_only"]]).encode()).hexdigest()[:16]

    # -- reading a run -------------------------------------------------------------------

    def _run(self, run_id: Any) -> Tuple[Dict[str, Any], Any]:
        if not isinstance(run_id, str):
            raise AssistantError("malformed", "run_id must be a run id", status=400)
        try:
            record = self.ws.record_or_unreadable(run_id)
        except Exception:  # noqa: BLE001 - RunNotFound and unreadable runs alike
            raise AssistantError("not_found", "there is no run with that id", status=404) from None
        if record.get("status") not in ("done", "failed", "cancelled", "abandoned", "interrupted"):
            raise AssistantError("conflict", "the run is not finished yet", status=409)
        result = None
        try:
            result = json.loads(self.ws.result_path(run_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            result = None
        return record, result

    def _engine_methods(self, run_id: str, record: Mapping[str, Any]) -> Optional[str]:
        for a in record.get("artifacts") or []:
            if isinstance(a, dict) and a.get("name") == "methods.md":
                try:
                    return self.ws.artifact_path(run_id, "methods.md").read_text(encoding="utf-8")[:3000]
                except (OSError, ValueError):
                    return None
        return None

    # -- prepare ----------------------------------------------------------------------------

    def prepare(self, body: Any) -> Dict[str, Any]:
        if not isinstance(body, dict):
            raise AssistantError("malformed", "the body must be an object", status=400)
        unknown = sorted(set(body) - {"feature", "run_id", "text", "question", "include_data"})
        if unknown:
            raise AssistantError("malformed", f"{unknown[0]!r} is not part of a prepare request", status=400)
        feature = body.get("feature")
        if feature not in CONSENT_KEYS:
            raise AssistantError("malformed", f"feature must be one of {', '.join(CONSENT_KEYS)}", status=400)
        include = body.get("include_data", False)
        if not isinstance(include, bool):
            raise AssistantError("malformed", "include_data must be true or false", status=400)
        s = self._gate(feature)                     # nothing below runs when the assistant is off
        provider = s["provider"]
        run_id = body.get("run_id") if feature != "describe" and feature != "test" else None
        redaction = {"data_dir": str(self.ws.root), "secrets": self.keys.secrets()}
        ctx: Dict[str, Any] = {}
        fallback: Dict[str, Any] = {}

        if feature == "test":
            system, user, source = TEST_SYSTEM, FIXED_TEST_PROMPT, {}
        elif feature == "describe":
            text = body.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > MAX_DESCRIBE_CHARS:
                raise AssistantError("malformed", f"text must be your description, up to {MAX_DESCRIBE_CHARS} "
                                                  "characters", status=400)
            candidates = self._enzyme_candidates(text)
            data = {"user_description": text.strip(),
                    "shapes": [{"name": sh.name, "describes": sh.describes, "needs_stages": sh.needs_stages,
                                "variants": list(sh.variants)} for sh in intents.shape_catalogue()],
                    "max_stages": intents.max_stages(), "enzyme_candidates": candidates}
            system, user = prompts.system_prompt("describe"), prompts.render_user_message("describe", data, **redaction)
            source = data
            ctx = {"user_text": text.strip(), "ec": {c["ec"] for c in candidates}, "candidates": candidates}
        else:
            record, result = self._run(run_id)
            kind = record.get("kind")
            dg = digestmod.digest(kind, result, record, include_input=include)
            fallback_text = digestmod.engine_text(kind, result, record)
            data = {"run": dg}
            if feature == "explain":
                fallback = {"text": fallback_text}
            elif feature == "methods":
                engine = self._engine_methods(run_id, record)
                if engine:
                    data["engine_methods_text"] = engine
                fallback = {"text": engine or fallback_text}
            elif feature == "ask":
                question = body.get("question")
                refusal = policy.screen_question(question if isinstance(question, str) else "")
                if refusal:
                    raise AssistantError("refused_" + refusal.code, refusal.message, status=409)
                data["question"] = question.strip()
                near = digestmod.nearest_facts(dg, question)
                fallback = {"text": "The assistant is not answering this one. The closest facts in this run's own "
                                    "record:\n" + ("\n".join(f"- {n}" for n in near) if near else "none found")}
            elif feature == "next":
                ranked = digestmod.ranked_experiments(result)
                if not ranked:
                    raise AssistantError("not_applicable", "This run has no ranked measurements. Run Compose with "
                                                           "the design analysis on to get them.", status=409)
                data["ranked_experiments"] = [{k: v for k, v in r.items()} for r in ranked[:6]]
                dg = {**dg, "ranked_experiments": data["ranked_experiments"]}
                data["run"] = dg
                ctx = {"ranked_keys": [r["key"] for r in ranked[:6]]}
                fallback = {"text": self._next_fallback(ranked[:6])}
            system, user = prompts.system_prompt(feature), prompts.render_user_message(feature, data, **redaction)
            source = data
            ctx["question"] = data.get("question")

        built = build_request(provider, s["models"][provider], system, user, max_tokens=s["max_tokens"],
                              local_url=s["local_url"] if PROVIDERS[provider].local else None)
        prep = Prepared(id=_secrets.token_hex(8), feature=feature, run_id=run_id, request=built,
                        sha256=hashlib.sha256(built.body).hexdigest(), source=source, ctx=ctx,
                        fingerprint=self._fingerprint(s), created=self.clock(), include_data=include,
                        fallback=fallback, local=PROVIDERS[provider].local)
        with self._lock:
            self._expire()
            self._prepared[prep.id] = prep
        return {
            "call_id": prep.id, "feature": feature, "provider": provider, "model": built.model,
            "destination": self._destination(s), "leaves_machine": not prep.local, "url": built.url,
            "payload": built.body.decode("utf-8"), "payload_sha256": prep.sha256, "bytes": len(built.body),
            "consent_required": self.config.consented(feature) is None, "include_data": include,
            "sends": FEATURE_SENDS[feature], "spend": {"remaining": self.spend.remaining()},
            "fallback": fallback,
        }

    @staticmethod
    def _next_fallback(ranked: Sequence[Mapping[str, Any]]) -> str:
        lines = []
        for i, r in enumerate(ranked, 1):
            nov = r.get("novelty")
            tail = (f"novelty {nov:.3g}, " if isinstance(nov, (int, float)) else "") + \
                   ("adds a new direction" if r.get("informative") else "adds nothing the measurements already taken do not show")
            lines.append(f"{i}. {r['key']}: {r.get('description') or ''} ({tail})".replace(" ()", ""))
        return "The engine's own ranking, best first:\n" + "\n".join(lines)

    def _enzyme_candidates(self, text: str) -> List[Dict[str, str]]:
        try:
            from caterva.studio.adapters.enzymes import find_base

            answer = find_base(text.strip()[:200], None, 5)
        except Exception:  # noqa: BLE001 - the finder is a convenience; no candidates means no EC may be proposed
            return []
        out = []
        for c in answer.get("candidates") or []:
            if isinstance(c, dict) and isinstance(c.get("ec"), str) and isinstance(c.get("name"), str):
                out.append({"ec": c["ec"], "name": c["name"]})
        return out[:5]

    def _expire(self) -> None:
        now = self.clock()
        for key in [k for k, p in self._prepared.items() if now - p.created > PREPARED_TTL_S and p.state != "sending"]:
            self._prepared.pop(key, None)
        while len(self._prepared) > MAX_PREPARED:
            self._prepared.pop(next(iter(self._prepared)))

    # -- send --------------------------------------------------------------------------------------

    def cancel(self, call_id: Any) -> Dict[str, Any]:
        prep = self._prepared.get(call_id) if isinstance(call_id, str) else None
        if prep is None:
            raise AssistantError("not_found", "there is no such call to cancel", status=404)
        prep.cancel.set()
        return {"call_id": prep.id, "cancelled": True}

    def send(self, body: Any) -> Dict[str, Any]:
        if not isinstance(body, dict) or set(body) - {"call_id", "payload_sha256", "consent"}:
            raise AssistantError("malformed", "send takes {call_id, payload_sha256, consent?}", status=400)
        prep = self._prepared.get(body.get("call_id")) if isinstance(body.get("call_id"), str) else None
        if prep is None or prep.state != "prepared":
            raise AssistantError("not_found", "that call is not waiting to be sent; prepare it again", status=404)
        s = self._gate(prep.feature)
        if self._fingerprint(s) != prep.fingerprint:
            raise AssistantError("conflict", "the provider, model or limits changed after the preview; prepare again",
                                 status=409)
        if body.get("payload_sha256") != prep.sha256:
            raise AssistantError("conflict", "the payload you were shown is not the one prepared; prepare again",
                                 status=409)
        if self.config.consented(prep.feature) is None:
            if body.get("consent") is not True:
                raise AssistantError("consent", f"Before the first {FEATURE_LABELS[prep.feature].lower()}, confirm what "
                                                "will be sent.", status=409)
            self.config.grant(prep.feature)
        with self._lock:
            if prep.feature in self._busy:
                raise AssistantError("busy", "this feature already has a request in flight", status=409)
            self._busy[prep.feature] = prep.id
            prep.state = "sending"
        started = self.clock()
        try:
            return self._execute(prep, s, started)
        finally:
            with self._lock:
                self._busy.pop(prep.feature, None)
                prep.state = "done"
                self._prepared.pop(prep.id, None)

    def _provider(self, s: Mapping[str, Any]) -> Provider:
        provider = s["provider"]
        return Provider(provider, s["models"][provider], transport=self.transport_factory(),
                        key=self.keys.get(provider), local_url=s["local_url"] if PROVIDERS[provider].local else None,
                        timeout_s=self.timeout_s, sleep=self.sleep, count_attempt=self.spend.take)

    def _execute(self, prep: Prepared, s: Mapping[str, Any], started: float) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "id": prep.id, "event": "call", "ts": _iso(self.clock()), "run_id": prep.run_id, "feature": prep.feature,
            "provider": s["provider"], "model": prep.request.model, "local": prep.local,
            "destination": prep.request.host, "include_data": prep.include_data, "payload": prep.request.body.decode("utf-8"),
            "payload_sha256": prep.sha256, "response": None, "grounding": None, "outcome": "error", "reason": None,
            "latency_ms": None, "attempts": 0, "usage": {},
        }
        box: Dict[str, Any] = {}

        def work() -> None:
            try:
                box["ok"] = self._provider(s).send(prep.request, cancelled=prep.cancel.is_set)
            except AssistantError as exc:
                box["err"] = exc
            except BaseException as exc:  # noqa: BLE001
                box["err"] = AssistantError("crash", f"the assistant failed: {type(exc).__name__}")

        thread = threading.Thread(target=work, name="caterva-assistant-call", daemon=True)
        thread.start()
        while thread.is_alive():
            thread.join(0.05)
            if prep.cancel.is_set() and thread.is_alive():
                record.update(outcome="cancelled", reason="the person cancelled", latency_ms=self._ms(started))
                self.audit.record(record)
                return self._answer(record, prep, error={"code": "cancelled", "message": "Cancelled."})
        record["latency_ms"] = self._ms(started)
        if "err" in box:
            exc: AssistantError = box["err"]
            code = "cancelled" if exc.code == "cancelled" else "error"
            record.update(outcome="cancelled" if code == "cancelled" else "error",
                          reason=scrub(f"{exc.code}: {exc.message}", self.keys.secrets()))
            self.audit.record(record)
            return self._answer(record, prep, error={"code": exc.code, "message": scrub(exc.message, self.keys.secrets()),
                                                     "retry_after_s": exc.retry_after_s})
        text, usage, attempts = box["ok"]
        record.update(response=scrub(text, self.keys.secrets()), usage=usage, attempts=attempts)
        return self._judge(record, prep, text)

    def _ms(self, started: float) -> int:
        return max(0, int((self.clock() - started) * 1000))

    def _judge(self, record: Dict[str, Any], prep: Prepared, text: str) -> Dict[str, Any]:
        feature = prep.feature
        if feature == "test":
            ok = "ready" in text.lower()
            record.update(outcome="accepted" if ok else "rejected", reason=None if ok else "unexpected reply")
            self.audit.record(record)
            return self._answer(record, prep, content={"reply": scrub(text.strip(), self.keys.secrets())[:80]})
        try:
            reply = prompts.parse_reply(feature, text)
        except prompts.ReplyRejected as exc:
            record.update(outcome="rejected", reason=f"schema: {exc}")
            self.audit.record(record)
            return self._answer(record, prep, rejection={"kind": "schema", "message":
                                "The assistant's reply was not in the form Caterva accepts, so it was discarded.",
                                "detail": str(exc), "rejected_text": scrub(text, self.keys.secrets())[:2000]})
        if feature == "describe":
            try:
                intent = intents.validate_describe(reply, prep.ctx["user_text"], prep.ctx["ec"])
            except intents.IntentRejected as exc:
                record.update(outcome="rejected", reason="intent: " + "; ".join(exc.reasons))
                self.audit.record(record)
                return self._answer(record, prep, rejection={"kind": "intent", "message":
                                    "The assistant's proposal was rejected by the engine's own rules.",
                                    "detail": "; ".join(exc.reasons), "reasons": exc.reasons,
                                    "rejected_text": scrub(text, self.keys.secrets())[:2000]})
            record.update(outcome="accepted", reason=None, proposal={"suggested": intent.suggested,
                                                                    "request": intent.request, "reading": intent.reading})
            self.audit.record(record)
            with self._lock:
                self._proposals[prep.id] = {"user_text": prep.ctx["user_text"], "ec": prep.ctx["ec"],
                                            "intent": intent, "provider": record["provider"], "model": record["model"],
                                            "created": self.clock()}
            return self._answer(record, prep, content={"proposal": {
                "shape": intent.shape, "description": intent.description, "request": intent.request,
                "reading": intent.reading, "organism_note": intent.organism_note, "stages": intent.stages,
                "variant": intent.variant, "suggested": intent.suggested,
                "enzyme_candidates": prep.ctx["candidates"],
                "variants": list(next(sh.variants for sh in intents.shape_catalogue() if sh.name == intent.shape)),
                "needs_stages": intent.stages is not None, "max_stages": intents.max_stages()}})
        if feature == "ask" and not reply["answerable"]:
            record.update(outcome="declined", reason="the model said the run does not contain the answer")
            self.audit.record(record)
            return self._answer(record, prep, content={"declined": True, "text":
                                "I can only answer about this run, and this run's result does not contain that."})
        if feature == "next":
            unranked = [k for k in reply["order"] if k not in prep.ctx["ranked_keys"]]
            if unranked:
                record.update(outcome="rejected", reason=f"chose a measurement the engine did not rank: {unranked}")
                self.audit.record(record)
                return self._answer(record, prep, rejection={"kind": "unranked", "message":
                                    "The assistant named a measurement the engine did not rank, so its wording was "
                                    "rejected.", "detail": ", ".join(unranked),
                                    "rejected_text": scrub(text, self.keys.secrets())[:2000]})
        failures: List[grounding.Failure] = []
        checked: Dict[str, int] = {}
        index = grounding.SourceIndex(prep.source)
        for label, prose, lenient in prompts.grounded_parts(feature, reply):
            result = grounding.check(prose, index, allow_derived=lenient)
            failures += [grounding.Failure(f.kind, f.token, f"{label}: {f.reason}", f.start, f.end) for f in result.failures]
            for k, v in result.checked.items():
                checked[k] = checked.get(k, 0) + v
        verdict = grounding.GroundingResult(ok=not failures, failures=failures, checked=checked)
        record["grounding"] = verdict.as_dict()
        if not verdict.ok:
            record.update(outcome="rejected", reason="grounding: " + verdict.summary())
            self.audit.record(record)
            return self._answer(record, prep, rejection={
                "kind": "grounding", "message": grounding.reject_message(verdict), "detail": verdict.summary(),
                "failures": [f.as_dict() for f in failures], "rejected_text": scrub(text, self.keys.secrets())[:2000]})
        record.update(outcome="accepted", reason=None)
        self.audit.record(record)
        return self._answer(record, prep, content={"reply": reply, "kind": "ai"})

    def _answer(self, record: Mapping[str, Any], prep: Prepared, *, content: Optional[Dict[str, Any]] = None,
                rejection: Optional[Dict[str, Any]] = None, error: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"call_id": prep.id, "feature": prep.feature, "outcome": record["outcome"], "provider": record["provider"],
                "model": record["model"], "local": record["local"], "latency_ms": record["latency_ms"],
                "content": content, "rejection": rejection, "error": error, "fallback": prep.fallback,
                "grounding": record.get("grounding"), "run_id": prep.run_id}

    # -- confirmation ------------------------------------------------------------------------------

    def confirm(self, body: Any) -> Dict[str, Any]:
        if not isinstance(body, dict) or set(body) - {"call_id", "event", "choices"}:
            raise AssistantError("malformed", "confirm takes {call_id, event, choices?}", status=400)
        call_id = body.get("call_id")
        call = self.audit.call(call_id) if isinstance(call_id, str) else None
        if call is None:
            raise AssistantError("not_found", "there is no such call", status=404)
        event = body.get("event", "confirm")
        if call["feature"] == "describe":
            if event != "confirm":
                raise AssistantError("malformed", "a proposal is confirmed with event: confirm", status=400)
            proposal = self._proposals.get(call_id)
            if proposal is None or call.get("outcome") != "accepted":
                raise AssistantError("conflict", "this proposal can no longer be confirmed; ask again", status=409)
            intent = proposal["intent"]
            choices = body.get("choices")
            suggested = intent.suggested
            if choices is not None:
                if not isinstance(choices, dict):
                    raise AssistantError("malformed", "choices must be an object", status=400)
                merged = {"shape": intent.shape, "stages": intent.stages, "variant": intent.variant,
                          "substrate": intent.request.get("substrate"), "inhibitor": intent.request.get("inhibitor"),
                          "organism": intent.request.get("organism"), "subject_ec": intent.request.get("subject"),
                          **choices}
                typed = " ".join(str(v) for v in choices.values() if isinstance(v, str))
                try:
                    intent = intents.validate_describe(merged, proposal["user_text"] + " " + typed, proposal["ec"])
                except intents.IntentRejected as exc:
                    raise AssistantError("malformed", "; ".join(exc.reasons), status=400) from None
            provenance = {"kind": "chosen", "by": "user",
                          "reason": f"suggested by an assistant ({proposal['model']}, {proposal['provider']}) and "
                                    "confirmed by you",
                          "suggested_by": {"assistant": proposal["model"], "provider": proposal["provider"],
                                           "call_id": call_id}}
            self.audit.record({"id": _secrets.token_hex(8), "event": "confirm", "call_id": call_id, "ts": _iso(self.clock()),
                               "run_id": call.get("run_id"), "suggested": suggested, "final": intent.request,
                               "edited": choices is not None, "provider": proposal["provider"],
                               "model": proposal["model"]})
            return {"call_id": call_id, "request": intent.request, "reading": intent.reading, "provenance": provenance}
        if event not in ("use", "edit"):
            raise AssistantError("malformed", "event is use or edit", status=400)
        self.audit.record({"id": _secrets.token_hex(8), "event": event, "call_id": call_id, "ts": _iso(self.clock()),
                           "run_id": call.get("run_id"), "provider": call.get("provider"), "model": call.get("model")})
        return {"call_id": call_id, "recorded": event}

    # -- reading the record ----------------------------------------------------------------------------

    def log(self, run_id: Optional[str]) -> Dict[str, Any]:
        records = self.audit.for_run(run_id) if run_id else self.audit.all_calls()
        return {"records": records, "methods": methods_sentences(records)}

    def used_runs(self) -> Dict[str, Any]:
        return {"run_ids": self.audit.runs_using_assistant(self.ws.runs_dir)}

    def attach(self, body: Any) -> Dict[str, Any]:
        if not isinstance(body, dict) or set(body) != {"run_id", "call_ids"} or not isinstance(body["call_ids"], list) \
                or not all(isinstance(c, str) for c in body["call_ids"]) or not isinstance(body["run_id"], str):
            raise AssistantError("malformed", "attach takes {run_id, call_ids}", status=400)
        try:
            n = self.audit.attach(body["run_id"], body["call_ids"])
        except ValueError:
            raise AssistantError("not_found", "there is no run with that id", status=404) from None
        return {"attached": n}

    def withdraw_consent(self) -> Dict[str, Any]:
        self.config.withdraw()
        return {"consent": {}}

    # -- the dispatch glue --------------------------------------------------------------------------------

    def handle(self, handler: str, query: Mapping[str, str], body: Any) -> Tuple[int, Dict[str, Any]]:
        """(HTTP status, JSON) for a route this service owns. Raises AssistantError for refusals."""
        if handler == "assistant_status":
            return 200, self.status()
        if handler == "assistant_get_settings":
            return 200, self.settings()
        if handler == "assistant_put_settings":
            try:
                return 200, self.put_settings(body)
            except ConfigError as exc:
                raise AssistantError("malformed", str(exc), status=400) from None
        if handler == "assistant_prepare":
            return 200, self.prepare(body)
        if handler == "assistant_send":
            return 200, self.send(body)
        if handler == "assistant_cancel":
            return 200, self.cancel((body or {}).get("call_id") if isinstance(body, dict) else None)
        if handler == "assistant_confirm":
            return 200, self.confirm(body)
        if handler == "assistant_log":
            return 200, self.log(query.get("run_id"))
        if handler == "assistant_runs":
            return 200, self.used_runs()
        if handler == "assistant_attach":
            return 200, self.attach(body)
        if handler == "assistant_forget_consent":
            return 200, self.withdraw_consent()
        raise AssistantError("not_found", "no such assistant route", status=404)


def _iso(epoch: float) -> str:
    import datetime as _dt

    return _dt.datetime.fromtimestamp(epoch, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


__all__ = ["AssistantService", "CONSENT_KEYS", "FEATURE_LABELS", "FIXED_TEST_PROMPT", "SpendGuard"]
