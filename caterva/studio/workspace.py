"""The studio's workspace on disk: settings, and every run's request, record, events, result and files.

WHY PLAIN FILES
---------------
History has to reopen a run a year later and show exactly what the engine
said then, and a user has to be able to take a run to a colleague. A
directory per run holding JSON anyone can read (`run.json`, `request.json`,
`result.json`, `events.jsonl`, `artifacts/`) does both with the standard
library and no schema migration tool; the zip export is that directory
plus the command that reproduces it. The layout is docs/studio/CONTRACT.md
section 11.

WHY EVERY WRITE IS A RENAME
---------------------------
The page polls run records while a worker thread rewrites them, and the
process can be killed at any moment (the macOS shell quitting, a laptop
lid). A JSON file written in place can be read half-written, and a reader
that gets half a record either crashes or, worse, shows a run with no
result as if it had none. So every JSON file is written to a temporary
name in the same directory and moved into place with `os.replace`, which
is atomic on every platform the studio runs on: a reader sees the old file
or the new one. `events.jsonl` is the exception: it is only ever appended,
one whole line per write, and a reader keeps only complete lines.

WHAT A RECORD IT CANNOT READ BECOMES
------------------------------------
A `run.json` with another schema (a newer studio wrote it) or one that is
not JSON at all is listed as unreadable by this version, with the reason,
not guessed at: its status is reported as `failed` with the error type
`UnreadableRun`, and nothing else about it is claimed.

TWO SERVERS, ONE FOLDER
-----------------------
At startup a run still marked queued or running belonged to a server that
stopped mid-run, and it is marked interrupted (never resumed). But a
second `caterva studio` on the same folder (the app and a terminal, or two
development servers) must not mark the first one's live runs interrupted.
So each server holds an exclusive lock on its own file under `instances/`
for as long as it runs, and each run records which server owns it; a run
is interrupted only when its owner's lock can be taken, which the
operating system allows only once that server has gone. Where the platform
has no `fcntl` (Windows), every other owner counts as gone, which is the
contract's original rule.

WHAT DELETING DOES
------------------
Moves the run's directory into `<data dir>/trash/`, out of History. It is
never removed from disk by the studio: a deletion clicked by mistake can
be undone by moving the folder back, and a user who wants the space back
empties that folder themselves. Files a run wrote into a directory the
user chose (CONTRACT.md 15) are the user's and are never touched.
"""
from __future__ import annotations

import base64
import binascii
import datetime as _dt
import io
import json
import os
import re
import shlex
import stat
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from caterva.studio.contract import (
    RUN_KINDS, RUN_RECORD_SCHEMA, RUN_STATUSES, THEMES, Malformed,
)
from caterva.studio.routes import ARTIFACT_NAME_PATTERN, RUN_ID_PATTERN

try:  # POSIX only; see "TWO SERVERS, ONE FOLDER"
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

_RUN_ID = re.compile(RUN_ID_PATTERN)
_ARTIFACT_NAME = re.compile(ARTIFACT_NAME_PATTERN)
_INSTANCE_ID = re.compile(r"[0-9a-f]{16}")

#: Kind as written in a run id ("md-setup") -> the RunKind ("md.setup").
_KIND_BY_SLUG = {kind.replace(".", "-"): kind for kind in RUN_KINDS}

TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled", "abandoned", "interrupted"})

DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "system",
    "max_parallel_runs": 2,
    "confirm_delete": True,
    "gromacs_path": None,
    "offline": False,
    "keep_runs": 200,
}
MAX_PARALLEL_RUNS = (1, 8)
_REQUIRED_SETTINGS = ("theme", "max_parallel_runs", "confirm_delete")
_OPTIONAL_SETTINGS = ("gromacs_path", "offline", "keep_runs")
#: The most and fewest finished runs History may be set to keep.
KEEP_RUNS = (10, 5000)

#: The page's history list shows this many runs unless asked for another
#: number, and never more than the maximum in one answer.
DEFAULT_LIMIT, MAX_LIMIT = 50, 200

INTERRUPTED_MESSAGE = "the studio stopped while this run was in progress"


class WorkspaceError(RuntimeError):
    """The data directory cannot be used; the message says why."""


