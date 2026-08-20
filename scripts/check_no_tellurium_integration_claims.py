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
import subprocess
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
    "docs/REMOVE_CONFIDENTIAL_FROM_HISTORY.md": (
        "The remediation plan for these exact files. Its inventory reads "
        '`Docw/terrium_full.docx    also: claims \"Tellurium integration\"` '
        "-- the phrase is the thing being removed, named so somebody can "
        "find it. This guard failed the build on it, so the document "
        "planning the cleanup was the one blocking CI, and the only way to "
        "go green would have been to describe the offending files "
        "vaguely enough that nobody could act on them."
    ),
}

#: Every DISCUSSES entry exempts a WHOLE document, so a genuine new claim in
#: one of these would go unseen. That cost was acceptable at two entries and
#: is worth watching at three: `Tests/test_no_tellurium_integration_claims.py`
#: pins this dict, so it cannot grow without somebody deciding it should.
#:
#: The narrower fix -- exempt the quoted occurrence rather than the file --
#: is what `check_documented_counts.is_quoted` does for counts. It is not
#: done here because this guard's author chose per-document exemption with
#: written reasons and said why; changing that is a redesign, not a repair,
#: and belongs to whoever owns the design rather than to the pass that
#: happened to hit the false positive.

#: `**/*.docx`, not `Docw/*.docx`. The first version of this guard named the
#: one directory where the claims had been found, which is the defect it was
#: written to catch, committed one pass after warning about it. There were
#: copies: Science-Agent-Pipeline/attached_assets/terrium_spec_*.docx and
#: terrium_full_*.docx hold the same four claims and the same "Confidential"
#: marking, tracked, and were never scanned. Removing Docw/ alone would have
#: removed nothing.
SUFFIXES = (".md", ".docx", ".pptx")

