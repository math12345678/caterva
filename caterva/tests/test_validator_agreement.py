"""The package split must stay in effect, and the shim must stay a shim.

Stage 4 Part 3's audit caught `caterva_engine.py` in a state where it
imported all 67 public names from the new package **and then redefined 64 of
them below**. Python takes the later definition, so the package was imported
and immediately shadowed. Every test passed -- because the monolith was still
doing the work.

That is the failure this file exists to prevent, and it is invisible to every
behavioural test in the suite: the answers were correct, they just came from
the wrong place. Constitution amendment (c) from Stage 4 states the rule --
*a passing suite does not prove a change took effect; when a refactor claims
to relocate code, assert the relocation directly.*

So this asserts the relocation directly, via `__module__`.

A second concern, now resolved by construction but worth guarding: while the
monolith and `core/validation.py` both existed, the same scientific
constraint lived in two places, and it drifted. The package copy converted
four molecular-dynamics plausibility **flags** into hard **rejections** --

    engine  validate_md_params(108, 0.9, ...)  ->  ok=True,  flagged=True
    package validate_md_params(108, 0.9, ...)  ->  ok=False

-- a direct Rule 2 violation that would have told a student valid physics was
impossible. Now that the shim holds no definitions there is only one copy, so
drift is impossible rather than merely tested for. The three-state behavioural
cases below stay anyway: they pin the flag/reject boundary itself, which is
what the drift corrupted.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

import pytest

_CATERVA_DIR = pathlib.Path(__file__).resolve().parents[1]
_REPO_ROOT = _CATERVA_DIR.parent
for _p in (str(_REPO_ROOT), str(_CATERVA_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from caterva import caterva_engine as engine  # noqa: E402

_PACKAGE_PRESENT = (_CATERVA_DIR / "core" / "validation.py").exists()

# Public API -> the package module it must come from once the split is live.
EXPECTED_HOMES: dict[str, str] = {
    "simulate_michaelis_menten": "continuous.simulations",
    "simulate_sbml": "continuous.simulations",
    "simulate_mm_competitive_inhibition": "continuous.simulations",
    "simulate_gillespie_ssa": "discrete.gillespie_ssa",
    "validate_michaelis_menten_params": "core.validation",
    "validate_mm_competitive_params": "core.validation",
    "validate_ssa_params": "core.validation",
}


# ---------------------------------------------------------------------------
# The split took effect
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _PACKAGE_PRESENT, reason="package split not present")
def test_shim_defines_no_implementations() -> None:
    """`caterva_engine.py` must re-export, never define.

    A definition here silently wins over the imported one -- the exact
    shadowing that made the half-finished split invisible to the suite.
    """
    source = (_CATERVA_DIR / "caterva_engine.py").read_text(encoding="utf-8")
    # An empty or unreadable shim would pass the scan below having checked
    # nothing, which is the state this test is least able to tolerate.
    assert source.strip(), "caterva_engine.py is empty; nothing was scanned"
    offenders = [
        line.split("(")[0].replace("def ", "").strip()
        for line in source.splitlines()
        if line.startswith(("def simulate_", "def validate_", "def build_"))
    ]
    assert not offenders, (
        "caterva_engine.py defines implementations instead of re-exporting: "
        f"{offenders}. A local definition shadows the package import and the "
        "split stops being in effect, with every test still green."
    )


@pytest.mark.skipif(not _PACKAGE_PRESENT, reason="package split not present")
@pytest.mark.parametrize(("name", "home"), sorted(EXPECTED_HOMES.items()))
def test_public_name_resolves_to_its_package_module(name: str, home: str) -> None:
    fn = getattr(engine, name, None)
    assert fn is not None, f"{name} is missing from caterva_engine"
    actual = getattr(fn, "__module__", "")
    assert actual.endswith(home), (
        f"{name} resolves to {actual!r}, expected a module ending in {home!r}. "
        "Either the split regressed or the function moved without this map "
        "being updated."
    )


# ---------------------------------------------------------------------------
# The flag/reject boundary itself
# ---------------------------------------------------------------------------

CASES: list[tuple[str, dict[str, Any], str, str]] = [
    ("validate_michaelis_menten_params", dict(km=2.0, vmax=5.0, s0=10.0), "accepted", "MM nominal"),
    ("validate_michaelis_menten_params", dict(km=1e-9, vmax=5.0, s0=10.0), "flagged", "MM km below bound"),
    ("validate_michaelis_menten_params", dict(km=1e5, vmax=5.0, s0=10.0), "flagged", "MM km above bound"),
    ("validate_michaelis_menten_params", dict(km=0.0, vmax=5.0, s0=10.0), "rejected", "MM km zero"),
    ("validate_michaelis_menten_params", dict(km=float("nan"), vmax=5.0, s0=10.0), "rejected", "MM km NaN"),






    # These five are the exact cases the flag->rejection inversion corrupted.

    ("validate_ssa_replicates_params", dict(n_replicates=100), "accepted", "SSA replicates nominal"),
    ("validate_ssa_replicates_params", dict(n_replicates=5), "flagged", "SSA few replicates"),
    ("validate_ssa_replicates_params", dict(n_replicates=0), "rejected", "SSA zero replicates"),
]


@pytest.mark.parametrize(
    ("validator", "kwargs", "expected", "label"),
    CASES,
    ids=[c[3] for c in CASES],
)
def test_flag_reject_boundary(
    validator: str, kwargs: dict[str, Any], expected: str, label: str
) -> None:
    """Rule 2: impossible is rejected, implausible is flagged, neither is
    silently accepted -- and the distinction is not collapsed in either
    direction."""
    v = getattr(engine, validator)(**kwargs)
    actual = "rejected" if not v.ok else ("flagged" if v.flagged else "accepted")
    assert actual == expected, (
        f"{label}: expected {expected}, got {actual}. "
        "A flag turned into a rejection tells a student that valid physics "
        "is impossible; a rejection turned into a flag lets an impossible "
        "parameter reach the solver."
    )
    if expected == "flagged":
        assert v.flag_reason, f"{label}: flagged with no flag_reason"
    if expected == "rejected":
        assert v.errors, f"{label}: rejected with no errors"


def test_every_validator_is_exercised_in_all_three_states() -> None:
    """A validator tested only on its happy path cannot reveal an inversion."""
    seen: dict[str, set[str]] = {}
    for validator, _, expected, _ in CASES:
        seen.setdefault(validator, set()).add(expected)
    for validator, states in sorted(seen.items()):
        assert states == {"accepted", "flagged", "rejected"}, (
            f"{validator} is only exercised in {sorted(states)}"
        )
