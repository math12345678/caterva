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
    "10.1038/ng.3141",  # Rahbari et al. 2015, Nature Genetics (human mutation rate)
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
    ROOT / "Tellurium/core/data_structures.py",
    ROOT / "Tellurium/continuous/model_building.py",
    ROOT / "Tests/epidemiology_resolver.py",
    ROOT / "Tests/popgen_resolver.py",
]

#: A DOI is `10.<registrant>/<suffix>`. The suffix is deliberately not
#: allowed to swallow trailing punctuation, quotes or markdown syntax,
#: which would otherwise produce DOIs that fail lookup for cosmetic
#: reasons and bury the real failures.
DOI_PATTERN = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>,)\]}]+)")


def discovered_dois() -> dict[str, list[str]]:
    """Every DOI appearing in DOI_SOURCE_FILES, mapped to where it appears."""
    found: dict[str, list[str]] = {}
    for path in DOI_SOURCE_FILES:
        if not path.is_file():
            continue
        for match in DOI_PATTERN.finditer(path.read_text(encoding="utf-8")):
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

    for doi in sorted(all_dois):
        where = ", ".join(sorted(set(all_dois[doi])))
        url = f"https://api.crossref.org/works/{doi}"
        try:
            r = retry_get(url, timeout=20)
            ok = r.status_code == 200
            check(f"{doi}  [{where}]", ok, f"{url} -> HTTP {r.status_code}")
            if not ok:
                failures += 1
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            failures += 1
            check(f"{doi}  [{where}]", False, f"{url} -> {exc!r}")

    print("\nStatic modelCitations URLs in queryResolver.ts (must resolve):")
    urls = set()
    if QUERY_RESOLVER.exists():
        text = QUERY_RESOLVER.read_text()
        for match in re.finditer(r"https?://[^\s'\"]+", text):
            url = match.group(0).rstrip(".,;)")
            if url and not url.endswith("/") and url not in urls:
                urls.add(url)
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

    print()
    if failures == 0:
        print(f"{PASS} all literature checks passed live")
    else:
        print(f"{FAIL} {failures} check(s) failed — re-verify by hand")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
