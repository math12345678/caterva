import httpx
from bs4 import BeautifulSoup
import re

r = httpx.get(
    "https://www.brenda-enzymes.org/enzyme.php",
    params={"ecno": "3.1.1.7"},
    timeout=15
)
soup = BeautifulSoup(r.text, "lxml")
rows = soup.find_all("div", class_=re.compile(r"row"))

# Just show ALL human rows with a numeric first cell, no substrate filter
print("All human AChE rows with numeric first cell:")
for row in rows:
    cells = row.find_all("div", class_="cell")
    if len(cells) < 3:
        continue
    cell_texts = [c.get_text(strip=True) for c in cells]
    full_text = " | ".join(cell_texts)
    if "Homo sapiens" not in full_text:
        continue
    if not re.match(r'^(\d+\.?\d*)$', cell_texts[0].strip()):
        continue
    print(" ", " | ".join(c[:60] for c in cell_texts[:5]))