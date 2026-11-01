"""The audit trail: every assistant call, recorded where the run it belongs to is.

A record holds what a reviewer needs to reproduce the judgement: provider,
model, feature, the EXACT payload that was sent (after redaction), the raw
response, the grounding result, whether the output was accepted or rejected,
the person's confirmation if there was one, and a timestamp. It never holds a
key: every string is passed through `redact.scrub` (key shapes and the exact
configured secrets) on its way in.

Where it goes:
  * `<data dir>/assistant/calls.jsonl`: the per-call log, every call;
  * `<run dir>/assistant.jsonl`: the same records for a call about that run,
    which the run bundle includes (`workspace.bundle`) and History marks.
A call made before a run exists (Compose "describe it") is attached to the
run the person then starts, when they confirm (`attach`).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from caterva.assistant.redact import scrub

RUN_FILE = "assistant.jsonl"


def _scrub_value(value: Any, secrets: Iterable[str]) -> Any:
    secrets = list(secrets)
    if isinstance(value, str):
        return scrub(value, secrets)
    if isinstance(value, dict):
        return {scrub(str(k), secrets): _scrub_value(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_value(v, secrets) for v in value]
    return value


class AuditLog:
    def __init__(self, data_dir: Path, run_dir_for: Callable[[str], Path],
                 secrets: Callable[[], Iterable[str]] = lambda: ()) -> None:
        self.dir = Path(data_dir) / "assistant"
        self.run_dir_for = run_dir_for
        self.secrets = secrets
        self._lock = threading.Lock()

    @property
    def calls_path(self) -> Path:
        return self.dir / "calls.jsonl"

    def _append(self, path: Path, record: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
        with self._lock:
            fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(line)

    def record(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        clean = _scrub_value(dict(record), self.secrets())
        self._append(self.calls_path, clean)
        run_id = clean.get("run_id")
        if isinstance(run_id, str):
            try:
                run_dir = self.run_dir_for(run_id)
            except ValueError:
                run_dir = None
            if run_dir is not None and run_dir.is_dir():
                self._append(run_dir / RUN_FILE, clean)
        return clean

    def read(self, path: Path) -> List[Dict[str, Any]]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                out.append(value)
        return out

    def for_run(self, run_id: str) -> List[Dict[str, Any]]:
        try:
            return self.read(self.run_dir_for(run_id) / RUN_FILE)
        except ValueError:
            return []

    def all_calls(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self.read(self.calls_path)[-limit:]

    def call(self, call_id: str) -> Optional[Dict[str, Any]]:
        found = None
        for r in self.read(self.calls_path):
            if r.get("id") == call_id and r.get("event", "call") == "call":
                found = r
        return found

    def attach(self, run_id: str, call_ids: Iterable[str]) -> int:
        """Copy the log's records for these calls (and their confirmations) into the run's own file."""
        wanted = set(call_ids)
        run_dir = self.run_dir_for(run_id)
        if not run_dir.is_dir():
            return 0
        have = {(r.get("id"), r.get("event", "call")) for r in self.read(run_dir / RUN_FILE)}
        n = 0
        for r in self.read(self.calls_path):
            rid = r.get("id") if r.get("event", "call") == "call" else r.get("call_id")
            if rid in wanted and (r.get("id"), r.get("event", "call")) not in have:
                self._append(run_dir / RUN_FILE, {**r, "run_id": run_id})
                n += 1
        return n

    def runs_using_assistant(self, runs_dir: Path) -> List[str]:
        out = []
        try:
            for child in sorted(runs_dir.iterdir()):
                if (child / RUN_FILE).is_file():
                    out.append(child.name)
        except OSError:
            pass
        return out


def methods_sentences(records: Iterable[Mapping[str, Any]]) -> List[str]:
    """Methods-text sentences for what the assistant did in a run: deterministic, from the records only."""
    calls: Dict[str, Mapping[str, Any]] = {}
    confirms: Dict[str, Mapping[str, Any]] = {}
    for r in records:
        if r.get("event", "call") == "call":
            calls[str(r.get("id"))] = r
        elif r.get("event") in ("confirm", "edit"):
            confirms[str(r.get("call_id"))] = r
    out: List[str] = []
    for cid, r in calls.items():
        who = f"An assistant ({r.get('model')}, {r.get('provider')}{', running on this computer' if r.get('local') else ''})"
        feature = r.get("feature")
        confirmation = confirms.get(cid)
        accepted = r.get("outcome") == "accepted"
        if feature == "describe":
            if confirmation and confirmation.get("event") == "confirm" and accepted:
                fields = ", ".join(f"{k} = {v}" for k, v in (confirmation.get("suggested") or []))
                out.append(f"{who} suggested the mechanism description ({fields}); the person confirmed it, and the "
                           "values became choices made by the person.")
            else:
                out.append(f"{who} was asked to interpret a description; its suggestion was not used.")
        elif accepted:
            what = {"explain": "a plain-language explanation of the result",
                    "methods": "a draft of this methods text",
                    "ask": "an answer to a question about this run",
                    "next": "a plain-language account of the ranked next measurements"}.get(str(feature), "text")
            edited = confirmation is not None and confirmation.get("event") == "edit"
            out.append(f"{who} generated {what}. The text was checked by Caterva against the run's own results "
                       f"(every figure, unit, EC number and citation found in them)"
                       + (" and edited by the person." if edited else "."))
        else:
            out.append(f"{who} produced text for {feature} that was rejected by that check and not shown as its wording.")
    return out


__all__ = ["AuditLog", "RUN_FILE", "methods_sentences"]
