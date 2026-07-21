"""
Targeted re-check for the two AChE fixture rows flagged last round as
"not reverified live" (organism-in-compound-position row, and the
mislabeled-Kcat-as-Km row). Searches specifically for these two shapes
instead of the generic capture that missed them.
"""

import re

from brenda_client import GENERIC_ORGANISM_PATTERN, _find_table_container, fetch_brenda_html
from bs4 import BeautifulSoup

EC = "3.1.1.7"

print(f"Fetching EC {EC} ...")
html = fetch_brenda_html(EC)
soup = BeautifulSoup(html, "lxml")

container = _find_table_container(soup, "KM Values")
rows = container.find_all("div", class_=re.compile(r"row"))
subrows = container.find_all("div", id=re.compile(r"sr\d+$"))
all_rows = rows + subrows

organism_in_position_rows = []
kcat_mentioned_rows = []

for row in all_rows:
    cells = row.find_all("div", class_="cell")
    cell_texts = [c.get_text(strip=True) for c in cells]
    if not cell_texts:
        continue
    if not re.match(r"^\d+\.?\d*(e-?\d+)?$", cell_texts[0].strip(), re.IGNORECASE):
        continue

    # Shape check: exactly 5 cells (no separate substrate cell) AND
    # cell[1] is organism-shaped per the same pattern brenda_client.py uses.
    if len(cell_texts) == 5 and GENERIC_ORGANISM_PATTERN.fullmatch(cell_texts[1].strip()):
        organism_in_position_rows.append(cell_texts)

    full_text = " | ".join(cell_texts)
    if "Homo sapiens" in full_text and re.search(r"\bKcat\b", full_text, re.IGNORECASE):
        kcat_mentioned_rows.append(cell_texts)

print(f"\nOrganism-in-compound-position rows (5-cell shape): {len(organism_in_position_rows)}")
for r in organism_in_position_rows[:10]:
    print(" ", r)

print(f"\nHuman rows in KM Values table mentioning 'Kcat': {len(kcat_mentioned_rows)}")
for r in kcat_mentioned_rows[:10]:
    print(" ", r)
