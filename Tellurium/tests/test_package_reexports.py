"""Regression: the package namespace must not drift from the engine.

`Tellurium/__init__.py` was a hand-written list of imports plus a
hand-written `__all__` — a second copy of a list that already existed in
`tellurium_engine.__all__`. It fell 25 names behind, including seven
simulation domains that the engine exports and the API dispatches:

    simulate_lotka_volterra          simulate_gillespie_ssa
    simulate_cell_cycle_oscillator   simulate_gillespie_ssa_bimolecular
    simulate_repressilator           simulate_gillespie_ssa_replicates
    simulate_mm_competitive_inhibition

`import Tellurium; Tellurium.simulate_lotka_volterra` raised AttributeError
for a function that demonstrably worked.

No existing check covered it. `check_domain_parity.py` compares the runner,
the TypeScript union and the Zod schemas; `test_boundary_contract.py`
compares DISPATCH against `tellurium_engine.__all__`. A package's own
re-export list is not somewhere anyone thinks to look for drift, which is
exactly why it drifted.

The fix re-exports programmatically, so the two agree by construction. This
file pins that they still do — a future edit reintroducing a manual list
would pass every other test in the repository.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import Tellurium  # noqa: E402
from Tellurium import tellurium_engine  # noqa: E402

#: The seven that were actually missing. Named individually so a failure
#: says which capability disappeared rather than only a count.
DOMAINS_THAT_WENT_MISSING = [
    "simulate_lotka_volterra",
    "simulate_cell_cycle_oscillator",
    "simulate_repressilator",
    "simulate_gillespie_ssa",
    "simulate_gillespie_ssa_bimolecular",
    "simulate_gillespie_ssa_replicates",
    "simulate_mm_competitive_inhibition",
]


class TestPackageMirrorsTheEngine:
    def test_every_engine_export_is_reachable_from_the_package(self):
        missing = [
            name for name in tellurium_engine.__all__
            if not hasattr(Tellurium, name)
        ]
        assert missing == [], (
            f"{len(missing)} engine exports are unreachable as "
            f"Tellurium.<name>: {sorted(missing)}"
        )

    @pytest.mark.parametrize("name", DOMAINS_THAT_WENT_MISSING)
    def test_the_specific_domains_that_regressed(self, name):
        assert hasattr(Tellurium, name), (
            f"Tellurium.{name} raises AttributeError for a domain the "
            "engine exports and tellurium_runner.py dispatches"
        )
        assert callable(getattr(Tellurium, name))

    def test_package_all_covers_the_engine_all(self):
        engine = set(tellurium_engine.__all__)
        package = set(Tellurium.__all__)
        assert engine <= package, (
            f"__all__ has drifted; missing: {sorted(engine - package)}"
        )

    def test_package_all_advertises_nothing_it_lacks(self):
        # The other direction: __all__ must not promise absent names, or
        # `from Tellurium import *` fails at import.
        absent = [n for n in Tellurium.__all__ if not hasattr(Tellurium, n)]
        assert absent == [], f"__all__ names undefined symbols: {absent}"


class TestTheModuleItselfStaysImportable:
    def test_tellurium_engine_module_is_still_reachable(self):
        """`from Tellurium import tellurium_engine` is the API bridge's path.

        `tellurium_runner.py` imports the MODULE, not its contents. A
        re-export refactor that dropped the submodule binding would break
        every simulation while leaving the function-level tests green.
        """
        assert Tellurium.tellurium_engine is tellurium_engine
        assert "tellurium_engine" in Tellurium.__all__

    def test_a_domain_actually_runs_through_the_package_path(self):
        # Reachable is not the same as working.
        result = Tellurium.simulate_lotka_volterra(end=5.0, points=51)
        assert len(result.data) == 51
        assert result.colnames[0] == "time"
