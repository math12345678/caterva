"""Kinds `fep.status` and `complex.check`: where an FEP run stands (owner: sci-structure).

WHAT IT WILL CALL
    caterva/fep/__main__.py `summarise(DIR)`: reads caterva-fep.json and each
        leg's BAR output, combines replicas, judges against the band (bind.core.judge)
    caterva/fep/complex.py `check(DIR, resname, itp)`: the pose after equilibration

WHAT HAS NO STRUCTURED FORM YET
    `summarise` computes and prints in one pass and returns only the exit
    code; split it into a function returning the per-replica values, the
    mean and sigma and the Verdict, and a printer over that. The parsers of
    both commands are built inside `main`; expose `build_parser(prog)`.
    `complex --check` judges "kept" (the final RMSD, then the worst frame of
    npt.xtc when present) inside `main`; move that into a function
    returning the values and the judgement. A CLI defect to report: `--check`
    accepts --ligand-itp and does not pass it to `check()`, so the request
    has no ligand_itp (contract.ComplexCheckRequest).
"""
from __future__ import annotations


def register(registry) -> None:
    """Registers nothing until sci-structure builds this adapter."""
