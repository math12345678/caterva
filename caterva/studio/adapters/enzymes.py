"""The enzyme finder's two endpoints (owner: sci-kinetics, registered by compose).

    GET /api/enzymes/find?q=<text>&organism=<name>&limit=<n>   -> EnzymeFindResponse
    GET /api/enzymes/{ec}?organism=<name>                      -> EnzymeDetail

WHAT THEY CALL
--------------
`caterva.enzymes`, the offline finder over the IUBMB/ExPASy nomenclature, and
nothing else. `find` returns what `caterva enzyme QUERY --json` prints
(`caterva.enzymes.__main__.find_payload`, one function for both), so the
page's candidates are the command's candidates; this module adds to each
candidate only whether it is the finder's recommendation and the caution the
finder gives, and to the response the organism's label and the optional
UniProt fallback. `GET /api/enzymes/{ec}` is one entry of the same index and
`isozymes()` for the organism asked about.

SPEED AND SAFETY
----------------
The index is read once per process (`load_index` is cached) and a query
touches memory only: no file, no network. The answer to a query is kept
(the index never changes while the server runs), so typing and deleting
costs nothing the second time. `q` is at most 200 characters and may not
contain a control character; `organism` at most 100; `limit` 1 to 50. Text
from the request is only ever searched for: it is never used as a path, a
command or a pattern the standard library compiles. `{ec}` in the second
route must be a complete EC number to match the route at all.

THE UNIPROT FALLBACK
--------------------
When the finder finds nothing, and ONLY then, the response may carry
`fallback: {kind: "uniprot", ...}`: the EC numbers UniProt files reviewed
proteins of that name under, read through the same policy a run uses
(`resolve_enzyme_name` with `literature_uniprot_lookup`). It is asked only
when the capabilities say the network is reachable and the literature layer
is present, with a short timeout; otherwise `fallback` is null and
`fallback_unavailable` says why. Nothing is ever suggested that UniProt did
not return.
"""
from __future__ import annotations

import re
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Mapping, Optional, Tuple

from caterva.studio import contract
from caterva.studio.adapters import EndpointRequest

MAX_QUERY_CHARS = 200
MAX_ORGANISM_CHARS = 100
MAX_LIMIT = 50
#: The host the fallback asks, whose own status gates it (not an aggregate of every host).
UNIPROT_HOST = "rest.uniprot.org"
#: How long the UniProt fallback may take before it is reported as failed.
FALLBACK_TIMEOUT_S = 6.0
#: Answers kept: a query, an organism and a limit give one answer for the life of the process.
CACHE_SIZE = 256

_FIND_KEYS = ("q", "organism", "limit")
_DETAIL_KEYS = ("organism",)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

_cache: "OrderedDict[Tuple[str, str, int], Dict[str, Any]]" = OrderedDict()
_cache_lock = threading.Lock()


def _only(query: Mapping[str, str], allowed: Tuple[str, ...]) -> None:
    for key in query:
        if key not in allowed:
            raise contract.Malformed(f"{key} is not a query key of this route ({', '.join(allowed) or 'none'})",
                                     field=key)


def _text(query: Mapping[str, str], key: str, longest: int, *, required: bool = False) -> Optional[str]:
    value = query.get(key)
    if value is None:
        if required:
            raise contract.Malformed(f"{key} is required", field=key)
        return None
    if _CONTROL.search(value):
        raise contract.Malformed(f"{key} may not contain control characters", field=key)
    value = " ".join(value.split())
    if required and not value:
        raise contract.Malformed(f"{key} is empty", field=key)
    if len(value) > longest:
        raise contract.Malformed(f"{key} may be at most {longest} characters; this one is {len(value)}", field=key)
    return value or None


def _limit(query: Mapping[str, str]) -> int:
    from caterva.enzymes.finder import DEFAULT_LIMIT

    raw = query.get("limit")
    if raw is None:
        return DEFAULT_LIMIT
    if not re.fullmatch(r"[0-9]{1,3}", raw):
        raise contract.Malformed("limit is a whole number from 1 to %d" % MAX_LIMIT, field="limit")
    value = int(raw)
    if not 1 <= value <= MAX_LIMIT:
        raise contract.Malformed("limit is a whole number from 1 to %d" % MAX_LIMIT, field="limit")
    return value


