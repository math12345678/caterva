"""Caterva Studio's `bind` kind against `caterva bind`, on BRENDA's LDH Ki page.

The command reads the page with `--html`; the studio reads it through the
fetch the command makes without one, which here serves the same committed
file (studio_kinetics_offline.ldh_ki_page_offline). For each mode the
studio's report is the command's stdout, the exit code is the command's,
and every number is the unrounded one the command formatted: each Ki row
as BRENDA gives it with its reference, its ΔG°bind from bind.core, the
band's edges, and with a computed value the gap and the Ki fold the
verdict printed. The quinoline sulfonamide of BRENDA ref 739793 (0.00059
and 0.00252 mM at 37 °C) is the main case, as in caterva/tests/test_bind.py.
"""
from __future__ import annotations

import pytest

from caterva.bind import core
from caterva.bind.__main__ import _rows, assess, main, survey_targets
from caterva.studio import contract
from caterva.studio.adapters import bind as adapter
from studio_kinetics_offline import LDH_KI_PAGE, QUINOLINE, Recorder, context, ldh_ki_page_offline, run_cli

BASE = {"ec": "1.1.1.27", "organism": "human"}


def cli(*args):
    return run_cli(main, ["--ec", "1.1.1.27", "--organism", "human", "--html", str(LDH_KI_PAGE), *args])


def studio(request, tmp_path, progress=None):
    with ldh_ki_page_offline():
        return adapter.run(request, context(tmp_path, progress))


def test_the_quinoline_target_matches_the_command(tmp_path):
    code, out, _ = cli("--inhibitor", QUINOLINE)
    progress = Recorder()
    outcome = studio({**BASE, "mode": "inhibitor", "inhibitor": QUINOLINE}, tmp_path, progress)
    assert outcome.exit_code == code == 0
    assert outcome.result["report_text"] + "\n" == out
    assert progress.stages() == ["fetch", "rows", "target"]
    target = outcome.result["target"]
    html = LDH_KI_PAGE.read_text(encoding="utf-8")
    t = core.target(_rows(html, "1.1.1.27", "Homo sapiens", QUINOLINE), "free")
    assert [row["ki"]["value"] for row in target["used"]] == [m.ki_mM for m in t.used]
    assert sorted(m.ki_mM for m in t.used) == [0.00059, 0.00252]
    assert target["band_low"]["value"] == t.lo and target["band_high"]["value"] == t.hi
    assert f"{t.lo:.2f} to {t.hi:.2f} kcal/mol" in out
    for row, m in zip(target["used"], t.used):
        ki = row["ki"]["provenance"]
        assert ki["kind"] == "measured" and ki["citation"]["reference_id"] == m.reference == "739793"
        assert ki["citation"]["text"] == "BRENDA ref 739793"
        assert ki["citation"]["url"] == "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27"
        assert ki["commentary"] == m.commentary and ki["conditions"]["temperature_c"] == m.temperature_c
        assert row["dg"]["value"] == m.dg_kcal[0]
        assert row["dg"]["provenance"]["kind"] == "computed"
        assert row["dg"]["provenance"]["inputs"] == [row["ki"]["id"]]
    assert outcome.result["verdict"] is None


def test_a_computed_value_far_too_tight_is_a_negative_finding(tmp_path):
    code, out, _ = cli("--inhibitor", QUINOLINE, "--computed", "-10.5±0.3")
    request = {**BASE, "mode": "inhibitor", "inhibitor": QUINOLINE, "computed": {"value": -10.5, "error": 0.3}}
    progress = Recorder()
    outcome = studio(request, tmp_path, progress)
    assert outcome.exit_code == code == 4
    assert outcome.result["report_text"] + "\n" == out
    assert progress.stages()[-1] == "judge"
    html = LDH_KI_PAGE.read_text(encoding="utf-8")
    a = assess(_rows(html, "1.1.1.27", "Homo sapiens", QUINOLINE), "free", (-10.5, 0.3), "kcal")
    verdict = outcome.result["verdict"]
    assert verdict["word"] == a.verdict.word == "disagrees"
    assert verdict["gap_kcal"]["value"] == a.verdict.gap_kcal
    assert verdict["ki_fold"]["value"] == a.verdict.ki_fold
    assert verdict["temperature_c"]["value"] == a.temperature_c == 37.0
    assert verdict["temperature_c"]["provenance"]["kind"] == "computed"
    assert verdict["computed"]["value"] == -10.5 and verdict["computed"]["provenance"]["by"] == "user"
    assert verdict["computed_error"]["value"] == 0.3
    assert outcome.summary.startswith("VERDICT  DISAGREES")


def test_a_computed_value_in_kj_is_judged_in_kcal_as_the_command_judges_it(tmp_path):
    code, out, _ = cli("--inhibitor", QUINOLINE, "--computed", "-35.0±1.0", "--unit", "kj")
    outcome = studio({**BASE, "mode": "inhibitor", "inhibitor": QUINOLINE,
                      "computed": {"value": -35.0, "error": 1.0, "unit": "kj"}}, tmp_path)
    assert outcome.exit_code == code
    assert outcome.result["report_text"] + "\n" == out
    assert outcome.result["verdict"]["computed"]["value"] == -35.0 / core.KJ_PER_KCAL


