#!/usr/bin/env python3
"""Live, key-authenticated cross-checks on cited identifiers.

    python scripts/verify_values_live.py            # keys from env or Science-Agent-Pipeline/.env
    python scripts/verify_values_live.py --json

Keys used: NCBI_API_KEY (PubMed E-utilities), CORE_API_KEY (CORE v3). No LLM
key is used: a language model is not a source for a citation. Key values are
never printed; every error message passes through scrub() first.

WHY THIS EXISTS
---------------
`verify_citations_live.py` asked only whether an identifier RESOLVES, and
that was shown to be too weak: it pinned "740253" as a PMID, and PubMed
resolves it -- to a 1978 paper on jugular-vein cannulation. 740253 is a
BRENDA reference id (golden tuple G1), a different namespace. An existence
check passed a number in the wrong namespace. (verify_citations_live.py now
checks titles too; this script adds the cross-namespace and second-index
checks it does not.)

So this script checks that the identifier is the right KIND of thing and the
paper is ABOUT what we cite it for:

  * PMIDs  -> NCBI esummary title must mention the claimed topic (the same
    PMIDS table verify_citations_live.py uses, imported, not copied).
  * Golden BRENDA reference ids -> reported as "BRENDA-namespace, not
    PubMed-checkable", plus whether they collide with an unrelated PMID.
  * DOIs   -> CORE is a second, independent index. A DOI counts as indexed
    only when a returned work carries exactly that DOI -- a nonzero hit
    count for a fielded query is not the same thing. Absent from CORE is
    INFORMATION (coverage is incomplete), never a failure.

RATE LIMITS
-----------
CORE's free tier allows 10 requests per window and says so in its headers
(X-RateLimit-Remaining, X-RateLimit-Retry-After as a timestamp). The first
version slept 6 s before every request and honoured one 429 for at most
30 s, so a run that met the limit reported every remaining DOI unreachable
and exited 1. Now:

  * DOIs are asked in batches (one OR query per CORE_BATCH DOIs), so a run
    needs a handful of requests rather than one per DOI;
  * when X-RateLimit-Remaining reaches 0, the next request waits for the
    advertised reset instead of spending a 429 to learn it;
  * a 429 is retried after Retry-After / X-RateLimit-Retry-After when the
    server gives one, else after exponential backoff;
  * all waiting together is bounded by CORE_WAIT_BUDGET_S. A batch still
    refused when it is spent is UNREACHABLE, honestly, not retried forever.

THREE OUTCOMES: matched / mismatched / unreachable. Exit 0 / 2 / 1.
"""
from __future__ import annotations

import argparse
import datetime
import email.utils
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "Tests"))

from golden_set import GOLDEN  # noqa: E402
from verify_citations_live import (  # noqa: E402
    PMIDS as PMID_TOPICS,
    discovered_dois,
    load_env_keys,
    scrub,
)

CORE_URL = "https://api.core.ac.uk/v3/search/works"
#: DOIs per CORE query. Small enough that the OR query stays well inside
#: CORE's query-length limits and a result page cannot plausibly fill.
CORE_BATCH = 5
#: Works per CORE result page. A page that comes back full means absence
#: from it is not established, and those DOIs are reported unreachable.
CORE_PAGE = 100
#: Total seconds this run may spend waiting on CORE's rate limit.
CORE_WAIT_BUDGET_S = 180.0
#: Attempts per batch before it is given up as unreachable.
CORE_MAX_ATTEMPTS = 5
#: First backoff when a 429 carries no usable reset time; doubles each try.
CORE_BACKOFF_BASE_S = 5.0


def pubmed_summaries(ids: list[str], key: str) -> dict[str, dict]:
    r = httpx.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        params={"db": "pubmed", "retmode": "json", "id": ",".join(ids), "api_key": key},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["result"]


