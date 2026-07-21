"""
Captures real AChE (EC 3.1.1.7) KM Values rows from live BRENDA, same
purpose as the other *_realrows_debug.py scripts this session.
brenda_ache_fixture.html is labeled "Synthetic" but claims several of its
rows reproduce real shapes/values seen in a prior (not-directly-visible)
session - this re-verifies those claims against a fresh live capture
rather than trusting the old claim, consistent with how every other
fixture has been handled this session.
"""

import re

from brenda_client import _find_table_container, fetch_brenda_html
from bs4 import BeautifulSoup

EC = "3.1.1.7"

print(f"Fetching EC {EC} ...")
html = fetch_brenda_html(EC)
soup = BeautifulSoup(html, "lxml")

container = _find_table_container(soup, "KM Values")
if container is None:
    print("Could not find KM Values container.")
else:
    rows = container.find_all("div", class_=re.compile(r"row"))
    subrows = container.find_all("div", id=re.compile(r"sr\d+$"))
    all_rows = rows + subrows
    print(f"Total rows (including sub-rows): {len(all_rows)}")

    human_rows = []
    non_human_rows = []
    organism_in_compound_position_rows = []
    for row in all_rows:
        cells = row.find_all("div", class_="cell")
        cell_texts = [c.get_text(strip=True) for c in cells]
        if not cell_texts:
            continue
        if not re.match(r"^\d+\.?\d*(e-?\d+)?$", cell_texts[0].strip(), re.IGNORECASE):
            continue
        full_text = " | ".join(cell_texts)
        # flag rows where cell[1] itself looks like "Genus species" (organism
        # in the compound-name slot, no separate substrate cell)
        if len(cell_texts) > 1 and re.fullmatch(r"[A-Z][a-z]{2,}(?:\s[a-z]{2,}){1,2}", cell_texts[1].strip()):
            organism_in_compound_position_rows.append(cell_texts)
        elif "Homo sapiens" in full_text:
            human_rows.append(cell_texts)
        elif len(non_human_rows) < 5:
            non_human_rows.append(cell_texts)

    print(f"\nHuman rows found: {len(human_rows)}")
    print("First 15:")
    for row in human_rows[:15]:
        print(" ", row)

    print(f"\nOrganism-in-compound-position rows found: {len(organism_in_compound_position_rows)}")
    for row in organism_in_compound_position_rows[:5]:
        print(" ", row)

    print(f"\nFirst {len(non_human_rows)} non-human rows:")
    for row in non_human_rows:
        print(" ", row)
