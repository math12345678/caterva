"""Every stochastic domain must use numpy.random.default_rng(seed), per ADR
0005 (docs/adr/0005-rng-convention.md).

This is the shared cross-layer constraint Rule 4 requires an executable
test for, not just a comment: Monte Carlo (Stage 1) and Wright-Fisher
(Stage 2) both independently follow this convention today, and nothing
previously stopped a future stochastic domain from silently drifting to a
different RNG interface (`random.Random`, `np.random.RandomState`,
`np.random.seed`'s global-state API) except manual review at implementation
time. See scripts/check_rng_convention.py for the static analysis this test
wraps -- verified, by deliberately mutating tellurium_engine.py's RNG
constructor and confirming this check fails, then reverting and confirming
it passes again (Stage 2 "continue improving" follow-up, 2026-07-30).
"""

import pathlib
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_rng_convention import check  # noqa: E402


def test_all_stochastic_domains_use_default_rng():
    violations = check()
    assert not violations, (
        "ADR 0005 (numpy.random.default_rng(seed)) is violated by: "
        f"{violations}. See docs/adr/0005-rng-convention.md."
    )
