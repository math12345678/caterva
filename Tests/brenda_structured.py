"""
brenda_structured.py

Superseded by brenda_client.py + enzyme_lookup.py, which is what the
active pipeline (run_all_enzymes.py, fallback_logic.py) actually uses -
this file is kept only as an earlier development snapshot, not deleted
per instruction. It has been fixed in place rather than removed: it
previously carried a hardcoded EC->UniProt fallback dict (EC_UNIPROT_FALLBACK)
covering just 2 enzymes, and a hardcoded default substrate list covering
just LDH/AChE/hexokinase-shaped names - both are exactly the kind of
per-enzyme hardcoding removed from the real pipeline. Both are now
resolved dynamically via enzyme_lookup.py (UniProt REST API, KEGG REST
API), same as brenda_client.py, so nothing in this file returns
fabricated or enzyme-specific baked-in values even though it's not the
file actually used in production.

This file also lacks brenda_client.py's later correctness fixes (table-
scoping, aggregate-row expansion, generic organism matching, etc.) - use
brenda_client.fetch_and_parse_brenda_km for anything real. This file is
retained as-is beyond the hardcoding fix, per instruction not to delete.
"""

from __future__ import annotations


import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel
import re

import enzyme_lookup
from brenda_client import UNIPROT_CELL_PATTERN
from http_retry import retry_get

class BRENDAKmEntry(BaseModel):
    km_value: float
    unit: str = "mM"
    substrate: str
    organism: str
    uniprot: str | None = None
    conditions: str | None = None
    reference_id: str | None = None
    flagged: bool = False
    flag_reason: str | None = None

# Plausible Km range in mM. Values outside this are almost always a
# mislabeled Kcat, Ki, IC50, or a unit/OCR artifact from BRENDA's table,
# not a genuine Michaelis constant.
KM_PLAUSIBLE_MIN_MM = 0.0000001
KM_PLAUSIBLE_MAX_MM = 1000

