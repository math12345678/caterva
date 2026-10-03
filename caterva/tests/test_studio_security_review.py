"""Regression tests for the security review of Caterva Studio.

Each test reproduces one attack the reviewer proved through the dispatch
layer (no socket is needed) and asserts that it no longer works. They are
grouped by finding: S1 to S11 in the review, and the SECURITY section of
docs/studio/CONTRACT.md records the rules they protect.
"""
from __future__ import annotations

import io
import json
import os
import stat
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

import pytest

from caterva.studio import __main__ as studio_main
from caterva.studio.adapters import Registry
from caterva.studio.contract import SESSION_HEADER
from caterva.studio.dispatch import App, Request
from caterva.studio.security import bootstrap_url, mint_token
from caterva.studio.static_files import StaticSite
from caterva.studio.workspace import Workspace

PORT = 18771
TOKEN = mint_token()
HOST = ("Host", f"127.0.0.1:{PORT}")
AUTH = (SESSION_HEADER, TOKEN)
INDEX = ('<!doctype html><html><head><meta name="caterva-studio-page" content="token-in-url-fragment">'
         '<script type="module" src="/assets/index-abc.js"></script></head><body></body></html>')

GMX_OUT = "GROMACS version:    2025.3\n"


def make_app(tmp_path: Path, *, run=None, registry=None, job_options=None, **kwargs: Any) -> App:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True, exist_ok=True)
    (static / "index.html").write_text(INDEX, encoding="utf-8")
    (static / "assets" / "index-abc.js").write_text("export const ok = true;\n", encoding="utf-8")
    options = dict(head=lambda host, timeout: None, literature_import=lambda: None, which=lambda name: None,
                   is_executable=lambda path: False)
    if run is not None:
        options["run"] = run
    app = App(workspace=Workspace(tmp_path / "data"), port=PORT, token=TOKEN, static_site=StaticSite(static),
              registry=registry or Registry(), capability_options=options, job_options=job_options, **kwargs)
    app.start(apply_environment=False)
    return app


def req(app: App, method: str, target: str, body: Any = None, *, token: bool = True, extra=()):
    headers = [HOST] + ([AUTH] if token else []) + list(extra)
    raw = None
    if body is not None:
        raw = json.dumps(body).encode()
        headers += [("Content-Type", "application/json"), ("Content-Length", str(len(raw)))]
    return app.dispatch(Request(method, target, headers, raw))


def program(path: Path, mode: int = 0o755) -> Path:
    path.write_text("#!/bin/sh\necho 'GROMACS version: 2025.3'\n")
    path.chmod(mode)
    return path


@pytest.fixture
def app(tmp_path):
    app = make_app(tmp_path)
    yield app
    app.close()


# ---------------------------------------------------------------------------
# S1: the session token is in no document the server serves
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/compose", "/index.html", "/assets/index-abc.js", "/history/x"])
def test_s1_no_document_the_server_serves_holds_the_token(app, path):
    response = req(app, "GET", path, token=False)
    assert response.status in (200, 404)
    assert TOKEN.encode() not in response.body
    assert TOKEN not in json.dumps(response.headers)


def test_s1_the_built_page_never_carries_a_placeholder_or_a_session_tag(app):
    body = req(app, "GET", "/", token=False).body.decode()
    assert "__CATERVA_SESSION_TOKEN__" not in body and 'name="caterva-session"' not in body


def test_s1_a_stranger_with_only_a_valid_host_cannot_reach_a_gromacs_run(tmp_path):
    """The reviewer's chain: GET / for the token, PUT settings, GET capabilities."""
    ran: List[Any] = []
    evil = program(tmp_path / "evil.sh")
    app = make_app(tmp_path, run=lambda *a, **k: ran.append(a))
    try:
        assert req(app, "GET", "/", token=False).status == 200  # nothing in it to use
        refused = req(app, "PUT", "/api/settings", {"theme": "system", "max_parallel_runs": 2,
                                                    "confirm_delete": True, "gromacs_path": str(evil)},
                      token=False)
        assert refused.status == 401
        assert req(app, "GET", "/api/capabilities", token=False).status == 401
        assert ran == []
    finally:
        app.close()


