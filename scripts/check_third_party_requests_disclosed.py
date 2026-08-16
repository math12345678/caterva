#!/usr/bin/env python3
"""Every third-party host a public page contacts is named in PRIVACY.md.

WHY THIS EXISTS
---------------
A visitor's IP address is personal data under GDPR Article 4 -- settled by the
CJEU in *Breyer* (C-582/14, 2016). A page that loads a font or a script from
someone else's server hands that address over before the visitor has clicked
anything.

On 20 January 2022 the Landgericht Muenchen I (Az. 3 O 17493/20) held that
embedding Google Fonts from Google's CDN without consent breaches GDPR Article
6, awarded the visitor EUR 100, and attached penalties of up to EUR 250,000 for
continuing. Terrium is aimed at students, including students in the EU.

Until 2026-08-16, docs/PRIVACY.md said "no third-party requests **from the page
itself**", and then -- in the correction that replaced it -- "the page does not
call anyone; the *server* does". Both were false. Three public pages were
loading fonts from Google and scripts from Cloudflare and jsDelivr the whole
time. The document describing third-party disclosure got the client half wrong
twice in a row, the second time while correcting the first.

That is what this guard is for. Not to forbid CDNs -- that is a judgement call
about self-hosting -- but to make it impossible for a page to contact a host
that the privacy document does not mention. The failure mode here was never a
missing capability; it was a document drifting out of step with the HTML while
sounding confident.

WHAT IT CHECKS
--------------
For every public-facing page, collect the external hosts it references. Every
such host must appear somewhere in docs/PRIVACY.md.

Hosts that appear only in comments, in prose, or as documentation links are
still reported if they sit inside a src/href attribute, because the browser
does not read comments -- it fetches what the attribute says.

WHAT IT DOES NOT CHECK
----------------------
- That the disclosure is *accurate*, only that the host is named. A sentence
  claiming a host is contacted "only on Tuesdays" would pass. Prose accuracy
  is not mechanically checkable; the point is that a new CDN cannot be added
  silently.
- Requests a page makes at runtime via fetch()/XHR to hosts computed at
  runtime. Those are not visible in a static scan. This checks what the markup
  declares.
- Whether self-hosting has happened. That is the fix, and it is a separate,
  deliberate change.

Run with --selftest to prove the matcher can fail.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIVACY_DOC = REPO_ROOT / "docs" / "PRIVACY.md"

# Public-facing surfaces: anything a visitor's browser renders.
PAGE_GLOBS = (
    "mule/*.html",
    "terrium-site/*.html",
    "landing/**/*.html",
    "src/web/*.html",
    "src/web/server.ts",
)

# Hosts that are never fetched by a browser: spec/doc references, our own
# domains, and localhost. Matching these would make the guard noisy without
# making anyone safer.
IGNORED_HOST_RE = re.compile(
    r"""^(
        localhost | 127\.0\.0\.1 | 0\.0\.0\.0 | \[?::1\]? |
        (www\.)?w3\.org | schema\.org | (www\.)?apache\.org |
        html\.spec\.whatwg\.org | developer\.mozilla\.org |
        (www\.)?example\.(com|org) |
        .*\bterrium\b.* | .*\bterium\b.*
    )$""",
    re.X | re.I,
)

# Only attributes the browser actually dereferences.
FETCHING_ATTR_RE = re.compile(
    r"""\b(?:src|href)\s*=\s*["']\s*(https?://[^"'\s>]+)""", re.I
)

# A scan that finds no pages is broken, not clean.
_MIN_PAGES = 3


def _external_hosts(text: str) -> set[str]:
    hosts: set[str] = set()
    for url in FETCHING_ATTR_RE.findall(text):
        match = re.match(r"https?://([^/:?#]+)", url)
        if not match:
            continue
        host = match.group(1).lower()
        if not IGNORED_HOST_RE.match(host):
            hosts.add(host)
    return hosts


def _pages() -> list[Path]:
    found: list[Path] = []
    for pattern in PAGE_GLOBS:
        found.extend(p for p in REPO_ROOT.glob(pattern) if p.is_file())
    return sorted(set(found))


def check(
    pages: list[Path] | None = None, privacy_text: str | None = None
) -> list[str]:
    problems: list[str] = []

    pages = _pages() if pages is None else pages
    if len(pages) < _MIN_PAGES:
        return [
            f"found only {len(pages)} public page(s), expected at least "
            f"{_MIN_PAGES}. The globs no longer match the tree, so this guard "
            f"is not reporting success -- it is reporting that it is blind."
        ]

    if privacy_text is None:
        if not PRIVACY_DOC.is_file():
            return [f"{PRIVACY_DOC.relative_to(REPO_ROOT)} does not exist"]
        privacy_text = PRIVACY_DOC.read_text()

    disclosed = privacy_text.lower()

    for page in pages:
        for host in sorted(_external_hosts(page.read_text(errors="replace"))):
            if host not in disclosed:
                problems.append(
                    f"{page.relative_to(REPO_ROOT)} fetches from {host}, which "
                    f"docs/PRIVACY.md never mentions. Every visitor's IP "
                    f"address reaches that host on page load."
                )
    return problems


def _selftest() -> int:
    failures: list[str] = []

    if check():
        failures.append(f"the real tree should be clean, got: {check()}")

    fake = REPO_ROOT / "mule" / "index.html"
    pages = _pages()

    # A page contacting an undisclosed host must be caught.
    if not check(pages, privacy_text="this document mentions nothing at all"):
        failures.append("an empty privacy document was accepted")

    # The host must be found in a fetching attribute even amid other text.
    hosts = _external_hosts(
        '<link href="https://fonts.googleapis.com/css2?family=X" rel="stylesheet">'
    )
    if "fonts.googleapis.com" not in hosts:
        failures.append("did not extract a host from a real <link href=...>")

    # A bare mention in prose is not a fetch, and must not be reported.
    if _external_hosts("see https://cdn.example.net for details"):
        failures.append("treated prose text as a fetched resource")

    # The floor must fire rather than pass when nothing matches.
    if not any("blind" in p for p in check(pages=[])):
        failures.append("the page floor did not fire on an empty page list")

    # Ignored hosts stay ignored.
    if _external_hosts('<a href="https://www.w3.org/TR/">spec</a>'):
        failures.append("w3.org was not ignored")

    _ = fake
    for f in failures:
        print(f"  selftest FAIL: {f}")
    if failures:
        return 1
    print("OK: selftest passed -- the matcher fails on five defective inputs.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true", help="prove it can fail")
    args = parser.parse_args()

    if args.selftest:
        return _selftest()

    problems = check()
    if problems:
        print("FAIL: a public page contacts a host PRIVACY.md does not disclose")
        for p in problems:
            print(f"  - {p}")
        print(
            "\nA visitor's IP is personal data (GDPR Art. 4; CJEU Breyer "
            "C-582/14). LG Muenchen I, 20 Jan 2022, Az. 3 O 17493/20 awarded "
            "damages for exactly this. Either self-host the resource or "
            "disclose the host in docs/PRIVACY.md."
        )
        return 1

    pages = _pages()
    hosts = sorted({h for p in pages for h in _external_hosts(p.read_text(errors="replace"))})
    print(
        f"OK: {len(pages)} public page(s) checked; "
        f"{len(hosts)} third-party host(s) contacted, all disclosed in PRIVACY.md."
    )
    for h in hosts:
        print(f"    {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
