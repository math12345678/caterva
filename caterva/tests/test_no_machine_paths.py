"""scripts/check_no_machine_paths.py: the guard passes on the repository and catches a path.

The guard reads tracked files (`git ls-files`), so the repository check needs
a checkout; the rest builds its own files.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("check_no_machine_paths", REPO / "scripts" / "check_no_machine_paths.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()
HOME_LINE = "cd " + "/Us" + "ers/someone/code"
SCRATCH_LINE = "see " + "/tmp/" + "claude-1/wt-x"
PRIVATE_LINE = "wrote " + "/private" + "/tmp/x"


def test_the_selftest_passes():
    assert guard.selftest() == 0


def test_the_repository_names_no_machine_path():
    result = subprocess.run([sys.executable, str(REPO / "scripts" / "check_no_machine_paths.py")],
                            capture_output=True, text=True, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("line", [HOME_LINE, SCRATCH_LINE, PRIVATE_LINE])
def test_each_kind_of_path_is_found(line, tmp_path):
    (tmp_path / "doc.md").write_text(f"fine\n{line}\n", encoding="utf-8")
    assert guard.findings(tmp_path, ["doc.md"]) == [f"doc.md:2: {line}"]


def test_a_neutral_document_is_clean(tmp_path):
    (tmp_path / "doc.md").write_text("cd path/to/caterva\n/tmp/caterva-fixtures/run\n", encoding="utf-8")
    assert guard.findings(tmp_path, ["doc.md"]) == []


def test_an_allowed_file_is_skipped_and_a_binary_is_not_read(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_no_machine_paths.py").write_text(HOME_LINE, encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\0\0" + HOME_LINE.encode())
    assert guard.findings(tmp_path, ["scripts/check_no_machine_paths.py", "blob.bin"]) == []


def test_every_allowance_has_a_reason_and_a_file():
    for key, reason in guard.ALLOWED.items():
        assert len(reason) > 20, key
        assert (REPO / key).exists(), key
