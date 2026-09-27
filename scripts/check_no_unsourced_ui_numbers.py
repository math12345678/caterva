#!/usr/bin/env python3
"""Every number on a user-facing page must come from somewhere.

WHY THIS EXISTS
---------------
`src/web/dashboard.html` is titled "Caterva - Scientific Enzyme Kinetics
Simulator". It has a Run Simulation card. It is the product, for anyone who
does not use the CLI.

It displayed seven numbers as static HTML, with no `id` and nothing capable
of updating them:

    Tests Passing       178/178      (the repo has ~1,631)
    Coverage            84.04%       (no live source)
    Uptime              99.9%        (nothing measures uptime)
    Sources             3
    Parameters          6
    Avg Impact Factor   19.79
    Avg Citations       904

Beside them, styled identically, sat four genuinely live metrics
(`totalRuns`, `avgConfidence`, `avgTime`, `successRate`). A reader could not
tell which was which.

"Avg Impact Factor 19.79" is the one to remember. Specific to two decimal
places, framed as a measurement, and typed by hand. A student reading it has
no way to distinguish it from the resolved Km three cards down, which is
real, cited, and carries its assay conditions.

This is the exact failure the project exists to prevent — a plausible number
with no source, presented with the authority of a computation — committed by
its own front page while the resolver behind it refused to default a Km.

AND IT PRE-FILLED THE FORBIDDEN DEFAULT
---------------------------------------
The same page shipped its simulation form as:

    <input type="number" id="km"   value="5.2">
    <input type="number" id="vmax" value="12.8">

ADR 0024, stating the rule the whole project rests on, reads: *"a parameter
that cannot be sourced stops the run. No `km = 5.2` fallback, no
plausible-looking default."*

The form was pre-filled with the exact number the constitution uses as its
example of the forbidden thing. `5.2` matches no LDH measurement in the
corpus. With the enzyme and substrate also pre-filled, a student could open
the page, press Run, and receive a confidence score and a green tick for a
simulation built on a number from nowhere.

A displayed fabrication misinforms a reader. A pre-filled one gets *used*,
and comes back wearing the output's authority.

THE RULE
--------
A number shown to a user must either be **written by code at run time**, or
be **explicitly allowlisted with a reason**. There is no third category, and
"it was true when I typed it" is not a source.

A **measured quantity** must never arrive pre-filled in an input. Km, Vmax,
Ki and kcat are things somebody measured; the page does not know which
measurement the student means, and offering one is the defaulting ADR
0012/0013 forbid. Experimental conditions the student chooses (S0, end,
points) are a different category — but this guard treats a pre-filled
measured quantity as an error regardless of how reasonable it looks, because
looking reasonable is the whole problem.

WHAT THIS DOES NOT DO
---------------------
It does not check prose. A sentence like "fifteen simulation domains" in a
paragraph is a documentation claim, and `check_documented_counts.py` already
covers that class. This checks *metric displays* — the places styled to look
like readings.

It does not check `mule/`, the marketing site. Marketing copy makes claims
about the project rather than readings from it, and conflating the two would
either flood this guard with false positives or dilute it into a spell
check. Saying which surface is unchecked beats implying both are.

Exit codes:
    0  every displayed metric is sourced or allowlisted
    1  at least one is neither
    2  the check could not run — NOT a pass
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Pages that render metrics to a user. Add to this list rather than
#: widening the glob: a guard that scans everything finds mostly noise, and
#: a noisy guard is one people learn to skip.
PAGES = [REPO_ROOT / "src" / "web" / "dashboard.html"]

#: Metric labels permitted to carry a static value, each with the reason.
#:
#: Empty on purpose. Every entry added here is a promise that the number is
#: true and will stay true, and the seven that motivated this guard were all
#: things somebody believed when they typed them.
ALLOWLIST: dict[str, str] = {}

#: Inputs whose value is a MEASURED QUANTITY. Pre-filling any of these is
#: the defaulting ADR 0012/0013 forbid, wearing an input box.
#:
#: Matched on the element id rather than the label, because a label can be
#: reworded and the id is what the code reads.
MEASURED_INPUT_IDS = {"km", "vmax", "ki", "kcat", "enzymeConc"}

_INPUT_RE = re.compile(r"<input([^>]*)>", re.S)
_VALUE_RE = re.compile(r'value="([^"]*)"')

#: A displayed metric: label beside value. Matches the dashboard's markup.
_METRIC_RE = re.compile(
    r'<span class="metric-label">([^<]*)</span>\s*'
    r'<span class="metric-value"([^>]*)>([^<]*)</span>',
    re.S,
)
_ID_RE = re.compile(r'id="([^"]+)"')

#: A value that is not a reading: an em dash, ellipsis, placeholder.
#: These are honest "nothing yet" states and must not be flagged.
_PLACEHOLDER = {"--", "—", "-", "", "…", "checking…", "n/a", "N/A"}


def _looks_numeric(value: str) -> bool:
    """Does this read as a measurement?

    Deliberately broad: `178/178`, `84.04%`, `19.79`, `904` all qualify. A
    guard that only caught bare integers would have missed five of the seven
    that motivated it.
    """
    return bool(re.search(r"\d", value))


def main() -> int:
    findings: list[str] = []
    checked = 0

    for page in PAGES:
        if not page.exists():
            print(f"CANNOT VERIFY: {page.relative_to(REPO_ROOT)} is missing.")
            print(
                "\nExit 2, not 0. A page that moved is a page this guard "
                "stopped checking, and reporting OK for it would be the "
                "failure this file is about."
            )
            return 2

        text = page.read_text()

        # Only the CONTENTS of <script> elements, not "everything after the
        # first <script> tag".
        #
        # The first version did the latter, and the dashboard loads Chart.js
        # from a CDN in its <head> — so `script` was the whole document from
        # there down, including every metric element. Every id matched
        # itself and the id-branch could never fail.
        #
        # An unfalsifiable branch inside a guard against unsourced displays.
        # Caught by mutation: replacing a live id with `neverWritten` and a
        # value of `99.9%` still reported OK.
        script = "\n".join(
            re.findall(r"<script[^>]*>(.*?)</script>", text, re.S)
        )

        for match in _METRIC_RE.finditer(text):
            label, attrs, value = (g.strip() for g in match.groups())
            checked += 1

            if value in _PLACEHOLDER or not _looks_numeric(value):
                continue

            id_match = _ID_RE.search(attrs)
            if id_match:
                element_id = id_match.group(1)
                # An id alone is not enough. An element nothing writes to is
                # exactly as static as one with no id, and looks more
                # trustworthy for having a hook.
                if element_id in script:
                    continue
                findings.append(
                    f"{page.relative_to(REPO_ROOT)}: {label!r} shows {value!r} "
                    f'with id="{element_id}", but no script writes to that id. '
                    "An unwritten id is a static number wearing a hook."
                )
                continue

            if label in ALLOWLIST:
                continue

            findings.append(
                f"{page.relative_to(REPO_ROOT)}: {label!r} shows {value!r} as "
                "static HTML. Nothing can update it and nothing sourced it."
            )

        # --- pre-filled measured quantities -----------------------------
        for match in _INPUT_RE.finditer(text):
            attrs = match.group(1)
            id_match = _ID_RE.search(attrs)
            value_match = _VALUE_RE.search(attrs)
            if not id_match or not value_match:
                continue
            element_id, value = id_match.group(1), value_match.group(1).strip()
            if element_id not in MEASURED_INPUT_IDS:
                continue
            if not value or not _looks_numeric(value):
                continue
            checked += 1
            findings.append(
                f"{page.relative_to(REPO_ROOT)}: input #{element_id} is "
                f'pre-filled with value="{value}". {element_id} is a MEASURED '
                "quantity — the page cannot know which measurement the "
                "student means, and offering one is the defaulting ADR "
                "0012/0013 forbid. Leave it empty with a placeholder."
            )

    if findings:
        print(f"Unsourced numbers on a user-facing page ({len(findings)}):\n")
        for finding in findings:
            print(f"  {finding}")
        print(
            "\nEvery one of these is presented to a student in the same style "
            "as the live metrics beside it, and they cannot tell the "
            "difference.\n"
            "\nFix by wiring it to an endpoint, removing it, or adding it to "
            "ALLOWLIST with a reason that will still be true next month.\n"
            "\nThis project refuses to default a Km it cannot source. The "
            "same standard applies to a dashboard."
        )
        return 1

    print(
        f"OK: {checked} displayed metric(s) across {len(PAGES)} page(s); "
        "every numeric one is written at run time or allowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
