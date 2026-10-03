"""The one policy for turning an enzyme name into an EC number.

WHY THIS IS ONE FUNCTION
------------------------
Six places turn a name into an EC number: `caterva compose --subject`,
`caterva structure --subject`, the catalog and report commands, the
literature-layer helper `ec_number_for_name` and the runner the API server
spawns. A policy copied into each drifts, and this repository has found that
defect in a plausibility table, a reliability score and a request validator.
So the decision lives here, and every caller supplies only what differs
between them: an optional UniProt lookup, and the wording of the flag to
re-run with.

THE POLICY
----------
1. Look the name up in the enzyme nomenclature (finder.py). Offline.
2. One enzyme at the best tier: return it, with how it was identified and
   anything the reader should know (a transferred number, an enzyme with no
   protein from the organism asked about).
3. Several: refuse, naming each candidate with its enzyme name and the
   proteins it lists for the organism, and end with the exact flag that
   would accept one. Nothing is picked.
4. Nothing, or only typo suggestions: ask the optional UniProt lookup, which
   covers a protein name that is not an enzyme name. One complete EC number
   from UniProt is returned; several are refused as in step 3; none is
   refused with the did-you-mean suggestions the nomenclature had.

A caller with no UniProt lookup (the installed app has no literature layer)
gets steps 1 to 3 and a refusal for 4. An EC number is read by the same
function: a transferred number resolves to its replacement and says so, a
deleted one is refused.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .finder import (
    Ambiguous, Candidate, Resolved, find, read_ec, recommend, refusal_text, resolve,
)
from .index import load_index

#: A complete EC number, as UniProt writes it. `1.1.98.-` is a class.
_COMPLETE_EC = re.compile(r"^\d+\.\d+\.\d+\.(?:n?\d+)$")

#: Why a name was not resolved.
AMBIGUOUS = "ambiguous"
SUGGESTIONS = "suggestions"
NONE_FOUND = "none"
LOOKUP_FAILED = "lookup_failed"
DELETED_OR_UNKNOWN = "unknown_ec"


class NameNotResolved(ValueError):
    """A name did not identify exactly one enzyme.

    `candidates` is the list of EC numbers, for callers that only want
    those; `named` is the same candidates as dictionaries with the enzyme
    name, the reason each matched and the organism's proteins (see
    `Candidate.to_dict`), for callers that render them; `kind` says which
    way it failed.
    """

    def __init__(
        self, message: str, candidates: Optional[Sequence[str]] = None,
        named: Optional[Sequence[Dict[str, object]]] = None, kind: str = NONE_FOUND,
        recommended: Optional[str] = None, rerun: str = "--subject {ec}",
    ):
        super().__init__(message)
        self.recommended = recommended
        self.rerun = rerun
        self.candidates: List[str] = list(candidates or [])
        self.named: List[Dict[str, object]] = [dict(n) for n in (named or [])]
        self.kind = kind


@dataclass(frozen=True)
class NameResolution:
    """The enzyme a name identified, and how."""

    ec: str
    #: In words: which name matched how, or that a number was transferred.
    how: str
    #: Things to read that do not change the answer.
    cautions: Tuple[str, ...] = ()
    #: `nomenclature` or `uniprot`.
    source: str = "nomenclature"
    name: str = ""

    def notes(self, query: str) -> List[str]:
        """Sentences for a report: what the query was read as, then cautions."""
        if self.ec == query.strip() and not self.cautions:
            return []
        head = f"Read {query.strip()!r} as EC {self.ec}"
        if self.name:
            head += f" ({self.name})"
        out = [f"{head}: {self.how}."]
        out.extend(c for c in self.cautions if c not in out[0])
        return out


def _named(candidates: Sequence[Candidate]) -> List[Dict[str, object]]:
    return [dict(c.to_dict(), label=c.label()) for c in candidates]


def _refuse(ambiguous: Ambiguous, rerun: str, kind: str) -> NameNotResolved:
    return NameNotResolved(
        refusal_text(ambiguous, rerun),
        [c.ec for c in ambiguous.candidates],
        _named(ambiguous.candidates),
        kind,
        recommended=ambiguous.recommended.ec if ambiguous.recommended is not None else None,
        rerun=rerun,
    )


def refusal_view(exc: NameNotResolved) -> Dict[str, object]:
    """A refusal as plain data, for a caller that renders it (Caterva Studio).

    Everything is read from the exception the policy raised; nothing is
    decided here. `named_candidates` are the finder's candidates with their
    enzyme names, reasons and organism proteins, never a bare list of EC
    numbers; `recommended` is the EC number the finder recommends or None;
    `rerun_flag` is the flag, with `{ec}`, that accepts one."""
    return {
        "kind": exc.kind,
        "message": str(exc),
        "named_candidates": [dict(n) for n in exc.named],
        "candidates": list(exc.candidates),
        "recommended": exc.recommended,
        "rerun_flag": exc.rerun,
    }


def _from_uniprot(
    name: str, organism: Optional[str], uniprot: Callable[[str], Sequence[str]],
    suggestions: Optional[Ambiguous], rerun: str,
) -> NameResolution:
    """Step 4: the nomenclature found nothing, so ask UniProt, once."""
    try:
        listed = [str(e) for e in uniprot(name)]
    except NameNotResolved:
        raise
    except Exception as exc:  # noqa: BLE001 - reported, never a traceback
        text = f"Could not look up {name!r} in UniProt: {exc}"
        if suggestions is not None and suggestions.candidates:
            text += "\n" + refusal_text(suggestions, rerun)
        raise NameNotResolved(
            text, [c.ec for c in (suggestions.candidates if suggestions else ())],
            _named(suggestions.candidates) if suggestions else (), LOOKUP_FAILED) from exc
    complete: List[str] = []
    for ec in listed:
        if _COMPLETE_EC.match(ec) and ec not in complete:
            complete.append(ec)

    if len(complete) == 1:
        entry = load_index().get(complete[0])
        return NameResolution(
            ec=complete[0], source="uniprot", name=entry.name if entry else "",
            how=("the enzyme nomenclature has no enzyme of that name, and UniProt's protein-name search "
                 "found exactly one EC number for it"))
    if complete:
        candidates = []
        for ec in complete:
            found = find(ec, organism, limit=1)
            if found:
                candidates.append(found[0])
        ambiguous = Ambiguous(
            query=name, candidates=tuple(candidates), recommended=recommend(candidates),
            reason=f"{name!r} names {len(complete)} enzymes in UniProt", organism=candidates[0].organism if candidates else None,
            release=load_index().release)
        if candidates:
            raise _refuse(ambiguous, rerun, AMBIGUOUS)
        raise NameNotResolved(
            f"{name!r} names more than one enzyme in UniProt: " + ", ".join(f"EC {e}" for e in complete)
            + ". These are different enzymes, so Caterva will not pick one for you. Re-run with "
            + rerun.format(ec=complete[0]),
            complete, [], AMBIGUOUS, rerun=rerun)
    if suggestions is not None and suggestions.candidates:
        raise _refuse(suggestions, rerun, SUGGESTIONS)
    raise NameNotResolved(
        f"No enzyme named {name!r} is in the enzyme nomenclature, and UniProt indexes no reviewed enzyme "
        "with that name and an EC number. Check the spelling, or pass the EC number directly if you know it.",
        [], [], NONE_FOUND)


def literature_uniprot_lookup(timeout: Optional[float] = None) -> Optional[Callable[[str], Sequence[str]]]:
    """UniProt's protein-name search from the literature layer, or None.

    The layer lives in the checkout's `Tests/` and is absent from an
    installed wheel and from the app folder, where the nomenclature alone
    resolves names. Every command that resolves a name asks for the lookup
    here, so none of them carries its own idea of when it is available.
    `timeout` (seconds) shortens the lookup for a caller that must answer
    quickly; None keeps the literature layer's own.
    """
    from caterva.checkout import LiteratureLayerUnavailable, literature_module

    try:
        lookup = literature_module("enzyme_lookup")
    except LiteratureLayerUnavailable:
        return None
    if timeout is None:
        return lambda name: lookup.fetch_ec_numbers_by_name(name, None)
    return lambda name: lookup.fetch_ec_numbers_by_name(name, None, timeout=timeout)


def resolve_enzyme_name(
    name: str,
    organism: Optional[str] = None,
    *,
    uniprot: Optional[Callable[[str], Sequence[str]]] = None,
    rerun: str = "--subject {ec}",
    allow_unlisted_ec: bool = False,
) -> NameResolution:
    """The enzyme `name` identifies, or `NameNotResolved` naming the choices.

    `name` is an enzyme name, an EC number, or a transferred or deleted EC
    number. `organism` is anything `organism_code` reads and ranks the
    candidates and names their proteins; it is never assumed. `uniprot` is
    the optional step-4 lookup: a function from a name to EC strings.
    `rerun` ends a refusal, with `{ec}` for the enzyme. `allow_unlisted_ec`
    lets a well-formed EC number the nomenclature does not hold through
    unchanged, for a caller whose own database may know a number this
    release does not.
    """
    text = " ".join(str(name).split())
    result = resolve(text, organism)
    if isinstance(result, Resolved):
        return NameResolution(
            ec=result.ec, how=result.how, cautions=result.cautions, source="nomenclature",
            name=result.candidate.name if result.candidate else "")

    parts = read_ec(text)
    if parts is not None:
        if len(parts) == 4 and not result.candidates and "is not in the enzyme nomenclature" in result.reason:
            if allow_unlisted_ec:
                return NameResolution(
                    ec=".".join(parts), how="the number is not in the enzyme nomenclature release the finder holds, "
                    "so it is used as given", cautions=(), source="given")
            raise NameNotResolved(result.reason, [], [], DELETED_OR_UNKNOWN)
        if result.candidates:
            raise _refuse(result, rerun, AMBIGUOUS)
        raise NameNotResolved(result.reason[0].upper() + result.reason[1:], [], [], DELETED_OR_UNKNOWN)

    if result.candidates and not result.suggestions_only:
        raise _refuse(result, rerun, AMBIGUOUS)

    suggestions = result if result.candidates else None
    if uniprot is None:
        if suggestions is not None:
            raise _refuse(suggestions, rerun, SUGGESTIONS)
        raise NameNotResolved(
            f"No enzyme named {text!r} is in the enzyme nomenclature (ExPASy ENZYME release {result.release}). "
            "Check the spelling, or pass the EC number directly if you know it.", [], [], NONE_FOUND)
    return _from_uniprot(text, organism, uniprot, suggestions, rerun)


__all__ = [
    "NameNotResolved", "NameResolution", "resolve_enzyme_name", "literature_uniprot_lookup", "refusal_view",
    "AMBIGUOUS", "SUGGESTIONS", "NONE_FOUND", "LOOKUP_FAILED", "DELETED_OR_UNKNOWN",
]
