"""Every shape builds from the sentence `--shapes` uses to describe it.

WHY
---
`caterva compose --shapes` prints each shape in one line and the usage
message says "describe any of them in your own words". On 2026-09-25, 21
of the 36 shapes did not build from their OWN line, and "two genes
repressing each other" -- the first example in the usage message and the
guide -- was refused. A user trying the tool's own suggestions hit a wall
on most of them, which is the difference between a tool and a demo.

This checks what the user is told to type, not a list of phrasings chosen
to pass.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from caterva.compose.grammar import RULES, UnrecognisedShape
from caterva.compose.pipeline import compose

ROOT = Path(__file__).resolve().parents[2]

#: Descriptions that name two alternatives on purpose. Building either would
#: be a guess, and the refusal says which words choose.
DELIBERATELY_AMBIGUOUS = {
    "feedforward_loop": "coherent and incoherent are opposite circuits",
}


def _winning_rule(query: str) -> str:
    lowered = query.lower()
    candidates = [
        r for r in RULES
        if all(w in lowered for w in r.requires)
        and (not r.triggers or any(t in lowered for t in r.triggers))
    ]
    return max(candidates, key=lambda r: r.priority).name if candidates else ""


def _as_typed(describes: str) -> str:
    # "N phosphorylation cycles" asks for a number; a user types one.
    return re.sub(r"^N ", "3 ", describes)


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.name)
def test_the_description_reaches_its_own_rule(rule) -> None:
    assert _winning_rule(_as_typed(rule.describes)) == rule.name


@pytest.mark.parametrize(
    "rule", [r for r in RULES if r.name not in DELIBERATELY_AMBIGUOUS],
    ids=lambda r: r.name,
)
def test_the_description_builds(rule) -> None:
    compose(_as_typed(rule.describes))


@pytest.mark.parametrize("name", sorted(DELIBERATELY_AMBIGUOUS))
def test_an_ambiguous_description_is_refused_with_a_reason(name) -> None:
    rule = next(r for r in RULES if r.name == name)
    with pytest.raises(UnrecognisedShape):
        compose(_as_typed(rule.describes))


def _advertised_examples() -> list[str]:
    """Every `caterva compose "..."` the usage message and the guide print."""
    text = (ROOT / "caterva" / "app.py").read_text()
    text += (ROOT / "docs" / "USING_CATERVA.md").read_text()
    found = re.findall(r'caterva compose "([^"]+)"', text)
    found += re.findall(r'^\s+"([^"]+)"\s+builds\.', text, re.MULTILINE)
    # "..." is the guide's placeholder for your own description.
    return sorted({q for q in found if "..." not in q})


def _help_examples() -> list[str]:
    """Every example line `caterva compose --help` prints, as argv."""
    import shlex

    from caterva.compose.__main__ import build_parser

    epilog = build_parser("caterva compose").epilog or ""
    lines = [l.strip() for l in epilog.splitlines()
             if l.strip().startswith("caterva compose ")]
    return [shlex.split(l.split(" > ")[0])[2:] for l in lines]


@pytest.mark.parametrize("argv", _help_examples(), ids=lambda a: " ".join(a)[:60])
def test_every_help_example_parses_and_builds(argv) -> None:
    from caterva.compose.__main__ import build_parser

    args = build_parser("caterva compose").parse_args(argv)
    if args.description:
        compose(args.description)


def test_the_help_examples_were_found() -> None:
    assert len(_help_examples()) >= 6


def test_the_advertised_examples_were_found() -> None:
    assert "two genes repressing each other" in _advertised_examples()


@pytest.mark.parametrize("query", _advertised_examples())
def test_every_advertised_example_builds_or_refuses_on_purpose(query) -> None:
    try:
        compose(query)
    except UnrecognisedShape as refusal:
        # The guide shows some refusals deliberately ("glycolysis"); those
        # must refuse for the stated reason, a named pathway, never for
        # want of a trigger.
        assert "No shape in this grammar matches" not in str(refusal), query


def test_the_guide_counts_the_scenario_presets_correctly() -> None:
    """The guide said "twelve teaching presets"; there were thirteen."""
    import subprocess
    import sys

    words = {10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
             14: "fourteen", 15: "fifteen", 16: "sixteen"}
    listed = subprocess.run(
        [sys.executable, "-m", "caterva.app", "sim", "scenarios"],
        capture_output=True, text=True, cwd=ROOT, check=True,
    ).stdout
    count = sum(1 for line in listed.splitlines() if line[:1].isalpha())
    guide = (ROOT / "docs" / "USING_CATERVA.md").read_text()
    assert f"# {words[count]} teaching presets" in guide
