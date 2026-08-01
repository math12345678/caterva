import httpx
from bs4 import BeautifulSoup
import re
from typing import List

r = httpx.get(
    "https://www.brenda-enzymes.org/enzyme.php",
    params={"ecno": "1.1.1.27"},
    timeout=15
)

soup = BeautifulSoup(r.text, "lxml")

# BRENDA structures Km tables specifically - look for section headers
# that indicate we're in the KM VALUE section, not inhibitor or other sections
km_section = None
for tag in soup.find_all(["h2", "h3", "div"], class_=re.compile(r"header|title|section")):
    if "KM" in tag.get_text() or "Michaelis" in tag.get_text():
        km_section = tag
        print(f"Found KM section header: {tag.get_text(strip=True)[:100]}")

rows = soup.find_all("div", class_=re.compile(r"row"))

real_km_rows: List[List[str]] = []
for row_tag in rows:
    cells = row_tag.find_all("div", class_="cell")
    if len(cells) < 3:
        continue
    
    cell_texts = [c.get_text(strip=True) for c in cells]
    full_text = " | ".join(cell_texts)
    
    # A real Km row should have:
    # - a numeric value that looks like a concentration (e.g. 0.09, 1.02, 0.31)
    # - Homo sapiens
    # - a substrate name (not a drug compound name)
    has_numeric = bool(re.search(r'\b\d+\.?\d*\b', cell_texts[0] if cell_texts else ""))
    has_human = "Homo sapiens" in full_text
    # Filter out long compound names (inhibitors tend to be long chemical names)
    first_cell_short = len(cell_texts[0]) < 40 if cell_texts else False
    
    if has_numeric and has_human and first_cell_short:
        real_km_rows.append(cell_texts)

print(f"\nFiltered real Km rows (human, numeric, short substrate name): {len(real_km_rows)}")
print("\nFirst 15:")
for row_cells in real_km_rows[:15]:
    print(" ", " | ".join(row_cells[:5]))
