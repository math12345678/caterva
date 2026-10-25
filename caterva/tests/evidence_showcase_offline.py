"""The showcase claims bundle, built once per test session with the network made impossible.

Shared by caterva/tests/test_check_verify.py and test_verify_mutations.py,
which hold `caterva verify` to the bundle caterva/evidence/showcase.py
writes from the recorded hexokinase page. It is a helper module beside
studio_kinetics_offline.py and assistant_support.py rather than a
conftest.py, the house style, so a test file names where its fixtures come
from. test_evidence_showcase.py and test_why.py still build their own copy
with the same body; switching them is a one-line fixture each
(`return showcase_built(tmp_path_factory)`).

WHY ONCE PER SESSION
--------------------
A build reads and parses the 3.7 MB recorded page, about five seconds, and
each module that built its own paid it again (four modules, about 22 s a
suite run, measured 2026-10-24). One build can serve every module because
nobody writes to it: a test that damages a bundle damages a copy
(`copy_bundle`), and the shared directory is read-only by that rule.

WHY THE NETWORK IS MADE IMPOSSIBLE
----------------------------------
The showcase is the offline example ADR 0179 shows; a build that reached
BRENDA would pass or fail with the database's mood. Every httpx send raises
while it runs, and the two recorded-answer variables are unset so that the
recorded page is read only where showcase.py reads it.
"""
from __future__ import annotations

import io
import json
import shutil
import zlib
from contextlib import redirect_stderr, redirect_stdout
from typing import TYPE_CHECKING, Any, Callable

import httpx
import pytest

from caterva.evidence import showcase
from caterva.evidence.claims import Certificate, Derivation, RuleRef, make_claim, to_dict

if TYPE_CHECKING:
    from pathlib import Path

#: basetemp of the session -> (bundle directory, root ref): one build per session.
_BUILT: dict[str, tuple[Path, str]] = {}


def no_network(self: Any, request: httpx.Request) -> httpx.Response:
    """httpx.HTTPTransport.handle_request while a build runs: every send refused."""
    raise httpx.ConnectError("network disabled in this test", request=request)


def showcase_built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """(directory, root claim ref) of the showcase bundle, built on the first
    call of the session and the same directory on every later one. Read-only:
    copy it with `copy_bundle` before changing a byte."""
    key = str(tmp_path_factory.getbasetemp())
    if key not in _BUILT:
        out = tmp_path_factory.mktemp("showcase")
        patch = pytest.MonkeyPatch()
        patch.setattr(httpx.HTTPTransport, "handle_request", no_network)
        patch.delenv("CATERVA_BRENDA_RECORDED", raising=False)
        patch.delenv("CATERVA_HTTP_RECORDED", raising=False)
        try:
            root = showcase.showcase_bundle(out)
        finally:
            patch.undo()
        _BUILT[key] = (out, root)
    return _BUILT[key]


def copy_bundle(directory: Path, tmp_path: Path) -> Path:
    """A fresh copy of the bundle to damage; the producer's store is not copied
    (the checker reads only the bundle's own files)."""
    target = tmp_path / "bundle"
    shutil.copytree(directory, target, ignore=shutil.ignore_patterns("store"))
    return target


def records(path: Path) -> list[dict]:
    """The JSON records of a bundle file, split on newline only, as both readers split."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def write_records(path: Path, items: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in items), encoding="utf-8")


def recomputed(record: dict) -> dict:
    """The claim record with its id recomputed by the PRODUCER (`make_claim`),
    so a test can state a changed derivation and leave identity out of what
    it tests."""
    derivation = record["derivation"]
    claim = make_claim(
        record["kind"], record["subject"], record["value_text"], record["unit"], record["tolerance"],
        Derivation(
            RuleRef(**derivation["rule"]), inputs=tuple(derivation["inputs"]),
            certificates=tuple(Certificate(c["snapshot"], tuple(c["span"]), c["matched"]) for c in derivation["certificates"]),
            settings=dict(derivation["settings"]),
        ),
    )
    return to_dict(claim)


def zeros_gzip(path: Path, size: int) -> Path:
    """A gzip file of `size` zero bytes, written a MiB at a time so the test
    never holds what the blob inflates to (128 MiB of zeros is a 130 KB
    file): the shape of a gzip bomb, for the checker's bound on inflation."""
    deflater = zlib.compressobj(6, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
    zeros = b"\0" * (1 << 20)
    with path.open("wb") as handle:
        left = size
        while left:
            take = min(left, len(zeros))
            handle.write(deflater.compress(zeros[:take]))
            left -= take
        handle.write(deflater.flush())
    return path


def run_command(main: Callable[[list[str]], int], args: list[str]) -> tuple[int, str, str]:
    """(exit code, stdout, stderr) of a command's `main`, argparse's exits included."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = main(args)
        except SystemExit as exc:  # argparse
            code = exc.code
    return code, out.getvalue(), err.getvalue()


__all__ = [
    "copy_bundle", "no_network", "recomputed", "records", "run_command", "showcase_built", "write_records",
    "zeros_gzip",
]
