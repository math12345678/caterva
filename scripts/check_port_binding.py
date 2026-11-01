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
COMPOSE_FILES = ["docker-compose.yml", "docker-compose.yaml"]

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
    found: List[tuple[int, str]] = []
    in_ports = False
    ports_indent = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        indent = len(line) - len(line.lstrip())
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
                found.append((lineno, match.group(1)))
    return found


def is_loopback(entry: str) -> bool:
    """A published port bound to loopback, or not published to the host.

    A bare "3000" publishes the container port on an EPHEMERAL host port --
    still on 0.0.0.0. It is not treated as safe, because it is not.
    """
    return entry.startswith(LOOPBACK_PREFIXES)


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

    if server_has_auth():
        print(
            "OK: src/web/server.ts appears to have authentication, so "
            "publishing the port is\n    a deliberate choice rather than an "
            "accident. This guard stops objecting.\n"
            "\n    It does NOT mean the authentication is correct — see "
            "check_deployment_warning.py."
        )
        return 0

    problems: List[str] = []
    checked = 0
    for path in files:
        for lineno, entry in published_ports(path.read_text(encoding="utf-8")):
            checked += 1
            if not is_loopback(entry):
                problems.append(
                    f"{path.name}:{lineno} publishes {entry!r} — bound to all "
                    "interfaces."
                )

    if checked == 0:
        print(
            "FAIL: a compose file exists but no published port was parsed out "
            "of it.\nThe parser is broken, not the file — a scan that finds "
            "nothing must not pass."
        )
        return 1

    if problems:
        print(f"Ports published to every interface ({len(problems)}):\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\n`src/web/server.ts` has NO AUTHENTICATION, and "
            "`GET /api/jobs/history` returns\nthe last 50 jobs — including the "
            "query text somebody typed — to any caller.\n"
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
