"""Initial-rate kinetics from a lab's own measurements: `caterva rates`.

The other door beside the literature: where `caterva compose` asks BRENDA
for a constant, this estimates it from the rates a laboratory measured, says
how well the data determine it, which mechanisms the data rule out, and how
it compares with the constant BRENDA cites. `__main__.py` lists the modules
in the order a run uses them. Nothing produced here is a literature value,
and every output says so.
"""
from __future__ import annotations
