"""Guard that documented API examples call endpoints that exist.

WHAT THIS CAUGHT ON ITS FIRST RUN

`examples/python_integration.py` is the client example
`QUICK_START_DEPLOYMENT.md` points readers at. Ten of the eleven endpoints
it called did not exist:

    /api/health           -> the route is /api/healthz
    /api/jobs/<id>        -> the route is /api/simulate/<jobId>
    /api/export/jobs/csv  -> the route is /api/simulate/<jobId>/export
    /api/jobs/query, /api/batch, /api/batches/<id>, /api/sweep,
    /api/sweeps/<id>, /api/compare/jobs, /api/stats
                          -> no such routes, at all

Only `POST /api/simulate` was real. Someone following the quick start would
have got a 404 on essentially every call, and concluded the product was
broken rather than the documentation.

Nothing could have noticed. The example is Python, so `tsc` never sees it;
it makes no network calls at import time, so no test exercises it; and the
orphan guard's complaint -- "imported by nothing" -- is the wrong diagnosis,
because an example is *meant* to be read rather than imported. It was
simultaneously unreachable and wrong, and the two conditions hid each other.

WHAT IT CHECKS

Every `{base_url}/api/...` path in `EXAMPLE_FILES`, resolved against the
routes actually registered by the Express app, with `:param` segments and
Python `{placeholders}` treated as wildcards.

This is a text-level check, not a live one: it needs no server, so it runs
in the fast path alongside the other static guards. It cannot tell whether
the request BODY is right -- only that the address exists. That is the
larger half of the defect it found, and worth saying plainly rather than
implying more coverage than there is.

Run directly: python scripts/check_example_endpoints.py
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

API_SERVER = REPO_ROOT / "Science-Agent-Pipeline" / "artifacts" / "api-server"
ROUTES_DIR = API_SERVER / "src" / "routes"
APP_FILE = API_SERVER / "src" / "app.ts"

#: Files whose documented endpoints must exist. Add to this rather than
#: writing a new guard: an example is a promise, and every promise in the
#: repository should be checkable.
EXAMPLE_FILES = [
    REPO_ROOT / "examples" / "python_integration.py",
    REPO_ROOT / "examples" / "nodejs_integration.js",
]

#: Markdown that documents the HTTP API, and must therefore describe the
#: API that exists.
#:
#: Added after a sweep of the repository root found **242 of 294 endpoint
#: mentions wrong across 23 documents — 82%**. Whole families of endpoints
#: were described in detail and had never existed: `/api/batch`,
#: `/api/sweep`, `/api/compare/jobs`, `/api/analyze/sweep/<id>`,
#: `/api/jobs/<id>`, `/api/stats`, `/api/literature/search`.
#:
#: Eighteen of those documents open with a hand-written "CORRECTION" banner
#: admitting their own claims are unverified. That is the wrong repair:
#: a reader who has been told the document is unreliable still reads the
#: endpoint table, and a disclaimer does not make a wrong URL right. The
#: fix for a false claim is to make it true or remove it, and then to make
#: it checkable so it cannot rot again.
#:
#: Only documents that are meant to be FOLLOWED belong here. Narrative
#: records (Business/build-stages/**) are deliberately excluded: they
#: describe what was true on a date, and rewriting history to satisfy a
#: guard would destroy the thing that makes them worth keeping.
#: Each entry is (path, must_document_endpoints).
#:
#: `docs/API.md` is the reference: if it stops naming any endpoint, the
#: reference has been gutted and that is a failure. `API_DOCUMENTATION.md`
#: is now a signpost pointing at it, and legitimately names none — but if
#: fabricated endpoints reappear there, they must still be caught. So the
#: two questions are separated: "does this file describe the API" and "is
#: what it describes true".
DOC_FILES: list[tuple[pathlib.Path, bool]] = [
    (REPO_ROOT / "API_DOCUMENTATION.md", False),
    (REPO_ROOT / "docs" / "API.md", True),
]

#: `router.get("/simulate/:jobId", ...)` across several formatting styles,
#: including the multi-line form Prettier produces:
#:     router.get(
#:       "/simulate/:jobId",
ROUTE_RE = re.compile(
    r"""(?:router|app)\.(get|post|put|patch|delete)\(\s*['"`]([^'"`]+)['"`]""",
    re.MULTILINE,
)

#: THIS PROJECT SERVES TWO HTTP APIS, and the first version of this guard
#: knew about only one.
#:
#: `Science-Agent-Pipeline/artifacts/api-server/` is Express and matched
#: ROUTE_RE. `src/web/server.ts` is a raw `http.createServer` that
#: dispatches on `pathname === '/api/...'` and `pathname.match(/^\/api\/...`,
#: so ROUTE_RE never saw a single one of its routes.
#:
#: The consequence was not a missed check but a WRONG one: measured against
#: half the route table, this guard reported 242 of 294 endpoint mentions
#: across the documentation as nonexistent. Many of them were real. A
#: checker whose source of truth is incomplete does not fail quietly — it
#: produces confident false accusations, and I acted on several before
#: noticing.
#:
#: Recorded rather than tidied away, because the shape recurs: it is the
#: same defect as `check_typescript_compiles` deciding membership by walking
#: up to a tsconfig that matched everything (Part 14), and as a citation
#: guard parsing zero entries and printing OK (Part 20). The lesson is that
#: a guard must be able to say how much of the world it looked at.
WEB_SERVER = REPO_ROOT / "src" / "web" / "server.ts"

#: `pathname === '/api/stats'`
PATHNAME_EQ_RE = re.compile(r"""pathname\s*===\s*['"`]([^'"`]+)['"`]""")

#: `pathname.match(/^\/api\/jobs\/[a-z0-9_]+$/i)` -- the parameterised
#: routes. The regex body is converted to a route pattern by replacing each
#: character-class or wildcard segment with `:param`.
PATHNAME_MATCH_RE = re.compile(r"""pathname\.match\(\s*/\^(.+?)/[gimsuy]*\s*\)""")

#: Where the router is mounted: `app.use("/api", router)`.
MOUNT_RE = re.compile(r"""app\.use\(\s*['"`](/[^'"`]*)['"`]\s*,\s*router""")

#: Any `/api/...` path in a string or template literal, in any language.
#:
#: The first version matched only Python's `f"{self.base_url}/api/..."`.
#: `examples/nodejs_integration.js` writes `axios.get('/api/health')` and
#: `` `/api/jobs/${jobId}` ``, so it matched NOTHING — and the guard would
#: have reported "no API calls" rather than the eleven wrong endpoints it
#: actually contained. A checker that only understands one of the two
#: example files it is pointed at is a checker with a blind spot the size of
#: the thing it missed.
#:
#: Anchoring on `/api/` rather than on how the base URL is spelled keeps it
#: language-agnostic; `${...}` and `{...}` placeholders are normalised to a
#: wildcard below.
CALL_RE = re.compile(r"""['"`]?(/api/[A-Za-z0-9_/:${}.-]*)""")


def _mount_prefix() -> str:
    if not APP_FILE.is_file():
        raise FileNotFoundError(
            f"{APP_FILE} does not exist, so the route table could not be "
            "read. Refusing to report success: with no routes parsed, every "
            "example endpoint would look wrong, or (worse) the check would "
            "pass vacuously."
        )
    match = MOUNT_RE.search(APP_FILE.read_text(encoding="utf-8"))
    return match.group(1).rstrip("/") if match else ""


def registered_routes() -> set[str]:
    """Every path the Express app serves, mount prefix included."""
    prefix = _mount_prefix()
    routes: set[str] = set()

    sources = [APP_FILE]
    if ROUTES_DIR.is_dir():
        sources += sorted(ROUTES_DIR.glob("*.ts"))

    for path in sources:
        if not path.is_file() or ".test." in path.name:
            continue
        for match in ROUTE_RE.finditer(path.read_text(encoding="utf-8")):
            route = match.group(2)
            if not route.startswith("/"):
                continue
            full = route if path == APP_FILE else f"{prefix}{route}"
            routes.add(full.rstrip("/") or "/")

    routes |= _web_server_routes()
    return routes


def _web_server_routes() -> set[str]:
    """Routes served by the raw-http server in `src/web/server.ts`."""
    if not WEB_SERVER.is_file():
        # Not a silent skip: this file is half the route table, and
        # pretending it is empty is what produced the false accusations
        # documented above.
        raise FileNotFoundError(
            f"{WEB_SERVER} does not exist, so half the API's routes could "
            "not be read. Refusing to check documentation against a route "
            "table known to be incomplete."
        )

    text = WEB_SERVER.read_text(encoding="utf-8")
    routes = {match.group(1).rstrip("/") or "/" for match in PATHNAME_EQ_RE.finditer(text)}

    for match in PATHNAME_MATCH_RE.finditer(text):
        # `\/api\/jobs\/[a-z0-9_]+$` -> `/api/jobs/:param`
        raw = match.group(1).replace("\\/", "/")
        anchored = raw.endswith("$")
        body = raw.rstrip("$")

        segments = [s for s in body.split("/") if s]
        cleaned = [
            ":param" if re.search(r"[\[\].*+]", segment) else segment
            for segment in segments
        ]

        # An UNANCHORED pattern ending in `/` is a prefix match:
        # `/^\/api\/batches\//` accepts `/api/batches/<anything>`. Without
        # this the route was recorded as `/api/batches`, which is not a path
        # the server serves -- so a document correctly citing
        # `/api/batches/<id>` would have been reported as wrong.
        if not anchored and body.endswith("/"):
            cleaned.append(":param")

        if cleaned:
            routes.add("/" + "/".join(cleaned))

    return routes


def _to_pattern(route: str) -> re.Pattern[str]:
    """Turn `/api/simulate/:jobId` into a matcher for a concrete path."""
    parts = [
        r"[^/]+" if segment.startswith(":") else re.escape(segment)
        for segment in route.strip("/").split("/")
    ]
    return re.compile("^/" + "/".join(parts) + "$")


def _is_prose(line: str, state: dict) -> bool:
    """Whether this line is a comment or docstring rather than code.

    Needed because the guard's own fix notes list the endpoints that USED to
    be wrong. Flagging a comment that documents a past defect would make the
    only honest way to record the history a build failure — which is a good
    way to teach people to delete the history.

    Tracks Python `\"\"\"` docstrings and JS `/* */` blocks, and skips `#`,
    `//` and `*` line comments. Deliberately simple: it only has to be right
    about the two example files, and being wrong in the safe direction
    (treating code as prose) costs a missed check, not a false alarm.
    """
    stripped = line.strip()

    if state.get("in_block"):
        if state["in_block"] in stripped:
            state["in_block"] = None
        return True

    for opener, closer in (('"""', '"""'), ("'''", "'''"), ("/*", "*/")):
        if stripped.startswith(opener):
            # A docstring opened and closed on one line is wholly prose.
            if stripped.count(opener) < 2 and closer not in stripped[len(opener):]:
                state["in_block"] = closer
            return True

    return stripped.startswith(("#", "//", "*"))


def example_calls(path: pathlib.Path) -> list[tuple[int, str]]:
    """(line number, endpoint) for each API call in an example file."""
    calls: list[tuple[int, str]] = []
    state: dict = {"in_block": None}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if _is_prose(line, state):
            continue
        for match in CALL_RE.finditer(line):
            endpoint = match.group(1).rstrip("/") or "/"
            # `{job_id}` (Python) and `${jobId}` (JS template literal) are
            # both values the caller supplies -- the same role `:jobId`
            # plays on the server side.
            endpoint = re.sub(r"\$?\{[^}]*\}", ":param", endpoint)
            calls.append((number, endpoint))
    return calls


def check() -> list[str]:
    """Returns a list of violation strings, empty when every example is true."""
    routes = registered_routes()
    if not routes:
        return [
            "parsed ZERO routes from the api-server. Refusing to report "
            "success: with no route table there is nothing to check against, "
            "and every example would be reported wrong. A guard that cannot "
            "distinguish 'all correct' from 'nothing read' is worse than no "
            "guard, because it is trusted."
        ]

    patterns = [(route, _to_pattern(route)) for route in sorted(routes)]
    violations: list[str] = []
    checked = 0

    targets: list[tuple[pathlib.Path, bool]] = [
        (path, True) for path in EXAMPLE_FILES
    ] + DOC_FILES

    for path, must_document in targets:
        if not path.is_file():
            violations.append(
                f"{path.relative_to(REPO_ROOT)} is listed in EXAMPLE_FILES "
                "but does not exist. Remove it from the list or restore the "
                "file; a missing example silently shrinks what is checked."
            )
            continue

        calls = example_calls(path)
        if not calls:
            if must_document:
                violations.append(
                    f"{path.relative_to(REPO_ROOT)} yielded no API calls. "
                    "Either it stopped describing the API or CALL_RE stopped "
                    "matching it; both are worth knowing, and neither is a "
                    "pass."
                )
            continue

        relative = path.relative_to(REPO_ROOT)
        for line, endpoint in calls:
            checked += 1
            if any(pattern.match(endpoint) for _route, pattern in patterns):
                continue
            near = [r for r in sorted(routes) if r.split("/")[:3] == endpoint.split("/")[:3]]
            hint = f" Closest registered: {', '.join(near[:3])}." if near else ""
            violations.append(
                f"{relative}:{line} documents {endpoint}, which the API does "
                f"not serve.{hint} A reader following this example gets a 404 "
                "and concludes the product is broken."
            )

    if not violations:
        print(
            f"OK: {checked} documented endpoint(s) across "
            f"{len(EXAMPLE_FILES)} example file(s) and {len(DOC_FILES)} "
            f"doc(s) all exist among the {len(routes)} routes the API "
            "registers."
        )
    return violations


def main() -> int:
    violations = check()
    if not violations:
        return 0

    print(f"Example endpoints that do not exist ({len(violations)}):\n")
    for violation in violations:
        print(f"  {violation}")
    print(
        "\nAn example nobody checks is documentation that rots. Fix the "
        "example, or the route."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
