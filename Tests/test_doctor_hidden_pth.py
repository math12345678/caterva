"""`make doctor` names the macOS + iCloud failure that makes `caterva` vanish.

Python 3.13 skips `.pth` files carrying the macOS `hidden` flag, and iCloud
Drive sets that flag on files inside `.venv` when the checkout is under
~/Desktop or ~/Documents. The symptom -- `No module named 'caterva'` from an
interpreter that imported it a minute earlier -- points nowhere near
iCloud, which is why the doctor checks for it by name.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

MAC = sys.platform == "darwin"


def _doctor():
    spec = importlib.util.spec_from_file_location("doctor", ROOT / "scripts" / "doctor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _venv_with_pth(tmp_path, hidden):
    site = tmp_path / ".venv" / "lib" / "python3.13" / "site-packages"
    site.mkdir(parents=True)
    pth = site / "__editable__.caterva.pth"
    pth.write_text("import x\n")
    if hidden and MAC:
        # The real flag, where it exists.
        subprocess.run(["chflags", "hidden", str(pth)], check=True)
    return tmp_path


def _as_mac(doctor, monkeypatch, hidden_names=()):
    """Run the macOS branch everywhere. On a Mac the real flag is read; on
    other platforms the flag is simulated for the named files, so the
    branch is tested on every CI runner instead of skipped on all but one."""
    monkeypatch.setattr(doctor, "IS_MACOS", True)
    if not MAC:
        monkeypatch.setattr(doctor, "_is_hidden", lambda p: p.name in hidden_names)


def test_a_hidden_pth_is_a_named_failure(tmp_path, monkeypatch):
    doctor = _doctor()
    root = _venv_with_pth(tmp_path / "Desktop" / "repo", hidden=True)
    _as_mac(doctor, monkeypatch, hidden_names={"__editable__.caterva.pth"})
    monkeypatch.setattr(doctor, "VENV", root / ".venv")
    monkeypatch.setattr(doctor, "REPO_ROOT", root)
    doctor.check_hidden_pth()

    name, status, detail = doctor.checked[-1]
    assert (name, status) == ("hidden .pth", "FAIL")
    assert "Python skips them" in detail
    assert "iCloud" in detail, "a checkout under Desktop must be told why"
    assert doctor.problems and "chflags nohidden" in doctor.problems[-1][1]


def test_a_visible_pth_passes(tmp_path, monkeypatch):
    doctor = _doctor()
    root = _venv_with_pth(tmp_path / "Code" / "repo", hidden=False)
    _as_mac(doctor, monkeypatch)
    monkeypatch.setattr(doctor, "VENV", root / ".venv")
    monkeypatch.setattr(doctor, "REPO_ROOT", root)
    doctor.check_hidden_pth()
    assert doctor.checked[-1][:2] == ("hidden .pth", "PASS")


def test_the_caterva_command_is_declared():
    """`caterva` is what every document teaches; the wheel must install it."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'caterva = "caterva.app:main"' in text


def test_off_macos_the_check_says_so_rather_than_passing_silently(monkeypatch):
    doctor = _doctor()
    monkeypatch.setattr(doctor, "IS_MACOS", False)
    doctor.check_hidden_pth()
    name, status, detail = doctor.checked[-1]
    assert (name, status) == ("hidden .pth", "PASS")
    assert "not macOS" in detail
