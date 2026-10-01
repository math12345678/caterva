"""Kind `constants`: `scripts/cite.py`, real constants with their citations (owner: sci-kinetics).

WHAT IT CALLS
    scripts/cite.py's `build_parser`, `read_organism` (the organism read as
    `caterva compose` reads it) and `build_payload`, then
    `run_report_lab(payload)`: scripts/report_lab.py's `run_payload`, in
    this process. report_lab resolves each quantity with
    fallback_logic.resolve_kinetic_value (BRENDA, UniProt, NCBI Taxonomy,
    PubMed) and returns the document's markdown, the lists sourced /
    supplied / derived / refusals / disagreements / defensible, and now
    `resolved`: each KineticResult the document was built from. Every
    ConstantRow is read from that object, never parsed out of the markdown.
    The document is `cite.document(result)`, the text `cite.py` prints.

WHY IN-PROCESS
    cite.py runs report_lab as `[sys.executable, "scripts/report_lab.py"]`.
    In a frozen app `sys.executable` is the app, not Python, so the studio
    calls the same function the subprocess would have run.

WHERE IT RUNS
    scripts/ and the literature layer (Tests/) are in the repository, not
    in the wheel or the app folder (ADR 0177). This kind is therefore
    available from a source checkout only, and `unavailable()` says which
    of the two is missing, in the words cite.py and caterva.checkout use.

WHAT EACH NUMBER IS
    A resolved constant is `measured`: report_lab's citation text (the
    words its document prints: "BRENDA ref 641068"), the citation's own
    registry, reference and link, the row's organism, its assay pH,
    temperature and buffer, the conditions BRENDA says the paper did not
    report, and the row's commentary verbatim. The rows the evidence could
    not rank below it (`selection_tie`), or the other organisms' rows when
    the asked organism had none (`cross_species_candidates`), are its
    alternatives, each measured. The values a person supplies (s0, vmax)
    are `chosen`, by the user when the request names them and by cite.py's
    stated default otherwise, with the basis the document prints beside
    them.

WHAT IS REFUSED
    --json and --fixture are never produced: the result is the structured
    form, and a saved page in place of BRENDA belongs to the test suite.
    A refusal (an ambiguous enzyme name, with every candidate named) is
    exit 3 with cite.py's own words.
"""
from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, List, Mapping, Optional

from caterva.studio import contract
from caterva.studio.adapters import AdapterOutcome, AdapterSpec, RunContext, cli_parser

KIND = "constants"
PROG = "python3 scripts/cite.py"
QUANTITIES = ("km", "kcat", "ki")
_STRINGS = ("ec", "enzyme", "organism", "substrate", "concentration_unit", "basis", "title", "question")
_NUMBERS = ("s0", "vmax")
_KEYS = frozenset(_STRINGS + _NUMBERS + ("quantities", "seed"))

#: The repository root, where scripts/cite.py lives in a source checkout.
REPO_ROOT = Path(__file__).resolve().parents[3]
CITE = REPO_ROOT / "scripts" / "cite.py"


@functools.lru_cache(maxsize=1)
def cite_module() -> ModuleType:
    """scripts/cite.py, imported by path: scripts/ is not a package."""
    module = sys.modules.get("caterva_cite")
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location("caterva_cite", CITE)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"{CITE} is missing; this needs the source checkout, not the app folder.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["caterva_cite"] = module
    return module


@functools.lru_cache(maxsize=1)
def _missing() -> Optional[str]:
    if not CITE.is_file():
        return f"{CITE} is missing; this needs the source checkout, not the app folder."
    cite = cite_module()
    if not cite.REPORT_LAB.is_file():
        return cite.MISSING
    from caterva.checkout import LiteratureLayerUnavailable, literature_module

    try:
        literature_module("fallback_logic")
    except LiteratureLayerUnavailable as exc:
        return str(exc)
    return None


def unavailable() -> Optional[str]:
    return _missing()


# ---------------------------------------------------------------------------
# Request -> argv
# ---------------------------------------------------------------------------


