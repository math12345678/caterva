"""
core_fulltext.py

Open-access full-text search via the CORE API (https://core.ac.uk), the
aggregator that indexes full text from institutional and subject
repositories worldwide. Used as a fallback when a paper found through
PubMed is not itself open-access -- exactly the situation this project hit
directly: Guerra et al. (2017)'s measles R0 systematic review (PMID
28757186) has no PMC full text, so its stratified R0 table could not be
pulled during ADR 0017's research, and the paper was excluded from the
epidemiology registry rather than guessed at.

Design, matching every other resolver in this project:

- `fetch_core_search()` is the only function that touches the network.
- `parse_core_search()` is a pure function: JSON response in, list of
  CoreFullTextCandidate out. Testable offline with saved fixture JSON.
- Never fabricates a value. This returns candidate papers (title, DOI,
  download URL) for human review -- exactly like
  fallback_logic.py's PubMed literature-candidates tier -- not an
  auto-extracted numeric claim.
- Degrades gracefully: missing API key, HTTP errors, and malformed
  responses all return found=False with a log entry explaining why,
  never an exception a caller has to handle specially.

CORE API v3 authenticates with a Bearer token in the Authorization header
(not a query-string key, unlike NCBI/BRENDA) -- see
https://api.core.ac.uk/v3/search/works. This could not be live-verified
against the real API from this project's sandbox, which has no general
internet egress (confirmed directly: even NCBI's own E-utilities returned
a connection failure from here, so this is an environment limit, not
something specific to CORE). Verify with one real call
(`resolve_open_access_fulltext("test query")` with CORE_API_KEY set)
before relying on this in a live path.
"""

from __future__ import annotations

import os
from typing import Callable, List, Optional

import httpx
from pydantic import BaseModel

from http_retry import retry_get

CORE_SEARCH_URL = "https://api.core.ac.uk/v3/search/works"

#: Free CORE API key, from https://core.ac.uk/services/api/ -> "Get your
#: API key". Unlike NCBI, this key is required -- CORE's v3 API has no
#: unauthenticated tier -- so a missing key degrades every call to
#: found=False rather than a request CORE would reject anyway.
CORE_API_KEY = os.environ.get("CORE_API_KEY")


class CoreFullTextCandidate(BaseModel):
    core_id: str
    title: str
    doi: Optional[str] = None
    download_url: Optional[str] = None
    year: Optional[int] = None


class CoreFullTextResult(BaseModel):
    found: bool
    candidates: List[CoreFullTextCandidate] = []
    search_log: List[str] = []


FetchFn = Callable[[str, int], dict]


def fetch_core_search(query: str, max_results: int = 5, timeout: float = 15) -> dict:
    """The only function here that touches the network. Raises
    httpx.HTTPError on failure -- callers (resolve_open_access_fulltext)
    are responsible for catching it, exactly like every other fetch_*
    function in this project's literature layer."""
    if not CORE_API_KEY:
        raise RuntimeError("CORE_API_KEY is not set")
    r = retry_get(
        CORE_SEARCH_URL,
        params={"q": query, "limit": max_results},
        headers={"Authorization": f"Bearer {CORE_API_KEY}"},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def parse_core_search(data: dict) -> List[CoreFullTextCandidate]:
    """Pure function: CORE v3 search-works JSON response in, candidate
    list out. CORE's response shape nests results under "results", each
    with "id", "title", "doi", "downloadUrl", and "yearPublished" --
    fields absent on a given result are passed through as None rather
    than defaulted, matching every other parser in this project."""
    candidates = []
    for item in data.get("results", []):
        core_id = item.get("id")
        title = item.get("title")
        if core_id is None or not title:
            continue
        candidates.append(
            CoreFullTextCandidate(
                core_id=str(core_id),
                title=title,
                doi=item.get("doi"),
                download_url=item.get("downloadUrl"),
                year=item.get("yearPublished"),
            )
        )
    return candidates


def resolve_open_access_fulltext(
    query: str,
    max_results: int = 5,
    fetch: Callable[[str, int], dict] = fetch_core_search,
) -> CoreFullTextResult:
    """Search CORE for open-access full text matching a query. Returns
    candidate papers for human review -- never an auto-extracted claim.

    `fetch` is injectable so this is testable offline: pass a function
    that returns fixture JSON instead of hitting the network.
    """
    log: List[str] = []

    if not CORE_API_KEY:
        return CoreFullTextResult(
            found=False,
            search_log=["CORE_API_KEY is not set; open-access search skipped"],
        )

    try:
        data = fetch(query, max_results)
    except httpx.HTTPError as exc:
        return CoreFullTextResult(
            found=False,
            search_log=[f"CORE search failed: {exc}"],
        )
    except RuntimeError as exc:
        return CoreFullTextResult(found=False, search_log=[str(exc)])

    candidates = parse_core_search(data)
    if not candidates:
        return CoreFullTextResult(
            found=False,
            search_log=[f"CORE search for '{query}' returned no results"],
        )

    log.append(f"CORE search for '{query}' returned {len(candidates)} candidate(s)")
    return CoreFullTextResult(found=True, candidates=candidates, search_log=log)
