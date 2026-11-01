"""
Captures real hexokinase (EC 2.7.1.1) KM Values rows from live BRENDA,
same purpose as brenda_chymotrypsin_debug.py - the existing hexokinase
fixture is explicitly labeled "synthetic... representative of published
kinetics" rather than verbatim captured data. This dumps real human rows
(a manageable sample, not all 106+ seen earlier) so the fixture can be
rebuilt from actual captured cells instead of approximated ones.
"""

import re
from typing import List

from brenda_client import _find_table_container, fetch_brenda_html
from bs4 import BeautifulSoup

EC = "2.7.1.1"

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

    human_rows: List[List[str]] = []
    non_human_rows: List[List[str]] = []
    for row in all_rows:
        cells = row.find_all("div", class_="cell")
        cell_texts = [c.get_text(strip=True) for c in cells]
        if not cell_texts:
            continue
        full_text = " | ".join(cell_texts)
        if not re.match(r"^\d+\.?\d*$", cell_texts[0].strip()):
            continue
        if "Homo sapiens" in full_text:
            human_rows.append(cell_texts)
        elif len(non_human_rows) < 5:
            non_human_rows.append(cell_texts)

    print(f"\nHuman rows found: {len(human_rows)}")
    print("First 15 human rows (want a mix of D-glucose and ATP substrates):")
    for row in human_rows[:15]:
        print(" ", row)

    print(f"\nFirst {len(non_human_rows)} non-human rows (for the exclusion test case):")
    for row in non_human_rows:
        print(" ", row)
