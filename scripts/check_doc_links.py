#!/usr/bin/env python3
"""Every relative link in a contributor document must resolve.

WHY THIS EXISTS
---------------
`START_HERE.md` is the first thing a new contributor reads. It is almost
entirely links. A dead one is the worst possible first impression: it says,
before they have written a line, that the project's claims about checking
things are decoration.

This guard was written immediately after `caterva/README.md` shipped with

    [ADR 0001](../docs/adr/0001-no-tellurium-dependency.md)

when the file is `0001-no-tellurium-umbrella-package.md`. Plausible,
confidently written, wrong. Caught by a one-off script; nothing in the
repository would have caught the next one.

That is the pattern this project keeps hitting: a real check exists for
counts (`check_documented_counts.py`) and for named scripts
(`check_commands_runnable.py`), and the space between them -- a link to a
document -- was unwatched. Not a new class of defect, a new location for it.

WHY THIS IS NOT check_doc_paths_resolve.py
------------------------------------------
That guard checks **backticked paths in prose** -- `` `Tests/foo.py`` `` --
and deliberately skips bare filenames. This one checks **markdown links**,
`[text](target)`. The two look like the same job and are not, and the
project's rule against a second implementation of anything makes the
difference worth demonstrating rather than asserting.

So it was measured. A broken markdown link was appended to `START_HERE.md`
and both guards were run:

    check_doc_paths_resolve.py  ->  OK: every path ... resolves
    check_doc_links.py          ->  START_HERE.md:184 -> docs/NOT_REAL_AT_ALL.md

A link target is not backticked, so it is invisible to the other guard. The
real broken ADR 0001 link that prompted this file was of exactly that form.

If the two are ever merged, the merged guard must still fail that case.

WHAT IT CHECKS
--------------
Relative markdown links and image paths in the documents listed below
resolve to something on disk. A link ending in `/` must be a directory; a
fragment (`#section`) is stripped before resolving.

WHAT IT DOES NOT CHECK
----------------------
**Anchors.** `file.md#some-heading` is verified as far as `file.md`. Checking
the fragment means parsing every heading and reimplementing GitHub's slug
rules, which have edge cases around punctuation and duplicates. Stated
rather than silently skipped, because "the link works" would otherwise be
read as more than it is.

**External URLs.** Fetching them would make the build depend on the network
and on other people's uptime, and a guard that fails when someone else's
site is down teaches people to ignore it.

WHY A CURATED LIST AND NOT EVERY .md
------------------------------------
Historical records are never rewritten (see `docs/README.md`). A 2026-08
build-stage record may link to a file that has since moved, and that link
was correct when written -- fixing it would falsify the record, and failing
the build over it would create pressure to. So the list is the set of
documents the project promises to keep true today.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parent.parent

# Present-tense contributor docs. Deliberately overlaps
# check_documented_counts.PRESENT_TENSE_DOCS -- same promise, different
# property -- plus the per-directory READMEs, which are the map a newcomer
# navigates by.
DOCS = [
    "README.md",
    "START_HERE.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "SUPPORT.md",
    "GOVERNANCE.md",
    "docs/INBOUND_LICENSE.md",
    "docs/PRIVACY.md",
    "docs/README.md",
    "docs/FIRST_TASKS.md",
    "docs/REPO_MAP.md",
    "docs/AGENT_BRIEF.md",
    "docs/AGENT_BRIEFING.md",
    "docs/INTERN_ONBOARDING.md",
    "docs/CONSTITUTION.md",
    "docs/API.md",
    "docs/adr/README.md",
    "caterva/README.md",
    "Tests/README.md",
    "src/README.md",
    "examples/README.md",
    "scripts/README.md",
    "Science-Agent-Pipeline/README.md",
    "mule/README.md",
]

# `[text](target)` and `![alt](target)`.
LINK = re.compile(r"!?\[[^\]]*\]\(\s*([^)\s]+)")

SKIP_PREFIXES = ("http://", "https://", "mailto:", "#", "<")

#: A GitHub URL pointing back into THIS repository is a repo-relative path
#: wearing a URL, and it is checkable offline.
#:
#: `.github/ISSUE_TEMPLATE/config.yml` routes every newcomer through five of
#: these -- "I have a question", "where do I start", "pick something to work
#: on". GitHub requires absolute URLs in contact links, so they cannot be
#: written relatively, and this guard skipped them as external. Rename
#: SUPPORT.md and every one of those links 404s for the exact person least
#: equipped to work out why.
#:
#: External URLs stay out of scope: fetching them would make the build
#: depend on somebody else's uptime. This resolves against the local tree
#: and touches the network never.
SELF_URL = re.compile(
    r"^https://github\.com/math12345678/caterva/(?:blob|tree)/[^/]+/(.+)$"
)

#: Below this the extractor is broken rather than the docs being sparse.
#:
#: Found by mutation, and only because the NUMBER was read rather than the
#: verdict. Breaking `SELF_URL` so it matched nothing dropped the scan from
#: 168 links to 163 -- and the guard still printed OK. It was checking five
#: fewer things and reporting success, which is the failure mode this whole
#: project keeps rediscovering: a check that quietly does less.
#:
#: Three sibling guards already had this and this one did not:
#: `check_dependency_licenses._MIN_DEPS`,
#: `check_investor_claims._MIN_WORDS`,
#: `check_non_affiliation_notice._MIN_SURFACES`.
#:
#: Set below the current count with room for a document to be retired, and
#: far enough above zero that a broken extractor cannot pass.
_MIN_LINKS = 120

#: Files whose links are checked but which are not markdown.
EXTRA_FILES = [
    ".github/ISSUE_TEMPLATE/config.yml",
]


def links_in(text: str) -> List[Tuple[int, str]]:
    """`(line number, target)` for each relative link."""
    found: List[Tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        # A link inside a fenced code block is an example, not a link.
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in LINK.finditer(line):
            target = match.group(1)
            if target.startswith(SKIP_PREFIXES):
                self_ref = SELF_URL.match(target)
                if self_ref:
                    # Recorded as the repo path it actually names, so the
                    # failure message points at a file rather than a URL.
                    found.append((lineno, self_ref.group(1)))
                continue
            found.append((lineno, target))
    return found


def self_urls_in(text: str) -> List[Tuple[int, str]]:
    """`(line number, repo path)` for bare self-referencing GitHub URLs.

    `LINK` only matches markdown `[text](target)`. A YAML contact link is
    `url: https://github.com/...` with no brackets, so the markdown
    extractor never sees it -- which would have made adding config.yml to
    DOCS a check that scanned the file and found nothing, the most
    convincing kind of false pass.
    """
    found: List[Tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for token in re.findall(r"https://\S+", line):
            match = SELF_URL.match(token.rstrip(">,)\"'"))
            if match:
                found.append((lineno, match.group(1)))
    return found


def resolve(doc: Path, target: str) -> bool:
    # Strip the fragment; anchors are explicitly out of scope.
    path_part = target.split("#", 1)[0]
    if not path_part:
        return True  # a bare "#anchor" -- same-document, nothing to resolve
    candidate = (doc.parent / path_part)
    if path_part.endswith("/"):
        return candidate.is_dir()
    return candidate.exists()


def selftest() -> int:
    """Prove the matcher and the resolver can both fail.

    On a clean tree this guard reports zero findings forever, and a matcher
    that matched nothing would report zero too -- ADR 0034's lesson, and the
    reason `check_documented_counts.py` sat on one file for months without
    anyone noticing.
    """
    extract_cases = [
        ("see [the map](docs/REPO_MAP.md) for more", ["docs/REPO_MAP.md"]),
        ("![shot](assets/a.png)", ["assets/a.png"]),
        ("[external](https://example.com)", []),
        ("[anchor only](#the-standard)", []),
        ("[two](a.md) and [links](b.md)", ["a.md", "b.md"]),
        ("[frag](docs/README.md#writing-here)", ["docs/README.md#writing-here"]),
    ]
    failures: List[str] = []

    for text, expected in extract_cases:
        got = [t for _, t in links_in(text)]
        if got != expected:
            failures.append(f"extractor on {text!r}: expected {expected}, got {got}")

    # A fenced example must not be treated as a link.
    fenced = "```\n[not a link](nope/does-not-exist.md)\n```\n"
    if links_in(fenced):
        failures.append("extractor followed a link inside a code fence")

    # The resolver must say no to something absent and yes to something present.
    here = Path(__file__)
    if resolve(here, "definitely-not-a-real-file-9f3a.md"):
        failures.append("resolver accepted a nonexistent target")
    if not resolve(here, "check_doc_links.py"):
        failures.append("resolver rejected a file that exists")
    if not resolve(here, "check_doc_links.py#anything"):
        failures.append("resolver did not strip the fragment")
    if resolve(here, "check_doc_links.py/"):
        failures.append("resolver accepted a file where a directory was written")

    if failures:
        print("SELFTEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(
        f"SELFTEST OK: {len(extract_cases)} extraction form(s), the code-fence "
        "exclusion, and 4 resolver case(s) all behaved as intended."
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    failures: List[str] = []
    checked_docs = 0
    checked_links = 0

    for relative in EXTRA_FILES:
        doc = REPO / relative
        if not doc.exists():
            failures.append(
                f"{relative} is listed in EXTRA_FILES but does not exist."
            )
            continue
        checked_docs += 1
        for lineno, target in self_urls_in(doc.read_text(encoding="utf-8")):
            checked_links += 1
            # These are absolute repo paths, not relative to the file.
            if not (REPO / target.split("#", 1)[0]).exists():
                failures.append(f"{relative}:{lineno} -> {target}")

    for relative in DOCS:
        doc = REPO / relative
        if not doc.exists():
            failures.append(
                f"{relative} is listed as a contributor doc but does not exist. "
                "Remove it from DOCS or restore it."
            )
            continue
        checked_docs += 1
        for lineno, target in links_in(doc.read_text(encoding="utf-8")):
            checked_links += 1
            if not resolve(doc, target):
                failures.append(f"{relative}:{lineno} -> {target}")

    if failures:
        print(f"Broken links in contributor documentation ({len(failures)}):\n")
        for failure in failures:
            print(f"  {failure}")
        print(
            "\nSTART_HERE.md is the first thing a new contributor reads, and it"
            "\nis almost entirely links. A dead one tells them, before they have"
            "\nwritten a line, that this project's claims about checking things"
            "\nare decoration.\n"
            "\nFix the path, or remove the link. Do not remove the document from"
            "\nDOCS to make the build green."
        )
        return 1

    if checked_links < _MIN_LINKS:
        print(
            f"FAIL: only {checked_links} link(s) extracted, below the floor of "
            f"{_MIN_LINKS}.\n"
            "The extractor is broken, not the documentation. A scan that finds "
            "almost nothing\nreports the same green as one that finds "
            "everything, so this is a failure."
        )
        return 1

    print(
        f"OK: {checked_links} relative link(s) across {checked_docs} contributor "
        "doc(s) all resolve. (Anchors and external URLs are out of scope -- see "
        "this script.)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
