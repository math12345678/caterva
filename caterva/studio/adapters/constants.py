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
    In a source checkout, scripts/cite.py and the literature layer
    (Tests/) are read where they are. In the wheel and the app folder the
    release build has copied cite.py, report_lab.py and the modules they
    import into caterva/_literature/ (scripts/vendor_literature.py), and
    this kind reads them from there. `unavailable()` says which part is
    missing when a build lacks them, in the words cite.py and
    caterva.checkout use.

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
    exit 3 with cite.py's own words, and the outcome's `name_refusal` carries
    the one name policy's refusal as data: each candidate named, the kind,
    the recommended EC number and the flag that re-runs with one.
"""
from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, List, Mapping, Optional

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
#: Where cite.py is: the checkout's scripts/, else the installed package's copy.
CITE = REPO_ROOT / "scripts" / "cite.py"
if not CITE.is_file():
    CITE = Path(__file__).resolve().parents[2] / "_literature" / "cite.py"


@functools.lru_cache(maxsize=1)
def cite_module() -> ModuleType:
    """scripts/cite.py, imported by path: scripts/ is not a package."""
    module = sys.modules.get("caterva_cite")
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location("caterva_cite", CITE)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"{CITE} is missing; this build carries no literature layer.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["caterva_cite"] = module
    return module


@functools.lru_cache(maxsize=1)
def _missing() -> Optional[str]:
    if not CITE.is_file():
        return f"{CITE} is missing; this build carries no literature layer."
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
                              refusal=reason, name_refusal=result.get("name_refusal"))

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
    substrate = payload.get("parameters", [{}])[0].get("substrate") if payload.get("parameters") else None
    rows = [constant_row(entry["name"], entry.get("quantity", "km"), resolved.get(entry["name"]), substrate=substrate)
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
        "isozyme_notice": isozyme_view(payload, args),
    }


def _citation_text(citation: Optional[Mapping[str, Any]]) -> str:
    """report_lab's `_citation_of`, over the dumped citation: the words its
    document prints beside the value."""
    lab = sys.modules.get("caterva_report_lab")
    if lab is None:
        raise RuntimeError("report_lab is not loaded; the citation text is its words")
    holder = SimpleNamespace(citation=None if citation is None else SimpleNamespace(**citation))
    return lab._citation_of(holder)


def isozyme_view(payload: Mapping[str, Any], args: Any) -> Optional[Dict[str, Any]]:
    """The isozyme notice compose carries, for the EC number this lookup is about.

    The same function the compose verdict reads (`enzymes.isozyme`): shown when the EC number
    is several proteins in the organism asked about, because the constants of a lookup may
    belong to any of them (a lookup has no --isoform). None for one protein, none, or an
    organism the index does not know."""
    from caterva.enzymes.isozyme import isozyme_notice
    from caterva.enzymes.policy import NameNotResolved, resolve_enzyme_name

    ec = payload.get("ec")
    organism = payload.get("organism") or getattr(args, "organism", None)
    if not ec and payload.get("enzyme"):
        try:
            ec = resolve_enzyme_name(str(payload["enzyme"]), organism).ec
        except NameNotResolved:
            return None
    notice = isozyme_notice(ec, organism, None)
    if notice is None:
        return None
    return {
        "ec": notice.ec, "organism": notice.organism, "organism_label": notice.label, "count": notice.count,
        "symbols": list(notice.symbols), "broad": notice.broad, "headline": notice.headline,
        "detail": notice.lookup_detail,
        "remedy": "use the Isoform field of Compose to take each constant from a row that names one isozyme",
        "text": notice.lookup_detail + ".",
    }


def scope_concerns(commentary: Optional[str], quantity: Optional[str], substrate: Optional[str]) -> List[str]:
    """What the row's own commentary says that could make it the wrong number: another isoform
    named, an inhibition mode, none stated. `caterva compose` prints the same sentences under
    "What each value's own row says it measured", read by the same function."""
    from caterva.compose.row_scope import read_scope

    scope = read_scope(commentary, table=quantity, substrate=substrate)
    return [getattr(c, "plain", str(c)) for c in (scope.concerns if scope is not None else ())]


def tie_provenance(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """The engine's own account of a tie, as the provenance fields that carry it.

    When the evidence ranked several rows equal, the resolver says so in `selection_tie.reason`
    ("3 rows were equally well evidenced ... taking the lowest, which the evidence does not
    justify"), with the rows. That sentence is `chosen_because`, and the span is the `spread`."""
    tie = raw.get("selection_tie") or {}
    rows = tie.get("candidates") or []
    if len(rows) < 2 or not tie.get("reason"):
        return {"chosen_because": None, "spread": None}
    from caterva.compose.export import Spread

    references = tuple(sorted({str(r["reference_id"]) for r in rows if r.get("reference_id")}))
    spread = Spread(low=float(tie["low"]), high=float(tie["high"]), unit=str(raw.get("unit") or ""),
                    carried=float(raw["value"]), n_values=len(rows), references=references)
    return {"chosen_because": str(tie["reason"]), "spread": {
        "low": float(spread.low), "high": float(spread.high), "unit": str(spread.unit),
        "carried": float(spread.carried), "n_values": int(spread.n_values),
        "references": [str(r) for r in spread.references], "sentence": spread.sentence()}}


def constant_row(name: str, quantity: str, raw: Optional[Mapping[str, Any]],
                 substrate: Optional[str] = None) -> contract.ConstantRow:
    """One resolved quantity, read from the resolver's KineticResult."""
    if raw is None:
        raise ValueError(f"report_lab returned no KineticResult for {name!r}")
    value = None
    if raw.get("found") and raw.get("value") is not None:
        value = measured(raw, ident=name, label=name, quantity=quantity, substrate=substrate)
    alternatives: List[contract.SourcedValue] = []
    tie = raw.get("selection_tie") or {}
    for i, candidate in enumerate(tie.get("candidates") or []):
        if not candidate.get("selected"):
            alternatives.append(candidate_value(candidate, f"{name}:tied:{i}", "selection_tie",
                                                cross_species=False, quantity=quantity, substrate=substrate))
    for i, candidate in enumerate(raw.get("cross_species_candidates") or []):
        alternatives.append(candidate_value(candidate, f"{name}:other_organism:{i}",
                                            "cross_species_candidates", cross_species=True,
                                            quantity=quantity, substrate=substrate))
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


def measured(raw: Mapping[str, Any], *, ident: str, label: str, quantity: Optional[str] = None,
             substrate: Optional[str] = None) -> contract.SourcedValue:
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
        "commentary": raw.get("commentary"),
        "scope": scope_concerns(raw.get("commentary"), quantity, substrate)
        + [str(m["reason"]) for m in raw.get("form_mixtures") or [] if m.get("reason")],
        **tie_provenance(raw),  # type: ignore[typeddict-item]
    }
    return contract.sourced(raw["value"], str(raw.get("unit") or ""), provenance, ident=ident, label=label)


def candidate_value(candidate: Mapping[str, Any], ident: str, via: str, *,
                    cross_species: bool, quantity: Optional[str] = None,
                    substrate: Optional[str] = None) -> contract.SourcedValue:
    """A row the resolver ranked and did not carry (a TiedCandidate)."""
    reference = candidate.get("reference_id")
    citation: contract.Citation = {"text": f"BRENDA ref {reference}" if reference else "BRENDA",
                                   "registry": "BRENDA", "reference_id": reference, "via": via}
    provenance: contract.Provenance = {
        "kind": "measured", "citation": citation, "organism": candidate.get("organism"),
        "cross_species": cross_species,
        "conditions": {"ph": None, "temperature_c": None, "buffer": None, "unreported": []},
        "commentary": candidate.get("conditions"),
        "scope": scope_concerns(candidate.get("conditions"), quantity, substrate),
        "chosen_because": None, "spread": None,
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

