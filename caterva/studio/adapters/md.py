"""Kinds `md.setup` and `md.summarise`: `caterva md` (owner: sci-structure).

WHAT IT WILL CALL (caterva/md/)
    __main__._from_kinetics(ec, organism, substrate)   conditions from a cited Km's
                                                       assay (a compose search: network)
    setup.MdSetup(...).files() / .parameters           the files and every parameter's origin
    convergence.collect / summarise / report           `--summarise DIR`

WHAT HAS NO STRUCTURED FORM YET
    `main` interleaves computing the setup with writing and printing it;
    extract the part before the writes so the adapter gets the MdSetup and
    the note without re-deriving either. Three refusals in `main` (no
    --pdb/--out, --replicas below 1, a malformed PDB id, --subject without
    --substrate) return 2 after parsing, outside argparse, so `parse_cli`
    cannot see them; move them into one check that calls `parser.error`.
    `Conditions` carries the measured temperature's citation only inside
    the `temperature_source` sentence; keep the Measurement beside it so
    the provenance is read from an object, never parsed out of prose.
    `--summarise` writes CONVERGENCE.md into the user's directory, as the
    CLI does; the result says so (CONTRACT.md, "User paths").
"""
from __future__ import annotations


def register(registry) -> None:
    """Registers nothing until sci-structure builds this adapter."""
