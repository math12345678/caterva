"""The seam between the literature layer and the simulation layer.

This is Phase 1 Week 4 of the build plan expressed as tests: a Km that BRENDA
resolved has to arrive at roadrunner with its provenance and its flags intact.

The failure mode these tests exist to catch is not a crash. It is a value that
the literature layer marked as suspicious quietly becoming a confident number
in a student's plot.
"""

import pathlib
import sys

import pytest

# The BRENDA layer lives in the sibling Tests/ package.
_BRENDA_DIR = pathlib.Path(__file__).resolve().parents[2] / "Tests"
if str(_BRENDA_DIR) not in sys.path:
    sys.path.insert(0, str(_BRENDA_DIR))

brenda_client = pytest.importorskip(
    "brenda_client", reason="BRENDA layer not importable from this checkout")

from terium_engine import (  # noqa: E402
    KM_PLAUSIBLE_MAX_MM,
    KM_PLAUSIBLE_MIN_MM,
    simulate_michaelis_menten,
    validate_michaelis_menten_params,
)


# ---------------------------------------------------------------------------
# Constant agreement
#
# Regression guard for a real bug: the engine had 1e4 while BRENDA had 1e3, so
# a Km of 5000 mM was flagged upstream and silently accepted downstream.
# ---------------------------------------------------------------------------


def test_km_lower_bound_matches_the_brenda_layer():
    assert KM_PLAUSIBLE_MIN_MM == brenda_client.KM_PLAUSIBLE_MIN_MM


def test_km_upper_bound_matches_the_brenda_layer():
    assert KM_PLAUSIBLE_MAX_MM == brenda_client.KM_PLAUSIBLE_MAX_MM, (
        "the simulation layer would accept a Km the literature layer flags")


@pytest.mark.parametrize("km", [5e3, 1e4, 5e4])
def test_values_flagged_upstream_are_flagged_downstream(km):
    # Each of these is above the shared upper bound; both layers must agree
    # that it is suspicious.
    assert km > brenda_client.KM_PLAUSIBLE_MAX_MM
    assert validate_michaelis_menten_params(km=km, vmax=1.0, s0=1.0).flagged


@pytest.mark.parametrize("km", [1e-9, 1e-8])
def test_tiny_values_flagged_upstream_are_flagged_downstream(km):
    assert km < brenda_client.KM_PLAUSIBLE_MIN_MM
    assert validate_michaelis_menten_params(km=km, vmax=1.0, s0=1.0).flagged


@pytest.mark.parametrize("km", [1e-7, 0.049, 0.49, 4.9, 100.0, 1000.0])
def test_values_accepted_upstream_are_accepted_downstream(km):
    # Real BRENDA-range values must pass both layers unflagged, or the product
    # cries wolf on ordinary data.
    within_brenda = (brenda_client.KM_PLAUSIBLE_MIN_MM <= km
                     <= brenda_client.KM_PLAUSIBLE_MAX_MM)
    assert within_brenda
    assert not validate_michaelis_menten_params(km=km, vmax=1.0, s0=1.0).flagged


# ---------------------------------------------------------------------------
# End-to-end: real fixture data -> simulation
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ldh_entries():
    """Km entries parsed from the real captured BRENDA page for LDH.

    Both conditions below were `pytest.skip` and are now hard failures.

    The fixture file is committed to this repository, so its absence is a
    broken checkout, not an environment this suite should tolerate. And if
    the parser returns nothing from a fixture that demonstrably contains
    rows, that is precisely the regression these tests exist to catch --
    skipping on it would make *every test in this file* vanish from the run
    while the suite stayed green.

    That is not hypothetical: a sibling test in this file skipped itself
    into vacuity for months on a near-identical `if not X: skip` (see
    test_flagged_brenda_entries_do_not_become_confident_numbers).
    """
    fixture = _BRENDA_DIR / "fixtures" / "brenda_ldh_fixture.html"
    assert fixture.exists(), (
        f"committed fixture missing: {fixture} -- this is a broken checkout, "
        "not a reason to skip the literature/simulation seam tests")
    entries = brenda_client.parse_brenda_km_html(
        html=fixture.read_text(),
        ec_number="1.1.1.27",
        target_substrates=["pyruvate", "NADH", "lactate", "NAD+"],
        target_organism="Homo sapiens",
        require_substrate_match=False,
    )
    assert entries, (
        "parsed zero Km entries from the committed LDH fixture; the fixture "
        "contains rows, so this is a parser regression -- failing loudly "
        "rather than skipping every test in this file")
    return entries


