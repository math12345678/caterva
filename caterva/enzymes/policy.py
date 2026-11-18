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
   would accept one. Nothing is picked. A gene symbol, lab abbreviation or
   curated alias that the symbol table maps to ONE enzyme in the organism
   is not several: it resolves with its isoform and, when no organism was
   given and the name implies one, the organism, each said in `notes`
   ("HK2" is hexokinase, isoform HK2, Homo sapiens; ADR 0182). One several
   enzymes go by (HK, SDH, AK, NOS, PEPCK with no organism) is this case.
4. Nothing, or only typo suggestions: a spelling with one close enzyme name
   is read as it and said ("acetylcholinestrase"); otherwise ask the
   optional UniProt lookups: the protein-name search (a protein name that is
   not an enzyme name), then, for a name shaped like a gene symbol, the
   gene-name search in human unless an organism was given ("CYP2B6"). One
   complete EC number from either is returned; for a cytochrome P450 gene
   with several, EC 1.14.14.1, where BRENDA files P450 kinetics, is taken
   and said; several otherwise are refused as in step 3; none is refused
   with the did-you-mean suggestions the nomenclature had.

A trailing point-mutation tag ("IDH1 R132H") is set aside before the name is
read, and the note says the constants are taken only from BRENDA rows
measuring that mutant (`caterva compose` sends it to the resolver as
`mutation`), never from the wild-type enzyme's.

A caller with no UniProt lookup (the installed app has no literature layer)
gets steps 1 to 3 and a refusal for 4. An EC number is read by the same
function: a transferred number resolves to its replacement and says so, a
deleted one is refused.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
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
        recommended: Optional[str] = None, rerun: str = "--subject {ec}", confirm_only: bool = False,
    ):
        super().__init__(message)
        self.confirm_only = confirm_only
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
    #: The protein of the EC number the name was (HK2, CYP2B6), for
    #: `--isoform`; None when the name is the whole enzyme.
    isoform: Optional[str] = None
    #: The organism (binomial) assumed because none was given and the name
    #: implies one (Homo sapiens for HK2); None when none was assumed. A
    #: caller fills `--organism` from it only when no organism was given.
    organism: Optional[str] = None
    #: Sentences saying what was assumed or read (the organism, the
    #: isoform, a spelling, a mutation set aside). Each automatic choice is one.
    read_notes: Tuple[str, ...] = ()

    def notes(self, query: str, *, isoform_applied: bool = False, organism_applied: bool = False) -> List[str]:
        """Sentences for a report: what the query was read as, then what was
        assumed, then cautions.

        Two of the reading's sentences are claims about the SEARCH ("the
        constants are taken from BRENDA rows that name HK2", "so Homo
        sapiens was searched"), and they are true only for a caller that
        put the isoform and organism into its search. `caterva compose`
        does (read_subject) and says so with `isoform_applied` /
        `organism_applied`. Every other caller -- `caterva bind --ec`,
        `rates --ec`, `fep --ec`, `structure --subject` -- takes only the
        EC number, and printed both claims anyway: `rates --ec CYP2B6` said
        Homo sapiens was searched and the constants came from CYP2B6 rows
        while it searched every organism and every P450 (review of ADR
        0182, 2026-11-11). For those callers each claim is replaced by what
        the name implies and the flag that would apply it.
        """
        if self.ec == query.strip() and not self.cautions and not self.read_notes:
            return []
        typed = query.strip()
        head = f"Read {typed!r} as EC {self.ec}"
        if self.name:
            head += f" ({self.name})"
        out = [f"{head}: {self.how}."]
        for note in self.read_notes:
            if self.isoform and is_isoform_claim(note) and not isoform_applied:
                note = (f"{typed!r} names the isoform {self.isoform} of EC {self.ec}, but this search was not "
                        f"narrowed to it: rows of every isoform were read (pass --isoform {self.isoform} where "
                        "the command takes one).")
            elif self.organism and is_organism_claim(note) and not organism_applied:
                note = (f"{typed!r} names an enzyme of {self.organism}, but no organism was given and this search "
                        f"was not narrowed to one (pass --organism \"{self.organism}\" to search it).")
            if note not in out:
                out.append(note)
        out.extend(c for c in self.cautions if c not in out[0])
        return out

    def to_json(self) -> Dict[str, object]:
        return {"ec": self.ec, "name": self.name, "how": self.how, "source": self.source,
                "isoform": self.isoform, "organism": self.organism, "notes": list(self.read_notes),
                "cautions": list(self.cautions)}


