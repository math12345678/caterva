"""Kind `sim`: `caterva sim ssa`, exact Gillespie SSA (owner: sci-kinetics).

WHAT IT WILL CALL (caterva/cli.py `_cmd_ssa`)
    caterva_engine.simulate_gillespie_ssa(a0, k, end, seed) or
    simulate_gillespie_ssa_bimolecular(a0, b0, k, end, seed); milliseconds to
    seconds, no network.

WHAT HAS NO STRUCTURED FORM YET
    The ODE expectation printed beside the result ("expected A(end) (ODE)")
    is computed inline in `_cmd_ssa`'s printing code. Move it into a function
    both the printer and the adapter call, and the event count
    (`len(result.data) - 2`) with it. The parser is built inside `main`;
    expose `build_parser(prog)` so `parse_cli` can use it.

    A CLI defect to report, not to copy: `--k` defaults to 0.5 for the
    bimolecular reaction too, while its help says 0.005. SimRequest.k is
    therefore sent explicitly whenever the page shows a default.
"""
from __future__ import annotations


def register(registry) -> None:
    """Registers nothing until sci-kinetics builds this adapter."""
