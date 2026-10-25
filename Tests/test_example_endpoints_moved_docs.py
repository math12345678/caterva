"""The endpoint guard after the root's documents moved into docs/.

`scripts/check_example_endpoints.py` read every `*.md` at the root; the
API, operations, guide, science and history documents moved to five docs/
folders on 2026-10-24, and the guard follows them there (`MOVED_DOC_GLOBS`).
Two things came with the move, and both are pinned here in both directions:

- `docs/api/` is a folder, so a link such as `../api/OPENAPI_GUIDE.md`
  contains `/api/`. Such a path is excused as a file, not an address. A
  relative call (`fetch('../api/x')`) or a URL with a docs segment is not:
  the first version of the rule excused both.
- A folder that comes back empty refuses the run, and a document in a
  subfolder of one is read.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_example_endpoints as guard  # noqa: E402

AS_FILE = "a path into this repository's docs/api/ folder, not an address"


def _reasons(tmp_path: pathlib.Path, text: str) -> dict[str, str | None]:
    doc = tmp_path / "probe.md"
    doc.write_text(text + "\n", encoding="utf-8")
    return {endpoint: reason for _, endpoint, reason in guard.doc_mentions(doc)}


@pytest.mark.parametrize("line, mention", [
    ("See [the quick reference](docs/api/API_QUICK_REFERENCE.md).", "/api/API_QUICK_REFERENCE.md"),
    ("From docs/history: `../api/OPENAPI_GUIDE.md`.", "/api/OPENAPI_GUIDE.md"),
    ("The interface is described in /docs/api/WEB_INTERFACE.md", "/api/WEB_INTERFACE.md"),
])
def test_a_path_to_a_document_in_docs_api_is_a_file_not_an_address(tmp_path, line, mention):
    assert (guard.REPO_ROOT / "docs" / mention.lstrip("/")).is_file(), "the probe must name a real document"
    assert _reasons(tmp_path, line)[mention] == AS_FILE


@pytest.mark.parametrize("line", [
    "const res = await fetch('../api/zzqfabricated');",
    'axios.get("../api/zzqfabricated")',
    "curl http://localhost:3000/docs/api/zzqfabricated",
    'curl "https://caterva.example.org/docs/api/zzqfabricated"',
])
def test_a_call_written_after_docs_or_dot_dot_is_still_a_claim(tmp_path, line):
    reasons = _reasons(tmp_path, line)
    assert reasons, "the probe line must be read as a mention"
    assert all(reason != AS_FILE for reason in reasons.values()), reasons


def test_the_moved_documents_are_read_and_a_subfolder_with_them(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("root\n", encoding="utf-8")
    for pattern in guard.MOVED_DOC_GLOBS:
        folder = tmp_path / pattern.split("/**")[0]
        folder.mkdir(parents=True)
        (folder / "A.md").write_text("a\n", encoding="utf-8")
    deeper = tmp_path / "docs" / "api" / "v2" / "B.md"
    deeper.parent.mkdir()
    deeper.write_text("b\n", encoding="utf-8")
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(guard, "EXTRA_DOC_FILES", [])
    found = guard.documentation_files()
    assert deeper in found
    assert len(found) == 1 + len(guard.MOVED_DOC_GLOBS) + 1


def test_a_moved_folder_that_comes_back_empty_refuses_the_run(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("root\n", encoding="utf-8")
    for pattern in guard.MOVED_DOC_GLOBS[1:]:
        folder = tmp_path / pattern.split("/**")[0]
        folder.mkdir(parents=True)
        (folder / "A.md").write_text("a\n", encoding="utf-8")
    monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError, match=r"no documents match docs/api/\*\*/\*\.md"):
        guard.documentation_files()


def test_the_real_tree_reads_every_moved_document():
    found = set(guard.documentation_files())
    for folder in ("api", "operations", "guides", "science", "history"):
        docs = sorted((guard.REPO_ROOT / "docs" / folder).glob("*.md"))
        assert docs, f"docs/{folder}/ holds no documents"
        assert set(docs) <= found, f"a document in docs/{folder}/ is not read"
