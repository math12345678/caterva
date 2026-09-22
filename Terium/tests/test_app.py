"""`terrium <command>`: the one-executable dispatcher the app folder runs.

`Terium/app.py` is what the frozen folder's `terrium` binary executes
(ADR 0177). The freeze cannot be built or run in every environment, so
the dispatch is pinned here, from a checkout, where it can.
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

import pytest

from Terium import __version__
from Terium.app import COMMANDS, main


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
    assert out.startswith("usage: terrium <command>")
    for name in COMMANDS:
        assert f"\n  {name} " in out


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_prints_usage_and_succeeds(flag):
    rc, out, _ = _run([flag])
    assert rc == 0 and out.startswith("usage: terrium <command>")


@pytest.mark.parametrize("flag", ["-V", "--version"])
def test_version_is_the_package_version(flag):
    rc, out, _ = _run([flag])
    assert rc == 0 and out.strip() == f"terrium {__version__}"


def test_unknown_command_is_refused_on_stderr():
    rc, out, err = _run(["bogus"])
    assert rc == 2 and out == ""
    assert "unknown command 'bogus'" in err and "usage: terrium" in err


def test_sim_dispatches_to_the_engine_cli_unchanged():
    rc, out, _ = _run(["sim", "--help"])
    assert rc == 0
    for sub in ("wf", "kimura", "ssa"):
        assert sub in out


def test_compose_dispatches_to_the_composer_unchanged():
    rc, out, _ = _run(["compose", "--help"])
    assert rc == 0 and "--subject" in out


def test_arguments_after_the_command_pass_through_verbatim():
    # `--shapes` is the composer's own flag; the dispatcher must not eat it.
    rc, out, _ = _run(["compose", "--shapes"])
    assert rc == 0 and "toggle" in out.lower()
