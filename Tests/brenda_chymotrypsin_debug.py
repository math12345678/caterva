"""
Captures real chymotrypsin (EC 3.4.21.1) KM Values rows from live BRENDA,
same purpose as brenda_trypsin_debug.py earlier this session: the
existing chymotrypsin fixture uses "ATEE"/"BTEE" textbook acronyms, which
is exactly the kind of fabricated-looking substrate name already proven
wrong for trypsin (BAPNA/TAME never appeared in real BRENDA text - it
uses full chemical names). This dumps real human rows so the fixture can
be rebuilt from verbatim captured data instead of guessed/textbook names.
"""

import re

from brenda_client import _find_table_container, fetch_brenda_html

from bs4 import BeautifulSoup

EC = "3.4.21.1"

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
    for row in all_rows:
        cells = row.find_all("div", class_="cell")
        cell_texts = [c.get_text(strip=True) for c in cells]
        if not cell_texts:
            continue
        full_text = " | ".join(cell_texts)
        if "Homo sapiens" in full_text:
            human_rows.append(cell_texts)

    print(f"\nHuman rows found: {len(human_rows)}")
    for row in human_rows[:30]:
        print(" ", row)
