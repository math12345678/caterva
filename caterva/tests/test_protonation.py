"""Which active-site residues have an uncertain charge at the assay pH.

The survey values are from the abstract of Grimsley, Scholtz & Pace (2009)
Protein Sci. 18:247 (doi:10.1002/pro.19), read from PubMed on 2026-09-29.
Henderson-Hasselbalch checked by hand: His (pKa 6.6) at pH 7.5 is
1 / (1 + 10^0.9) = 0.112 protonated; at pKa 7.6, 1 / (1 + 10^-0.1) = 0.557.
"""
from __future__ import annotations

import pytest

from caterva.prepare import protonation as pr
from caterva.prepare.audit import Audit, TitratableSite
from caterva.prepare.__main__ import protonation_section


def test_the_survey_values_are_the_papers():
    assert pr.PKA == {
        "ASP": (3.5, 1.2, 139), "GLU": (4.2, 0.9, 153), "HIS": (6.6, 1.0, 131), "CYS": (6.8, 2.7, 25),
        "TYR": (10.3, 1.2, 20), "LYS": (10.5, 1.1, 35), "CTERM": (3.3, 0.8, 22), "NTERM": (7.7, 0.5, 16),
    }


def test_henderson_hasselbalch_by_hand():
    assert pr.fraction_protonated(7.5, 6.6) == pytest.approx(0.112, abs=1e-3)
    assert pr.fraction_protonated(7.5, 7.6) == pytest.approx(0.557, abs=1e-3)
    assert pr.fraction_protonated(4.0, 4.0) == pytest.approx(0.5)


@pytest.mark.parametrize("group,ph,settled", [
    ("ASP", 7.5, False), ("GLU", 7.5, False), ("LYS", 7.5, True), ("TYR", 7.5, True),
    ("HIS", 7.5, None), ("CYS", 7.5, None), ("ASP", 3.0, None), ("HIS", 3.0, True), ("ASP", 1.0, True),
])
def test_settled_or_uncertain(group, ph, settled):
    assert pr.assess(group, ph).settled is settled


def test_a_default_that_contradicts_typical_behaviour_is_caught():
    # At pH 1 every Asp is protonated; pdb2gmx would still leave it charged.
    assert pr.assess("ASP", 1.0).default_contradicted
    assert not pr.assess("ASP", 7.5).default_contradicted
    # His has no fixed default: pdb2gmx follows hydrogen bonds, so it is never "contradicted".
    assert pr.assess("HIS", 3.0).default_protonated is None
    assert not pr.assess("HIS", 3.0).default_contradicted


def test_arginine_is_not_assessed():
    assert pr.assess("ARG", 7.5) is None


def _audit(sites):
    return Audit("TEST", "t", "X-RAY", 2.0, 0.2, ["A"], [], [], None, [], [], sites)


def test_the_report_names_uncertain_and_wrong_residues():
    sites = [TitratableSite("A", "192", "HIS", 0.0, True), TitratableSite("A", "165", "ASP", 0.0, True),
             TitratableSite("A", "105", "ARG", 0.0, True)]
    text = "\n".join(protonation_section(_audit(sites), 7.5))
    assert "His192 (catalytic)" in text and "**uncertain**" in text
    assert "Arg is not in the survey" in text and "10.1002/pro.19" in text
    at_one = "\n".join(protonation_section(_audit(sites), 1.0))
    assert "Set these by hand" in at_one and "Asp165" in at_one


def test_without_a_ph_it_asks_for_one():
    text = "\n".join(protonation_section(_audit([TitratableSite("A", "192", "HIS", 0.0, True)]), None))
    assert "Pass --ph" in text