def test_s1_the_address_for_the_launcher_carries_the_token_in_its_fragment(app):
    url = app.bootstrap_url
    assert url == f"http://127.0.0.1:{PORT}/#token={TOKEN}"
    assert url == bootstrap_url("127.0.0.1", PORT, TOKEN)
    assert "#" not in app.url and TOKEN not in app.url
    assert bootstrap_url("::1", 7, "abc") == "http://[::1]:7/#token=abc"


def test_s1_the_printed_line_has_the_token_and_the_log_and_stderr_do_not(tmp_path, monkeypatch):
    import sys

    from caterva.studio import server as server_module

    class QuietServer(server_module.StudioHTTPServer):
        def __init__(self, host, port):  # no socket: the sandbox cannot bind
            self.app = None
            self.address_family = 2
            self.server_address = (host, 18791)

        @property
        def port(self):
            return 18791

        def serve_forever(self, poll_interval=0.5):
            pass

        def shutdown(self):
            pass

        def server_close(self):
            pass

    monkeypatch.setattr(server_module, "StudioHTTPServer", QuietServer)
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    stop = threading.Event()
    seen: List[App] = []

    def serving(app):
        seen.append(app)
        stop.set()

    code = studio_main.main(["--port", "0", "--no-browser", "--print-url", "--data-dir", str(tmp_path / "d")],
                            stop=stop, on_serving=serving)
    assert code == 0
    token = seen[0].token
    assert out.getvalue() == f"CATERVA_STUDIO_URL=http://127.0.0.1:18791/#token={token}\n"
    assert token not in err.getvalue()
    assert token not in (tmp_path / "d" / "studio.log").read_text()


def test_s1_the_browser_is_given_a_private_file_not_an_argument_with_the_token(tmp_path):
    opened: List[str] = []
    app = SimpleNamespace(bootstrap_url=f"http://127.0.0.1:{PORT}/#token={TOKEN}", url=f"http://127.0.0.1:{PORT}/")
    studio_main._open_browser(app, tmp_path, opener=lambda url: opened.append(url) or True, ttl_s=0.05)
    assert len(opened) == 1 and opened[0].startswith("file://") and TOKEN not in opened[0]
    page = Path(opened[0][len("file://"):])
    from urllib.parse import unquote
    page = Path(unquote(str(page)))
    assert page.name.startswith(".open-studio-")
    assert f"#token={TOKEN}" in page.read_text()
    assert stat.S_IMODE(page.stat().st_mode) == 0o600
    deadline = 50
    while page.exists() and deadline:
        threading.Event().wait(0.05)
        deadline -= 1
    assert not page.exists()


def test_s1_a_browser_that_cannot_open_logs_the_address_without_the_token(tmp_path, caplog):
    app = SimpleNamespace(bootstrap_url=f"http://127.0.0.1:{PORT}/#token={TOKEN}", url=f"http://127.0.0.1:{PORT}/")
    with caplog.at_level("WARNING", logger="caterva.studio"):
        studio_main._open_browser(app, tmp_path, opener=lambda url: False, ttl_s=0.05)
    assert "--print-url" in caplog.text and TOKEN not in caplog.text


def test_s1_the_launch_page_is_not_written_through_a_planted_link(tmp_path):
    target = tmp_path / "victim.txt"
    target.write_text("keep")
    real = studio_main.secrets.token_hex
    studio_main.secrets.token_hex = lambda n=8: "fixed"
    try:
        (tmp_path / ".open-studio-fixed.html").symlink_to(target)
        with pytest.raises(OSError):
            studio_main.write_launch_page(tmp_path, "http://127.0.0.1:1/#token=x")
    finally:
        studio_main.secrets.token_hex = real
    assert target.read_text() == "keep"


# -- gromacs_path -----------------------------------------------------------------------


def put_gmx(app: App, path: str):
    return req(app, "PUT", "/api/settings", {"theme": "system", "max_parallel_runs": 2, "confirm_delete": True,
                                             "gromacs_path": path})


@pytest.mark.parametrize("name", ["gmx", "gmx_mpi", "gmx_d", "gmx_custom"])
def test_s1_a_gmx_program_named_like_gromacs_is_accepted(app, tmp_path, name):
    gmx = program(tmp_path / "bin" / name) if (tmp_path / "bin").mkdir() is None else None
    assert put_gmx(app, str(gmx)).status == 200


