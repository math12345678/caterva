#!/usr/bin/env python3
"""If a form collects an email address, it must say what happens to it.

WHY THIS EXISTS
---------------
`WaitlistForm.tsx` collected an email address and wrote it to a JSON file on
the server. The form said, in its entirety:

    placeholder="Enter your email"

No statement of who takes it, why, how long it is kept, or how to get it
back. Twelve passes of audit went over licences, dependency terms, published
repositories and attribution, and none of them looked at the one place the
project asks a stranger for personal data.

An email address is personal data. Transparency about it attaches at the
moment of collection -- not in a document somebody would have to go looking
for, and not later.

WHAT WAS ALREADY FINE, AND WORTH RECORDING
-------------------------------------------
Checking this found three things that were right, which is why the fix is a
notice rather than an incident:

  * `/waitlist/count` returns a count and nothing else. There is no endpoint
    that returns the addresses.
  * `resetWaitlist()` is an exported function for tests, not an HTTP route,
    so the list cannot be wiped remotely.
  * `artifacts/api-server/data/*.json` is gitignored, with a comment
    recording that an earlier pattern was wrong and was fixed. Emails do not
    reach git history, which is the one mistake that cannot be undone.

Somebody thought about this. What was missing was telling the person typing.

WHAT IT CHECKS
--------------
A conditional, and the conditional is the design:

    IF a form collects an email address
    THEN a notice must sit beside that form, AND docs/PRIVACY.md must exist
         and say what is collected and how to get it removed

If email collection is ever removed, this stops demanding a notice. A guard
that kept insisting on a privacy notice for a form that no longer exists
would be noise, and noise gets deleted along with the useful half.

WHAT IT DOES NOT CHECK
----------------------
**That any of this is lawful.** A privacy policy needs a named controller, a
legal basis and a retention period, and `docs/PRIVACY.md` says plainly that
three of those four do not exist. This checks that a statement is present
and specific -- not that it is sufficient. Sufficiency is a lawyer's call.

Stated because "the privacy guard passes" must not be read as "the privacy
position is fine".
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parent.parent
FORM = (
    REPO / "Science-Agent-Pipeline" / "artifacts" / "terrium-landing"
    / "src" / "components" / "ui" / "WaitlistForm.tsx"
)
PRIVACY = REPO / "docs" / "PRIVACY.md"

#: Evidence that the form asks for an email.
COLLECTS_EMAIL = [
    re.compile(r'type\s*=\s*["\']email["\']'),
    re.compile(r"aria-label\s*=\s*[\"'][^\"']*email", re.I),
]

#: What the notice beside the form must actually say. Each is load-bearing:
#: a notice missing any of them leaves the reader without something they
#: need in order to decide.
NOTICE_REQUIRED = [
    (re.compile(r"\bstored\b", re.I), "where it goes"),
    (re.compile(r"\bremov|delet", re.I), "how to get it back"),
    (re.compile(r"mailto:", re.I), "a route to ask -- an address, not a promise"),
]

#: What docs/PRIVACY.md must cover.
DOC_REQUIRED = [
    (re.compile(r"\bwaitlist\b", re.I), "the thing that collects"),
    (re.compile(r"\bremov|delet", re.I), "how to get data removed"),
    (re.compile(r"not legal advice", re.I), "that it is not a policy"),
    (re.compile(r"\bretention\b|how long", re.I), "how long it is kept"),
]


def _strip_jsx_comments(text: str) -> str:
    """Remove {/* ... */} blocks, so prose ABOUT a notice is not the notice."""
    return re.sub(r"\{/\*.*?\*/\}", "", text, flags=re.S)


def form_collects_email(text: str) -> bool:
    stripped = _strip_jsx_comments(text)
    return any(pattern.search(stripped) for pattern in COLLECTS_EMAIL)


def selftest() -> int:
    """Prove both branches, and that a comment is not a notice.

    On a clean tree this reports zero findings forever. The `must_not` half
    matters as much as the `must`: an earlier guard in this repository was
    found treating a comment describing a defect as the defect, and the
    mirror of that mistake here would be treating a comment describing a
    notice as the notice.
    """
    failures: List[str] = []

    collecting = [
        '<input type="email" />',
        "<motion.input type='email' aria-label='Email address' />",
        '<input aria-label="Your email address" />',
    ]
    not_collecting = [
        '<input type="text" aria-label="Search" />',
        '{/* we used to ask for an email here, type="email" */}',
        "<button>Join</button>",
    ]
    for sample in collecting:
        if not form_collects_email(sample):
            failures.append(f"collection not detected: {sample!r}")
    for sample in not_collecting:
        if form_collects_email(sample):
            failures.append(f"collection wrongly detected: {sample!r}")

    good_notice = (
        "Your email is stored on our own server. Email "
        "mailto:someone@example.com to have it removed."
    )
    for pattern, what in NOTICE_REQUIRED:
        if not pattern.search(good_notice):
            failures.append(f"a complete notice read as missing {what}")

    if failures:
        print("SELFTEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"SELFTEST OK: {len(collecting)} collecting form(s) detected, "
        f"{len(not_collecting)} non-collecting form(s) — including a comment "
        f"about a removed field — ignored, and {len(NOTICE_REQUIRED)} notice "
        "clause(s) detectable."
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    if not FORM.exists():
        print(
            "OK: the waitlist form does not exist, so nothing here collects "
            "an email address."
        )
        return 0

    text = FORM.read_text(encoding="utf-8")

    if not form_collects_email(text):
        print(
            "OK: the waitlist form no longer collects an email address, so no "
            "notice is\n    required. This guard stops asking."
        )
        return 0

    problems: List[str] = []

    # The notice beside the form. Comments stripped: prose explaining why a
    # notice is needed is not a notice.
    visible = _strip_jsx_comments(text)
    for pattern, what in NOTICE_REQUIRED:
        if not pattern.search(visible):
            problems.append(
                f"the form collects an email but its notice does not say "
                f"{what}."
            )

    if not PRIVACY.exists():
        problems.append(
            "docs/PRIVACY.md does not exist. The form collects personal data "
            "and nothing\n      describes what happens to it."
        )
    else:
        doc = PRIVACY.read_text(encoding="utf-8")
        for pattern, what in DOC_REQUIRED:
            if not pattern.search(doc):
                problems.append(f"docs/PRIVACY.md does not cover {what}.")

    if problems:
        print(f"Email is collected without an adequate notice ({len(problems)}):\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nAn email address is personal data, and transparency about it "
            "attaches at the\nmoment of collection -- beside the field, not "
            "in a document somebody would have\nto go looking for.\n"
            "\nThis does NOT check that the notice is legally sufficient. It "
            "checks that one\nexists and is specific. Sufficiency needs a "
            "lawyer."
        )
        return 1

    print(
        "OK: the waitlist collects an email, and both the notice beside the "
        "form and\n    docs/PRIVACY.md say what happens to it.\n"
        "\n    This is not a finding that the privacy position is adequate — "
        "see the\n    'not claimed' section of docs/PRIVACY.md."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
