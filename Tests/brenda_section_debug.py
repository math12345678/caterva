"""
One-off debug script: dump BRENDA's page structure around KM VALUE vs
TURNOVER NUMBER vs KI VALUE tables to see if there's a real structural
marker (header element, data attribute, section wrapper) that lets us
tell which kind of value a row belongs to - instead of guessing from the
number's magnitude the way KM_PLAUSIBLE_MIN/MAX_MM currently does.

Run with:  python3 brenda_section_debug.py
"""

import httpx
from bs4 import BeautifulSoup
import re

r = httpx.get(
    "https://www.brenda-enzymes.org/enzyme.php",
    params={"ecno": "3.1.1.7"},
    timeout=15,
)
soup = BeautifulSoup(r.text, "lxml")

print("=== All heading-like elements (h1-h4, and divs/spans with")
print("    'header'/'title'/'section' in their class) ===")
headers = soup.find_all(
    ["h1", "h2", "h3", "h4", "div", "span"],
    class_=re.compile(r"header|title|section|tab", re.IGNORECASE),
)
for h in headers[:60]:
    text = h.get_text(strip=True)
    if text:
        print(f"  <{h.name} class='{h.get('class')}'> {text[:80]}")

print()
print("=== Any element whose text is exactly one of the known BRENDA")
print("    value-type labels (KM VALUE, TURNOVER NUMBER, KI VALUE, IC50) ===")
target_labels = {"KM VALUE", "TURNOVER NUMBER", "KI VALUE", "IC50 VALUE", "IC50"}
for el in soup.find_all(True):
    text = el.get_text(strip=True)
    if text.upper() in target_labels and len(list(el.children)) <= 3:
        print(f"  <{el.name} class='{el.get('class')}' id='{el.get('id')}'> {text}")

print()
print("=== First 3 top-level containers with class containing 'row' -")
print("    check their PARENT chain for any section/table identifier ===")
rows = soup.find_all("div", class_=re.compile(r"row"))
for row in rows[:3]:
    print(f"  row classes: {row.get('class')}")
    parent = row.parent
    depth = 0
    while parent is not None and depth < 6:
        pid = parent.get("id")
        pclass = parent.get("class")
        if pid or pclass:
            print(f"    parent[{depth}] <{parent.name} id={pid} class={pclass}>")
        parent = parent.parent
        depth += 1
    print()
