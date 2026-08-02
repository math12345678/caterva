"""Capture a real BRENDA Turnover Numbers (kcat) table as a fixture.

Run this once, from the Tests/ directory, on a machine with network access:

    cd ~/Desktop/Coding/Terrium/Tests
    ../.venv/bin/python brenda_kcat_capture.py

It prints what it found and, on success, writes
`fixtures/brenda_ache_kcat_fixture.html`.

Why a script and not a one-liner
--------------------------------
`_find_table_container` matches a navigation link by its EXACT text
(case-insensitive). If BRENDA words the tab differently from the string we
guess, a single-label probe reports "NOT FOUND" and looks like the data does
not exist. So this tries several plausible labels and, if all miss, prints
every tab label on the page — which turns a dead end into the answer.

Nothing is written unless a real table container is found. No fixture is ever
fabricated: every fixture in this repository is a live capture, and a
hand-written one would put invented evidence into the golden set.
"""

from __future__ import annotations

import pathlib
import sys

from bs4 import BeautifulSoup

from brenda_client import _find_table_container, fetch_brenda_html

# Acetylcholinesterase. Chosen because its Km fixture is already a verified
# live capture, and it is the enzyme behind the STRENDA-complete golden tuple
# (Km 0.0714 mM, pH 7.4, 37 C, BRENDA ref 713996).
EC = "3.1.1.7"

CANDIDATE_LABELS = [
    "Turnover Numbers",
    "Turnover Number",
    "Turnover number",
    "kcat",
    "Kcat",
    "TN Values",
    "Turnover Number [1/s]",
]

OUT = pathlib.Path("fixtures") / "brenda_ache_kcat_fixture.html"


def main() -> int:
    if not pathlib.Path("fixtures").is_dir():
        print("ERROR: run this from the Tests/ directory (no fixtures/ here).")
        return 2

    print(f"Fetching BRENDA EC {EC} ...")
    try:
        html = fetch_brenda_html(EC)
    except Exception as exc:  # network, timeout, HTTP error
        print(f"ERROR: could not fetch BRENDA: {exc}")
        return 1

    print(f"  fetched {len(html):,} characters")
    soup = BeautifulSoup(html, "html.parser")

    for label in CANDIDATE_LABELS:
        node = _find_table_container(soup, label)
        if node is not None:
            text = str(node)
            rows = text.count('class="row"')
            print(f"\nFOUND  label={label!r}  ({len(text):,} chars, ~{rows} rows)")
            OUT.write_text(text, encoding="utf-8")
            print(f"Wrote {OUT}")
            print("\nPaste the whole output of this script back to Claude.")
            return 0
        print(f"  miss: {label!r}")

    # Every candidate missed. The useful thing now is the real tab list.
    print("\nNOT FOUND with any candidate label.")
    print("Tab labels actually present on this page:")
    seen = set()
    for a in soup.find_all("a", href=True):
        t = a.get_text(strip=True)
        if t and len(t) < 60 and t not in seen:
            seen.add(t)
    for t in sorted(seen):
        print(f"  - {t}")
    print("\nPaste this list back to Claude; the correct label will be in it,")
    print("or it will show that this page genuinely has no turnover data.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
