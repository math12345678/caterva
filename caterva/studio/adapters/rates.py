"""Kind `rates`: reserved for `caterva rates`, which arrives from another branch.

Registers nothing until that command is integrated. The page shows /rates
only when /api/capabilities reports `rates.available`, and that stays false
while this module registers nothing, so the route cannot lead anywhere empty.
"""
from __future__ import annotations


def register(registry) -> None:
    """Registers nothing until `caterva rates` is integrated."""