#: How the reading's two claims about the search begin (symbols._assumed_note,
#: finder._reading_notes, _from_gene below): see `NameResolution.notes`.
_ORGANISM_CLAIM = "No organism was given"
_ISOFORM_CLAIM = re.compile(r"^Read .+ as the isoform .+; the constants are taken from BRENDA rows")


def is_organism_claim(note: str) -> bool:
    """True for the sentence saying an organism nobody gave was searched."""
    return note.startswith(_ORGANISM_CLAIM)


def is_isoform_claim(note: str) -> bool:
    """True for the sentence saying the constants come from rows naming the isoform."""
    return bool(_ISOFORM_CLAIM.match(note))


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
        confirm_only=ambiguous.confirm_only,
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
        "confirm_only": exc.confirm_only,
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


def literature_uniprot_gene_lookup(timeout: Optional[float] = None) -> Optional[Callable[..., Sequence[str]]]:
    """UniProt's gene-name search from the literature layer, or None.

    A function `(symbol, taxon_id) -> EC strings`; `taxon_id` None searches
    every organism. Absent from an installed wheel, like the protein-name
    lookup above.
    """
    from caterva.checkout import LiteratureLayerUnavailable, literature_module

    try:
        lookup = literature_module("enzyme_lookup")
    except LiteratureLayerUnavailable:
        return None
    if not hasattr(lookup, "fetch_ec_numbers_by_gene"):
        return None
    if timeout is None:
        return lambda symbol, taxon: lookup.fetch_ec_numbers_by_gene(symbol, taxon)
    return lambda symbol, taxon: lookup.fetch_ec_numbers_by_gene(symbol, taxon, timeout=timeout)


#: NCBI taxon ids of the organisms a gene-name search can be narrowed to.
TAXON_IDS = {
    "HUMAN": "9606", "MOUSE": "10090", "RAT": "10116", "YEAST": "559292", "ECOLI": "83333",
    "BOVIN": "9913", "PIG": "9823", "CHICK": "9031", "ARATH": "3702", "BACSU": "224308",
    "DROME": "7227", "CAEEL": "6239", "RABIT": "9986", "SCHPO": "284812", "DANRE": "7955",
    "XENLA": "8355", "MYCTU": "83332", "HORSE": "9796", "SHEEP": "9940", "CAVPO": "10141",
}

#: A gene symbol shape worth asking UniProt's gene field about: no space, a
#: letter first, at most 20 characters ("CYP2B6", "Hk2", "folA").
_SYMBOL_SHAPE = re.compile(r"^[A-Za-z][A-Za-z0-9\-]{1,19}$")
#: A point mutation written after a name: R132H, V600E, G12D.
_MUTATION = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]\d{1,4}[ACDEFGHIKLMNPQRSTVWY*]$")


def split_mutation(text: str) -> Tuple[str, Tuple[str, ...]]:
    """(the name, the point-mutation tags typed after it): "IDH1 R132H" is ("IDH1", ("R132H",))."""
    words = text.split()
    tags: List[str] = []
    while len(words) > 1 and _MUTATION.match(words[-1]):
        tags.insert(0, words.pop())
    return " ".join(words), tuple(tags)


def mutation_note(name: str, tags: Sequence[str]) -> str:
    return (f"{name} {'/'.join(tags)} is a mutant: each constant is taken only from BRENDA rows measuring "
            f"{'that mutant' if len(tags) == 1 else 'those mutations together'}, never from the wild-type "
            f"enzyme's, and a constant with no such row is a placeholder that says so.")


