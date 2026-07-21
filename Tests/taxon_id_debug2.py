"""
Live check for the new enzyme_lookup.fetch_taxon_id, which replaced a
hardcoded 7-organism dict (ORGANISM_TAXON_IDS) with a dynamic NCBI
taxonomy lookup. Confirms it resolves organisms that were in the old
list (sanity check against known values) AND organisms that were NOT -
e.g. Cryptosporidium parvum, which the old dict would have silently
returned None for.
"""

import enzyme_lookup

TEST_ORGANISMS = [
    ("Homo sapiens", "9606"),       # was in the old dict - known value
    ("Sus scrofa", "9823"),         # was in the old dict - known value
    ("Cryptosporidium parvum", None),  # NOT in the old dict - real BRENDA LDH organism
    ("Epidalea calamita", None),       # NOT in the old dict - real BRENDA LDH organism
]

for name, expected in TEST_ORGANISMS:
    taxon_id = enzyme_lookup.fetch_taxon_id(name)
    status = "OK" if (expected is None or taxon_id == expected) else "MISMATCH"
    print(f"{name!r:35} -> taxon_id={taxon_id!r}  (expected={expected!r})  [{status}]")
