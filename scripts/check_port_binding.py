#!/usr/bin/env python3
"""A server with no authentication must not be published to every interface.

WHY THIS EXISTS
---------------
`docker-compose.yml` shipped:

    ports:
      - "3000:3000"
    environment:
      NODE_ENV: production
    restart: unless-stopped

Docker binds the short form to **0.0.0.0** -- every network interface. So the
shipped, production-labelled, auto-restarting configuration published
`src/web/server.js` to the whole local network, and on a cloud host to the
internet.

That server has no authentication, and `GET /api/jobs/history` returns the
last 50 jobs -- including the query text somebody typed -- to any caller.

The rest of that file is carefully hardened: `cap_drop: ALL`, `read_only`,
a non-root `USER`, tmpfs mounts. Somebody thought about container security.
All of it concerns what a compromised container can do, and none of it
concerns who can reach the port -- which for this server is the entire risk.

HOW IT WAS MISSED, WHICH IS THE PART WORTH RECORDING
-----------------------------------------------------
`SECURITY.md` said, in a section added one pass earlier by the same author
who wrote this guard:

    Run it on localhost. That is what `make web` and the Docker image are
    for, and it is the only configuration anyone here has treated as safe.

The Docker image was not a localhost configuration. The sentence was written
from an assumption about what a container "obviously" does, in a document
whose purpose was to state the deployment position accurately, in a project
whose whole rule is that claims get checked.

An audit that produces a confident false statement is worse than one that
finds nothing, because the statement then gets trusted. The correction is
recorded in SECURITY.md rather than quietly fixed.

WHAT IT CHECKS
--------------
Every host port published in a compose file binds to a loopback address,
UNLESS the server has authentication.

Conditional, like `check_deployment_warning.py`: if authentication is ever
added, exposing the port becomes a deliberate choice rather than an
accident, and this stops objecting. Both guards read the same signal from
the same file so they cannot disagree with each other.

WHAT IT DOES NOT CHECK
----------------------
Deployment done outside compose -- a bare `docker run -p 3000:3000`, a
Kubernetes manifest, a PaaS that ignores the file. No static check can see
those. Stated because a guard implying more coverage than it has is the
failure this project cares most about.

The authentication exemption reads `src/web/server.ts` only, and applies
only to services that compose BUILDS (a `build:` key -- this repository's
Dockerfile, whose CMD runs that server). A service pulled as an `image:`
(Prometheus, Grafana) is never exempted by it. Until 2026-10-31 the exemption
was global: authentication added to server.ts would have stopped this guard
checking the monitoring file's Prometheus and Grafana ports too, though
neither is that server. The `build:` signal is a heuristic: a built service
that runs something other than server.ts would be exempted with it.

Nor does it verify that a loopback binding is *sufficient*. A host with
Docker's userland proxy, an SSH tunnel, or a reverse proxy in front can
still reach it. This checks the default, not the deployment.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "src" / "web" / "server.ts"
#: The monitoring stack runs the same unauthenticated server, beside a
#: Prometheus with no login and a Grafana whose admin password was "admin"
#: until 2026-10-31. It published all three on 0.0.0.0 while only the root
#: file was read here.
#:
#: Each entry is a group of alternative spellings; at least one of each must
#: exist (the selftest checks every group, not only the last).
COMPOSE_GROUPS = [("docker-compose.yml", "docker-compose.yaml"),
                  ("deploy/monitoring/docker-compose-monitoring.yml",)]
COMPOSE_FILES = [name for group in COMPOSE_GROUPS for name in group]

#: A published port entry: "HOST:CONTAINER" or "IP:HOST:CONTAINER".
PORT_ENTRY = re.compile(r"^\s*-\s*[\"']?([0-9a-zA-Z.:\[\]]+)[\"']?\s*(?:#.*)?$")

LOOPBACK_PREFIXES = ("127.0.0.1:", "localhost:", "::1:", "[::1]:")

#: Same signals as check_deployment_warning.py, deliberately. Two guards
#: reading the same fact must not be able to disagree about it.
AUTH_SIGNALS = [
    re.compile(r"\bauthenticate\b", re.I),
    re.compile(r"req\.headers\[?['\"]?authorization", re.I),
    re.compile(r"\bbearer\b", re.I),
    re.compile(r"\bapi[_-]?key\b", re.I),
    re.compile(r"\brequireAuth\b"),
]


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"^\s*//.*$", "", text, flags=re.M)


def server_has_auth() -> bool:
    if not SERVER.exists():
        return False
    code = _strip_comments(SERVER.read_text(encoding="utf-8"))
    return any(signal.search(code) for signal in AUTH_SIGNALS)


def published_ports(text: str) -> List[tuple[int, str]]:
    """`(line number, entry)` for each published port under a `ports:` key."""
    return [(lineno, entry) for lineno, _, entry in ports_by_service(text)]


def built_services(text: str) -> set[str]:
    """Services with a `build:` key: built from this repository's Dockerfile,
    so they run `src/web/server.ts`. Only these can be exempted by it."""
    return {service for service, key in _service_keys(text) if key == "build"}


def _service_keys(text: str) -> List[tuple[str, str]]:
    """`(service, key)` for each direct key of each service under `services:`."""
    found: List[tuple[str, str]] = []
    in_services, service, service_indent, key_indent = False, "", -1, -1
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            in_services, service = stripped == "services:", ""
            continue
        if not in_services:
            continue
        if service_indent < 0 or indent <= service_indent:
            service_indent, service, key_indent = indent, stripped.rstrip(":"), -1
            continue
        if key_indent < 0:
            key_indent = indent
        if indent == key_indent and ":" in stripped:
            found.append((service, stripped.split(":", 1)[0]))
    return found


def ports_by_service(text: str) -> List[tuple[int, str, str]]:
    """`(line number, service, entry)` for each published port."""
    found: List[tuple[int, str, str]] = []
    in_ports = False
    ports_indent = 0
    service, service_indent = "", -1
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            service, service_indent = "", -1
        elif service_indent < 0 or indent <= service_indent:
            service, service_indent = stripped.rstrip(":"), indent
        if stripped.rstrip(":") == "ports" and stripped.endswith(":"):
            in_ports, ports_indent = True, indent
            continue
        if in_ports:
            # A key at or above the `ports:` indent ends the block.
            if indent <= ports_indent and not stripped.startswith("-"):
                in_ports = False
                continue
            match = PORT_ENTRY.match(line)
            if match:
                found.append((lineno, service, match.group(1)))
    return found


def is_loopback(entry: str) -> bool:
    """A published port bound to loopback, or not published to the host.

    A bare "3000" publishes the container port on an EPHEMERAL host port --
    still on 0.0.0.0. It is not treated as safe, because it is not.
    """
    return entry.startswith(LOOPBACK_PREFIXES)


def exposed_entries(text: str, server_auth: bool) -> List[tuple[int, str]]:
    """Non-loopback ports, minus those of built services when server.ts has
    authentication. The exemption is per service, never per file."""
    exempt = built_services(text) if server_auth else set()
    return [(lineno, entry) for lineno, service, entry in ports_by_service(text)
            if service not in exempt and not is_loopback(entry)]


def selftest() -> int:
    """Prove both branches and the parser.

    On a clean tree this reports zero findings forever, so the matcher needs
    exercising directly -- the lesson from four guards found on one day to
    be checking a narrower scope than anyone believed.
    """
    failures: List[str] = []

    loopback = ["127.0.0.1:3000:3000", "localhost:8080:80", "[::1]:3000:3000"]
    exposed = ["3000:3000", "0.0.0.0:3000:3000", "8080:3000", "3000"]
    for entry in loopback:
        if not is_loopback(entry):
            failures.append(f"loopback entry not recognised: {entry!r}")
    for entry in exposed:
        if is_loopback(entry):
            failures.append(f"exposed entry wrongly treated as loopback: {entry!r}")

    sample = (
        "services:\n"
        "  app:\n"
        "    ports:\n"
        '      - "127.0.0.1:3000:3000"\n'
        "      # a comment\n"
        "    environment:\n"
        "      PORT: 3000\n"
    )
    got = [e for _, e in published_ports(sample)]
    if got != ["127.0.0.1:3000:3000"]:
        failures.append(f"parser on a sample compose: expected one entry, got {got}")

    # `PORT: 3000` under `environment:` must not be read as a published port.
    if any("PORT" in e for _, e in published_ports(sample)):
        failures.append("parser read an environment variable as a published port")

    # The monitoring file's shape: list-form environment, volume mounts with
    # colons, and the three ports it shipped on 0.0.0.0.
    monitoring = (
        "services:\n"
        "  caterva:\n"
        "    ports:\n"
        '      - "3000:3000"\n'
        "    environment:\n"
        "      - PORT=3000\n"
        "  prometheus:\n"
        "    ports:\n"
        '      - "9090:9090"\n'
        "    volumes:\n"
        "      - ./prometheus.yml:/etc/prometheus/prometheus.yml\n"
        "  grafana:\n"
        "    ports:\n"
        '      - "127.0.0.1:3001:3000"\n'
    )
    got = [e for _, e in published_ports(monitoring)]
    if got != ["3000:3000", "9090:9090", "127.0.0.1:3001:3000"]:
        failures.append(f"parser on the monitoring shape: got {got}")
    if [e for e in got if not is_loopback(e)] != ["3000:3000", "9090:9090"]:
        failures.append("monitoring shape: the two exposed ports were not both flagged")
    # Every group, not only the last: the root file moving would otherwise
    # leave this guard reading only the monitoring file, and passing.
    for group in COMPOSE_GROUPS:
        if not any((REPO / name).exists() for name in group):
            failures.append(f"{' / '.join(group)} is listed but missing: moved, and no longer read")

    # The authentication exemption is per service: server.ts gaining auth
    # exempts only services built from this repository, never an `image:`.
    by_service = [(s, e) for _, s, e in ports_by_service(monitoring)]
    if by_service != [("caterva", "3000:3000"), ("prometheus", "9090:9090"),
                      ("grafana", "127.0.0.1:3001:3000")]:
        failures.append(f"ports not attributed to their services: got {by_service}")
    built = (
        "services:\n"
        "  caterva:\n"
        "    build:\n"
        "      context: ../..\n"
        "    ports:\n"
        '      - "3000:3000"\n'
        "  prometheus:\n"
        "    image: prom/prometheus:latest\n"
        "    ports:\n"
        '      - "9090:9090"\n'
        "volumes:\n"
        "  build:\n"
        "    driver: local\n"
    )
    if built_services(built) != {"caterva"}:
        failures.append(f"built services: expected {{'caterva'}}, got {built_services(built)}")
    still_flagged = [e for _, e in exposed_entries(built, server_auth=True)]
    if still_flagged != ["9090:9090"]:
        failures.append(
            "with server.ts authenticated, the image-based Prometheus port must "
            f"still be flagged and the built server's must not: got {still_flagged}"
        )
    if [e for _, e in exposed_entries(built, server_auth=False)] != ["3000:3000", "9090:9090"]:
        failures.append("without authentication, both exposed ports must be flagged")

    if failures:
        print("SELFTEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"SELFTEST OK: {len(loopback)} loopback form(s) accepted, "
        f"{len(exposed)} exposed form(s) rejected, and the parser reads a "
        "ports block without mistaking environment keys for entries."
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    files = [REPO / name for name in COMPOSE_FILES if (REPO / name).exists()]
    if not files:
        print("OK: no compose file found; nothing publishes a port here.")
        return 0

    auth = server_has_auth()
    if auth:
        print(
            "NOTE: src/web/server.ts appears to have authentication, so "
            "publishing the ports of\n    services built from this repository "
            "is a deliberate choice. Every other service\n    (an `image:`, "
            "such as Prometheus or Grafana) is still checked.\n"
            "\n    It does NOT mean the authentication is correct — see "
            "check_deployment_warning.py.\n"
        )

    problems: List[str] = []
    checked = 0
    for path in files:
        entries = published_ports(path.read_text(encoding="utf-8"))
        if not entries:
            # Per file: with two files read, one that parsed to nothing would
            # otherwise hide behind the other's count.
            print(
                f"FAIL: {path.relative_to(REPO)} exists but no published port "
                "was parsed out of it.\nThe parser is broken, not the file — a "
                "scan that finds nothing must not pass."
            )
            return 1
        checked += len(entries)
        for lineno, entry in exposed_entries(path.read_text(encoding="utf-8"), auth):
            problems.append(
                f"{path.relative_to(REPO)}:{lineno} publishes {entry!r} — "
                "bound to all interfaces."
            )

    if problems:
        print(f"Ports published to every interface ({len(problems)}):\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nUnless the NOTE above says otherwise, `src/web/server.ts` has NO "
            "AUTHENTICATION, and\n`GET /api/jobs/history` returns the last 50 "
            "jobs — including the query text\nsomebody typed — to any caller. "
            "Prometheus has no login at all.\n"
            "\nDocker binds the short form \"3000:3000\" to 0.0.0.0. Use "
            "\"127.0.0.1:3000:3000\"\nunless you have put authentication in "
            "front of it.\n"
            "\nThe container hardening in that file (cap_drop, read_only, "
            "non-root) is about\nwhat a compromised container can do. It does "
            "not address who can reach the port."
        )
        return 1

    print(
        f"OK: all {checked} published port(s) bind to loopback, which is the "
        "right default for a\n    server with no authentication."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
