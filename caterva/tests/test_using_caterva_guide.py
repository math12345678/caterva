"""Every command in the user's guide must still be a command.

WHY THIS EXISTS
---------------
`docs/USING_CATERVA.md` is the document a stranger reads before anything
else, and its whole value is that the lines in it can be pasted. A guide
whose commands have drifted from the parser is worse than no guide: it
teaches a flag that was renamed and sends the reader to the tracker.

Running each command would take minutes (steady-state searches, resampling),
so this checks what rot actually looks like instead: a flag the parser does
not define, a shape the grammar does not recognise, an export format that
is not offered, a `sim` subcommand that is gone.

WHAT IT DOES NOT CHECK
----------------------
That the commands produce good output, or that the prose around them is
true. Those need a person. This catches the mechanical drift only.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "USING_CATERVA.md"

#: Lines in the guide that illustrate a contrast rather than being typed.
#: They carry an arrow to their explanation, e.g.
#:   caterva compose "glycolysis"   ->  refuses, and says why
_ILLUSTRATION = re.compile(r"->")

#: `caterva compose "..."` is a template: the reader substitutes their own
#: description. The flags on such a line are still checked.
_TEMPLATE_DESCRIPTION = "..."


def _command_lines() -> list[str]:
    text = GUIDE.read_text(encoding="utf-8")
    lines = []
    for raw in re.findall(r"^\s*(?:\./)?caterva\s+(.+)$", text, re.M):
        if _ILLUSTRATION.search(raw):
            continue
        # Strip trailing shell redirection and comments; keep the arguments.
        line = raw.split("#")[0].split(">")[0].strip().rstrip("\\").strip()
        if line:
            lines.append(line)
    return lines


def test_the_guide_contains_commands_at_all():
    """A parser that silently matches nothing would make every test below pass."""
    assert GUIDE.is_file(), f"{GUIDE} is missing; the README and release notes link to it"
    assert len(_command_lines()) >= 15, _command_lines()


@pytest.mark.parametrize("line", _command_lines(), ids=lambda s: s[:48])
def test_every_flag_and_shape_in_the_guide_still_exists(line: str):
    import shlex

    from caterva.app import COMMANDS

    parts = shlex.split(line)
    command, rest = parts[0], parts[1:]
    assert command in COMMANDS, f"`caterva {command}` is not a command; {sorted(COMMANDS)}"

    flags = {p for p in rest if p.startswith("-")}
    positionals = [p for p in rest if not p.startswith("-")]

    if command == "compose":
        from caterva.compose.__main__ import build_parser
        from caterva.compose.grammar import UnrecognisedShape, recognise

        known = {opt for action in build_parser()._actions for opt in action.option_strings}
        unknown = flags - known
        assert not unknown, f"the guide uses {sorted(unknown)}, which the composer no longer defines"

        # The first positional is the description, when the line has one.
        if positionals and positionals[0] != _TEMPLATE_DESCRIPTION:
            description = positionals[0]
            try:
                recognise(description)
            except UnrecognisedShape as exc:  # pragma: no cover - failure path
                pytest.fail(f"the guide builds {description!r}, which the grammar no longer recognises: {exc}")

        if "--export" in rest:
            fmt = rest[rest.index("--export") + 1]
            action = next(a for a in build_parser()._actions if "--export" in a.option_strings)
            assert fmt in (action.choices or []), f"--export {fmt} is no longer offered; {action.choices}"

    elif command == "rates":
        from caterva.rates.__main__ import build_parser as rates_parser

        parser = rates_parser()
        known = {opt for action in parser._actions for opt in action.option_strings}
        unknown = flags - known
        assert not unknown, f"the guide uses {sorted(unknown)}, which `caterva rates` no longer defines"
        for flag in flags:
            action = next(a for a in parser._actions if flag in a.option_strings)
            if action.choices:
                value = rest[rest.index(flag) + 1]
                assert value in action.choices, f"{flag} {value} is no longer offered; {action.choices}"
        # A file the guide runs from the repository must be in it; a name
        # like my_rates.csv is the reader's own.
        for path in positionals:
            if path.startswith("examples/"):
                assert (GUIDE.parents[1] / path).is_file(), f"the guide runs {path}, which is gone"

    elif command == "sim":
        from caterva.cli import main as _engine_main  # noqa: F401 - import proves the module loads

        subcommands = {"wf", "kimura", "ne", "sweep", "scenarios", "ld", "ssa"}
        assert positionals, f"`caterva sim` in the guide names no subcommand: {line}"
        assert positionals[0] in subcommands, f"`sim {positionals[0]}` is not a subcommand; {sorted(subcommands)}"


def test_the_guide_teaches_the_rule_that_explains_most_refusals():
    """The shape/subject distinction is the single most common confusion."""
    text = GUIDE.read_text(encoding="utf-8").lower()
    assert "shape" in text and "subject" in text
    assert "glycolysis" in text, "the guide should show the refusal a reader will actually hit"


def test_the_guide_and_the_usage_message_agree_about_the_shape_count():
    """Two places state how many mechanisms there are; neither may drift."""
    from caterva.app import _usage
    from caterva.compose.grammar import shapes

    assert str(len(shapes())) in _usage()
    guide = GUIDE.read_text(encoding="utf-8")
    stated = re.findall(r"(\d+)\s+mechanisms", guide)
    for number in stated:
        assert int(number) == len(shapes()), (
            f"the guide says {number} mechanisms; the grammar has {len(shapes())}"
        )
