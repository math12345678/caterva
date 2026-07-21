"""
Follow-up to brenda_ldh_realrows_debug.py: that script's first 5
non-human rows (by row order, unfiltered) didn't happen to include
lactate/pyruvate/NAD+ - needed for the cross-species test, which checks
that a non-human row for one of the SAME real substrates as the human
rows is correctly included with target_organism=None. This filters
specifically for non-human rows whose substrate matches LDH_SUBSTRATES,
so the fixture doesn't need any invented/relabeled organism.
"""

import re

from brenda_client import _find_table_container, fetch_brenda_html
from bs4 import BeautifulSoup

EC = "1.1.1.27"
TARGET_SUBSTRATES = ["lactate", "pyruvate", "NAD+", "NADH"]

print(f"Fetching EC {EC} ...")
html = fetch_brenda_html(EC)
soup = BeautifulSoup(html, "lxml")

container = _find_table_container(soup, "KM Values")
rows = container.find_all("div", class_=re.compile(r"row"))
subrows = container.find_all("div", id=re.compile(r"sr\d+$"))
all_rows = rows + subrows

matches = []
for row in all_rows:
    cells = row.find_all("div", class_="cell")
    cell_texts = [c.get_text(strip=True) for c in cells]
    if not cell_texts or len(cell_texts) < 3:
        continue
    if not re.match(r"^\d+\.?\d*(e-?\d+)?$", cell_texts[0].strip(), re.IGNORECASE):
        continue
    if "Homo sapiens" in cell_texts[2]:
        continue
    substrate_cell = cell_texts[1] if len(cell_texts) > 1 else ""
    if any(sub.lower() in substrate_cell.lower() for sub in TARGET_SUBSTRATES):
        matches.append(cell_texts)

print(f"Non-human rows matching {TARGET_SUBSTRATES}: {len(matches)}")
for m in matches[:10]:
    print(" ", m)
