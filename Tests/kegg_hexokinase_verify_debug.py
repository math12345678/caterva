"""
Isolated re-run of just the hexokinase half of kegg_fixtures_verify_debug.py
- the earlier combined run's hexokinase result wasn't visible in the
pasted output (the LDH diff was too long and pushed it out of view).
This checks only EC 2.7.1.1 so the result can't get lost in scrollback.
"""

import difflib
import os

from enzyme_lookup import fetch_kegg_enzyme_text

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

EC = "2.7.1.1"
FNAME = "kegg_hexokinase_fixture.txt"

live_text = fetch_kegg_enzyme_text(EC)
fixture_path = os.path.join(FIXTURES_DIR, FNAME)
with open(fixture_path, encoding="utf-8") as f:
    fixture_text = f.read()

# Strip the disclosure comment block (lines starting with "//") before
# comparing, since that's annotation added by this session, not KEGG content.
fixture_kegg_only = "\n".join(
    line for line in fixture_text.splitlines() if not line.startswith("//")
).strip()

print(f"=== EC {EC} ===")
print("\n--- LIVE (first 25 lines) ---")
print("\n".join(live_text.splitlines()[:25]))

print("\n--- Diff (fixture's real KEGG content vs live) ---")
diff = list(difflib.unified_diff(
    fixture_kegg_only.splitlines(keepends=True),
    live_text.splitlines(keepends=True),
    fromfile="fixture",
    tofile="live",
))
if not diff:
    print("EXACT MATCH")
else:
    print("".join(diff[:80]))  # cap output length
    if len(diff) > 80:
        print(f"... ({len(diff) - 80} more diff lines, truncated)")

print("\n--- SUBSTRATE field specifically (this is what parse_kegg_substrates reads) ---")
for line in live_text.splitlines():
    if line.startswith("SUBSTRATE") or (line.startswith((" ", "\t")) and "SUBSTRATE" not in line):
        pass
in_sub = False
for line in live_text.splitlines():
    if line.startswith("SUBSTRATE"):
        in_sub = True
        print(line)
        continue
    if in_sub:
        if line.startswith((" ", "\t")):
            print(line)
            continue
        else:
            break