@pytest.mark.parametrize("name", ["evil.sh", "gmxevil", "mdrun", "gmx.sh", "xgmx", "gmx_"])
def test_s1_a_program_with_any_other_name_is_refused(app, tmp_path, name):
    other = program(tmp_path / name)
    response = put_gmx(app, str(other))
    assert response.status == 400 and response.json()["error"]["field"] == "gromacs_path"


def test_s1_a_link_named_gmx_to_another_program_is_refused(app, tmp_path):
    evil = program(tmp_path / "evil.sh")
    link = tmp_path / "gmx"
    link.symlink_to(evil)
    response = put_gmx(app, str(link))
    assert response.status == 400 and "link" in response.json()["error"]["message"]


def test_s1_a_world_writable_program_or_folder_is_refused(app, tmp_path):
    loose = program(tmp_path / "gmx", 0o777)
    assert put_gmx(app, str(loose)).status == 400
    folder = tmp_path / "open"
    folder.mkdir()
    inside = program(folder / "gmx")
    folder.chmod(0o777)
    try:
        assert put_gmx(app, str(inside)).status == 400
    finally:
        folder.chmod(0o755)


def test_s1_relative_dotdot_directory_and_non_executable_paths_are_refused(app, tmp_path):
    good = program(tmp_path / "gmx")
    assert put_gmx(app, "gmx").status == 400
    assert put_gmx(app, f"{tmp_path}/sub/../gmx").status == 400
    assert put_gmx(app, str(tmp_path)).status == 400
    plain = tmp_path / "other" / "gmx"
    plain.parent.mkdir()
    plain.write_text("x")
    plain.chmod(0o644)
    assert put_gmx(app, str(plain)).status == 400
    assert put_gmx(app, str(good)).status == 200


def test_s1_reading_capabilities_never_runs_the_chosen_program(tmp_path):
    ran: List[list] = []

    def run(argv, **kwargs):
        ran.append(list(argv))
        return SimpleNamespace(returncode=0, stdout=GMX_OUT, stderr="")

    gmx = program(tmp_path / "gmx")
    app = make_app(tmp_path, run=run)
    try:
        assert put_gmx(app, str(gmx)).status == 200
        assert ran == [[str(gmx), "--version"]]  # the explicit save probed it once, as an argument list
        for _ in range(3):
            assert req(app, "GET", "/api/capabilities").json()["gromacs"]["found"] is True
        assert len(ran) == 1
        # A restart: the saved path is known, and reading capabilities still runs nothing.
        again = make_app(tmp_path, run=run)
        try:
            body = req(again, "GET", "/api/capabilities").json()["gromacs"]
            assert body["found"] is False and "has not been checked" in body["reason"]
            assert len(ran) == 1
            refreshed = req(again, "POST", "/api/capabilities/refresh", {})
            assert refreshed.status == 200 and refreshed.json()["gromacs"]["found"] is True
            assert len(ran) == 2
            assert req(again, "POST", "/api/capabilities/refresh", {"x": 1}).status == 400
            assert req(again, "POST", "/api/capabilities/refresh", {}, token=False).status == 401
        finally:
            again.close()
    finally:
        app.close()


def test_s1_a_chosen_program_that_changed_after_it_was_saved_is_validated_again_before_it_runs(tmp_path):
    ran: List[list] = []
    gmx = program(tmp_path / "gmx")
    app = make_app(tmp_path, run=lambda argv, **k: ran.append(list(argv)) or SimpleNamespace(
        returncode=0, stdout=GMX_OUT, stderr=""))
    try:
        assert put_gmx(app, str(gmx)).status == 200
        ran.clear()
        gmx.chmod(0o777)  # someone made it writable by everyone afterwards
        body = req(app, "POST", "/api/capabilities/refresh", {}).json()["gromacs"]
        assert body["found"] is False and "is not run" in body["reason"] and ran == []
    finally:
        app.close()


# ---------------------------------------------------------------------------
# S8: the development origin
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,ok", [
    ("http://127.0.0.1:18741", True), ("http://localhost:5173", True), ("http://127.0.0.1:65535", True),
    ("http://127.0.0.1:1", True),
    ("http://127.0.0.1:18741\n", False), ("http://127.0.0.1:0", False), ("http://127.0.0.1:99999", False),
    ("http://127.0.0.1:65536", False), ("http://127.0.0.1:18741/", False), ("https://127.0.0.1:18741", False),
    ("http://127.0.0.1:١٨٧٤١", False), ("http://example.com:80", False), (" http://127.0.0.1:18741", False),
])
def test_s8_the_dev_origin_is_a_whole_loopback_origin_with_a_real_port(text, ok):
    assert studio_main.valid_dev_origin(text) is ok


