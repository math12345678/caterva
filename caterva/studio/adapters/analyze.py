"""Kind `analyze`: `caterva analyze DIR`, catalytic geometry across replicas (owner: sci-structure).

WHAT IT WILL CALL (caterva/analyze/__main__.py)
    setup_info, catalytic_residues (M-CSA via prepare: network), plan,
    measure_native (reads .xtc natively; seconds to minutes) or run_gromacs +
    measure (needs gmx), then Analysis(...) and report(analysis).

WHAT HAS NO STRUCTURED FORM YET
    `main` builds the Analysis inline between its argument handling and its
    printing. Extract that middle into one function returning the Analysis
    (and whether a script was written), called by `main` and the adapter.
    Keep the change small: feat/analyze-pca and feat/analyze-sasa edit this
    file too. `main` writes analyze.sh, the chi1 index and ANALYSIS.md into
    the user's directory, as the CLI does; the result says so. The GROMACS
    route reads GMX from the environment, as the CLI does.
"""
from __future__ import annotations


def register(registry) -> None:
    """Registers nothing until sci-structure builds this adapter."""
