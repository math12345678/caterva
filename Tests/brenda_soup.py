import httpx
from bs4 import BeautifulSoup
import re

r = httpx.get(
    "https://www.brenda-enzymes.org/enzyme.php",
    params={"ecno": "1.1.1.27"},
    timeout=15
)

soup = BeautifulSoup(r.text, "lxml")

# Find all rows in BRENDA's data tables
rows = soup.find_all("div", class_=re.compile(r"row"))

human_km_rows = []

for row in rows:
    cells = row.find_all("div", class_="cell")
    if not cells:
        continue
    
    text = " | ".join(c.get_text(strip=True) for c in cells)
    
    # Keep rows that mention Homo sapiens AND contain a number that looks like a Km
    if "Homo sapiens" in text and re.search(r'\d+\.?\d*', text):
        human_km_rows.append(text)

print(f"Human rows with numeric data: {len(human_km_rows)}")
print("\nFirst 10:")
for row in human_km_rows[:10]:
    print(" ", row[:200])