"""`caterva bind`: cited Ki -> the ΔG band a free-energy calculation is judged against.

Offline, against the recorded BRENDA LDH Ki page (Tests/fixtures). The
numbers asserted here are arithmetic on rows in that file, checked by hand:
Ki 1.9 µM at 37 °C is RT ln(1.9e-6) = 0.6163 x -13.173 = -8.12 kcal/mol.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from caterva.bind import core
from caterva.bind.__main__ import main

ROOT = Path(__file__).resolve().parents[2]
KI_PAGE = ROOT / "Tests" / "fixtures" / "brenda_ldh_ki_fixture.html"
QUINOLINE = "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid"


def run(capsys, *args):
    code = main(["--ec", "1.1.1.27", "--organism", "human", "--html", str(KI_PAGE), *args])
    out = capsys.readouterr()
    return code, out.out, out.err


# --- the physics -----------------------------------------------------------

def test_dg_is_rt_ln_ki_over_one_molar_at_the_stated_temperature():
    assert core.kj_to_kcal(core.dg_kj(0.0019, 37.0)) == pytest.approx(-8.12, abs=0.005)
    # 1 mM at 25 °C: RT ln(1e-3) = -4.09 kcal/mol, the textbook anchor.
    assert core.kj_to_kcal(core.dg_kj(1.0, 25.0)) == pytest.approx(-4.09, abs=0.005)


def test_a_tenfold_ki_is_rt_ln10_in_free_energy():
    d = core.dg_kj(0.01, 25.0) - core.dg_kj(0.001, 25.0)
    assert core.kj_to_kcal(d) == pytest.approx(0.5925 * math.log(10), abs=0.002)


def test_no_temperature_gives_a_range_not_a_guess():
    m = core.measurement(0.0019, "gossypol", "Homo sapiens", "711801",
                         "LDH-A, temperature not specified in the publication", None, None)
    assert len(m.dg_kcal) == 2
    assert m.dg_lo == pytest.approx(-8.12, abs=0.005)  # at 37 °C
    assert m.dg_hi == pytest.approx(-7.26, abs=0.01)   # at 4 °C


@pytest.mark.parametrize("text,mode,versus", [
    ("competitive versus NADH, pH 7.5, 37°C", "competitive", "NADH"),
    ("noncompetitive versus pyruvate, pH 7.5", "noncompetitive", "pyruvate"),
    ("non-competitive inhibition", "noncompetitive", None),
    ("uncompetitive vs. lactate, 25°C", "uncompetitive", "lactate"),
    ("mixed-type inhibition versus NAD+", "mixed", "NAD+"),
    # BRENDA's wording, rabbit hexokinase and MgADP- (ref 640206): read as
    # mixed with nothing measured against until "inhibitor" was accepted.
    ("erythrocyte enzyme, mixed inhibitor versus glucose", "mixed", "glucose"),
    ("pH 7.0, 4°C", "unstated", None),
    (None, "unstated", None),
])
def test_the_mode_is_read_from_the_row(text, mode, versus):
    assert core.read_mode(text) == (mode, versus)


# --- which binding event ---------------------------------------------------

def _row(mode_text, ki=0.001, iso=None):
    c = mode_text + (f", {iso}" if iso else "") + ", pH 7.5, 25°C"
    return core.measurement(ki, "X", "Homo sapiens", "1", c, 7.5, 25.0)


def test_an_uncompetitive_ki_cannot_validate_an_apo_simulation():
    t = core.target([_row("uncompetitive versus pyruvate")], "free")
    assert t.lo is None and len(t.excluded) == 1
    assert "ternary" in t.excluded[0].excluded


def test_but_it_can_validate_a_ternary_one():
    t = core.target([_row("uncompetitive versus pyruvate")], "ternary")
    assert t.lo is not None


def test_mixed_inhibition_is_excluded_because_the_row_does_not_say_which_constant():
    t = core.target([_row("mixed-type versus NADH")], "free")
    assert t.lo is None and "which" in t.excluded[0].excluded


def test_isoforms_are_different_proteins():
    rows = [_row("competitive", 0.001, "LDH-A"), _row("competitive", 0.01, "LDH-B")]
    pooled = core.target(rows, "free")
    assert any("isoforms" in c for c in pooled.caveats)
    only_a = core.target(rows, "free", isoform="LDH-A")
    assert [m.isoform for m in only_a.used] == ["LDH-A"]
    assert "LDH-B" in only_a.excluded[0].excluded


# --- the verdict -----------------------------------------------------------

def test_agreement_is_overlap_at_two_sigma():
    t = core.target([_row("competitive", 1.0)], "free")  # 1 mM: -4.09 kcal/mol
    assert core.judge(t, -4.8, 0.4).word == "agrees"       # -4.8 + 0.8 reaches -4.09
    v = core.judge(t, -6.0, 0.3)
    assert v.word == "disagrees"
    assert v.gap_kcal == pytest.approx(-4.09 - (-6.0 + 0.6), abs=0.01)
    assert v.ki_fold == pytest.approx(math.exp(v.gap_kcal / 0.5925), rel=0.01)


@pytest.mark.parametrize("text,expected", [
    ("-7.9", (-7.9, 0.0)), ("-7.9±0.4", (-7.9, 0.4)), ("-7.9+-0.4", (-7.9, 0.4)),
    ("-7.9 +/- 0.4", (-7.9, 0.4)), ("−7.9±0.4", (-7.9, 0.4)), ("-7.9 0.4", (-7.9, 0.4)),
])
def test_computed_values_parse(text, expected):
    assert core.parse_computed(text) == expected


# --- the command, on the recorded page ---------------------------------------

def test_list_names_the_compounds_not_the_molecules_they_compete_with(capsys):
    code, out, _ = run(capsys, "--list")
    assert code == 0
    assert "gossypol" in out and QUINOLINE in out
    assert "NADH" not in out  # named only in a commentary: not an inhibitor row


def test_the_quinoline_band_is_its_two_rows_at_37C_with_the_construct_caveat(capsys):
    code, out, _ = run(capsys, "--inhibitor", QUINOLINE)
    assert code == 0
    assert "-8.84 to -7.95 kcal/mol" in out
    assert "tagged" in out and "one publication" in out


def test_a_simulation_far_too_tight_is_told_by_how_much(capsys):
    code, out, _ = run(capsys, "--inhibitor", QUINOLINE, "--computed", "-10.5±0.3")
    assert code == 4
    assert "binds too tightly" in out and "1.06 kcal/mol" in out


def test_isoform_selects_ldh_a_from_the_gossypol_rows(capsys):
    code, out, _ = run(capsys, "--inhibitor", "gossypol", "--isoform", "LDH-A", "--json")
    data = json.loads(out)
    assert [r["ki_mM"] for r in data["used"]] == [0.0019]
    assert {r["isoform"] for r in data["excluded"]} == {"LDH-B", "LDH-C"}


def test_an_inhibitor_with_no_ki_is_refused_with_what_exists(capsys):
    code, _, err = run(capsys, "--inhibitor", "oxamate")
    assert code == 3
    assert "gossypol" in err


def test_nadh_has_no_ki_row_of_its_own(capsys):
    """The row that once made the website print 0.00059 as oxamate's Ki."""
    code, _, _ = run(capsys, "--inhibitor", "NADH")
    assert code == 3


