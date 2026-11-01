"""Tests for effector_presence.py -- contrast detection across a pool.

Extraction is `effector.py`'s job and is tested in `test_effector.py`. This
file tests only what no single row and no pair of rows can answer: whether
the pool contains both arms of one experiment.

Providers are injected so the network is never touched. The fixture CIDs are
real (fructose 1,6-bisphosphate 172440, NADH 439153), so they describe the
API this code actually talks to.
"""
from __future__ import annotations

import pathlib

import pytest

from effector_presence import find_contrasts


CID_BY_NAME = {
    "fructose 1,6-bisphosphate": 172440,
    "fructose 1,6-diphosphate": 172440,
    "d-fructose-1,6-diphosphate": 172440,
    "fructose-1,6-bisphosphate": 172440,
    "nadh": 439153,
}


def fake_cid(name: str) -> str:
    cid = CID_BY_NAME.get(name.strip().lower())
    if cid is None:
        return '{"Fault": {"Code": "PUGREST.NotFound"}}'
    return '{"IdentifierList": {"CID": [%d]}}' % cid


def fake_parent(cid: int) -> str:
    return '{"IdentifierList": {"CID": [%d]}}' % cid


def contrasts(rows):
    return find_contrasts(rows, fake_cid, fake_parent)


# ---------------------------------------------------------------------------
# The thing this module exists to detect
# ---------------------------------------------------------------------------

REAL_LDH_ARMS = [
    (21.1, "pH 6.0, 25°C, recombinant wild-type enzyme in presence of fructose 1,6-bisphosphate"),
    (327.2, "pH 6.0, 25°C, recombinant wild-type enzyme in absence of fructose 1,6-bisphosphate"),
    (178.4, "pH 6.0, 25°C, recombinant mutant D38R in presence of fructose 1,6-bisphosphate"),
    (194.9, "pH 6.0, 25°C, recombinant mutant D38R in absence of fructose 1,6-bisphosphate"),
]


def test_the_real_contrast_is_detected():
    found = contrasts(REAL_LDH_ARMS)
    assert len(found) == 1
    assert "fructose" in found[0].compound.lower()
    assert found[0].present_values == [21.1, 178.4]
    assert found[0].absent_values == [194.9, 327.2]


def test_the_contrast_reports_its_magnitude():
    contrast = contrasts(REAL_LDH_ARMS)[0]
    # 327.2 / 21.1 -- the span a reader is being asked to look at.
    assert contrast.fold_difference == pytest.approx(327.2 / 21.1, rel=1e-6)
    assert "factor of" in contrast.reason


def test_the_reason_names_both_arms():
    # A warning that says "there is a contrast" without the numbers is
    # unactionable: the reader cannot tell whether it matters.
    reason = contrasts(REAL_LDH_ARMS)[0].reason
    assert "21.1" in reason and "327.2" in reason
    assert "half an experiment" in reason


def test_spelling_variants_of_one_compound_still_pair():
    """"fructose 1,6-bisphosphate" and "D-fructose-1,6-diphosphate".

    Two curators, one molecule. If these did not match, the contrast would
    go undetected -- and a missed contrast is invisible, where a spurious
    one is merely dismissed.
    """
    rows = [
        (21.1, "in presence of fructose 1,6-bisphosphate"),
        (327.2, "in absence of D-fructose-1,6-diphosphate"),
    ]
    found = contrasts(rows)
    assert len(found) == 1


def test_no_contrast_when_every_row_is_the_same_arm():
    rows = [
        (21.1, "in presence of fructose 1,6-bisphosphate"),
        (178.4, "in presence of fructose 1,6-bisphosphate"),
    ]
    assert contrasts(rows) == []


def test_no_contrast_from_silence():
    rows = [
        (21.1, "in presence of fructose 1,6-bisphosphate"),
        (327.2, "pH 6.0, 25°C, recombinant wild-type enzyme"),
    ]
    # The second row does not say FBP was absent. It says nothing.
    assert contrasts(rows) == []


def test_different_compounds_do_not_pair():
    rows = [
        (21.1, "in presence of fructose 1,6-bisphosphate"),
        (327.2, "in absence of NADH"),
    ]
    assert contrasts(rows) == []


def test_no_contrast_in_an_empty_pool():
    assert contrasts([]) == []


