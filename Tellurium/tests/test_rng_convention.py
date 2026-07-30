"""Every discrete/stochastic domain must comply with ADR 0005.

ADR 0005 requires all discrete/stochastic domains to use
``numpy.random.default_rng(seed)`` with ``seed: int | None = None``.
This test wraps ``scripts/check_rng_convention.py`` to run the same
AST-based static analysis as part of the test suite — so a domain that
violates the convention causes a CI failure, not just a script warning.
"""

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_rng_convention import check  # noqa: E402


def test_all_stochastic_domains_comply_with_adr_0005():
    violations = check()
    assert not violations, (
        "ADR 0005 violations found:\n" + "\n".join(f"  {v}" for v in violations)
    )