@pytest.mark.parametrize("bad", ["http://127.0.0.1:18741\n", "http://127.0.0.1:0", "http://127.0.0.1:99999"])
def test_s8_the_command_line_refuses_them_with_exit_2(bad, capsys):
    with pytest.raises(SystemExit) as stopped:
        studio_main.main(["--dev-origin", bad, "--no-browser"])
    assert stopped.value.code == 2


# ---------------------------------------------------------------------------
# S2: nothing a request holds reaches the generated script as shell
# ---------------------------------------------------------------------------

HOSTILE_CHAINS = ['A"; touch /tmp/PWNED; echo "', "A\nB", "A B", "A;", "$(id)", "AAAAA", "", "é", "A'", "`id`"]
HOSTILE_PDBS = ["1I10\n", "1I10 ", " 1I10", "١I10", "1I1٣", "1I10;id", "1I1", "11I10", "I110", "1I1'",
                "1i10\n", "1I10\x00"]


def _md_request(**changes):
    return {"pdb": "1I10", **changes}


@pytest.mark.parametrize("chain", HOSTILE_CHAINS)
def test_s2_a_chain_that_is_not_one_to_four_letters_or_digits_is_refused_before_a_run_exists(tmp_path, chain):
    from caterva.studio import contract
    from caterva.studio.adapters import md as adapter

    with pytest.raises(contract.Malformed):
        adapter.setup_argv(_md_request(chain=chain))


@pytest.mark.parametrize("pdb", HOSTILE_PDBS)
def test_s2_a_pdb_id_is_four_ascii_characters_exactly(tmp_path, pdb):
    from caterva.studio import contract
    from caterva.studio.adapters import md as adapter

    with pytest.raises(contract.Malformed):
        adapter.setup_argv(_md_request(pdb=pdb))


@pytest.mark.parametrize("chain", HOSTILE_CHAINS[:6])
def test_s2_the_same_refusal_comes_from_the_command_line_library(chain, capsys):
    from caterva.md.__main__ import main

    code = main(["--pdb", "1I10", "--chain", chain, "--out", "/tmp/never-written-s2"])
    assert code == 2 and not Path("/tmp/never-written-s2").exists()


def test_s2_the_library_refuses_a_setup_object_with_a_bad_id_too():
    from caterva.md.setup import Conditions, MdSetup

    for kwargs in ({"pdb_id": "1I10\n"}, {"pdb_id": "1I10", "chain": 'A"; touch x; "'}):
        with pytest.raises(ValueError):
            MdSetup(**{"pdb_id": "1I10", "chain": "A", "conditions": Conditions(), **kwargs})


@pytest.mark.parametrize("flag,value", [("--ns", "nan"), ("--ns", "inf"), ("--ns", "-1"), ("--ns", "0"),
                                        ("--ionic-strength", "nan"), ("--ionic-strength", "-0.1"),
                                        ("--temperature", "inf"), ("--ph", "99"), ("--seed", "-5"),
                                        ("--replicas", "100000")])
def test_s2_numbers_that_would_be_written_into_the_files_are_finite_and_bounded(flag, value, capsys):
    from caterva.md.__main__ import main

    assert main(["--pdb", "1I10", "--out", "/tmp/never-written-s2b", flag, value]) == 2
    assert not Path("/tmp/never-written-s2b").exists()


