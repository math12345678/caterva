"""Tests for form_mixture.py.

Every commentary is REAL, from the LDH turnover and hexokinase fixtures.
PubChem is never touched: providers are injected, matching buffer_identity,
effector and taxonomy.
"""
from __future__ import annotations

import pathlib

import pytest

from form_mixture import extract_forms, find_form_mixtures


#: NADH and NADP resolve; LDH and HK do not. That asymmetry is the whole
#: mechanism keeping cofactor acronyms out of the results.
#: Real CIDs. "nad" is present because PubChem genuinely knows the stem
#: (CID 5893) -- omitting it from an earlier draft of this fixture is what
#: exposed the base-versus-token bug the module now guards against.
CID_BY_NAME = {"nad": 5893, "nadh": 439153, "nadp": 5886, "atp": 5957}


def fake_cid(name: str) -> str:
    cid = CID_BY_NAME.get(name.strip().lower())
    if cid is None:
        return '{"Fault": {"Code": "PUGREST.NotFound"}}'
    return '{"IdentifierList": {"CID": [%d]}}' % cid


def fake_parent(cid: int) -> str:
    return '{"IdentifierList": {"CID": [%d]}}' % cid


def mixtures(rows):
    return find_form_mixtures(rows, fake_cid, fake_parent)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "commentary,base,designator",
    [
        ("LDHB, in the presence of 0.125 mM NADH", "LDH", "B"),
        ("pH 7.5, LDH-1, with 3 mM fructose-1,6-bisphosphate", "LDH", "1"),
        ("pH 7.5, wild-type LDH-2, with 3 mM fructose", "LDH", "2"),
        ("hexokinase I", "hexokinase", "I"),
        ("hexokinase Ia", "hexokinase", "Ia"),
        ("hexokinase Ib", "hexokinase", "Ib"),
    ],
)
def test_real_form_names_are_extracted(commentary, base, designator):
    forms = extract_forms(commentary)
    assert any(
        f.base == base and f.designator == designator for f in forms
    ), [(f.base, f.designator) for f in forms]


def test_every_form_carries_its_evidence():
    # An extraction with no evidence is an assertion.
    forms = extract_forms("LDHB, in the presence of 0.125 mM NADH")
    assert forms[0].evidence


@pytest.mark.parametrize(
    "commentary",
    ["pH 8.0, 30°C, native enzyme", "25°C", "in 0.5 M Tris-HCl buffer"],
)
def test_commentaries_naming_no_form_yield_nothing(commentary):
    assert extract_forms(commentary) == []


# ---------------------------------------------------------------------------
# The case this module exists for
# ---------------------------------------------------------------------------

REAL_LDH_POOL = [
    (142.0, "LDHB, in the presence of 0.125 mM NADH"),
    (350.0, "LDHB, in the presence of 0.25 mM NADH"),
    (1500.0, "pH 7.5, temperature not specified in the publication, LDH-1, with 3 mM fructose-1,6-bisphosphate"),
    (1300.0, "pH 7.5, temperature not specified in the publication, wild-type LDH-2, with 3 mM fructose-1,6-bisphosphate"),
]


def test_the_real_ldh_mixture_is_detected():
    found = mixtures(REAL_LDH_POOL)
    ldh = [m for m in found if m.base == "LDH"]
    assert ldh, [m.base for m in found]
    assert set(ldh[0].values_by_form) == {"B", "1", "2"}


def test_the_mixture_reports_its_magnitude():
    ldh = [m for m in mixtures(REAL_LDH_POOL) if m.base == "LDH"][0]
    # 1500 / 142 -- an order of magnitude, which is the point.
    assert ldh.fold_difference == pytest.approx(1500.0 / 142.0, rel=1e-6)
    assert "factor of" in ldh.reason


def test_the_reason_names_each_form_and_its_values():
    # "there is a mixture" without the numbers is unactionable.
    reason = [m for m in mixtures(REAL_LDH_POOL) if m.base == "LDH"][0].reason
    assert "LDHB" in reason and "LDH1" in reason and "LDH2" in reason
    assert "142" in reason and "1500" in reason


def test_the_hexokinase_pool_is_detected():
    rows = [
        (0.5, "hexokinase I"),
        (0.56, "hexokinase Ib"),
        (0.77, "hexokinase Ia"),
    ]
    found = [m for m in mixtures(rows) if m.base == "hexokinase"]
    assert found
    assert set(found[0].values_by_form) == {"I", "Ia", "Ib"}


# ---------------------------------------------------------------------------
# Compound acronyms must not read as enzyme forms
# ---------------------------------------------------------------------------

def test_nadh_and_nadp_do_not_form_a_mixture():
    """The false positive this module would otherwise generate constantly.

    By shape alone "NADH" is base NAD + designator H, and "NADP" is base NAD
    + designator P. Two cofactors in one pool would report as two forms of
    one enzyme.

    They are excluded because PubChem resolves NAD to a compound -- an
    API-backed claim, not an exclusion list. That is the same mechanism
    buffers (ADR 0028) and effectors (ADR 0032) use.
    """
    rows = [
        (142.0, "in the presence of 0.125 mM NADH"),
        (350.0, "in the presence of 0.2 mM NADP"),
    ]
    assert [m for m in mixtures(rows) if m.base == "NAD"] == []


def test_a_real_enzyme_acronym_survives_the_compound_check():
    # The counterpart. Without this, the test above would pass because
    # everything is filtered.
    rows = [(142.0, "LDHB assay"), (1500.0, "LDH-1 assay")]
    assert [m for m in mixtures(rows) if m.base == "LDH"]


