#!/usr/bin/env python3
"""JSON bridge between the Node API server and the Python Tellurium engine.

The TypeScript API server spawns this script and writes a JSON payload to
stdin. This script imports tellurium_engine from the repo root, runs the
requested simulation, and prints a JSON result to stdout.

Usage:
    PYTHONPATH=/repo/root python3 tellurium_runner.py < request.json

Expected input JSON shape:
    {
      "domain": "mm" | "sir" | "seir",
      "parameters": { ...domain-specific params... }
    }

Output JSON shape:
    {
      "ok": true,
      "domain": "mm",
      "parameters": { ... },
      "trajectory": [ { "t": 0.0, "S": 10.0, ... }, ... ],
      "flagged": false,
      "flagReason": null
    }

or on error:
    { "ok": false, "error": "..." }
"""

from __future__ import annotations

import json
import math
import sys
from typing import Any, Dict, List

# The repo root must be on PYTHONPATH so we can import Tellurium.tellurium_engine.
# The API server sets this when spawning the process.
from Tellurium import tellurium_engine  # type: ignore


def _to_point(row: List[float], colnames: List[str]) -> Dict[str, float]:
    return {name: float(row[i]) for i, name in enumerate(colnames)}


def run_mm(params: Dict[str, Any]) -> Dict[str, Any]:
    km = float(params.get("km", 2.0))
    vmax = float(params.get("vmax", 5.0))
    s0 = float(params.get("s0", 10.0))
    end = float(params.get("end", 10.0))
    points = int(params.get("points", 51))

    result = tellurium_engine.simulate_michaelis_menten(
        km=km, vmax=vmax, s0=s0, end=end, points=points
    )

    return {
        "ok": True,
        "domain": "mm",
        "parameters": {"km": km, "vmax": vmax, "s0": s0, "end": end, "points": points},
        "trajectory": [
            _to_point(list(row), result.colnames) for row in result.data
        ],
        "flagged": result.flagged,
        "flagReason": result.validation.flag_reason if result.flagged else None,
    }


def run_sir(params: Dict[str, Any]) -> Dict[str, Any]:
    beta = float(params.get("beta", 0.3))
    gamma = float(params.get("gamma", 0.1))
    s0 = float(params.get("s0", 990.0))
    i0 = float(params.get("i0", 10.0))
    r0 = float(params.get("r0_recovered", 0.0))
    end = float(params.get("end", 100.0))
    points = int(params.get("points", 101))

    result = tellurium_engine.simulate_sir(
        beta=beta, gamma=gamma, s0=s0, i0=i0, r0_recovered=r0, end=end, points=points
    )

    return {
        "ok": True,
        "domain": "sir",
        "parameters": {"beta": beta, "gamma": gamma, "s0": s0, "i0": i0, "r0_recovered": r0, "end": end, "points": points},
        "trajectory": [
            _to_point(list(row), result.colnames) for row in result.data
        ],
        "flagged": result.flagged,
        "flagReason": result.validation.flag_reason if result.flagged else None,
    }


def run_seir(params: Dict[str, Any]) -> Dict[str, Any]:
    beta = float(params.get("beta", 0.3))
    sigma = float(params.get("sigma", 0.2))
    gamma = float(params.get("gamma", 0.1))
    s0 = float(params.get("s0", 990.0))
    e0 = float(params.get("e0", 10.0))
    i0 = float(params.get("i0", 0.0))
    r0 = float(params.get("r0_recovered", 0.0))
    end = float(params.get("end", 100.0))
    points = int(params.get("points", 101))

    result = tellurium_engine.simulate_seir(
        beta=beta, sigma=sigma, gamma=gamma, s0=s0, e0=e0, i0=i0,
        r0_recovered=r0, end=end, points=points
    )

    return {
        "ok": True,
        "domain": "seir",
        "parameters": {
            "beta": beta, "sigma": sigma, "gamma": gamma,
            "s0": s0, "e0": e0, "i0": i0, "r0_recovered": r0,
            "end": end, "points": points,
        },
        "trajectory": [
            _to_point(list(row), result.colnames) for row in result.data
        ],
        "flagged": result.flagged,
        "flagReason": result.validation.flag_reason if result.flagged else None,
    }


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw:
            raise ValueError("no input JSON provided")
        payload = json.loads(raw)
        domain = payload.get("domain")
        params = payload.get("parameters", {})

        if domain == "mm":
            result = run_mm(params)
        elif domain == "sir":
            result = run_sir(params)
        elif domain == "seir":
            result = run_seir(params)
        else:
            raise ValueError(f"unknown domain: {domain!r}")

        print(json.dumps(result))
    except Exception as exc:
        error_payload = {"ok": False, "error": str(exc)}
        print(json.dumps(error_payload), file=sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
