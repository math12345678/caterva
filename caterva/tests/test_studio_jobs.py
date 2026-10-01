"""Runs as jobs: refused up front or queued, run on threads, followed by events, cancelled, timed out.

The adapters here are written for these tests and compute nothing: they
block on events the test controls, so each step of a run's life
(queued, running, a stage, a log line, done / failed / cancelled /
abandoned / timed out / interrupted) can be reached on purpose and its
record, its events on disk and its event stream compared with
docs/studio/CONTRACT.md section 8. Their results hold text, not numbers:
what is tested is the machinery, not a science result.
"""
from __future__ import annotations

import dataclasses
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, List

import pytest

from caterva.studio.adapters import AdapterOutcome, AdapterSpec, Artifact, Registry
from caterva.studio.contract import NEGATIVE_MEANING, SESSION_HEADER, Malformed
from caterva.studio.dispatch import App, Request
from caterva.studio.jobs import (
    KEEP_LOG_LINES, KEEPALIVE_FRAME, SINKS, JobManager, OutputRouter, RUN_DIR_PLACEHOLDER, cli_prefix, make_run_id,
    sse_frame,
)
from caterva.studio.routes import RUN_ID_PATTERN
from caterva.studio.static_files import StaticSite
from caterva.studio.workspace import Workspace

PORT = 18767
TOKEN = "t" * 43
HEADERS = [("Host", f"127.0.0.1:{PORT}"), (SESSION_HEADER, TOKEN)]
TEST_PREFIX = ("caterva-studio-test",)


