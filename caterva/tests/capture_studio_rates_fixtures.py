"""Capture the Rates screen's UI fixtures from the running dispatch layer.

    cd <repository root> && PYTHONPATH=$PWD python caterva/tests/capture_studio_rates_fixtures.py

Every file written under
Science-Agent-Pipeline/artifacts/caterva-studio/src/__fixtures__/api/rates/
is what the studio server answered to a real request, through
`caterva.studio.dispatch.App.dispatch` exactly as the socket layer hands a
request over: the table preview for each shape of table, three runs of the
`rates` kind (with their events and result) and the capabilities. Nothing is
typed by hand and the JSON must not be edited by hand. The README beside them
says what each is.

THE DATA
Every measurement is a value of examples/rates/puromycin.csv, R's
`datasets::Puromycin` (Treloar 1974; Bates and Watts 1988): the file itself,
its treated rows alone, and the two lowest substrate concentrations of the
treated rows. The other tables are the same values saved the way a
spreadsheet or a plate reader saves them (tabs, decimal commas, a byte-order
mark, Windows line endings, one column per replicate, a header with units in
brackets): formats, not data. The few bad cells in the "messy" table contain
no invented number. The literature layer is never reached: the one literature
request is declined by the command itself, before any lookup, because the
substrate is in ppm.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "caterva" / "tests"))

import capture_studio_enzyme_fixtures as base  # noqa: E402

OUT = base.OUT / "rates"
EXAMPLE = REPO / "examples" / "rates" / "puromycin.csv"
TEXT = EXAMPLE.read_text(encoding="utf-8")
HEAD = [l for l in TEXT.splitlines() if l and not l.startswith("#")]
ROWS = [r for r in csv.reader(io.StringIO("\n".join(HEAD)))][1:]
TREATED = [(s, v) for s, v, g in ROWS if g == "treated"]
UNTREATED = [(s, v) for s, v, g in ROWS if g == "untreated"]


def comma(x: str) -> str:
    return x.replace(".", ",")


def tables() -> Dict[str, str]:
    by_s: Dict[str, List[str]] = {}
    for s, v in TREATED:
        by_s.setdefault(s, []).append(v)
    messy = ["substrate (ppm)\trate (counts/min/min)\tstate"]
    for k, (s, v) in enumerate(TREATED):
        messy.append(f"{s}\t{v}\ttreated")
        if k == 1:
            messy.append("0.06\tn/a\ttreated")
        if k == 3:
            messy.append("0.11\t\ttreated")
        if k == 7:
            messy.append("0,56\t200\ttreated")
    messy.insert(3, "")
    return {
        "puromycin": TEXT,
        "pasted-decimal-comma": "\ufeff[S] (ppm)\tv0 (counts/min/min)\r\n"
        + "\r\n".join(f"{comma(s)}\t{comma(v)}" for s, v in TREATED) + "\r\n\r\n",
        "wide": "[S] (ppm)\trep1 (counts/min/min)\trep2 (counts/min/min)\n"
        + "\n".join(f"{s}\t{vs[0]}\t{vs[1]}" for s, vs in by_s.items()) + "\n",
        "messy": "\n".join(messy) + "\n",
        "no-units": "\n".join(f"{s}\t{v}" for s, v in TREATED) + "\n",
        "binary": "PK\x03\x04\x14\x00\x00\x00\x08\x00 a spreadsheet saved as a workbook\x00\x00",
        "never-saturates": "\n".join([HEAD[0]] + [",".join(r) for r in ROWS if r[2] == "treated" and float(r[0]) <= 0.06]) + "\n",
    }


def write(path: Path, body: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(base.neutral(json.dumps(body, indent=1, ensure_ascii=False, allow_nan=False)).replace("\ufeff", "\\ufeff") + "\n", encoding="utf-8")
    print("wrote", path.relative_to(REPO))


def preview(app: Any, name: str, text: str, filename: str | None, mapping: Dict[str, Any] | None = None) -> None:
    body: Dict[str, Any] = {"text": text}
    if filename:
        body["filename"] = filename
    if mapping:
        body["mapping"] = mapping
    response = base.call(app, "POST", "/api/rates/preview", body)
    write(OUT / f"preview-{name}.json", {"request": {"method": "POST", "path": "/api/rates/preview", "body": body},
                                         "status": response.status, "body": response.json()})


def run(app: Any, name: str, request: Dict[str, Any]) -> None:
    created = base.call(app, "POST", "/api/runs", {"kind": "rates", "request": request})
    assert created.status == 202, created.json()
    run_id = created.json()["run"]["id"]
    while True:
        record = base.call(app, "GET", f"/api/runs/{run_id}").json()
        if record["status"] in ("done", "failed", "cancelled", "interrupted"):
            break
        time.sleep(0.2)
    result = base.call(app, "GET", f"/api/runs/{run_id}/result")
    events = base.call(app, "GET", f"/api/runs/{run_id}/events")
    frames: List[Dict[str, Any]] = []
    for chunk in events.stream or ():
        for block in chunk.decode("utf-8").split("\n\n"):
            fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
            if "event" in fields and "data" in fields:
                frames.append({"event": fields["event"], "data": json.loads(fields["data"])})
    data_dir = str(app.ws.root)
    text = json.dumps({
        "captured": {"kind": "rates", "request": request},
        "run": record,
        "result_status": result.status,
        ("result" if result.status == 200 else "error"): result.json(),
        "events": frames,
    }, indent=1, ensure_ascii=False, allow_nan=False).replace(data_dir, "<data dir>")
    path = OUT / f"run-{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(base.neutral(text).replace("\ufeff", "\\ufeff") + "\n", encoding="utf-8")
    print("wrote", path.relative_to(REPO), record["status"], record["outcome"]["meaning"] if record.get("outcome") else "")


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="caterva-rates-fixtures-"))
    base.SCRATCH[:] = [str(work), str(work.resolve())]
    os.environ["XDG_CACHE_HOME"] = str(work / "cache")
    app = base.make_app(work)
    try:
        t = tables()
        preview(app, "puromycin", t["puromycin"], "puromycin.csv")
        preview(app, "pasted-decimal-comma", t["pasted-decimal-comma"], None)
        preview(app, "wide", t["wide"], "replicates.tsv")
        preview(app, "messy", t["messy"], "treated-messy.tsv")
        preview(app, "no-units", t["no-units"], None)
        # The person names the units one at a time, each time sending back the mapping the server answered
        # with that unit added, as the page does.
        bare = json.loads((OUT / "preview-no-units.json").read_text())["body"]["mapping"]
        first = {**bare, "units": {**bare.get("units", {}), "substrate": "ppm"}}
        preview(app, "no-units-substrate-named", t["no-units"], None, first)
        both = {**first, "units": {**first["units"], "rate": "counts/min/min"}}
        preview(app, "no-units-named", t["no-units"], None, both)
        preview(app, "binary", t["binary"], "workbook.xlsx")
        preview(app, "never-saturates", t["never-saturates"], "treated-low.csv")
        # The effective mapping the server answered, sent back, is what a run carries.
        answered = json.loads((OUT / "preview-puromycin.json").read_text())["body"]["mapping"]
        # The person sets the group column to "not used": the mapping changes, and the server answers again.
        ungrouped = {**answered, "roles": {**answered["roles"], "group": None}}
        preview(app, "puromycin-group-off", t["puromycin"], "puromycin.csv", ungrouped)
        run(app, "puromycin-residuals", {"dataset": {"text": t["puromycin"], "filename": "puromycin.csv", "mapping": answered},
                                         "sigma_from": "residuals"})
        run(app, "puromycin-replicates", {"dataset": {"text": t["puromycin"], "filename": "puromycin.csv", "mapping": answered},
                                          "sigma_from": "replicates", "error_model": "proportional"})
        low = json.loads((OUT / "preview-never-saturates.json").read_text())["body"]["mapping"]
        run(app, "never-saturates", {"dataset": {"text": t["never-saturates"], "filename": "treated-low.csv", "mapping": low},
                                     "sigma_from": "residuals"})
        run(app, "literature-declined", {"dataset": {"text": t["puromycin"], "filename": "puromycin.csv", "mapping": answered},
                                         "sigma_from": "residuals", "ec": "2.4.1.22", "organism": "human",
                                         "substrate": "galactose"})
        run(app, "refused-law-needs-inhibitor", {"dataset": {"text": t["puromycin"], "filename": "puromycin.csv", "mapping": answered},
                                         "sigma_from": "residuals", "model": "competitive"})
        write(OUT / "capabilities-rates.json", base.get_json(app, "/api/capabilities"))
    finally:
        app.close()


if __name__ == "__main__":
    main()