# --- the survey --------------------------------------------------------------

def test_survey_finds_no_sound_benchmark_among_human_ldh_kis(capsys):
    """The recorded page's answer: every human Ki is one publication."""
    code, out, _ = run(capsys, "--survey")
    assert code == 0
    assert "0 usable as a benchmark" in out
    assert "gossypol [LDH-A]" in out and "gossypol [LDH-B]" in out  # isoforms never pooled


def test_survey_never_pools_species(capsys):
    from caterva.bind.__main__ import survey
    rows = survey(KI_PAGE.read_text(), "1.1.1.27", "", "free")
    gossypol = [(r["organism"], r["isoform"]) for r in rows if r["compound"] == "gossypol"]
    assert len(gossypol) == len(set(gossypol)) == 5
    assert ("Plasmodium falciparum", None) in gossypol


def test_the_benchmark_rule(monkeypatch):
    """Two publications, a stated mode and a stated temperature: then, and
    only then, a benchmark."""
    import caterva.bind.__main__ as cli
    def fake_rows(html, ec, organism, inhibitor):
        return [core.measurement(0.002, "X", "Homo sapiens", "1", "competitive, pH 7.5, 25°C", 7.5, 25.0),
                core.measurement(0.003, "X", "Homo sapiens", "2", "competitive, pH 7.5, 25°C", 7.5, 25.0),
                core.measurement(0.002, "Y", "Homo sapiens", "3", "competitive, pH 7.5, 25°C", 7.5, 25.0),
                core.measurement(0.002, "Y", "Homo sapiens", "4", "pH 7.5", 7.5, None)]
    monkeypatch.setattr(cli, "_rows", fake_rows)
    rows = {r["compound"]: r for r in cli.survey("", "1.1.1.1", "Homo sapiens", "free")}
    assert rows["X"]["benchmark"] and rows["X"]["why_not"] == []
    assert not rows["Y"]["benchmark"]
    assert set(rows["Y"]["why_not"]) == {"mode not stated", "temperature not stated"}
