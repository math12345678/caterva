#!/usr/bin/env python3
"""JSON bridge between the Node API server and the real scientific lookup layer.

The TypeScript API server spawns this script and writes a JSON payload to stdin.
This script uses the existing Tests/brenda_client.py, Tests/enzyme_lookup.py,
and Tests/fallback_logic.py modules to resolve literature-backed Km values for
enzyme-kinetic queries. It returns a structured JSON result that the TypeScript
pipeline can turn into Michaelis-Menten parameters.

Usage:
    PYTHONPATH=/repo/root:/repo/root/Tests python3 science_agent_runner.py

Expected input JSON shape:
    {
      "enzymeName": "lactate dehydrogenase",
      "substrate": "pyruvate",
      "organism": "Homo sapiens",
      "ecNumber": "1.1.1.27",
      "quantity": "km"
    }

"quantity" selects which constant is resolved: "km" (default) reads
BRENDA's "KM Values" table, "ki" reads the "Ki Values" table (the
inhibition constant), "kcat" reads the "Turnover Numbers" table. All three
use the same exact/cross-species/literature chain. Each call resolves
exactly one quantity, and the output value is emitted under the matching
key ("km", "ki", or "kcat") -- so a cross-species Ki never borrows a
verified Km's provenance (see provenance.ts / ADR 0008).

A resolved "kcat" is a real, citable literature value but is NOT a
simulation-ready parameter: the MM engine takes Vmax, and
Vmax = kcat * [E]0 needs an enzyme concentration BRENDA does not supply
and Caterva never defaults or infers (ADR 0012 / ADR 0013). "kcat" is
therefore deliberately absent from RESOLVABLE_FIELDS -- resolvable and
displayable, not yet wired to a simulation. See ADR 0019.

"ecNumber" is optional. If omitted (or empty) and "enzymeName" is present,
this script resolves an EC number live via UniProt's name search
(enzyme_lookup.fetch_ec_number_by_name) before attempting BRENDA/KEGG/
PubMed -- see resolve_ec_number() below. If UniProt has nothing indexed
under that name, the result is an honest {"found": false}, never a
fabricated EC number or Km/Ki. If BOTH "ecNumber" and "enzymeName" are
missing, that's a hard error: there is nothing to search for at all.

Output JSON shape (success, quantity="km"):
    {
      "ok": true,
      "found": true,
      "km": 2.5,
      "unit": "mM",
      "organism": "Homo sapiens",
      "source": "brenda_exact",
      "citation": { "source": "BRENDA", "reference_id": "...", "url": "..." },
      "literatureCandidates": [],
      "logs": []
    }

With quantity="ki" the value is emitted under "ki" instead of "km".

Output JSON shape (not found):
    {
      "ok": true,
      "found": false,
      "logs": [...]
    }

Output JSON shape (error):
    {
      "ok": false,
      "error": "..."
    }
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

import enzyme_lookup
import epidemiology_resolver
import fallback_logic
import reliability
from fallback_logic import KineticResult
import httpx
import popgen_resolver


def resolve_ec_number(enzyme_name: str, organism: str) -> str | None:
    """Live enzyme-name -> EC-number resolution via UniProt, used whenever
    the caller didn't already supply one (e.g. an enzyme name outside the
    small hardcoded pattern list in enzymes.ts, or a name guessed from free
    text). Tries the query's stated organism first, then an unrestricted
    search, so a mismatch between the caller's organism guess and what
    UniProt actually has indexed doesn't sink an otherwise-real match.
    Returns None -- never guesses -- if UniProt has nothing indexed under
    this name at all.

    Referenced via the enzyme_lookup module (not imported by name) so
    tests can monkeypatch enzyme_lookup.fetch_taxon_id /
    enzyme_lookup.fetch_ec_number_by_name and stay offline."""
    candidates = resolve_ec_candidates(enzyme_name, organism)
    return candidates[0] if len(candidates) == 1 else None


def resolve_ec_candidates(enzyme_name: str, organism: str) -> list:
    """EVERY EC number UniProt indexes under this name.

    WHY THE PLURAL
    --------------
    `resolve_ec_number` used to take the first and say nothing. EC 1.1.1.27
    is L-lactate dehydrogenase and EC 1.1.1.28 is D-lactate dehydrogenase:
    different proteins on different stereoisomers, one common name -- and
    "lactate dehydrogenase" is the example in this project's own CLI help.

    An EC number is not a parameter. It is the identity of the protein
    every citation downstream refers to, so picking one silently produces a
    correctly formatted reference to the wrong enzyme, before any of the
    machinery that prevents exactly that gets to run (ADR 0126).

    The organism-first, then-unrestricted order is unchanged: a mismatch
    between the caller's organism guess and what UniProt has indexed should
    not sink an otherwise-real match.
    """
    taxon_id = enzyme_lookup.fetch_taxon_id(organism) if organism else None
    if taxon_id:
        narrowed = enzyme_lookup.fetch_ec_numbers_by_name(enzyme_name, taxon_id)
        if narrowed:
            return narrowed
    return enzyme_lookup.fetch_ec_numbers_by_name(enzyme_name, None)


def taxon_id_for(organism: str | None) -> str | None:
    """NCBI Taxonomy id for an organism name, or None if it cannot be got.

    None means "not resolved". It never means "assume human" -- that
    substitution used to live in `enzyme_lookup.DEFAULT_TAXON_ID` and fired
    on a *network failure*, stamping a human identifier onto a thermophile's
    measurement (see Tests/test_no_default_organism.py).

    Emitted so the SBML exporter can write `bqbiol:hasTaxon` on each
    parameter. Without it the cross-species mismatch is prose only, and
    prose is invisible to a pipeline. The runner already resolved this id
    for its own EC lookup and threw it away.

    Referenced through the `enzyme_lookup` module rather than by name so the
    test suite can monkeypatch it and stay offline.
    """
    if not organism:
        return None
    try:
        return enzyme_lookup.fetch_taxon_id(organism)
    except Exception:
        # A failed taxonomy lookup must not sink a resolution that
        # otherwise succeeded. The annotation is an addition to the answer,
        # not a precondition for it -- so its absence is reported by being
        # absent, and the Km is still returned.
        return None


def resolve_substrate_from_kegg(ec_number: str) -> str | None:
    """Live substrate-name lookup for an EC number via KEGG, used to fill
    in a substrate name when the caller didn't supply one -- which happens
    whenever the enzyme name came from the free-text guess in
    queryResolver.ts rather than the hardcoded enzymes.ts list (that list
    bundles a substrate per entry; a live-resolved enzyme has none yet).

    This matters, not just fills a gap cosmetically: brenda_client.py
    filters BRENDA's results by substrate name, and enzyme_lookup.py's own
    module docstring explains why that filter exists -- without it, a
    BRENDA enzyme page's Km data is dominated by every inhibitor and assay
    surrogate anyone has ever tested, not the enzyme's real substrate. A
    live-resolved enzyme with no substrate would silently get the same
    noise a hardcoded entry is built to avoid.

    Returns None -- never guesses -- if KEGG has no SUBSTRATE field for
    this EC number, or the lookup fails outright (network error, unknown
    EC). A failure here degrades to the unfiltered BRENDA fallback that
    already exists for this exact case (see brenda_client.py); it must
    never crash the whole resolution."""
    try:
        text = enzyme_lookup.fetch_kegg_enzyme_text(ec_number)
    except httpx.HTTPError:
        return None
    except enzyme_lookup.KeggLicenceNotConfigured:
        # KEGG is OFF by default because Caterva has no licence position for
        # it (ADR 0068, NOTICE, docs/LICENSING.md). This is a deliberate
        # abstention, not a swallowed failure, which is why it is caught by
        # NAME rather than by widening the clause above -- widening it is
        # what `test_programming_error_is_not_swallowed` exists to prevent.
        #
        # Degrading to None is already the designed behaviour for "KEGG did
        # not give us a substrate", and the unfiltered BRENDA fallback below
        # handles it. The user sees a broader BRENDA result set, not a crash.
        return None
    substrates = enzyme_lookup.parse_kegg_substrates(text)
    return substrates[0] if substrates else None


def resolve_kinetic_value(
    enzyme_name: str,
    substrate: str,
    organism: str,
    ec_number: str,
    quantity: str = "km",
    allow_cross_species: bool = False,
    allow_variants: bool = False,
    isoform: Optional[str] = None,
    inhibition_mode: Optional[str] = None,
    model_substrate: Optional[str] = None,
) -> KineticResult:
    """Thin wrapper around the real fallback logic in Tests/fallback_logic.py.

    ``quantity`` selects which BRENDA table is read ("km" -> KM Values,
    "ki" -> Ki Values). One call resolves exactly one quantity, so Km and
    Ki get independent lookups and independent citations.

    We keep the orchestrator thin so that OpenCode can swap it out for a
    different resolver (e.g., a local model or another database) without
    touching the Node/TypeScript side.

    ``quantity`` ("km" or "ki") passes straight through to
    fallback_logic.resolve_kinetic_value, which owns the mapping to a
    BRENDA table label (QUANTITY_TABLE_LABELS in fallback_logic.py) and to
    the PubMed query term. This wrapper does no translation of its own so
    there's exactly one place that mapping can drift.

    ``allow_cross_species`` defaults to False and passes straight through
    for the same reason: fallback_logic owns the policy and this wrapper
    owns nothing. Defaulting it True here would silently re-enable the
    behaviour ADR 0024 disabled, in a file nobody would think to check.
    """
    return fallback_logic.resolve_kinetic_value(
        enzyme_ec=ec_number,
        organism=organism,
        substrate=substrate,
        enzyme_name=enzyme_name,
        quantity=quantity,
        allow_cross_species=allow_cross_species,
        allow_variants=allow_variants,
        isoform=isoform,
        inhibition_mode=inhibition_mode,
        model_substrate=model_substrate,
    )



def _parse_physiological(payload: dict):
    """Build a PhysiologicalReference from the caller's payload, or None.

    ALL FIVE FIELDS ARE REQUIRED, and a partial reference is refused rather
    than completed.

    A caller who supplies a pH and no temperature has stated half of what
    the model represents. Filling the other half -- with 37 C, say -- would
    silently assume a mammal, which is the exact assumption this axis was
    designed not to make: 37 C misdescribes Thermus thermophilus, whose
    enzymes are measured near 70 C. Tolerances are equally not defaultable:
    how far a Km may drift before it stops representing the modelled system
    is a property of the enzyme.

    So a partial reference produces None, and the axis reports
    `not_assessed` with its reason -- which is true, rather than a
    confident grade against a reference nobody fully stated.
    """
    spec = payload.get("physiologicalReference")
    if not isinstance(spec, dict):
        return None

    required = ("ph", "temperatureC", "basis", "phTolerance", "temperatureToleranceC")
    if any(spec.get(field) is None for field in required):
        return None

    try:
        return reliability.PhysiologicalReference(
            ph=float(spec["ph"]),
            temperature_c=float(spec["temperatureC"]),
            basis=str(spec["basis"]),
            ph_tolerance=float(spec["phTolerance"]),
            temperature_tolerance_c=float(spec["temperatureToleranceC"]),
        )
    except (TypeError, ValueError):
        return None


def _resolved_effectors_dict(effectors):
    """Resolve each effector to a PubChem compound, or pass it through.

    Network failure is NOT an error. A resolved kinetic value with an
    unresolved effector is still a resolved kinetic value; refusing the
    lookup because PubChem was slow would turn an enrichment into a
    dependency. `compare_effectors` reads an unresolved identity as
    "could not check", never as "the conditions agree".
    """
    if not effectors:
        return []
    try:
        import effector as effector_module
        return [e.model_dump() for e in effector_module.resolve_effectors(effectors)]
    except Exception:  # noqa: BLE001
        return [e.model_dump() for e in effectors]


def _row_scope(commentary):
    """{isoform, inhibitionMode, versus, kitzWilson} from a BRENDA row's
    commentary, or None when there is no commentary.

    Read by caterva.compose.ki_mode.read_row, which reads with
    caterva.bind.core (the one implementation of this reading) and is what
    the resolver ranked the row by when a Ki was asked for by mode, so the
    flags describe the row by the reading that chose it.

    `kitzWilson` is True for a row "determined from Kitz-Wilson plots" (ref
    702238): the K_I of an irreversible inactivation, filed in BRENDA's Ki
    table and stating no mode. Without it the row reads only as "states no
    inhibition mode", which is true of its words and hides what it is. A
    mode-aware lookup takes one only when nothing else is left, and says so
    here when it does."""
    if not commentary:
        return None
    try:
        from caterva.compose.ki_mode import read_row
    except ImportError:
        return None
    row = read_row(commentary)
    return {"isoform": row.isoform, "inhibitionMode": row.mode, "versus": row.versus,
            "kitzWilson": row.kitz_wilson}


def _buffer_identity_dict(raw_buffer):
    """Resolve a reported buffer string to a comparable identity, or None.

    NETWORK FAILURE IS NOT AN ERROR HERE. A resolved kinetic value with an
    unresolved buffer is still a resolved kinetic value; refusing the whole
    lookup because PubChem was slow would turn an enrichment into a
    dependency. buffer_identity's own three states carry the failure
    forward, and the coherence check reads `unresolvable` as "could not
    check", never as "buffers agree".
    """
    if not raw_buffer:
        return None
    try:
        import buffer_identity
        return buffer_identity.resolve_identity(raw_buffer).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "raw": raw_buffer,
            "status": "unresolvable",
            "reason": (
                f"Buffer identity lookup failed ({type(exc).__name__}). "
                "The buffer was reported; it could not be resolved to a "
                "compound."
            ),
        }


def _reliability_dict(result, requested_organism: str, physiological=None) -> dict:
    """Grade the resolved value on Bakker's three axes (ADR 0024).

    No physiological reference is passed, and that is not an oversight: it
    is an experimental condition the caller states, not something this layer
    may assume. Absent one, the proximity axis reports `not_assessed` and
    says why. See Tests/reliability.py.
    """
    verdict = next(
        (
            v.model_dump()
            for v in result.relatedness
            if v.candidate_organism == result.organism
        ),
        None,
    )
    score = reliability.score_reliability(
        ph=result.assay_ph,
        temperature_c=result.assay_temperature_c,
        unreported=list(result.assay_unreported),
        reference=physiological,
        requested_organism=requested_organism,
        measured_organism=result.organism,
        cross_species=result.cross_species_flag,
        relatedness=verdict,
    )
    return {
        "assayCompleteness": {
            "grade": score.assay_completeness.grade,
            "reason": score.assay_completeness.reason,
        },
        "conditionProximity": {
            "grade": score.condition_proximity.grade,
            "reason": score.condition_proximity.reason,
        },
        "organismMatch": {
            "grade": score.organism_match.grade,
            "reason": score.organism_match.reason,
        },
        "noAggregateReason": score.no_aggregate_reason,
    }


def _ensure_caterva_path() -> str:
    """Ensure caterva/ directory is in sys.path for validation imports.

    Returns the Caterva directory path. This is shared by vmax and beta_gamma bridges
    to avoid duplicating the import setup logic.
    """
    import pathlib
    import sys

    caterva_dir = str(pathlib.Path(__file__).resolve().parents[5] / "caterva")
    if caterva_dir not in sys.path:
        sys.path.insert(0, caterva_dir)
    return caterva_dir


def bridge_vmax_from_kcat(kcat: float, enzyme_conc: float) -> tuple[float, bool, bool, str | None]:
    """Compute Vmax = kcat * [E]0 via the SAME implementation the engine
    itself uses (caterva.core.validation.vmax_from_kcat), rather than a
    second copy of the arithmetic and its Rule 2 bounds in TypeScript. See
    ADR 0019.

    Imported lazily as ``core.validation`` with the caterva/ directory
    (not the Caterva package root) added to sys.path -- this reaches
    caterva/core/validation.py directly as validation.py's own module
    docstring anticipates (its imports already try
    ``caterva.core.data_structures`` first, falling back to
    ``core.data_structures``) WITHOUT executing caterva/__init__.py's
    full antimony-dependent import chain, which the public
    ``caterva_engine`` entry point requires just to expose one
    pure-arithmetic function. This keeps every non-kcat lookup (km, ki,
    mutation_rate) free of an antimony dependency it never needed.

    Returns (vmax, ok, flagged, flag_reason_or_error). ``ok=False`` means
    the inputs were rejected (non-finite/non-positive); the caller must
    not treat the returned vmax as usable in that case.
    """
    _ensure_caterva_path()
    from core import validation as caterva_validation  # noqa: PLC0415

    vmax, result = caterva_validation.vmax_from_kcat(kcat, enzyme_conc)
    if not result.ok:
        return 0.0, False, False, "; ".join(result.errors)
    return vmax, True, result.flagged, result.flag_reason


def bridge_beta_gamma_from_r0(
    r0: float, infectious_period_days: float
) -> tuple[float, float, bool, bool, str | None]:
    """Compute (beta, gamma) = R0/infectious-period bridge via the SAME
    implementation the SIR engine itself uses
    (caterva.core.validation.beta_gamma_from_r0), imported the same
    lightweight way bridge_vmax_from_kcat() reaches vmax_from_kcat -- as
    ``core.validation`` with caterva/ (not the Caterva package root) on
    sys.path, never executing caterva/__init__.py's antimony-dependent
    chain. See ADR 0017 for the resolver, ADR 0020 for this bridge.

    Returns (beta, gamma, ok, flagged, flag_reason_or_error).
    """
    _ensure_caterva_path()
    from core import validation as caterva_validation  # noqa: PLC0415

    beta, gamma, result = caterva_validation.beta_gamma_from_r0(
        r0, infectious_period_days
    )
    if not result.ok:
        return 0.0, 0.0, False, False, "; ".join(result.errors)
    return beta, gamma, True, result.flagged, result.flag_reason


def resolve_popgen_parameter(param_type: str, organism: str) -> dict | None:
    """Resolve a population genetics parameter from literature.
    
    Args:
        param_type: Parameter type (e.g., 'mutation_rate')
        organism: Organism name
        
    Returns:
        Dict with value, unit, citation info, or None if not found.
    """
    if param_type == 'mutation_rate':
        result = popgen_resolver.resolve_mutation_rate(organism)
        if not result.found:
            return None
        return {
            'value': result.value,
            'unit': result.unit,
            'source': result.source,
            'citation': result.citation,
            'organism': result.organism,
            'doi': result.doi,
        }
    return None


def _citation_to_dict(citation) -> Dict[str, Any] | None:
    if citation is None:
        return None
    return {
        "source": citation.source,
        "referenceId": citation.reference_id,
        "url": citation.url,
        "title": citation.title,
        "organism": citation.organism,
        "notes": citation.notes,
    }


def _candidates_to_dict(candidates) -> list:
    # source/pmid/doi added when CORE open-access search started
    # supplementing PubMed (fallback_logic.py) -- pmid and doi are each
    # None on the source that doesn't provide them (CORE has no PMID;
    # PubMed's esummary response has no DOI), never fabricated as "".
    return [
        {
            "pmid": c.pmid,
            "title": c.title,
            "url": c.url,
            "source": c.source,
            "doi": c.doi,
        }
        for c in candidates
    ]


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw:
            raise ValueError("no input JSON provided")  # noqa: TRY301
        payload = json.loads(raw)

        enzyme_name = payload.get("enzymeName", "")
        substrate = payload.get("substrate", "")
        # NOT `payload.get("organism", "Homo sapiens")`. That default sat
        # here until 2026-08-15 and answered about humans whenever a caller
        # omitted the organism -- the same defect as DEFAULT_TAXON_ID one
        # layer up, and in a tool whose headline behaviour is refusing to
        # substitute one organism for another. An empty organism now flows
        # through as empty and the resolver refuses, which is the true
        # answer to a question nobody finished asking.
        organism = payload.get("organism") or ""
        ec_number = payload.get("ecNumber", "")
        parameter_type = payload.get("parameterType", "")
        quantity = payload.get("quantity", "km")
        if quantity not in ("km", "ki", "kcat"):
            quantity = "km"
        enzyme_conc = payload.get("enzymeConc")
        #: Opt-in for cross-species values (ADR 0024). Absent means False:
        #: reading a missing flag permissively is exactly how the old
        #: automatic fallback would creep back in.
        allow_cross_species = payload.get("allowCrossSpecies") is True
        #: Opt in to values measured on a sequence variant -- a point mutant
        #: or a named isozyme (ADR 0029). Absent means False, for the same
        #: reason allowCrossSpecies reads that way: the permissive reading of
        #: a missing flag is how the old behaviour returns silently.
        allow_variants = payload.get("allowVariants") is True
        #: The isoform the query is about ("LDH-A"), when it names one. Rows
        #: measuring it are used; a constant only measured on other isoforms
        #: is refused, source "isoform_withheld" (fallback_logic).
        isoform = payload.get("isoform") if isinstance(payload.get("isoform"), str) else None
        #: The inhibition mode of the model a Ki is for ("competitive" for
        #: the API's mm_competitive_inhibition, `scientific resolve --mode`),
        #: and that model's substrate; the payload's `substrate` is the
        #: inhibitor for a Ki. With a mode the resolver takes a Ki row whose
        #: stated mode fits the model, by `caterva compose`'s ranking, and
        #: refuses, source "mode_withheld", when every row states another.
        #: A mode no model can be of is an error, not a request dropped.
        inhibition_mode = (payload.get("inhibitionMode")
                           if isinstance(payload.get("inhibitionMode"), str) else None)
        model_substrate = (payload.get("modelSubstrate")
                           if isinstance(payload.get("modelSubstrate"), str) else None)
        #: The conditions the model represents. An experimental condition
        #: the caller states, never assumed here (ADR 0012/0013).
        physiological = _parse_physiological(payload)
        resolution_log: list[str] = []

        # Handle population genetics parameter resolution
        if parameter_type == "mutation_rate":
            popgen_result = resolve_popgen_parameter("mutation_rate", organism)
            if popgen_result is None:
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "found": False,
                            "source": "popgen_not_found",
                            "literatureCandidates": [],
                            "logs": [
                                f"No literature value found for mutation_rate in '{organism}'"
                            ],
                        }
                    )
                )
                return
            print(
                json.dumps(
                    {
                        "ok": True,
                        "found": True,
                        "km": popgen_result["value"],  # Reuse km field for the value
                        "ki": None,
                        "unit": popgen_result["unit"],
                        "organism": popgen_result["organism"],
                        "source": "popgen_literature",
                        "crossSpecies": False,
                        "assayConditions": {},
                        "citation": {
                            "source": popgen_result["source"],
                            "referenceId": popgen_result["doi"],
                            "url": f"https://doi.org/{popgen_result['doi']}" if popgen_result['doi'] else None,
                            "title": popgen_result["citation"],
                        },
                        "literatureCandidates": [],
                        "logs": resolution_log + [f"Resolved mutation_rate from literature: {popgen_result['citation']}"],
                    }
                )
            )
            return

        # Handle epidemiology parameter resolution (ADR 0017 / ADR 0020):
        # a disease name resolves to a hand-curated (R0, infectious period)
        # golden tuple, then bridges to the SIR engine's own (beta, gamma)
        # via the exact same beta_gamma_from_r0() the engine uses. Only
        # diseases in the registry resolve; everything else is an honest
        # found=False, never a fabricated R0.
        if parameter_type == "disease_parameters":
            disease = payload.get("disease", "")
            epi_result = epidemiology_resolver.resolve_disease_parameters(disease)
            if not epi_result.found:
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "found": False,
                            "source": "epidemiology_not_found",
                            "literatureCandidates": [],
                            "logs": epi_result.search_log,
                        }
                    )
                )
                return

            beta, gamma, bg_ok, bg_flagged, bg_reason = bridge_beta_gamma_from_r0(
                epi_result.r0, epi_result.infectious_period_days
            )
            output = {
                "ok": True,
                "found": True,
                "disease": epi_result.disease,
                "r0": epi_result.r0,
                "infectiousPeriodDays": epi_result.infectious_period_days,
                "organism": None,
                "source": epi_result.source,
                "crossSpecies": False,
                "assayConditions": {},
                "citation": {
                    "source": epi_result.source,
                    "referenceId": epi_result.pmid,
                    "url": f"https://doi.org/{epi_result.doi}" if epi_result.doi else None,
                    "title": epi_result.citation,
                },
                # ADR 0169: a cross-study composite carries BOTH sources
                # and must surface flagged, never verified. The secondary
                # citation is the serial-interval half; omitting it would
                # present a two-paper number as if one paper supported it.
                "crossStudyComposite": epi_result.cross_study_composite,
                "compositeNote": epi_result.composite_note,
                "secondaryCitation": (
                    {
                        "source": epi_result.source,
                        "referenceId": epi_result.secondary_pmid,
                        "url": (
                            f"https://doi.org/{epi_result.secondary_doi}"
                            if epi_result.secondary_doi
                            else None
                        ),
                        "title": epi_result.secondary_citation,
                    }
                    if epi_result.secondary_pmid
                    else None
                ),
                "betaGammaValidation": {
                    "ok": bg_ok,
                    "flagged": bg_flagged,
                    "reason": bg_reason,
                },
                "literatureCandidates": [],
                "logs": epi_result.search_log,
            }
            if bg_ok:
                output["beta"] = beta
                # "gamma" here, NOT "gamma_rate" -- gamma_rate is only the
                # Antimony-emitted model-string name (ADR 0004); the
                # Python/TS API surface takes "gamma".
                output["gamma"] = gamma
                output["logs"] = output["logs"] + [
                    f"Bridged beta={beta:g}, gamma={gamma:g} from R0="
                    f"{epi_result.r0:g} and infectious_period="
                    f"{epi_result.infectious_period_days:g} days."
                ]
            print(json.dumps(output))
            return

        if not ec_number:
            if not enzyme_name:
                raise ValueError(  # noqa: TRY301
                    "enzymeName or ecNumber is required to resolve real enzyme parameters"
                )
            ec_candidates = resolve_ec_candidates(enzyme_name, organism)
            if len(ec_candidates) > 1:
                # NOT `ec_not_resolved`. UniProt resolved it fine — to more
                # than one enzyme. Reporting that as "could not resolve"
                # would be a worse message than the silent pick it
                # replaces, because it denies the existence of the answer
                # instead of asking which one was meant.
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "found": False,
                            "source": "ec_ambiguous",
                            "ecCandidates": ec_candidates,
                            "literatureCandidates": [],
                            "logs": [
                                f"'{enzyme_name}' names more than one enzyme: "
                                + ", ".join(ec_candidates)
                                + ". These are different proteins, so no EC "
                                "number was chosen — a wrong one is a citation "
                                "for the wrong enzyme, not merely a wrong "
                                "value. Re-run with the EC number you meant."
                            ],
                        }
                    )
                )
                return

            ec_number = ec_candidates[0] if ec_candidates else ""
            if ec_number:
                resolution_log.append(
                    f"Resolved EC {ec_number} for '{enzyme_name}' via UniProt name search."
                )
                if not substrate:
                    kegg_substrate = resolve_substrate_from_kegg(ec_number)
                    if kegg_substrate:
                        substrate = kegg_substrate
                        resolution_log.append(
                            f"Resolved substrate '{substrate}' for EC {ec_number} via KEGG."
                        )
                    else:
                        resolution_log.append(
                            f"No KEGG substrate found for EC {ec_number}; "
                            "BRENDA lookup will be unfiltered by substrate."
                        )
            else:
                print(
                    json.dumps(
                        {
                            "ok": True,
                            "found": False,
                            "source": "ec_not_resolved",
                            "literatureCandidates": [],
                            "logs": [
                                f"Could not resolve an EC number for '{enzyme_name}' via "
                                "UniProt; no BRENDA/KEGG/PubMed lookup is possible without one."
                            ],
                        }
                    )
                )
                return

        result = resolve_kinetic_value(
            enzyme_name, substrate, organism, ec_number,
            quantity=quantity,
            allow_cross_species=allow_cross_species,
            allow_variants=allow_variants,
            isoform=isoform,
            inhibition_mode=inhibition_mode,
            model_substrate=model_substrate,
        )
        result.search_log = resolution_log + result.search_log

        if result.found and result.value is not None:
            # Emit the value under the key matching the requested quantity
            # so the TypeScript side reads km from "km" and ki from "ki" --
            # never the other way around.
            value_key = {"ki": "ki", "kcat": "kcat"}.get(quantity, "km")
            output = {
                "ok": True,
                "found": True,
                value_key: result.value,
                "unit": result.unit,
                "organism": result.organism,
                # The taxon of the organism the value was MEASURED in, and
                # of the one the caller ASKED about. Two fields because for
                # a cross-species result they differ, and that difference is
                # exactly what makes the substitution machine-detectable in
                # the exported SBML rather than only readable in a note.
                "taxonId": taxon_id_for(result.organism),
                "requestedTaxonId": taxon_id_for(organism),
                "source": result.source,
                "crossSpecies": result.cross_species_flag,
                # STRENDA-mandated assay conditions (ADR 0010). Keys are
                # omitted-as-null rather than defaulted: the TypeScript
                # side treats absence as "incomplete", which is the
                # honest reading when the source never reported them.
                "assayConditions": {
                    "ph": result.assay_ph,
                    "temperatureC": result.assay_temperature_c,
                    "buffer": result.assay_buffer,
                    # The buffer string resolved to a comparable chemical
                    # identity (ADR 0028). The raw string stays alongside it:
                    # this is an ADDITION to what was reported, never a
                    # replacement for it, and a reader has to be able to
                    # disagree with the resolution.
                    "bufferIdentity": _buffer_identity_dict(result.assay_buffer),
                    "unreported": result.assay_unreported,
                },
                # Which protein this row measured (ADR 0029). Emitted for
                # FOUND values as well as withheld ones: `unstated` is the
                # majority case, and a reader needs to know the row simply
                # did not say rather than assume it was wild-type.
                "variant": (
                    result.variant.model_dump() if result.variant else None
                ),
                # The chosen row's BRENDA commentary, verbatim: which isoform
                # it measured and, for a Ki, which inhibition mode and against
                # which molecule. Without it a reader cannot tell gossypol's
                # LDH-B Ki from its LDH-A one, or a Ki measured versus NADH
                # from one versus the modelled substrate.
                "commentary": getattr(result, "commentary", None),
                # What that commentary says, decided HERE by the same parser
                # `caterva bind` and `caterva compose` use, so the TypeScript
                # side reports it rather than re-deriving it (ADR 0027).
                "rowScope": _row_scope(getattr(result, "commentary", None)),
                # How the enzyme was PREPARED (ADR 0092): immobilised,
                # affinity-tagged, covalently modified, native, or unstated.
                #
                # Emitted beside `variant` because it is the same question
                # one category over -- ADR 0029 asks "is this the enzyme's
                # sequence?", this asks "is this the free enzyme?" -- and
                # neither is visible to the other's filter.
                #
                # Measured before it existed: the human LDH Ki resolved to
                # 0.00059, a "recombinant His-tagged enzyme" row, with
                # nothing in the response saying so. ADR 0038 is the
                # precedent for emitting it HERE: effectors were compared
                # correctly and stopped at this boundary, and severing the
                # resolver broke none of the 35 unit tests.
                "preparation": (
                    {
                        **result.preparation.model_dump(),
                        # The DECISION, made once, here, by the module that
                        # owns the rule.
                        #
                        # `differs_for(quantity)` is the whole judgement:
                        # was the enzyme altered, and did the curator say
                        # the alteration left THIS quantity alone. The
                        # first version emitted only the inputs and let
                        # queryResolver.ts re-derive it, which is two
                        # implementations of one rule -- ADR 0027 exactly,
                        # written while fixing ADR 0027's shape elsewhere.
                        #
                        # A client may still read `status` and
                        # `stated_not_to_affect` to render differently.
                        # What it must not do is decide again.
                        "warrantsWarning": result.preparation.differs_for(
                            quantity
                        ),
                    }
                    if result.preparation else None
                ),
                # Cofactors and effectors, with PubChem identity resolved
                # HERE rather than during parsing -- so parsing a fixture
                # stays offline and a network outage degrades the identity
                # rather than failing the whole lookup (ADR 0032).
                "effectors": _resolved_effectors_dict(result.effectors),
                # The tie the evidence could not break (ADR 0048). Emitted on
                # FOUND results: the point is that a value was returned while
                # equally-evidenced alternatives existed unmentioned.
                # Which named form the returned value IS, when the pool
                # mixed forms (ADR 0052). None in every fixture today.
                "selectedForm": (
                    result.selected_form.model_dump()
                    if result.selected_form else None
                ),
                "selectionTie": (
                    result.selection_tie.model_dump()
                    if result.selection_tie else None
                ),
                # EVERY SURVIVING ROW, WITH THE SCORE THAT WEIGHTS IT.
                #
                # `selectionTie` says the evidence could not choose and lists
                # the alternatives. This says how much each one is worth --
                # Bakker's three axes, graded per candidate rather than only
                # for the winner, which is what the sampling needs and what
                # made it unbuildable until the resolver started carrying
                # them (ADR 0137).
                #
                # Emitted whether or not anybody samples: it is a handful of
                # dicts, and a client that wants to draw a band should not
                # have to ask for a second resolution to get the weights.
                #
                # Empty means nothing was resolved, which is a resolution
                # failure to report -- never a band with no members.
                "ensembleCandidates": list(
                    getattr(result, "ensemble_candidates", []) or []
                ),
                # Every relatedness verdict, including the ones that
                # REJECTED a candidate. A filter that reports only what
                # survived it cannot be argued with, and the organisms it
                # dropped are precisely what a reader would want to check.
                "relatedness": [v.model_dump() for v in result.relatedness],
                # POOL-LEVEL FINDINGS. Facts about the candidate set, not
                # about the value that won it.
                #
                # These were computed and dropped here for four ADRs. The
                # resolver attached them to KineticResult, the runner never
                # emitted them, and only a prose line reached the diagnostic
                # log -- which is not `provenance.flags`, the list the CLI
                # and web UI actually render. Exactly ADR 0027's defect: a
                # thing computed correctly and discarded at a boundary,
                # invisible because every test on the computation passed.
                # See ADR 0039.
                "poolFindings": {
                    "effectorContrasts": [c.model_dump() for c in result.effector_contrasts],
                    "formMixtures": [m.model_dump() for m in result.form_mixtures],
                    "organismDiscrepancies": [
                        d.model_dump() for d in result.organism_discrepancies
                    ],
                    "sourceMixtures": [m.model_dump() for m in result.source_mixtures],
                    # "nothing found" and "nothing checked" are different
                    # facts. Set when source tokens were extracted and none
                    # could be classified -- with NCBI unreachable, a pool
                    # holding heart and muscle reports no mixture at all.
                    #
                    # Omitted from the first draft of this dict, one pass
                    # after the field was added, and caught by
                    # check_findings_reach_a_surface.py on its first run.
                    # The guard written to stop fields being dropped found
                    # one that had already been dropped.
                    "sourceCheckUnavailable": (
                        result.source_check_unavailable.model_dump()
                        if result.source_check_unavailable
                        else None
                    ),
                },
                # Bakker's three axes, graded in Python so the CLI and the
                # API show the same grades by construction rather than by
                # two implementations happening to agree. Both are asserted
                # against Tests/reliability_cases.json.
                "reliability": _reliability_dict(result, organism, physiological),
                "citation": _citation_to_dict(result.citation),
                "literatureCandidates": _candidates_to_dict(result.literature_candidates),
                "logs": result.search_log,
            }

            # ADR 0019: a resolved kcat plus a caller-supplied enzyme
            # concentration bridges to a simulable Vmax. enzyme_conc is
            # NEVER resolved or defaulted here (ADR 0013) -- it only
            # reaches this branch if queryResolver.ts found it as an
            # explicit user override on the query.
            if quantity == "kcat" and enzyme_conc is not None:
                try:
                    enzyme_conc_f = float(enzyme_conc)
                except (TypeError, ValueError):
                    output["vmaxValidation"] = {
                        "ok": False,
                        "flagged": False,
                        "reason": f"enzyme_conc {enzyme_conc!r} is not a number",
                    }
                else:
                    vmax, ok, flagged, reason = bridge_vmax_from_kcat(
                        result.value, enzyme_conc_f
                    )
                    output["vmaxValidation"] = {
                        "ok": ok,
                        "flagged": flagged,
                        "reason": reason,
                    }
                    if ok:
                        output["vmax"] = vmax
                        output["logs"] = output["logs"] + [
                            f"Bridged Vmax={vmax:g} mM/s from kcat={result.value:g} "
                            f"1/s x enzyme_conc={enzyme_conc_f:g} mM."
                        ]

            print(json.dumps(output))
        else:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "found": False,
                        "source": result.source,
                        # A refusal has to say what it refused. Without
                        # this the client sees source="cross_species_withheld"
                        # and cannot tell the user what opting in would
                        # get them -- the miss becomes unactionable at the
                        # API boundary even though the resolver knew.
                        "crossSpeciesOrganismsAvailable": result.cross_species_organisms_available,
                        # Which variants were found and withheld. A refusal
                        # that cannot name what it refused leaves the opt-in
                        # it demands unexercisable.
                        "variantCandidatesAvailable": result.variant_candidates_available,
                        # Which isoforms the rows measured, when the one
                        # asked for is not among them.
                        "isoformsAvailable": result.isoforms_available,
                        # What the rows state, when a Ki was asked for by
                        # the model's mode and every row states another
                        # (source "mode_withheld"): the mechanisms whose
                        # constants exist, so the refusal can name them.
                        "modesAvailable": result.modes_available,
                        # The same courtesy for the field a student is far
                        # MORE likely to get wrong. An organism has one
                        # binomial name; a metabolite has a dozen aliases,
                        # and BRENDA's label for lactate is `(S)-lactate`,
                        # so "lactate" matches by substring and "L-lactate"
                        # returns nothing at all.
                        "substratesAvailable": result.substrates_available,
                        "relatedness": [v.model_dump() for v in result.relatedness],
                        "literatureCandidates": _candidates_to_dict(result.literature_candidates),
                        "logs": result.search_log,
                    }
                )
            )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
