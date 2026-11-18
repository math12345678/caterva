"""Read a sentence the way `caterva compose` reads it, and say what it chose, as JSON.

WHY THIS EXISTS
---------------
The adversarial round of 2026-11-11 put the same sentences to four front
ends. `caterva compose` and Caterva Studio read them with one reader
(`read_description`, then the ADR 0182 choosers); the HTTP API and the
TypeScript CLI each kept a reader of their own, and each misread a
different sentence:

- "chymotrypsin follows Michaelis-Menten kinetics" was trypsin on the API
  (a regular expression for "trypsin" matched inside "chymotrypsin");
- "hexokinase Michaelis-Menten kinetics" asked BRENDA for the Km of a
  substrate called "michaelis menten kinetics";
- "competitive inhibition of xanthine oxidase by allopurinol" carried the
  Km of allopurinol AS A SUBSTRATE as the model's Km;
- "HK2 with glucose" dropped the isoform and carried a hexokinase-I row;
- "lactate dehydrogenase with pyruvate in human" was refused on the TS
  CLI, where compose takes EC 1.1.1.27 because BRENDA's rows single it out.

Four readers of one sentence are four answers to it. This module is the
one entry point the other front ends call instead of reading the sentence
themselves: the reading is compose's own (`read_description`, the policy's
`read_subject`, `_choose_what_was_not_named`), imported, not copied, so a
sentence cannot be understood two ways.

WHAT IT RETURNS
---------------
`read(description, ...)` -> a dict (`--json` prints it):

    enzyme_text   the words read as the enzyme, or null
    ec            the EC number the enzyme was taken as, or null
    isoform       the isoform it names ("HK2"), or null
    organism      the organism named or chosen, or null
    substrate     the substrate named or chosen, or null
    inhibitor     the inhibitor named or chosen, or null
    rule          the grammar rule the description builds
                  ("michaelis_menten", "competitive_inhibition", ...)
    tables        the BRENDA tables the model reads ("km", "kcat", "ki")
    named         {"organism", "substrate", "inhibitor"}: what the sentence
                  or a flag NAMED, as opposed to chose
    choices       every automatic choice, in the order made, each
                  Choice.to_json() plus its "note" (the report's sentence)
    notes         every other sentence compose's report would carry
    refusal       why nothing can be looked up, or null

Flags (--subject, --organism, --substrate, --inhibitor, --isoform) win over
the sentence exactly as they do for compose. `--no-choose` reads only, with
no BRENDA fetch for a choice. Exit 0 when an enzyme was read, 3 when none
was or the reading was refused (the JSON says which), 2 on bad arguments.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence


def _choice_json(choice: Any) -> Dict[str, Any]:
    out = choice.to_json()
    out["note"] = choice.note()
    return out


def read(
    description: str,
    *,
    subject: Optional[str] = None,
    organism: Optional[str] = None,
    substrate: Optional[str] = None,
    inhibitor: Optional[str] = None,
    isoform: Optional[str] = None,
    choose: bool = True,
) -> Dict[str, Any]:
    """What compose makes of `description` with these flags (module doc)."""
    from caterva.compose.__main__ import (
        _choose_what_was_not_named,
        build_parser,
        compounds_from,
        read_description,
        read_subject,
    )
    from caterva.compose.grammar import UnrecognisedShape
    from caterva.compose.pipeline import compose

    argv: List[str] = [description]
    for flag, value in (("--subject", subject), ("--organism", organism), ("--substrate", substrate),
                        ("--inhibitor", inhibitor), ("--isoform", isoform)):
        if value:
            argv += [flag, value]
    args = build_parser().parse_args(argv)
    out: Dict[str, Any] = {
        "description": description, "enzyme_text": None, "ec": None, "isoform": None,
        "organism": None, "organism_text": None, "substrate": None, "inhibitor": None, "rule": None, "tables": [],
        "named": {}, "choices": [], "notes": [], "refusal": None,
    }
    try:
        reading = read_description(args, err=io.StringIO(), look_up_substrate=choose)
    except UnrecognisedShape as exc:
        out["refusal"] = str(exc)
        return out
    out["notes"] = list(reading.notes)
    from caterva.enzymes.sentence import read_sentence

    sentence = read_sentence(description, organism=organism)
    out["enzyme_text"] = reading.enzyme_text or getattr(sentence, "enzyme_text", None)
    out["organism_text"] = getattr(sentence, "organism_text", None) if sentence.organism else None
    try:
        model = compose(reading.description, subject=args.subject, organism=args.organism,
                        substrate=args.substrate, compounds=compounds_from(args))
    except UnrecognisedShape as exc:
        out["refusal"] = str(exc)
        return out
    out["rule"] = model.recognition.rule if hasattr(model, "recognition") else None
    out["tables"] = sorted({q.table for q in model.resolvable if q.table in ("km", "kcat", "ki")},
                           key=("km", "kcat", "ki").index)
    choices = list(reading.choices)
    if reading.name_refusal is not None:
        out["refusal"] = reading.refusal_note
    elif reading.unapplied and not args.subject:
        out["refusal"] = reading.unapplied[:1].upper() + reading.unapplied[1:] + "."
    elif args.subject:
        model, read_as, refusal, _ = read_subject(model, args)
        if read_as:
            out["notes"].append(read_as)
        if refusal is not None:
            out["refusal"] = refusal
        else:
            out["ec"] = model.ec_number
            # What the sentence or a flag named, before anything is chosen.
            out["named"] = {k: v for k, v in (
                ("organism", args.organism), ("substrate", args.substrate),
                ("inhibitor", compounds_from(args).get("@inhibitor"))) if v}
            if choose:
                if getattr(args, "isoform", None):
                    model = replace(model, isoform=args.isoform)
                model = replace(model, choices=tuple(choices))
                model, blocked = _choose_what_was_not_named(model, args)
                choices = list(getattr(model, "choices", ()) or ())
                if blocked is not None:
                    out["refusal"] = blocked
    out["isoform"] = getattr(args, "isoform", None) or None
    out["organism"] = args.organism or None
    out["substrate"] = args.substrate or None
    out["inhibitor"] = compounds_from(args).get("@inhibitor")
    out["choices"] = [_choice_json(c) for c in choices]
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m caterva.compose.read",
        description="Read a sentence as `caterva compose` reads it (the enzyme, its isoform, "
                    "organism, substrate, inhibitor and mechanism) and make the ADR 0182 "
                    "choices for what it leaves out, printed as JSON.")
    parser.add_argument("description", help="the sentence, e.g. \"hexokinase in human\"")
    parser.add_argument("--subject", help="the enzyme (name or EC number); wins over the sentence")
    parser.add_argument("--organism", help="the organism; wins over the sentence")
    parser.add_argument("--substrate", help="the substrate; wins over the sentence")
    parser.add_argument("--inhibitor", help="the inhibitor; wins over the sentence")
    parser.add_argument("--isoform", help="the isoform; wins over what a gene symbol implies")
    parser.add_argument("--no-choose", action="store_true",
                        help="read only: choose nothing and fetch nothing from BRENDA")
    parser.add_argument("--json", action="store_true", help="print the reading as JSON (the default)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = read(args.description, subject=args.subject, organism=args.organism,
                      substrate=args.substrate, inhibitor=args.inhibitor, isoform=args.isoform,
                      choose=not args.no_choose)
    except Exception as exc:  # noqa: BLE001 - said, as JSON, exit 1
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["ec"] and not result["refusal"] else 3


__all__ = ["build_parser", "main", "read"]


if __name__ == "__main__":
    sys.exit(main())