def test_s2_every_value_in_run_sh_is_quoted_and_a_hostile_one_runs_nothing(tmp_path):
    """Even a value the checks would refuse (set on the object directly) is inert."""
    import subprocess

    from caterva.md.setup import Conditions, MdSetup

    victim = tmp_path / "PWNED"
    hostile = f"x'; touch {victim}; echo '"
    setup = MdSetup("1I10", "A", Conditions(), force_field=hostile, water=hostile, replicas=1)
    script = tmp_path / "run.sh"
    script.write_text(setup.files()["run.sh"])
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    (tmp_path / "1I10.pdb").write_text("ATOM      1  N   ALA A   1       0.0   0.0   0.0\n")
    fake = tmp_path / "gmx"
    fake.write_text("#!/bin/sh\ncat > /dev/null\nexit 0\n")
    fake.chmod(0o755)
    done = subprocess.run(["bash", str(script)], env={**os.environ, "GMX": str(fake)}, capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert not victim.exists()


def test_s2_a_normal_setup_script_still_reads_as_before(tmp_path):
    from caterva.md.setup import Conditions, MdSetup

    text = MdSetup("1i10", "A", Conditions()).files()["run.sh"]
    assert "awk -v chain=A '" in text and "1I10.pdb" in text and "-ff amber99sb-ildn -water tip3p" in text


def test_s2_the_complex_build_script_quotes_what_came_from_files(tmp_path):
    import subprocess

    from caterva.fep.complex import build_script
    from caterva.md.setup import Conditions, MdSetup

    hostile = f"mol'; touch {tmp_path / 'PWNED'}; echo '"
    text = build_script("1I10", hostile, f"lig'and\".itp", MdSetup("1I10", "A", Conditions(), replicas=1), hostile)
    script = tmp_path / "build.sh"
    script.write_text(text)
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    assert not (tmp_path / "PWNED").exists()
    assert hostile not in text  # only ever present inside quotes


def test_s2_a_name_that_would_close_a_topology_include_or_a_comment_is_refused_or_flattened():
    from caterva.fep.setup import _file_name, _one_line

    assert _one_line("A\n; rm -rf ~\n") == "A ; rm -rf ~ "
    with pytest.raises(ValueError):
        _file_name('lig".itp')
    assert _file_name("lig.itp") == "lig.itp"


# ---------------------------------------------------------------------------
# S3: analyze runs replica folders and selections it has checked, with no shell
# ---------------------------------------------------------------------------


def test_s3_a_folder_that_is_not_rep_number_is_refused_with_a_plain_message(tmp_path):
    from caterva.analyze.__main__ import AnalyzeError, replicas

    (tmp_path / "rep1").mkdir()
    (tmp_path / "rep1" / "md.xtc").write_text("x")
    (tmp_path / "rep1" / "md.tpr").write_text("x")
    assert [r.name for r in replicas(tmp_path)] == ["rep1"]
    (tmp_path / "rep1;touch PWNED;#").mkdir()
    with pytest.raises(AnalyzeError) as refused:
        replicas(tmp_path)
    assert "not a replica" in str(refused.value) and "rep1, rep2" in str(refused.value)
    assert not (tmp_path / "PWNED").exists()


@pytest.mark.parametrize("name", ["rep", "rep1a", "rep-1", "rep1;id", "rep١", "rep 1", "REP1"])
def test_s3_replica_names_are_rep_and_digits_only(tmp_path, name):
    from caterva.analyze.__main__ import AnalyzeError, commands

    plan = SimpleNamespace(pairs=[], angles=[], faces=[], sites=[], pocket=[], rest=[])
    with pytest.raises(AnalyzeError):
        commands(plan, [name])


def _hostile_plan(selection: str):
    one = SimpleNamespace(selection=lambda: selection, arm_selection=lambda: selection)
    return SimpleNamespace(pairs=[one], angles=[one], faces=[one], sites=[], pocket=[], rest=[])


def test_s3_a_selection_string_is_one_shell_word_whatever_it_holds(tmp_path):
    import shlex

    from caterva.analyze.__main__ import commands

    hostile = "resname X'; touch PWNED; echo '"
    lines = commands(_hostile_plan(hostile), ["rep1"])
    words = [shlex.split(line) for line in lines]
    assert any(hostile in w for w in words)
    assert all(not any(token in ("touch", "PWNED;") for token in w) for w in words)


def test_s3_gromacs_steps_run_as_argument_lists_without_bash(tmp_path, monkeypatch):
    from caterva.analyze import __main__ as analyze

    seen = []

    def fake_run(argv, **kwargs):
        seen.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(analyze.subprocess, "run", fake_run)
    hostile = f"resname X'; touch {tmp_path / 'PWNED'}; echo '"
    analyze.run_gromacs(tmp_path, _hostile_plan(hostile), [Path("rep1")], "/opt/gmx dir/gmx")
    assert seen and all(argv[0] == "/opt/gmx dir/gmx" and argv[0] != "bash" for argv, _ in seen)
    assert all("-c" not in argv[:2] for argv, _ in seen)
    assert any(hostile in argv for argv, _ in seen)
    trjconv = next(kw for argv, kw in seen if argv[1] == "trjconv")
    assert trjconv["input"] == "Protein\n"
    assert not (tmp_path / "PWNED").exists()


def test_s3_a_command_of_an_unexpected_shape_is_not_run():
    from caterva.analyze.__main__ import AnalyzeError, command_argv

    assert command_argv("printf 'Protein\\n' | $GMX trjconv -s a", "/x/gmx") == (["/x/gmx", "trjconv", "-s", "a"],
                                                                              "Protein\n")
    assert command_argv("$GMX distance -select 'a b'", "gmx") == (["gmx", "distance", "-select", "a b"], None)
    for line in ("rm -rf x", "echo hi | $GMX x", "printf 'a' | printf 'b' | $GMX x", "$GMX x | cat"):
        with pytest.raises(AnalyzeError):
            command_argv(line, "gmx")


# ---------------------------------------------------------------------------
# S4: md.setup never writes through a link inside the folder
# ---------------------------------------------------------------------------


def _previous_setup(folder: Path):
    from caterva.md.__main__ import plan, write, build_parser

    args = build_parser().parse_args(["--pdb", "1I10", "--chain", "A", "--out", str(folder)])
    planned = plan(args)
    write(planned.setup, folder)
    return planned


def test_s4_a_run_sh_that_is_a_link_is_not_written_through(tmp_path):
    from caterva.md.__main__ import UnsafeOutput, write

    out = tmp_path / "setup"
    planned = _previous_setup(out)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    (out / "run.sh").unlink()
    (out / "run.sh").symlink_to(victim)
    with pytest.raises(UnsafeOutput):
        write(planned.setup, out)
    assert victim.read_text() == "keep me"
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".caterva-md-")]


