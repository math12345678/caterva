#!/usr/bin/env python3
"""If the web server has no authentication, SECURITY.md must say so.

WHY THIS EXISTS
---------------
`src/web/server.ts` has no authentication of any kind, and
`GET /api/jobs/history` returns the last 50 jobs -- the query text somebody
typed, their parameters and their results -- to any caller. There is no
per-user separation because there are no users.

On a shared instance every student can read every other student's queries.

That is a defensible state for a pre-launch tool meant to run on localhost.
What was not defensible is that **nothing said so**, in seven passes of
audit. A reader could open the dashboard, see a working simulation tool with
a history panel, and have no reason to suspect the panel was showing them
somebody else's work.

Terrium is aimed at teaching labs, which makes the omission worse than it
would be for a developer tool: the person deploying it may be a teacher, and
the people using it may be minors.

WHAT IT CHECKS
--------------
A conditional, which is the part worth getting right:

    IF the server has no authentication
    THEN SECURITY.md must carry the deployment warning

**If authentication is ever added, this guard stops demanding the warning.**
A check that kept insisting on "there is no authentication" after somebody
built some would be teaching people to ignore it, and would eventually be
deleted along with the useful half.

WHAT "HAS AUTHENTICATION" MEANS HERE
------------------------------------
A crude signal: the server module mentions a recognisable auth mechanism
outside a comment. That is deliberately loose in the safe direction -- it
will not notice a bad implementation, and it does not try to.

This guard cannot assess whether authentication *works*. It only decides
which of two documents the repository owes its readers. Anyone adding auth
should expect a real review, and this guard going quiet is not one.

WHAT IT DOES NOT CHECK
----------------------
The API server in `Science-Agent-Pipeline/artifacts/api-server` is a separate
surface with its own routes. SECURITY.md's own correction banner notes that
it was previously mis-scoped. It is out of scope here rather than silently
included, because a guard that claims to cover two servers while checking
one is worse than a guard that covers one and says so.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "src" / "web" / "server.ts"
SECURITY = REPO / "SECURITY.md"

#: Signals that some authentication exists. Loose on purpose.
AUTH_SIGNALS = [
    re.compile(r"\bauthenticate\b", re.I),
    re.compile(r"\bauthorization\s*header\b", re.I),
    re.compile(r"req\.headers\[?['\"]?authorization", re.I),
    re.compile(r"\bbearer\b", re.I),
    re.compile(r"\bapi[_-]?key\b", re.I),
    re.compile(r"\brequireAuth\b"),
    re.compile(r"\bsession\b", re.I),
]

#: What the warning must actually say. Each phrase is load-bearing: a
#: warning that omits any of them leaves a reader with a wrong picture.
REQUIRED_PHRASES = [
    ("no authentication", "that the server is open"),
    ("/api/jobs/history", "the specific endpoint that leaks other people's queries"),
    ("localhost", "where it IS safe to run, so the warning is actionable"),
]


def _strip_comments(text: str) -> str:
    """Remove // and /* */ comments, so prose about auth is not mistaken for auth."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    return text


def server_has_auth() -> bool:
    if not SERVER.exists():
        return False
    code = _strip_comments(SERVER.read_text(encoding="utf-8"))
    return any(signal.search(code) for signal in AUTH_SIGNALS)


def selftest() -> int:
    """Prove both branches, and that comments do not count as authentication.

    The conditional is the whole design, so both sides need exercising. A
    guard that only ever ran the "no auth" branch would silently keep
    demanding the warning forever, which is the failure this file's own
    docstring argues against.
    """
    failures: List[str] = []

    looks_like_auth = [
        "  if (!authenticate(req)) return res.writeHead(401).end();",
        "  const key = req.headers['authorization'];",
        "  if (token !== process.env.API_KEY) { ... }",
        "  const session = await getSession(req);",
    ]
    not_auth = [
        "  // there is no authentication on this server -- see SECURITY.md",
        "  /* authorization header handling is NOT implemented */",
        "  const authors = paper.authors || [];",
        "  res.writeHead(200, { 'Content-Type': 'application/json' });",
    ]

    for line in looks_like_auth:
        code = _strip_comments(line)
        if not any(s.search(code) for s in AUTH_SIGNALS):
            failures.append(f"auth not detected in: {line.strip()!r}")
    for line in not_auth:
        code = _strip_comments(line)
        if any(s.search(code) for s in AUTH_SIGNALS):
            failures.append(f"auth wrongly detected in: {line.strip()!r}")

    # The warning text itself must be detectable as absent.
    complete = (
        "There is no authentication. GET /api/jobs/history returns everyone's "
        "queries. Run it on localhost."
    )
    for phrase, _ in REQUIRED_PHRASES:
        if phrase.lower() not in complete.lower():
            failures.append(f"a complete warning was read as missing {phrase!r}")
        if phrase.lower() in complete.replace(phrase, "").lower():
            failures.append(f"removing {phrase!r} did not make it undetectable")

    if failures:
        print("SELFTEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"SELFTEST OK: {len(looks_like_auth)} auth form(s) detected, "
        f"{len(not_auth)} non-auth form(s) (including comments ABOUT auth) "
        f"ignored, and {len(REQUIRED_PHRASES)} required phrase(s) detectable "
        "both present and absent."
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    if not SERVER.exists():
        print(f"FAIL: {SERVER.relative_to(REPO)} not found; nothing was checked.")
        return 1

    if server_has_auth():
        print(
            "OK: src/web/server.ts appears to have authentication, so the "
            "no-auth deployment\n    warning is no longer required.\n"
            "\n    This guard does NOT assess whether that authentication is "
            "correct. Somebody\n    should review it properly, and this "
            "going quiet is not that review."
        )
        return 0

    if not SECURITY.exists():
        print(
            "FAIL: the web server has no authentication and SECURITY.md does "
            "not exist.\nA reader has no way to learn that the job history is "
            "shared."
        )
        return 1

    text = SECURITY.read_text(encoding="utf-8")
    missing = [
        (phrase, why)
        for phrase, why in REQUIRED_PHRASES
        if phrase.lower() not in text.lower()
    ]

    if missing:
        print(
            f"The web server has no authentication, and SECURITY.md is "
            f"missing {len(missing)} part(s) of the warning:\n"
        )
        for phrase, why in missing:
            print(f"  - {phrase!r} — {why}")
        print(
            "\n`GET /api/jobs/history` returns the last 50 jobs, including the "
            "query text\nsomebody typed, to any caller. On a shared instance "
            "every student can read\nevery other student's queries.\n"
            "\nEither restore the warning, or add authentication -- in which "
            "case this guard\nstops asking. Do not delete the guard: the "
            "exposure is there either way."
        )
        return 1

    print(
        "OK: the web server has no authentication, and SECURITY.md says so — "
        "naming the\n    endpoint that shares job history and where it is safe "
        "to run."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