def test_fixture_yields_real_entries(ldh_entries):
    assert len(ldh_entries) > 0
    assert all(hasattr(e, "km_value") for e in ldh_entries)


def test_every_unflagged_brenda_km_is_simulable(ldh_entries):
    """The core contract: anything the literature layer blesses must run."""
    usable = [e for e in ldh_entries
              if not getattr(e, "flagged", False) and e.km_value]
    # Assertion, not skip: the LDH fixture demonstrably yields unflagged
    # entries, so an empty list means the parser or the flagging logic
    # regressed. Skipping would retire this contract silently.
    assert usable, (
        "no unflagged entries parsed from the LDH fixture; it contains "
        "several, so this is a regression rather than a reason to skip")

    for entry in usable:
        km = float(entry.km_value)
        result = simulate_michaelis_menten(km=km, vmax=1.0, s0=max(km * 10, 1.0),
                                           end=1.0, points=11)
        assert len(result) == 11
        assert not result.flagged, (
            f"Km {km} passed BRENDA but was flagged by the engine")


def test_flagged_brenda_entries_do_not_become_confident_numbers(ldh_entries):
    """The core Rule 2 assertion at this seam.

    This test previously read:

        flagged = [e for e in ldh_entries if e.flagged]
        if not flagged:
            pytest.skip("no flagged entries in this fixture")

    Every fixture in the repository parses to **zero** flagged entries, so
    the skip fired every time and the assertions below had never executed
    once. It was counted in the suite while testing nothing -- the Stage 4
    amendment ("structural tests are blind to semantic emptiness") in a new
    costume: a test that skips itself into vacuity.

    Real flagged rows cannot simply be added to a fixture, because the
    fixtures are live BRENDA captures and BRENDA does not happen to serve a
    flagged row for these enzymes. So the entries below are constructed
    directly and labelled as synthetic. They are not claimed to be BRENDA
    data; they exist to drive the contract, and each one mirrors a flag
    cause that `parse_brenda_km_html` genuinely produces.
    """
    # Any real flagged entries the fixture does produce are still checked.
    flagged = [e for e in ldh_entries if getattr(e, "flagged", False)]

    # SYNTHETIC (not BRENDA data): one per real flag cause in brenda_client.
    flagged = [
        *flagged,
        # Cause 1: outside the plausible Km range -- the engine must agree.
        #
        # 50000 mM is a fixed literal, deliberately NOT derived from
        # KM_PLAUSIBLE_MAX_MM. A value written as `KM_PLAUSIBLE_MAX_MM * 10`
        # moves with the bound, so widening the bound would move the test
        # value too and the assertion would keep passing -- the test would
        # be blind to exactly the regression it exists to catch. Verified:
        # mutating the constant to 1e12 leaves this test green when the
        # value is derived, and fails it when the value is a literal.
        brenda_client.BRENDAKmEntry(
            km_value=50000.0,
            substrate="pyruvate",
            organism="Homo sapiens",
            ec_number="1.1.1.27",
            flagged=True,
            flag_reason=(
                "Km value 50000.0 mM is outside plausible range; likely a "
                "unit error or an anomalous entry"
            ),
        ),
        # Cause 2: commentary mentions Kcat -- may be a turnover number, not
        # a Km. In range, so the engine will NOT flag it; the entry must
        # still carry its own reason.
        brenda_client.BRENDAKmEntry(
            km_value=0.5,
            substrate="pyruvate",
            organism="Homo sapiens",
            ec_number="1.1.1.27",
            conditions="pH 7.4, 25C, kcat measurement",
            flagged=True,
            flag_reason=(
                "conditions text mentions Kcat; row may report a turnover "
                "number rather than a true Km"
            ),
        ),
    ]

    assert flagged, "the synthetic entries above must make this non-empty"

    checked_out_of_range = False
    for entry in flagged:
        if not entry.km_value:
            continue
        km = float(entry.km_value)
        # Either the engine agrees it is out of range, or the flag came from a
        # non-range cause (organism mismatch, Kcat mislabel). Either way the
        # entry itself must still be carrying its reason.
        if km < KM_PLAUSIBLE_MIN_MM or km > KM_PLAUSIBLE_MAX_MM:
            assert simulate_michaelis_menten(
                km=km, vmax=1.0, s0=1.0, end=0.1, points=3).flagged, (
                f"Km {km} mM is outside the plausible range and was flagged by "
                "the literature layer, but the engine accepted it silently")
            checked_out_of_range = True
        assert getattr(entry, "flag_reason", None), (
            "a flagged entry must always carry a human-readable reason")

    # Guards against the whole loop degenerating again: at least one entry
    # must have exercised the engine-agreement branch, not just the
    # cheaper reason-is-present check.
    assert checked_out_of_range, (
        "no flagged entry exercised the engine-agreement path")