def argv_of(request: Mapping[str, Any]) -> List[str]:
    """One flag per key; `quantities` -> repeated --quantity; exactly one of
    ec and enzyme (cite.py's own parser enforces it). Never --json or
    --fixture."""
    if not isinstance(request, Mapping):
        raise contract.Malformed("a constants request is a JSON object")
    for key in request:
        if key not in _KEYS:
            raise contract.Malformed(f"{key} is not a constants request key", field=key)
    out: List[str] = []
    for key in _STRINGS:
        value = request.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise contract.Malformed(f"{key} must be a non-empty string", field=key)
        out.append(f"--{key.replace('_', '-')}={value}")
    for key in _NUMBERS:
        value = request.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise contract.Malformed(f"{key} must be a number", field=key)
        out.append(f"--{key}={float(value)!r}")
    seed = request.get("seed")
    if seed is not None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise contract.Malformed("seed must be an integer", field="seed")
        out.append(f"--seed={seed}")
    quantities = request.get("quantities")
    if quantities is not None:
        if not isinstance(quantities, list) or not all(isinstance(q, str) for q in quantities):
            raise contract.Malformed(f"quantities is a list of {', '.join(QUANTITIES)}",
                                     field="quantities")
        out += [f"--quantity={q}" for q in quantities]
    return out


def _parsed(argv: List[str]) -> Any:
    return cli_parser(cite_module().build_parser, PROG).parse_args(argv)


def argv(request: Mapping[str, Any]) -> List[str]:
    out = argv_of(request)
    _parsed(out)
    return out


def describe(request: Mapping[str, Any]) -> str:
    who = request.get("enzyme") or f"EC {request.get('ec')}"
    quantities = ", ".join(request.get("quantities") or ["km"])
    parts = [f"{quantities} of {who}", str(request.get("substrate") or "")]
    if request.get("organism"):
        parts.append(str(request["organism"]))
    return ", ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def run(request: Mapping[str, Any], ctx: RunContext) -> AdapterOutcome:
    cite = cite_module()
    args = _parsed(argv_of(request))
    organism_note = cite.read_organism(args)
    if organism_note:
        ctx.progress.log(organism_note)
    payload = cite.build_payload(args)

    ctx.progress.check_cancelled()
    who = args.enzyme or f"EC {args.ec}"
    ctx.progress.stage("resolve", f"Resolving {', '.join(args.quantity)} of {who} for "
                                  f"{args.substrate} from BRENDA", None)
    result = cite.run_report_lab(payload)
    ctx.progress.check_cancelled()
    if not result.get("ok"):
        reason = cite.refusal(result)
        return AdapterOutcome(exit_code=3, result=None, summary=str(result.get("error", "")).split("\n")[0],
                              refusal=reason)

    ctx.progress.stage("document", "Writing the document with a citation beside each number", None)
    out = constants_result(request, args, payload, result, organism_note)
    sourced = result.get("sourced") or []
    summary = (f"{len(sourced)} constant(s) from the literature: {', '.join(sourced)}"
               if sourced else "no constant came from the literature")
    return AdapterOutcome(exit_code=0, result=out, summary=summary)


def constants_result(request: Mapping[str, Any], args: Any, payload: Mapping[str, Any],
                     result: Mapping[str, Any], organism_note: Optional[str]) -> contract.ConstantsResult:
    cite = cite_module()
    resolved: Mapping[str, Any] = result.get("resolved") or {}
    rows = [constant_row(entry["name"], entry.get("quantity", "km"), resolved.get(entry["name"]))
            for entry in payload.get("parameters") or []]
    supplied = []
    for entry in payload.get("supplied") or []:
        given = request.get(entry["name"]) is not None
        supplied.append(contract.sourced(
            entry["value"], str(entry["unit"]),
            contract.chosen("user" if given else "default",
                            entry.get("basis") if given else
                            f"the default of cite.py --{entry['name']}; {entry.get('basis')}"),
            ident=str(entry["name"])))
    return {
        "document_markdown": cite.document(result),
        "constants": rows,
        "supplied": supplied,
        "sourced": list(result.get("sourced") or []),
        "derived": list(result.get("derived") or []),
        "refusals": list(result.get("refusals") or []),
        "disagreements": list(result.get("disagreements") or []),
        "defensible": bool(result.get("defensible")),
        "organism_note": organism_note,
    }


