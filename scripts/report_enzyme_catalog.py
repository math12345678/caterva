#!/usr/bin/env python3
"""What an enzyme reports, before you ask it for a value.

Reads a JSON payload on stdin, writes a JSON catalog on stdout.

    {"ecNumber": "1.1.1.27"}

WHAT PROBLEM THIS SOLVES
------------------------
Measured through the real resolver:

    substrate="lactate"    -> found, 10.73
    substrate="L-lactate"  -> found=False

BRENDA's label is `(S)-lactate`. A student's first query is a guess at three
things at once -- the substrate's exact label, an organism that has rows, and
whether the enzyme has that quantity at all -- and a wrong guess on any of
them is indistinguishable from "the literature has nothing".

ADR 0118 made the miss name the substrates. This is the other side: the
first command need not be a refusal.

ONE REQUEST
-----------
The Km, Ki and turnover tables are on the same BRENDA page, so this costs
the single fetch a single lookup costs. Lisa Jeske (BRENDA/DSMZ) asked that
tools be gentle with their servers; a discovery command that fetched three
times to answer one question would be a poor way to honour that.
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "Tests"))
# The repository root too. `export_citations.py` shipped in HEAD with only
# the first of these two lines and died on its import line (ADR 0107).
sys.path.insert(0, str(REPO_ROOT))

from brenda_client import fetch_brenda_html  # noqa: E402
from enzyme_catalog import catalog  # noqa: E402
from enzyme_lookup import fetch_ec_numbers_by_name  # noqa: E402


def _fail(message: str) -> int:
    print(json.dumps({"ok": False, "error": message}))
    return 1


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        return _fail(f"Invalid JSON payload: {exc}")

    ec_number = payload.get("ecNumber")
    enzyme_name = payload.get("enzyme")

    if not ec_number and enzyme_name:
        # A NAME IS NOT AN ENZYME.
        #
        # "lactate dehydrogenase" is EC 1.1.1.27 (L-lactate dehydrogenase)
        # AND EC 1.1.1.28 (D-lactate dehydrogenase) -- different enzymes on
        # different stereoisomers. Measured: `parse_ec_number_search` took
        # `results[0]` then `ec_numbers[0]` and returned "1.1.1.27" with
        # nothing saying a choice had been made.
        #
        # An EC number is not a parameter; it is the identity of the protein
        # everything downstream is about. A wrong Km is a wrong number, and
        # a wrong EC is a citation for a different enzyme. So this refuses
        # and names the candidates, exactly as the cross-species and variant
        # refusals do -- a refusal that cannot say what it refused leaves
        # the choice unexercisable.
        try:
            candidates = fetch_ec_numbers_by_name(str(enzyme_name), None)
        except Exception as exc:  # noqa: BLE001 - reported, never a trace
            return _fail(f"Could not look up {enzyme_name!r} in UniProt: {exc}")

        if not candidates:
            return _fail(
                f"UniProt indexes no reviewed enzyme named {enzyme_name!r} "
                "with an EC number. Check the spelling, or pass the EC number "
                "directly if you know it."
            )
        if len(candidates) > 1:
            return _fail(
                f"{enzyme_name!r} names more than one enzyme: "
                + ", ".join(candidates)
                + ". These are different proteins, so Terrium will not pick "
                "one for you — a wrong EC number is a citation for the wrong "
                "enzyme, not merely a wrong value. Re-run with the one you "
                "meant."
            )
        ec_number = candidates[0]

    if not ec_number:
        return _fail(
            "No 'ecNumber' or 'enzyme' given. This command reports what one "
            "enzyme's BRENDA page holds, so it needs to know which page."
        )

    try:
        result = catalog(str(ec_number), fetch_brenda_html)
    except Exception as exc:  # noqa: BLE001 - reported as data, never a trace
        # A discovery command that dies with a stack trace has told the
        # reader less than one that says the page could not be read.
        return _fail(f"Could not read BRENDA's page for EC {ec_number}: {exc}")

    print(
        json.dumps(
            {
                "ok": True,
                "catalog": result.model_dump(),
                "organisms": result.organisms,
                "usable": result.usable,
                # The sentence is built in Python, where it was argued
                # over, so the terminal and any other surface cannot drift
                # apart on it (ADR 0003).
                "summary": result.summary(),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
