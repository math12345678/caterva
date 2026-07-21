"""
Hardening check: why does KEGG return zero substrates for trypsin
(EC 3.4.21.4) and chymotrypsin (EC 3.4.21.1)? Dumps the raw KEGG flat
text so we can see the actual field structure, rather than guessing.
Generic - works for any EC number.
"""

import sys

import enzyme_lookup

EC = sys.argv[1] if len(sys.argv) > 1 else "3.4.21.4"

print(f"Fetching KEGG flat text for EC {EC} ...")
text = enzyme_lookup.fetch_kegg_enzyme_text(EC)
print(text)
print("\n=== parse_kegg_substrates result ===")
print(enzyme_lookup.parse_kegg_substrates(text))
