"""Kind `prepare`: `caterva prepare`, a PDB entry audited before simulating it (owner: sci-structure).

WHAT IT WILL CALL (caterva/prepare/__main__.py)
    run_audit(entry, fetch)       mmCIF from RCSB (or a local .cif), UniProt
                                  sequences; network unless a local file
    report(audit, ph)             the text; `dataclasses.asdict(audit)` is --json
    exit 0 a clean chain exists, 4 every chain blocked, 3 refused

WHAT HAS NO STRUCTURED FORM YET
    The protonation table is rendered inside `protonation_section` from
    `protonation.assess`; lift the per-residue assessment into a function the
    section and the adapter both call. The exit rule ("a chain with no
    blocking defect and its catalytic residues intact") is an expression
    inside `main`; make it a function or an Audit property so the adapter
    reads the same decision rather than restating it.
    A local .cif entry is a user path (CONTRACT.md, "User paths").
"""
from __future__ import annotations


def register(registry) -> None:
    """Registers nothing until sci-structure builds this adapter."""
