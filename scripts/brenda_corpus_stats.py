#!/usr/bin/env python3
"""How much of BRENDA actually reports the conditions a Km was measured under?

    python scripts/brenda_corpus_stats.py path/to/brenda_km_download.tsv
    python scripts/brenda_corpus_stats.py path/to/download.tsv --json

WHY THIS EXISTS
---------------
Terrium has been repeating a figure: "roughly three quarters of our default
parameters are unverified under STRENDA." That number came from this
project's own small hand-assembled default set. It was never a basis for a
claim about the literature, and it has been quoted in outreach as though it
were one.

Professor Barbara Bakker's reply is what made the distinction matter. She
scores parameters partly on "completeness of assay description", which
presumes you know what the distribution of completeness actually looks like.
Lisa Jeske's recommendation to use the bulk downloads is what finally made
it answerable: her download has no organism column and so cannot feed the
resolver, but it can answer a question about the corpus that no per-enzyme
lookup ever could.

So this reports the real figure, with its denominator, from a file the user
downloaded themselves.

WHAT IT REFUSES TO DO
---------------------
It does not download anything. BRENDA data is CC BY 4.0 and freely
available, and Jeske asked that tools be gentle with DSMZ's servers; a
statistics script that silently pulls a multi-megabyte export every time
someone is curious is not gentle. The user fetches the file once and points
this at it.

It does not report a percentage without the counts behind it. A bare "62%"
invites exactly the reuse that produced the wrong number in the first place.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "Tests"))

from brenda_bulk import parse_rows, read_bytes, strenda_completeness  # noqa: E402


def _percent(part: int, whole: int) -> str:
    """A percentage that refuses to exist without a denominator."""
    if whole == 0:
        return "n/a (no rows)"
    return f"{(part / whole) * 100:.1f}%"


def analyse(path: pathlib.Path) -> dict:
    text = read_bytes(path.read_bytes())
    rows, report = parse_rows(text)
    stats = strenda_completeness(rows)

    ec_numbers = sorted({row.ec_number for row in rows})
    return {
        "file": str(path),
        "parse": {
            "rows": report.rows,
            "additionalInformation": report.additional_information,
            "malformed": len(report.malformed),
            "linesConsidered": report.total_lines_considered,
            # Reported even when zero. A reader has to be able to check the
            # denominator, and a truncated download is a fact about the file
            # rather than a detail to swallow.
            "malformedExamples": [
                {"line": number, "excerpt": excerpt}
                for number, excerpt in report.malformed[:5]
            ],
        },
        "ecNumbers": {"distinct": len(ec_numbers), "first": ec_numbers[:3]},
        "strenda": stats,
        "caveats": [
            "This download carries no organism column, so none of these rows "
            "can answer an organism-specific question. See Tests/brenda_bulk.py.",
            "'additional information' rows are excluded from the STRENDA "
            "denominator: they describe kinetics in prose and never had a "
            "value for conditions to accompany.",
            "A condition is counted as reported only when it appears in the "
            "commentary. BRENDA sometimes states that the publication did not "
            "report one, which is a fact about the paper and is counted "
            "separately as explicitlyUnreported.",
        ],
    }


def render(result: dict) -> str:
    stats = result["strenda"]
    parse = result["parse"]
    measured = stats["measured_rows"]

    lines = [
        f"BRENDA corpus: {result['file']}",
        "",
        f"  rows parsed            {parse['rows']}",
        f"  prose-only rows        {parse['additionalInformation']} "
        f"(excluded from the figures below)",
        f"  malformed / truncated  {parse['malformed']}",
        f"  distinct EC numbers    {result['ecNumbers']['distinct']}",
        "",
        f"STRENDA reporting, across {measured} measured value(s)",
        "",
        f"  both pH and temperature  {stats['both_conditions']:>6}  "
        f"{_percent(stats['both_conditions'], measured)}",
        f"  exactly one              {stats['one_condition']:>6}  "
        f"{_percent(stats['one_condition'], measured)}",
        f"  neither                  {stats['neither_condition']:>6}  "
        f"{_percent(stats['neither_condition'], measured)}",
        "",
        f"  of which BRENDA states the publication did not report one: "
        f"{stats['explicitly_unreported']}",
        "",
    ]

    for caveat in result["caveats"]:
        lines.append(f"  - {caveat}")

    if parse["malformedExamples"]:
        lines.append("")
        lines.append("  Malformed lines (first few):")
        for entry in parse["malformedExamples"]:
            lines.append(f"    line {entry['line']}: {entry['excerpt']!r}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report STRENDA reporting completeness across a BRENDA bulk "
            "download. Does not download anything -- fetch the file first."
        )
    )
    parser.add_argument("path", type=pathlib.Path, help="a BRENDA bulk .tsv")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    if not args.path.is_file():
        # Distinct from "the file is empty". A missing file is a mistake in
        # the invocation; an empty one is a fact about the download.
        print(
            json.dumps({"ok": False, "error": f"No such file: {args.path}"})
            if args.json
            else f"No such file: {args.path}\n\n"
            "Download a bulk export first -- see the URLs in docs/EXPERT_FEEDBACK.md, "
            "section 1d. Nothing is fetched automatically, on purpose.",
            file=sys.stderr,
        )
        return 1

    result = analyse(args.path)

    # NOT ONE CASE. TWO, AND THEY NEED DIFFERENT ANSWERS.
    #
    # This branch used to cover both, printing "all prose-only or malformed"
    # and returning 0. The `or` in that sentence is the tell: the code could
    # not say which had happened, while the comment beside it said the reader
    # needs to know. Both also exited 0, so
    #
    #     scientific corpus notes.txt --json   ->  {"ok": true, ...}, exit 0
    #
    # reported a file that is not a BRENDA download at all as a successful
    # analysis with every figure zero. A script sees a pass.
    if result["parse"]["rows"] == 0 and result["parse"]["linesConsidered"] > 0:
        # NOTHING matched the nine-field schema. Not a threshold and not a
        # judgement about quality -- zero of N lines parsed is categorical.
        # Almost always the wrong file was passed, which is a mistake in the
        # invocation like "No such file" above, and exits the same way.
        message = (
            f"{args.path} does not have the shape of a BRENDA bulk download: "
            f"none of its {result['parse']['linesConsidered']} line(s) matched "
            "the expected nine tab-separated fields.\n\n"
            "No figures are reported, because nothing was read. Check that this "
            "is the .tsv from a BRENDA bulk export rather than, say, a CSV or a "
            "saved web page."
        )
        print(
            json.dumps({"ok": False, "error": "unrecognised-format", **result})
            if args.json
            else message,
            file=sys.stderr if not args.json else sys.stdout,
        )
        return 1

    if result["strenda"]["measured_rows"] == 0:
        # A genuine download that carries no measured values -- every row is
        # 'additional information', BRENDA's prose-only form. That is a real
        # finding about the download, so it exits 2 rather than 1: the
        # analysis ran, and this is its answer. Same distinction `resolve`
        # draws between "the literature has nothing" and "the lookup failed".
        message = (
            f"{args.path} parsed, and contains no measured values "
            f"({result['parse']['rows']} row(s), all 'additional information' — "
            "BRENDA's prose-only form). No STRENDA figures can be computed "
            "from it."
        )
        print(json.dumps({"ok": False, **result}) if args.json else message)
        return 2

    print(json.dumps({"ok": True, **result}, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
