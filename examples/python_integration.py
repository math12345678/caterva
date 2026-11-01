#!/usr/bin/env python3
"""
Caterva Python Integration Examples

Working examples of the Caterva web API from Python.

WHICH SERVER THIS TALKS TO
--------------------------
Caterva serves TWO HTTP APIs, and they are not interchangeable:

  * `src/web/server.ts` — the root tree's own server, started with
    `npm run web`. THIS FILE TARGETS THAT ONE. It exposes /api/simulate,
    /api/jobs/<id>, /api/sweep, /api/batch, /api/compare, /api/stats and the
    CSV export routes, and accepts `{query, parameters, enzyme, substrate}`.

  * `Science-Agent-Pipeline/artifacts/api-server/` — the Express service,
    documented in `docs/API.md`. Different routes (/api/healthz,
    /api/simulate/<jobId>) and a different request shape: parameters go
    INSIDE the query string there, because that resolver refuses to invent
    an experimental condition it was not given.

Pointing a client at the wrong one produces 404s that look like the product
is broken. `scripts/check_example_endpoints.py` checks every endpoint below
against the routes both servers actually register.

Requires: pip install requests
"""

import sys
import time
from typing import Any, Dict, List, Optional

import requests

CATERVA_URL = "http://localhost:3000"
API_TIMEOUT = 30


