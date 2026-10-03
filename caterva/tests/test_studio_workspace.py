"""The workspace on disk: atomic writes, the round trip of a run, listing, trash, export, settings.

History reopens a run from these files a year later, and a process can be
killed between any two writes, so what is tested here is what a reader
sees: never half a file, the record and request exactly as written, a run
another version wrote reported as unreadable rather than guessed at, a
deleted run moved aside rather than destroyed, and an export that names
every file it holds (docs/studio/CONTRACT.md section 11).
"""
from __future__ import annotations

import io
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from caterva.studio.contract import Malformed
from caterva.studio.jobs import make_run_id
from caterva.studio.workspace import (
    DEFAULT_SETTINGS, RunNotFound, UnreadableRun, Workspace, WorkspaceError, decode_cursor, default_data_dir,
    encode_cursor, kind_of_run_id, validate_settings, write_json_atomic,
)


def record_for(run_id: str, *, status: str = "done", created_at: str = "2026-09-30T14:15:02.000Z",
               **extra) -> dict:
    base = {"schema": "caterva.studio.run/1", "id": run_id, "kind": kind_of_run_id(run_id), "title": "A run",
            "status": status, "created_at": created_at, "started_at": None, "finished_at": None,
            "caterva_version": "0.4.0", "cli": ["caterva", "compose", "--shape", "michaelis menten"],
            "request": {"shape": "michaelis menten"}, "outcome": None, "error": None, "artifacts": [],
            "progress": None}
    base.update(extra)
    return base


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    workspace = Workspace(tmp_path / "data")
    workspace.ensure()
    return workspace


# -- the folder ------------------------------------------------------------------