# ---------------------------------------------------------------------------
# Corpus level: it must fire on the actual fixture, not just on fixtures of
# fixtures
# ---------------------------------------------------------------------------

def test_the_contrast_is_present_in_the_real_ldh_table():
    """The unit tests above use hand-copied strings. This parses the file.

    A hand-copied string can be subtly different from what the parser
    actually produces -- different whitespace, a stripped clause -- and a
    module that works on the copy and not the original is worse than
    useless, because its tests are green.
    """
    from brenda_client import TURNOVER_TABLE_LABEL, parse_brenda_km_html

    html = pathlib.Path(__file__).parent.joinpath(
        "fixtures", "brenda_ldh_kcat_fixture.html"
    ).read_text(errors="replace")
    rows = parse_brenda_km_html(
        html, "1.1.1.27", [], target_organism=None,
        require_substrate_match=False, table_label=TURNOVER_TABLE_LABEL,
    )
    assert rows, "fixture parsed to nothing; this test would pass vacuously"

    # Providers injected: a corpus test that reached PubChem would be a
    # live-network test wearing a unit test's name.
    found = find_contrasts(
        [(r.km_value, r.conditions) for r in rows], fake_cid, fake_parent
    )
    assert found, (
        "no contrast found in the LDH turnover table, which contains "
        "'in presence of fructose 1,6-bisphosphate' and 'in absence of "
        "fructose 1,6-bisphosphate' rows"
    )
    fbp = [c for c in found if "fructose" in c.compound.lower()]
    assert fbp, [c.compound for c in found]
    assert fbp[0].fold_difference and fbp[0].fold_difference > 10, (
        "the fixture no longer demonstrates a large presence/absence span; "
        "re-verify before relaxing this"
    )


# ---------------------------------------------------------------------------
# The presence filter is load-bearing but currently unreachable
# ---------------------------------------------------------------------------

def test_an_unstated_effector_never_forms_a_contrast(monkeypatch):
    """`unstated` must not be bucketed with `absent`.

    This is tested by construction rather than through a commentary string,
    and the reason is worth recording. `effector._presence_of` returns only
    `"present"` or `"absent"` -- the `"unstated"` third state its own
    `Effector.presence` docstring promises is never produced today. So the
    filter in `find_contrasts` is currently unreachable, and the mutation
    that deletes it changes nothing.

    An unreachable filter is one somebody removes as dead code, and the day
    after that a future extractor emits `unstated` and every silent row
    pairs with every "presence of X" row. The same shape as ADR 0026's
    origin filter, which was also unreachable, also mutation-proof, and also
    load-bearing the moment the code around it changed.

    So it is tested where it CAN fail: with the state the type permits and
    the extractor does not yet emit.
    """
    import effector
    import effector_presence

    def fake_extract(commentary):
        if commentary == "SILENT":
            return [effector.Effector(
                raw="", compound_text="fructose 1,6-bisphosphate",
                presence="unstated",
            )]
        return [effector.Effector(
            raw="", compound_text="fructose 1,6-bisphosphate",
            presence="present",
        )]

    monkeypatch.setattr(effector_presence, "extract_effectors", fake_extract)
    monkeypatch.setattr(effector_presence, "resolve_effectors", lambda es, *a, **k: es)

    found = effector_presence.find_contrasts([(21.1, "PRESENT"), (327.2, "SILENT")])
    assert found == [], (
        "an `unstated` effector was treated as an arm of a contrast; "
        "silence is not a statement that the compound was absent"
    )


def test_the_filter_admits_a_genuine_absent(monkeypatch):
    # The counterpart. Without this, the test above would pass because
    # `find_contrasts` returned [] for everything.
    import effector
    import effector_presence

    def fake_extract(commentary):
        presence = "absent" if commentary == "ABSENT" else "present"
        return [effector.Effector(
            raw="", compound_text="fructose 1,6-bisphosphate", presence=presence,
        )]

    monkeypatch.setattr(effector_presence, "extract_effectors", fake_extract)
    monkeypatch.setattr(effector_presence, "resolve_effectors", lambda es, *a, **k: es)

    found = effector_presence.find_contrasts([(21.1, "PRESENT"), (327.2, "ABSENT")])
    assert len(found) == 1
