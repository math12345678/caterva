"""Kind `bind`: `caterva bind`, the measured binding free energy a simulation is held to (owner: sci-kinetics).

WHAT IT WILL CALL (caterva/bind/__main__.py, caterva/bind/core.py)
    brenda_client.fetch_brenda_html(ec)          network, literature layer
    _rows / _compound_names / survey             parse the Ki rows
    core.target(rows, state, isoform)            the band (Target)
    core.judge(target, value, error, T)          the verdict (Verdict)
    report(rows, state, computed, unit, isoform) the text, exit code and --json payload

WHAT HAS NO STRUCTURED FORM YET
    The argument parser is built inside `main`; expose `build_parser(prog)`.
    `report` already returns (text, code, payload), which is the accessor.
    `main` rewrites `--computed -7.9` to `--computed=-7.9` before parsing
    (argparse reads a negative number as a flag); argv() must emit the
    `--computed=VALUE±ERROR` form itself. `--list` has only the private
    `_compound_names`; make it public rather than re-reading the page.
    Exit 4 here means "disagrees" (contract.NEGATIVE_MEANING), a result.
"""
from __future__ import annotations


def register(registry) -> None:
    """Registers nothing until sci-kinetics builds this adapter."""
