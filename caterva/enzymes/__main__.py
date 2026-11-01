"""`caterva enzyme`: which enzyme does this name mean?

    caterva enzyme "pyruvate kinase"
    caterva enzyme "lactate dehydrogenase" --organism human
    caterva enzyme 1.1.1.-  --limit 5
    caterva enzyme "hexokinse" --json

Looks the name (or EC number) up in the IUBMB enzyme nomenclature that ships
with Caterva, offline, and prints every enzyme that matches with the reason
it matched, its reaction, its class, the proteins it lists for the organism,
and the `caterva compose` line that would use it. It never picks for you when
a name is several enzymes; it says which one it would recommend, and why.

Exit codes follow the rest of Caterva: 0 the name resolved to one enzyme, or
candidates were listed to choose from; 2 a malformed command line; 3 nothing
matched (any did-you-mean suggestions are still printed); 1 a crash.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from typing import Any, Dict, List, Optional, Sequence

from .finder import (
    DEFAULT_LIMIT, TIER_TYPO, Candidate, Resolved, find, resolve,
)
from .index import load_index, organism_code, organism_label


def build_parser(prog: str = "caterva enzyme") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Find the enzyme a name means. Looks the name or EC number up in the IUBMB enzyme "
            "nomenclature (offline) and lists every match with why it matched, its reaction, "
            "its class, its proteins in your organism and the compose command to use it."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            f"  {prog} 'pyruvate kinase'\n"
            f"  {prog} 'lactate dehydrogenase' --organism human\n"
            f"  {prog} 1.1.1.-\n"
            f"  {prog} 'hexokinse' --json\n"
            "\nExit codes: 0 resolved or candidates listed, 2 malformed command, "
            "3 nothing matched (suggestions still printed), 1 a crash."
        ),
    )
    parser.add_argument(
        "query",
        help="an enzyme name (pyruvate kinase), an EC number (1.1.1.27, EC 1.1.1.27) or a partial one (1.1.1.-)",
    )
    parser.add_argument(
        "--organism",
        help="human, mouse, rat, yeast, E. coli, ... (or a Latin name): ranks enzymes with a protein "
             "in this organism first and lists those proteins",
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"how many candidates to list (default {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="print the result as JSON instead of text",
    )
    return parser


def compose_line(ec: str, organism: Optional[str]) -> str:
    """The command that would use this enzyme, with the substrate left to fill in."""
    line = f'caterva compose "Michaelis Menten" --subject {ec}'
    if organism:
        line += f" --organism {shlex.quote(organism)}"
    return line + " --substrate <substrate>"


def _outcome(result: Any) -> str:
    """resolved, ambiguous (a choice), partial (only fragments of longer
    names or protein symbols), suggestions (close spellings only), or none."""
    if isinstance(result, Resolved):
        return "resolved"
    if not result.candidates:
        return "none"
    if result.suggestions_only:
        return "suggestions" if all(c.tier == TIER_TYPO for c in result.candidates) else "partial"
    return "ambiguous"


def _card(rank: int, candidate: Candidate, organism: Optional[str], recommended: bool) -> List[str]:
    head = f"{rank:>2}. EC {candidate.ec}  {candidate.name}" if candidate.name else f"{rank:>2}. EC {candidate.ec}"
    if recommended:
        head += "   <- recommended"
    lines = [head, f"      why: {candidate.why}"]
    if candidate.status != "active":
        lines.append(f"      status: {candidate.status}"
                     + ("; now " + ", ".join(f"EC {e}" for e in candidate.superseded_by)
                        if candidate.superseded_by else ""))
    if candidate.reaction:
        lines.append(f"      reaction: {candidate.reaction}")
    if candidate.class_path:
        lines.append(f"      class: {candidate.class_path}")
    if candidate.organism:
        label = organism_label(candidate.organism)
        if candidate.organism_proteins:
            symbols = ", ".join(f"{p.label} ({p.accession})" for p in candidate.organism_proteins)
            lines.append(f"      {label} proteins ({candidate.organism_protein_count}): {symbols}")
        elif candidate.organism_protein_count:
            lines.append(f"      {label} proteins: {candidate.organism_protein_count} UniProt entries "
                         "(the index keeps counts, not names, for this organism)")
        else:
            lines.append(f"      {label} proteins: none listed")
    if candidate.status == "active":
        lines.append(f"      use: {compose_line(candidate.ec, organism)}")
    return lines


def _text(query: str, organism: Optional[str], result: Any, shown: Sequence[Candidate], total: int) -> str:
    index = load_index()
    code = organism_code(organism)
    context = f"ExPASy ENZYME release {index.release}" + (f", {organism_label(code)}" if code else "")
    out: List[str] = [f"Enzyme finder: {query!r} ({context})", ""]
    if organism and code is None:
        out += [f"Note: {organism!r} is not an organism the index knows, so nothing is ranked by organism.", ""]
    outcome = _outcome(result)
    recommended_ec = None
    if isinstance(result, Resolved):
        out.append(f"Resolved: EC {result.ec}"
                   + (f" ({result.candidate.name})" if result.candidate and result.candidate.name else "")
                   + f" -- {result.how}.")
        for caution in result.cautions:
            out.append(f"Caution: {caution}")
    elif outcome == "ambiguous":
        out.append(f"Not resolved: {result.reason.rstrip('.')}. Caterva will not pick one for you: a wrong EC number is a "
                   "citation for the wrong enzyme, not merely a wrong value.")
        if result.recommended is not None:
            recommended_ec = result.recommended.ec
            out.append(f"Recommended: EC {recommended_ec} ({result.recommended.name}), the only enzyme matched "
                       "that has a protein from the organism you gave. Confirm it with --subject "
                       f"{recommended_ec}.")
    elif outcome in ("suggestions", "partial"):
        out.append(f"Not resolved: {result.reason.rstrip('.')}. Did you mean one of these?")
    else:
        out.append(f"Nothing matched: {result.reason}")
    if shown:
        out.append("")
    for rank, candidate in enumerate(shown, 1):
        out += _card(rank, candidate, organism, candidate.ec == recommended_ec)
        out.append("")
    if total > len(shown):
        out.append(f"{total - len(shown)} more; raise --limit to see them.")
    if outcome == "none":
        out.append("Check the spelling, or give an EC number. `caterva enzyme 1.1.1.-` lists a class.")
    return "\n".join(out).rstrip() + "\n"


def with_recommendation(shown: Sequence[Candidate], ranked: Sequence[Candidate], result: Any) -> List[Candidate]:
    """`shown`, plus the recommended enzyme when the limit cut it off, so what the
    page says about the recommendation can be seen on the page."""
    out = list(shown)
    recommended = getattr(result, "recommended", None)
    if recommended is not None and all(c.ec != recommended.ec for c in out):
        out.append(next(c for c in ranked if c.ec == recommended.ec))
    return out


def _json(query: str, organism: Optional[str], result: Any, shown: Sequence[Candidate], total: int) -> Dict[str, Any]:
    index = load_index()
    code = organism_code(organism)
    payload: Dict[str, Any] = {
        "query": query,
        "organism": organism,
        "organism_code": code,
        "release": index.release,
        "outcome": _outcome(result),
        "candidates_total": total,
        "candidates": [dict(c.to_dict(), compose=compose_line(c.ec, organism)) for c in shown],
    }
    if isinstance(result, Resolved):
        payload.update(resolved_ec=result.ec, how=result.how, cautions=list(result.cautions))
    else:
        payload.update(
            reason=result.reason,
            recommended_ec=result.recommended.ec if result.recommended else None,
            confirm_only=bool(getattr(result, "confirm_only", False)),
        )
    return payload


def find_payload(query: str, organism: Optional[str] = None, limit: int = DEFAULT_LIMIT) -> Dict[str, Any]:
    """What `caterva enzyme QUERY --json` prints, as a dictionary.

    One function for the command and for Caterva Studio's
    `GET /api/enzymes/find`, so the page's candidates are the command's.
    """
    query = " ".join(query.split())
    result = resolve(query, organism)
    ranked = find(query, organism, limit=None)
    return _json(query, organism, result, with_recommendation(ranked[:limit], ranked, result), len(ranked))


def main(argv: Optional[Sequence[str]] = None, prog: str = "caterva enzyme") -> int:
    args = build_parser(prog).parse_args(argv)
    if args.limit < 1:
        print(f"{prog}: --limit must be at least 1", file=sys.stderr)
        return 2
    query = " ".join(args.query.split())
    if not query:
        print(f"{prog}: the query is empty", file=sys.stderr)
        return 2
    result = resolve(query, args.organism)
    ranked = find(query, args.organism, limit=None)
    shown = with_recommendation(ranked[: args.limit], ranked, result)
    if args.json:
        print(json.dumps(_json(query, args.organism, result, shown, len(ranked)), indent=2))
    else:
        print(_text(query, args.organism, result, shown, len(ranked)), end="")
    return 3 if _outcome(result) in ("none", "suggestions") else 0  # a partial match lists real names


def console_main() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
