"""
Hardening check: does BRENDA embed ALL individual measurements for a
large aggregate row (e.g. pyruvate's "130 entries" on the LDH page) in
the static HTML, or only a first page with the rest behind further
pagination/AJAX? If sub-row expansion silently under-counts for large
aggregates, that's a real correctness bug - results would look complete
(table_scoped=True, not flagged) while actually missing most of the data.

Generic - takes EC number and the declared row id + entry count to check
against, no hardcoded enzyme assumptions beyond what's passed in.
"""

import re
import sys

from brenda_client import fetch_brenda_html
from bs4 import BeautifulSoup

EC = sys.argv[1] if len(sys.argv) > 1 else "1.1.1.27"
ROW_ID = sys.argv[2] if len(sys.argv) > 2 else "tab12r17"  # pyruvate, declared "130 entries"

print(f"Fetching EC {EC} ...")
html = fetch_brenda_html(EC)
soup = BeautifulSoup(html, "lxml")

# Find the summary row itself and read its declared count from the
# "N entries" link text, generically (no hardcoded "130").
summary_row = soup.find(id=ROW_ID)
if summary_row is None:
    print(f"Could not find row id={ROW_ID!r} on this page - check the id.")
    sys.exit(1)

link = summary_row.find("a", class_="rowpreview")
declared_text = link.get_text(strip=True) if link else "(no rowpreview link found)"
print(f"Summary row {ROW_ID}: declared as {declared_text!r}")

m = re.search(r"(\d+)\s*entries", declared_text)
declared_count = int(m.group(1)) if m else None
print(f"Declared entry count: {declared_count}")

subrow_pattern = re.compile(rf"^{re.escape(ROW_ID)}sr\d+$")
subrows = soup.find_all(id=subrow_pattern)
print(f"Actual sub-row elements found in static HTML: {len(subrows)}")

if declared_count is not None:
    if len(subrows) == declared_count:
        print("MATCH: all declared entries are present in the static HTML.")
    else:
        print(
            f"MISMATCH: found {len(subrows)} of {declared_count} declared entries - "
            f"large aggregates may be paginated/truncated in the static HTML."
        )

if subrows:
    print("\nLast 3 sub-rows found (to check whether they look complete or cut off):")
    for row in subrows[-3:]:
        cells = row.find_all("div", class_="cell")
        cell_texts = [c.get_text(strip=True) for c in cells]
        print(f"  id={row.get('id')}  {cell_texts}")

# Also check for any "load more" / pagination-looking link near the row
print("\nAny links near this row mentioning 'more' or 'page':")
for a in soup.find_all("a", href=True):
    text = a.get_text(strip=True).lower()
    if "more" in text or "page" in text:
        print(f"  text={a.get_text(strip=True)!r} href={a['href']!r}")
