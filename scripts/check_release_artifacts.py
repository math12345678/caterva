#!/usr/bin/env python3
"""Publishing a build artifact changes Caterva's licence obligations.

WHY THIS EXISTS
---------------
Caterva's dependency licences are clean today for one reason, and it is not
a property of the licences. It is that **nothing here is distributed**.

`requirements.txt` names dependencies; pip fetches them onto the user's own
machine. Almost every obligation in an open-source licence attaches on
DISTRIBUTION, and distributing source that NAMES a dependency is not
distributing the dependency.

Two of those dependencies would carry real obligations if that changed:

  python-libsbml   LGPL-2.1-or-later. Conveying the library requires notice
                   and the ability for a recipient to relink against a
                   modified libSBML.

  stdpopsim        GPL-3.0-or-later. Now opt-in via requirements-popgen.txt
                   (ADR 0058), but a build that installs that file and is
                   then published is a distribution of GPLv3 code, and the
                   combined work's terms change accordingly.

`.devcontainer/Dockerfile` already runs `pip install -r requirements-dev.txt`,
so an image built from it CONTAINS libSBML. Building it locally is private
use. Pushing it is conveyance.

So the compliance position rests on a fact about CI that nobody is watching:
as of 2026-08-15 this repository has one workflow, `tests.yml`, and it
publishes nothing. The day someone adds a release job -- a perfectly
reasonable thing to want -- the obligations attach silently, and the person
adding it has no reason to know that.

**A legal position that depends on an unwatched fact is not a position, it
is a coincidence.** This guard watches the fact.

WHAT IT CHECKS
--------------
If any CI workflow contains a step that publishes an artifact -- pushing a
container image, uploading to PyPI, creating a GitHub release -- then NOTICE
must contain a conveyance section stating the LGPL and GPL obligations that
now apply.

It does NOT try to decide whether the obligations are met. That needs a
lawyer and a look at the actual artifact. It fails the build with a pointer
to what must be done, which is the honest limit of what a regex can offer.

WHAT IT DOES NOT CHECK
----------------------
Publishing done outside CI -- someone running `docker push` from a laptop --
is invisible here. No static check can see that. Stated because a guard that
implies more coverage than it has is the failure mode this project cares
most about.

Nor does it check the npm side. `package.json` has no `publish` script today
and the TypeScript tree is not distributed as a package; if that changes,
this guard needs extending and will not tell you so.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"
NOTICE = REPO / "NOTICE"

#: Markers that a workflow step publishes something a third party can obtain.
#: Each is paired with what it would be conveying.
PUBLISH_MARKERS: List[Tuple[str, str]] = [
    (r"docker\s+push", "a container image"),
    (r"docker/build-push-action", "a container image"),
    (r"\bpush:\s*true\b", "a container image (build-push-action)"),
    (r"pypa/gh-action-pypi-publish", "a PyPI distribution"),
    (r"\btwine\s+upload\b", "a PyPI distribution"),
    (r"softprops/action-gh-release", "a GitHub release artifact"),
    (r"gh\s+release\s+create", "a GitHub release artifact"),
    (r"actions/upload-release-asset", "a GitHub release artifact"),
]

#: The NOTICE must say these things once an artifact is published.
REQUIRED_IN_NOTICE = [
    "LGPL-2.1",
    "conveyance",
]


def publishing_steps() -> List[str]:
    """`file:line: marker` for each step that publishes an artifact."""
    found: List[str] = []
    if not WORKFLOWS.is_dir():
        return found
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        text = workflow.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, conveying in PUBLISH_MARKERS:
                if re.search(pattern, line, re.IGNORECASE):
                    found.append(
                        f"{workflow.relative_to(REPO)}:{lineno} publishes "
                        f"{conveying}\n      {stripped[:100]}"
                    )
    return found


def notice_has_conveyance_section() -> bool:
    if not NOTICE.exists():
        return False
    text = NOTICE.read_text(encoding="utf-8")
    return all(token.lower() in text.lower() for token in REQUIRED_IN_NOTICE)


def selftest() -> int:
    """Prove the detector can fail.

    Nothing publishes today, so on a clean tree this guard reports zero
    findings forever -- and a detector whose patterns matched nothing would
    report zero too. That is the shape of every unfalsifiable check this
    project has shipped, so the patterns are exercised against text directly.
    """
    must_detect = [
        "        run: docker push ghcr.io/caterva-sim/caterva:latest",
        "      - uses: docker/build-push-action@v5",
        "          push: true",
        "      - uses: pypa/gh-action-pypi-publish@release/v1",
        "        run: twine upload dist/*",
        "        run: gh release create v1.0.0 dist/caterva.whl",
    ]
    must_ignore = [
        "        run: docker build -f .devcontainer/Dockerfile -t local .",
        "      - uses: actions/checkout@v4",
        "        run: python -m pytest -v",
        "      # docker push is deliberately not done here -- see NOTICE",
        "        run: git push origin main",
    ]

    failures: List[str] = []
    for line in must_detect:
        if not any(re.search(p, line, re.IGNORECASE) for p, _ in PUBLISH_MARKERS):
            failures.append(f"should have detected, did not: {line.strip()!r}")
    for line in must_ignore:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        hit = [p for p, _ in PUBLISH_MARKERS if re.search(p, line, re.IGNORECASE)]
        if hit:
            failures.append(f"should have ignored, matched {hit}: {stripped!r}")

    # The NOTICE check must be capable of saying no.
    if not notice_has_conveyance_section():
        failures.append(
            "NOTICE lacks the conveyance section, so this guard would fail the "
            "build the moment publishing were added. Add it to NOTICE."
        )

    if failures:
        print("SELFTEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"SELFTEST OK: {len(must_detect)} publishing form(s) detected, "
        f"{len(must_ignore)} non-publishing form(s) ignored, and NOTICE "
        "carries the conveyance section."
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    steps = publishing_steps()

    if not steps:
        print(
            "OK: no CI workflow publishes an artifact, so no LGPL/GPL "
            "conveyance obligation attaches.\n"
            "    Caterva distributes source that names its dependencies, not "
            "the dependencies themselves.\n"
            "    (Publishing done outside CI is invisible here -- see this "
            "script.)"
        )
        return 0

    print(f"This repository now publishes build artifacts ({len(steps)}):\n")
    for step in steps:
        print(f"  {step}")

    if notice_has_conveyance_section():
        print(
            "\nNOTICE carries the conveyance section, so the obligations are "
            "at least written down.\n"
            "This guard cannot verify they are MET -- that needs a look at the "
            "actual artifact and\nadvice from counsel. Treat this as a "
            "reminder, not a clearance."
        )
        return 0

    print(
        "\nFAIL: NOTICE does not state the conveyance obligations.\n"
        "\nUntil now Caterva conveyed nothing, so the LGPL and GPL terms of its"
        "\ndependencies imposed no obligations. Publishing an artifact that "
        "CONTAINS them\nchanges that:\n"
        "\n  python-libsbml is LGPL-2.1-or-later. Conveying it requires notice "
        "and that a\n  recipient be able to relink against a modified libSBML.\n"
        "\n  stdpopsim is GPL-3.0-or-later. If the artifact includes "
        "requirements-popgen.txt,\n  the combined work's terms change (ADR "
        "0058).\n"
        "\nAdd a conveyance section to NOTICE naming both, and get advice "
        "before shipping.\nDo not delete this guard to go green: the "
        "obligation exists whether or not the\nbuild is passing."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
