"""
One-off diagnostic: figure out HOW BRENDA's "N entries" aggregate rows
(e.g. LDH's "0.0018 - 1100 | (S)-lactate | 50 entries") actually expose
their underlying individual values, if at all, from the raw page HTML.

Generic by design - this just dumps the raw markup around any cell whose
text matches "N entries" inside the real KM Values table, for a given EC
number, so we can see whatever link/onclick/data-* mechanism BRENDA uses
without guessing or hardcoding a specific enzyme's structure.
"""

import re
import sys

from brenda_client import _find_table_container, fetch_brenda_html
from bs4 import BeautifulSoup

EC = sys.argv[1] if len(sys.argv) > 1 else "1.1.1.27"

print(f"Fetching EC {EC} ...")
html = fetch_brenda_html(EC)
soup = BeautifulSoup(html, "lxml")

container = _find_table_container(soup, "KM Values")
if container is None:
    print("Could not find KM Values container - aborting.")
    sys.exit(1)

rows = container.find_all("div", class_=re.compile(r"row"))
print(f"Total rows in KM Values container: {len(rows)}")

entries_pattern = re.compile(r"\d+\s*entries", re.IGNORECASE)

found_any = False
for i, row in enumerate(rows):
    cells = row.find_all("div", class_="cell")
    cell_texts = [c.get_text(strip=True) for c in cells]
    full_text = " | ".join(cell_texts)
    if not entries_pattern.search(full_text):
        continue
    found_any = True
    print(f"\n--- Row {i} matches an aggregate 'N entries' cell ---")
    print(f"Cell texts: {cell_texts}")
    print("Raw HTML of this row (first 3000 chars):")
    print(str(row)[:3000])

    # Look for any link/button/data attribute anywhere in this row that
    # might reveal an expand mechanism (href, onclick, data-*, etc.)
    print("\nAll <a> tags in this row:")
    for a in row.find_all("a"):
        print(f"  href={a.get('href')!r}  onclick={a.get('onclick')!r}  text={a.get_text(strip=True)!r}")
    print("Elements with any data-* attribute in this row:")
    for tag in row.find_all(True):
        data_attrs = {k: v for k, v in tag.attrs.items() if k.startswith("data-")}
        if data_attrs:
            print(f"  <{tag.name}> {data_attrs}")

if not found_any:
    print("\nNo 'N entries' aggregate cells found in the KM Values container for this EC.")
