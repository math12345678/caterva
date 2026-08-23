"""The provenance example on the front page is what Terrium actually outputs.

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
