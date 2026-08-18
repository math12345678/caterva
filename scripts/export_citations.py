#!/usr/bin/env python3
"""Emit a bibliography for every source behind a run.

Reads a JSON payload on stdin, writes BibTeX or RIS on stdout.

The counterpart to export_annotated_model.py, and the reachable end of
Tests/citation_export.py -- which was built and then callable from nowhere.

    {"format": "bibtex" | "ris",
     "cited": [{"parameter": "km", "citationSource": "BRENDA",
                "referenceId": "740253", "url": "...", "title": "...",
                "value": 2.5, "unit": "mM", "organism": "Homo sapiens"}]}

An empty `cited` list is NOT an error. "This run had no literature-backed
values" is a fact, and the exporters say so in the document rather than
writing an empty file that is indistinguishable from a failed export.
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "Tests"))
# The REPO ROOT as well, not only `Tests/`.
#
# `citation_export` imports `Terium.core.data_sources` (the shared source
# table, ADR 0079) and `Terium` is a package at the root, so with only
# `Tests/` on the path this script died on its import line:
#
#     ModuleNotFoundError: No module named 'Terium'
#
# It had been failing since that import landed, in HEAD, unnoticed —
# because every test imports `citation_export` directly, where pytest's
# rootdir is already on `sys.path`. The library was covered and the way a
# user actually reaches it was not. This file's own docstring calls itself
# "the reachable end of Tests/citation_export.py -- which was built and
# then callable from nowhere", and it had quietly become unreachable
# again. `test_the_script_runs_end_to_end` now enters through this door.
sys.path.insert(0, str(REPO_ROOT))

from citation import Citation  # noqa: E402
from citation_export import CitedParameter, to_bibtex, to_ris  # noqa: E402

FORMATS = {"bibtex": to_bibtex, "ris": to_ris}


def _fail(message: str) -> int:
    print(json.dumps({"ok": False, "error": message}))
    return 1


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        return _fail(f"Invalid JSON payload: {exc}")

    fmt = payload.get("format")
    if fmt not in FORMATS:
        return _fail(
            f"Unknown citation format {fmt!r}. Known: {', '.join(sorted(FORMATS))}."
        )

    cited: list[CitedParameter] = []
    for entry in payload.get("cited") or []:
        source = entry.get("citationSource")
        if not source:
            # A citation with no source is not a citation. Refusing the
            # whole export is right: emitting the others would produce a
            # bibliography that is silently short, and the caller would
            # have no way to know which value lost its record.
            return _fail(
                f"Entry for {entry.get('parameter', '(unnamed)')!r} has no "
                "citation source. A bibliography missing an entry with "
                "nothing said about it is worse than a refused export."
            )
        cited.append(
            CitedParameter(
                parameter=str(entry.get("parameter", "value")),
                citation=Citation(
                    source=str(source),
                    reference_id=entry.get("referenceId"),
                    url=entry.get("url"),
                    title=entry.get("title"),
                    organism=entry.get("organism"),
                ),
                value=entry.get("value"),
                unit=entry.get("unit"),
                organism=entry.get("organism"),
            )
        )

    document = FORMATS[fmt](cited)
    print(json.dumps({"ok": True, "document": document, "entries": len(cited)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
