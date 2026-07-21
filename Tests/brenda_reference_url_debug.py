"""
Verifies whether citation.py's brenda_reference_url() pattern
(https://www.brenda-enzymes.org/literature.php?refid={id}) actually
resolves to a real citation page, using real reference IDs seen in this
project's live debugging (LDH ref 740541/740001/286460/740253, hexokinase
ref 721735). This URL pattern has been marked "best-effort, unverified"
in citation.py since it was written - never actually checked against a
live response until now.
"""

import httpx

from citation import brenda_reference_url

REAL_REFERENCE_IDS = ["740541", "740001", "286460", "740253", "721735"]

for ref_id in REAL_REFERENCE_IDS:
    url = brenda_reference_url(ref_id)
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        print(f"ref_id={ref_id}  url={url}")
        print(f"  status={r.status_code}  final_url={r.url}  length={len(r.text)}")
        # The <title> alone was identical/blank across all ref_ids in the
        # first pass ("Reference for EC = ") - dig into the <body> to see
        # whether real per-reference content (authors, journal, year) is
        # actually there, or whether this is a broken/generic template
        # that happens to return HTTP 200.
        body_start = r.text.find("<body")
        body_snippet = r.text[body_start:body_start + 1500].replace("\n", " ") if body_start != -1 else "(no <body> found)"
        print(f"  body snippet: {body_snippet}")
        print()
    except Exception as exc:  # noqa: BLE001
        print(f"ref_id={ref_id}  url={url}  ERROR: {exc}\n")
