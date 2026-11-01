"""
One-off diagnostic for the LDH (EC 1.1.1.27) zero-result regression.

run_all_enzymes.py went from 7 solid entries (before table-scoping) to 0
entries (after), even with the unfiltered fallback tier
(require_substrate_match=False) that should return ANY human numeric-Km
row regardless of substrate name. Zero results even from that fallback
means one of:
  1. _find_table_container isn't finding the "KM Values" nav link/container
     on LDH's page anymore (prints "container: None").
  2. It finds a container, but it has zero rows containing "Homo sapiens"
     text at all - possible if BRENDA's markup for this specific page
     differs, or if the fetch itself got back something unexpected
     (rate-limit page, CAPTCHA, redirect) instead of the real enzyme page.
  3. The fetch succeeded and looks like a real enzyme page, but the KM
     Values container legitimately doesn't have data for "Homo sapiens"
     right now.

This script prints exactly which of those is happening, with raw output,
no guessing.
"""

import re

from brenda_client import (
    BRENDA_ENZYME_URL,
    _SHOW_TABLE_HREF_PATTERN,
    _find_table_container,
    fetch_brenda_html,
)
from bs4 import BeautifulSoup

EC = "1.1.1.27"

print(f"Fetching {BRENDA_ENZYME_URL}?ecno={EC} ...")
html = fetch_brenda_html(EC)
print(f"Response length: {len(html)} characters")

soup = BeautifulSoup(html, "lxml")

# 1. Does the page even look like a real enzyme page?
title = soup.find("title")
print(f"Page <title>: {title.get_text(strip=True) if title else 'NOT FOUND'}")

# 2. List every showTable nav link found, so we can see if "KM Values"
#    is even present under that exact label on this page.
print("\nAll showTable nav links found on this page:")
nav_links = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    if isinstance(href, list):
        href = href[0] if href else ""
    m = _SHOW_TABLE_HREF_PATTERN.search(str(href))
    if m:
        label = a.get_text(strip=True)
        nav_links.append((label, m.group(1)))
        print(f"  {label!r} -> {m.group(1)}")
if not nav_links:
    print("  (none found at all - page structure may differ from expected)")

# 3. Try to find the KM Values container specifically.
container = _find_table_container(soup, "KM Values")
print(f"\n_find_table_container(soup, 'KM Values') -> {'FOUND' if container is not None else 'None'}")

if container is not None:
    rows = container.find_all("div", class_=re.compile(r"row"))
    print(f"Rows inside KM Values container: {len(rows)}")
    human_rows = [r for r in rows if "Homo sapiens" in r.get_text()]
    print(f"Rows inside KM Values container mentioning 'Homo sapiens': {len(human_rows)}")

    print("\nFirst 5 raw rows in the KM Values container (any organism):")
    for row in rows[:5]:
        cells = row.find_all("div", class_="cell")
        cell_texts = [c.get_text(strip=True) for c in cells]
        print(f"  {cell_texts}")
else:
    print("Falling back to whole-page row scan for diagnostics:")
    rows = soup.find_all("div", class_=re.compile(r"row"))
    print(f"Total div.row elements on whole page: {len(rows)}")
    human_rows = [r for r in rows if "Homo sapiens" in r.get_text()]
    print(f"Whole-page rows mentioning 'Homo sapiens': {len(human_rows)}")
    print("\nFirst 5 raw rows on the whole page:")
    for row in rows[:5]:
        cells = row.find_all("div", class_="cell")
        cell_texts = [c.get_text(strip=True) for c in cells]
        print(f"  {cell_texts}")
