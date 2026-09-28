"""`caterva <command>`: the one-executable dispatcher the app folder runs.

`caterva/app.py` is what the frozen folder's `caterva` binary executes
(ADR 0177). The freeze cannot be built or run in every environment, so
the dispatch is pinned here, from a checkout, where it can.
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

import pytest

from caterva import __version__
from caterva.app import COMMANDS, main


def _run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            rc = main(args)
        except SystemExit as exc:  # argparse --help exits
            rc = exc.code
    return rc, out.getvalue(), err.getvalue()


def test_no_arguments_prints_usage_and_fails():
    rc, out, _ = _run([])
    assert rc == 2
    assert out.startswith("caterva ")
    for name in COMMANDS:
        assert f"\n  {name} " in out


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_prints_usage_and_succeeds(flag):
    rc, out, _ = _run([flag])
    assert rc == 0 and out.startswith("caterva ")


def test_the_usage_teaches_the_one_rule_and_a_real_first_command():
    """The first thing a lost user types must answer 'what do I type'.

    Not a style check: the shape/subject rule is the cause of most
    refusals, and a usage message that omits it sends people to the
    tracker. The shape COUNT is read from the grammar, so this also
    catches the message claiming a number the builder does not have.
    """
    from caterva.compose.grammar import shapes

    _, out, _ = _run(["--help"])
    assert "--shapes" in out
    assert f"The {len(shapes())} mechanisms" in out
    assert "never a subject" in out.lower()
    # A copy-pasteable command, not a placeholder.
    assert 'caterva compose "a toggle switch between two repressors"' in out


def test_the_usage_never_fails_even_if_the_grammar_will_not_import(monkeypatch):
    """A usage message that raises is worse than one that says 'many'."""
    import builtins

    real_import = builtins.__import__

    def explode(name, *args, **kwargs):
        if name == "caterva.compose.grammar":
            raise RuntimeError("grammar is broken")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", explode)
    rc, out, _ = _run(["--help"])
    assert rc == 0 and "The many mechanisms" in out


@pytest.mark.parametrize("flag", ["-V", "--version"])
def test_version_is_the_package_version(flag):
    rc, out, _ = _run([flag])
    assert rc == 0 and out.strip() == f"caterva {__version__}"


def test_unknown_command_is_refused_on_stderr():
    rc, out, err = _run(["bogus"])
    assert rc == 2 and out == ""
    # The refusal carries the usage with it: someone who mistyped a command
    # is exactly the person who needs to see the list of real ones.
    assert "unknown command 'bogus'" in err
    for name in COMMANDS:
        assert f"\n  {name} " in err


def test_sim_dispatches_to_the_engine_cli_unchanged():
    rc, out, _ = _run(["sim", "--help"])
    assert rc == 0
    assert "ssa" in out
    # The population-genetics subcommands were archived on 2026-09-27.
    for gone in ("{wf", "kimura"):
        assert gone not in out


def test_compose_dispatches_to_the_composer_unchanged():
    rc, out, _ = _run(["compose", "--help"])
    assert rc == 0 and "--subject" in out


def test_arguments_after_the_command_pass_through_verbatim():
    # `--shapes` is the composer's own flag; the dispatcher must not eat it.
    rc, out, _ = _run(["compose", "--shapes"])
    assert rc == 0 and "toggle" in out.lower()
