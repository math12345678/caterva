#!/usr/bin/env python3
"""No published document may claim Terrium is built on or integrates Tellurium.

WHY THIS EXISTS
---------------
NOTICE says, publicly:

    Terrium is unaffiliated with it, is not a fork of it, and does not depend
    on the `tellurium` package.

On 2026-08-16, `Docw/terrium_spec.docx` -- tracked, published, in every clone
-- was found to say, also publicly:

    "built with the Tellurium systems-biology toolkit"
    "Rich visualization via Tellurium"
    "Tellurium integration"          (in its deliverables list)

The code agrees with NOTICE. There is no Tellurium in the software and
`check_forbidden_packages.py` proves it on every push. The spec describes a
product plan that was not built. But both documents are public, they say
opposite things, and a reader has no way to know which is current. That is the
"three files, three answers" defect LICENSE was written about, in the one place
where the project makes a legal claim about someone else's trademark.

WHY THE EXISTING GUARDS DID NOT CATCH IT
----------------------------------------
Two guards were adjacent to this and neither could see it:

  check_forbidden_packages     scans DOC_GLOBS = ("*.md", "docs/**/*.md") for
                               `pip install <forbidden>`. Two independent
                               misses: a .docx is a zip, so its text is
                               invisible to a line-based scan; and the spec
                               never says "pip install" -- it claims
                               integration in prose, which that pattern is not
                               looking for.

  check_non_affiliation_notice checks that each shipping surface *carries* the
                               disclaimer. Presence, not contradiction. Every
                               surface can carry it while another document
                               denies it.

So the prohibition was enforced against manifests, against install
instructions, and against the absence of a disclaimer -- and never against a
document asserting the opposite in plain English. This guard covers exactly
that gap, and reads Office files, because that is where the instance lived.

WHAT IT CHECKS
--------------
Every published document -- markdown, .docx and .pptx -- for a sentence
claiming Terrium uses, integrates, embeds or is built on Tellurium.

Denials are not claims. "does not depend on tellurium" and "is not a fork of
it" must pass, or the guard would flag NOTICE itself, which is the document
making the correct statement.

HISTORICAL RECORDS
------------------
A document describing what was planned on a date is not corrected by
rewriting it; this repository does not rewrite `Business/build-stages/` either.
Such a file goes in `HISTORICAL` with a written reason, which keeps the
contradiction recorded rather than deleted, and keeps the guard able to fail
for anything new.

An entry here is not an endorsement of publishing the document. Whether
`Docw/terrium_spec.docx` should be superseded, corrected or withdrawn is an
editorial decision for its author, and is recorded in
`Business/LEGAL_BRIEF_NAMING.md` section 3a.

Run with --selftest to prove the matcher can fail.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: A claim that Terrium *uses* Tellurium, as opposed to naming it.
CLAIM = re.compile(
    r"\b(?:built\s+(?:with|on)|using|uses|via|powered\s+by|integrat\w*\s+with"
    r"|renders?\s+(?:using|with)|based\s+on)\s+(?:the\s+)?tellurium\b"
    r"|\btellurium\s+integration\b"
    r"|\btellurium\s+toolkit\b",
    re.I,
)

#: Wording that makes a sentence a denial. NOTICE must not trip this guard.
DENIAL = re.compile(
    r"\b(not|never|no|without|avoid|forbidden|banned|instead\s+of|rather\s+than"
    r"|unaffiliated|does\s+not|is\s+not|cannot)\b",
    re.I,
)

#: Documents that record a superseded plan. Each needs a reason, and being
#: listed here does not mean the document should stay published.
HISTORICAL: dict[str, str] = {
    "Docw/terrium_spec.docx": (
        "Brand and Product Spec v1.0, July 2026. Describes an intended "
        "product that was not built: a browser notebook rendering via the "
        "Tellurium toolkit. ADR 0001 records the decision not to depend on "
        "tellurium, on packaging grounds, and the code has never contained "
        "it. Kept unrewritten because it is a dated record. Whether it should "
        "remain published is open -- see Business/LEGAL_BRIEF_NAMING.md 3a, "
        "which also notes it is marked 'Internal Use Only' and 'Confidential' "
        "while sitting in a public repository."
    ),
    "Docw/terrium_full.docx": (
        "Found by this guard on 2026-08-16, after the spec above and after a "
        "report saying the spec was the only one. It assigns 'Tellurium "
        "integration' to a named engineer as a backend responsibility, in a "
        "team/roles table -- so it reads as a live work item rather than a "
        "design aspiration, which is worse. Same disposition and same open "
        "question as the spec: a dated record, not rewritten, and whether it "
        "stays published is the author's call."
    ),
}

#: Documents whose subject IS this contradiction, and which therefore quote
#: the claims in order to record them. Exempt for the same reason a guard's
#: own fixture is exempt: reporting them would punish the act of writing the
#: finding down, and would push the next author to describe it vaguely.
DISCUSSES: dict[str, str] = {
    "Business/LEGAL_BRIEF_NAMING.md": (
        "Section 3a quotes the spec's claims verbatim so a lawyer can read "
        "them. Flagging it would mean the only way to keep the guard green "
        "was to stop quoting the evidence."
    ),
    "docs/PRIVACY.md": (
        "Carries correction banners that restate superseded claims; same "
        "reason the third-party guard reads only its table."
    ),
}

DOC_GLOBS = ("*.md", "docs/**/*.md", "Business/**/*.md", "Docw/*.docx", "*.pptx")

#: A scan that reads no Office file is not reading the place this was found.
_MIN_DOCS = 30
_MIN_OFFICE = 1


def _office_text(path: Path) -> str:
    """Visible text from a .docx/.pptx, standard library only."""
    tag = "w:t" if path.suffix == ".docx" else "a:t"
    member = "word/document.xml" if path.suffix == ".docx" else None
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        return ""
    parts: list[str] = []
    with archive:
        names = [member] if member else [
            n for n in archive.namelist() if n.startswith("ppt/slides/slide")
        ]
        for name in names:
            try:
                xml = archive.read(name).decode("utf8", "replace")
            except KeyError:
                continue
            # `<{tag}(?:\s[^>]*)?>` and not `<{tag}[^>]*>`: the second also
            # matches <w:tblPr>, <w:tbl>, <w:tc> -- `w:t` is a prefix of them
            # all -- so it captured raw table XML as if it were body text and
            # reported a match inside markup. Require the tag to end, or to be
            # followed by whitespace before its attributes.
            parts.extend(
                re.findall(rf"<{tag}(?:\s[^>]*)?>(.*?)</{tag}>", xml, re.S)
            )
    text = " ".join(parts)
    for entity, char in (("&apos;", "'"), ("&quot;", '"'), ("&amp;", "&")):
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text)


def _documents() -> list[Path]:
    found: list[Path] = []
    for pattern in DOC_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if path.is_file() and "build-stages" not in path.parts:
                found.append(path)
    return sorted(set(found))


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?;:])\s+|\n", text)


def check(docs: list[Path] | None = None) -> list[str]:
    problems: list[str] = []
    docs = _documents() if docs is None else docs

    office = [p for p in docs if p.suffix in {".docx", ".pptx"}]
    if len(docs) < _MIN_DOCS or len(office) < _MIN_OFFICE:
        return [
            f"scanned {len(docs)} document(s), {len(office)} of them Office "
            f"files; expected at least {_MIN_DOCS} and {_MIN_OFFICE}. The "
            f"globs no longer match the tree, so this guard is blind, not "
            f"clean -- which is exactly how the .docx went unread."
        ]

    for path in docs:
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in HISTORICAL or rel in DISCUSSES:
            continue
        if path.suffix in {".docx", ".pptx"}:
            text = _office_text(path)
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
        for sentence in _sentences(text):
            if CLAIM.search(sentence) and not DENIAL.search(sentence):
                problems.append(
                    f"{rel} claims Terrium uses Tellurium:\n"
                    f'      "{sentence.strip()[:150]}"\n'
                    f"      NOTICE says it does not. Both are published."
                )
                break
    return problems


def _selftest() -> int:
    failures: list[str] = []

    if check():
        failures.append(f"the real tree should be clean, got: {check()[:1]}")

    if not CLAIM.search("plots render using the Tellurium toolkit"):
        failures.append("did not match a real claim from the spec")
    if not CLAIM.search("Tellurium integration, file handling"):
        failures.append("did not match 'Tellurium integration'")
    if not CLAIM.search("built with the Tellurium systems-biology toolkit"):
        failures.append("did not match 'built with the Tellurium'")

    notice = "Terrium is unaffiliated with it, is not a fork of it, and does not depend on the tellurium package"
    if CLAIM.search(notice) and not DENIAL.search(notice):
        failures.append("would have flagged NOTICE's own denial")

    # The historical entry must be the only thing keeping the tree green.
    without = {k: v for k, v in HISTORICAL.items() if k != "Docw/terrium_spec.docx"}
    saved = dict(HISTORICAL)
    HISTORICAL.clear(); HISTORICAL.update(without)
    if not any("terrium_spec" in p for p in check()):
        failures.append("the spec is not actually caught when unexempted")
    HISTORICAL.clear(); HISTORICAL.update(saved)

    if not any("blind" in p for p in check(docs=[])):
        failures.append("the floor did not fire on an empty document list")

    for f in failures:
        print(f"  selftest FAIL: {f}")
    if failures:
        return 1
    print("OK: selftest passed -- the matcher fails on six defective inputs.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true", help="prove it can fail")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()

    problems = check()
    if problems:
        print("FAIL: a published document contradicts the non-affiliation notice")
        for p in problems:
            print(f"  - {p}")
        return 1

    docs = _documents()
    office = [p for p in docs if p.suffix in {".docx", ".pptx"}]
    print(
        f"OK: {len(docs)} document(s) checked ({len(office)} Office file(s)); "
        f"none claims Terrium is built on Tellurium. "
        f"{len(HISTORICAL)} recorded as historical."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
