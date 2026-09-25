#!/usr/bin/env python3
"""Real constants, from the literature, with the citation beside each one.

WHY THIS EXISTS
---------------
This is the thing Terrium is for, and until now you could not type it.

`scripts/report_lab.py` has produced literature-backed documents since
ADR 0149: it asks UniProt which enzyme a name means, refuses to pick when
the name is ambiguous, reads BRENDA, ranks the rows by how well evidenced
they are, carries the disagreement between papers through the model, and
prints the citation for every number it used. It reads a JSON payload on
stdin. That interface is correct for the TypeScript CLI that calls it and
unusable for a person: the first thing anyone wants -- "what is the Km of
this enzyme, and who measured it" -- required hand-writing a JSON object
and knowing the six keys it needs.

So this is that same code behind flags a person can type. It builds the
payload and hands it to `report_lab`; it does not re-implement any of the
resolution, the ranking or the document. A second rendering path would
drift from the first and the drift would surface in front of the reader.

    python3 scripts/cite.py --ec 1.1.1.27 --organism "Homo sapiens" \
        --substrate pyruvate --quantity km

    python3 scripts/cite.py --enzyme "acetylcholinesterase" \
        --organism "Homo sapiens" --substrate acetylcholine

A name that means more than one enzyme is refused with every candidate
named, because a wrong EC number is a citation for the wrong protein.

OFFLINE
-------
`--fixture PATH` reads a saved BRENDA page instead of the network, which is
how the test suite and `make demo` run with no account and no connection.
The document then says, in its own words, that no search was run.

WHAT IT DOES NOT DO
-------------------
Compose a mechanism. That is `terrium compose`, which today builds
structure with the motif library's placeholder values and does not run this
search (ADR 0178 records the gap and what wiring it would take).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: BRENDA tables `report_lab` can read. `quantity` is the model's name for
#: the symbol; the table is where the measurement lives.
QUANTITIES = ("km", "kcat", "ki")


def build_payload(args: argparse.Namespace) -> dict:
    """The payload `report_lab` expects, from the flags a person typed."""
    parameters = [
        {"name": q, "substrate": args.substrate, "quantity": q}
        for q in args.quantity
    ]
    supplied = []
    for name, value, unit in (("s0", args.s0, args.concentration_unit),
                              ("vmax", args.vmax, f"{args.concentration_unit}/s")):
        supplied.append({
            "name": name, "value": value, "unit": unit,
            "basis": args.basis,
        })
    payload = {
        "title": args.title or _default_title(args),
        "question": args.question,
        "organism": args.organism,
        "parameters": parameters,
        "supplied": supplied,
        "vmax": args.vmax,
        "s0": args.s0,
    }
    if args.ec:
        payload["ec"] = args.ec
    if args.enzyme:
        payload["enzyme"] = args.enzyme
    if args.fixture:
        payload["fixture"] = args.fixture
    if args.seed is not None:
        payload["seed"] = args.seed
    return payload


def _default_title(args: argparse.Namespace) -> str:
    who = args.enzyme or f"EC {args.ec}"
    return f"{who} in {args.organism}" if args.organism else str(who)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="terrium-cite",
        description=__doc__.splitlines()[0],
        epilog=(
            "Examples:\n"
            "  cite.py --ec 1.1.1.27 --organism 'Homo sapiens' --substrate pyruvate\n"
            "  cite.py --enzyme acetylcholinesterase --organism 'Homo sapiens' \\\n"
            "          --substrate acetylcholine --quantity km --quantity kcat\n"
            "  cite.py --ec 1.1.1.27 --substrate pyruvate --fixture Tests/fixtures/brenda_ldh_fixture.html\n"
            "\n"
            "Exit codes: 0 a document was produced, 2 the request was not well\n"
            "formed, 3 Terrium refused and said why (an ambiguous enzyme name,\n"
            "a quantity nothing measured).\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--ec", help="EC number, e.g. 1.1.1.27 (exact, never guessed)")
    who.add_argument("--enzyme", help="enzyme name; refused if it means more than one")
    parser.add_argument("--organism", help="e.g. 'Homo sapiens'. Omit to accept whatever the resolver's documented default is")
    parser.add_argument("--substrate", required=True, help="the substrate the constant belongs to, e.g. pyruvate")
    parser.add_argument("--quantity", action="append", choices=QUANTITIES,
                        help="which constant to resolve; repeatable (default: km)")
    parser.add_argument("--s0", type=float, default=10.0, help="starting substrate concentration -- YOURS, not the literature's (default 10)")
    parser.add_argument("--vmax", type=float, default=0.25, help="Vmax for the run -- YOURS, not the literature's (default 0.25)")
    parser.add_argument("--concentration-unit", default="mM", help="unit for --s0 (default mM)")
    parser.add_argument("--basis", default="chosen for this run", help="how you justify the supplied values; it is printed beside them")
    parser.add_argument("--title", help="document title")
    parser.add_argument("--question", default="What are the measured constants, and where did each come from?")
    parser.add_argument("--fixture", help="a saved BRENDA page, instead of the network")
    parser.add_argument("--seed", type=int, help="seed for the ensemble across values the literature disagrees about; without it no band is produced, deliberately")
    parser.add_argument("--json", action="store_true", help="print report_lab's raw JSON rather than the document")
    args = parser.parse_args(argv)

    if not args.quantity:
        args.quantity = ["km"]

    # The same reading `terrium compose` applies: "human" is Homo sapiens,
    # and saying so beats a search for an organism nobody spells that way.
    sys.path.insert(0, str(ROOT))
    from Terium.compose.organisms import normalise_organism

    args.organism, organism_note = normalise_organism(args.organism)
    if organism_note:
        print(organism_note, file=sys.stderr)

    payload = build_payload(args)
    report_lab = ROOT / "scripts" / "report_lab.py"
    if not report_lab.is_file():
        print(f"{report_lab} is missing; this needs the source checkout, not the app folder.", file=sys.stderr)
        return 2

    run = subprocess.run(
        [sys.executable, str(report_lab)],
        input=json.dumps(payload), capture_output=True, text=True, cwd=str(ROOT),
    )
    if run.returncode != 0 and not run.stdout.strip():
        sys.stderr.write(run.stderr)
        return run.returncode or 1

    try:
        result = json.loads(run.stdout)
    except json.JSONDecodeError:
        sys.stdout.write(run.stdout)
        sys.stderr.write(run.stderr)
        return run.returncode or 1

    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 3

    if not result.get("ok"):
        # A refusal is the product working, not failing: an ambiguous name
        # is a citation for the wrong protein waiting to happen.
        print(f"Not produced.\n\n{result.get('error', 'no reason given')}", file=sys.stderr)
        return 3

    print(result["markdown"], end="")
    sourced = result.get("sourced") or []
    supplied = result.get("supplied") or []
    if sourced or supplied:
        print(
            f"\n<!-- {len(sourced)} constant(s) from the literature: "
            f"{', '.join(sourced) or 'none'}; "
            f"{len(supplied)} supplied by you: {', '.join(supplied) or 'none'} -->"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