def _seconds_until(value: str | None, now: float) -> float | None:
    """A reset hint as seconds from now: delta-seconds, HTTP-date or ISO."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    when = None
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            # CORE writes "+0000"; fromisoformat accepts that from 3.11 on.
            when = datetime.datetime.fromisoformat(value)
        except ValueError:
            return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return max(0.0, when.timestamp() - now)


def rate_limit_wait(headers: httpx.Headers, attempt: int) -> float:
    """How long to wait before retrying a 429 (attempt counts from 1)."""
    now = time.time()
    for name in ("Retry-After", "X-RateLimit-Retry-After"):
        wait = _seconds_until(headers.get(name), now)
        if wait is not None:
            # One second of slack: the reset is a timestamp at 1 s resolution.
            return wait + 1.0
    return CORE_BACKOFF_BASE_S * 2 ** (attempt - 1)


class CoreClient:
    """CORE v3 search with paced, bounded handling of its rate limit."""

    def __init__(self, key: str, *, sleep=time.sleep, get=httpx.get):
        """`sleep` and `get` are injectable so the waiting can be tested offline."""
        self._key = key
        self._sleep = sleep
        self._get = get
        self.waited = 0.0
        self._next_ok_at = 0.0

    def _wait(self, seconds: float) -> bool:
        """Wait if the budget allows; False means it does not."""
        if seconds <= 0:
            return True
        if self.waited + seconds > CORE_WAIT_BUDGET_S:
            return False
        self._sleep(seconds)
        self.waited += seconds
        return True

    def search(self, query: str) -> dict:
        """One search. Raises httpx.HTTPError when it cannot be answered."""
        for attempt in range(1, CORE_MAX_ATTEMPTS + 1):
            if not self._wait(self._next_ok_at - time.time()):
                raise httpx.HTTPError(
                    f"CORE rate-limit wait budget ({CORE_WAIT_BUDGET_S:.0f}s) spent"
                )
            r = self._get(
                CORE_URL,
                params={"q": query, "limit": CORE_PAGE},
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=30,
                follow_redirects=True,
            )
            if r.headers.get("X-RateLimit-Remaining") == "0":
                reset = _seconds_until(r.headers.get("X-RateLimit-Retry-After"), time.time())
                if reset is not None:
                    self._next_ok_at = time.time() + reset + 1.0
            if r.status_code == 429:
                wait = rate_limit_wait(r.headers, attempt)
                if attempt == CORE_MAX_ATTEMPTS or not self._wait(wait):
                    raise httpx.HTTPError(
                        f"CORE HTTP 429 after {attempt} attempt(s), "
                        f"{self.waited:.0f}s waited in total"
                    )
                continue
            r.raise_for_status()
            return r.json()
        raise httpx.HTTPError("CORE: attempts exhausted")  # pragma: no cover


def core_indexed(dois: list[str], client: CoreClient) -> dict[str, bool | None]:
    """DOI -> True (a returned work has exactly this DOI), False, or None.

    None means the batch could not be answered, or its result page came back
    full so absence from it proves nothing.
    """
    out: dict[str, bool | None] = {}
    for i in range(0, len(dois), CORE_BATCH):
        batch = dois[i:i + CORE_BATCH]
        query = " OR ".join(f'doi:"{d}"' for d in batch)
        data = client.search(query)
        results = data.get("results") or []
        seen = {str(w.get("doi") or "").lower() for w in results}
        full = len(results) >= CORE_PAGE
        for d in batch:
            out[d] = True if d.lower() in seen else (None if full else False)
    return out


def run(keys: dict[str, str], *, core_client: CoreClient | None = None) -> dict:
    out: dict = {"matched": [], "mismatched": [], "unreachable": [], "info": []}
    ncbi, core = keys.get("NCBI_API_KEY"), keys.get("CORE_API_KEY")

    golden_refs = {t["expected"]["ref"]: t["id"] for t in GOLDEN}
    ids = sorted(set(PMID_TOPICS) | set(golden_refs))
    if not ncbi:
        out["unreachable"].append("NCBI_API_KEY missing: PubMed checks not performed")
    else:
        try:
            res = pubmed_summaries(ids, ncbi)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            out["unreachable"].append(scrub(f"PubMed: {exc!r}", keys))
            res = None
        for pmid, words in PMID_TOPICS.items():
            if res is None:
                break
            entry = res.get(pmid)
            if not isinstance(entry, dict):
                out["unreachable"].append(f"PMID {pmid}: esummary returned no entry")
                continue
            if "error" in entry:
                out["mismatched"].append(f"PMID {pmid}: not in PubMed ({entry['error']!r})")
                continue
            title = entry.get("title", "")
            ok = any(w in title.lower() for w in words)
            (out["matched"] if ok else out["mismatched"]).append(
                f"PMID {pmid}: {title!r} vs topic {words}"
            )
        for ref, gid in golden_refs.items():
            if res and isinstance(res.get(ref), dict) and "error" not in res[ref]:
                out["info"].append(
                    f"{gid.split(':')[0]} ref {ref} is a BRENDA reference id; as a "
                    f"PMID it is an unrelated paper ({res[ref].get('title', '')[:70]!r}). "
                    "Never cite it as a PMID."
                )

    dois = sorted(discovered_dois())
    if not core:
        out["unreachable"].append("CORE_API_KEY missing: CORE checks not performed")
    else:
        client = core_client or CoreClient(core)
        found: dict[str, bool | None] = {}
        for i in range(0, len(dois), CORE_BATCH):
            batch = dois[i:i + CORE_BATCH]
            try:
                found.update(core_indexed(batch, client))
            except (httpx.HTTPError, ValueError) as exc:
                for d in batch:
                    out["unreachable"].append(scrub(f"CORE {d}: {exc!r}", keys))
        for doi in dois:
            state = found.get(doi, "skip")
            if state is True:
                out["matched"].append(f"DOI {doi}: indexed in CORE")
            elif state is False:
                out["info"].append(f"DOI {doi}: not in CORE (coverage gap, not a failure)")
            elif state is None:
                out["unreachable"].append(
                    f"CORE {doi}: result page full, absence not established"
                )
        if client.waited:
            out["info"].append(f"CORE rate limit: waited {client.waited:.0f}s in total")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = run(load_env_keys())
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        for k in ("matched", "mismatched", "unreachable", "info"):
            print(f"\n{k.upper()} ({len(out[k])})")
            for line in out[k]:
                print("  -", line)
    if out["mismatched"]:
        return 2
    return 1 if out["unreachable"] else 0


if __name__ == "__main__":
    sys.exit(main())
