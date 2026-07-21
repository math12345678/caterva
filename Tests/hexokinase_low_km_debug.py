"""
Hardening check: hexokinase's (EC 2.7.1.1) reported lowest Km was
2.3e-07 mM for ATP - barely above the plausibility floor
(KM_PLAUSIBLE_MIN_MM = 1e-7). Dumps the raw row(s) with the smallest
Km values in the real KM Values table so we can see the actual BRENDA
text (conditions, reference) and judge whether this is a real
ultra-high-affinity measurement or a unit-parsing artifact. Generic -
works for any EC number, no enzyme-specific assumptions beyond the EC
passed in.
"""

import re
import sys

from brenda_client import _find_table_container, fetch_brenda_html
from bs4 import BeautifulSoup

EC = sys.argv[1] if len(sys.argv) > 1 else "2.7.1.1"

print(f"Fetching EC {EC} ...")
html = fetch_brenda_html(EC)
soup = BeautifulSoup(html, "lxml")

container = _find_table_container(soup, "KM Values")
if container is None:
    print("Could not find KM Values container.")
    sys.exit(1)

rows = container.find_all("div", class_=re.compile(r"row"))
subrows = container.find_all("div", id=re.compile(r"sr\d+$"))
all_rows = rows + subrows

human_numeric_rows = []
for row in all_rows:
    cells = row.find_all("div", class_="cell")
    cell_texts = [c.get_text(strip=True) for c in cells]
    if not cell_texts:
        continue
    full_text = " | ".join(cell_texts)
    if "Homo sapiens" not in full_text:
        continue
    m = re.match(r"^(\d+\.?\d*)$", cell_texts[0].strip())
    if not m:
        continue
    human_numeric_rows.append((float(m.group(1)), cell_texts))

human_numeric_rows.sort(key=lambda pair: pair[0])
print(f"\nTotal human numeric KM Values rows found: {len(human_numeric_rows)}")
print("\n10 smallest Km values (raw cell texts):")
for val, cells in human_numeric_rows[:10]:
    print(f"  {val}  ->  {cells}")