def parse_brenda_km(ec_number: str, target_organism: str = "Homo sapiens",
                     target_substrates: list = None) -> list[BRENDAKmEntry]:

    r = retry_get(
        "https://www.brenda-enzymes.org/enzyme.php",
        params={"ecno": ec_number},
        timeout=15
    )
    soup = BeautifulSoup(r.text, "lxml")
    rows = soup.find_all("div", class_=re.compile(r"row"))

    results = []
    # Resolved dynamically via KEGG for any EC number - no hardcoded
    # per-enzyme substrate list. Falls back to an empty list (matching
    # every row's substrate check to fail, i.e. zero results) rather than
    # a fabricated guess if KEGG has nothing for this EC number, same
    # honest-gap behavior as brenda_client.py.
    if target_substrates is not None:
        natural_substrates = target_substrates
    else:
        try:
            kegg_text = enzyme_lookup.fetch_kegg_enzyme_text(ec_number)
            natural_substrates = enzyme_lookup.parse_kegg_substrates(kegg_text)
        except Exception:
            natural_substrates = []

    # Resolve the UniProt fallback ONCE per (ec_number, organism) before
    # the row loop, not once per row. The earlier version of this fix
    # called enzyme_lookup.fetch_taxon_id/fetch_uniprot_accession inside
    # the loop - for an enzyme with 100+ matching rows (e.g. hexokinase),
    # that's 100+ redundant live HTTP requests per run instead of one,
    # and risks hitting NCBI/UniProt rate limits. The result is identical
    # for every row of the same EC+organism, so it belongs outside the loop.
    fallback_uniprot = None
    try:
        taxon_id = enzyme_lookup.fetch_taxon_id(target_organism) or enzyme_lookup.DEFAULT_TAXON_ID
        fallback_uniprot = enzyme_lookup.fetch_uniprot_accession(ec_number, taxon_id)
    except Exception:
        fallback_uniprot = None

    for row in rows:
        cells = row.find_all("div", class_="cell")
        if len(cells) < 3:
            continue
        cell_texts = [c.get_text(strip=True) for c in cells]
        full_text = " | ".join(cell_texts)

        # Must mention target organism
        if target_organism not in full_text:
            continue

        # First cell must be a plain number (the Km value itself)
        km_match = re.match(r'^(\d+\.?\d*)$', cell_texts[0].strip())
        if not km_match:
            continue

        km_value = float(km_match.group(1))

        # Must mention a real substrate
        matched_substrate = None
        for sub in natural_substrates:
            if sub.lower() in full_text.lower():
                matched_substrate = sub
                break

        if not matched_substrate:
            continue

        # Extract UniProt ID if present in this row. Uses the same real
        # accession pattern as brenda_client.py (UNIPROT_CELL_PATTERN) -
        # this file previously had its own stale copy of the narrow
        # "^[A-Z]\d{5}$" pattern that was already fixed in brenda_client.py
        # but never propagated here, so it would have silently missed real
        # accessions like "Q6GPI1" the same way the main module once did.
        uniprot = None
        for cell in cell_texts:
            if UNIPROT_CELL_PATTERN.match(cell.strip()):
                uniprot = cell.strip()
                break

        # BRENDA doesn't always repeat the accession per row (e.g. when a
        # row has no purified/recombinant enzyme note). Fall back to the
        # canonical UniProt accession resolved once above - no hardcoded
        # per-enzyme map, and no redundant per-row network calls.
        if uniprot is None:
            uniprot = fallback_uniprot

        # Conditions are usually the longest descriptive cell
        conditions = max(cell_texts, key=len) if cell_texts else None

        # Reference ID is usually the last numeric cell
        ref_id = None
        for cell in reversed(cell_texts):
            if re.match(r'^\d{6}$', cell.strip()):
                ref_id = cell.strip()
                break

        # Flag entries that are unlikely to be genuine Km values so bad
        # data doesn't silently flow into citations.
        flagged = False
        flag_reason = None
        if km_value > KM_PLAUSIBLE_MAX_MM or km_value < KM_PLAUSIBLE_MIN_MM:
            flagged = True
            flag_reason = f"Km value {km_value} mM is outside plausible range " \
                           f"({KM_PLAUSIBLE_MIN_MM}-{KM_PLAUSIBLE_MAX_MM} mM); " \
                           f"likely a mislabeled Kcat/Ki/IC50 or unit error"
        elif conditions and re.search(r'\bkcat\b', conditions, re.IGNORECASE):
            flagged = True
            flag_reason = "conditions text mentions Kcat; row may report a " \
                           "turnover number rather than a true Km"

        results.append(BRENDAKmEntry(
            km_value=km_value,
            unit="mM",
            substrate=matched_substrate,
            organism=target_organism,
            uniprot=uniprot,
            conditions=conditions,
            reference_id=ref_id,
            flagged=flagged,
            flag_reason=flag_reason
        ))

    return results

# Test on LDH (1.1.1.27) and AChE (3.1.1.7)
print("=== Human LDH (EC 1.1.1.27) ===")
ldh_results = parse_brenda_km("1.1.1.27", "Homo sapiens",
                               ["lactate", "pyruvate", "NADH", "NAD+"])
for r in ldh_results:
    flag = "  [FLAGGED]" if r.flagged else ""
    print(f"  Km={r.km_value} {r.unit} | substrate={r.substrate} | "
          f"uniprot={r.uniprot} | ref={r.reference_id}{flag}")
    if r.conditions:
        print(f"    conditions: {r.conditions[:100]}")
    if r.flag_reason:
        print(f"    flag_reason: {r.flag_reason}")

print(f"\n  Total: {len(ldh_results)} entries "
      f"({sum(1 for r in ldh_results if r.flagged)} flagged)")

print("\n=== Human AChE (EC 3.1.1.7) ===")
ache_results = parse_brenda_km("3.1.1.7", "Homo sapiens",
                                ["acetylcholine", "acetylthiocholine", "acetyl thiocholine"])
for r in ache_results:
    flag = "  [FLAGGED]" if r.flagged else ""
    print(f"  Km={r.km_value} {r.unit} | substrate={r.substrate} | "
          f"uniprot={r.uniprot} | ref={r.reference_id}{flag}")
    if r.conditions:
        print(f"    conditions: {r.conditions[:100]}")
    if r.flag_reason:
        print(f"    flag_reason: {r.flag_reason}")

print(f"\n  Total: {len(ache_results)} entries "
      f"({sum(1 for r in ache_results if r.flagged)} flagged)")
