"""The studio's API routes, as data: method, path pattern, handler name, what it returns.

WHY A TABLE AND NOT DECORATORS
------------------------------
The server, the page and the contract document all have to agree on the
same list, and it was written before any handler existed so five people
could build against it at once. A table can be read by a test without
starting anything: `caterva/tests/test_studio_contract.py` checks that
every route here is described in docs/studio/CONTRACT.md and that every
handler name is unique. The dispatch layer (owner: core) looks each handler
up by name on its handler object, so implementing a route never means
editing this file; adding or changing one means amending the contract.

Paths are matched after percent-decoding and never with a trailing slash.
`{id}` is a run id (RUN_ID_PATTERN), `{name}` an artifact name
(ARTIFACT_NAME_PATTERN), `{pdb_id}` a four-character PDB id, `{ec}` a complete EC number; anything else
in those positions is 404, not 400, so the table never echoes a path back.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

#: yyyymmdd-hhmmss-<kind with dots as dashes>-<8 hex>, e.g.
#: 20260930-141502-compose-3f9a0c1d. Sorts by time, and is a valid directory name on every platform.
RUN_ID_PATTERN = r"[0-9]{8}-[0-9]{6}-[a-z]+(?:-[a-z]+)?-[0-9a-f]{8}"

#: Artifact names are chosen by adapters from fixed vocabularies
#: ("model.sbml", "report.md"); a name from a request must match this and
#: be listed on the run record before anything is read.
ARTIFACT_NAME_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"

PDB_ID_PATTERN = r"[0-9][A-Za-z0-9]{3}"

#: A complete EC number, preliminary ones included ("3.2.1.n3"). Anything
#: else in that position is 404, so a path is never echoed back.
EC_PATTERN = r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,3}\.(?:n?[0-9]{1,4})"


@dataclass(frozen=True)
class Route:
    method: str
    #: A path with {placeholders}.
    path: str
    handler: str
    #: The response type name in contract.py, or a media type for a file.
    returns: str
    #: Whether the session token is required. False only for the
    #: development token endpoint, which exists only with --dev-origin.
    token: bool = True
    #: Only registered when the server was started with --dev-origin.
    dev_only: bool = False
    summary: str = ""
    #: Who supplies the handler: "core" (the dispatch layer's own handler
    #: object) or an adapter module in adapters.ADAPTER_MODULES, which
    #: registers it with Registry.add_endpoint. A route an adapter owns and
    #: has not registered answers 503 "unavailable", not 404.
    owner: str = "core"


ROUTES: Tuple[Route, ...] = (
    Route("GET", "/api/health", "health", "Health",
          summary="liveness, version and api_version"),
    Route("GET", "/api/capabilities", "capabilities", "Capabilities",
          summary="what this installation can do; ?probe=network checks the hosts"),
    Route("POST", "/api/capabilities/refresh", "refresh_capabilities", "Capabilities",
          summary="run the chosen gmx now and answer capabilities; the only request that runs it (body {})"),
    Route("GET", "/api/settings", "get_settings", "Settings"),
    Route("PUT", "/api/settings", "put_settings", "Settings",
          summary="replace the settings; unknown keys are malformed"),
    Route("GET", "/api/compose/shapes", "compose_shapes", "ShapesResponse",
          summary="grammar.shapes(), the mechanisms compose can build", owner="compose"),
    Route("POST", "/api/rates/preview", "rates_preview", "RatesPreview",
          summary="body {text, filename?, mapping?}: how a pasted or dropped table is read (delimiter, header, "
                  "decimal mark, units, columns), every decision and every problem by line and column; "
                  "never a 400 for a bad table, only for a body that is not a question", owner="rates"),
    Route("POST", "/api/organisms/normalise", "normalise_organism", "NormaliseOrganismResponse",
          summary="compose.organisms.normalise_organism, for form hints", owner="compose"),
    Route("GET", "/api/enzymes/find", "find_enzymes", "EnzymeFindResponse",
          summary="?q=&organism=&limit= the enzyme finder's ranked candidates (offline index; UniProt only "
                  "when nothing is found and the network is reachable)", owner="compose"),
    Route("GET", "/api/enzymes/{ec}", "enzyme_detail", "EnzymeDetail",
          summary="one enzyme of the nomenclature, with ?organism= its isozymes", owner="compose"),
    Route("GET", "/api/structure/{pdb_id}/coordinates", "structure_coordinates", "CoordinatesResponse",
          summary="atoms for the 3D viewer, from the entry's mmCIF (network, cached)", owner="structure"),
    Route("POST", "/api/runs", "create_run", "RunCreated",
          summary="start a run of any kind; 202"),
    Route("GET", "/api/runs", "list_runs", "RunList",
          summary="?kind=&status=&limit=&cursor= newest first"),
    Route("GET", "/api/runs/{id}", "get_run", "RunRecord"),
    Route("DELETE", "/api/runs/{id}", "delete_run", "RunSummary",
          summary="remove a finished run from the workspace; 409 while it runs"),
    Route("GET", "/api/runs/{id}/result", "get_result", "<kind result>",
          summary="the kind's Result; 409 until the run is done"),
    Route("GET", "/api/runs/{id}/events", "run_events", "text/event-stream",
          summary="SSE: replay from the start or Last-Event-ID, then live"),
    Route("POST", "/api/runs/{id}/cancel", "cancel_run", "RunRecord",
          summary="202; 409 when already finished"),
    Route("GET", "/api/runs/{id}/artifacts/{name}", "get_artifact", "<artifact media type>",
          summary="a file the run produced, by its recorded name"),
    Route("GET", "/api/runs/{id}/bundle", "get_bundle", "application/zip",
          summary="run.json, request.json, result.json, events.jsonl and artifacts; ?redact_paths=true (default) "
                  "writes the home folder as ~, ?diagnostics=false (default) leaves out tracebacks"),
    Route("GET", "/api/dev/session", "dev_session", "DevSession",
          token=False, dev_only=True,
          summary="the session token for the Vite dev server's index.html (--dev-origin only)"),
)


def compile_path(path: str) -> "re.Pattern[str]":
    """The regular expression a route's path matches, placeholders typed."""
    patterns = {"id": RUN_ID_PATTERN, "name": ARTIFACT_NAME_PATTERN, "pdb_id": PDB_ID_PATTERN, "ec": EC_PATTERN}

    def placeholder(match: "re.Match[str]") -> str:
        name = match.group(1)
        return f"(?P<{name}>{patterns[name]})"

    return re.compile("^" + re.sub(r"\{([a-z_]+)\}", placeholder, path) + "$")


def find(method: str, path: str, *, dev: bool) -> Tuple[Optional[Route], dict, bool]:
    """(route, path parameters, path matched some route).

    The third value distinguishes 405 (the path exists with another method)
    from 404.
    """
    matched_path = False
    for route in ROUTES:
        if route.dev_only and not dev:
            continue
        m = compile_path(route.path).match(path)
        if not m:
            continue
        matched_path = True
        if route.method == method:
            return route, m.groupdict(), True
    return None, {}, matched_path


__all__ = ["ARTIFACT_NAME_PATTERN", "EC_PATTERN", "PDB_ID_PATTERN", "ROUTES", "RUN_ID_PATTERN", "Route",
           "compile_path", "find"]
