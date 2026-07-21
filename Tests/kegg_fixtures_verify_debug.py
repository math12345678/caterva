"""
Verifies kegg_hexokinase_fixture.txt and kegg_ldh_fixture.txt against a
fresh live fetch from KEGG - these two fixtures were reviewed by eye last
round (pattern-matched as "looks like real KEGG format") but never
actually re-fetched and diffed. This closes that gap.
"""

import difflib
import os

from enzyme_lookup import fetch_kegg_enzyme_text

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

TARGETS = {
    "2.7.1.1": "kegg_hexokinase_fixture.txt",
    "1.1.1.27": "kegg_ldh_fixture.txt",
}

for ec, fname in TARGETS.items():
    print(f"\n=== EC {ec} -> {fname} ===")
    live_text = fetch_kegg_enzyme_text(ec)
    fixture_path = os.path.join(FIXTURES_DIR, fname)
    with open(fixture_path, encoding="utf-8") as f:
        fixture_text = f.read()

    if live_text.strip() == fixture_text.strip():
        print("EXACT MATCH")
    else:
        print("DIFFERS - unified diff (fixture vs live):")
        diff = difflib.unified_diff(
            fixture_text.splitlines(keepends=True),
            live_text.splitlines(keepends=True),
            fromfile="fixture",
            tofile="live",
        )
        print("".join(diff))
