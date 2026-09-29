#!/usr/bin/env python3
"""The exported archive opens in a tool that did not write it.

WHY THIS EXISTS
---------------
`combine_archive.py` claims an `.omex` "opens in COPASI, Tellurium, JWS
Online and the BioSimulators runners". For a long time that was inference
from libSEDML being the reference implementation, and the module said so.

ADR 0189 measured two of the four by hand: Tellurium ran the whole archive,
COPASI loaded the model and integrated it to a substrate within 2.8e-08
relative of Terrium's own answer. It also recorded the gap this closes:

    Nothing automated does this. It was run by hand once. No test
    reproduces it, because the pinned environment cannot import tellurium,
    so a test would need a second interpreter to be meaningful.

A measurement nobody can re-run is a claim, not evidence. ADR 0186 made
that argument about a different hand-run procedure and turned it into a
guard; this is the same argument applied to my own.

WHY IT IS NOT CALLED `check_`, AND IS NOT A GUARD
-------------------------------------------------
This project's rule is that "a guard is not delivered until something runs
it unasked" (check_guard_wiring). Nothing can run this unasked: it needs a
second interpreter holding tellurium or basico, and no CI here has one.

Calling it `check_export_opens_elsewhere.py` would have claimed a status it
cannot have -- `check_guard_wiring` globs `check_*.py` and would have
demanded a harness, and the honest answer is that there is none. It is a
reproducible PROCEDURE: the thing ADR 0189 did by hand, written down so the
next person runs the same steps instead of inventing them.

WHY IT IS NOT A PYTEST TEST
---------------------------
Tellurium cannot be installed alongside Terrium's pinned environment:
requirements.txt pins `antimony==2.14.0` and tellurium 2.2.13.1 requires
`antimony>=3.1.0`, so pip resolves the conflict by moving the pin. A test
inside the pinned suite could therefore only ever skip -- and a suite that
skips is the failure `check_no_silent_skips` exists to catch.

So the reader is a SECOND INTERPRETER, named explicitly, and its absence is
reported as "could not check" (exit 3) rather than as success. Three states,
not two: opened / did not open / no reader available to try.

    TERRIUM_INTEROP_PYTHON=/path/to/venv/bin/python \\
        python scripts/verify_export_opens_elsewhere.py

Usage:
    python scripts/verify_export_opens_elsewhere.py [--selftest]
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
READER_ENV = "TERRIUM_INTEROP_PYTHON"

#: Terrium's own answer for the payload below, from its in-process run.
#: Compared rather than asserted flat: two adaptive integrators at default
#: tolerances do not agree to the last bit, and demanding that they do would
#: make this guard fail for a reason that is not a defect. 1e-06 is far
#: looser than the 2.8e-08 measured against COPASI and far tighter than any
#: real modelling difference.
TOLERANCE = 1e-6

PAYLOAD = {
    "format": "omex", "domain": "mm",
    "parameters": {"km": 0.31, "vmax": 0.25, "s0": 10.0},
    "provenance": {
        "km": {
            "origin": "resolved", "citation": "PMID 16333295",
            "citationSource": "pubmed", "referenceId": "16333295",
            "organism": "Homo sapiens", "taxonId": "9606", "source": "BRENDA",
            # No assayConditions on purpose. They ride in the SBML NOTES,
            # and this procedure checks CVTerms -- so they would test
            # nothing here while putting a hardcoded pH and temperature in
            # a source file, which `check_no_hardcoded_assay_conditions`
            # forbids and duly caught on the first run. A payload should
            # carry what the check needs and no more.
        },
        "s0": {"origin": "user", "note": "chosen by the student"},
    },
    "endTime": 10.0, "points": 11,
}

#: Run inside the READER interpreter. Prints one JSON object on stdout.
#:
#: Deliberately tolerant about which reader is present: tellurium and basico
#: are different packages and a machine may have either. What it must not do
#: is report success having loaded nothing, so `opened_with` is empty unless
#: a reader actually parsed the model.
READER_SNIPPET = r'''
import json, sys, zipfile, tempfile, os, warnings
warnings.filterwarnings("ignore")
out = {"opened_with": [], "final_substrate": None, "uris": [],
       "annotations_readable": False, "errors": []}
archive = sys.argv[1]
with zipfile.ZipFile(archive) as z:
    out["entries"] = sorted(z.namelist())
    sbml = z.read("model.xml").decode("utf-8")

try:
    import libsbml
    out["annotations_readable"] = True
    doc = libsbml.readSBMLFromString(sbml); model = doc.getModel()
    for i in range(model.getNumParameters()):
        p = model.getParameter(i)
        for t in range(p.getNumCVTerms()):
            term = p.getCVTerm(t)
            for r in range(term.getNumResources()):
                out["uris"].append(term.getResourceURI(r))
except Exception as exc:
    out["errors"].append("libsbml: %s" % exc)

try:
    import tellurium as te
    rr = te.loadSBMLModel(sbml)
    res = rr.simulate(0, 10, 11)
    out["opened_with"].append("tellurium")
    out["final_substrate"] = float(res[-1][1])
except Exception as exc:
    out["errors"].append("tellurium: %s" % type(exc).__name__)

if out["final_substrate"] is None:
    try:
        import basico
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "m.xml")
            # encoding stated: the model carries non-ASCII (units, notes),
            # and a reader whose default encoding is not UTF-8 raises
            # UnicodeEncodeError here -- which this guard reported as the
            # EXPORT failing. Measured against the basico environment.
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(sbml)
            basico.load_model(p)
            tc = basico.run_time_course(start_time=0, duration=10, intervals=10)
        out["opened_with"].append("copasi")
        out["final_substrate"] = float(tc.iloc[-1]["S"])
    except Exception as exc:
        out["errors"].append("basico: %s" % type(exc).__name__)

print(json.dumps(out))
'''


def _reader() -> str | None:
    path = os.environ.get(READER_ENV, "").strip()
    return path or None


def _export(destination: Path) -> tuple[bool, str]:
    """Build the archive with THIS interpreter -- the pinned one."""
    done = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "export_annotated_model.py")],
        input=json.dumps(PAYLOAD), capture_output=True, text=True,
        cwd=str(REPO_ROOT), timeout=300,
    )
    if done.returncode != 0:
        return False, f"export failed: {done.stderr.strip()[:300]}"
    try:
        result = json.loads(done.stdout.strip())
    except json.JSONDecodeError as exc:
        return False, f"export produced unreadable output: {exc}"
    if not result.get("ok"):
        return False, f"export refused: {result.get('error', '')[:200]}"
    destination.write_bytes(base64.b64decode(result["modelBase64"]))
    return True, ""


def _caterva_substrate() -> float | None:
    """Caterva's own final substrate, for comparison."""
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from caterva.continuous.simulations import simulate_michaelis_menten\n"
        "r = simulate_michaelis_menten(km=0.31, vmax=0.25, s0=10.0, end=10.0, points=11)\n"
        "print(float(list(r.data)[-1][1]))\n" % str(REPO_ROOT)
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, cwd=str(REPO_ROOT), timeout=300)
    try:
        return float(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def main() -> int:
    reader = _reader()
    if reader is None or not Path(reader).exists():
        print(
            "Could not check: no reader interpreter.\n"
            f"\nSet {READER_ENV} to a python that has tellurium or basico:\n"
            f"    {READER_ENV}=/path/to/venv/bin/python \\\n"
            "        python scripts/verify_export_opens_elsewhere.py\n"
            "\nIt must be a SEPARATE environment. Tellurium requires\n"
            "antimony>=3.1.0 and requirements.txt pins 2.14.0, so installing\n"
            "it here would move the pin (ADR 0189).\n"
            "\nExiting 3: 'no reader available' is not 'the archive opens'."
        )
        return 3

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "export.omex"
        ok, why = _export(archive)
        if not ok:
            print(f"FAIL: {why}", file=sys.stderr)
            return 1

        done = subprocess.run([reader, "-c", READER_SNIPPET, str(archive)],
                              capture_output=True, text=True, timeout=600)
        if done.returncode != 0 or not done.stdout.strip():
            print(f"FAIL: the reader could not run.\n  {done.stderr.strip()[:400]}",
                  file=sys.stderr)
            return 1
        try:
            report = json.loads(done.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError as exc:
            print(f"FAIL: reader output unreadable ({exc}).", file=sys.stderr)
            return 1

    problems: list[str] = []
    unverified: list[str] = []
    if not report["opened_with"]:
        problems.append(
            "no reader opened the model: " + "; ".join(report["errors"][:3])
        )
    if not report.get("entries"):
        problems.append("the archive listed no entries")

    # The annotations must survive into what the other tool sees. Asserted on
    # the evidence URI, not on the word "ECO": the accession appears in the
    # model's notes too, and matching there would pass whether or not a
    # CVTerm crossed (ADR 0128).
    #
    # ONLY WHEN THERE WAS A PARSER TO LOOK WITH. The first version reported
    # "the evidence CVTerm did not reach the reader" against an environment
    # that simply had no standalone libsbml -- COPASI bundles its own -- so
    # an empty URI list meant "nobody looked", and the guard called it
    # "not there". That is the three-state failure this project keeps
    # recording, committed by a guard written to close one.
    if report.get("annotations_readable"):
        if not any("eco/ECO:0000269" in u for u in report["uris"]):
            problems.append("the evidence CVTerm did not reach the reader")
        if not any("pubmed" in u for u in report["uris"]):
            problems.append("the citation CVTerm did not reach the reader")
    else:
        unverified.append(
            "annotations were NOT checked: the reader has no standalone "
            "libsbml, so there was nothing to inspect the CVTerms with. "
            "Opening and integrating were still checked."
        )

    mine = _caterva_substrate()
    theirs = report.get("final_substrate")
    if mine is None:
        problems.append("Terrium's own run produced no number to compare")
    elif theirs is None:
        problems.append("the reader produced no trajectory to compare")
    else:
        rel = abs(mine - theirs) / abs(mine)
        if rel > TOLERANCE:
            problems.append(
                f"trajectories disagree: Terrium {mine!r}, reader {theirs!r}, "
                f"relative {rel:.2e} > {TOLERANCE:.0e}"
            )

    if problems:
        print(f"FAIL: the export did not survive the trip ({len(problems)}):\n")
        for p in problems:
            print(f"  - {p}")
        return 1

    for u in unverified:
        print(f"NOT CHECKED: {u}")
    print(f"OK: opened by {', '.join(report['opened_with'])}, "
          f"{len(report['entries'])} archive entries, "
          f"{len(report['uris'])} annotation URI(s) visible.")
    print(f"    substrate at t=10: Terrium {mine!r}, reader {theirs!r} "
          f"(relative {abs(mine - theirs) / abs(mine):.2e})")
    return 0


def selftest() -> int:
    """Prove the comparison can fail, and that absence is not success."""
    failures = 0

    saved = os.environ.pop(READER_ENV, None)
    code = main()
    ok = code == 3
    failures += 0 if ok else 1
    print(f"  [{'ok' if ok else 'FAIL'}] no reader configured -> exit 3, "
          f"not 0 (got {code})")

    os.environ[READER_ENV] = "/nonexistent/python"
    code = main()
    ok = code == 3
    failures += 0 if ok else 1
    print(f"  [{'ok' if ok else 'FAIL'}] reader path that does not exist -> "
          f"exit 3 (got {code})")

    if saved is not None:
        os.environ[READER_ENV] = saved
    else:
        os.environ.pop(READER_ENV, None)

    # The tolerance must reject a real disagreement rather than wave it
    # through. Checked arithmetically: a 1% difference is 1e-2, four orders
    # above the bar.
    ok = (0.01 > TOLERANCE) and (2.8e-08 < TOLERANCE)
    failures += 0 if ok else 1
    print(f"  [{'ok' if ok else 'FAIL'}] tolerance admits the measured "
          f"2.8e-08 and rejects a 1% difference")

    if failures:
        print(f"\nFAIL: {failures} selftest case(s) failed.")
        return 1
    print("\nSelftest passed: a missing reader is reported as unknown, "
          "not as success.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    raise SystemExit(main())
