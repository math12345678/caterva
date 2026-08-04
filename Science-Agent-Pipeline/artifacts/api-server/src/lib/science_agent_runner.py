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
      "ecNumber": "1.1.1.27"
    }

"ecNumber" is optional. If omitted (or empty) and "enzymeName" is present,
this script resolves an EC number live via UniProt's name search
(enzyme_lookup.fetch_ec_number_by_name) before attempting BRENDA/KEGG/
PubMed -- see resolve_ec_number() below. If UniProt has nothing indexed
under that name, the result is an honest {"found": false}, never a
fabricated EC number or Km. If BOTH "ecNumber" and "enzymeName" are
missing, that's a hard error: there is nothing to search for at all.

Output JSON shape (success):
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


def resolve_kinetic_value(
    enzyme_name: str,
    substrate: str,
    organism: str,
    ec_number: str,
) -> KineticResult:
    """Thin wrapper around the real fallback logic in Tests/fallback_logic.py.

    We keep the orchestrator thin so that OpenCode can swap it out for a
    different resolver (e.g., a local model or another database) without
    touching the Node/TypeScript side.
    """
    return fallback_logic.resolve_kinetic_value(
        enzyme_ec=ec_number,
        organism=organism,
        substrate=substrate,
        enzyme_name=enzyme_name,
    )


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
        resolution_log: list[str] = []

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

        result = resolve_kinetic_value(enzyme_name, substrate, organism, ec_number)
        result.search_log = resolution_log + result.search_log

        if result.found and result.value is not None:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "found": True,
                        "km": result.value,
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
