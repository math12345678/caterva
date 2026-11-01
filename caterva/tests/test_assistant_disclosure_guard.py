"""scripts/check_llm_disclosure.py now covers Studio's assistant: it fails when the privacy document does not.

The guard reads the real provider layer (caterva/assistant/providers.py) to learn that text can leave, then
requires docs/PRIVACY.md to say so. These tests run the guard's own `main` against a privacy file without the
Studio section, and against the real one.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def guard():
    spec = importlib.util.spec_from_file_location("check_llm_disclosure", ROOT / "scripts" / "check_llm_disclosure.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_the_guard_sees_that_studios_provider_layer_can_reach_a_provider(guard):
    assert guard.studio_can_call_out() is True


def test_it_fails_when_privacy_md_does_not_cover_studios_assistant(guard, tmp_path, monkeypatch, capsys):
    stripped = tmp_path / "PRIVACY.md"
    stripped.write_text("The resolver is an LLM. It is off by default. The query is sent. Their terms apply.\n")
    monkeypatch.setattr(guard, "PRIVACY", stripped)
    monkeypatch.setattr("sys.argv", ["check_llm_disclosure.py"])
    assert guard.main() == 1
    assert "Studio's assistant" in capsys.readouterr().out


def test_it_fails_when_only_the_studio_section_is_removed(guard, tmp_path, monkeypatch, capsys):
    real = (ROOT / "docs" / "PRIVACY.md").read_text(encoding="utf-8")
    start = real.index("## Caterva Studio's assistant")
    end = real.index("## What is deliberately not claimed here")
    cut = tmp_path / "PRIVACY.md"
    cut.write_text(real[:start] + real[end:], encoding="utf-8")
    monkeypatch.setattr(guard, "PRIVACY", cut)
    monkeypatch.setattr("sys.argv", ["check_llm_disclosure.py"])
    assert guard.main() == 1
    out = capsys.readouterr().out
    assert "missing" in out and "OFF by default" in out


def test_it_passes_on_the_real_privacy_document(guard, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["check_llm_disclosure.py"])
    assert guard.main() == 0
    out = capsys.readouterr().out
    assert "Studio's assistant can reach an external provider" in out


def test_the_selftest_still_passes(guard, monkeypatch):
    monkeypatch.setattr("sys.argv", ["check_llm_disclosure.py", "--selftest"])
    assert guard.main() == 0