def _candidate(item: Mapping[str, Any], recommended_ec: Optional[str], resolved_ec: Optional[str],
               cautions: List[str]) -> Dict[str, Any]:
    out = dict(item)
    out["recommended"] = recommended_ec is not None and item["ec"] == recommended_ec
    out["caution"] = " ".join(cautions) if cautions and item["ec"] == resolved_ec else None
    return out


def find_base(query: str, organism: Optional[str], limit: int) -> Dict[str, Any]:
    """The finder's answer for one question, without the uniprot fallback.

    Kept for the life of the process: the index is immutable."""
    from caterva.enzymes.__main__ import find_payload
    from caterva.enzymes.index import ORGANISM_SCOPE, organism_label

    key = (query.casefold(), (organism or "").casefold(), limit)
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit
    payload = find_payload(query, organism, limit)
    cautions = list(payload.get("cautions") or [])
    resolved_ec = payload.get("resolved_ec")
    recommended_ec = payload.get("recommended_ec")
    code = payload.get("organism_code")
    answer: Dict[str, Any] = {
        "query": payload["query"],
        "organism": organism,
        "organism_code": code,
        "organism_label": organism_label(code) if code else None,
        "release": payload["release"],
        "outcome": payload["outcome"],
        "resolved_ec": resolved_ec,
        "how": payload.get("how"),
        "cautions": cautions,
        "reason": payload.get("reason"),
        "recommended_ec": recommended_ec,
        "confirm_only": bool(payload.get("confirm_only")),
        "candidates_total": payload["candidates_total"],
        "candidates": [_candidate(c, recommended_ec, resolved_ec, cautions) for c in payload["candidates"]],
        "fallback": None,
    }
    if code in ORGANISM_SCOPE:
        answer["organism_scope"] = ORGANISM_SCOPE[code]
    with _cache_lock:
        _cache[key] = answer
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return answer


def uniprot_fallback(query: str, organism: Optional[str]) -> contract.EnzymeFallback:
    """What UniProt's protein-name search returns for `query`, read by the
    policy a run uses. Called only when the finder found nothing and the
    network is known to be reachable."""
    from caterva.enzymes.index import load_index
    from caterva.enzymes.policy import AMBIGUOUS, NameNotResolved, literature_uniprot_lookup, resolve_enzyme_name

    index = load_index()

    def named(ec: str) -> contract.UniprotSuggestion:
        entry = index.get(ec)
        return {"ec": ec, "name": entry.name if entry else None}

    try:
        resolution = resolve_enzyme_name(query, organism, uniprot=literature_uniprot_lookup(FALLBACK_TIMEOUT_S))
    except NameNotResolved as exc:
        if exc.kind == AMBIGUOUS and exc.candidates:
            return {"kind": "uniprot", "suggestions": [named(ec) for ec in exc.candidates],
                    "note": f"UniProt files reviewed proteins named {query!r} under {len(exc.candidates)} "
                            "EC numbers. These are different enzymes: choose the one you mean."}
        return {"kind": "uniprot", "suggestions": [], "note": str(exc)}
    return {"kind": "uniprot", "suggestions": [named(resolution.ec)],
            "note": "UniProt's protein-name search found exactly one EC number for this name. "
                    "Check it is the enzyme you mean."}


def _fallback(request: EndpointRequest, answer: Dict[str, Any], query: str,
              organism: Optional[str]) -> Dict[str, Any]:
    known = request.capabilities() if request.capabilities is not None else {}
    network = known.get("network") or {}
    literature = known.get("literature") or {}
    if known.get("offline"):
        why = "offline mode is on (Settings), so UniProt was not asked"
    elif (network.get("hosts") or {}).get(UNIPROT_HOST) is not True:
        why = ("UniProt is not known to be reachable (its own last outcome, from a lookup or a check; check "
               "the network from the status bar), so UniProt was not asked")
    elif not literature.get("available"):
        why = "the literature layer, which asks UniProt, is not in this installation"
    else:
        return dict(answer, fallback=uniprot_fallback(query, organism))
    return dict(answer, fallback_unavailable=why)


def find_enzymes(request: EndpointRequest) -> Dict[str, Any]:
    """GET /api/enzymes/find."""
    _only(request.query, _FIND_KEYS)
    query = _text(request.query, "q", MAX_QUERY_CHARS, required=True)
    organism = _text(request.query, "organism", MAX_ORGANISM_CHARS)
    limit = _limit(request.query)
    assert query is not None
    answer = find_base(query, organism, limit)
    if answer["outcome"] == "none":
        return _fallback(request, answer, query, organism)
    return answer


