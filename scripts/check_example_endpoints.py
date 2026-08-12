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
]

#: `router.get("/simulate/:jobId", ...)` across several formatting styles,
#: including the multi-line form Prettier produces:
#:     router.get(
#:       "/simulate/:jobId",
ROUTE_RE = re.compile(
    r"""(?:router|app)\.(get|post|put|patch|delete)\(\s*['"`]([^'"`]+)['"`]""",
    re.MULTILINE,
)

#: Where the router is mounted: `app.use("/api", router)`.
MOUNT_RE = re.compile(r"""app\.use\(\s*['"`](/[^'"`]*)['"`]\s*,\s*router""")

#: `f"{self.base_url}/api/simulate/{job_id}"` and friends.
CALL_RE = re.compile(r"""\{(?:self\.)?base_url\}(/[A-Za-z0-9_/:{}.-]*)""")


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

    return routes


def _to_pattern(route: str) -> re.Pattern[str]:
    """Turn `/api/simulate/:jobId` into a matcher for a concrete path."""
    parts = [
        r"[^/]+" if segment.startswith(":") else re.escape(segment)
        for segment in route.strip("/").split("/")
    ]
    return re.compile("^/" + "/".join(parts) + "$")


def example_calls(path: pathlib.Path) -> list[tuple[int, str]]:
    """(line number, endpoint) for each API call in an example file."""
    calls: list[tuple[int, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for match in CALL_RE.finditer(line):
            endpoint = match.group(1).rstrip("/") or "/"
            # `{job_id}` in an f-string is a value the caller supplies --
            # the same role `:jobId` plays on the server side.
            calls.append((number, re.sub(r"\{[^}]+\}", ":param", endpoint)))
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

    for path in EXAMPLE_FILES:
        if not path.is_file():
            violations.append(
                f"{path.relative_to(REPO_ROOT)} is listed in EXAMPLE_FILES "
                "but does not exist. Remove it from the list or restore the "
                "file; a missing example silently shrinks what is checked."
            )
            continue

        calls = example_calls(path)
        if not calls:
            violations.append(
                f"{path.relative_to(REPO_ROOT)} yielded no API calls. Either "
                "it stopped calling the API or CALL_RE stopped matching it; "
                "both are worth knowing, and neither is a pass."
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
            f"{len(EXAMPLE_FILES)} example file(s) all exist among the "
            f"{len(routes)} routes the API registers."
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