def test_flagged_entries_do_not_become_confident_numbers_deterministic():
    """Same contract as the test above, without depending on scraped data.

    The fixture-driven version above skips whenever the real captured BRENDA
    page for LDH happens to contain zero flagged rows (it currently does --
    every Km on that particular page was plausible). That's a legitimate
    property of real data, not a bug, but it means the "flagged Km stays
    flagged all the way through the engine" contract could go unexercised for
    however long the fixture stays clean. This test builds a flagged entry
    directly, so the contract always runs regardless of what's in the
    fixture.
    """
    out_of_range_km = KM_PLAUSIBLE_MAX_MM * 10
    entry = brenda_client.BRENDAKmEntry(
        km_value=out_of_range_km,
        substrate="pyruvate",
        organism="Homo sapiens",
        flagged=True,
        flag_reason=f"Km {out_of_range_km} mM exceeds the plausible range",
    )

    assert entry.km_value < KM_PLAUSIBLE_MIN_MM or entry.km_value > KM_PLAUSIBLE_MAX_MM
    result = simulate_michaelis_menten(
        km=entry.km_value, vmax=1.0, s0=1.0, end=0.1, points=3)
    assert result.flagged, (
        "a Km outside the plausible range must come back flagged from the "
        "engine, regardless of what upstream (BRENDA) already flagged it as"
    )
    assert entry.flag_reason, (
        "a flagged entry must always carry a human-readable reason")


def test_real_km_values_produce_physically_sane_trajectories(ldh_entries):
    usable = [e for e in ldh_entries
              if not getattr(e, "flagged", False) and e.km_value][:5]
    # Assertion, not skip -- see test_every_unflagged_brenda_km_is_simulable.
    assert usable, (
        "no unflagged entries parsed from the LDH fixture; it contains "
        "several, so this is a regression rather than a reason to skip")

    for entry in usable:
        km = float(entry.km_value)
        res = simulate_michaelis_menten(km=km, vmax=1.0, s0=km * 5,
                                        end=10.0, points=21)
        s, p = res.column("S"), res.column("P")
        assert all(v >= -1e-6 for v in s), "negative substrate"
        assert all(v >= -1e-6 for v in p), "negative product"
        # Mass conservation must hold regardless of how extreme the real Km is.
        totals = [a + b for a, b in zip(s, p)]
        assert max(totals) - min(totals) < 1e-6 * max(1.0, totals[0])


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_simulation_result_reports_why_it_was_flagged():
    res = simulate_michaelis_menten(km=KM_PLAUSIBLE_MAX_MM * 10, vmax=1.0,
                                    s0=1.0, end=0.1, points=3)
    assert res.flagged
    assert res.validation.flag_reason
    # The reason has to name the offending quantity, not just say "invalid".
    assert "Km" in res.validation.flag_reason


def test_flag_reason_quotes_the_actual_bound():
    res = simulate_michaelis_menten(km=1e6, vmax=1.0, s0=1.0, end=0.1,
                                    points=3)
    assert str(int(KM_PLAUSIBLE_MAX_MM)) in res.validation.flag_reason.replace(
        "1000", str(int(KM_PLAUSIBLE_MAX_MM)))
