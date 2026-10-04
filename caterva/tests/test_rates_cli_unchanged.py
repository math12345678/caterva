"""`caterva rates` prints what it printed before `caterva.rates.run` existed, byte for byte.

Studio needed the command's sequence (check the question, read, fit, compare
with the literature) as a library call, so it was moved out of
`__main__.main` into `caterva/rates/run.py`, and `main` now calls it. A
refactor of a command that people cite is only safe if the output cannot
have moved. The sixteen files in `fixtures/rates_cli_golden/` are the
command's stdout, stderr and exit code on the real Puromycin table, written
by the code before the change (the README there says how); each is run again
here and compared, with only the machine's version strings masked.
"""
from __future__ import annotations

import io
import json
import re
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from caterva.rates.__main__ import main
from caterva.rates.literature import LiteratureUnavailable

REPO = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).resolve().parent / "fixtures" / "rates_cli_golden"
CASES = sorted(GOLDEN.glob("*.json"))

_SOFTWARE = re.compile(r"Caterva \S+ \(caterva rates\), Python \S+, NumPy \S+, SciPy \S+")
_VERSION = re.compile(r'"caterva": "[^"]*"')


def mask(text: str) -> str:
    return _VERSION.sub('"caterva": "VERSION"', _SOFTWARE.sub("Caterva VERSION (caterva rates), Python X, NumPy X, SciPy X", text))


def no_literature(**_kwargs):
    raise LiteratureUnavailable("stubbed: no literature layer in this golden run")


def test_the_golden_set_is_all_sixteen_invocations():
    assert len(CASES) == 16


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_the_command_prints_what_it_printed_before(path, monkeypatch):
    golden = json.loads(path.read_text(encoding="utf-8"))
    monkeypatch.chdir(REPO)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = main(golden["argv"], resolver=no_literature)
        except SystemExit as exc:  # argparse
            code = exc.code
    assert code == golden["exit"]
    assert mask(out.getvalue()) == mask(golden["stdout"])
    assert mask(err.getvalue()) == mask(golden["stderr"])
