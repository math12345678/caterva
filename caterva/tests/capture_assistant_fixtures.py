"""Capture the REAL run results the assistant's tests use as their source JSON.

    cd <repository root> && PYTHONPATH=$PWD python caterva/tests/capture_assistant_fixtures.py

Each file under caterva/tests/fixtures/assistant/runs/ is what the studio
server answered to a real run request, through `App.dispatch` exactly as the
socket layer hands one over: the run record and the kind's Result. Literature
answers are the committed recordings (`studio_kinetics_offline`), so the
numbers are BRENDA's as recorded and the engine's as computed. Nothing is typed
by hand and the JSON must not be edited by hand.

These are the SOURCE the grounding tests check wording against; the wording
itself (what a model might say) is hand-written in the tests and labelled as
test input. Nothing here calls a language model.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "caterva" / "tests"))

OUT = REPO / "caterva" / "tests" / "fixtures" / "assistant" / "runs"
PORT = 18771
TOKEN = "e" * 43

LDH = {"description": "Michaelis-Menten with a competitive inhibitor", "subject": "1.1.1.27", "organism": "human",
       "substrate": "pyruvate", "inhibitor": "gossypol"}

RUNS = {
    # name: (kind, request, offline context name)
    "compose-ldh-gossypol-analysed": ("compose", {**LDH, "analyses": {"design": True, "validate": True,
                                                                      "identifiability": True, "robustness": {"samples": 5}}},
                                      "ldh"),
    "compose-glycolysis-refused": ("compose", {"description": "glycolysis"}, None),
    "constants-hexokinase": ("constants", {"ec": "2.7.1.1", "organism": "human", "substrate": "glucose"}, "hk"),
    "bind-gossypol": ("bind", {"mode": "inhibitor", "ec": "1.1.1.27", "organism": "human", "inhibitor": "gossypol"},
                      "ldhki"),
}


def main() -> None:
    from capture_studio_enzyme_fixtures import call, make_app
    from studio_kinetics_offline import hexokinase_offline, ldh_ki_page_offline, ldh_offline

    contexts = {"ldh": ldh_offline, "hk": hexokinase_offline, "ldhki": ldh_ki_page_offline, None: None}
    work = Path(tempfile.mkdtemp(prefix="caterva-assistant-fixtures-"))
    os.environ["XDG_CACHE_HOME"] = str(work / "cache")
    app = make_app(work)
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    try:
        for name, (kind, request, ctx) in RUNS.items():
            if only and name not in only:
                continue
            manager = contexts[ctx]() if contexts[ctx] else None
            if manager is not None:
                manager.__enter__()
            try:
                created = call(app, "POST", "/api/runs", {"kind": kind, "request": request})
                body: Dict[str, Any] = created.json()
                if created.status != 202:
                    print("REFUSED", name, created.status, body)
                    continue
                run_id = body["run"]["id"]
                while True:
                    record = call(app, "GET", f"/api/runs/{run_id}").json()
                    if record["status"] in ("done", "failed", "cancelled", "interrupted"):
                        break
                    time.sleep(0.3)
                result = call(app, "GET", f"/api/runs/{run_id}/result")
                files = {}
                for art in record.get("artifacts") or []:
                    if str(art.get("content_type", "")).startswith("text/markdown"):
                        got = call(app, "GET", f"/api/runs/{run_id}/artifacts/{art['name']}")
                        files[art["name"]] = got.body.decode("utf-8")
            finally:
                if manager is not None:
                    manager.__exit__(None, None, None)
            data_dir = str(app.ws.root)
            text = json.dumps({"captured": {"kind": kind, "request": request}, "run": record,
                               "result_status": result.status,
                               "result": result.json() if result.status == 200 else None,
                               "artifact_files": files},
                              indent=1, ensure_ascii=False, allow_nan=False)
            for spelling in {data_dir, str(Path(data_dir).resolve()), str(work), str(work.resolve())}:
                text = text.replace(spelling, "<data dir>")
            (OUT / f"{name}.json").write_text(text + "\n", encoding="utf-8")
            print("wrote", name, record["status"], (record.get("outcome") or {}).get("meaning"), result.status, flush=True)
    finally:
        app.close()


if __name__ == "__main__":
    main()
