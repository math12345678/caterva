"""Kind `constants`: `scripts/cite.py`, real constants with their citations (owner: sci-kinetics).

WHAT IT WILL CALL
    scripts/cite.py builds a payload and runs scripts/report_lab.py in a
    subprocess; report_lab resolves each quantity with
    fallback_logic.resolve_kinetic_value (BRENDA, UniProt, NCBI Taxonomy,
    PubMed: network and the literature layer) and returns JSON with the
    document's markdown and the lists sourced/supplied/derived/refusals/
    disagreements/defensible.

WHAT HAS NO STRUCTURED FORM YET
    report_lab's JSON carries the document but not the per-constant
    KineticResult it was built from (value, unit, citation, conditions,
    alternatives, the organisms/isoforms/modes a refusal names). Add
    `"resolved": {name: result.model_dump(mode="json")}` to that JSON, beside
    the markdown, so ConstantRow is read from the resolver's own object.

    cite.py builds its parser inside `main`; expose `build_parser(prog)`.
    It runs report_lab as `[sys.executable, "scripts/report_lab.py"]`, which
    in a frozen app is the `caterva` executable, not Python; give report_lab
    a function taking the payload and returning the dict it prints, and
    call that in-process (the CLI keeps its subprocess). scripts/ is not in
    the wheel, so this kind is available from a source checkout only, and
    `unavailable()` says so in the words cite.py already uses.
"""
from __future__ import annotations


def register(registry) -> None:
    """Registers nothing until sci-kinetics builds this adapter."""
