#!/usr/bin/env python3
"""
verify_citations_live.py

Prove that the literature Caterva's resolvers cite is actually findable.

Static guards (check_citation_format.py, ADR 0008 amendments, the golden
set) ensure every citation carries a locator-shaped locator -- but
"locator-shaped" is not "locator". A URL that returns 404, a DOI that
resolves to nothing, or a BRENDA enzyme page that no longer lists the
reference would all pass static checks and still be unverifiable. This
script is the live half of that guarantee:

  * every golden-set tuple (Tests/test_golden_set.py) resolves to a real
    BRENDA enzyme page, and that page genuinely carries the reference id;
  * every pinned PMID is the paper it is pinned for: its NCBI esummary
    title must name the topic it is cited for (resolving is not enough --
    see PMIDS);
  * every DOI in the model/resolved citations is registered (CrossRef API);
    doi.org redirects are avoided because publishers bot-gate them;
  * every static modelCitations URL in queryResolver.ts resolves.

It is a report, not a gate: literature moves (pages get restructured,
DOIs get corrected), so a failing check is a flag to re-verify by hand,
not an automatic CI failure. It reuses Tests/http_retry.py so the same
backoff/retry policy as the live resolvers applies.

THREE OUTCOMES, not two. Every check ends MATCHED (the host answered and
the answer supports the citation), MISMATCHED (the host answered and the
answer contradicts it: a 404/410, a missing reference id, a title about
something else), or UNREACHABLE (the host did not give an answer: a
timeout, a connection error, a 429/5xx, a bot gate). Until 2026-10-31 a
network failure was counted as a failed citation, so a flaky host and a
wrong reference printed the same red cross.

Exit 0 = everything matched, 2 = at least one mismatch, 1 = no mismatch
but at least one check could not be made. A mismatch outranks
unreachability: it is a finding, the other is an absence of one.

NCBI_API_KEY is used for the PubMed esummary call when it is set in the
environment or in Science-Agent-Pipeline/.env. It is optional (NCBI
allows 3 requests/s without one) and its value is never printed.

Run:  python3 scripts/verify_citations_live.py
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "Tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from http_retry import retry_get  # noqa: E402

#: Hard wall-clock budget for the whole run. The point of this script is to
#: re-verify citations, and a citation whose host hangs is UNREACHABLE, not
#: a reason to hang the build. 2026-08-14: a stalled upstream host combined
#: with generous 20s-per-phase httpx timeouts made a single check eat the
#: full 120s guard budget. A bounded deadline turns that into a fast,
#: explicit failure.
BUDGET_SECONDS = 90
_DEADLINE = time.monotonic() + BUDGET_SECONDS


def bounded_get(url: str, **kwargs: object) -> httpx.Response:
    """retry_get with the remaining global budget applied to every phase.

    httpx's default getaddrinfo path does not honor timeouts, so the only
    hard guarantee is the outer budget: once it is spent, we refuse to
    start another request (that raises, and the caller reports a clean
    failure) rather than sit in a hung connect.
    """
    remaining = _DEADLINE - time.monotonic()
    if remaining <= 0:
        raise httpx.TimeoutException(
            f"global {BUDGET_SECONDS}s budget exhausted before checking {url}"
        )
    per_phase = min(12.0, remaining)
    timeout = httpx.Timeout(
        per_phase, connect=min(8.0, remaining),
        read=per_phase, write=per_phase, pool=min(8.0, remaining),
    )
    return retry_get(url, timeout=timeout, **kwargs)

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

# PMIDs pinned by the literature chain (citation.py, pubmed.py), each with
# words of which at least one must appear in the paper's PubMed title.
#
# 740253 was listed here until 2026-10-31: it is a BRENDA reference id
# (golden tuple G1, above), not a PMID, and PubMed resolves it -- to an
# unrelated 1978 paper on jugular-vein cannulation. The check was "the
# PubMed page answers 2xx", so a number from the wrong namespace passed.
# An identifier that resolves is not an identifier that is right; the
# title has to be about what it is cited for.
PMIDS = {
    "34962677": ("lactate dehydrogenase",),
    "31520487": ("hexokinase",),
}

ENV_FILE = ROOT / "Science-Agent-Pipeline" / ".env"


def load_env_keys(names: tuple[str, ...] = ("NCBI_API_KEY", "CORE_API_KEY")) -> dict[str, str]:
    """API keys from the process environment, else Science-Agent-Pipeline/.env.

    The environment wins so CI (which has no .env) and a deliberate
    override both behave. Values are returned to the caller and never
    printed; scrub() exists so an exception message carrying a request URL
    cannot print one either.
    """
    keys = {n: os.environ[n] for n in names if os.environ.get(n)}
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            k = k.strip().removeprefix("export ").strip()
            v = v.strip().strip("\"'")
            if k in names and v and k not in keys:
                keys[k] = v
    return keys


def scrub(text: str, keys: dict[str, str]) -> str:
    """Replace every key value in text with <redacted>."""
    for v in keys.values():
        if v:
            text = text.replace(v, "<redacted>")
    return text

# DOIs cited for resolved values (popgen_resolver.py via stdpopsim; ADR 0017
# epidemiology registry). Kermack & McKendrick 1927 is the SIR model citation.
DOIS = [
    # "10.1038/ng.3141" was listed here as "Rahbari et al. 2015 (human
    # mutation rate)" and removed 2026-08-09. It is a THIRD distinct
    # Rahbari DOI, alongside ng.3285 (recombination -- was miscited for a
    # mutation rate) and ng.3469 (the actual germline-mutation paper,
    # verified via PubMed PMID 26656846). Nothing in the codebase cites
    # ng.3141: popgen_resolver.py resolves from stdpopsim and carries
    # stdpopsim's own bundled citations, which the discovery pass below
    # picks up. An unverified DOI in a checker's own allowlist is the
    # checker asserting something it never checked.
    #
    # This comment named those bundled citations as "IHGSC 2001, Jonsson
    # 2017" until 2026-09-05. Checked by running stdpopsim 0.3.0: HomSap
    # bundles IHGSC 2001 for the GENOME ASSEMBLY, Tian/Browning/Browning
    # 2019 for the MUTATION RATE, and HapMap 2007 for recombination --
    # Jonsson is not in the HomSap catalog at all. A citation checker
    # repeating an unchecked citation claim in its own source is the
    # failure this script exists to catch, one level up.
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
    # Added 2026-09-05, and the reason is the paragraph directly above.
    #
    # These four publish DOIs straight into live API responses --
    # /api/dashboard/overview and /api/pipeline/literature both print a
    # STRENDA citation, and verifiable-metrics.ts is the constant behind
    # them. None was enrolled, and the DOI they served,
    # 10.1038/nbt0610-592 attributed to "Gelperin et al. (2010)", did not
    # exist: doi.org and CrossRef 404, PubMed has no such paper, and
    # CrossRef's full Nature Biotechnology 28(6) listing has no article
    # starting at page 592. It was the citation for the standard that
    # decides whether a resolved Km is reported "verified" or "flagged".
    #
    # Exactly the blind spot this list's own comment describes, hit a
    # second time, on the files whose output a user reads.
    ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/lib/verifiable-metrics.ts",
    ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/lib/strenda-validator.ts",
    ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/routes/dashboard.ts",
    ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/routes/pipeline.ts",
    ROOT / "caterva/core/data_structures.py",
    ROOT / "caterva/continuous/model_building.py",
    ROOT / "Tests/epidemiology_resolver.py",
    ROOT / "Tests/popgen_resolver.py",
    # Added 2026-09-05. This list held only .ts and .py sources, so the one
    # document in the repository whose entire purpose is to enumerate
    # Caterva's citations was the one file the citation checker never read.
    #
    # That gap has a measured cost. `domain-literature.ts` was corrected on
    # 2026-08-09 from doi 10.1038/ng.3285 -- which CrossRef records as
    # Polderman et al. (2015), a twin-studies heritability meta-analysis --
    # to Rahbari's actual germline-mutation paper, 10.1038/ng.3469.
    # Business/build-stages/STAGE_10_PART_06.md then named "the ng.3285
    # citation surviving in two markdown files after the code was fixed" as
    # a known symptom. It survived in THIS file for another month, because
    # nothing read it.
    #
    # Moved from the root to docs/science/ on 2026-10-24. A path that stops
    # existing raises in discovered_dois() rather than shrinking this list,
    # so the move had to be followed here for the check to run at all.
    ROOT / "docs" / "science" / "LITERATURE_BACKING_DATABASE.md",
]

#: A DOI is `10.<registrant>/<suffix>`. The suffix is deliberately not
#: allowed to swallow trailing punctuation, quotes or markdown syntax,
#: which would otherwise produce DOIs that fail lookup for cosmetic
#: reasons and bury the real failures.
#:
#: PARENTHESES ARE PART OF REAL DOIs. Elsevier's legacy scheme puts the
#: two-digit year in parens -- Gillespie 1976 is
#: `10.1016/0021-9991(76)90041-3` -- and the first version of this
#: pattern excluded `)` outright, so that DOI truncated to
#: `10.1016/0021-9991(76` and reported HTTP 404 against CrossRef: the
#: checker manufacturing exactly the cosmetic failure this comment says
#: it refuses to. (It surfaced the moment a citation was CORRECTED to
#: that DOI -- the fix for a wrong reference tripped the checker's own
#: matcher-narrower-than-its-subject defect, this repository's oldest
#: recurring shape.) `)` is now allowed mid-DOI, and `_trim_doi` strips
#: only a trailing unbalanced `)` -- the "(see 10.1234/x)" prose case.
DOI_PATTERN = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>,\]}]+)")


def _trim_doi(doi: str) -> str:
    """Strip trailing `)` only when unbalanced against `(` in the DOI."""
    while doi.endswith(")") and doi.count(")") > doi.count("("):
        doi = doi[:-1]
    return doi.rstrip(".;:")


#: Lines that merely *discuss* a DOI rather than cite it. When a wrong DOI
#: is corrected, the comment explaining what it used to be stays behind --
#: and a naive scrape then re-checks the very DOI that was just removed,
#: turning every documented mistake into a permanent failing check. Three
#: corrected DOIs (the fabricated Michaelis-Menten one, the recombination
#: paper, "Mitotic motors") reappeared this way immediately after being
#: fixed.
_COMMENT_PREFIXES = ("#", "//", "*", "/*")

#: The same rule, for markdown. A `>` blockquote is this repository's
#: house style for "here is what this entry USED to say and why it was
#: wrong" -- see the correction notes throughout
#: docs/science/LITERATURE_BACKING_DATABASE.md -- so it is the markdown
#: equivalent of a comment: discussion, not assertion.
#:
#: Note that `*` is deliberately NOT reused here even though it appears in
#: _COMMENT_PREFIXES: in C-family sources it continues a block comment, but
#: in markdown it opens a bullet, and treating every `* ` bullet as prose
#: would silently exclude whole reference lists from the check.
_MARKDOWN_PROSE_PREFIXES = (">",)

#: In markdown, a DOI is ASSERTED only when written as a resolvable link.
#: A bare or backticked DOI in running text is being named, usually to
#: record that it was wrong: the Harter entry in
#: docs/science/LITERATURE_BACKING_DATABASE.md
#: cites `https://doi.org/10.2307/1403077` and, on the very same line,
#: backticks `10.2307/1402059` to say that DOI resolves to a different
#: paper. A line-level prose rule cannot separate those two; the link form
#: can.
MARKDOWN_DOI_PATTERN = re.compile(
    r"https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/[^\s\"'<>,\]}`]+)"
)


def _is_prose_line(line: str, *, markdown: bool = False) -> bool:
    if markdown:
        return line.lstrip().startswith(_MARKDOWN_PROSE_PREFIXES)
    return line.lstrip().startswith(_COMMENT_PREFIXES)


def _dois_asserted_in(line: str, *, markdown: bool = False) -> list[str]:
    """The DOIs this line CITES, as opposed to merely mentions."""
    pattern = MARKDOWN_DOI_PATTERN if markdown else DOI_PATTERN
    return [_trim_doi(m.group(1)) for m in pattern.finditer(line)]


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
        markdown = path.suffix.lower() == ".md"
        for line in path.read_text(encoding="utf-8").splitlines():
            if _is_prose_line(line, markdown=markdown):
                continue
            for doi in _dois_asserted_in(line, markdown=markdown):
                found.setdefault(doi, []).append(path.name)
    return found

QUERY_RESOLVER = ROOT / "Science-Agent-Pipeline/artifacts/api-server/src/lib/queryResolver.ts"

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"
SKIP = "\033[33m?\033[0m"

MATCHED, MISMATCHED, UNREACHABLE = "matched", "mismatched", "unreachable"

#: Statuses that ARE an answer: the host is saying the thing is not there.
#: Anything else outside 2xx (403 bot gates, 429, 5xx) says nothing about the
#: citation -- only that we did not get to ask.
ABSENT_STATUSES = frozenset({404, 410})

#: A citation URL that is a DOI redirect; group 1 is the DOI.
DOI_URL = re.compile(r"https?://(?:dx\.)?doi\.org/(10\.\S+)$", re.IGNORECASE)


def report(label: str, outcome: str, detail: str, tally: dict[str, int]) -> str:
    """Print one check in its three-outcome form and count it."""
    tally[outcome] += 1
    mark = {MATCHED: PASS, MISMATCHED: FAIL, UNREACHABLE: SKIP}[outcome]
    print(f"  {mark} {label}", flush=True)
    if outcome != MATCHED:
        tag = "UNREACHABLE: " if outcome == UNREACHABLE else ""
        print(f"      {tag}{detail}", flush=True)
    return outcome


def status_outcome(status: int) -> str | None:
    """None for a 2xx (the caller judges the body), else the outcome."""
    if is_ok(status):
        return None
    return MISMATCHED if status in ABSENT_STATUSES else UNREACHABLE


def is_ok(status: int) -> bool:
    """Any 2xx is a resolve.

    Strictly `== 200` has failed twice in the wild: PubMed's CDN answered
    203 Non-Authoritative Information while serving the page, and BRENDA
    answers 200/203 interchangeably. 2xx means the host answered.
    """
    return 200 <= status < 300


_STOPWORDS = {
    "a", "an", "and", "of", "the", "in", "on", "for", "to", "with", "by",
    "its", "их", "der", "die", "das", "und", "et", "al",
}


def _words(title: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z]{4,}", title.lower())
        if w not in _STOPWORDS
    }


#: How many distinctive words each side must have before two titles that
#: share vocabulary are called AMBIGUOUS rather than the same work.
#:
#: Two, because one is routinely produced by punctuation, a subtitle, or the
#: journal text our stored titles append -- and calling those ambiguous would
#: flood the report and get it ignored.
_DISTINCTIVE_THRESHOLD = 2


def compare_titles(claimed: str, registered: str) -> str:
    """`"match"`, `"mismatch"`, `"ambiguous"`, or `"unknown"`.

    Three states plus "we could not look", because two is not enough here.

    THE CASE THE BOOLEAN VERSION MISSED
    -----------------------------------
    `_titles_overlap` returned True on two content words in common. That
    catches a DOI swapped for a paper about something else -- the fabricated
    recombination-rate DOI cited for a mutation rate, which is the defect it
    was written for. It cannot catch the swap that actually happens.

    Measured on two real papers this repository cites:

        claimed:    "A general method for numerically simulating the
                     stochastic time evolution of coupled chemical
                     reactions"          (Gillespie 1976, J. Comput. Phys.)
        registered: "Exact stochastic simulation of coupled chemical
                     reactions"          (Gillespie 1977, J. Phys. Chem.)

        shared: {chemical, coupled, reactions, stochastic}  -> 4 >= 2 -> True

    Nobody accidentally cites a paper on an unrelated subject. They cite the
    ADJACENT paper -- same author, same algorithm, one year apart -- and
    those two share vocabulary by construction. The check passed exactly the
    error it is most likely to meet.

    So: shared vocabulary is necessary and not sufficient. When BOTH titles
    carry distinctive words the other lacks, they may be two papers rather
    than one description of one, and that is reported as ambiguous rather
    than waved through.

    Containment stays lenient, deliberately. Our stored titles append
    journal/volume text and bracket translated originals, so the registered
    title is often a subset of the claimed one -- one distinctive side only,
    which is a decorated match, not two papers.
    """
    claimed_words, registered_words = _words(claimed), _words(registered)
    if not claimed_words or not registered_words:
        # Nothing to compare. NOT a pass -- the caller reports this
        # separately, because "we could not check" reading as "checked and
        # fine" is the inversion this project keeps finding.
        return "unknown"

    if len(claimed_words & registered_words) < 2:
        return "mismatch"

    only_claimed = claimed_words - registered_words
    only_registered = registered_words - claimed_words
    if (
        len(only_claimed) >= _DISTINCTIVE_THRESHOLD
        and len(only_registered) >= _DISTINCTIVE_THRESHOLD
    ):
        return "ambiguous"
    return "match"


def _titles_overlap(claimed: str, registered: str) -> bool:
    """Back-compatible boolean: only an outright mismatch is False.

    Retained so the pass/fail column keeps its old meaning -- an ambiguous
    pair is not evidence of a wrong citation, and failing on it would turn a
    report people read into one they mute. Ambiguity is surfaced in its own
    section instead.
    """
    return compare_titles(claimed, registered) != "mismatch"


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


def check_pmids(tally: dict[str, int], keys: dict[str, str]) -> None:
    """Each pinned PMID's PubMed title must name the topic it is cited for.

    One esummary call for all of them. NCBI answers 200 for an id it does
    not know, with an `error` field in that id's entry, so "not in PubMed"
    is a MISMATCH read from the body, not from a status code.
    """
    print("\nPubMed PMIDs (title must mention the topic cited for):")
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pubmed", "retmode": "json", "id": ",".join(PMIDS)}
    if keys.get("NCBI_API_KEY"):
        params["api_key"] = keys["NCBI_API_KEY"]
    try:
        r = bounded_get(url, params=params)
        status = status_outcome(r.status_code)
        result = r.json().get("result", {}) if status is None else {}
    except (httpx.HTTPError, ValueError) as exc:  # pragma: no cover - network
        detail = scrub(f"esummary -> {exc!r}", keys)
        for pmid in PMIDS:
            report(f"PMID {pmid}", UNREACHABLE, detail, tally)
        return
    if status is not None:
        # A non-2xx for the whole batch says nothing about any one PMID: a
        # 404 here is the endpoint moving, not every pinned paper vanishing.
        for pmid in PMIDS:
            report(f"PMID {pmid}", UNREACHABLE,
                   f"esummary -> HTTP {r.status_code}", tally)
        return
    for pmid, topics in PMIDS.items():
        entry = result.get(pmid)
        if not isinstance(entry, dict):
            report(f"PMID {pmid}", UNREACHABLE,
                   "esummary answered without an entry for this id", tally)
            continue
        if "error" in entry:
            report(f"PMID {pmid}", MISMATCHED,
                   f"PubMed has no such paper ({entry['error']!r})", tally)
            continue
        title = entry.get("title", "")
        ok = any(t in title.lower() for t in topics)
        report(f"PMID {pmid}", MATCHED if ok else MISMATCHED,
               f"title {title!r} mentions none of {topics}", tally)
        if ok:
            print(f"      {title!r}", flush=True)


def main() -> int:
    tally = {MATCHED: 0, MISMATCHED: 0, UNREACHABLE: 0}
    keys = load_env_keys(("NCBI_API_KEY",))

    print("\nBRENDA golden-set enzyme pages (must resolve AND list the ref):")
    for entry in GOLDEN_SET:
        url = brenda_url(entry["ec"])
        label = f"[{entry['id']}]"
        try:
            r = bounded_get(url)
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            report(label, UNREACHABLE, f"{url} -> {exc!r}", tally)
            continue
        status = status_outcome(r.status_code)
        if status is not None:
            report(label, status, f"{url} -> HTTP {r.status_code}", tally)
        elif str(entry["ref"]) in r.text:
            report(label, MATCHED, "", tally)
        else:
            report(label, MISMATCHED,
                   f"{url} -> HTTP {r.status_code}; page does not contain ref "
                   f"{entry['ref']} (BRENDA may have restructured)", tally)

    check_pmids(tally, keys)

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
    ambiguous: list[str] = []

    for doi in sorted(all_dois):
        where = ", ".join(sorted(set(all_dois[doi])))
        url = f"https://api.crossref.org/works/{doi}"
        label = f"{doi}  [{where}]"
        try:
            r = bounded_get(url)
            status = status_outcome(r.status_code)
            if status is not None:
                # 404 is CrossRef saying the DOI is not registered: a
                # finding. 429/5xx is CrossRef not answering: not one.
                report(label, status, f"{url} -> HTTP {r.status_code}", tally)
                continue
            ok = True
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
                    verdict = compare_titles(claimed, registered)
                    if verdict == "ambiguous":
                        # Shared vocabulary, but each title carries words the
                        # other lacks. Two papers by one author on one topic
                        # look exactly like this, and so does one paper
                        # described two ways -- which is why it is listed for
                        # a human rather than decided here.
                        ambiguous.append(
                            f"{doi} [{where}]\n"
                            f"        we cite : {claimed!r}\n"
                            f"        CrossRef: {registered!r}"
                        )
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
            # report() prints detail only when not matched, so a passing DOI's
            # registered title was being computed and discarded. The
            # existence-only marker is worth seeing on a pass, which is the
            # only time it matters.
            report(label, MATCHED if ok else MISMATCHED, detail, tally)
            if ok and doi in {e.split(" ", 1)[0] for e in existence_only}:
                print(f"      {detail}")
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            report(label, UNREACHABLE, f"{url} -> {exc!r}", tally)

    if ambiguous:
        print(
            f"\n{len(ambiguous)} DOI(s) could NOT be told apart from a "
            "neighbouring paper:"
        )
        for item in ambiguous:
            print(f"      {item}")
        print(
            "      Both titles share vocabulary AND each carries words the\n"
            "      other lacks. That is what an adjacent paper by the same\n"
            "      author looks like -- check these by hand; the automated\n"
            "      comparison cannot settle them."
        )

    print("\nStatic modelCitations URLs in queryResolver.ts (must resolve):")
    urls = set()
    if not QUERY_RESOLVER.exists():
        report(
            "queryResolver.ts",
            MISMATCHED,
            f"{QUERY_RESOLVER} does not exist, so NO static citation URL was "
            "checked.",
            tally,
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
            # zero to the failure count, and fed a summary reading "all literature
            # checks passed live".
            #
            # A bare directory URL is exactly as worth checking as any other:
            # if brenda-enzymes.org stops resolving, every BRENDA citation
            # this project emits points at nothing.
            if url:
                urls.add(url)

        if not urls:
            report(
                "URL extraction",
                MISMATCHED,
                "no URLs were extracted from queryResolver.ts, so this "
                "section checked nothing. Either the citations stopped "
                "carrying URLs or the pattern stopped matching; both are "
                "worth knowing, and neither is a pass.",
                tally,
            )

    for url in sorted(urls):
        # A doi.org URL is asked of CrossRef, for the reason the module
        # docstring gives: publishers bot-gate the doi.org redirect, so
        # fetching it answers 403 and says nothing about the citation. This
        # section asked doi.org directly anyway, and every doi.org citation
        # in queryResolver.ts came back UNREACHABLE on every run.
        doi = DOI_URL.match(url)
        target = f"https://api.crossref.org/works/{doi.group(1)}" if doi else url
        label = f"{url}  (via CrossRef)" if doi else url
        try:
            r = bounded_get(target, follow_redirects=True)
            outcome = status_outcome(r.status_code) or MATCHED
            report(label, outcome, f"{target} -> HTTP {r.status_code}", tally)
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            report(label, UNREACHABLE, f"{target} -> {exc!r}", tally)

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
        for line in existence_only:
            print(f"      {line}")
    if not all_dois:
        tally[MISMATCHED] += 1
        print(
            f"  {FAIL} zero DOIs were checked. Refusing to report success: "
            "an empty check set is not a clean one."
        )

    print(
        f"\nOutcomes: {tally[MATCHED]} matched, {tally[MISMATCHED]} "
        f"mismatched, {tally[UNREACHABLE]} unreachable."
    )
    if tally[MISMATCHED]:
        print(f"{FAIL} {tally[MISMATCHED]} check(s) MISMATCHED — re-verify by hand")
        return 2
    if tally[UNREACHABLE]:
        print(
            f"{SKIP} nothing mismatched, but {tally[UNREACHABLE]} check(s) "
            "could not be made. That is not a pass: re-run when the hosts "
            "answer."
        )
        return 1
    print(
        f"{PASS} literature checks passed live "
        f"({len(all_dois)} DOIs, {title_checked} title-verified, "
        f"{len(urls)} URLs)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
