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
and Terrium never defaults or infers (ADR 0012 / ADR 0013). "kcat" is
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
from typing import Any, Dict

import enzyme_lookup
import epidemiology_resolver
import fallback_logic
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
    taxon_id = enzyme_lookup.fetch_taxon_id(organism) if organism else None
    if taxon_id:
        ec = enzyme_lookup.fetch_ec_number_by_name(enzyme_name, taxon_id)
        if ec:
            return ec
    return enzyme_lookup.fetch_ec_number_by_name(enzyme_name, None)


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
    substrates = enzyme_lookup.parse_kegg_substrates(text)
    return substrates[0] if substrates else None


def resolve_kinetic_value(
    enzyme_name: str,
    substrate: str,
    organism: str,
    ec_number: str,
    quantity: str = "km",
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
    """
    return fallback_logic.resolve_kinetic_value(
        enzyme_ec=ec_number,
        organism=organism,
        substrate=substrate,
        enzyme_name=enzyme_name,
        quantity=quantity,
    )


def _ensure_terium_path() -> str:
    """Ensure Terium/ directory is in sys.path for validation imports.

    Returns the Terium directory path. This is shared by vmax and beta_gamma bridges
    to avoid duplicating the import setup logic.
    """
    import pathlib
    import sys

    terium_dir = str(pathlib.Path(__file__).resolve().parents[5] / "Terium")
    if terium_dir not in sys.path:
        sys.path.insert(0, terium_dir)
    return terium_dir


def bridge_vmax_from_kcat(kcat: float, enzyme_conc: float) -> tuple[float, bool, bool, str | None]:
    """Compute Vmax = kcat * [E]0 via the SAME implementation the engine
    itself uses (Terium.core.validation.vmax_from_kcat), rather than a
    second copy of the arithmetic and its Rule 2 bounds in TypeScript. See
    ADR 0019.

    Imported lazily as ``core.validation`` with the Terium/ directory
    (not the Terium package root) added to sys.path -- this reaches
    Terium/core/validation.py directly as validation.py's own module
    docstring anticipates (its imports already try
    ``Terium.core.data_structures`` first, falling back to
    ``core.data_structures``) WITHOUT executing Terium/__init__.py's
    full antimony-dependent import chain, which the public
    ``terium_engine`` entry point requires just to expose one
    pure-arithmetic function. This keeps every non-kcat lookup (km, ki,
    mutation_rate) free of an antimony dependency it never needed.

    Returns (vmax, ok, flagged, flag_reason_or_error). ``ok=False`` means
    the inputs were rejected (non-finite/non-positive); the caller must
    not treat the returned vmax as usable in that case.
    """
    _ensure_terium_path()
    from core import validation as terium_validation  # noqa: PLC0415

    vmax, result = terium_validation.vmax_from_kcat(kcat, enzyme_conc)
    if not result.ok:
        return 0.0, False, False, "; ".join(result.errors)
    return vmax, True, result.flagged, result.flag_reason


def bridge_beta_gamma_from_r0(
    r0: float, infectious_period_days: float
) -> tuple[float, float, bool, bool, str | None]:
    """Compute (beta, gamma) = R0/infectious-period bridge via the SAME
    implementation the SIR engine itself uses
    (Terium.core.validation.beta_gamma_from_r0), imported the same
    lightweight way bridge_vmax_from_kcat() reaches vmax_from_kcat -- as
    ``core.validation`` with Terium/ (not the Terium package root) on
    sys.path, never executing Terium/__init__.py's antimony-dependent
    chain. See ADR 0017 for the resolver, ADR 0020 for this bridge.

    Returns (beta, gamma, ok, flagged, flag_reason_or_error).
    """
    _ensure_terium_path()
    from core import validation as terium_validation  # noqa: PLC0415

    beta, gamma, result = terium_validation.beta_gamma_from_r0(
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
        organism = payload.get("organism", "Homo sapiens")
        ec_number = payload.get("ecNumber", "")
        parameter_type = payload.get("parameterType", "")
        quantity = payload.get("quantity", "km")
        if quantity not in ("km", "ki", "kcat"):
            quantity = "km"
        enzyme_conc = payload.get("enzymeConc")
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
            ec_number = resolve_ec_number(enzyme_name, organism) or ""
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

        result = resolve_kinetic_value(enzyme_name, substrate, organism, ec_number, quantity=quantity)
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
                    "unreported": result.assay_unreported,
                },
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
