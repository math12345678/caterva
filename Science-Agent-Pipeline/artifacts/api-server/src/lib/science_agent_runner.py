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
from typing import Any, Dict, Optional

import fallback_logic
from fallback_logic import KineticResult


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


def _citation_to_dict(citation) -> Optional[Dict[str, Any]]:
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

        if not ec_number:
            raise ValueError("ecNumber is required to resolve real enzyme parameters")  # noqa: TRY301

        result = resolve_kinetic_value(enzyme_name, substrate, organism, ec_number)

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
