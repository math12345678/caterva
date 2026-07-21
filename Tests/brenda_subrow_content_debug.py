"""
Confirms the cell layout of BRENDA's hidden sub-rows (id pattern
"tab{N}r{row}sr{sub}") that back an aggregate "N entries" summary row.
Generic - takes the row id prefix as an argument, no hardcoded enzyme
assumptions.
"""

import re
import sys

from brenda_client import fetch_brenda_html
from bs4 import BeautifulSoup

EC = sys.argv[1] if len(sys.argv) > 1 else "1.1.1.27"
ROW_PREFIX = sys.argv[2] if len(sys.argv) > 2 else "tab12r0sr"

print(f"Fetching EC {EC} ...")
html = fetch_brenda_html(EC)
soup = BeautifulSoup(html, "lxml")

# Find all sub-row containers (id like "tab12r0sr0", "tab12r0sr1", ... -
# NOT their per-cell children like "tab12r0sr0c0").
subrow_pattern = re.compile(rf"^{re.escape(ROW_PREFIX)}\d+$")
subrows = soup.find_all(id=subrow_pattern)
print(f"Found {len(subrows)} sub-row containers matching {ROW_PREFIX}N")

for row in subrows[:6]:
    cells = row.find_all("div", class_="cell")
    cell_texts = [c.get_text(strip=True) for c in cells]
    print(f"\nid={row.get('id')}  class={row.get('class')}")
    print(f"  cell texts: {cell_texts}")
