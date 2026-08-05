"""
http_retry.py

Lightweight exponential-backoff retry wrapper for the httpx calls the
literature layer makes against public APIs (NCBI PubMed/Taxonomy, UniProt,
KEGG, BRENDA). These services throttle at different rates:

  - NCBI E-utilities:  3 req/s without an API key, 10 req/s with one.
    A 429 (Retry-After) is routine during a batch test run.
  - UniProt REST:      generous but not unlimited; bursts from parallel
    tests occasionally trigger 429s.
  - KEGG REST:         no published rate limit, but intermittent 502/503
    from their load balancer, especially from CI runners.
  - BRENDA:            no documented rate limit; 503 during maintenance
    windows, 429 very rarely.

Every caller that needs retries can import ``retry_get`` and use it as a
drop-in replacement for ``httpx.get``. The rest of the httpx API (params,
timeout, headers, follow_redirects, etc.) is passed through unchanged.

Usage:
    from http_retry import retry_get

    r = retry_get("https://eutils.ncbi.nlm.nih.gov/...", params={...}, timeout=15)
    r.raise_for_status()

Do NOT wrap calls in tests that supply a fixture-HTML provider --
``retry_get`` is meant for live network calls only, and the defaults
(3 retries, 1-4s backoff) assume a ~10-15s total window, which is fine
for a live API call but wasteful inside a unit test.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

# Tuned for public free-tier APIs without API keys.
#  - max_retries=3 means at most 4 total attempts (original + 3 retries).
#  - base_delay=1.0 gives a 1s/2s/4s backoff sequence (<8s total wait).
# Together they fit inside BRENDA's 15s default timeout with room to spare.
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0

RETRYABLE_STATUSES = frozenset({429, 502, 503})


def retry_get(
    url: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    **kwargs: Any,
) -> httpx.Response:
    """httpx.get with exponential backoff for transient server errors.

    Retries on 429 (Too Many Requests), 502 (Bad Gateway), and 503
    (Service Unavailable). Other status codes (including 4xx client errors
    that aren't 429) are returned immediately -- retrying a 404 or 400
    wastes everyone's time.

    Each retry waits ``base_delay * 2**attempt`` seconds, so the default
    sequence is 1s / 2s / 4s.

    Raises the last ``httpx.HTTPStatusError`` if all retries are exhausted.
    Other exceptions (timeout, connection error) are NOT retried --
    they indicate a different class of problem.
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            r = httpx.get(url, **kwargs)
            if r.status_code not in RETRYABLE_STATUSES:
                return r
            # 429/502/503: retryable server-side blip.
            last_exc = httpx.HTTPStatusError(
                f"Server error {r.status_code} for {url}",
                request=r.request,
                response=r,
            )
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                time.sleep(delay)
                continue
            # Exhausted retries — let the last error propagate naturally.
            r.raise_for_status()
        except httpx.ConnectError as exc:
            # Connection refused / DNS failure — transient, worth retrying.
            # httpx does NOT raise on 4xx/5xx by default (we handle those
            # above), so HTTPStatusError is never caught here.
            last_exc = exc
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                time.sleep(delay)
                continue
            raise

    # Should be unreachable (the loop always raises or returns), but
    # satisfy the type checker.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"retry_get exhausted all {max_retries + 1} attempts for {url}")
