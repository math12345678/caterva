"""
Follow-up diagnostic: brenda_aggregate_row_debug.py showed that aggregate
"N entries" rows use href="javascript:showRows('tab12r0',0);" to expand.
This script is generic (no enzyme-specific assumptions) - it:

1. Searches every <script> tag on the page for a "function showRows"
   definition, to see whether expansion is client-side (rows already in
   the static HTML, just hidden) or an AJAX call to some endpoint.
2. Searches the whole page for any element whose id contains the row id
   (e.g. "tab12r0") beyond the summary row itself, in case the individual
   entries are already embedded in the static HTML as hidden children.
"""

import re
import sys

from brenda_client import fetch_brenda_html
from bs4 import BeautifulSoup

EC = sys.argv[1] if len(sys.argv) > 1 else "1.1.1.27"
ROW_ID = sys.argv[2] if len(sys.argv) > 2 else "tab12r0"

print(f"Fetching EC {EC} ...")
html = fetch_brenda_html(EC)
soup = BeautifulSoup(html, "lxml")

print("\n=== Searching <script> tags for 'showRows' function definition ===")
found_def = False
for script in soup.find_all("script"):
    text = script.string or ""
    if "showRows" in text:
        found_def = True
        # print a window of text around each occurrence
        for m in re.finditer(r"showRows", text):
            start = max(0, m.start() - 200)
            end = min(len(text), m.start() + 800)
            print(f"\n--- occurrence at offset {m.start()} ---")
            print(text[start:end])
if not found_def:
    print("No <script> tag containing 'showRows' found (may be in an external .js file).")

print(f"\n=== Searching whole page for elements with id containing {ROW_ID!r} ===")
matches = soup.find_all(id=re.compile(re.escape(ROW_ID)))
print(f"Found {len(matches)} elements with id containing {ROW_ID!r}:")
for el in matches:
    print(f"  <{el.name} id={el.get('id')!r} class={el.get('class')}>")

print("\n=== Searching for external script src attributes (in case showRows lives there) ===")
for script in soup.find_all("script", src=True):
    print(f"  {script['src']}")
