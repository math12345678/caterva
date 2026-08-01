import httpx
from bs4 import BeautifulSoup
import re
from typing import List

import enzyme_lookup

r = httpx.get(
    "https://www.brenda-enzymes.org/enzyme.php",
    params={"ecno": "1.1.1.27"},
    timeout=15
)

soup = BeautifulSoup(r.text, "lxml")
rows = soup.find_all("div", class_=re.compile(r"row"))

# Resolved dynamically via KEGG for EC 1.1.1.27 - no hardcoded
# per-enzyme substrate list. Falls back to an empty list (matching
# nothing, rather than a guessed name) if KEGG has nothing for this EC.
try:
    _kegg_text = enzyme_lookup.fetch_kegg_enzyme_text("1.1.1.27")
    real_substrates = enzyme_lookup.parse_kegg_substrates(_kegg_text)
except Exception:
    real_substrates = []

substrate_km_rows: List[List[str]] = []
for row_tag in rows:
    cells = row_tag.find_all("div", class_="cell")
    if len(cells) < 3:
        continue
    cell_texts = [c.get_text(strip=True) for c in cells]
    full_text = " | ".join(cell_texts)
    
    has_real_substrate = any(s.lower() in full_text.lower() for s in real_substrates)
    has_human = "Homo sapiens" in full_text
    has_numeric = bool(re.search(r'\b\d+\.?\d*\b', cell_texts[0]))
    
    if has_real_substrate and has_human and has_numeric:
        substrate_km_rows.append(cell_texts)

print(f"Human LDH rows with real substrates: {len(substrate_km_rows)}")
print()
for row_cells in substrate_km_rows[:20]:
    print("  " + " | ".join(str(c)[:60] for c in row_cells[:5]))
