#!/usr/bin/env python3
"""Sixty seconds, no network, no account: what Caterva actually produces.

WHY THIS EXISTS
---------------
Caterva's front page describes a document. To see one, a stranger had to
clone the repository (private), run `make setup` (120 MB, two to five
minutes), install Node, learn which of ten commands to type, discover that
BRENDA calls lactate "(S)-lactate", and have the network reach four separate
services at that moment.

Every one of those is defensible on its own. Together they meant **nobody
had ever seen the output without being told how**, which is the difference
between a project that is good and a project somebody adopts.

This became possible on 2026-08-21, when `report` learned `--fixture`
(ADR 0149). Before that there was no offline path to demonstrate.

WHY IT DRIVES THE REAL BUILDER
------------------------------
It calls `report_lab.py` with the payload the CLI would send. It does not
render its own document.

A demo with its own rendering path is the worst kind of check that cannot
fail: it keeps looking impressive while the product it advertises rots, and
the discrepancy surfaces in front of the first person who tries the real
command. `Tests/test_demo_shows_the_real_thing.py` asserts the payload
matches what `scientificCLI.ts` builds.

WHY NO NODE
-----------
The CLI is TypeScript, and `make setup` installs Python. Requiring a Node
toolchain to see one document would reintroduce a smaller version of the
barrier this removes. The equivalent CLI command is printed at the end, so
the real path is one copy-paste away rather than hidden.

WHAT IT IS HONEST ABOUT
-----------------------
The saved BRENDA page is committed under `Tests/fixtures/`. This run
therefore proves the pipeline, not the network — and the document says so
itself, in its own "What Caterva would not do" section, because that is
where a reader looks before trusting it.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "Tests" / "fixtures" / "brenda_ldh_fixture.html"
OUT = REPO_ROOT / "demo-report.md"

#: Lactate dehydrogenase, the enzyme in every introductory kinetics lab.
#: `pyruvate` rather than `lactate` on purpose: BRENDA's label for the latter
#: is "(S)-lactate", and a demo whose first run came back empty would be
#: teaching the wrong lesson about the tool on the way to teaching the right
#: one about the database.
PAYLOAD = {
    "title": "Lactate dehydrogenase in Homo sapiens",
    "question": "How fast is pyruvate consumed, and where did every number come from?",
    "ec": "1.1.1.27",
    "organism": "Homo sapiens",
    "fixture": str(FIXTURE),
    "parameters": [{"name": "km", "substrate": "pyruvate", "quantity": "km"}],
    "supplied": [
        {"name": "s0", "value": 10.0, "unit": "mM", "basis": "chosen for this run"},
        {"name": "vmax", "value": 0.25, "unit": "mM/s", "basis": "chosen for this run"},
    ],
    "s0": 10.0,
    "vmax": 0.25,
    "seed": 1,
}

CLI_EQUIVALENT = (
    'npx ts-node src/cli/scientificCLI.ts report \\\n'
    '    --ec 1.1.1.27 --organism "Homo sapiens" --substrate pyruvate \\\n'
    '    --s0 10mM --vmax 0.25mM/s --seed 1 \\\n'
    '    --fixture Tests/fixtures/brenda_ldh_fixture.html --out report.md'
)


def build() -> tuple[int, str]:
    """Run the real builder. Returns (exit code, markdown-or-error)."""
    done = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "report_lab.py")],
        input=json.dumps(PAYLOAD),
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    try:
        parsed = json.loads(done.stdout.strip())
    except json.JSONDecodeError:
        return 1, (
            "The report builder returned output the demo could not read.\n"
            f"  stdout: {done.stdout[:300]}\n  stderr: {done.stderr[:300]}"
        )
    if not parsed.get("ok") or not parsed.get("markdown"):
        # Reported, not swallowed. A demo that prints "see demo-report.md"
        # after failing to write one is the shape this project keeps finding.
        return 1, parsed.get("error", "The report could not be built.")
    return 0, parsed["markdown"]


def main() -> int:
    if not FIXTURE.is_file():
        print(f"The saved BRENDA page is missing: {FIXTURE}")
        print("  This demo reads a committed fixture and makes no network")
        print("  requests. Without it there is nothing to demonstrate.")
        return 1

    code, body = build()
    if code:
        print(body)
        return code

    OUT.write_text(body, encoding="utf-8")

    print(body)
    print()
    print("=" * 70)
    print(f"Written to {OUT.relative_to(REPO_ROOT)}")
    print()
    print("No network was used. The BRENDA page came from")
    print(f"  {FIXTURE.relative_to(REPO_ROOT)}")
    print("so this shows the pipeline, not a live lookup — and the document")
    print("says so itself, under 'What Caterva would not do'.")
    print()
    print("The same thing through the CLI, which does go to BRENDA when you")
    print("drop --fixture:")
    print()
    print(f"  {CLI_EQUIVALENT}")
    print()
    print("Start with `catalog` if you do not know the substrate label:")
    print("  npx ts-node src/cli/scientificCLI.ts catalog 1.1.1.27")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