def _citation_text(citation: Optional[Mapping[str, Any]]) -> str:
    """report_lab's `_citation_of`, over the dumped citation: the words its
    document prints beside the value."""
    lab = sys.modules.get("caterva_report_lab")
    if lab is None:
        raise RuntimeError("report_lab is not loaded; the citation text is its words")
    holder = SimpleNamespace(citation=None if citation is None else SimpleNamespace(**citation))
    return lab._citation_of(holder)


def constant_row(name: str, quantity: str, raw: Optional[Mapping[str, Any]]) -> contract.ConstantRow:
    """One resolved quantity, read from the resolver's KineticResult."""
    if raw is None:
        raise ValueError(f"report_lab returned no KineticResult for {name!r}")
    value = None
    if raw.get("found") and raw.get("value") is not None:
        value = measured(raw, ident=name, label=name)
    alternatives: List[contract.SourcedValue] = []
    tie = raw.get("selection_tie") or {}
    for i, candidate in enumerate(tie.get("candidates") or []):
        if not candidate.get("selected"):
            alternatives.append(candidate_value(candidate, f"{name}:tied:{i}", "selection_tie",
                                                cross_species=False))
    for i, candidate in enumerate(raw.get("cross_species_candidates") or []):
        alternatives.append(candidate_value(candidate, f"{name}:other_organism:{i}",
                                            "cross_species_candidates", cross_species=True))
    return {
        "name": name,
        "quantity": quantity,
        "found": bool(raw.get("found")),
        "source": str(raw.get("source")),
        "value": value,
        "alternatives": alternatives,
        "organisms_available": list(raw.get("cross_species_organisms_available") or []),
        "isoforms_available": list(raw.get("isoforms_available") or []),
        "modes_available": list(raw.get("modes_available") or []),
        "variants_available": list(raw.get("variant_candidates_available") or []),
        "raw": dict(raw),
    }


def measured(raw: Mapping[str, Any], *, ident: str, label: str) -> contract.SourcedValue:
    citation = raw.get("citation") or None
    cite_obj: contract.Citation = {"text": _citation_text(citation), "via": str(raw.get("source"))}
    if citation:
        cite_obj.update({"registry": citation.get("source"), "reference_id": citation.get("reference_id"),
                         "url": citation.get("url"), "title": citation.get("title")})
    provenance: contract.Provenance = {
        "kind": "measured", "citation": cite_obj, "organism": raw.get("organism"),
        "cross_species": bool(raw.get("cross_species_flag")),
        "conditions": {"ph": raw.get("assay_ph"), "temperature_c": raw.get("assay_temperature_c"),
                       "buffer": raw.get("assay_buffer"),
                       "unreported": [str(x) for x in raw.get("assay_unreported") or []]},
        "commentary": raw.get("commentary"), "scope": [], "chosen_because": None, "spread": None,
    }
    return contract.sourced(raw["value"], str(raw.get("unit") or ""), provenance, ident=ident, label=label)


def candidate_value(candidate: Mapping[str, Any], ident: str, via: str, *,
                    cross_species: bool) -> contract.SourcedValue:
    """A row the resolver ranked and did not carry (a TiedCandidate)."""
    reference = candidate.get("reference_id")
    citation: contract.Citation = {"text": f"BRENDA ref {reference}" if reference else "BRENDA",
                                   "registry": "BRENDA", "reference_id": reference, "via": via}
    provenance: contract.Provenance = {
        "kind": "measured", "citation": citation, "organism": candidate.get("organism"),
        "cross_species": cross_species,
        "conditions": {"ph": None, "temperature_c": None, "buffer": None, "unreported": []},
        "commentary": candidate.get("conditions"), "scope": [], "chosen_because": None, "spread": None,
    }
    return contract.sourced(candidate["value"], str(candidate.get("unit") or ""), provenance, ident=ident)


SPEC = AdapterSpec(
    kind=KIND,
    title="Measured constants",
    command="cite",
    needs=("network", "literature"),
    argv=argv,
    run=run,
    unavailable=unavailable,
    describe=describe,
    cli_prefix=("python3", "scripts/cite.py"),
    serial=True,
)


def register(registry: Any) -> None:
    registry.register(SPEC)

