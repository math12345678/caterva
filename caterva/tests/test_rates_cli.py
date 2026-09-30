"""`caterva rates` end to end: the command, its outputs, its refusals, and the literature.

WHAT RUNS OFFLINE, AND ON WHAT
------------------------------
The literature comparison asks the literature layer's resolver
(Tests/fallback_logic.py, resolve_kinetic_value) exactly as the command does,
with BRENDA's page for lactate dehydrogenase (1.1.1.27) read from the
committed, unmodified copy in Tests/fixtures/ki_mode/ (fetched 2026-09-29;
its README has the hash) instead of the network, and UniProt and NCBI stubbed
as Tests/test_ki_mode_resolution.py stubs them. Human LDH's cited pyruvate Km
there is 0.03 mM (BRENDA ref 286469), and the quinoline sulfonamide of ref
739793 has 0.00059 mM "competitive versus NADH" and 0.00252 mM
"noncompetitive versus pyruvate".

The rates those comparisons are made with are SYNTHETIC, generated from a
rate law at stated constants with seeded noise, to check that the comparison
RECOVERS a known relation: rates made at the cited constants must come out
inside the fitted interval with a ratio near 1, and rates made at four times
the cited Ki must come out outside it with a ratio near 4. They are not
measurements, and no synthetic number appears in an example or a document.
The puromycin file is real (test_rates_puromycin.py says whose).
"""
from __future__ import annotations

import csv
import functools
import gzip
import io
import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import numpy as np
import pytest

from caterva.rates.__main__ import main
from caterva.rates.linearize import WHY
from caterva.rates.models import law_for

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "rates" / "puromycin.csv"
LDH_PAGE = REPO / "Tests" / "fixtures" / "ki_mode" / "brenda_1.1.1.27.html.gz"
QUINOLINE = "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid"
#: The cited values on the committed page (module docstring), in mM.
CITED_KM = 0.03
CITED_KI_COMPETITIVE = 0.00059
CITED_KI_NONCOMPETITIVE = 0.00252


def run(argv, **kw):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = main(argv, **kw)
        except SystemExit as exc:  # argparse
            code = exc.code
    return code, out.getvalue(), err.getvalue()


@functools.lru_cache(maxsize=1)
def _ldh_html():
    # errors="replace": the page carries six Latin-1 bytes (the README says
    # which), and a live fetch through requests decodes them the same way.
    return gzip.decompress(LDH_PAGE.read_bytes()).decode("utf-8", errors="replace")


def offline_resolver(ec, organism, compound, **kw):
    from caterva.checkout import literature_module

    resolve = literature_module("fallback_logic").resolve_kinetic_value
    pages = {"1.1.1.27": _ldh_html()}
    return resolve(ec, organism, compound, html_provider=pages.__getitem__,
                   uniprot_provider=lambda ec_, org: None,
                   taxon_id_provider={"Homo sapiens": "9606"}.get, search_literature=False, **kw)


def synthetic_inhibition(tmp_path, name, *, km_uM=30.0, ki_nM=590.0, kip_nM=2000.0, seed=1):
    """SYNTHETIC rates (module docstring): `name`'s law at the given constants,
    substrate in uM and inhibitor in nM, so the comparison has units to convert."""
    law = law_for(name)
    s, i = np.meshgrid([5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 320.0], [0.0, 300.0, 900.0, 2700.0])
    s, i = np.repeat(s.ravel(), 2), np.repeat(i.ravel(), 2)
    constants = {"Vmax": 10.0, "Km": km_uM, "Ki": ki_nM, "Ki_prime": kip_nM}
    v = law.rate(constants, s, i)
    sd = 0.03 * v + 0.02
    observed = v + sd * np.random.default_rng(seed).standard_normal(len(v))
    path = tmp_path / f"synthetic-{name}.csv"
    lines = ["# SYNTHETIC rates for a test; not a measurement",
             "substrate (uM),inhibitor (nM),rate (uM/min),sigma (uM/min)"]
    lines += [f"{float(a)!r},{float(b)!r},{float(c)!r},{float(d)!r}"
              for a, b, c, d in zip(s, i, observed, sd)]
    path.write_text("\n".join(lines) + "\n")
    return path


