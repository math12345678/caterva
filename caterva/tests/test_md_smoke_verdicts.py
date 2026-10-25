"""When the md smoke run may excuse a difference between the two exposure routes' verdicts.

The rows below are constructed to exercise the rule, not measurements: what
matters is where their areas sit relative to the 20% and 40% thresholds.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from caterva.analyze.sasa import BURIED, EXPOSED, Exposure, exposure_verdict, routes_agree_nm2

LARGEST = 1.95  # nm^2, the residue's own reference area, as the smoke run passes it


def _smoke():
    spec = importlib.util.spec_from_file_location(
        "md_smoke", Path(__file__).resolve().parents[2] / "scripts" / "md_smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _differ(rows_n, rows_g, same_verdict=False):
    smoke = _smoke()
    native = {"Asn46": (LARGEST, "partly exposed throughout")}
    gromacs = {"Asn46": (LARGEST, "partly exposed throughout" if same_verdict else "buried in rep1")}
    return smoke._verdicts_differ(native, gromacs, {"Asn46": rows_n}, {"Asn46": rows_g})


def test_equal_verdicts_need_no_excuse():
    assert _differ([0.9, 0.9], [0.9, 0.9], same_verdict=True) == ([], [])


def test_a_pair_of_areas_in_different_states_explains_a_difference():
    below, above = BURIED * LARGEST - 0.01, BURIED * LARGEST + 0.01
    assert _differ([above, above], [below, above]) == (["Asn46"], [])


def test_a_threshold_inside_the_span_explains_a_difference_the_replica_rows_do_not():
    """Every replica-level pair falls in one state, but a frame between the start and the replica mean can
    sit either side of the 20% line on each route: the case a CI run met on a real GROMACS trajectory."""
    edge = BURIED * LARGEST
    rows = [edge + 0.03, edge + 0.01, edge + 0.04]
    assert min(rows) - routes_agree_nm2(max(rows)) <= edge  # the line is inside the span and its allowance
    smoke = _smoke()
    assert smoke.state(round(rows[0] / LARGEST, 2)) == smoke.state(round(rows[2] / LARGEST, 2))
    other_route = [x + 0.004 for x in rows]  # the routes' areas agree only to a tolerance, never exactly
    assert _differ(rows, other_route) == (["Asn46"], [])


def test_a_difference_far_from_both_thresholds_is_still_a_failure():
    middle = (BURIED + EXPOSED) / 2 * LARGEST
    allowance = routes_agree_nm2(middle)
    assert abs(middle - BURIED * LARGEST) > 3 * allowance and abs(middle - EXPOSED * LARGEST) > 3 * allowance
    assert _differ([middle, middle], [middle, middle]) == ([], ["Asn46"])


def test_identical_areas_on_both_routes_near_a_threshold_but_clear_of_its_rounding_edge_explain_nothing():
    """Within the routes' allowance of 20%, so the span would excuse a difference were the areas to differ,
    but every area is more than half a printed unit above 19.5% of the maximum, where the state changes."""
    edge = BURIED * LARGEST
    rows = [edge + 0.03, edge + 0.01, edge + 0.04]
    assert _differ(rows, list(rows)) == ([], ["Asn46"])


def test_areas_printed_alike_either_side_of_the_rounding_edge_explain_a_difference():
    """Every printed pair is equal and in one state, but rep1's 97.5th percentile lies either side of 19.5% of
    the maximum on the two routes (0.3815 and 0.3790 nm^2, both printed 0.38). The verdict judges the share
    rounded to a whole per cent, so rep1 reaches back into the starting state on one route and not the
    other: the md-setup CI job failed on this on 2026-10-24."""
    def verdict(high):
        return exposure_verdict(Exposure("Asn46", "ASN", 0.47, [("rep1", 0.35, 0.02, 0.32, high),
                                                                 ("rep2", 0.40, 0.02, 0.37, 0.44)]))
    native, gromacs = verdict(0.3815), verdict(0.3790)
    assert native != gromacs
    rows = [0.47, 0.35, 0.32, 0.38, 0.40, 0.37, 0.44]  # both routes' areas, as ANALYSIS.md prints them
    smoke = _smoke()
    assert smoke._verdicts_differ({"Asn46": (LARGEST, native)}, {"Asn46": (LARGEST, gromacs)},
                                  {"Asn46": rows}, {"Asn46": list(rows)}) == (["Asn46"], [])


def test_identical_areas_a_printed_unit_from_the_rounding_edge_are_still_unexplained():
    """19.5% and 39.5% of Asn's maximum are 0.380 and 0.770 nm^2. An area printed 0.37 or 0.39, 0.76 or 0.78
    lies within 0.005 nm^2 of its printed value, so wholly on one side of the edge, and on both routes alike."""
    edges = [(share - 0.005) * LARGEST for share in (BURIED, EXPOSED)]
    for printed in (0.37, 0.39, 0.76, 0.78):
        rows = [0.47, 0.35, 0.32, printed, 0.40, 0.37, 0.44]
        assert all(abs(a - edge) > 0.005 for a in rows for edge in edges)
        assert _differ(rows, list(rows)) == ([], ["Asn46"])