def test_s4_a_linked_subfolder_or_a_link_anywhere_below_is_refused(tmp_path):
    from caterva.md.__main__ import UnsafeOutput, write

    out = tmp_path / "setup"
    planned = _previous_setup(out)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (out / "rep1" / "nvt.mdp").unlink()
    (out / "rep1" / "nvt.mdp").symlink_to(elsewhere / "target.mdp")
    with pytest.raises(UnsafeOutput):
        write(planned.setup, out)
    assert list(elsewhere.iterdir()) == []


def test_s4_through_the_studio_adapter_the_run_fails_without_writing(tmp_path):
    from caterva.studio import contract
    from caterva.studio.adapters import RunContext
    from caterva.studio.adapters import md as adapter

    class Progress:
        def stage(self, *a, **k): pass
        def log(self, line): pass
        def check_cancelled(self): pass

    out = tmp_path / "setup"
    _previous_setup(out)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    (out / "run.sh").unlink()
    (out / "run.sh").symlink_to(victim)
    run_dir = tmp_path / "data" / "runs" / "20260930-120000-md-setup-0badc0de"
    run_dir.mkdir(parents=True)
    ctx = RunContext(run_dir.name, run_dir, tmp_path / "data", Progress())
    with pytest.raises(contract.Malformed) as refused:
        adapter.setup_run({"pdb": "1I10", "chain": "A", "out": str(out)}, ctx)
    assert refused.value.field == "out" and victim.read_text() == "keep me"


def test_s4_the_command_line_says_so_and_exits_3(tmp_path, capsys):
    from caterva.md.__main__ import main

    out = tmp_path / "setup"
    _previous_setup(out)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    (out / "md.mdp").unlink()
    (out / "md.mdp").symlink_to(victim)
    assert main(["--pdb", "1I10", "--chain", "A", "--out", str(out)]) == 3
    assert "symbolic link" in capsys.readouterr().err and victim.read_text() == "keep me"


def test_s4_a_second_setup_over_a_previous_one_replaces_its_files_and_keeps_run_sh_runnable(tmp_path):
    from caterva.md.__main__ import build_parser, plan, write

    out = tmp_path / "setup"
    _previous_setup(out)
    (out / "em.mdp").write_text("stale")
    args = build_parser().parse_args(["--pdb", "1I10", "--chain", "A", "--out", str(out), "--ns", "5"])
    names = write(plan(args).setup, out)
    assert "run.sh" in names and (out / "em.mdp").read_text() != "stale"
    assert os.access(out / "run.sh", os.X_OK) and not (out / "run.sh").is_symlink()
    assert "nsteps          = 2500000" in (out / "md.mdp").read_text()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".caterva-md-")]