def test_an_unresolvable_token_is_kept_not_dropped():
    """A failed PubChem lookup must not silently drop a real enzyme form.

    `unresolvable` is not "definitely a chemical". Treating it as one would
    lose mixtures whenever the network hiccuped -- and a missed mixture is
    invisible, where a spurious one is dismissed.
    """
    def exploding(_name):
        raise TimeoutError("PubChem unreachable")

    rows = [(142.0, "LDHB assay"), (1500.0, "LDH-1 assay")]
    found = find_form_mixtures(rows, exploding, fake_parent)
    assert [m for m in found if m.base == "LDH"]


# ---------------------------------------------------------------------------
# One form is not a mixture
# ---------------------------------------------------------------------------

def test_a_pool_naming_one_form_is_not_a_mixture():
    rows = [(142.0, "LDHB assay one"), (350.0, "LDHB assay two")]
    assert mixtures(rows) == []


def test_a_pool_naming_no_form_is_not_a_mixture():
    rows = [(142.0, "pH 7.4, 37°C"), (350.0, "25°C, native enzyme")]
    assert mixtures(rows) == []


def test_an_empty_pool_is_not_a_mixture():
    assert mixtures([]) == []


def test_the_compound_check_is_skipped_when_there_is_no_mixture():
    """One designator short-circuits before any network call.

    The common case is a pool naming no form at all, and paying two PubChem
    round trips per acronym on every resolution would be a real cost for a
    result that is almost always empty.
    """
    calls = []

    def counting(name):
        calls.append(name)
        return fake_cid(name)

    find_form_mixtures([(1.0, "LDHB assay"), (2.0, "LDHB again")], counting, fake_parent)
    assert calls == []


# ---------------------------------------------------------------------------
# Corpus level
# ---------------------------------------------------------------------------

def test_the_mixture_is_present_in_the_real_ldh_table():
    """Hand-copied strings can differ from what the parser produces.

    A module green on the copy and broken on the original is worse than
    untested, because its tests reassure.
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

    found = find_form_mixtures(
        [(r.km_value, r.conditions) for r in rows], fake_cid, fake_parent
    )
    ldh = [m for m in found if m.base == "LDH"]
    assert ldh, [m.base for m in found]
    assert len(ldh[0].values_by_form) >= 3, ldh[0].values_by_form
    assert ldh[0].fold_difference and ldh[0].fold_difference > 5, (
        "the fixture no longer demonstrates a large span across LDH forms; "
        "re-verify before relaxing this"
    )


# ---------------------------------------------------------------------------
# Two defensive paths the fixtures above cannot reach
#
# Both were found by mutating them and watching nothing fail. That is the
# fourth and fifth time in this codebase (ADR 0026's origin filter, ADR
# 0031's never-matched input, ADR 0033's `unstated` filter), and the reason
# it keeps recurring is that mutation testing proves a check can fail on the
# inputs it RECEIVES, and says nothing about inputs it never receives.
#
# An untestable branch is one somebody deletes as dead code. So each is
# tested where it can fail: by constructing the state the code guards against
# rather than the state the corpus currently produces.
# ---------------------------------------------------------------------------

def test_the_full_token_is_checked_and_not_only_the_base():
    """A compound whose STEM is not itself catalogued.

    PubChem happens to know "NAD", so checking only the base excuses NADH by
    luck. Mutating the code to check only the base therefore breaks nothing
    that the fixtures above can see.

    This constructs the case that luck covers: the base does not resolve, the
    full tokens do. It is not hypothetical -- it is what happens for any
    acronym whose leading letters are not a compound in their own right, and
    the code should not depend on PubChem's catalogue happening to include
    every stem.
    """
    resolves = {"xyzq": 111, "xyzr": 222}   # full tokens known, base "XYZ" not

    def cid(name: str) -> str:
        hit = resolves.get(name.strip().lower())
        if hit is None:
            return '{"Fault": {"Code": "PUGREST.NotFound"}}'
        return '{"IdentifierList": {"CID": [%d]}}' % hit

    rows = [(1.0, "measured with XYZQ"), (2.0, "measured with XYZR")]
    assert find_form_mixtures(rows, cid, fake_parent) == [], (
        "a compound was reported as two forms of an enzyme because only its "
        "truncated stem was checked against PubChem"
    )


def test_a_raising_resolver_does_not_drop_the_form(monkeypatch):
    """`_is_compound`'s exception guard, tested where it can fire.

    `buffer_identity.resolve_identity` swallows provider failures itself and
    returns `status="unresolvable"`, so the try/except in `_is_compound` is
    unreachable through the provider arguments -- mutating it to `return
    True` breaks nothing.

    It still matters: if `resolve_identity` ever raises for a reason the
    providers do not cause, treating that as "definitely a compound" would
    silently drop real enzyme forms. Tested by making the resolver itself
    raise.
    """
    import buffer_identity as bi
    import form_mixture

    def exploding(*_a, **_k):
        raise RuntimeError("resolver blew up")

    monkeypatch.setattr(form_mixture.buffer_identity, "resolve_identity", exploding)

    rows = [(142.0, "LDHB assay"), (1500.0, "LDH-1 assay")]
    found = form_mixture.find_form_mixtures(rows, fake_cid, fake_parent)
    assert [m for m in found if m.base == "LDH"], (
        "a resolver exception was read as 'this is a compound' and the "
        "mixture was dropped"
    )
