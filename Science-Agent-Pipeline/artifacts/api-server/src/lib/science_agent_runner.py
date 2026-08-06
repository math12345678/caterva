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
inhibition constant, same exact/cross-species/literature chain). Each
call resolves exactly one quantity, and the output value is emitted under
the matching key ("km" or "ki") -- so a cross-species Ki never borrows a
verified Km's provenance (see provenance.ts / ADR 0008).

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
    """
    return fallback_logic.resolve_kinetic_value(
        enzyme_ec=ec_number,
        organism=organism,
        substrate=substrate,
        enzyme_name=enzyme_name,
        quantity=quantity,
    )


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
    return [
        {
            "pmid": c.pmid,
            "title": c.title,
            "url": c.url,
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
        if quantity not in ("km", "ki"):
            quantity = "km"
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
            value_key = "ki" if quantity == "ki" else "km"
            print(
                json.dumps(
                    {
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
                )
            )
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
