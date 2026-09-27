#!/usr/bin/env python3
"""If the code can send user text to a third party, the privacy doc must say so.

WHY THIS EXISTS
---------------
`llmResolver.ts` can send the query somebody typed to one of six external
providers -- OpenAI, Groq, OpenRouter, Mistral, SiliconFlow, TokenRouter.
The payload is `{ role: "user", content: query }`: the raw text.

`docs/PRIVACY.md` said:

    No cookies, no localStorage, no analytics, no telemetry, no third-party
    requests **from the page itself**.

That qualifier made a misleading sentence technically true. The page does
not call anyone; the server does. A user's query text reaching OpenAI is a
third-party disclosure regardless of which machine initiates the request,
and a privacy document that hides behind "from the page itself" is doing the
opposite of its job.

I wrote that sentence, one pass earlier, in the document whose entire
purpose is to describe this accurately. It is the second time in two passes
that a security or privacy claim I wrote turned out narrower than the truth
-- the first was "the Docker image is a localhost configuration", which was
simply wrong. Both were written from what seemed obvious rather than from
reading the code.

WHAT IS ACTUALLY THE CASE, AND IS FINE
---------------------------------------
  * It is **off by default**. No API key, no request: `getApiKey()` returns
    undefined and `resolveWithLLM` returns `null`.
  * No key is committed. Keys come from environment variables, `.env` is
    gitignored (`*.env` too), and only `.env.example` templates are tracked.
  * Only the query goes -- not the email waitlist, not job history.

The defect was never the capability. It was the disclosure.

WHAT IT CHECKS
--------------
A conditional, the same shape as the auth and collection guards:

    IF the code can call an external LLM provider
    THEN docs/PRIVACY.md must say so, name that it is off by default, and
         say that the provider's terms govern what is sent

If the LLM path is ever removed, this stops asking.

WHAT IT DOES NOT CHECK
----------------------
**Whether enabling it is lawful for you.** That depends on your users, your
jurisdiction and the provider's data-processing terms. This checks that the
capability is disclosed, not that the disclosure is sufficient -- and a
school deploying this needs its own answer, not this file's.

It also does not detect a NEW third-party call added somewhere else. It
watches the one module known to make them. A second module doing the same
thing elsewhere would be invisible here, which is the narrow-scope failure
this project has now found seven times; stated so the next person knows
where to widen it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parent.parent
RESOLVER = (
    REPO / "Science-Agent-Pipeline" / "artifacts" / "api-server"
    / "src" / "lib" / "llmResolver.ts"
)
PRIVACY = REPO / "docs" / "PRIVACY.md"

#: Evidence the module can reach an external provider.
CALLS_OUT = [
    re.compile(r"https://api\.(openai|groq|mistral)\.", re.I),
    re.compile(r"https://openrouter\.ai/", re.I),
    re.compile(r"\bchat/completions\b"),
]

#: What PRIVACY.md must cover once it can.
REQUIRED = [
    (re.compile(r"\bllm\b|language[- ]model", re.I),
     "that an LLM provider can be called at all"),
    (re.compile(r"off (unless|by default)|disabled by default", re.I),
     "that it is OFF by default -- the difference between a capability and a practice"),
    (re.compile(r"\bquery\b", re.I),
     "what is actually sent"),
    (re.compile(r"their terms|provider'?s?\s+(data|terms)|retention", re.I),
     "that the provider's terms govern it, not Caterva's"),
]


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"^\s*//.*$", "", text, flags=re.M)


def can_call_out() -> bool:
    if not RESOLVER.exists():
        return False
    code = _strip_comments(RESOLVER.read_text(encoding="utf-8"))
    return any(pattern.search(code) for pattern in CALLS_OUT)


def selftest() -> int:
    """Prove both branches, and that a comment is not a call.

    The `must_not` half is load-bearing: a sibling guard in this repository
    was found treating a comment describing a defect as the defect, and the
    same mistake here would fire on a file that merely mentions OpenAI.
    """
    failures: List[str] = []

    calling = [
        'const url = "https://api.openai.com/v1/chat/completions";',
        'apiUrl: "https://openrouter.ai/api/v1/chat/completions",',
        'fetch(base + "/chat/completions")',
    ]
    not_calling = [
        '// we deliberately do NOT call https://api.openai.com here',
        "/* chat/completions was removed in ADR 00xx */",
        'const message = "no external providers are used";',
    ]
    for sample in calling:
        if not any(p.search(_strip_comments(sample)) for p in CALLS_OUT):
            failures.append(f"outbound call not detected: {sample!r}")
    for sample in not_calling:
        if any(p.search(_strip_comments(sample)) for p in CALLS_OUT):
            failures.append(f"outbound call wrongly detected: {sample!r}")

    complete = (
        "An LLM provider can be called. It is off by default. The query text "
        "is sent. The provider's terms and retention govern it."
    )
    for pattern, what in REQUIRED:
        if not pattern.search(complete):
            failures.append(f"a complete disclosure read as missing {what}")

    if failures:
        print("SELFTEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"SELFTEST OK: {len(calling)} outbound form(s) detected, "
        f"{len(not_calling)} comment(s) about outbound calls ignored, and "
        f"{len(REQUIRED)} disclosure clause(s) detectable."
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    if not can_call_out():
        print(
            "OK: no module here can call an external LLM provider, so no "
            "disclosure is\n    required. This guard stops asking."
        )
        return 0

    if not PRIVACY.exists():
        print(
            "FAIL: the code can send user query text to an external LLM "
            "provider and\ndocs/PRIVACY.md does not exist."
        )
        return 1

    doc = PRIVACY.read_text(encoding="utf-8")
    missing = [(p, w) for p, w in REQUIRED if not p.search(doc)]

    if missing:
        print(
            f"The code can call an external LLM provider, and docs/PRIVACY.md "
            f"is missing {len(missing)} part(s):\n"
        )
        for _, what in missing:
            print(f"  - {what}")
        print(
            "\n`llmResolver.ts` sends `{ role: \"user\", content: query }` -- the "
            "raw text somebody\ntyped -- to whichever provider is configured. "
            "That is a third-party disclosure\nwhether or not the browser is "
            "the one making the request.\n"
            "\nSaying 'no third-party requests from the page itself' is the "
            "kind of true\nsentence that misleads, and it is what this guard "
            "exists to stop recurring."
        )
        return 1

    print(
        "OK: the code can call an external LLM provider, and docs/PRIVACY.md "
        "discloses it —\n    including that it is off by default and that the "
        "provider's terms govern it."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
