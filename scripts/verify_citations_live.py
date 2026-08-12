#!/usr/bin/env python3
"""
verify_citations_live.py

Prove that the literature Terrium's resolvers cite is actually findable.

Static guards (check_citation_format.py, ADR 0008 amendments, the golden
set) ensure every citation carries a locator-shaped locator -- but
"locator-shaped" is not "locator". A URL that returns 404, a DOI that
resolves to nothing, or a BRENDA enzyme page that no longer lists the
reference would all pass static checks and still be unverifiable. This
script is the live half of that guarantee:

  * every golden-set tuple (Tests/test_golden_set.py) resolves to a real
    BRENDA enzyme page, and that page genuinely carries the reference id;
  * every known PMID resolves on PubMed;
  * every DOI in the model/resolved citations is registered (CrossRef API);
    doi.org redirects are avoided because publishers bot-gate them;
  * every static modelCitations URL in queryResolver.ts resolves.

It is a report, not a gate: literature moves (pages get restructured,
DOIs get corrected), so a failing check is a flag to re-verify by hand,
not an automatic CI failure. It reuses Tests/http_retry.py so the same
backoff/retry policy as the live resolvers applies.

Run:  python3 scripts/verify_citations_live.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "Tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from http_retry import retry_get  # noqa: E402

# --- Golden set (Tests/test_golden_set.py, hand-verified tuples) ---------
GOLDEN_SET = [
    {
        "id": "G1: LDH/lactate/Homo sapiens (Km 10.73 mM)",
        "ec": "1.1.1.27",
        "ref": "740253",
    },
    {
        "id": "G2: AChE/acetyl thiocholine/Homo sapiens (Km 0.09 mM)",
        "ec": "3.1.1.7",
        "ref": "649716",
    },
    {
        "id": "G3: LDH/lactate/Mus musculus (cross-species, Km 0.0026 mM)",
        "ec": "1.1.1.27",
        "ref": "740001",
    },
]

# PMIDs pinned by the golden set / literature chain (citation.py, pubmed.py).
PMIDS = ["740253", "34962677", "31520487"]

# DOIs cited for resolved values (popgen_resolver.py via stdpopsim; ADR 0017
# epidemiology registry). Kermack & McKendrick 1927 is the SIR model citation.
DOIS = [
    # "10.1038/ng.3141" was listed here as "Rahbari et al. 2015 (human
    # mutation rate)" and removed 2026-08-09. It is a THIRD distinct
    # Rahbari DOI, alongside ng.3285 (recombination -- was miscited for a
    # mutation rate) and ng.3469 (the actual germline-mutation paper,
    # verified via PubMed PMID 26656846). Nothing in the codebase cites
    # ng.3141: popgen_resolver.py resolves from stdpopsim and carries
    # stdpopsim's own citations (IHGSC 2001, Jonsson 2017), both of which
    # the discovery pass below picks up. An unverified DOI in a checker's
    # own allowlist is the checker asserting something it never checked.
    "10.1098/rspa.1927.0118",  # Kermack & McKendrick 1927, Proc. R. Soc. A
]

#: Files whose DOIs are DISCOVERED rather than listed above.
#:
#: A hardcoded DOI list only checks the DOIs someone remembered to add to
#: it. On 2026-08-09 `domain-literature.ts` -- which serves citations to
#: users -- carried `10.1038/35002131` for Elowitz & Leibler (2000), whose
#: real DOI is `10.1038/35002125` (PubMed, PMID 10659856). The wrong value
#: had propagated to five files. This checker did not catch it because the
#: file was not in the list and the DOI was not in DOIS.
#:
#: So the DOIs are now scraped out of the sources that actually publish
#: them. Adding a citation to any of these files enrols it automatically.
DOI_SOURCE_FILES = [
    ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/lib/domain-literature.ts",
    ROOT / "Terium/core/data_structures.py",
    ROOT / "Terium/continuous/model_building.py",
    ROOT / "Tests/epidemiology_resolver.py",
    ROOT / "Tests/popgen_resolver.py",
]

#: A DOI is `10.<registrant>/<suffix>`. The suffix is deliberately not
#: allowed to swallow trailing punctuation, quotes or markdown syntax,
#: which would otherwise produce DOIs that fail lookup for cosmetic
#: reasons and bury the real failures.
DOI_PATTERN = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>,)\]}]+)")


#: Lines that merely *discuss* a DOI rather than cite it. When a wrong DOI
#: is corrected, the comment explaining what it used to be stays behind --
#: and a naive scrape then re-checks the very DOI that was just removed,
#: turning every documented mistake into a permanent failing check. Three
#: corrected DOIs (the fabricated Michaelis-Menten one, the recombination
#: paper, "Mitotic motors") reappeared this way immediately after being
#: fixed.
_COMMENT_PREFIXES = ("#", "//", "*", "/*")


def _is_prose_line(line: str) -> bool:
    return line.lstrip().startswith(_COMMENT_PREFIXES)


def discovered_dois() -> dict[str, list[str]]:
    """Every DOI *cited* in DOI_SOURCE_FILES, mapped to where it appears.

    Comment lines are skipped: a DOI named in prose is being discussed, not
    asserted, and checking it reports failures for citations the code no
    longer makes.
    """
    found: dict[str, list[str]] = {}
    for path in DOI_SOURCE_FILES:
        if not path.is_file():
            # A configuration error, not an environmental one. Skipping it
            # silently meant that moving domain-literature.ts -- which alone
            # supplies 11 of the 13 discovered DOIs -- would drop the checked
            # set to one hardcoded entry, print "(1 DOIs: 1 listed, 0
            # discovered in source)", and still report "all literature checks
            # passed live". The count is a signal, but nobody diffs a count.
            raise FileNotFoundError(
                f"DOI source file {path} does not exist, so its citations "
                "were NOT checked. Update DOI_SOURCE_FILES if the file "
                "moved; a missing source must not shrink the checked set in "
                "silence."
            )
        for line in path.read_text(encoding="utf-8").splitlines():
            if _is_prose_line(line):
                continue
            for match in DOI_PATTERN.finditer(line):
                doi = match.group(1).rstrip(".;")
                found.setdefault(doi, []).append(path.name)
    return found

QUERY_RESOLVER = ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/lib/queryResolver.ts"

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"


def check(label: str, ok: bool, detail: str) -> bool:
    mark = PASS if ok else FAIL
    print(f"  {mark} {label}")
    if not ok:
        print(f"      {detail}")
    return ok


_STOPWORDS = {
    "a", "an", "and", "of", "the", "in", "on", "for", "to", "with", "by",
    "its", "их", "der", "die", "das", "und", "et", "al",
}


def _words(title: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z]{4,}", title.lower())
        if w not in _STOPWORDS
    }


def _titles_overlap(claimed: str, registered: str) -> bool:
    """Whether two titles plausibly name the same work.

    Deliberately lenient: our stored titles often append journal/volume
    text or bracket a translated original, so an exact match would be
    noise. Two content words in common is enough to say "same paper";
    zero in common is what a swapped DOI looks like.
    """
    claimed_words, registered_words = _words(claimed), _words(registered)
    if not claimed_words or not registered_words:
        return True  # nothing to compare -- do not manufacture a failure
    return len(claimed_words & registered_words) >= 2


def claimed_titles() -> dict[str, str]:
    """DOI -> the title our own source claims for it, where discoverable.

    Only domain-literature.ts is parsed: it is the file that pairs a DOI
    with a title in a machine-readable object literal, and it is the file
    that serves citations to users.
    """
    path = ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/lib/domain-literature.ts"
    if not path.is_file():
        # Returning {} disabled the TITLE-MISMATCH check for every DOI while
        # leaving every green tick in place. That check is the only part of
        # the DOI section that verifies the citation rather than the
        # identifier: it exists because 10.1038/ng.3285 (a RECOMBINATION-rate
        # paper) was cited to justify a MUTATION rate, resolved cleanly, and
        # passed. Degrading silently to "does this DOI exist" is the exact
        # regression it was written to prevent.
        raise FileNotFoundError(
            f"{path} does not exist, so no DOI could be title-checked. "
            "Every DOI would degrade to an existence check while still "
            "printing a tick."
        )
    text = path.read_text(encoding="utf-8")
    titles: dict[str, str] = {}
    # title: "..." (possibly concatenated across lines with +) then doi: "..."
    for block in re.finditer(
        # `[^{}]*?` keeps the match inside ONE object literal. Without it,
        # an entry that has a title but no doi (Lehninger, Fisher 1930)
        # lets the scan run on and pair that title with the NEXT entry's
        # doi -- which produced a map claiming bi201284u was "Lehninger
        # Principles of Biochemistry". A mis-paired map would report false
        # title mismatches, which is worse than not checking at all.
        r"title:\s*((?:\s*\"[^\"]*\"\s*\+?)+),[^{}]*?doi:\s*\"([^\"]+)\"",
        text,
        re.DOTALL,
    ):
        joined = "".join(re.findall(r'\"([^\"]*)\"', block.group(1)))
        titles[block.group(2)] = joined
    return titles



def brenda_url(ec: str) -> str:
    return f"https://www.brenda-enzymes.org/enzyme.php?ecno={ec}"


def main() -> int:
    failures = 0

    print("\nBRENDA golden-set enzyme pages (must resolve AND list the ref):")
    for entry in GOLDEN_SET:
        url = brenda_url(entry["ec"])
        try:
            r = retry_get(url, timeout=20)
            status = r.status_code
            body_ok = status == 200 and str(entry["ref"]) in r.text
            ok = status == 200 and body_ok
            if not ok and not body_ok:
                detail = (
                    f"{url} -> HTTP {status}; page does not contain ref "
                    f"{entry['ref']} (BRENDA may have restructured)"
                )
            else:
                detail = f"{url} -> HTTP {status}"
            if not check(f"[{entry['id']}]", ok, detail):
                failures += 1
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            failures += 1
            check(f"[{entry['id']}]", False, f"{url} -> {exc!r}")

    print("\nPubMed PMIDs (must resolve to a 200):")
    for pmid in PMIDS:
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        try:
            r = retry_get(url, timeout=20)
            ok = r.status_code == 200
            check(f"PMID {pmid}", ok, f"{url} -> HTTP {r.status_code}")
            if not ok:
                failures += 1
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            failures += 1
            check(f"PMID {pmid}", False, f"{url} -> {exc!r}")

    print(
        "\nDOIs (CrossRef registry = the DOI exists; publishers bot-gate doi.org"
        " redirects, so registry is the reliable probe):"
    )
    # The explicit list, plus every DOI scraped out of the files that
    # actually publish citations -- see DOI_SOURCE_FILES for why.
    scraped = discovered_dois()
    all_dois: dict[str, list[str]] = {doi: ["DOIS"] for doi in DOIS}
    for doi, sources in scraped.items():
        all_dois.setdefault(doi, []).extend(sources)

    print(f"  ({len(all_dois)} DOIs: {len(DOIS)} listed, "
          f"{len(scraped)} discovered in source)")

    # Hoisted out of the loop: this parses domain-literature.ts, and it was
    # being re-read and re-regexed once per DOI.
    claimed_by_doi = claimed_titles()
    title_checked = 0
    existence_only: list[str] = []

    for doi in sorted(all_dois):
        where = ", ".join(sorted(set(all_dois[doi])))
        url = f"https://api.crossref.org/works/{doi}"
        try:
            r = retry_get(url, timeout=20)
            ok = r.status_code == 200
            detail = f"{url} -> HTTP {r.status_code}"

            # A DOI that RESOLVES is not a DOI that supports the claim.
            # domain-literature.ts cited 10.1038/ng.3285 ("Variation and
            # heritability of RECOMBINATION rate in humans") to justify a
            # MUTATION rate: it resolved cleanly and this checker passed
            # it, because existence was all it tested. So the registered
            # title is printed alongside, and flagged when it shares no
            # meaningful words with the title claimed in our source.
            if ok:
                try:
                    titles = r.json()["message"].get("title") or []
                    registered = titles[0] if titles else ""
                except (ValueError, KeyError, IndexError):
                    registered = ""

                claimed = claimed_by_doi.get(doi, "")
                if registered and claimed:
                    title_checked += 1
                    detail = f"{url} -> {registered!r}"
                    if not _titles_overlap(claimed, registered):
                        ok = False
                        detail = (
                            f"TITLE MISMATCH\n"
                            f"        we cite : {claimed!r}\n"
                            f"        CrossRef: {registered!r}\n"
                            f"        The DOI exists but may be a different "
                            f"paper than the one being cited."
                        )
                else:
                    # This DOI got an EXISTENCE check only, and used to print
                    # a tick identical to one that was fully verified. Two
                    # different reasons land here -- our source claims no
                    # title for it, or CrossRef returned none -- and neither
                    # was visible in the output.
                    reason = (
                        "no title claimed in domain-literature.ts"
                        if not claimed
                        else "CrossRef returned no title"
                    )
                    existence_only.append(f"{doi} ({reason})")
                    detail = f"{url} -> exists; NOT title-checked ({reason})"
            # `check` prints detail only on failure, so a passing DOI's
            # registered title was being computed and discarded. The
            # existence-only marker is worth seeing on a pass, which is the
            # only time it matters.
            check(f"{doi}  [{where}]", ok, detail)
            if ok and doi in {e.split(" ", 1)[0] for e in existence_only}:
                print(f"      {detail}")
            if not ok:
                failures += 1
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            failures += 1
            check(f"{doi}  [{where}]", False, f"{url} -> {exc!r}")

    print("\nStatic modelCitations URLs in queryResolver.ts (must resolve):")
    urls = set()
    if not QUERY_RESOLVER.exists():
        failures += 1
        check(
            "queryResolver.ts",
            False,
            f"{QUERY_RESOLVER} does not exist, so NO static citation URL was "
            "checked.",
        )
    else:
        text = QUERY_RESOLVER.read_text()
        for match in re.finditer(r"https?://[^\s'\"]+", text):
            url = match.group(0).rstrip(".,;)")
            # The `not url.endswith("/")` filter used to live here, and it
            # made this entire section vacuous. queryResolver.ts contains
            # exactly two URLs, both `https://www.brenda-enzymes.org/`, and
            # both end in a slash -- so `urls` was ALWAYS empty. The section
            # printed a header saying "must resolve", iterated nothing, added
            # zero to `failures`, and fed a summary reading "all literature
            # checks passed live".
            #
            # A bare directory URL is exactly as worth checking as any other:
            # if brenda-enzymes.org stops resolving, every BRENDA citation
            # this project emits points at nothing.
            if url:
                urls.add(url)

        if not urls:
            failures += 1
            check(
                "URL extraction",
                False,
                "no URLs were extracted from queryResolver.ts, so this "
                "section checked nothing. Either the citations stopped "
                "carrying URLs or the pattern stopped matching; both are "
                "worth knowing, and neither is a pass.",
            )

    for url in sorted(urls):
        try:
            r = retry_get(url, timeout=20, follow_redirects=True)
            ok = r.status_code == 200
            check(url, ok, f"-> HTTP {r.status_code}")
            if not ok:
                failures += 1
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            failures += 1
            check(url, False, f"-> {exc!r}")

    # Coverage, printed whether or not anything failed. "All literature
    # checks passed" was a conclusion about coverage the script never
    # computed: it was true of whatever happened to get checked, and stayed
    # true when that set shrank to nothing.
    print(
        f"\nCoverage: {len(all_dois)} DOI(s) checked, {title_checked} with "
        f"title verification, {len(urls)} URL(s) checked."
    )
    if existence_only:
        print(
            f"  {WARN} {len(existence_only)} DOI(s) got an existence check "
            "only -- the DOI resolves, but nothing confirmed it is the paper "
            "being cited:"
        )
        for entry in existence_only:
            print(f"      {entry}")
    if not all_dois:
        failures += 1
        print(
            f"  {FAIL} zero DOIs were checked. Refusing to report success: "
            "an empty check set is not a clean one."
        )

    print()
    if failures == 0:
        print(
            f"{PASS} literature checks passed live "
            f"({len(all_dois)} DOIs, {title_checked} title-verified, "
            f"{len(urls)} URLs)"
        )
    else:
        print(f"{FAIL} {failures} check(s) failed — re-verify by hand")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