#: Directories that are not ours to police.
_SKIP_PARTS = {"node_modules", ".venv", "venv", "dist", "build", ".git"}

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
    """Every *tracked* document. `git ls-files`, not a filesystem walk.

    Two reasons, and the second is the point. A `**/*.docx` glob walks
    node_modules and everything else before any filter applies, which made this
    guard take minutes. And "published" is exactly what git tracks: an
    untracked file on somebody's disk is not a document the world can read, and
    a tracked one is, wherever it happens to live. Asking git removes the need
    to guess which directories to police.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []

    found: list[Path] = []
    for rel in out.stdout.split("\0"):
        if not rel or not rel.endswith(SUFFIXES):
            continue
        parts = Path(rel).parts
        if "build-stages" in parts or _SKIP_PARTS & set(parts):
            continue
        path = REPO_ROOT / rel
        if path.is_file():
            found.append(path)
    return sorted(set(found))


# THE CONVENTION, IMPORTED RATHER THAN RESTATED
# ---------------------------------------------
# ADR 0099 states it once:
#
#     A claim written plainly is an assertion and is checked. The same words
#     in quotation marks or backticks are a citation and are not.
#
# and adds that the rule "is about claims, not numbers" -- it was written
# for `check_documented_counts.is_quoted`, and a guard reading a PHRASE had
# no reason to look for it.
#
# This guard then flagged `docs/adr/0099-plain-asserts-quoted-cites.md`,
# whose entire subject is three guards confusing a citation with an
# assertion. It reproduced the defect the ADR beside it describes, and did
# so on every CI run: the failure sat in the workflow and turned main red
# for seven consecutive commits.
#
# ADR 0099 offers two repairs and prefers the narrow one. A `DISCUSSES`
# entry exempts a whole FILE, so a future ADR quoting the phrase trips this
# again and the next author adds another entry. `is_quoted` exempts the
# quoted OCCURRENCE, so every document that quotes the claim in order to
# discuss it is covered once and forever.
#
# Imported from the module that owns it. A second copy of a convention is
# two conventions the day one of them is edited (ADR 0003).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_documented_counts import is_quoted  # noqa: E402


def _sentences(text: str) -> list[str]:
    """Sentences, not lines.

    THE DEFECT THIS FIXES
    ---------------------
    This split on EVERY newline. Markdown hard-wraps prose inside a
    paragraph, so a sentence spanning two lines was torn in half at the
    wrap point — and both halves were then judged as if each were a whole
    claim.

    Measured, in `docs/adr/0099-plain-asserts-quoted-cites.md`:

        ...found no denial word on the line, and reported the document as
        claiming
        Terrium is built on Tellurium.

    The second line alone reads as a flat assertion. With the first, it is
    a REPORT of somebody else's claim. The guard flagged the tail and
    turned CI red on every commit for a week.

    It is not only about reporting clauses: `DENIAL` is checked per
    sentence too, so any denial that happened to land on the previous line
    was invisible. A false positive from a hard wrap is not an edge case in
    a repository whose prose is wrapped at 72 columns throughout.

    Paragraphs are separated by blank lines; within one, newlines are
    whitespace. That is what markdown means by them, and now what this
    reads.
    """
    # A FENCED BLOCK IS QUOTED MATERIAL.
    #
    # ADR 0099's convention — a claim written plainly is an assertion, the
    # same words in quotation marks or backticks are a citation — has a
    # third form this guard meets constantly: ``` blocks. Their entire
    # purpose is to reproduce text verbatim.
    #
    # Found by this guard flagging `docs/adr/0130-green-was-a-local-opinion.md`,
    # the ADR describing the previous repair, which quotes the offending
    # sentence inside a fence in order to explain it. Every future document
    # that shows the reader what the guard catches would trip it too — a
    # guard nobody can write about is one that gets exempted per-file until
    # it means nothing.
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)

    sentences: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        joined = re.sub(r"\s*\n\s*", " ", paragraph.strip())
        if joined:
            sentences.extend(re.split(r"(?<=[.!?;:])\s+", joined))
    return sentences


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
            match = CLAIM.search(sentence)
            if match and not DENIAL.search(sentence) and not is_quoted(
                sentence, match.start(), match.end()
            ):
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

    # A document carrying the claim must be caught. This used to assert that
    # removing Docw/terrium_spec.docx from HISTORICAL made the tree fail --
    # a real test until 2026-08-16, when those files were removed from the
    # repository. `_documents()` reads `git ls-files`, so an untracked file is
    # not scanned at all and the exemption stopped being load-bearing. Keeping
    # the old assertion would have meant a selftest that passed for a reason
    # unrelated to what it claimed to check. It is replaced, not deleted.
    # The probe lives inside REPO_ROOT: check() reports paths via
    # `relative_to(REPO_ROOT)`, so a file in /tmp raises ValueError rather
    # than being scanned. Caught by this selftest failing.
    probe = REPO_ROOT / ".selftest_probe.md"
    try:
        probe.write_text("Plots render using the Tellurium toolkit for ODE domains.\n")
        # The floor runs before the scan, so the probe list must satisfy BOTH
        # halves of it or check() returns "blind" and never looks at the
        # probe -- which is what this selftest did on its first two attempts.
        office = [p for p in _documents() if p.suffix in {".docx", ".pptx"}]
        padding = [probe] * _MIN_DOCS + office[:1]
        if not any(".selftest_probe.md" in p for p in check(docs=padding)):
            failures.append("a document carrying the claim was not caught")
    finally:
        probe.unlink(missing_ok=True)

    # The HISTORICAL entries are now inert: the files they name are no longer
    # tracked. That is recorded rather than removed, because the reasons are
    # the record of why those documents were withdrawn.
    if any((REPO_ROOT / rel).exists() and rel in {
        p.relative_to(REPO_ROOT).as_posix() for p in _documents()
    } for rel in HISTORICAL):
        failures.append("a HISTORICAL file is tracked again; re-check its entry")

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