def _protein_view(protein: Any) -> Dict[str, Any]:
    """One listed protein with the gene symbol and names UniProt gives it, and whether the
    engine that reads papers' isoform names can match it."""
    from caterva.enzymes.isoforms import can_match, names_for

    label = protein.label
    return {
        "accession": protein.accession, "entry_name": protein.entry_name, "symbol": protein.symbol,
        "gene": protein.gene, "label": label,
        "names": list(names_for(protein.accession, protein.symbol))[:8],
        "engine_matches": can_match(label),
    }


def _replacements(index: Any, entry: Any) -> List[Dict[str, str]]:
    """The active enzymes a transferred number is now filed under, named, following chains."""
    found: List[Dict[str, str]] = []
    seen = {entry.ec}
    frontier = list(entry.superseded_by)
    for _ in range(5):
        following: List[str] = []
        for ec in frontier:
            if ec in seen:
                continue
            seen.add(ec)
            target = index.get(ec)
            if target is None:
                continue
            if target.status == "active":
                found.append({"ec": ec, "name": target.name})
            else:
                following.extend(target.superseded_by)
        frontier = following
    return found


def enzyme_detail(request: EndpointRequest) -> Dict[str, Any]:
    """GET /api/enzymes/{ec}."""
    from caterva.enzymes.finder import isozymes
    from caterva.enzymes.index import ORGANISM_SCOPE, load_index, organism_code, organism_label
    from caterva.enzymes.isozyme import BROAD_CLASS, isozyme_notice

    _only(request.query, _DETAIL_KEYS)
    organism = _text(request.query, "organism", MAX_ORGANISM_CHARS)
    ec = request.params["ec"]
    index = load_index()
    entry = index.get(ec)
    if entry is None:
        raise contract.NotFound(f"EC {ec} is not in the enzyme nomenclature (ExPASy ENZYME release "
                                f"{index.release}). Check the number.")
    found = isozymes(ec, organism)
    code = organism_code(organism)
    notice = isozyme_notice(ec, organism, None)
    name = entry.name
    name_note: Optional[str] = None
    replaced_by: List[Dict[str, str]] = []
    if entry.status == "transferred":
        replaced_by = _replacements(index, entry)
        name = "; ".join(r["name"] for r in replaced_by)
        name_note = (f"EC {ec} was transferred in the enzyme nomenclature and keeps no name of its own here; "
                     "the name shown is that of the enzyme" + ("s" if len(replaced_by) != 1 else "")
                     + " it is now filed under")
    elif entry.status == "deleted":
        name = "Deleted entry"
        name_note = (f"EC {ec} was deleted from the enzyme nomenclature and has no replacement; the nomenclature "
                     "keeps no name for a deleted number")
    return {
        "ec": ec,
        "name": name,
        "name_note": name_note,
        "replaced_by": replaced_by,
        "alternative_names": list(entry.alternative_names),
        "reaction": entry.reaction,
        "class_path": index.class_path(ec),
        "status": entry.status,
        "superseded_by": list(entry.superseded_by),
        "release": index.release,
        "isozymes": {
            "organism": found.organism,
            "organism_label": organism_label(code) if code else None,
            "count": found.count,
            "proteins": [_protein_view(p) for p in found.proteins],
            "organism_known": code is not None,
            "broad": found.count > BROAD_CLASS,
            "note": notice.text if notice is not None else None,
            "organism_scope": ORGANISM_SCOPE.get(code) if code else None,
            "filed_elsewhere": (notice.elsewhere_text or None) if notice is not None else None,
        },
    }


def register_endpoints(registry: Any, owner: str) -> None:
    """Supply the handlers of the two routes `owner` holds in routes.ROUTES."""
    registry.add_endpoint("find_enzymes", find_enzymes, owner=owner)
    registry.add_endpoint("enzyme_detail", enzyme_detail, owner=owner)


__all__ = ["CACHE_SIZE", "FALLBACK_TIMEOUT_S", "MAX_LIMIT", "MAX_ORGANISM_CHARS", "MAX_QUERY_CHARS",
           "enzyme_detail", "find_base", "find_enzymes", "register_endpoints", "uniprot_fallback"]
