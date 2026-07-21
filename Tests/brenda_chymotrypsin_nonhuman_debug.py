"""
Follow-up to brenda_chymotrypsin_debug.py: captures a real NON-human row
from the same live KM Values table, so the rebuilt fixture's
organism-exclusion test case uses a genuine captured row instead of an
invented one.
"""

import re

from brenda_client import _find_table_container, fetch_brenda_html
from bs4 import BeautifulSoup

EC = "3.4.21.1"

print(f"Fetching EC {EC} ...")
html = fetch_brenda_html(EC)
soup = BeautifulSoup(html, "lxml")

container = _find_table_container(soup, "KM Values")
rows = container.find_all("div", class_=re.compile(r"row"))
subrows = container.find_all("div", id=re.compile(r"sr\d+$"))
all_rows = rows + subrows

non_human_rows = []
for row in all_rows:
    cells = row.find_all("div", class_="cell")
    cell_texts = [c.get_text(strip=True) for c in cells]
    if not cell_texts:
        continue
    full_text = " | ".join(cell_texts)
    if "Homo sapiens" not in full_text and re.match(r"^\d+\.?\d*$", cell_texts[0].strip()):
        non_human_rows.append(cell_texts)

print(f"Non-human numeric rows found: {len(non_human_rows)}")
for row in non_human_rows[:10]:
    print(" ", row)
