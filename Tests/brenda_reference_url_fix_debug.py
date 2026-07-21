"""
citation.py's brenda_reference_url() was confirmed broken: every refid
returns an identical generic template page (same byte length, blank
"Reference for EC = " title) regardless of the actual reference ID -
never a real per-reference citation. The blank "EC = " suggests the
endpoint wants an "ecno" parameter alongside "refid". This script tries
several candidate URL shapes against a real, known (ec_number, refid)
pair - LDH (1.1.1.27), refid 740253 - and prints enough of each response
to tell which one (if any) actually returns real citation content
(authors/journal/year), instead of guessing.
"""

import httpx

EC = "1.1.1.27"
REFID = "740253"

CANDIDATES = [
    f"https://www.brenda-enzymes.org/literature.php?refid={REFID}",
    f"https://www.brenda-enzymes.org/literature.php?ecno={EC}&refid={REFID}",
    f"https://www.brenda-enzymes.org/reference.php?refid={REFID}",
    f"https://www.brenda-enzymes.org/reference.php?ecno={EC}&refid={REFID}",
    f"https://www.brenda-enzymes.org/enzyme.php?ecno={EC}#REFERENCE",
]

for url in CANDIDATES:
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        title_start = r.text.find("<title>")
        title_end = r.text.find("</title>")
        title = r.text[title_start:title_end + 8] if title_start != -1 else "(no title)"
        print(f"url={url}")
        print(f"  status={r.status_code}  length={len(r.text)}")
        print(f"  title: {title}")
        print()
    except Exception as exc:  # noqa: BLE001
        print(f"url={url}  ERROR: {exc}\n")
