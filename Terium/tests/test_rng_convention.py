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


def test_default_rng_is_pcg64_as_adr_0005_states():
    """ADR 0005 named the wrong BitGenerator, and it mattered.

    The ADR justified "reproducibility across numpy versions is not
    guaranteed" with the claim that "numpy 2.x moved to Philox". It did
    not. `default_rng` has returned PCG64 since numpy 1.17, and numpy's
    own docstring says so.

    The conclusion was correct and the evidence was invented, which is the
    worse combination: the decision holds up, so nobody re-reads the
    premise. This asserts the premise against the installed numpy instead
    of against the prose, so a future numpy that genuinely changed the
    default would fail here and the ADR would be re-read on purpose.
    """
    import numpy as np

    assert type(np.random.default_rng(0).bit_generator).__name__ == "PCG64", (
        "numpy's default BitGenerator is no longer PCG64; ADR 0005's "
        "consequences section states that it is and must be re-read"
    )


def test_numpy_still_declines_to_guarantee_the_stream():
    """The real reason cross-version reproducibility is not promised.

    ADR 0005 depends on this being numpy's position. If numpy ever DID
    promise stream stability for `Generator`, the ADR's accepted
    limitation would no longer be a limitation and the trade-off it
    declines to make (pinning a BitGenerator) would need revisiting.
    """
    import numpy as np

    doc = np.random.Generator.__doc__ or ""
    assert "No Compatibility Guarantee" in doc, (
        "numpy's Generator docstring no longer carries the "
        "'No Compatibility Guarantee' clause that ADR 0005 relies on"
    )
