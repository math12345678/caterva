#!/usr/bin/env python3
"""
Terrium Python Integration Examples

Working examples of Terrium's REST API from Python.

WHY THIS FILE WAS REWRITTEN (2026-08-11)
----------------------------------------
The previous version documented eleven endpoints, and ten of them did not
exist:

    /api/health           the route is /api/healthz
    /api/jobs/<id>        the route is /api/simulate/<jobId>
    /api/export/jobs/csv  the route is /api/simulate/<jobId>/export
    /api/jobs/query, /api/batch, /api/batches/<id>, /api/sweep,
    /api/sweeps/<id>, /api/compare/jobs, /api/stats
                          no such routes, at all

It also taught a parameter-passing model the product does not have. It sent

    {"query": "michaelis-menten", "parameters": {"km": 5.2, ...}}

but Terrium takes parameters INSIDE the query string:

    {"query": "simulate michaelis menten km=5.2 vmax=12.8 s0=10 end=10 points=51"}

That difference is not cosmetic. Terrium refuses to invent a parameter it
was not given (ADR 0012/0013): experimental conditions like s0, end and
points are chosen by whoever runs the experiment and are never defaulted or
resolved from literature. A request that omits them comes back
MISSING_REQUIRED_INPUT naming exactly what to add — which is the product
working, and which the old example gave no way to discover.

`scripts/check_example_endpoints.py` now checks every endpoint here against
the routes the server actually registers, so this file cannot drift back.

Requires: pip install requests
"""

import sys
import time
from typing import Any, Dict, Optional

import requests

TERRIUM_URL = "http://localhost:3000"
API_TIMEOUT = 30


class TerriumClient:
    """Python client for the Terrium API."""

    def __init__(self, base_url: str = TERRIUM_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    # -- health ---------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Liveness. Returns {"status": "ok"}."""
        response = self.session.get(
            f"{self.base_url}/api/healthz", timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def pipeline_status(self) -> Dict[str, Any]:
        """Per-subsystem status and queue depth."""
        response = self.session.get(
            f"{self.base_url}/api/pipeline/status", timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    # -- running a simulation -------------------------------------------

    def simulate(self, query: str) -> str:
        """Enqueue a simulation, return its job id.

        `query` carries the parameters. There is no separate `parameters`
        field: the resolver reads `km=2 vmax=5 s0=10` out of the text, and
        anything it cannot find there and cannot resolve from literature is
        reported as missing rather than guessed.
        """
        response = self.session.post(
            f"{self.base_url}/api/simulate",
            json={"query": query},
            timeout=API_TIMEOUT,
        )
        if response.status_code == 400:
            raise ValueError(f"Rejected: {response.json().get('message')}")
        response.raise_for_status()
        return response.json()["jobId"]

    def get_job(self, job_id: str) -> Dict[str, Any]:
        """Current state of a job: pending, running, completed or failed."""
        response = self.session.get(
            f"{self.base_url}/api/simulate/{job_id}", timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def wait_for(
        self, job_id: str, attempts: int = 60, interval: float = 0.5
    ) -> Dict[str, Any]:
        """Poll to completion. Raises on failure rather than returning None.

        A failed job is a result, not an absence of one -- its error names
        what was missing, which is usually the thing the caller needs to
        read.
        """
        for _ in range(attempts):
            job = self.get_job(job_id)
            if job["status"] == "completed":
                return job["result"]
            if job["status"] == "failed":
                raise RuntimeError(f"Job {job_id} failed: {job.get('error')}")
            time.sleep(interval)
        raise TimeoutError(
            f"Job {job_id} did not finish in {attempts * interval:.0f}s"
        )

    def cancel(self, job_id: str) -> Dict[str, Any]:
        """Cancel a pending or running job."""
        response = self.session.post(
            f"{self.base_url}/api/simulate/{job_id}/cancel", timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    # -- what backs the numbers ------------------------------------------

    def confidence(self, job_id: str) -> Dict[str, Any]:
        """Per-parameter confidence, derived from provenance."""
        response = self.session.get(
            f"{self.base_url}/api/simulate/{job_id}/confidence",
            timeout=API_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def audit(self, job_id: str) -> Dict[str, Any]:
        """Publication audit: which parameters can be cited, and which cannot.

        Measured quantities (km, ki, kcat, vmax) need a citation.
        Experimental conditions (s0, i0, temperature, pH) are chosen by the
        experimenter and are reported, not cited -- so they never block
        publication readiness.
        """
        response = self.session.get(
            f"{self.base_url}/api/simulate/{job_id}/audit", timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def export_csv(self, job_id: str) -> str:
        """The trajectory as CSV text."""
        response = self.session.get(
            f"{self.base_url}/api/simulate/{job_id}/export", timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.text

    # -- catalogue and metrics -------------------------------------------

    def enzymes(self) -> Dict[str, Any]:
        """Enzymes the resolver recognises by name."""
        response = self.session.get(
            f"{self.base_url}/api/enzymes", timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def pipeline_metrics(self) -> Dict[str, Any]:
        """Stage-level metrics with Wilson confidence intervals."""
        response = self.session.get(
            f"{self.base_url}/api/simulate/metrics/pipeline", timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def dashboard_overview(self) -> Dict[str, Any]:
        """System state: queue, literature backing, STRENDA compliance."""
        response = self.session.get(
            f"{self.base_url}/api/dashboard/overview", timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------


def example_michaelis_menten(client: TerriumClient) -> None:
    """A simulation with every parameter supplied in the query."""
    job_id = client.simulate(
        "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51"
    )
    result = client.wait_for(job_id)
    print(f"  domain     : {result['domain']}")
    print(f"  points     : {len(result['trajectory'])}")
    print(f"  parameters : {result['parameters']}")


def example_missing_condition(client: TerriumClient) -> None:
    """What happens when a required condition is omitted.

    This is the behaviour most worth understanding: Terrium does not fill in
    s0/i0/end/points with plausible-looking numbers. It names them.
    """
    job_id = client.simulate("simulate sir beta=0.3 gamma=0.1")
    try:
        client.wait_for(job_id, attempts=30)
    except RuntimeError as exc:
        print(f"  refused, as designed: {exc}")


def example_provenance(client: TerriumClient) -> None:
    """Where each number came from, and whether it can be cited."""
    job_id = client.simulate(
        "simulate lactate dehydrogenase vmax=5 s0=10 end=10 points=51"
    )
    result = client.wait_for(job_id)

    for key, prov in sorted(result.get("parameterProvenance", {}).items()):
        origin = prov.get("origin")
        citation = prov.get("citation", "-")
        print(f"  {key:<8} {origin:<10} {citation}")

    audit = client.audit(job_id)
    print(f"  publication ready: {audit.get('readyToPublish')}")


def main() -> int:
    client = TerriumClient()

    try:
        client.health_check()
    except requests.RequestException:
        print(f"No Terrium server at {TERRIUM_URL}. Start it with `npm start`.")
        return 1

    for name, example in [
        ("Michaelis-Menten", example_michaelis_menten),
        ("A missing experimental condition", example_missing_condition),
        ("Provenance and publication audit", example_provenance),
    ]:
        print(f"\n{name}")
        print("-" * len(name))
        try:
            example(client)
        except Exception as exc:  # noqa: BLE001 - an example should show the error
            print(f"  {type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