def _from_gene(
    name: str, organism: Optional[str], gene: Callable[..., Sequence[str]], rerun: str,
) -> Optional[NameResolution]:
    """The UniProt gene-name search, after the protein-name search found nothing.

    Human unless an organism was given, and said. Accepted only when it
    yields ONE complete EC number, or several that include EC 1.14.14.1 for
    a cytochrome P450 gene. None when it yields nothing or cannot be asked;
    several are refused with the candidates named."""
    from .index import ORGANISMS, organism_code
    from .symbols import P450_EC

    if not _SYMBOL_SHAPE.match(name):
        return None
    code = organism_code(organism)
    taxon = TAXON_IDS.get(code) if code else TAXON_IDS["HUMAN"]
    if code and taxon is None:
        return None
    try:
        listed = [str(e) for e in gene(name, taxon)]
    except Exception:  # noqa: BLE001 - the protein-name answer stands
        return None
    complete: List[str] = []
    for ec in listed:
        if _COMPLETE_EC.match(ec) and ec not in complete:
            complete.append(ec)
    notes: List[str] = []
    assumed = None
    if not code:
        assumed = ORGANISMS["HUMAN"][0]
        notes.append(f"No organism was given; {name} was looked up as a human gene symbol, so Homo sapiens "
                     "was searched (pass --organism to change it).")
    if len(complete) > 1 and P450_EC in complete and name.lower().startswith("cyp"):
        notes.append(f"UniProt files {name} under several EC numbers ({', '.join(complete)}); EC {P450_EC} "
                     "(unspecific monooxygenase) was read because BRENDA files cytochrome P450 kinetics there.")
        complete = [P450_EC]
    if not complete:
        return None
    if len(complete) > 1:
        candidates = [found[0] for found in (find(ec, organism, limit=1) for ec in complete) if found]
        ambiguous = Ambiguous(
            query=name, candidates=tuple(candidates), recommended=None, confirm_only=True,
            reason=f"UniProt files the gene {name!r} under {len(complete)} EC numbers",
            organism=code, release=load_index().release)
        if candidates:
            raise _refuse(ambiguous, rerun, AMBIGUOUS)
        return None
    entry = load_index().get(complete[0])
    # The gene is one protein of the EC number. Carried as the isoform only
    # when the EC number is several proteins in the organism (or the index
    # cannot say), as SymbolTable.read does: for the one protein of its EC
    # number, `--isoform` would only drop rows that name it another way.
    counts = entry.counts if entry is not None else {}
    isoform: Optional[str] = name if entry is None or counts.get(code or "HUMAN", 0) != 1 else None
    if isoform:
        notes.append(f"Read {name!r} as the isoform {isoform} of EC {complete[0]}; the constants are taken from "
                     "BRENDA rows that name it where there are any (pass --isoform to change it).")
    return NameResolution(
        ec=complete[0], source="uniprot", name=entry.name if entry else "", isoform=isoform,
        organism=assumed, read_notes=tuple(notes),
        how=(f"the enzyme nomenclature has no enzyme of that name, and UniProt files the reviewed entry of the "
             f"{'human ' if not code else ''}gene {name} under exactly this EC number"))


def resolve_enzyme_name(
    name: str,
    organism: Optional[str] = None,
    *,
    uniprot: Optional[Callable[[str], Sequence[str]]] = None,
    rerun: str = "--subject {ec}",
    allow_unlisted_ec: bool = False,
    gene: Optional[Callable[..., Sequence[str]]] = None,
) -> NameResolution:
    """The enzyme `name` identifies, or `NameNotResolved` naming the choices.

    `name` is an enzyme name, an EC number, or a transferred or deleted EC
    number. `organism` is anything `organism_code` reads and ranks the
    candidates and names their proteins; it is never assumed. `uniprot` is
    the optional step-4 lookup: a function from a name to EC strings.
    `rerun` ends a refusal, with `{ec}` for the enzyme. `allow_unlisted_ec`
    lets a well-formed EC number the nomenclature does not hold through
    unchanged, for a caller whose own database may know a number this
    release does not. `gene` is the optional UniProt gene-name lookup,
    `(symbol, taxon_id) -> EC strings`; when `uniprot` is given and `gene`
    is not, the literature layer's is used when present.
    """
    text = " ".join(str(name).split())
    bare, mutations = split_mutation(text)
    if mutations:
        found = resolve_enzyme_name(bare, organism, uniprot=uniprot, rerun=rerun,
                                    allow_unlisted_ec=allow_unlisted_ec, gene=gene)
        return replace(found, read_notes=found.read_notes + (mutation_note(bare, mutations),))
    result = resolve(text, organism)
    if isinstance(result, Resolved):
        return NameResolution(
            ec=result.ec, how=result.how, cautions=result.cautions, source="nomenclature",
            name=result.candidate.name if result.candidate else "", isoform=result.isoform,
            organism=result.organism, read_notes=result.notes)

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
    try:
        return _from_uniprot(text, organism, uniprot, suggestions, rerun)
    except NameNotResolved as exc:
        if exc.kind not in (NONE_FOUND, SUGGESTIONS):
            raise
        if gene is None:
            gene = literature_uniprot_gene_lookup()
        if gene is not None:
            found = _from_gene(text, organism, gene, rerun)
            if found is not None:
                return found
        raise


__all__ = [
    "NameNotResolved", "NameResolution", "resolve_enzyme_name", "literature_uniprot_lookup",
    "literature_uniprot_gene_lookup", "refusal_view", "split_mutation", "mutation_note",
    "AMBIGUOUS", "SUGGESTIONS", "NONE_FOUND", "LOOKUP_FAILED", "DELETED_OR_UNKNOWN",
]
