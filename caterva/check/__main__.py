"""`caterva verify DIR`: re-check a claims bundle offline, sharing no code with what wrote it.

    caterva verify ./claims
    caterva verify ./claims --json

One line per check (`ok  identity  claim:sha256:...  reaction_Km`), a
summary, and exit 0 when every check passed, 3 when one failed (stderr says
`Refused:` and names the first failing claim), 2 when the directory is not a
bundle this checker can read (nothing in it was checked, which is not the
same as a check failing), 1 a crash. `--json` prints the Report instead.

The imports here are relative (`from .verify import ...`) and not
`caterva.check.verify`, because the independence guard refuses any import
that names `caterva`: the one way to be sure this package reaches nothing
of the producer is to let it name nothing outside itself (ADR 0179).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

from .verify import BundleMalformed, Check, Report, verify_bundle

if TYPE_CHECKING:
    from collections.abc import Sequence

EXIT_OK, EXIT_CRASH, EXIT_MALFORMED, EXIT_REFUSED = 0, 1, 2, 3

#: Width of the check-name column: "unit arithmetic" is the longest name.
_NAME_WIDTH = 15


def build_parser(prog: str = "caterva verify") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Re-check a claims bundle written by `caterva compose --claims DIR` against "
            "the bytes it kept, offline, with a checker that imports nothing of the code "
            "that wrote it. Every row and claim id is recomputed, every certified span is "
            "re-read, every cited row is re-found in its page, a stated unit factor is "
            "redone in decimal arithmetic, and what cannot be checked is listed as such."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            f"  {prog} ./claims\n"
            f"  {prog} ./claims --json\n"
            "\n"
            "Exit codes: 0 every check passed, 3 a check failed (stderr names the first "
            "failing claim), 2 the directory is not a bundle this checker can read, 1 a crash.\n"
            "A bundle that passes is re-checkable: its derivations and stated reasons hold "
            "against the pinned bytes. Whether the biology is right is not checked."
        ),
    )
    parser.add_argument("directory", help="the bundle directory (manifest.json, claims.jsonl, rows.jsonl, snapshots.jsonl, snapshots/)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON instead of one line per check")
    return parser


def _line(check: Check) -> str:
    status = "ok" if check.ok else "FAIL"
    columns = [status, check.name.ljust(_NAME_WIDTH)]
    if check.claim is not None:
        columns.append(check.claim)
    columns.append(check.detail)
    return "  ".join(columns)


def render(report: Report) -> list[str]:
    """The lines `caterva verify` prints: one per check, the not-checked line, the summary."""
    ran = [c for c in report.checks if c.name != "not checked"]
    skipped = [c for c in report.checks if c.name == "not checked"]
    lines = [_line(c) for c in ran]
    if skipped:
        lines.append("not checked: " + "; ".join(c.detail for c in skipped))
    failed = [c for c in ran if not c.ok]
    verdict = (
        "Re-checkable: every derivation and stated reason holds against the pinned bytes."
        if not failed else
        f"{len(failed)} check(s) did not hold; the first is named on stderr."
    )
    lines.append(f"{len(ran)} checks: {len(ran) - len(failed)} ok, {len(failed)} failed; {len(skipped)} not checked. {verdict}")
    return lines


def refusal(report: Report) -> str:
    """The stderr line for exit 3: the first failing check and the claim it names."""
    first = report.failed()[0]
    about = first.claim if first.claim is not None else first.detail.split(":", 1)[0]
    return f"Refused: {first.name} did not hold for {about}: {first.detail}"


def main(argv: Sequence[str] | None = None, prog: str | None = None) -> int:
    parser = build_parser(prog) if prog else build_parser()
    args = parser.parse_args(argv)
    try:
        report = verify_bundle(args.directory)
    except BundleMalformed as exc:
        print(f"Not a claims bundle this checker can read: {exc}", file=sys.stderr)
        return EXIT_MALFORMED
    if args.json:
        print(json.dumps(report.to_dict(), indent=1, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(render(report)))
    if report.ok:
        return EXIT_OK
    print(refusal(report), file=sys.stderr)
    return EXIT_REFUSED


def console_main() -> int:
    return main()


__all__ = ["EXIT_CRASH", "EXIT_MALFORMED", "EXIT_OK", "EXIT_REFUSED", "build_parser", "main", "refusal", "render"]

if __name__ == "__main__":
    sys.exit(main())