class RunNotFound(LookupError):
    """No run directory with this id."""


class UnreadableRun(ValueError):
    """A run directory whose run.json this version cannot read."""

    def __init__(self, run_id: str, reason: str, schema: Optional[str] = None) -> None:
        super().__init__(reason)
        self.run_id = run_id
        self.schema = schema


# ---------------------------------------------------------------------------
# Time and identifiers
# ---------------------------------------------------------------------------


def utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def iso(moment: _dt.datetime) -> str:
    """ISO 8601 UTC with milliseconds and a Z, fixed width so it sorts as text."""
    return moment.astimezone(_dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def kind_of_run_id(run_id: str) -> Optional[str]:
    """The RunKind a run id names, or None."""
    if not _RUN_ID.fullmatch(run_id):
        return None
    slug = run_id[16:-9]
    return _KIND_BY_SLUG.get(slug)


def created_from_run_id(run_id: str) -> str:
    """The creation second a run id encodes, as an ISO time."""
    stamp = _dt.datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").replace(tzinfo=_dt.timezone.utc)
    return iso(stamp)


def default_data_dir(platform: str = sys.platform, environ: Mapping[str, str] = os.environ,
                     home: Optional[Path] = None) -> Path:
    """Where runs and settings live unless --data-dir says otherwise (CONTRACT.md 11)."""
    home = Path.home() if home is None else home
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Caterva"
    if platform.startswith("win"):
        appdata = environ.get("APPDATA")
        return (Path(appdata) if appdata else home / "AppData" / "Roaming") / "Caterva"
    xdg = environ.get("XDG_DATA_HOME")
    if xdg and Path(xdg).is_absolute():
        return Path(xdg) / "caterva"
    return home / ".local" / "share" / "caterva"


# ---------------------------------------------------------------------------
# Writing without half-files
# ---------------------------------------------------------------------------


def _mkdir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write `data` to `path` so a reader sees the old file or the new one."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:  # mkstemp creates it 0600
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def json_bytes(obj: Any) -> bytes:
    """JSON as the studio writes it: UTF-8, no NaN or Infinity (the page's
    JSON.parse rejects them), indented so a person can read the file."""
    return (json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def write_json_atomic(path: Path, obj: Any) -> None:
    write_bytes_atomic(path, json_bytes(obj))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def validate_settings(body: Any, stored: Mapping[str, Any]) -> Dict[str, Any]:
    """A full Settings from a PUT body, or Malformed naming the field.

    The three original contract keys are required. `gromacs_path` and
    `offline` are optional: a body without one keeps the stored value, so a
    page that does not know the key cannot erase it by saving the theme."""
    if not isinstance(body, dict):
        raise Malformed("the settings must be a JSON object", field=None)
    unknown = sorted(set(body) - set(_REQUIRED_SETTINGS) - set(_OPTIONAL_SETTINGS))
    if unknown:
        raise Malformed(f"{unknown[0]!r} is not a setting", field=unknown[0])
    for key in _REQUIRED_SETTINGS:
        if key not in body:
            raise Malformed(f"{key!r} is missing; PUT /api/settings takes the whole settings object", field=key)
    theme = body["theme"]
    if theme not in THEMES:
        raise Malformed(f"theme must be one of {', '.join(THEMES)}", field="theme")
    parallel = body["max_parallel_runs"]
    low, high = MAX_PARALLEL_RUNS
    if isinstance(parallel, bool) or not isinstance(parallel, int) or not low <= parallel <= high:
        raise Malformed(f"max_parallel_runs must be a whole number from {low} to {high}", field="max_parallel_runs")
    confirm = body["confirm_delete"]
    if not isinstance(confirm, bool):
        raise Malformed("confirm_delete must be true or false", field="confirm_delete")
    gromacs = body["gromacs_path"] if "gromacs_path" in body else stored.get("gromacs_path")
    if gromacs is not None:
        gromacs = _validate_gromacs_path(gromacs)
    offline = body["offline"] if "offline" in body else stored.get("offline", False)
    if not isinstance(offline, bool):
        raise Malformed("offline must be true or false", field="offline")
    keep = body["keep_runs"] if "keep_runs" in body else stored.get("keep_runs", DEFAULT_SETTINGS["keep_runs"])
    low_keep, high_keep = KEEP_RUNS
    if isinstance(keep, bool) or not isinstance(keep, int) or not low_keep <= keep <= high_keep:
        raise Malformed(f"keep_runs must be a whole number from {low_keep} to {high_keep}", field="keep_runs")
    return {"theme": theme, "max_parallel_runs": parallel, "confirm_delete": confirm, "gromacs_path": gromacs,
            "offline": offline, "keep_runs": keep}


#: What the program a gromacs_path names may be called: `gmx`, `gmx_mpi`,
#: `gmx_d`, or `gmx_` and a suffix. Anything else (a script called
#: evil.sh, a link named gmx that leads to one) is not accepted.
GMX_NAME = re.compile(r"gmx(?:_[A-Za-z0-9][A-Za-z0-9_.+-]{0,30})?", re.ASCII)


def validate_gromacs_path(value: Any) -> Path:
    """The absolute, resolved path of a GROMACS program, or Malformed.

    The setting names a program the server will run, so it is checked like
    one: an absolute path with no `..`; a name from GMX_NAME, both as given
    and after links are resolved (a link named gmx to another program is
    refused); a regular file the current user can execute, owned by this
    user or root; neither the file nor, unless sticky, its folder writable
    by everyone."""
    if not isinstance(value, str) or not value.strip():
        raise Malformed("gromacs_path must be the absolute path of the gmx program, or null", field="gromacs_path")
    if "\x00" in value or len(value) > 4096:
        raise Malformed("gromacs_path is not a usable path", field="gromacs_path")
    path = Path(value)
    if not path.is_absolute():
        raise Malformed("gromacs_path must be an absolute path", field="gromacs_path")
    if ".." in path.parts:
        raise Malformed("gromacs_path must not contain `..`", field="gromacs_path")
    if not GMX_NAME.fullmatch(path.name):
        raise Malformed("gromacs_path must name the GROMACS program: gmx, gmx_mpi, gmx_d or gmx_<suffix>",
                        field="gromacs_path")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise Malformed(f"gromacs_path {value!r} does not exist", field="gromacs_path") from None
    if not GMX_NAME.fullmatch(resolved.name):
        raise Malformed("gromacs_path is a link to a program that is not named gmx, gmx_mpi, gmx_d or gmx_<suffix>",
                        field="gromacs_path")
    try:
        info = resolved.stat()
        folder = resolved.parent.stat()
    except OSError:
        raise Malformed(f"gromacs_path {value!r} cannot be read", field="gromacs_path") from None
    if not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK):
        raise Malformed(f"gromacs_path {value!r} is not an executable file", field="gromacs_path")
    if hasattr(os, "getuid") and info.st_uid not in (os.getuid(), 0):
        raise Malformed("gromacs_path must be owned by you or by root", field="gromacs_path")
    if info.st_mode & stat.S_IWOTH:
        raise Malformed("gromacs_path is writable by every user, so it is not run", field="gromacs_path")
    if folder.st_mode & stat.S_IWOTH and not folder.st_mode & stat.S_ISVTX:
        raise Malformed("the folder holding gromacs_path is writable by every user, so it is not run",
                        field="gromacs_path")
    return resolved


def _validate_gromacs_path(value: Any) -> str:
    validate_gromacs_path(value)
    return str(Path(value))


# ---------------------------------------------------------------------------
# The workspace
# ---------------------------------------------------------------------------


class Workspace:
    """One data directory. Thread-safe for the operations the server makes."""

    def __init__(self, root: Path) -> None:
        self.root = Path(os.path.abspath(os.path.expanduser(str(root))))
        self._lock = threading.RLock()
        self._summaries: Dict[str, Tuple[Tuple[int, int], Dict[str, Any]]] = {}
        self._claim_fd: Optional[int] = None
        self.instance_id: Optional[str] = None

    # -- layout --------------------------------------------------------------

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def trash_dir(self) -> Path:
        return self.root / "trash"

    @property
    def instances_dir(self) -> Path:
        return self.root / "instances"

    @property
    def settings_path(self) -> Path:
        return self.root / "settings.json"

    @property
    def log_path(self) -> Path:
        return self.root / "studio.log"

    def run_dir(self, run_id: str) -> Path:
        if not _RUN_ID.fullmatch(run_id):
            raise ValueError(f"{run_id!r} is not a run id")
        return self.runs_dir / run_id

    # -- setup ---------------------------------------------------------------

    def ensure(self) -> None:
        """Create the directory (0700) and prove it is writable, or raise
        WorkspaceError saying why."""
        try:
            _mkdir(self.root)
            _mkdir(self.runs_dir)
        except OSError as exc:
            raise WorkspaceError(f"the data folder {self.root} cannot be created: {exc.strerror or exc}") from None
        reason = self.unwritable_reason()
        if reason:
            raise WorkspaceError(reason)

    def unwritable_reason(self) -> Optional[str]:
        """None when a file can be written in the data folder, else why not."""
        if not self.root.is_dir():
            return f"the data folder {self.root} does not exist"
        try:
            fd, probe = tempfile.mkstemp(prefix=".write-probe-", dir=str(self.root))
            os.close(fd)
            os.unlink(probe)
        except OSError as exc:
            return f"the data folder {self.root} is not writable: {exc.strerror or exc}"
        return None

    # -- which server owns what ---------------------------------------------

    def claim(self, instance_id: str) -> None:
        """Hold this server's lock for as long as it runs."""
        if not _INSTANCE_ID.fullmatch(instance_id):
            raise ValueError(f"{instance_id!r} is not an instance id")
        self.instance_id = instance_id
        if fcntl is None:  # pragma: no cover - Windows
            return
        _mkdir(self.instances_dir)
        fd = os.open(self.instances_dir / f"{instance_id}.lock", os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode("ascii"))
        self._claim_fd = fd

    def release(self) -> None:
        if self._claim_fd is None or self.instance_id is None:
            return
        path = self.instances_dir / f"{self.instance_id}.lock"
        try:
            path.unlink()
        except OSError:
            pass
        try:
            os.close(self._claim_fd)  # closing drops the flock
        finally:
            self._claim_fd = None

    def owner_alive(self, instance_id: Optional[str]) -> bool:
        """Whether the server that owns a run is still running."""
        if instance_id is None or not _INSTANCE_ID.fullmatch(instance_id):
            return False
        if instance_id == self.instance_id:
            return True
        if fcntl is None:  # pragma: no cover - Windows
            return False
        path = self.instances_dir / f"{instance_id}.lock"
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError:
            return False
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            try:
                path.unlink()  # a lock nobody holds: its server is gone
            except OSError:
                pass
            return False
        finally:
            os.close(fd)

    def owner_of(self, run_id: str) -> Optional[str]:
        try:
            text = (self.run_dir(run_id) / "owner").read_text(encoding="ascii").strip()
        except (OSError, UnicodeDecodeError):
            return None
        return text if _INSTANCE_ID.fullmatch(text) else None

    # -- settings ------------------------------------------------------------

    def load_settings(self) -> Tuple[Dict[str, Any], Optional[str]]:
        """(settings, why the stored file was not used). A settings file that
        cannot be read gives the defaults and the reason, never a crash."""
        if not self.settings_path.is_file():
            return dict(DEFAULT_SETTINGS), None
        try:
            stored = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return dict(DEFAULT_SETTINGS), f"{self.settings_path} was not used ({exc}); the defaults apply"
        try:
            return validate_settings(stored, DEFAULT_SETTINGS), None
        except Malformed as exc:
            reason = f"{self.settings_path} was not used ({exc}); the defaults apply"
            if exc.field == "gromacs_path" and isinstance(stored, dict):
                # The program moved since it was chosen; the rest may still hold.
                try:
                    kept = validate_settings({**stored, "gromacs_path": None}, DEFAULT_SETTINGS)
                    return kept, f"the stored gromacs_path was not used: {exc}"
                except Malformed:
                    pass
            return dict(DEFAULT_SETTINGS), reason

    def save_settings(self, settings: Mapping[str, Any]) -> None:
        write_json_atomic(self.settings_path, dict(settings))

    # -- runs: writing -------------------------------------------------------

    def create_run(self, record: Mapping[str, Any], request: Any, owner: Optional[str]) -> Path:
        run_dir = self.run_dir(record["id"])
        _mkdir(self.runs_dir)
        run_dir.mkdir(mode=0o700)  # an existing id is a programming error, not a merge
        if owner is not None:
            write_bytes_atomic(run_dir / "owner", f"{owner}\n".encode("ascii"))
        write_json_atomic(run_dir / "request.json", request)
        write_json_atomic(run_dir / "run.json", dict(record))
        return run_dir

    def write_record(self, record: Mapping[str, Any]) -> None:
        write_json_atomic(self.run_dir(record["id"]) / "run.json", dict(record))

    def append_event(self, run_id: str, name: str, data: Mapping[str, Any]) -> None:
        line = json.dumps({"event": name, "data": dict(data)}, ensure_ascii=False, allow_nan=False) + "\n"
        path = self.run_dir(run_id) / "events.jsonl"
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)

    def write_result(self, run_id: str, result: Mapping[str, Any]) -> None:
        write_json_atomic(self.run_dir(run_id) / "result.json", result)

    def write_artifact(self, run_id: str, name: str, content: bytes) -> int:
        if not _ARTIFACT_NAME.fullmatch(name):
            raise ValueError(f"{name!r} is not an artifact name")
        folder = self.run_dir(run_id) / "artifacts"
        _mkdir(folder)
        write_bytes_atomic(folder / name, content)
        return len(content)

    # -- runs: reading -------------------------------------------------------

    def run_ids(self) -> List[str]:
        try:
            names = os.listdir(self.runs_dir)
        except OSError:
            return []
        return [n for n in names if _RUN_ID.fullmatch(n) and kind_of_run_id(n) and (self.runs_dir / n).is_dir()]

    def exists(self, run_id: str) -> bool:
        try:
            return self.run_dir(run_id).is_dir()
        except ValueError:
            return False

    def read_record(self, run_id: str) -> Dict[str, Any]:
        """The run's record, or RunNotFound, or UnreadableRun with the reason."""
        if not self.exists(run_id):
            raise RunNotFound(run_id)
        path = self.run_dir(run_id) / "run.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise UnreadableRun(run_id, "the run has no run.json") from None
        except (OSError, ValueError) as exc:
            raise UnreadableRun(run_id, f"run.json cannot be read: {exc}") from None
        if not isinstance(record, dict):
            raise UnreadableRun(run_id, "run.json is not a JSON object")
        schema = record.get("schema")
        if schema != RUN_RECORD_SCHEMA:
            raise UnreadableRun(
                run_id, f"run.json has schema {schema!r}; this version reads {RUN_RECORD_SCHEMA!r}",
                schema=schema if isinstance(schema, str) else None,
            )
        if record.get("id") != run_id or record.get("status") not in RUN_STATUSES:
            raise UnreadableRun(run_id, "run.json does not describe this run", schema=schema)
        return record

    def record_or_unreadable(self, run_id: str) -> Dict[str, Any]:
        """The record, or for a run this version cannot read, a record that
        says only that, and why (module docstring)."""
        try:
            return self.read_record(run_id)
        except UnreadableRun as exc:
            return unreadable_record(run_id, str(exc), exc.schema)

    def read_request(self, run_id: str) -> Any:
        return json.loads((self.run_dir(run_id) / "request.json").read_text(encoding="utf-8"))

    def result_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "result.json"

    def artifact_path(self, run_id: str, name: str) -> Path:
        if not _ARTIFACT_NAME.fullmatch(name):
            raise ValueError(f"{name!r} is not an artifact name")
        return self.run_dir(run_id) / "artifacts" / name

    def read_events(self, run_id: str, offset: int = 0) -> Tuple[List[Tuple[str, Dict[str, Any]]], int]:
        """Complete event lines from byte `offset` on, and the offset after the
        last complete line. A line being written is left for the next read."""
        path = self.run_dir(run_id) / "events.jsonl"
        try:
            with open(path, "rb") as handle:
                handle.seek(offset)
                chunk = handle.read()
        except FileNotFoundError:
            return [], offset
        end = chunk.rfind(b"\n")
        if end == -1:
            return [], offset
        events: List[Tuple[str, Dict[str, Any]]] = []
        for raw in chunk[: end + 1].splitlines():
            try:
                item = json.loads(raw.decode("utf-8"))
                name, data = item["event"], item["data"]
            except (ValueError, KeyError, TypeError):
                continue  # a torn line from a killed process: not an event
            if isinstance(name, str) and isinstance(data, dict):
                events.append((name, data))
        return events, offset + end + 1

    def last_seq(self, run_id: str) -> int:
        events, _ = self.read_events(run_id)
        seqs = [d.get("seq") for _, d in events if isinstance(d.get("seq"), int)]
        return max(seqs, default=0)

    # -- runs: listing -------------------------------------------------------

    def summary(self, run_id: str) -> Dict[str, Any]:
        path = self.run_dir(run_id) / "run.json"
        try:
            st = path.stat()
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            stamp = (-1, -1)
        with self._lock:
            cached = self._summaries.get(run_id)
            if cached and cached[0] == stamp and stamp != (-1, -1):
                return cached[1]
        record = self.record_or_unreadable(run_id)
        summary = summary_of(record)
        with self._lock:
            self._summaries[run_id] = (stamp, summary)
        return summary

    def list_runs(self, *, kind: Optional[str] = None, status: Optional[str] = None,
                  limit: int = DEFAULT_LIMIT, cursor: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Newest first. `cursor` is the previous page's `next_cursor`."""
        after = decode_cursor(cursor) if cursor else None
        rows = []
        for run_id in self.run_ids():
            if kind is not None and kind_of_run_id(run_id) != kind:
                continue
            summary = self.summary(run_id)
            if status is not None and summary["status"] != status:
                continue
            rows.append(summary)
        rows.sort(key=lambda s: (s["created_at"], s["id"]), reverse=True)
        if after is not None:
            rows = [s for s in rows if (s["created_at"], s["id"]) < after]
        page = rows[:limit]
        more = len(rows) > limit
        next_cursor = encode_cursor(page[-1]["created_at"], page[-1]["id"]) if more and page else None
        return page, next_cursor

    # -- runs: removing and exporting ---------------------------------------

    def trash(self, run_id: str) -> Path:
        """Move the run out of History into <data dir>/trash/ (module docstring)."""
        source = self.run_dir(run_id)
        if not source.is_dir():
            raise RunNotFound(run_id)
        _mkdir(self.trash_dir)
        target = self.trash_dir / run_id
        n = 1
        while target.exists():
            n += 1
            target = self.trash_dir / f"{run_id}.{n}"
        os.replace(source, target)
        with self._lock:
            self._summaries.pop(run_id, None)
        return target

    def bundle(self, run_id: str, *, redact_paths: bool = True, diagnostics: bool = False,
               home: Optional[str] = None) -> bytes:
        """The run as a zip: what History shows, and the command that reproduces it.

        A run's files hold where it ran: the home folder and the data folder
        in its command line, its request, its events, its artifacts, and in
        the traceback of a crash. An export leaves the machine, so by default
        (`redact_paths`) the home folder is written as `~` and the data
        folder, when it is elsewhere, as `<data dir>` in every text file, and
        (unless `diagnostics`) a crash's traceback is left out: its type and
        message stay. `diagnostics=True` keeps the traceback, still with
        paths redacted when `redact_paths` is on. README.txt says which was
        done."""
        run_dir = self.run_dir(run_id)
        if not run_dir.is_dir():
            raise RunNotFound(run_id)
        record = self.record_or_unreadable(run_id)
        home_dir = os.path.expanduser("~") if home is None else home
        replacements = _path_replacements(home_dir, str(self.root)) if redact_paths else []

        def clean(text: str) -> str:
            for old, new in replacements:
                text = text.replace(old, new)
            return text

        def tidy_json(text: str) -> str:
            if diagnostics:
                return clean(text)
            try:
                value = json.loads(text)
            except ValueError:
                return clean(text)
            return clean(json.dumps(_without_traceback(value), indent=2, ensure_ascii=False) + "\n")

        def tidy_events(text: str) -> str:
            lines = []
            for line in text.splitlines():
                if not diagnostics:
                    try:
                        line = json.dumps(_without_traceback(json.loads(line)), ensure_ascii=False,
                                          separators=(",", ":"))
                    except ValueError:
                        pass
                lines.append(clean(line))
            return "\n".join(lines) + ("\n" if lines else "")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            names: List[str] = []

            def add(name: str, data: bytes, source: Optional[Path] = None) -> None:
                info = zipfile.ZipInfo(name, date_time=_zip_time(source))
                info.external_attr = 0o600 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
                names.append(name)

            for filename in ("run.json", "request.json", "result.json", "events.jsonl"):
                path = run_dir / filename
                if path.is_file():
                    text = path.read_bytes().decode("utf-8", errors="replace")
                    text = tidy_events(text) if filename == "events.jsonl" else tidy_json(text)
                    add(filename, text.encode("utf-8"), path)
            for artifact in record.get("artifacts") or []:
                name = artifact.get("name") if isinstance(artifact, dict) else None
                if not isinstance(name, str) or not _ARTIFACT_NAME.fullmatch(name):
                    continue
                path = run_dir / "artifacts" / name
                if path.is_file():
                    data = path.read_bytes()
                    if replacements and _is_text(artifact.get("content_type")):
                        data = clean(data.decode("utf-8", errors="replace")).encode("utf-8")
                    add(f"artifacts/{name}", data, path)
            cli = record.get("cli") if isinstance(record.get("cli"), list) else []
            command = clean(shlex.join(str(part) for part in cli)) + "\n" if cli else ""
            if command:
                add("command.txt", command.encode("utf-8"))
            add("README.txt", bundle_readme(_for_readme(record, clean, diagnostics), names, command,
                                            redact_paths=redact_paths, diagnostics=diagnostics).encode("utf-8"))
        return buffer.getvalue()


def _path_replacements(home: str, data_dir: str) -> List[Tuple[str, str]]:
    """(what to find, what to write) for paths of this machine, longest first."""
    pairs: List[Tuple[str, str]] = []
    home = home.rstrip("/\\")
    data_dir = data_dir.rstrip("/\\")
    if data_dir and home and not (data_dir == home or data_dir.startswith(home + os.sep)):
        pairs.append((data_dir, "<data dir>"))
    if home and home not in ("/", "~"):
        pairs.append((home, "~"))
    out: List[Tuple[str, str]] = []
    for old, new in pairs:
        out.append((old, new))
        escaped = json.dumps(old)[1:-1]
        if escaped != old:
            out.append((escaped, new))
    return sorted(out, key=lambda pair: -len(pair[0]))


def _without_traceback(value: Any) -> Any:
    """`value` with every `traceback` key of an error set to null."""
    if isinstance(value, dict):
        return {k: (None if k == "traceback" else _without_traceback(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_without_traceback(v) for v in value]
    return value


def _is_text(content_type: Any) -> bool:
    kind = str(content_type or "").split(";")[0].strip().lower()
    return kind.startswith("text/") or kind in ("application/json", "application/xml", "application/x-ndjson") \
        or kind.endswith("+xml") or kind.endswith("+json")


def _for_readme(record: Mapping[str, Any], clean: Any, diagnostics: bool) -> Dict[str, Any]:
    """The record as the README shows it: paths cleaned in the error line."""
    shown = dict(record)
    if isinstance(shown.get("error"), dict):
        shown["error"] = {**shown["error"], "message": clean(str(shown["error"].get("message")))}
    return shown


def _zip_time(source: Optional[Path]) -> Tuple[int, int, int, int, int, int]:
    moment = utc_now()
    if source is not None:
        try:
            moment = _dt.datetime.fromtimestamp(source.stat().st_mtime, _dt.timezone.utc)
        except OSError:
            pass
    return (max(moment.year, 1980), moment.month, moment.day, moment.hour, moment.minute, moment.second)


_FILE_MEANINGS = {
    "run.json": "the run record: kind, title, status, times, the Caterva version, the command line, "
                "the outcome (or the error) and the list of files it produced (schema "
                f"{RUN_RECORD_SCHEMA})",
    "request.json": "the request exactly as the studio accepted it",
    "result.json": "the result the engine produced, every number with its provenance "
                   "(docs/studio/CONTRACT.md, section 9)",
    "events.jsonl": "every progress event the run emitted, one JSON object per line, in order",
    "command.txt": "the command that reproduces this run from the repository root",
}


def bundle_readme(record: Mapping[str, Any], names: List[str], command: str, *, redact_paths: bool = False,
                  diagnostics: bool = True) -> str:
    """The README.txt of an exported run: what each file in the zip is, and
    what was taken out of it before it left this computer."""
    lines = [
        f"Caterva Studio run {record.get('id')}",
        "",
        f"Title:    {record.get('title')}",
        f"Kind:     {record.get('kind')}",
        f"Status:   {record.get('status')}",
        f"Created:  {record.get('created_at')}",
        f"Finished: {record.get('finished_at') or 'not finished'}",
        f"Caterva:  {record.get('caterva_version') or 'unknown'}",
    ]
    outcome = record.get("outcome")
    if isinstance(outcome, dict):
        lines.append(f"Outcome:  {outcome.get('meaning')} (the command exits {outcome.get('exit_code')})")
        if outcome.get("reason"):
            lines.append(f"Reason:   {outcome.get('reason')}")
    error = record.get("error")
    if isinstance(error, dict):
        lines.append(f"Error:    {error.get('type')}: {error.get('message')}")
    if command:
        lines += ["", "To reproduce it in a terminal, from the repository root:", "", "    " + command.rstrip("\n")]
    lines += ["", "Files:", ""]
    for name in names:
        if name.startswith("artifacts/"):
            description = next(
                (a.get("description") for a in record.get("artifacts") or []
                 if isinstance(a, dict) and f"artifacts/{a.get('name')}" == name), None,
            )
            lines.append(f"  {name}\n      a file the run produced: {description or 'no description recorded'}")
        else:
            lines.append(f"  {name}\n      {_FILE_MEANINGS.get(name, '')}")
    lines.append("  README.txt\n      this file")
    lines += ["", "What was left out:", ""]
    lines.append("  Paths on the computer that made this bundle: the home folder is written as ~ and the data "
                 "folder as <data dir>." if redact_paths else
                 "  Nothing: paths on the computer that made this bundle are written as they were.")
    lines.append("  Error tracebacks are included (diagnostics were asked for)." if diagnostics else
                 "  Error tracebacks: the error's type and message are kept; its traceback is not. Export again "
                 "with diagnostics included to add it.")
    return "\n".join(lines) + "\n"


def summary_of(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: record.get(key) for key in
            ("id", "kind", "title", "status", "created_at", "finished_at", "outcome")}


def unreadable_record(run_id: str, reason: str, schema: Optional[str] = None) -> Dict[str, Any]:
    """A record for a run this version cannot read, claiming nothing but that."""
    return {
        "schema": schema or "unknown",
        "id": run_id,
        "kind": kind_of_run_id(run_id),
        "title": f"Unreadable by this version of Caterva Studio: {reason}",
        "status": "failed",
        "created_at": created_from_run_id(run_id),
        "started_at": None,
        "finished_at": None,
        "caterva_version": "",
        "cli": [],
        "request": {},
        "outcome": None,
        "error": {"type": "UnreadableRun", "message": reason, "traceback": None},
        "artifacts": [],
        "progress": None,
    }


def encode_cursor(created_at: str, run_id: str) -> str:
    raw = json.dumps([created_at, run_id], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> Tuple[str, str]:
    """The (created_at, id) a cursor stands for, or Malformed."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        created_at, run_id = value
        if not isinstance(created_at, str) or not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            raise ValueError
        return created_at, run_id
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        raise Malformed("cursor is not one this server issued", field="cursor") from None


__all__ = [
    "DEFAULT_LIMIT", "DEFAULT_SETTINGS", "INTERRUPTED_MESSAGE", "MAX_LIMIT", "MAX_PARALLEL_RUNS", "RunNotFound",
    "TERMINAL_STATUSES", "UnreadableRun", "Workspace", "WorkspaceError", "bundle_readme", "created_from_run_id",
    "decode_cursor", "default_data_dir", "encode_cursor", "iso", "json_bytes", "kind_of_run_id", "summary_of",
    "unreadable_record", "utc_now", "validate_settings", "write_bytes_atomic", "write_json_atomic",
]
