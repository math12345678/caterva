"""
Captures real LDH (EC 1.1.1.27) KM Values rows from live BRENDA, same
purpose as brenda_hexokinase_realrows_debug.py / brenda_chymotrypsin_debug.py.
brenda_ldh_fixture.html is honestly labeled "Synthetic" (not falsely
claimed real), but its structure doesn't match real BRENDA pages either
(it merges substrate name + assay conditions into one cell; real BRENDA
splits Km | substrate | organism | uniprot | comment | reference into 6
separate cells, confirmed via every other fixture rebuilt this session).
This dumps real human rows across multiple distinct substrates (lactate,
pyruvate, NAD+) plus a real non-human row, so the fixture can be rebuilt
from actual captured cells instead of a synthetic-but-plausible shape.
"""

import re

from brenda_client import _find_table_container, fetch_brenda_html
from bs4 import BeautifulSoup

EC = "1.1.1.27"

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

    human_by_substrate = {}
    non_human_rows = []
    for row in all_rows:
        cells = row.find_all("div", class_="cell")
        cell_texts = [c.get_text(strip=True) for c in cells]
        if not cell_texts:
            continue
        if not re.match(r"^\d+\.?\d*(e-?\d+)?$", cell_texts[0].strip(), re.IGNORECASE):
            continue
        full_text = " | ".join(cell_texts)
        if len(cell_texts) > 1 and "entries" in cell_texts[2].lower() if len(cell_texts) > 2 else False:
            continue  # unexpanded aggregate row
        if "Homo sapiens" in full_text:
            substrate = cell_texts[1] if len(cell_texts) > 1 else "?"
            human_by_substrate.setdefault(substrate, []).append(cell_texts)
        elif len(non_human_rows) < 5:
            non_human_rows.append(cell_texts)

    print(f"\nDistinct human substrate labels: {len(human_by_substrate)}")
    for substrate, rows_for_sub in list(human_by_substrate.items())[:20]:
        print(f"\n  substrate={substrate!r} ({len(rows_for_sub)} rows)")
        for r in rows_for_sub[:3]:
            print("   ", r)

    print(f"\nFirst {len(non_human_rows)} non-human rows:")
    for row in non_human_rows:
        print(" ", row)
