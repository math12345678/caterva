"""The Tellurium notice must reach every surface that ships.

Wraps `scripts/check_non_affiliation_notice.py` so something runs it
unasked, and exercises its failing branches on constructed input -- the
repository is clean today, so a test that only asserts `main() == 0` would
pass just as happily if the guard stopped guarding.
"""
from __future__ import annotations

import pathlib
import re
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_non_affiliation_notice as guard  # noqa: E402


def test_every_shipping_surface_carries_the_notice() -> None:
    problems = guard.check()
    assert not problems, "\n".join(problems)


def test_a_surface_that_drops_the_notice_is_reported(tmp_path, monkeypatch) -> None:
    """The failing branch, run rather than assumed."""
    surface = tmp_path / "thing.md"
    surface.write_text("A simulation engine. Nothing about the other project.")
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(
        guard, "SURFACES",
        {"thing.md": ("a test surface", (r"not\s+tellurium", r"unaffiliated"))},
    )
    monkeypatch.setattr(guard, "MUST_CREDIT", ())
    problems = guard.check()
    assert len(problems) == 2, problems
    assert all("thing.md" in p for p in problems)


def test_a_surface_that_disappears_is_a_failure_not_a_skip(tmp_path, monkeypatch) -> None:
    """Deleting the file is the easiest way to defeat a checklist."""
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(
        guard, "SURFACES", {"gone.md": ("a missing surface", (r"unaffiliated",))}
    )
    monkeypatch.setattr(guard, "MUST_CREDIT", ())
    problems = guard.check()
    assert len(problems) == 1
    assert "does not exist" in problems[0]


def test_a_denial_without_an_attribution_is_reported(tmp_path, monkeypatch) -> None:
    """Saying "we are not them" is not the same as crediting them.

    The attribution is the part libRoadRunner's Apache 2.0 and Antimony's
    MIT actually ask for; the disclaimer is Terrium's own problem. A
    surface that does only the second looks compliant and is not.
    """
    surface = tmp_path / "thing.md"
    surface.write_text(
        "Terrium is not Tellurium and is unaffiliated with it."
    )
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(
        guard, "SURFACES",
        {"thing.md": ("a test surface", (r"not\s+tellurium", r"unaffiliated"))},
    )
    monkeypatch.setattr(guard, "MUST_CREDIT", ("thing.md",))
    problems = guard.check()
    assert len(problems) == 1
    assert "does not credit libRoadRunner" in problems[0]

    surface.write_text(
        "Terrium is not Tellurium, is unaffiliated, and runs on libRoadRunner."
    )
    assert guard.check() == []


def test_the_floor_fires_when_the_checklist_is_gutted(monkeypatch, capsys) -> None:
    monkeypatch.setattr(guard, "SURFACES", {"NOTICE": ("x", (r"unaffiliated",))})
    assert guard.main() == 1
    assert "below the floor" in capsys.readouterr().out


def test_the_notice_reaches_the_installed_package_not_just_the_repo() -> None:
    """README and NOTICE stay behind; a docstring does not.

    Someone who runs `pip install terrium` and never opens the repository
    is exactly the person the naming confusion affects.
    """
    assert "Terium/__init__.py" in guard.SURFACES
    assert "CITATION.cff" in guard.SURFACES
    text = (guard.ROOT / "Terium" / "__init__.py").read_text()
    assert re.search(r"not\s+tellurium", text, re.I)


def test_every_surface_entry_says_what_the_surface_is_for() -> None:
    for rel, (what, patterns) in guard.SURFACES.items():
        assert len(what) > 15, (
            f"SURFACES[{rel!r}] does not say why the notice needs to be "
            "there. A checklist nobody understands gets pruned."
        )
        assert patterns, f"SURFACES[{rel!r}] requires nothing, so it cannot fail"