def test_the_data_folder_is_created_private(ws):
    assert stat.S_IMODE(ws.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(ws.runs_dir.stat().st_mode) == 0o700


def test_a_data_folder_that_cannot_be_written_is_refused_with_the_reason(tmp_path: Path):
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder")
    with pytest.raises(WorkspaceError, match="cannot be created"):
        Workspace(blocker / "data").ensure()
    readonly = tmp_path / "readonly"
    readonly.mkdir(mode=0o500)
    try:
        with pytest.raises(WorkspaceError, match="Permission denied"):
            Workspace(readonly).ensure()
    finally:
        readonly.chmod(0o700)


def test_the_default_folder_per_platform(tmp_path: Path):
    home = tmp_path
    assert default_data_dir("darwin", {}, home) == home / "Library" / "Application Support" / "Caterva"
    assert default_data_dir("linux", {}, home) == home / ".local" / "share" / "caterva"
    assert default_data_dir("linux", {"XDG_DATA_HOME": "/x/data"}, home) == Path("/x/data/caterva")
    assert default_data_dir("linux", {"XDG_DATA_HOME": "relative"}, home) == home / ".local" / "share" / "caterva"
    assert default_data_dir("win32", {"APPDATA": "C:/Users/u/AppData/Roaming"}, home) == \
        Path("C:/Users/u/AppData/Roaming") / "Caterva"


# -- atomic writes ------------------------------------------------------------------


def test_an_atomic_write_leaves_the_old_file_whole_when_it_fails(ws, monkeypatch):
    path = ws.root / "settings.json"
    write_json_atomic(path, {"theme": "light"})

    def broken_replace(src, dst):
        raise OSError("the disk filled up")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        write_json_atomic(path, {"theme": "dark"})
    monkeypatch.undo()
    assert json.loads(path.read_text()) == {"theme": "light"}
    assert [p.name for p in ws.root.iterdir() if p.name.endswith(".tmp")] == []


def test_an_atomic_write_is_private_and_refuses_nan(ws):
    path = ws.root / "x.json"
    write_json_atomic(path, {"a": 1})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(ValueError):
        write_json_atomic(path, {"a": float("nan")})
    assert json.loads(path.read_text()) == {"a": 1}


# -- a run's round trip --------------------------------------------------------------


def test_a_run_round_trips_through_its_files(ws):
    run_id = make_run_id("md.setup")
    record = record_for(run_id)
    ws.create_run(record, record["request"], owner="0123456789abcdef")
    assert ws.read_record(run_id) == record
    assert ws.read_request(run_id) == record["request"]
    assert ws.owner_of(run_id) == "0123456789abcdef"
    ws.write_result(run_id, {"value": 0.1 + 0.2})
    assert json.loads(ws.result_path(run_id).read_text())["value"] == 0.1 + 0.2  # no rounding on the way
    assert ws.write_artifact(run_id, "report.md", b"# report\n") == 9
    with pytest.raises(ValueError):
        ws.write_artifact(run_id, "../escape", b"x")
    for name in ("run.json", "request.json", "result.json"):
        assert stat.S_IMODE((ws.run_dir(run_id) / name).stat().st_mode) == 0o600


def test_events_are_appended_and_a_torn_last_line_is_left_for_later(ws):
    run_id = make_run_id("compose")
    ws.create_run(record_for(run_id), {}, owner=None)
    ws.append_event(run_id, "status", {"seq": 1, "status": "queued"})
    path = ws.run_dir(run_id) / "events.jsonl"
    with open(path, "ab") as handle:
        handle.write(b'{"event": "status", "data": {"seq": 2')  # a writer killed mid-line
    events, offset = ws.read_events(run_id)
    assert events == [("status", {"seq": 1, "status": "queued"})]
    assert ws.read_events(run_id, offset) == ([], offset)
    assert ws.last_seq(run_id) == 1


def test_a_record_another_version_wrote_is_unreadable_not_guessed(ws):
    run_id = make_run_id("compose")
    ws.create_run(record_for(run_id), {}, owner=None)
    write_json_atomic(ws.run_dir(run_id) / "run.json", {**record_for(run_id), "schema": "caterva.studio.run/2"})
    with pytest.raises(UnreadableRun, match="caterva.studio.run/2"):
        ws.read_record(run_id)
    shown = ws.record_or_unreadable(run_id)
    assert shown["status"] == "failed" and shown["error"]["type"] == "UnreadableRun"
    assert shown["title"].startswith("Unreadable by this version")
    assert shown["request"] == {} and shown["outcome"] is None
    (ws.run_dir(run_id) / "run.json").write_text("{ not json")
    assert ws.record_or_unreadable(run_id)["error"]["type"] == "UnreadableRun"
    with pytest.raises(RunNotFound):
        ws.read_record(make_run_id("compose"))


# -- listing ----------------------------------------------------------------------------


def test_runs_are_listed_newest_first_filtered_and_paged(ws):
    ids = []
    for n, kind in enumerate(["compose", "bind", "compose", "md.setup", "compose"]):
        run_id = f"2026093{n}-120000-{kind.replace('.', '-')}-0000000{n}"
        ids.append(run_id)
        ws.create_run(record_for(run_id, created_at=f"2026-09-3{n}T12:00:00.000Z",
                                 status="done" if n % 2 == 0 else "failed"), {}, owner=None)
    (ws.runs_dir / "not-a-run").mkdir()
    rows, cursor = ws.list_runs(limit=2)
    assert [r["id"] for r in rows] == [ids[4], ids[3]]
    rows2, cursor2 = ws.list_runs(limit=2, cursor=cursor)
    assert [r["id"] for r in rows2] == [ids[2], ids[1]]
    rows3, cursor3 = ws.list_runs(limit=2, cursor=cursor2)
    assert [r["id"] for r in rows3] == [ids[0]] and cursor3 is None
    assert [r["id"] for r in ws.list_runs(kind="compose")[0]] == [ids[4], ids[2], ids[0]]
    assert [r["id"] for r in ws.list_runs(status="failed")[0]] == [ids[3], ids[1]]
    assert set(rows[0]) == {"id", "kind", "title", "status", "created_at", "finished_at", "outcome"}


def test_a_cursor_is_opaque_and_a_forged_one_is_malformed():
    cursor = encode_cursor("2026-09-30T00:00:00.000Z", "20260930-000000-compose-00000000")
    assert decode_cursor(cursor) == ("2026-09-30T00:00:00.000Z", "20260930-000000-compose-00000000")
    for forged in ("zz", "", encode_cursor("x", "../../etc")):
        with pytest.raises(Malformed):
            decode_cursor(forged)


def test_a_listing_reflects_a_rewritten_record(ws):
    run_id = make_run_id("compose")
    ws.create_run(record_for(run_id, status="running"), {}, owner=None)
    assert ws.list_runs()[0][0]["status"] == "running"
    ws.write_record(record_for(run_id, status="done", title="A longer title so the size changes"))
    assert ws.list_runs()[0][0]["status"] == "done"


# -- deleting and exporting ----------------------------------------------------------------


def test_deleting_moves_the_run_to_the_trash_and_never_destroys_it(ws):
    run_id = make_run_id("compose")
    ws.create_run(record_for(run_id), {}, owner=None)
    first = ws.trash(run_id)
    assert first == ws.trash_dir / run_id and (first / "run.json").is_file()
    assert not ws.exists(run_id)
    ws.create_run(record_for(run_id), {}, owner=None)
    assert ws.trash(run_id) == ws.trash_dir / f"{run_id}.2"
    with pytest.raises(RunNotFound):
        ws.trash(run_id)


def test_an_export_holds_every_file_and_a_readme_saying_what_each_is(ws):
    run_id = make_run_id("compose")
    record = record_for(run_id, outcome={"exit_code": 0, "meaning": "produced", "summary": "s", "reason": None},
                        artifacts=[{"name": "model.sbml", "content_type": "application/xml", "bytes": 6,
                                    "description": "the model as SBML"}])
    ws.create_run(record, record["request"], owner=None)
    ws.write_result(run_id, {"answer": "kept"})
    ws.write_artifact(run_id, "model.sbml", b"<sbml>")
    ws.append_event(run_id, "end", {"seq": 1, "status": "done"})
    with zipfile.ZipFile(io.BytesIO(ws.bundle(run_id))) as archive:
        names = archive.namelist()
        assert names == ["run.json", "request.json", "result.json", "events.jsonl", "artifacts/model.sbml",
                         "command.txt", "README.txt"]
        assert archive.read("command.txt") == b"caterva compose --shape 'michaelis menten'\n"
        assert archive.read("artifacts/model.sbml") == b"<sbml>"
        assert json.loads(archive.read("result.json")) == {"answer": "kept"}
        readme = archive.read("README.txt").decode()
    for name in names:
        assert name in readme
    assert "the model as SBML" in readme
    assert "caterva compose --shape 'michaelis menten'" in readme
    with pytest.raises(RunNotFound):
        ws.bundle(make_run_id("compose"))


# -- settings ---------------------------------------------------------------------------------


def test_settings_default_and_round_trip(ws):
    assert ws.load_settings() == (DEFAULT_SETTINGS, None)
    stored = validate_settings({"theme": "dark", "max_parallel_runs": 3, "confirm_delete": False,
                                "offline": True}, DEFAULT_SETTINGS)
    ws.save_settings(stored)
    assert ws.load_settings() == (stored, None)
    assert stored == {"theme": "dark", "max_parallel_runs": 3, "confirm_delete": False, "gromacs_path": None,
                      "offline": True, "keep_runs": 200}


@pytest.mark.parametrize("body,field", [
    ({"theme": "blue", "max_parallel_runs": 2, "confirm_delete": True}, "theme"),
    ({"theme": "light", "max_parallel_runs": 9, "confirm_delete": True}, "max_parallel_runs"),
    ({"theme": "light", "max_parallel_runs": True, "confirm_delete": True}, "max_parallel_runs"),
    ({"theme": "light", "max_parallel_runs": 2.0, "confirm_delete": True}, "max_parallel_runs"),
    ({"theme": "light", "max_parallel_runs": 2, "confirm_delete": "yes"}, "confirm_delete"),
    ({"theme": "light", "max_parallel_runs": 2}, "confirm_delete"),
    ({"theme": "light", "max_parallel_runs": 2, "confirm_delete": True, "colour": "red"}, "colour"),
    ({"theme": "light", "max_parallel_runs": 2, "confirm_delete": True, "offline": "no"}, "offline"),
    ({"theme": "light", "max_parallel_runs": 2, "confirm_delete": True, "gromacs_path": "gmx"}, "gromacs_path"),
    ({"theme": "light", "max_parallel_runs": 2, "confirm_delete": True, "gromacs_path": "/no/such/gmx"},
     "gromacs_path"),
])
def test_a_bad_setting_is_refused_naming_its_field(body, field):
    with pytest.raises(Malformed) as refused:
        validate_settings(body, DEFAULT_SETTINGS)
    assert refused.value.field == field


def test_optional_settings_are_kept_when_a_page_omits_them(tmp_path: Path):
    gmx = tmp_path / "gmx"
    gmx.write_text("#!/bin/sh\n")
    gmx.chmod(0o700)
    stored = {**DEFAULT_SETTINGS, "gromacs_path": str(gmx), "offline": True}
    kept = validate_settings({"theme": "light", "max_parallel_runs": 1, "confirm_delete": True}, stored)
    assert kept["gromacs_path"] == str(gmx) and kept["offline"] is True


def test_a_settings_file_that_cannot_be_used_gives_the_defaults_and_says_why(ws, tmp_path: Path):
    ws.settings_path.write_text("{ not json")
    settings, note = ws.load_settings()
    assert settings == DEFAULT_SETTINGS and "was not used" in note
    write_json_atomic(ws.settings_path, {"theme": "dark", "max_parallel_runs": 4, "confirm_delete": True,
                                         "gromacs_path": str(tmp_path / "moved" / "gmx")})
    settings, note = ws.load_settings()
    assert settings["theme"] == "dark" and settings["max_parallel_runs"] == 4 and settings["gromacs_path"] is None
    assert "gromacs_path was not used" in note


# -- two servers, one folder ---------------------------------------------------------------------


def test_an_owner_is_alive_exactly_while_it_holds_its_lock(tmp_path: Path):
    a = Workspace(tmp_path / "data")
    a.ensure()
    b = Workspace(tmp_path / "data")
    a.claim("aaaaaaaaaaaaaaaa")
    b.claim("bbbbbbbbbbbbbbbb")
    assert b.owner_alive("aaaaaaaaaaaaaaaa") and b.owner_alive("bbbbbbbbbbbbbbbb")
    a.release()
    assert not b.owner_alive("aaaaaaaaaaaaaaaa")
    assert not b.owner_alive(None) and not b.owner_alive("../../x")
    b.release()
