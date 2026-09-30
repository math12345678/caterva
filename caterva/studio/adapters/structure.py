"""Kind `structure`: `caterva structure`, an enzyme's PDB entries, cited (owner: sci-structure).

WHAT IT WILL CALL (caterva/structure/)
    search.find_structures(ec, organism, gene, uniprot, ligand)  RCSB and UniProt:
                                                   network, a few seconds
    StructureSearch.ranked(), Structure.cite()     the ordering and citations
    chimerax.script(best, chosen, focus)           the optional ChimeraX script

Also serves GET /api/structure/{pdb_id}/coordinates (CoordinatesResponse)
for the 3D viewer, from the entry's mmCIF read with caterva/prepare/cif.py
through prepare's own `cached(live_fetch(), _cache_dir())`, registered with
`registry.add_endpoint("structure_coordinates", ..., owner="structure")`.

WHAT HAS NO STRUCTURED FORM YET
    None needed: `find_structures` returns the StructureSearch the report is
    drawn from. A CLI defect to fix, not copy: `--chimerax` with no entry in
    the ranking indexes `ranked()[0]` and crashes (IndexError, exit 1)
    instead of refusing.
"""
from __future__ import annotations


def register(registry) -> None:
    """Registers nothing until sci-structure builds this adapter."""