LDH = ["--ec", "1.1.1.27", "--organism", "human", "--substrate", "pyruvate",
       "--inhibitor", QUINOLINE]


# ---------------------------------------------------------------------------
# The example, end to end
# ---------------------------------------------------------------------------


def test_the_example_through_the_app_executable():
    proc = subprocess.run(
        [sys.executable, "-m", "caterva.app", "rates", str(EXAMPLE), "--sigma-from", "residuals",
         "--group", "state", "--model", "michaelis-menten"],
        cwd=REPO, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert out.index("## Verdict") < out.index("## The data") < out.index("## Michaelis-Menten")
    assert "| Vmax | 212.7 | 6.947 | 197.3 to 229.3 | counts/min/min |" in out
    assert "| Km | 0.06412 | 0.008281 | 0.04692 to 0.08616 | ppm |" in out
    assert "Residual standard error 10.93 counts/min/min on 10 degrees of freedom" in out
    assert "No goodness-of-fit chi-square is given" in out
    assert "| Km | F(1, 19) = 1.718 | 0.206 | no difference detected |" in out
    assert "Vmax differs between treated and untreated" in out


def test_json_carries_every_number_the_report_prints():
    code, out, _ = run([str(EXAMPLE), "--sigma-from", "residuals", "--group", "state", "--json"])
    assert code == 0
    doc = json.loads(out)
    assert doc["uncertainty"]["source"] == "residuals"
    treated = next(r for r in doc["results"] if r["group"] == "treated")
    mm = next(law for law in treated["laws"] if law["law"] == "michaelis-menten")
    km = next(c for c in mm["constants"] if c["constant"] == "Km")
    assert km["estimate"] == pytest.approx(0.06412128, rel=1e-5)
    assert km["low"] == pytest.approx(0.04692, rel=1e-3) and km["determined"] is True
    assert mm["chi_square"] is None and mm["residual_standard_error"] == pytest.approx(10.9337, rel=1e-4)
    assert {t["restricted"] for t in treated["tests"]} == {"michaelis-menten"}
    assert doc["groups"]["law"] == "michaelis-menten"
    assert any(t["shared"] == "Km" and not t["differs"] for t in doc["groups"]["tests"])
    assert doc["verdict"]


def test_the_csv_export_is_one_table_with_units():
    code, out, _ = run([str(EXAMPLE), "--sigma-from", "residuals", "--group", "state",
                        "--model", "michaelis-menten", "--export", "csv"])
    assert code == 0
    rows = list(csv.DictReader(io.StringIO(out)))
    assert "low (95% profile)" in rows[0]
    km = next(r for r in rows if r["group"] == "treated" and r["constant"] == "Km")
    assert km["unit"] == "ppm" and km["determined"] == "yes" and km["reported"] == "yes"
    assert float(km["estimate"]) == pytest.approx(0.06412128, rel=1e-5)
    shared = next(r for r in rows if r["group"] == "shared Km" and r["constant"] == "Km")
    assert float(shared["estimate"]) == pytest.approx(0.05797157, rel=1e-5)


def test_the_curves_export_has_one_row_per_point_and_units_in_the_headers():
    code, out, _ = run([str(EXAMPLE), "--sigma-from", "residuals", "--group", "state",
                        "--model", "michaelis-menten", "--export", "curves"])
    assert code == 0
    reader = csv.reader(io.StringIO(out))
    header = next(reader)
    assert header[:5] == ["kind", "group", "law", "substrate (ppm)", "rate (counts/min/min)"]
    assert "asymptotic" in header[5] and header[5].endswith("(counts/min/min)")
    rows = list(reader)
    assert sum(r[0] == "fit" for r in rows) == 2 * 60
    assert sum(r[0] == "measured" for r in rows) == 23
    # The curve is the fit: at the grid's top the treated curve is Vmax S / (Km + S).
    top = [r for r in rows if r[0] == "fit" and r[1] == "treated"][-1]
    s = float(top[3])
    assert float(top[4]) == pytest.approx(212.683743 * s / (0.0641212820 + s), rel=1e-6)
    assert float(top[5]) < float(top[4]) < float(top[6])


def test_the_methods_paragraph_names_the_method_and_the_software():
    import numpy
    import scipy

    code, out, _ = run([str(EXAMPLE), "--sigma-from", "residuals", "--group", "state",
                        "--export", "methods"])
    assert code == 0
    assert "profile-likelihood intervals (Bates & Watts 1988)" in out
    assert "estimated from the residuals" in out
    assert f"NumPy {numpy.__version__}, SciPy {scipy.__version__}" in out
    assert "Self & Liang 1987" in out and "Draper & Smith" in out


def test_the_straight_line_plots_are_printed_beside_the_fit_and_computed_independently():
    code, out, _ = run([str(EXAMPLE), "--sigma-from", "residuals", "--group", "state",
                        "--model", "michaelis-menten", "--show-linearizations"])
    assert code == 0
    assert WHY in out
    conc = np.array([0.02, 0.02, 0.06, 0.06, 0.11, 0.11, 0.22, 0.22, 0.56, 0.56, 1.10, 1.10])
    rate = np.array([76, 47, 97, 107, 123, 139, 159, 152, 191, 201, 207, 200], dtype=float)
    slope, intercept = np.polyfit(1 / conc, 1 / rate, 1)
    vmax, km = 1 / intercept, slope / intercept
    treated = out[out.index("### [treated] [I] = 0"):]
    line = next(x for x in treated.splitlines() if x.startswith("| Lineweaver-Burk"))
    assert f"| {vmax:.4g} | {km:.4g} |" in line
    assert "| nonlinear fit (michaelis-menten) | | | | 212.7 | 0.06412 |" in treated


def test_the_app_dispatches_to_the_command():
    from caterva.app import COMMANDS, main as app_main

    assert COMMANDS["rates"][0] == "caterva.rates.__main__"
    out = io.StringIO()
    with redirect_stdout(out):
        with pytest.raises(SystemExit) as exc:
            app_main(["rates", "--help"])
    assert exc.value.code == 0
    assert "--sigma-from" in out.getvalue() and "caterva rates" in out.getvalue()


# ---------------------------------------------------------------------------
# Refusals, each with its exit code
# ---------------------------------------------------------------------------


def test_no_uncertainty_is_refused_with_the_three_options(tmp_path):
    path = tmp_path / "rates.csv"
    path.write_text("substrate (mM),rate (uM/min)\n0.1,1\n0.2,2\n0.4,3\n")
    code, out, err = run([str(path)])
    assert code == 3 and out == ""
    assert "--sigma-from replicates" in err and "--sigma-from residuals" in err
    assert "sigma (uM/min)" in err


def test_a_unit_it_cannot_parse_is_refused_naming_the_column(tmp_path):
    path = tmp_path / "rates.csv"
    path.write_text("substrate (mM),rate (uM/mn)\n0.1,1\n")
    code, _, err = run([str(path), "--sigma-from", "residuals"])
    assert code == 3 and "'uM/mn' of column 'rate'" in err


def test_a_group_with_one_rate_is_refused(tmp_path):
    path = tmp_path / "rates.csv"
    path.write_text("substrate (mM),rate (uM/min),strain\n0.1,1,wt\n0.2,2,wt\n0.4,3,wt\n0.8,4,wt\n"
                    "0.1,1,mutant\n")
    code, _, err = run([str(path), "--sigma-from", "residuals", "--group", "strain"])
    assert code == 3 and "group 'mutant' has 1 row(s)" in err


def test_too_few_conditions_for_the_law_is_refused(tmp_path):
    path = tmp_path / "rates.csv"
    path.write_text("substrate (mM),rate (uM/min)\n0.1,1\n0.1,1.2\n0.1,0.9\n")
    code, _, err = run([str(path), "--sigma-from", "residuals", "--model", "michaelis-menten"])
    assert code == 3 and "1 distinct condition" in err


def test_malformed_questions_exit_2(tmp_path):
    path = tmp_path / "rates.csv"
    path.write_text("conc (mM),rate (uM/min)\n0.1,1\n")
    assert run([str(path), "--sigma-from", "residuals"])[0] == 2
    assert run([str(EXAMPLE), "--sigma-from", "sideways"])[0] == 2
    code, _, err = run([str(EXAMPLE), "--sigma-from", "residuals", "--ec", "1.1.1.27",
                        "--substrate", "x"])
    assert code == 2 and "--organism" in err
    code, _, err = run([str(EXAMPLE), "--sigma-from", "residuals", "--json", "--export", "csv"])
    assert code == 2
    code, _, err = run([str(EXAMPLE), "--sigma-from", "residuals", "--level", "95"])
    assert code == 2 and "0.95, not 95" in err
    assert run([str(tmp_path / "missing.csv"), "--sigma-from", "residuals"])[0] == 2


def test_an_inhibition_law_on_rates_without_inhibitor_is_refused():
    code, _, err = run([str(EXAMPLE), "--sigma-from", "residuals", "--model", "competitive"])
    assert code == 3 and "needs rates measured with an inhibitor" in err


# ---------------------------------------------------------------------------
# The literature, offline on the committed LDH page
# ---------------------------------------------------------------------------


def test_rates_made_at_the_cited_constants_come_back_inside_the_interval(tmp_path):
    path = synthetic_inhibition(tmp_path, "competitive", km_uM=CITED_KM * 1000,
                                ki_nM=CITED_KI_COMPETITIVE * 1e6)
    code, out, err = run([str(path), "--json"] + LDH, resolver=offline_resolver)
    assert code == 0, err
    doc = json.loads(out)
    assert doc["results"][0]["reported"] == ["competitive"]
    km, ki = doc["literature"]
    assert km["constant"] == "Km" and km["brenda_reference"] == "286469"
    assert km["cited"] == CITED_KM and km["cited_unit"] == "mM"
    assert km["contains_cited"] is True and km["ratio_fitted_to_cited"] == pytest.approx(1, abs=0.1)
    # The fitted Km was in uM; the comparison is in the cited mM.
    assert km["fitted_in_cited_unit"]["estimate"] == pytest.approx(CITED_KM, rel=0.1)
    assert km["spread"] == [0.03, 0.398] and km["equally_evidenced_rows"] == 2
    assert ki["constant"] == "Ki" and ki["mode"] == "competitive"
    assert ki["brenda_reference"] == "739793" and ki["cited"] == CITED_KI_COMPETITIVE
    assert ki["contains_cited"] is True and ki["ratio_fitted_to_cited"] == pytest.approx(1, abs=0.1)
    concerns = " ".join(ki["concerns"])
    assert "versus NADH" in concerns and "His-tagged" in concerns
    evidence = ki["evidence_against_mechanism"]
    assert "noncompetitive inhibition versus pyruvate" in evidence
    # These synthetic rates rule noncompetitive out, and the report says the
    # cited row and this experiment disagree about the mechanism itself.
    assert "rule noncompetitive inhibition out" in evidence


def test_the_resolver_is_asked_as_compose_asks_it(tmp_path):
    """Km under the substrate; Ki under the INHIBITOR, with the mode the data
    chose, the model's substrate and the isoform -- the arguments
    compose/narrowed.py relies on the resolver having been given."""
    calls = []

    def recording(ec, organism, compound, **kw):
        calls.append((ec, organism, compound, kw))
        return offline_resolver(ec, organism, compound, **kw)

    path = synthetic_inhibition(tmp_path, "competitive", km_uM=CITED_KM * 1000,
                                ki_nM=CITED_KI_COMPETITIVE * 1e6)
    code, _, err = run([str(path), "--isoform", "LDH-A"] + LDH, resolver=recording)
    assert code == 0, err
    assert calls == [
        ("1.1.1.27", "Homo sapiens", "pyruvate", {"quantity": "km", "isoform": "LDH-A"}),
        ("1.1.1.27", "Homo sapiens", QUINOLINE,
         {"quantity": "ki", "isoform": "LDH-A", "inhibition_mode": "competitive",
          "model_substrate": "pyruvate"}),
    ]


def test_rates_made_at_four_times_the_cited_ki_come_back_outside_it(tmp_path):
    path = synthetic_inhibition(tmp_path, "competitive", km_uM=CITED_KM * 1000,
                                ki_nM=4 * CITED_KI_COMPETITIVE * 1e6)
    code, out, _ = run([str(path)] + LDH, resolver=offline_resolver)
    assert code == 0
    line = next(x for x in out.splitlines() if x.startswith("- Literature: Ki, competitive"))
    assert "OUTSIDE the fitted interval" in line
    ratio = float(line.split("ratio fitted/cited ")[1].split(";")[0].rstrip("."))
    assert ratio == pytest.approx(4, rel=0.1)


def test_a_noncompetitive_fit_is_compared_with_the_noncompetitive_row(tmp_path):
    path = synthetic_inhibition(tmp_path, "noncompetitive", ki_nM=CITED_KI_NONCOMPETITIVE * 1e6)
    code, out, _ = run([str(path), "--json"] + LDH, resolver=offline_resolver)
    assert code == 0
    doc = json.loads(out)
    assert doc["results"][0]["reported"] == ["noncompetitive"]
    ki = next(c for c in doc["literature"] if c["constant"] == "Ki")
    assert ki["mode"] == "noncompetitive" and ki["cited"] == CITED_KI_NONCOMPETITIVE
    assert ki["commentary"].endswith("noncompetitive versus pyruvate")
    assert ki["contains_cited"] is True


def test_an_uncompetitive_fit_finds_no_row_of_its_mode_and_says_which_modes_there_are(tmp_path):
    path = synthetic_inhibition(tmp_path, "uncompetitive")
    code, out, _ = run([str(path), "--json"] + LDH, resolver=offline_resolver)
    assert code == 0  # the search ran and answered: no row of this mode
    doc = json.loads(out)
    ki = next(c for c in doc["literature"] if c["constant"] == "Ki'")
    assert ki["found"] is False and ki["resolver_source"] == "mode_withheld"
    assert "competitive inhibition versus NADH" in ki["refused"]


def test_a_mixed_fit_is_not_matched_to_a_single_row(tmp_path):
    path = synthetic_inhibition(tmp_path, "mixed", seed=5)
    code, out, err = run([str(path), "--json"] + LDH, resolver=offline_resolver)
    doc = json.loads(out)
    assert doc["results"][0]["reported"] == ["mixed"]
    ki = next(c for c in doc["literature"] if c["law"] == "mixed" and c["constant"] == "Ki")
    assert "does not say which one it measured" in ki["refused"]
    assert code == 3 and "Ki" in err


def test_an_arbitrary_unit_declines_the_comparison_by_name():
    code, out, err = run([str(EXAMPLE), "--sigma-from", "residuals", "--group", "state",
                          "--model", "michaelis-menten", "--ec", "2.4.1.22", "--organism", "rat",
                          "--substrate", "glucose"],
                         resolver=lambda *a, **k: pytest.fail("no search for an unconvertible unit"))
    assert code == 3
    assert "'ppm', which cannot be converted to a molar concentration" in out
    assert "a literature comparison was not made" in err


def test_without_the_literature_layer_the_fit_is_reported_and_the_comparison_refused(
        tmp_path, monkeypatch):
    import caterva.checkout as checkout

    def absent(name):
        raise checkout.LiteratureLayerUnavailable(
            f"{name!r} is part of Caterva's literature layer, which is not shipped in the app folder")

    monkeypatch.setattr(checkout, "literature_module", absent)
    path = synthetic_inhibition(tmp_path, "competitive")
    code, out, err = run([str(path)] + LDH)
    assert code == 3
    assert "## Verdict" in out and "Competitive inhibition" in out
    assert "not shipped in the app folder" in out and "not shipped in the app folder" in err
