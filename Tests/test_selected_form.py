"""Tests for `form_mixture.name_selected_form`.

The corpus test at the end is the one that matters: it runs the real
detector over the real hexokinase pool and asserts the returned value is
named as the form it actually is. Hand-built mixtures can pass while the
function is useless on the real thing.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from form_mixture import FormMixture, find_form_mixtures, name_selected_form


def mixture(base: str, values_by_form: dict[str, list[float]]) -> FormMixture:
    return FormMixture(
        base=base,
        values_by_form=values_by_form,
        reason="(fixture)",
    )


# ---------------------------------------------------------------------------
# When there is nothing to say
# ---------------------------------------------------------------------------

def test_no_mixture_is_not_a_finding():
    assert name_selected_form([], 0.5) is None
    assert name_selected_form(None, 0.5) is None


def test_no_selected_value_is_not_a_finding():
    m = mixture("hexokinase", {"I": [0.5], "Ia": [0.77]})
    assert name_selected_form([m], None) is None


def test_a_value_from_no_named_form_is_not_a_finding():
    """The ordinary good case: the pool mixed forms and the answer did not
    come from one of them. That is the outcome the warning hoped for, and
    reporting it would invert the finding."""
    m = mixture("hexokinase", {"I": [0.5], "Ia": [0.77]})
    assert name_selected_form([m], 1.23) is None


def test_a_value_appearing_under_two_forms_yields_none():
    """Two forms reporting the same number is a coincidence this function
    cannot resolve. Naming one would invent the distinction the module
    exists to preserve."""
    m = mixture("LDH", {"1": [1500.0], "2": [1500.0]})
    assert name_selected_form([m], 1500.0) is None


# ---------------------------------------------------------------------------
# The case this exists for
# ---------------------------------------------------------------------------

def test_it_names_the_form_the_value_came_from():
    m = mixture("hexokinase", {"I": [0.5], "Ia": [0.77], "Ib": [0.56]})
    found = name_selected_form([m], 0.5)
    assert found is not None
    assert found.base == "hexokinase"
    assert found.designator == "I"
    assert found.label == "hexokinaseI"


def test_it_lists_the_siblings_so_one_of_three_is_checkable():
    m = mixture("hexokinase", {"I": [0.5], "Ia": [0.77], "Ib": [0.56]})
    found = name_selected_form([m], 0.5)
    assert found.sibling_designators == ["I", "Ia", "Ib"]
    assert "3 forms" in found.reason
    assert "hexokinaseIa" in found.reason


def test_the_reason_says_the_warning_was_not_hypothetical():
    """The whole point. `FormMixture.reason` says returning the lowest
    *would* pick a form; this says it did."""
    m = mixture("hexokinase", {"I": [0.5], "Ia": [0.77]})
    found = name_selected_form([m], 0.5)
    assert "not hypothetical" in found.reason
    assert "a form was" in found.reason


def test_the_reason_says_the_request_did_not_ask_for_that_form():
    m = mixture("LDH", {"1": [1500.0], "B": [142.0]})
    found = name_selected_form([m], 142.0)
    assert "did not ask for LDHB" in found.reason
    assert "different gene product" in found.reason


def test_a_single_form_mixture_does_not_claim_a_sibling():
    # Defensive: a one-designator mixture should not produce
    # "and LDH is a different gene product" with an empty name.
    m = mixture("LDH", {"B": [142.0]})
    found = name_selected_form([m], 142.0)
    assert found is not None
    assert "different gene product" not in found.reason


# ---------------------------------------------------------------------------
# Corpus level: the real detector over the real pool
# ---------------------------------------------------------------------------

def test_no_named_form_is_selected_today_and_that_is_the_finding():
    """The honest state of the corpus, asserted rather than assumed.

    This test was first written to prove that `min()` returns hexokinase I
    (0.5) from a pool of three forms. **It does not.** The raw minimum is
    2.3e-07, from a row carrying no designator, and the full pipeline picks
    the same row. The LDH kcat pool behaves the same way: LDHB sits at 142
    and the pipeline returns 21.1.

    So the defect `name_selected_form` was written for does not currently
    manifest, and saying so is the point. The claim it was built on was
    wrong, and this test is what found that.

    What remains true is ADR 0029's argument: it is luck, not design.
    `FormMixture.reason` warns that "returning the lowest would pick a form"
    and nothing anywhere says whether it did. The function closes that, and
    this test pins the current answer so a future BRENDA update that DOES
    surface a form fails here loudly instead of passing silently.
    """
    from brenda_client import (
        parse_brenda_km_html,
        KM_TABLE_LABEL,
        TURNOVER_TABLE_LABEL,
    )
    import evidence_rank
    from protein_variant import classify

    fixtures = pathlib.Path(__file__).parent / "fixtures"
    checked = 0
    for name, ec, label in [
        ("brenda_hexokinase_fixture.html", "2.7.1.1", KM_TABLE_LABEL),
        ("brenda_ldh_kcat_fixture.html", "1.1.1.27", TURNOVER_TABLE_LABEL),
    ]:
        path = fixtures / name
        if not path.exists():
            continue
        rows = parse_brenda_km_html(
            path.read_text(errors="replace"), ec, [], target_organism=None,
            require_substrate_match=False, table_label=label,
        )
        if len(rows) < 2:
            continue
        mixtures = find_form_mixtures([(r.km_value, r.conditions) for r in rows])
        assert mixtures, f"{name}: no mixture in a pool known to hold several forms"
        checked += 1

        # The real pipeline: withhold variants, narrow by evidence, minimise.
        kept = [r for r in rows if classify(r.conditions).status != "variant"]
        selected = min(evidence_rank.frontier(kept), key=lambda e: e.km_value)

        found = name_selected_form(mixtures, selected.km_value)
        assert found is None, (
            f"{name}: the pipeline now selects {selected.km_value}, which IS a "
            f"named form ({found.label if found else '?'}). That is the defect "
            "this function was built for, it has started manifesting, and the "
            "finding should now be surfaced rather than this test relaxed."
        )

    assert checked, "no pool was examined; this test would have been vacuous"
