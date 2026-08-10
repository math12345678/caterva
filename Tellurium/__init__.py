"""Terrium simulation engine package.

The package namespace is DERIVED from ``tellurium_engine.__all__`` rather
than restated here.

It used to be a hand-written list of imports plus a hand-written
``__all__``, i.e. a second copy of a list that already existed. By
2026-08-09 that copy had fallen 25 names behind, including seven simulation
domains:

    simulate_lotka_volterra          simulate_gillespie_ssa
    simulate_cell_cycle_oscillator   simulate_gillespie_ssa_bimolecular
    simulate_repressilator           simulate_gillespie_ssa_replicates
    simulate_mm_competitive_inhibition

so ``import Tellurium; Tellurium.simulate_lotka_volterra`` raised
AttributeError for functions the engine exports and the API dispatches.
Nothing caught it: ``check_domain_parity.py`` compares the runner, the
TypeScript union and the schemas, and ``test_boundary_contract.py`` compares
DISPATCH against ``tellurium_engine.__all__`` — no check looked at this
file, because a package's own re-export list is not somewhere anyone thinks
to look for drift.

Re-exporting programmatically removes the possibility rather than adding a
fifteenth guard against it. ADR 0007's principle applied one level up: the
engine's ``__all__`` is the contract, and every other layer follows it
instead of maintaining a parallel truth.

Kept explicit: ``tellurium_engine`` itself, which the API bridge imports as
a module (``from Tellurium import tellurium_engine``).
"""

from __future__ import annotations

from . import tellurium_engine
from .tellurium_engine import *  # noqa: F401,F403

#: Mirrors the engine exactly. `list(...)` copies so that a caller mutating
#: `Tellurium.__all__` cannot reach through and corrupt the engine's own.
__all__ = [*tellurium_engine.__all__, "tellurium_engine"]

# A star-import only binds names the source module's __all__ advertises, so
# the two agree by construction. This assertion states that dependency out
# loud: if `tellurium_engine.__all__` ever names something it does not
# actually define, the failure surfaces here at import time rather than as
# an AttributeError in a student's simulation.
_missing = [
    _name for _name in tellurium_engine.__all__
    if not hasattr(tellurium_engine, _name)
]
if _missing:  # pragma: no cover - defensive; the contract guard also checks
    raise ImportError(
        "tellurium_engine.__all__ names symbols it does not define: "
        f"{sorted(_missing)}"
    )
del _missing
