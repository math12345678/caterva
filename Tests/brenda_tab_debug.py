"""
One-off debug script: find what "tab39" (and any sibling tab ids) are
actually labeled as on a BRENDA enzyme page. If BRENDA splits KM VALUE,
TURNOVER NUMBER, KI VALUE, IC50, etc. into separate tabs, there should be
a navigation element (likely <a> or <li> with an href/data-tab attribute
referencing "tab1", "tab2", ... "tab39") carrying the human-readable label
for each one.

Run with:  python3 brenda_tab_debug.py
"""

import re

import httpx
from bs4 import BeautifulSoup

r = httpx.get(
    "https://www.brenda-enzymes.org/enzyme.php",
    params={"ecno": "3.1.1.7"},
    timeout=15,
)
soup = BeautifulSoup(r.text, "lxml")

print("=== Every element whose id matches 'tab<number>' ===")
tab_containers = soup.find_all(id=re.compile(r"^tab\d+$"))
for t in tab_containers:
    print(f"  id={t.get('id')} class={t.get('class')} tag={t.name}")

print()
print("=== Every element with an href, data-tab, or onclick referencing 'tab' ===")
tab_refs = soup.find_all(
    lambda tag: any(
        "tab" in str(tag.get(attr, "")).lower()
        for attr in ("href", "data-tab", "onclick", "data-target")
    )
)
for el in tab_refs[:80]:
    text = el.get_text(strip=True)
    attrs = {k: v for k, v in el.attrs.items() if k in ("href", "data-tab", "onclick", "data-target", "id", "class")}
    print(f"  <{el.name}> text={text[:50]!r} attrs={attrs}")

print()
print("=== Raw text search: does the full HTML contain the literal strings")
print("    'KM VALUE', 'TURNOVER NUMBER', 'KI VALUE' anywhere at all (even")
print("    inside <script> tags, JS strings, JSON blobs, comments)? ===")
html_text = r.text
for label in ["KM VALUE", "TURNOVER NUMBER", "KI VALUE", "Km Value", "Turnover Number", "Ki Value"]:
    count = html_text.count(label)
    print(f"  '{label}': {count} occurrence(s)")
    if count:
        idx = html_text.find(label)
        print(f"    context: ...{html_text[max(0,idx-100):idx+100]}...")