def wait_for(predicate: Callable[[], Any], timeout: float = 30.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("the condition was not reached in time")


class Gate:
    """An adapter whose run waits for the test at each step."""

    def __init__(self, *, check_cancel: bool = True, prints: bool = False) -> None:
        self.prints = prints
        self.started = threading.Event()
        self.release = threading.Event()
        self.check_cancel = check_cancel
        self.contexts: List[Any] = []

    def run(self, request, ctx):
        self.contexts.append(ctx)
        ctx.progress.stage("waiting", "Waiting for the test")
        if self.prints:
            print("a line the library printed")  # becomes a log line only while stdout is routed
        else:
            ctx.progress.log("a line the library printed")
        self.started.set()
        while not self.release.wait(0.01):
            if self.check_cancel:
                ctx.progress.check_cancelled()
        ctx.progress.stage("finishing", "Finishing", 1.0)
        return AdapterOutcome(0, {"said": request.get("say", "")}, "the test adapter answered",
                              artifacts=(Artifact("note.txt", b"a file\n", "text/plain; charset=utf-8",
                                                  "a file the test adapter wrote"),))


def spec(kind: str, run, *, argv=None, serial=False, needs=(), unavailable=None, describe=None,
         prefix=TEST_PREFIX) -> AdapterSpec:
    def default_argv(request):
        unknown = set(request) - {"say"}
        if unknown:
            raise Malformed(f"{sorted(unknown)[0]!r} is not part of this request", field=sorted(unknown)[0])
        return ["--say", str(request.get("say", ""))]

    return AdapterSpec(kind=kind, title=f"Test {kind}", command=f"caterva {kind}", needs=tuple(needs),
                       argv=argv or default_argv, run=run, unavailable=unavailable or (lambda: None),
                       describe=describe, cli_prefix=prefix, serial=serial)


def make_manager(tmp_path: Path, registry: Registry, **kwargs) -> JobManager:
    ws = Workspace(tmp_path / "data")
    ws.ensure()
    ws.claim("0123456789abcdef")
    kwargs.setdefault("keepalive_s", 0.2)
    kwargs.setdefault("poll_s", 0.05)
    kwargs.setdefault("tick_s", 0.02)
    return JobManager(ws, registry, instance_id="0123456789abcdef", **kwargs)


def events_on_disk(manager: JobManager, run_id: str):
    events, _ = manager.ws.read_events(run_id)
    return events


def parse_frames(frames: List[bytes]):
    out = []
    for frame in frames:
        if frame == KEEPALIVE_FRAME:
            out.append(("keep-alive", None, None))
            continue
        text = frame.decode()
        assert text.endswith("\n\n")
        lines = text[:-2].split("\n")
        assert lines[0].startswith("id: ") and lines[1].startswith("event: ") and lines[2].startswith("data: ")
        assert len(lines) == 3
        out.append((lines[1][7:], int(lines[0][4:]), json.loads(lines[2][6:])))
    return out


@pytest.fixture
def gate():
    return Gate()


@pytest.fixture
def manager(tmp_path, gate):
    registry = Registry()
    registry.register(spec("compose", gate.run))
    manager = make_manager(tmp_path, registry)
    yield manager
    gate.release.set()
    manager.shutdown()


# -- refusing before a run exists ------------------------------------------------


def test_a_malformed_request_never_becomes_a_run(manager):
    with pytest.raises(Malformed) as refused:
        manager.submit("compose", {"say": "x", "colour": "red"})
    assert refused.value.field == "colour"
    assert manager.ws.run_ids() == []


def test_the_commands_own_parser_refuses_what_the_cli_would(tmp_path):
    registry = Registry()
    registry.register(spec("structure", Gate().run, argv=lambda r: ["--no-such-flag"], prefix=("caterva", "structure")))
    manager = make_manager(tmp_path, registry)
    try:
        with pytest.raises(Malformed) as refused:
            manager.submit("structure", {})
        # argparse's own words, as `caterva structure --no-such-flag` prints them before exit 2.
        assert str(refused.value) == "caterva structure: error: the following arguments are required: --subject"
        assert manager.ws.run_ids() == []
    finally:
        manager.shutdown()


def test_an_unregistered_or_unavailable_kind_is_refused_with_its_reason(tmp_path):
    from caterva.studio.contract import Unavailable

    registry = Registry()
    registry.register(spec("bind", Gate().run, unavailable=lambda: "the literature layer is not in this installation"))
    manager = make_manager(tmp_path, registry)
    try:
        with pytest.raises(Unavailable, match="not built yet"):
            manager.submit("sim", {})
        with pytest.raises(Unavailable, match="literature layer"):
            manager.submit("bind", {})
        assert manager.ws.run_ids() == []
    finally:
        manager.shutdown()


def test_offline_mode_refuses_a_kind_that_may_need_the_network(tmp_path):
    from caterva.studio.contract import Unavailable

    offline = [True]
    registry = Registry()
    registry.register(spec("constants", Gate().run, needs=("network", "literature")))
    manager = make_manager(tmp_path, registry, offline=lambda: offline[0])
    try:
        with pytest.raises(Unavailable, match="offline mode is on"):
            manager.submit("constants", {})
        assert manager.ws.run_ids() == []
    finally:
        manager.shutdown()


def test_offline_mode_runs_a_request_that_needs_no_network(tmp_path):
    from caterva.studio.contract import Unavailable

    registry = Registry()
    base = spec("compose", Gate().run, needs=("network", "literature"))
    registry.register(dataclasses.replace(
        base, needs_for=lambda request: ("network",) if request.get("say") == "search" else ()))
    manager = make_manager(tmp_path, registry, offline=lambda: True)
    try:
        with pytest.raises(Unavailable, match="offline mode is on"):
            manager.submit("compose", {"say": "search"})
        assert manager.ws.run_ids() == []
        record = manager.submit("compose", {"say": "local"})
        assert record["status"] == "queued"
    finally:
        manager.shutdown()


def test_the_real_adapters_need_the_network_only_for_requests_that_search():
    from caterva.studio.adapters import load_registry, request_needs

    registry = load_registry()
    compose, md_setup, prepare = registry.get("compose"), registry.get("md.setup"), registry.get("prepare")
    assert request_needs(compose, {"description": "Michaelis-Menten"}) == ()
    assert request_needs(compose, {"description": "Michaelis-Menten", "subject": "2.7.1.1"}) == ("network", "literature")
    assert request_needs(md_setup, {"pdb": "1AKI"}) == ()
    assert request_needs(md_setup, {"pdb": "1AKI", "subject": "3.2.1.17", "substrate": "x"}) == ("network", "literature")
    assert request_needs(prepare, {"entry": "/data/1l63.cif"}) == ()
    assert request_needs(prepare, {"entry": "1L63"}) == ("network",)
    assert request_needs(registry.get("bind"), {}) == ("network", "literature")


def test_an_md_setup_writing_into_the_workspace_is_malformed_before_a_run_exists(tmp_path):
    from caterva.studio.adapters import load_registry

    manager = make_manager(tmp_path, load_registry())
    try:
        with pytest.raises(Malformed, match="inside the studio's workspace") as refused:
            manager.submit("md.setup", {"pdb": "1AKI", "out": str(manager.ws.root / "elsewhere")})
        assert refused.value.field == "out"
        assert manager.ws.run_ids() == []
    finally:
        manager.shutdown()


# -- a run's life ------------------------------------------------------------------


def test_a_run_goes_queued_running_done_with_its_events_in_order(manager, gate):
    record = manager.submit("compose", {"say": "hello"})
    run_id = record["id"]
    assert record["status"] == "queued"
    assert record["cli"] == [*TEST_PREFIX, "--say", "hello"]
    assert record["title"] == "caterva-studio-test --say hello"
    import re
    assert re.fullmatch(RUN_ID_PATTERN, run_id) and "-compose-" in run_id

    gate.started.wait(30)
    assert manager.record(run_id)["status"] == "running"
    assert manager.record(run_id)["progress"] == {"stage": "waiting", "label": "Waiting for the test",
                                                   "fraction": None}
    gate.release.set()
    wait_for(lambda: manager.record(run_id)["status"] == "done")

    final = manager.record(run_id)
    assert final["outcome"] == {"exit_code": 0, "meaning": "produced", "summary": "the test adapter answered",
                                "reason": None}
    assert final["artifacts"] == [{"name": "note.txt", "content_type": "text/plain; charset=utf-8", "bytes": 7,
                                   "description": "a file the test adapter wrote"}]
    assert json.loads(manager.ws.result_path(run_id).read_text()) == {"said": "hello"}
    assert manager.ws.artifact_path(run_id, "note.txt").read_bytes() == b"a file\n"

    events = events_on_disk(manager, run_id)
    names = [name for name, _ in events]
    assert names == ["status", "status", "stage", "log", "stage", "result", "status", "end"]
    assert [d["seq"] for _, d in events] == list(range(1, len(events) + 1))
    assert [d.get("status") for n, d in events if n == "status"] == ["queued", "running", "done"]
    assert events[3][1]["line"] == "a line the library printed"
    assert events[-1][1] == {"run_id": run_id, "seq": len(events), "at": events[-1][1]["at"], "status": "done"}
    assert all(d["at"].endswith("Z") and d["run_id"] == run_id for _, d in events)


def test_the_stream_replays_then_follows_live_then_closes_after_end(manager, gate):
    run_id = manager.submit("compose", {"say": "x"})["id"]
    gate.started.wait(30)
    frames: List[bytes] = []
    done = threading.Event()

    def follow():
        for frame in manager.events(run_id):
            frames.append(frame)
        done.set()

    threading.Thread(target=follow, daemon=True).start()
    wait_for(lambda: len([f for f in frames if f != KEEPALIVE_FRAME]) >= 4)
    assert not done.is_set()
    gate.release.set()
    assert done.wait(30)
    parsed = [p for p in parse_frames(frames) if p[0] != "keep-alive"]
    assert [p[0] for p in parsed] == ["status", "status", "stage", "log", "stage", "result", "status", "end"]
    assert [p[1] for p in parsed] == list(range(1, 9))
    assert [p[1] for p in parsed] == [p[2]["seq"] for p in parsed]


def test_last_event_id_sends_only_what_came_after(manager, gate):
    run_id = manager.submit("compose", {})["id"]
    gate.release.set()
    wait_for(lambda: manager.record(run_id)["status"] == "done")
    parsed = parse_frames(list(manager.events(run_id, after=5)))
    assert [p[1] for p in parsed] == [6, 7, 8]
    assert parsed[-1][0] == "end"


def test_a_quiet_stream_sends_keep_alive_comments(manager, gate):
    run_id = manager.submit("compose", {})["id"]
    gate.started.wait(30)
    frames: List[bytes] = []
    stream = manager.events(run_id)

    def follow():
        for frame in stream:
            frames.append(frame)

    threading.Thread(target=follow, daemon=True).start()
    wait_for(lambda: frames.count(KEEPALIVE_FRAME) >= 2, timeout=10)
    gate.release.set()


def test_an_sse_frame_is_one_json_line_with_its_id_and_name():
    frame = sse_frame(7, "log", {"run_id": "r", "seq": 7, "at": "x", "line": "two\nlines"})
    assert frame == b'id: 7\nevent: log\ndata: {"run_id":"r","seq":7,"at":"x","line":"two\\nlines"}\n\n'
    with pytest.raises(ValueError):
        sse_frame(1, "log", {"value": float("nan")})


def test_a_refusal_keeps_the_clis_reason_and_a_negative_finding_its_words(tmp_path):
    def refuse(request, ctx):
        return AdapterOutcome(3, None, "refused", refusal="Refused: the shape was not recognised")

    def negative(request, ctx):
        return AdapterOutcome(4, {"verdict": "disagrees"}, "the computed value disagrees")

    registry = Registry()
    registry.register(spec("compose", refuse))
    registry.register(spec("bind", negative))
    manager = make_manager(tmp_path, registry)
    try:
        refused = manager.submit("compose", {})["id"]
        found = manager.submit("bind", {})["id"]
        wait_for(lambda: manager.record(refused)["status"] == "done" and manager.record(found)["status"] == "done")
        assert manager.record(refused)["outcome"]["reason"] == "Refused: the shape was not recognised"
        assert manager.record(refused)["outcome"]["meaning"] == "refused"
        assert not manager.ws.result_path(refused).exists()
        assert manager.record(found)["outcome"]["reason"] == NEGATIVE_MEANING["bind"]
        assert manager.record(found)["outcome"]["meaning"] == "negative"
    finally:
        manager.shutdown()


def test_a_crash_is_failed_with_type_message_and_traceback(tmp_path):
    def crash(request, ctx):
        raise ZeroDivisionError("the adapter divided by zero")

    registry = Registry()
    registry.register(spec("compose", crash))
    manager = make_manager(tmp_path, registry)
    try:
        run_id = manager.submit("compose", {})["id"]
        wait_for(lambda: manager.record(run_id)["status"] == "failed")
        error = manager.record(run_id)["error"]
        assert error["type"] == "ZeroDivisionError"
        assert error["message"] == "the adapter divided by zero"
        assert "Traceback" in error["traceback"]
        names = [n for n, _ in events_on_disk(manager, run_id)]
        assert names[-3:] == ["error", "status", "end"]
    finally:
        manager.shutdown()


def test_an_outcome_the_contract_refuses_is_failed_not_kept(tmp_path):
    def bad(request, ctx):
        return AdapterOutcome(3, {"x": "y"}, "no reason given")  # exit 3 without the CLI's reason

    registry = Registry()
    registry.register(spec("compose", bad))
    manager = make_manager(tmp_path, registry)
    try:
        run_id = manager.submit("compose", {})["id"]
        wait_for(lambda: manager.record(run_id)["status"] == "failed")
        assert manager.record(run_id)["error"]["type"] == "ContractViolation"
        assert not manager.ws.result_path(run_id).exists()
    finally:
        manager.shutdown()


def test_the_run_dir_placeholder_becomes_the_runs_own_folder(tmp_path):
    registry = Registry()
    registry.register(spec("md.setup", Gate().run, argv=lambda r: ["--out", f"{RUN_DIR_PLACEHOLDER}/md-setup"]))
    manager = make_manager(tmp_path, registry)
    try:
        record = manager.submit("md.setup", {})
        assert record["cli"][-1] == str(manager.ws.run_dir(record["id"]) / "md-setup")
        assert record["id"].split("-")[2:4] == ["md", "setup"]
    finally:
        manager.shutdown()


def test_describe_titles_the_run_and_a_failing_describe_falls_back_to_the_command(tmp_path):
    registry = Registry()
    registry.register(spec("compose", Gate().run, describe=lambda r: "A titled run"))
    registry.register(spec("sim", Gate().run, describe=lambda r: 1 / 0))
    manager = make_manager(tmp_path, registry)
    try:
        assert manager.submit("compose", {})["title"] == "A titled run"
        assert manager.submit("sim", {"say": "s"})["title"] == "caterva-studio-test --say s"
    finally:
        manager.shutdown()


# -- what a run prints ---------------------------------------------------------------


def test_what_a_run_prints_becomes_its_log_and_other_threads_output_does_not(tmp_path, capsys):
    gate = Gate(prints=True)
    registry = Registry()
    registry.register(spec("compose", gate.run))
    manager = make_manager(tmp_path, registry)
    real = sys.stdout
    sys.stdout = OutputRouter(sys.stderr)
    try:
        run_id = manager.submit("compose", {})["id"]
        gate.started.wait(30)
        print("from the main thread")
        gate.release.set()
        wait_for(lambda: manager.record(run_id)["status"] == "done")
    finally:
        sys.stdout = real
        manager.shutdown()
    lines = [d["line"] for n, d in events_on_disk(manager, run_id) if n == "log"]
    assert lines == ["a line the library printed"]
    assert "from the main thread" in capsys.readouterr().err
    assert SINKS.current() is None


def test_a_run_keeps_at_most_the_limit_of_log_lines_and_counts_the_rest(tmp_path):
    def chatty(request, ctx):
        for i in range(KEEP_LOG_LINES + 25):
            ctx.progress.log(f"line {i}")
        return AdapterOutcome(0, {}, "printed a lot")

    registry = Registry()
    registry.register(spec("compose", chatty))
    manager = make_manager(tmp_path, registry)
    try:
        run_id = manager.submit("compose", {})["id"]
        wait_for(lambda: manager.record(run_id)["status"] == "done", timeout=120)
        lines = [d["line"] for n, d in events_on_disk(manager, run_id) if n == "log"]
        assert len(lines) == KEEP_LOG_LINES + 1
        assert lines[-1] == f"25 more lines of output were not kept (a run keeps {KEEP_LOG_LINES:,})."
    finally:
        manager.shutdown()


# -- cancelling ------------------------------------------------------------------------


def test_cancelling_a_running_run_stops_it_at_its_next_check_and_keeps_no_result(manager, gate):
    run_id = manager.submit("compose", {})["id"]
    gate.started.wait(30)
    record = manager.cancel(run_id)
    assert record["status"] == "running"  # cooperative: it stops at its next check
    wait_for(lambda: manager.record(run_id)["status"] == "cancelled")
    assert not manager.ws.result_path(run_id).exists()
    events = events_on_disk(manager, run_id)
    lines = [d["line"] for n, d in events if n == "log"]
    assert "Cancel requested: the run stops at its next check." in lines
    assert lines[-1] == "Cancelled: the run stopped at its next check and keeps no result."
    assert [n for n, _ in events][-2:] == ["status", "end"]
    from caterva.studio.jobs import Conflict
    with pytest.raises(Conflict, match="already finished"):
        manager.cancel(run_id)


def test_cancelling_a_queued_run_ends_it_before_it_starts(tmp_path):
    gate = Gate()
    registry = Registry()
    registry.register(spec("compose", gate.run))
    manager = make_manager(tmp_path, registry, parallel=lambda: 1)
    try:
        first = manager.submit("compose", {})["id"]
        second = manager.submit("compose", {})["id"]
        gate.started.wait(30)
        assert manager.record(second)["status"] == "queued"
        manager.cancel(second)
        assert manager.record(second)["status"] == "cancelled"
        assert manager.record(second)["started_at"] is None
        gate.release.set()
        wait_for(lambda: manager.record(first)["status"] == "done")
        assert len(gate.contexts) == 1
    finally:
        manager.shutdown()


def test_a_run_that_cannot_stop_is_abandoned_and_says_so(tmp_path):
    gate = Gate(check_cancel=False)
    registry = Registry()
    registry.register(spec("sim", gate.run, serial=True))
    registry.register(spec("compose", Gate().run, serial=True))
    manager = make_manager(tmp_path, registry, cancel_grace_s=0.2)
    try:
        run_id = manager.submit("sim", {})["id"]
        gate.started.wait(30)
        manager.cancel(run_id)
        wait_for(lambda: manager.record(run_id)["status"] == "cancelled")
        lines = [d["line"] for n, d in events_on_disk(manager, run_id) if n == "log"]
        assert "abandoned" in lines[-1] and "Waiting for the test" in lines[-1]
        assert "the next engine run waits for it" in lines[-1]
        # The engine is still busy: a second serial run waits for the call to return.
        waiting = manager.submit("compose", {})["id"]
        time.sleep(0.3)
        assert manager.record(waiting)["status"] == "queued"
        gate.release.set()
        wait_for(lambda: manager.record(waiting)["status"] == "running")
        # What the abandoned call returned was discarded.
        assert not manager.ws.result_path(run_id).exists()
        assert not manager.ws.artifact_path(run_id, "note.txt").exists()
        assert manager.record(run_id)["status"] == "cancelled"
    finally:
        gate.release.set()
        manager.shutdown()


def test_a_stuck_run_times_out_as_failed_saying_whether_it_stopped_or_was_abandoned(tmp_path):
    stops = Gate()
    stuck = Gate(check_cancel=False)
    registry = Registry()
    registry.register(spec("compose", stops.run))
    registry.register(spec("bind", stuck.run))
    # A grace far longer than a check takes, so on a loaded machine the run that
    # checks still stops by itself before it could be abandoned.
    manager = make_manager(tmp_path, registry, timeout_s=0.3, cancel_grace_s=3.0)
    try:
        a = manager.submit("compose", {})["id"]
        b = manager.submit("bind", {})["id"]
        wait_for(lambda: manager.record(a)["status"] == "failed" and manager.record(b)["status"] == "failed")
        assert manager.record(a)["error"]["type"] == "TimedOut"
        assert "stopped at its next check" in manager.record(a)["error"]["message"]
        assert manager.record(b)["error"]["type"] == "TimedOut"
        assert "abandoned" in manager.record(b)["error"]["message"]
    finally:
        stuck.release.set()
        manager.shutdown()


# -- how many run at once ---------------------------------------------------------------


def test_at_most_max_parallel_runs_run_at_once_in_submission_order(tmp_path):
    gates = [Gate() for _ in range(3)]
    order: List[int] = []
    registry = Registry()

    def run(request, ctx):
        order.append(request["n"])
        return gates[request["n"]].run(request, ctx)

    registry.register(spec("bind", run, argv=lambda r: [str(r["n"])]))
    manager = make_manager(tmp_path, registry, parallel=lambda: 2)
    try:
        ids = [manager.submit("bind", {"n": n})["id"] for n in range(3)]
        gates[0].started.wait(30)
        gates[1].started.wait(30)
        time.sleep(0.2)
        assert [manager.record(i)["status"] for i in ids] == ["running", "running", "queued"]
        gates[1].release.set()
        gates[2].started.wait(30)
        assert order == [0, 1, 2]
        gates[0].release.set()
        gates[2].release.set()
        wait_for(lambda: all(manager.record(i)["status"] == "done" for i in ids))
    finally:
        for g in gates:
            g.release.set()
        manager.shutdown()


def test_serial_kinds_never_overlap_while_a_network_kind_runs_beside_them(tmp_path):
    a, b, net = Gate(), Gate(), Gate()
    registry = Registry()
    registry.register(spec("compose", a.run, serial=True))
    registry.register(spec("sim", b.run, serial=True))
    registry.register(spec("constants", net.run, needs=("network",)))
    manager = make_manager(tmp_path, registry, parallel=lambda: 3)
    try:
        first = manager.submit("compose", {})["id"]
        second = manager.submit("sim", {})["id"]
        third = manager.submit("constants", {})["id"]
        a.started.wait(30)
        net.started.wait(30)
        assert manager.record(second)["status"] == "queued"
        assert manager.record(third)["status"] == "running"
        a.release.set()
        b.started.wait(30)
        b.release.set()
        net.release.set()
        wait_for(lambda: all(manager.record(i)["status"] == "done" for i in (first, second, third)))
    finally:
        for g in (a, b, net):
            g.release.set()
        manager.shutdown()


# -- stopping and starting the server -------------------------------------------------------


def test_stopping_the_server_marks_unfinished_runs_interrupted_and_ends_streams(manager, gate):
    running = manager.submit("compose", {})["id"]
    gate.started.wait(30)
    frames: List[bytes] = []
    done = threading.Event()

    def follow():
        frames.extend(manager.events(running))
        done.set()

    threading.Thread(target=follow, daemon=True).start()
    manager.shutdown()
    assert done.wait(10)
    record = manager.ws.read_record(running)
    assert record["status"] == "interrupted"
    assert record["error"]["type"] == "Interrupted"
    names = [p[0] for p in parse_frames(frames) if p[0] != "keep-alive"]
    assert names[-2:] == ["status", "end"]
    from caterva.studio.contract import Unavailable
    with pytest.raises(Unavailable, match="stopping"):
        manager.submit("compose", {})


def test_runs_left_running_by_a_server_that_died_are_marked_interrupted_once(tmp_path):
    ws = Workspace(tmp_path / "data")
    ws.ensure()
    run_id = make_run_id("compose")
    record = {"schema": "caterva.studio.run/1", "id": run_id, "kind": "compose", "title": "t", "status": "running",
              "created_at": "2026-09-30T00:00:00.000Z", "started_at": None, "finished_at": None,
              "caterva_version": "0", "cli": ["caterva", "compose"], "request": {}, "outcome": None,
              "error": None, "artifacts": [], "progress": None}
    ws.create_run(record, {}, owner="fedcba9876543210")  # a server with no lock: gone
    ws.append_event(run_id, "status", {"run_id": run_id, "seq": 1, "at": "x", "status": "queued"})
    manager = JobManager(ws, Registry(), instance_id="0123456789abcdef")
    ws.claim("0123456789abcdef")
    try:
        assert manager.sweep_interrupted() == [run_id]
        assert manager.sweep_interrupted() == []
        assert ws.read_record(run_id)["status"] == "interrupted"
        events = events_on_disk(manager, run_id)
        assert [(n, d["seq"]) for n, d in events] == [("status", 1), ("status", 2), ("end", 3)]
    finally:
        ws.release()


def test_a_live_servers_runs_are_not_marked_interrupted_by_a_second_server(tmp_path):
    ws = Workspace(tmp_path / "data")
    ws.ensure()
    first = Workspace(tmp_path / "data")
    first.claim("aaaaaaaaaaaaaaaa")
    run_id = make_run_id("compose")
    record = {"schema": "caterva.studio.run/1", "id": run_id, "kind": "compose", "title": "t", "status": "running",
              "created_at": "2026-09-30T00:00:00.000Z", "started_at": None, "finished_at": None,
              "caterva_version": "0", "cli": [], "request": {}, "outcome": None, "error": None, "artifacts": [],
              "progress": None}
    ws.create_run(record, {}, owner="aaaaaaaaaaaaaaaa")
    second = JobManager(ws, Registry(), instance_id="bbbbbbbbbbbbbbbb")
    ws.claim("bbbbbbbbbbbbbbbb")
    try:
        assert second.sweep_interrupted() == []
        assert ws.read_record(run_id)["status"] == "running"
        first.release()
        assert second.sweep_interrupted() == [run_id]
    finally:
        ws.release()


def test_cli_prefix_reads_the_command_when_the_spec_sets_none():
    s = AdapterSpec(kind="md.summarise", title="t", command="caterva md --summarise", needs=(),
                    argv=lambda r: [], run=lambda r, c: None)
    assert cli_prefix(s) == ("caterva", "md")


# -- the same life through HTTP ---------------------------------------------------------------


def test_the_run_routes_through_dispatch(tmp_path):
    gate = Gate()
    registry = Registry()
    registry.register(spec("compose", gate.run))
    app = App(workspace=Workspace(tmp_path / "data"), port=PORT, token=TOKEN, registry=registry,
              static_site=StaticSite(tmp_path / "static"),
              capability_options=dict(head=lambda h, t: None, literature_import=lambda: None,
                                      which=lambda n: None, is_executable=lambda p: False),
              job_options=dict(keepalive_s=0.2, poll_s=0.05, tick_s=0.02))
    app.start(apply_environment=False)

    def call(method, target, body=None, *extra):
        headers = list(HEADERS) + list(extra)
        raw = None
        if body is not None:
            raw = json.dumps(body).encode()
            headers += [("Content-Type", "application/json"), ("Content-Length", str(len(raw)))]
        return app.dispatch(Request(method, target, headers, raw))

    try:
        bad = call("POST", "/api/runs", {"kind": "compose", "request": {"colour": "red"}})
        assert bad.status == 400 and bad.json()["error"]["field"] == "colour"
        assert call("POST", "/api/runs", {"kind": "rates", "request": {}}).status == 503
        assert call("POST", "/api/runs", {"kind": "nope", "request": {}}).status == 400
        assert call("POST", "/api/runs", {"kind": "compose", "request": {}, "extra": 1}).status == 400
        assert call("POST", "/api/runs", {"kind": "compose", "request": {}, "title": ""}).status == 400

        created = call("POST", "/api/runs", {"kind": "compose", "request": {"say": "hi"}, "title": "Mine"})
        assert created.status == 202
        run = created.json()["run"]
        assert run["title"] == "Mine" and run["status"] == "queued"
        rid = run["id"]
        gate.started.wait(30)

        assert call("GET", f"/api/runs/{rid}/result").status == 409
        assert call("DELETE", f"/api/runs/{rid}").status == 409
        assert call("GET", f"/api/runs/{rid}/artifacts/note.txt").status == 404

        gate.release.set()
        wait_for(lambda: call("GET", f"/api/runs/{rid}").json()["status"] == "done")
        assert call("GET", f"/api/runs/{rid}/result").json() == {"said": "hi"}
        assert call("POST", f"/api/runs/{rid}/cancel", {}).status == 409

        artifact = call("GET", f"/api/runs/{rid}/artifacts/note.txt")
        assert artifact.status == 200 and artifact.body == b"a file\n"
        assert artifact.header("Content-Disposition") == 'attachment; filename="note.txt"'
        assert artifact.header("Content-Type") == "text/plain; charset=utf-8"
        assert "sandbox" in artifact.header("Content-Security-Policy")
        assert call("GET", f"/api/runs/{rid}/artifacts/other.txt").status == 404

        events = call("GET", f"/api/runs/{rid}/events")
        assert events.header("Content-Type").startswith("text/event-stream")
        assert events.header("Cache-Control") == "no-store"
        parsed = parse_frames(list(events.stream))
        assert [p[0] for p in parsed][-1] == "end"
        resumed = call("GET", f"/api/runs/{rid}/events", None, ("Last-Event-ID", "6"))
        assert [p[1] for p in parse_frames(list(resumed.stream))] == [7, 8]
        assert call("GET", f"/api/runs/{rid}/events", None, ("Last-Event-ID", "x")).status == 400

        listed = call("GET", "/api/runs?kind=compose&status=done").json()
        assert [r["id"] for r in listed["runs"]] == [rid] and listed["next_cursor"] is None
        assert call("GET", "/api/runs?kind=sim").json()["runs"] == []
        for query in ("limit=0", "limit=201", "limit=x", "status=odd", "kind=odd", "cursor=zz", "other=1",
                      "limit=1&limit=2"):
            assert call("GET", f"/api/runs?{query}").status == 400, query

        bundle = call("GET", f"/api/runs/{rid}/bundle")
        assert bundle.header("Content-Type") == "application/zip"
        assert bundle.header("Content-Disposition") == f'attachment; filename="caterva-{rid}.zip"'

        deleted = call("DELETE", f"/api/runs/{rid}")
        assert deleted.status == 200 and deleted.json()["id"] == rid
        assert call("GET", f"/api/runs/{rid}").status == 404
        assert (tmp_path / "data" / "trash" / rid / "run.json").is_file()

        cancelled_id = call("POST", "/api/runs", {"kind": "compose", "request": {}}).json()["run"]["id"]
        gate.release.clear()
        assert call("POST", f"/api/runs/{cancelled_id}/cancel", {"why": 1}).status == 400
        assert call("POST", f"/api/runs/{cancelled_id}/cancel", {}).status == 202
        wait_for(lambda: call("GET", f"/api/runs/{cancelled_id}").json()["status"] == "cancelled")
        missing = call("GET", f"/api/runs/{cancelled_id}/result")
        assert missing.status == 404 and "cancelled" in missing.json()["error"]["message"]
    finally:
        gate.release.set()
        app.close()
