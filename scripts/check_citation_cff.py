#!/usr/bin/env python3
"""`CITATION.cff` must be valid, and must not say things that stopped being true.

WHY THIS EXISTS
---------------
The file was already in the repository. Nothing validated it, nothing
referenced it, and no exported run carried it — so a Terrium result could
cite every measurement it used and not the tool that produced them.

That is the half of Daniel Katz's field the earlier passes did not reach.
His objection was that per-constant citation is confusing; the FORCE11
Software Citation Principles (Smith et al. 2016, *PeerJ CS* 2:e86), which he
co-authored, make the converse point: the software behind a result is
citable and routinely goes uncited. Terrium exported a bibliography of
everyone else's measurements and no way to cite itself.

WHAT IS CHECKED
---------------
1. **Schema validity**, via `cffconvert` against CFF 1.2.0. An invalid
   CITATION.cff is worse than none: GitHub's "Cite this repository" button
   silently disappears, so the failure mode is an absence nobody notices.

2. **The repository URL resolves to this repository.** `repository-code` in
   CITATION.cff pointed at the pre-rename GitHub org once already (recorded
   in EXPERT_FEEDBACK). A citation pointing somewhere that is not the
   software is the software-citation version of a fabricated identifier.

3. **The licence agrees with LICENSE.** Three files claimed three different
   licences during the Apache-2.0 relicensing. `check_license_consistency.py`
   covers the general case; this pins the CFF specifically, because a
   citation carrying the wrong licence is a legal statement travelling
   inside every exported archive.

WHAT IS NOT CHECKED
-------------------
Whether the abstract is a good description. It is prose, and a guard that
grades prose produces arguments rather than findings. The abstract's *domain
list* is deliberately not compared against the fifteen domains README claims
— an abstract is allowed to be a summary rather than an inventory, and
demanding they match would be this guard inventing a rule nobody agreed to.

Exit 0 valid, 1 otherwise. Requires `cffconvert` (Apache-2.0, confirmed from
the LICENSE file the wheel ships — its metadata `License` field reads
UNKNOWN, which is exactly why the file was read instead).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CFF_PATH = REPO / "CITATION.cff"
LICENSE_PATH = REPO / "LICENSE"


def main() -> int:
    if not CFF_PATH.exists():
        print("FAIL  CITATION.cff does not exist.")
        print("      Without it, GitHub shows no 'Cite this repository' button")
        print("      and an exported run cannot say how to cite the tool.")
        return 1

    try:
        from cffconvert.cli.create_citation import create_citation
    except ImportError:
        print("UNREACHABLE  cffconvert is not installed, so validity was NOT checked.")
        print("      Declared in requirements-dev.txt. This is not a pass:")
        print("      'could not check' and 'checked and fine' are different facts.")
        return 1

    text = CFF_PATH.read_text(encoding="utf-8")

    try:
        citation = create_citation(str(CFF_PATH), None)
        citation.validate()
    except Exception as exc:  # cffconvert raises several unrelated types
        print("FAIL  CITATION.cff is not valid CFF 1.2.0:")
        print(f"      {str(exc)[:800]}")
        print("      An invalid file fails SILENTLY on GitHub -- the citation")
        print("      button simply does not appear -- so nothing else would")
        print("      have told anyone.")
        return 1

    problems: list[str] = []

    repository = re.search(r'^repository-code:\s*"?([^"\n]+)"?', text, re.M)
    if not repository:
        problems.append("no `repository-code`, so a reader cannot find the software")
    elif "Terrium-sim/terrium" not in repository.group(1):
        problems.append(
            f"`repository-code` is {repository.group(1)!r}, which is not this "
            "repository. It pointed at the pre-rename org once already."
        )

    declared_licence = re.search(r"^license:\s*(\S+)", text, re.M)
    if not declared_licence:
        problems.append("no `license`, so the archive carries a citation with no terms")
    elif LICENSE_PATH.exists():
        licence_text = LICENSE_PATH.read_text(encoding="utf-8")
        claimed = declared_licence.group(1).strip()
        if claimed == "Apache-2.0" and "Apache License" not in licence_text:
            problems.append(
                "CITATION.cff says Apache-2.0 and LICENSE does not look like "
                "the Apache licence"
            )
        elif claimed != "Apache-2.0":
            problems.append(
                f"CITATION.cff says {claimed!r}; LICENSE is the Apache licence. "
                "Three files claimed three different licences once before."
            )

    print(f"Checked {CFF_PATH.relative_to(REPO)}")
    print("  valid against CFF 1.2.0 (cffconvert)")

    if problems:
        print(f"\nFAIL  {len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("  repository-code points at this repository")
    print("  licence agrees with LICENSE")
    print("\nOK  CITATION.cff is valid and its claims still hold.")
    print("    Not checked: whether the abstract is a good description. That is")
    print("    prose, and a guard that grades prose produces arguments.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
