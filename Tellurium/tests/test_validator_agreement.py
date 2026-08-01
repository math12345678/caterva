"""The package split must stay in effect, and the shim must stay a shim.

Stage 4 Part 3's audit caught `tellurium_engine.py` in a state where it
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

_TELLURIUM_DIR = pathlib.Path(__file__).resolve().parents[1]
_REPO_ROOT = _TELLURIUM_DIR.parent
for _p in (str(_REPO_ROOT), str(_TELLURIUM_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from Tellurium import tellurium_engine as engine  # noqa: E402

_PACKAGE_PRESENT = (_TELLURIUM_DIR / "core" / "validation.py").exists()

# Public API -> the package module it must come from once the split is live.
EXPECTED_HOMES: dict[str, str] = {
    "simulate_michaelis_menten": "continuous.simulations",
    "simulate_sir": "continuous.simulations",
    "simulate_seir": "continuous.simulations",
    "simulate_sbml": "continuous.simulations",
    "simulate_pcr": "discrete.pcr",
    "simulate_monte_carlo_pi": "discrete.monte_carlo",
    "simulate_molecular_dynamics": "discrete.molecular_dynamics",
    "lj_cluster_positions": "discrete.molecular_dynamics",
    "lennard_jones_force": "discrete.molecular_dynamics",
    "simulate_wright_fisher": "discrete.population_genetics.core",
    "simulate_two_locus_wright_fisher": "discrete.population_genetics.two_locus",
    "validate_michaelis_menten_params": "core.validation",
    "validate_sir_params": "core.validation",
    "validate_seir_params": "core.validation",
    "validate_pcr_params": "core.validation",
    "validate_monte_carlo_params": "core.validation",
    "validate_wright_fisher_params": "core.validation",
    "validate_md_params": "core.validation",
}


# ---------------------------------------------------------------------------
# The split took effect
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _PACKAGE_PRESENT, reason="package split not present")
def test_shim_defines_no_implementations() -> None:
    """`tellurium_engine.py` must re-export, never define.

    A definition here silently wins over the imported one -- the exact
    shadowing that made the half-finished split invisible to the suite.
    """
    source = (_TELLURIUM_DIR / "tellurium_engine.py").read_text(encoding="utf-8")
    offenders = [
        line.split("(")[0].replace("def ", "").strip()
        for line in source.splitlines()
        if line.startswith(("def simulate_", "def validate_", "def build_"))
    ]
    assert not offenders, (
        "tellurium_engine.py defines implementations instead of re-exporting: "
        f"{offenders}. A local definition shadows the package import and the "
        "split stops being in effect, with every test still green."
    )


@pytest.mark.skipif(not _PACKAGE_PRESENT, reason="package split not present")
@pytest.mark.parametrize(("name", "home"), sorted(EXPECTED_HOMES.items()))
def test_public_name_resolves_to_its_package_module(name: str, home: str) -> None:
    fn = getattr(engine, name, None)
    assert fn is not None, f"{name} is missing from tellurium_engine"
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

    ("validate_sir_params", dict(beta=0.3, gamma=0.1, s0=990, i0=10), "accepted", "SIR nominal"),
    ("validate_sir_params", dict(beta=0.3, gamma=0.1, s0=990, i0=0), "flagged", "SIR no infected"),
    ("validate_sir_params", dict(beta=10.0, gamma=0.1, s0=990, i0=10), "flagged", "SIR R0=100"),
    ("validate_sir_params", dict(beta=-1.0, gamma=0.1, s0=990, i0=10), "rejected", "SIR beta negative"),

    ("validate_seir_params", dict(beta=0.3, sigma=0.2, gamma=0.1, s0=990, e0=10, i0=0), "accepted", "SEIR nominal"),
    ("validate_seir_params", dict(beta=0.3, sigma=0.2, gamma=0.1, s0=1000, e0=0, i0=0), "flagged", "SEIR no seed"),
    ("validate_seir_params", dict(beta=0.3, sigma=-1.0, gamma=0.1, s0=990, e0=10, i0=0), "rejected", "SEIR sigma negative"),

    ("validate_pcr_params", dict(n0=100.0, efficiency=0.95, cycles=30), "accepted", "PCR nominal"),
    ("validate_pcr_params", dict(n0=100.0, efficiency=0.2, cycles=30), "flagged", "PCR low efficiency"),
    ("validate_pcr_params", dict(n0=100.0, efficiency=1.4, cycles=30), "rejected", "PCR efficiency>1"),
    ("validate_pcr_params", dict(n0=100.0, efficiency=0.9, cycles=80), "rejected", "PCR cycles>60"),

    ("validate_monte_carlo_params", dict(n_samples=10_000), "accepted", "MC nominal"),
    ("validate_monte_carlo_params", dict(n_samples=10), "flagged", "MC below min"),
    ("validate_monte_carlo_params", dict(n_samples=0), "rejected", "MC zero"),

    ("validate_wright_fisher_params", dict(population_size=100, starting_frequency=0.5, generations=100, replicate_runs=50), "accepted", "WF nominal"),
    ("validate_wright_fisher_params", dict(population_size=5, starting_frequency=0.5, generations=100, replicate_runs=50), "flagged", "WF small N"),
    ("validate_wright_fisher_params", dict(population_size=100, starting_frequency=0.5, generations=100, replicate_runs=2), "flagged", "WF few replicates"),
    ("validate_wright_fisher_params", dict(population_size=0, starting_frequency=0.5, generations=100), "rejected", "WF N=0"),
    ("validate_wright_fisher_params", dict(population_size=100, starting_frequency=1.5, generations=100), "rejected", "WF p0>1"),

    # These five are the exact cases the flag->rejection inversion corrupted.
    ("validate_md_params", dict(n_particles=108, temperature=0.4, timestep=0.005, n_steps=100), "accepted", "MD nominal"),
    ("validate_md_params", dict(n_particles=108, temperature=0.9, timestep=0.005, n_steps=100), "flagged", "MD T above bound"),
    ("validate_md_params", dict(n_particles=108, temperature=0.05, timestep=0.005, n_steps=100), "flagged", "MD T below bound"),
    ("validate_md_params", dict(n_particles=108, temperature=0.4, timestep=0.05, n_steps=100), "flagged", "MD timestep high"),
    ("validate_md_params", dict(n_particles=108, temperature=-1.0, timestep=0.005, n_steps=100), "rejected", "MD T negative"),
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
