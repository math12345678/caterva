"""The provenance example on the front page is what Caterva actually outputs.

WHY THIS FILE EXISTS
--------------------
Three ADRs have now been spent on ways a documented citation can be wrong,
each one quieter than the last:

    ADR 0144   the reference does not exist          (`ref 12345`)
    ADR 0161   the reference is for another enzyme   (AChE ref under LDH)
    ADR 0162   the page does not report that value   (`0.14` under ref 740253)

Each was caught by a guard that reads STRINGS: does this id occur in a
fixture, does that fixture's EC match the prose, does that number appear on
the page. ADR 0162 named what string-matching still cannot do:

    That the value is the row for the substrate and organism the example
    names. `0.03` occurs on the LDH page; this guard does not confirm it is
    the pyruvate row rather than some other row.

This closes it, and not by matching harder. It runs the resolver — the
actual product — over the committed fixture and asserts the front page shows
what came back. The claim being checked stops being "these characters appear
somewhere on that page" and becomes **"this is what the tool does"**.

WHY THAT IS THE STRONGEST FORM
------------------------------
A README example is a promise about behaviour. Every check short of running
the thing tests a proxy for that promise, and this project's whole history
is proxies passing while the thing they stood for was broken: a guard that
printed "every collected test ran" while 275 failed to collect, a staleness
check that hardcoded the mode it verified, five assertions satisfied by
prose that explained the string they matched.

If the resolver's answer changes — a parser fix, a ranking change, a
different fixture — this fails and names both numbers. That is the whole
point: the front page cannot drift away from the product without somebody
being told.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from fallback_logic import resolve_kinetic_value

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "Tests" / "fixtures" / "brenda_ldh_fixture.html"

#: The surfaces carrying the provenance example, and the example itself.
#:
#: Listed rather than discovered: this is a claim that these three documents
#: show THIS example, and a discovery loop would silently cover zero of them
#: the day the block is reworded.
SURFACES = (
    "README.md",
    "docs/readmes/main.md",
    "docs/readmes/backend-main.md",
)

EC = "1.1.1.27"
ORGANISM = "Homo sapiens"
SUBSTRATE = "pyruvate"


def _no_network(*args, **kwargs):
    """Every auxiliary lookup, refused.

    The resolver also consults UniProt, NCBI Taxonomy and a literature
    search. This test is about the BRENDA row, and a test that reaches four
    services is a test that fails for reasons unrelated to what it checks —
    which is how it comes to be marked skip and stops meaning anything.
    """
    return None


@pytest.fixture(scope="module")
def resolved():
    text = FIXTURE.read_text(encoding="utf-8")

    def page(ec_number: str, timeout: float = 15) -> str:
        return text

    result = resolve_kinetic_value(
        EC, ORGANISM, SUBSTRATE,
        html_provider=page,
        quantity="km",
        uniprot_provider=_no_network,
        taxon_id_provider=_no_network,
        search_literature=False,
    )
    assert result.found, (
        "the committed LDH fixture no longer resolves a Km for pyruvate in "
        "Homo sapiens, so this test has nothing to compare the front page to"
    )
    return result


def _example_lines() -> list[tuple[str, str]]:
    """Every `km <value> mM ... BRENDA ref <id>` line on the listed surfaces."""
    pattern = re.compile(r"km\s+([\d.]+)\s*mM\b.*?BRENDA ref\s+(\d{6,})")
    found: list[tuple[str, str]] = []
    for relative in SURFACES:
        path = REPO_ROOT / relative
        assert path.is_file(), f"{relative} is listed as a surface and is missing"
        for line in path.read_text(encoding="utf-8").splitlines():
            match = pattern.search(line)
            if match:
                found.append((relative, line.strip()))
    return found


def test_all_three_surfaces_carry_the_example():
    """The premise, asserted rather than assumed.

    If the block is reworded and this finds nothing, every assertion below
    would pass over an empty list — the vacuous-green shape this repository
    has recorded more often than any other.
    """
    lines = _example_lines()
    assert len(lines) == len(SURFACES), (
        f"expected one km example per surface, found {len(lines)}: {lines}"
    )


def test_the_documented_value_is_the_one_the_resolver_returns(resolved):
    """Not "0.03 appears on the page" — "0.03 is what the tool says"."""
    pattern = re.compile(r"km\s+([\d.]+)\s*mM")
    for relative, line in _example_lines():
        shown = pattern.search(line).group(1)  # type: ignore[union-attr]
        assert float(shown) == pytest.approx(resolved.value), (
            f"{relative} shows km = {shown} mM, but resolving {SUBSTRATE} for "
            f"{ORGANISM} against the committed fixture returns "
            f"{resolved.value}. The front page and the tool disagree."
        )


def test_the_documented_reference_is_the_one_the_resolver_cites(resolved):
    """The pairing, which is what ADR 0162 found broken.

    `0.14 / ref 740253` had a real value elsewhere on the page and a real
    reference elsewhere on the page. Only the PAIR was wrong, and only
    running the resolver can check a pair.
    """
    citation = getattr(resolved, "citation", None)
    assert citation is not None, "the resolver returned a value with no citation"
    expected = str(citation.reference_id)

    pattern = re.compile(r"BRENDA ref\s+(\d{6,})")
    for relative, line in _example_lines():
        shown = pattern.search(line).group(1)  # type: ignore[union-attr]
        assert shown == expected, (
            f"{relative} cites BRENDA ref {shown} for the km, but the "
            f"resolver returns ref {expected} for that value. A citation is "
            "a claim about which row the number came from."
        )


def test_the_units_agree(resolved):
    """A number is not a measurement until it has a unit, and the unit the
    front page prints must be the unit the resolver produced. `0.03 mM` and
    `0.03 uM` are a thousandfold apart and look identical at a glance."""
    assert getattr(resolved, "unit", None) == "mM", (
        f"the resolver now returns {getattr(resolved, 'unit', None)}, and the "
        "front page says mM"
    )


# ---------------------------------------------------------------------------
# The FIFTH layer: right value, right reference, invented conditions.
#
# `docs/DESIGN.md` is the page that teaches what Caterva's trust grades mean,
# using ref 740253 as its worked example. Measured against the committed
# fixture, that example was wrong in three ways and every one of them
# overstated confidence:
#
#     it said                          the resolver says
#     ---------------------------      ------------------------------
#     measured at pH 7.5, 25 °C        pH 8.0; temperature NOT reported
#     assay completeness  complete     partial
#     pH and temperature both          the source states it did not
#       reported                         report temperature
#
# The value (10.73) and the reference (740253) were correct, so all four
# earlier layers pass it. The document explaining the trust model was the
# thing misreporting the trust model, in the reassuring direction.
# ---------------------------------------------------------------------------

DESIGN = REPO_ROOT / "docs" / "DESIGN.md"
LACTATE = "(S)-lactate"


@pytest.fixture(scope="module")
def resolved_lactate():
    text = FIXTURE.read_text(encoding="utf-8")

    def page(ec_number: str, timeout: float = 15) -> str:
        return text

    result = resolve_kinetic_value(
        EC, ORGANISM, LACTATE,
        html_provider=page, quantity="km",
        uniprot_provider=_no_network, taxon_id_provider=_no_network,
        search_literature=False,
    )
    assert result.found, "the fixture no longer resolves a Km for (S)-lactate"
    return result


def test_the_design_example_value_and_reference_are_the_resolvers(resolved_lactate):
    text = DESIGN.read_text(encoding="utf-8")
    assert f"Km = {resolved_lactate.value} mM" in text, (
        f"DESIGN.md's worked example does not show {resolved_lactate.value} mM"
    )
    assert f"ref {resolved_lactate.citation.reference_id}" in text


def _worked_example() -> str:
    """Just the ANSWER/SOURCE/TRUST block, not the whole document.

    The first version of the test below asserted `pH 7.5` appeared NOWHERE
    in DESIGN.md and failed on line 65 — an unrelated hypothetical about
    combining a Km at pH 7.5 with a Ki at pH 6, which is a correct sentence
    illustrating a different problem.

    A guard that fires on a correct sentence gets suppressed (ADR 0028), and
    the fix is to narrow the claim rather than to soften it: this is about
    one worked example, so it reads one worked example.
    """
    text = DESIGN.read_text(encoding="utf-8")
    start = text.index("  ANSWER      Km =")
    return text[start : text.index("  RESULT", start)]


def test_the_design_example_does_not_invent_assay_conditions(resolved_lactate):
    """The specific numbers, asserted as absent from the example block.

    `pH 7.5` and `25 °C` were in that block and in neither the fixture nor
    the resolver's output. Asserting their ABSENCE rather than the presence
    of the right ones is deliberate: a replacement that happened to contain
    "8.0" somewhere would satisfy a positive check while leaving the
    invented pair in place.
    """
    block = _worked_example()
    assert "pH 7.5" not in block
    assert "25 °C" not in block
    assert f"pH {resolved_lactate.assay_ph}" in block


def test_the_design_example_reports_the_temperature_as_unreported(resolved_lactate):
    """The claim that mattered most, because it is about the grading itself."""
    assert resolved_lactate.assay_temperature_c is None, (
        "the fixture now reports a temperature, so DESIGN.md should say it"
    )
    assert "temperature" in (resolved_lactate.assay_unreported or [])
    block = _worked_example()
    assert "temperature NOT reported" in block
    assert "pH and temperature both reported" not in block


def test_the_design_example_states_the_grade_the_grader_gives(resolved_lactate):
    """`complete` was written where the grader returns `partial`.

    Driven through the grader rather than hardcoded, so a change to how
    completeness is decided fails here instead of leaving the design
    document describing a rule the code stopped following.
    """
    from reliability import grade_assay_completeness

    axis = grade_assay_completeness(
        ph=resolved_lactate.assay_ph,
        temperature_c=resolved_lactate.assay_temperature_c,
        unreported=resolved_lactate.assay_unreported,
    )
    assert f"assay completeness   {axis.grade}" in _worked_example(), (
        f"DESIGN.md does not state the grade the grader returns ({axis.grade})"
    )