class CatervaClient:
    """Python client for the Caterva web API (`src/web/server.ts`)."""

    def __init__(self, base_url: str = CATERVA_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _get(self, path: str, **kwargs: Any) -> Any:
        response = self.session.get(
            f"{self.base_url}{path}", timeout=API_TIMEOUT, **kwargs
        )
        response.raise_for_status()
        return response.json()

    # -- health and stats -------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        return self._get("/api/health")

    def statistics(self) -> Dict[str, Any]:
        """Aggregate job statistics."""
        return self._get("/api/stats")

    # -- running a simulation ---------------------------------------------

    def simulate(
        self,
        query: str,
        parameters: Dict[str, float],
        enzyme: Optional[str] = None,
        substrate: Optional[str] = None,
    ) -> str:
        """Enqueue a simulation, return its job id.

        Supplying `enzyme` and `substrate` makes the server search PubMed
        for kinetics before running, so the result carries literature
        backing. Omit them and the run uses exactly the parameters given.
        """
        payload: Dict[str, Any] = {"query": query, "parameters": parameters}
        if enzyme:
            payload["enzyme"] = enzyme
        if substrate:
            payload["substrate"] = substrate

        response = self.session.post(
            f"{self.base_url}/api/simulate", json=payload, timeout=API_TIMEOUT
        )
        if response.status_code == 400:
            raise ValueError(f"Rejected: {response.text}")
        response.raise_for_status()
        return response.json()["jobId"]

    def get_job(self, job_id: str) -> Dict[str, Any]:
        return self._get(f"/api/jobs/{job_id}")

    def wait_for(
        self, job_id: str, attempts: int = 60, interval: float = 0.5
    ) -> Dict[str, Any]:
        """Poll to completion.

        Raises on failure rather than returning None. A failed job is a
        result, not the absence of one — its error names what went wrong,
        which is usually the thing the caller needs to read.
        """
        for _ in range(attempts):
            job = self.get_job(job_id)
            status = job.get("status")
            if status in ("complete", "completed"):
                return job
            if status in ("error", "failed"):
                raise RuntimeError(f"Job {job_id} failed: {job.get('error')}")
            time.sleep(interval)
        raise TimeoutError(
            f"Job {job_id} did not finish in {attempts * interval:.0f}s"
        )

    # -- history ----------------------------------------------------------

    def job_history(self) -> Dict[str, Any]:
        """The 50 most recent jobs."""
        return self._get("/api/jobs/history")

    def query_jobs(self, filters: str) -> Dict[str, Any]:
        """Filtered job query, e.g. `status=complete&minConfidence=0.9`.

        Date filters bound `startTime` at both ends, so a job that errored
        or is still running still appears in its window — those are usually
        the ones worth looking at.
        """
        return self._get(f"/api/jobs/query?{filters}")

    def export_jobs_csv(self) -> str:
        response = self.session.get(
            f"{self.base_url}/api/export/jobs/csv", timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.text

    # -- sweeps, batches, comparison --------------------------------------

    def sweep(
        self,
        query: str,
        base_parameters: Dict[str, float],
        sweep_parameters: List[Dict[str, str]],
    ) -> str:
        """Run one parameter across a range. Returns a sweep id."""
        response = self.session.post(
            f"{self.base_url}/api/sweep",
            json={
                "query": query,
                "baseParameters": base_parameters,
                "sweepParameters": sweep_parameters,
            },
            timeout=API_TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("sweepId")

    def get_sweep(self, sweep_id: str) -> Dict[str, Any]:
        return self._get(f"/api/sweeps/{sweep_id}")

    def batch(
        self,
        query: str,
        parameter_sets: List[Dict[str, float]],
        base_parameters: Optional[Dict[str, float]] = None,
    ) -> str:
        """Run many parameter sets. Returns a batch id.

        `base_parameters` are merged UNDER each set, so a value common to
        every run is stated once. The validator checks the merged result,
        which is what the engine runs.
        """
        payload: Dict[str, Any] = {"query": query, "parameterSets": parameter_sets}
        if base_parameters:
            payload["baseParameters"] = base_parameters

        response = self.session.post(
            f"{self.base_url}/api/batch", json=payload, timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.json().get("batchId")

    def get_batch(self, batch_id: str) -> Dict[str, Any]:
        return self._get(f"/api/batches/{batch_id}")

    def compare_jobs(self, job_ids: List[str]) -> Dict[str, Any]:
        """Compare finished jobs against each other."""
        response = self.session.post(
            f"{self.base_url}/api/compare/jobs",
            json={"jobIds": job_ids},
            timeout=API_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------


def example_simulation(client: CatervaClient) -> Optional[str]:
    job_id = client.simulate(
        query="michaelis-menten",
        parameters={"km": 5.2, "vmax": 12.8, "s0": 10.0},
    )
    job = client.wait_for(job_id)
    result = job.get("result", {})
    print(f"  final value : {result.get('finalValue')}")
    print(f"  confidence  : {result.get('confidence')}")
    print(f"  validated   : {result.get('validated')}")
    return job_id


def example_literature_backed(client: CatervaClient) -> None:
    """With enzyme and substrate, the server looks up real kinetics first."""
    job_id = client.simulate(
        query="michaelis-menten",
        parameters={"km": 5.2, "vmax": 12.8, "s0": 10.0},
        enzyme="lactate dehydrogenase",
        substrate="pyruvate",
    )
    job = client.wait_for(job_id, attempts=120)
    result = job.get("result", {})
    print(f"  validated against literature: {result.get('validated')}")


def example_sweep(client: CatervaClient) -> None:
    sweep_id = client.sweep(
        query="michaelis-menten",
        base_parameters={"vmax": 12.8, "s0": 10.0},
        sweep_parameters=[{"name": "km", "spec": "1:10:1"}],
    )
    print(f"  sweep id: {sweep_id}")


def example_statistics(client: CatervaClient) -> None:
    stats = client.statistics()
    for key in ("totalJobs", "successful", "failed"):
        print(f"  {key:<12} {stats.get(key)}")


def main() -> int:
    client = CatervaClient()

    try:
        client.health_check()
    except requests.RequestException:
        print(f"No Caterva web server at {CATERVA_URL}. Start it with `npm run web`.")
        return 1

    for name, example in [
        ("A simulation", example_simulation),
        ("Literature-backed kinetics", example_literature_backed),
        ("A parameter sweep", example_sweep),
        ("Statistics", example_statistics),
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
