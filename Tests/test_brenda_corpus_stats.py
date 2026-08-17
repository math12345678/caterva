"""`scientific corpus` — three outcomes, three exit codes.

WHY THIS FILE EXISTS
--------------------
`scripts/brenda_corpus_stats.py` had **no tests**. It is reachable (the CLI
`corpus` command spawns it) and it is the script that answers Jeske's STRENDA
question — how much of BRENDA states the pH and temperature a value was
measured under — so its figures end up quoted.

Untested, it conflated two situations its own comment said must be told
apart:

    # Not an error, and not a silent zero either. A file that parsed
    # cleanly but contained no measurements is a real outcome and the
    # reader needs to know which of the two happened.
    message = f"... ({rows} row(s), all prose-only or malformed)."
    return 0

The `or` in that message is the tell — the code could not say which had
happened. And both returned 0, so pointing the tool at a file that is not a
BRENDA download at all produced `{"ok": true, ...}` with every figure zero,
and a script saw a pass.

The three cases are now distinct, and this file pins each. They are built
from fixtures written here rather than from a real 200 MB download, because a
test that needs a file the user has to fetch by hand is a test that gets
skipped — and the two skips already in this suite are why this script went
untested in the first place.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "brenda_corpus_stats.py"


def write_tsv(path: Path, rows: list[tuple[str, ...]]) -> Path:
    """Nine fields per row: eight columns plus the trailing tab BRENDA emits.

    Not rstrip()ped, for the reason Tests/brenda_bulk.py records: every real
    row ends in a tab that produces a ninth, always-empty field, and a reader
    that strips disagrees with one that does not about the schema.
    """
    path.write_text("\n".join("\t".join(r) + "\t" for r in rows) + "\n", encoding="utf-8")
    return path


MEASURED = (
    "1.1.1.27", "L-lactate dehydrogenase", "10.73", "-", "pyruvate",
    "pH 7.5, 25°C, recombinant enzyme", "12345", "740253",
)
PROSE_ONLY = (
    "1.1.1.27", "L-lactate dehydrogenase", "additional information", "-",
    "pyruvate", "kinetics studied", "12346", "740254",
)


def run(path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path), *extra],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )


def test_a_download_with_measurements_reports_figures_and_exits_0(tmp_path):
    f = write_tsv(tmp_path / "km.tsv", [MEASURED, PROSE_ONLY])
    result = run(f)
    assert result.returncode == 0
    assert "STRENDA" in result.stdout


def test_the_prose_only_row_is_excluded_from_the_denominator(tmp_path):
    # The figure that matters: 'additional information' rows describe
    # kinetics in prose and never had a value for conditions to accompany,
    # so counting them would understate reporting.
    f = write_tsv(tmp_path / "km.tsv", [MEASURED, PROSE_ONLY])
    doc = json.loads(run(f, "--json").stdout)
    assert doc["strenda"]["measured_rows"] == 1
    assert doc["strenda"]["both_conditions"] == 1
    assert doc["parse"]["additionalInformation"] == 1


def test_a_download_of_only_prose_rows_exits_2(tmp_path):
    # A GENUINE BRENDA download that happens to carry no measured values.
    # The analysis ran and this is its answer, so it is exit 2 — the same
    # distinction `resolve` draws between "the literature has nothing" and
    # "the lookup could not be performed".
    f = write_tsv(tmp_path / "prose.tsv", [PROSE_ONLY, PROSE_ONLY])
    result = run(f)
    assert result.returncode == 2
    assert "no measured values" in result.stdout
    # It must name WHICH of the two situations this is. "prose-only or
    # malformed" was the old message and is exactly what this pins against.
    assert "additional information" in result.stdout
    assert "malformed" not in result.stdout


def test_a_file_that_is_not_a_brenda_download_exits_1(tmp_path):
    # Nothing matched the nine-field schema. Not a threshold — zero of N is
    # categorical — and almost always the wrong file, which is a mistake in
    # the invocation like "No such file", so it exits the same way.
    f = tmp_path / "notes.txt"
    f.write_text("these are my notes\nnot a tsv at all\n", encoding="utf-8")
    result = run(f)
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "does not have the shape of a BRENDA bulk download" in combined
    # And it must NOT report figures computed over nothing.
    assert "57.1%" not in combined


def test_the_unrecognised_file_says_so_in_json_too(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("garbage\n", encoding="utf-8")
    result = run(f, "--json")
    assert result.returncode == 1
    doc = json.loads(result.stdout)
    assert doc["ok"] is False
    assert doc["error"] == "unrecognised-format"
    # The evidence travels with the verdict: a caller can see WHY nothing
    # parsed rather than having to re-run without --json.
    assert doc["parse"]["rows"] == 0
    assert doc["parse"]["linesConsidered"] >= 1


def test_a_missing_file_is_not_an_empty_one(tmp_path):
    # Already true before this pass, asserted so it stays true: the three
    # negative outcomes are distinct, not two.
    result = run(tmp_path / "no_such_file.tsv")
    assert result.returncode == 1
    assert "No such file" in result.stdout + result.stderr


@pytest.mark.parametrize("case", ["measured", "prose", "unrecognised"])
def test_json_output_is_always_one_parsable_document(tmp_path, case):
    # `corpus --json` is a scripting contract. Whichever branch is taken,
    # stdout carries one document — the failure mode being guarded against is
    # a human-readable sentence printed alongside it.
    if case == "measured":
        f = write_tsv(tmp_path / "a.tsv", [MEASURED])
    elif case == "prose":
        f = write_tsv(tmp_path / "a.tsv", [PROSE_ONLY])
    else:
        f = tmp_path / "a.txt"
        f.write_text("nope\n", encoding="utf-8")

    out = run(f, "--json").stdout
    json.loads(out)  # raises, and fails the test, if anything else got in