def test_the_isoform_selects_the_rows_the_command_selects(tmp_path):
    code, out, _ = cli("--inhibitor", "gossypol", "--isoform", "LDH-A")
    outcome = studio({**BASE, "mode": "inhibitor", "inhibitor": "gossypol", "isoform": "LDH-A"}, tmp_path)
    assert outcome.exit_code == code and outcome.result["report_text"] + "\n" == out
    assert [r["ki"]["value"] for r in outcome.result["target"]["used"]] == [0.0019]
    assert {r["isoform"] for r in outcome.result["target"]["excluded"]} == {"LDH-B", "LDH-C"}


def test_list_matches_the_command(tmp_path):
    code, out, _ = cli("--list")
    outcome = studio({**BASE, "mode": "list"}, tmp_path)
    assert outcome.exit_code == code == 0
    assert outcome.result["report_text"] + "\n" == out
    assert "gossypol" in outcome.result["compounds"] and QUINOLINE in outcome.result["compounds"]


def test_survey_matches_the_command_with_the_band_unrounded(tmp_path):
    code, out, _ = cli("--survey")
    outcome = studio({**BASE, "mode": "survey"}, tmp_path)
    assert outcome.exit_code == code == 0
    assert outcome.result["report_text"] + "\n" == out
    html = LDH_KI_PAGE.read_text(encoding="utf-8")
    targets = survey_targets(html, "1.1.1.27", "Homo sapiens", "free")
    rows = outcome.result["survey"]
    assert [(r["compound"], r["isoform"]) for r in rows] == [(t.compound, t.isoform) for t in targets]
    for row, t in zip(rows, targets):
        assert (row["band_low"] or {}).get("value") == t.target.lo
        assert row["benchmark"] == (not t.why_not) and row["why_not"] == t.why_not
    assert not any(r["benchmark"] for r in rows)


def test_an_inhibitor_with_no_ki_is_refused_in_the_commands_words(tmp_path):
    code, out, err = cli("--inhibitor", "NADH")
    outcome = studio({**BASE, "mode": "inhibitor", "inhibitor": "NADH"}, tmp_path)
    assert outcome.exit_code == code == 3 and out == ""
    assert outcome.result is None
    assert outcome.refusal == err.rstrip("\n")


def test_no_row_for_the_state_is_refused_with_the_other_state_suggested(tmp_path):
    html = LDH_KI_PAGE.read_text(encoding="utf-8")
    t = core.target(_rows(html, "1.1.1.27", "Homo sapiens", QUINOLINE), "ternary")
    code, out, _ = cli("--inhibitor", QUINOLINE, "--state", "ternary")
    outcome = studio({**BASE, "mode": "inhibitor", "inhibitor": QUINOLINE, "state": "ternary"}, tmp_path)
    assert outcome.exit_code == code
    assert outcome.result["report_text"] + "\n" == out
    if t.lo is None:
        assert code == 3 and "REFUSED" in outcome.refusal
        assert outcome.result["target"]["band_low"] is None
    else:
        assert code == 0 and outcome.result["target"]["band_low"]["value"] == t.lo


def test_an_unreadable_page_is_a_refusal_not_a_crash(tmp_path):
    with ldh_ki_page_offline():
        outcome = adapter.run({"ec": "9.9.9.9", "mode": "list"}, context(tmp_path))
    assert outcome.exit_code == 3 and outcome.result is None
    assert outcome.refusal.startswith("caterva bind: could not read BRENDA for 9.9.9.9:")


def test_argv_uses_the_equals_form_so_a_negative_value_is_not_a_flag():
    argv = adapter.argv({**BASE, "mode": "inhibitor", "inhibitor": "gossypol",
                         "computed": {"value": -7.9, "error": 0.4}})
    assert "--computed=-7.9±0.4" in argv
    assert not any(a.startswith(("--html", "--json")) for a in argv)
    assert adapter.argv({**BASE, "mode": "survey"})[-1] == "--survey"


@pytest.mark.parametrize("request_, field", [
    ({"mode": "list"}, "ec"),
    ({**BASE, "mode": "everything"}, "mode"),
    ({**BASE, "mode": "inhibitor"}, "inhibitor"),
    ({**BASE, "mode": "list", "inhibitor": "x"}, "inhibitor"),
    ({**BASE, "mode": "inhibitor", "inhibitor": "x", "computed": {"value": "low"}}, "computed.value"),
    ({**BASE, "mode": "list", "html": "/tmp/x"}, "html"),
])
def test_a_malformed_request_names_its_field(request_, field):
    with pytest.raises(contract.Malformed) as caught:
        adapter.argv(request_)
    assert caught.value.field == field


def test_the_parser_refuses_what_the_command_refuses():
    with pytest.raises(contract.Malformed) as caught:
        adapter.argv({**BASE, "mode": "inhibitor", "inhibitor": "x", "state": "bound"})
    assert "invalid choice: 'bound'" in str(caught.value)
    with pytest.raises(contract.Malformed) as caught:
        adapter.argv({**BASE, "mode": "inhibitor", "inhibitor": "x", "computed": {"value": 1.0, "unit": "ev"}})
    assert "invalid choice: 'ev'" in str(caught.value)
