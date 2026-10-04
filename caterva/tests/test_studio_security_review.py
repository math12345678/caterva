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


def req(app: App, method: str, target: str, body: Any = None, *, authed: bool = True, extra=()):
    headers = [HOST] + ([AUTH] if authed else []) + list(extra)
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
    response = req(app, "GET", path, authed=False)
    assert response.status in (200, 404)
    assert TOKEN.encode() not in response.body
    assert TOKEN not in json.dumps(response.headers)


def test_s1_the_built_page_never_carries_a_placeholder_or_a_session_tag(app):
    body = req(app, "GET", "/", authed=False).body.decode()
    assert "__CATERVA_SESSION_TOKEN__" not in body and 'name="caterva-session"' not in body


def test_s1_a_stranger_with_only_a_valid_host_cannot_reach_a_gromacs_run(tmp_path):
    """The reviewer's chain: GET / for the token, PUT settings, GET capabilities."""
    ran: List[Any] = []
    evil = program(tmp_path / "evil.sh")
    app = make_app(tmp_path, run=lambda *a, **k: ran.append(a))
    try:
        assert req(app, "GET", "/", authed=False).status == 200  # nothing in it to use
        refused = req(app, "PUT", "/api/settings", {"theme": "system", "max_parallel_runs": 2,
                                                    "confirm_delete": True, "gromacs_path": str(evil)},
                      authed=False)
        assert refused.status == 401
        assert req(app, "GET", "/api/capabilities", authed=False).status == 401
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
            assert req(again, "POST", "/api/capabilities/refresh", {}, authed=False).status == 401
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
    hostile = f"x$(touch {victim})`touch {victim}`; touch {victim} #"
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


# ---------------------------------------------------------------------------
# S5: a run's work is bounded and a cancel reaches the loop
# ---------------------------------------------------------------------------


def _sim_registry():
    from caterva.studio.adapters import load_registry

    return load_registry()


@pytest.mark.parametrize("request_", [
    {"seed": 1, "a0": 10**12, "k": 0.5, "end": 1.0},
    {"seed": 1, "a0": 2_000_000, "k": 0.5, "end": 50.0},
    {"seed": 1, "a0": 300_000, "k": 1.0, "end": 100.0},
    {"seed": 1, "bimolecular": True, "a0": 5_000_000, "b0": 5_000_000, "k": 1.0, "end": 10.0},
])
def test_s5_a_request_expected_to_make_too_many_events_is_refused_with_the_limit(request_):
    from caterva.studio import contract
    from caterva.studio.adapters import sim

    with pytest.raises(contract.Malformed) as refused:
        sim.argv(request_)
    assert f"{contract.MAX_SSA_EVENTS:,}" in str(refused.value) and refused.value.field == "a0"


def test_s5_a_run_inside_the_limit_is_accepted():
    from caterva.studio.adapters import sim

    assert sim.argv({"seed": 1, "a0": 100, "k": 0.5, "end": 10.0})[0] == "ssa"
    assert sim.argv({"seed": 1, "a0": 10**12, "k": 1e-15, "end": 1.0})[0] == "ssa"  # few events: cheap
    assert sim.argv({"seed": 1, "bimolecular": True, "a0": 10, "b0": 10**9, "k": 1e-9, "end": 5.0})[0] == "ssa"


def test_s5_a_request_over_the_limit_is_a_400_through_the_dispatch_layer(tmp_path):
    from caterva.studio.adapters import load_registry

    app = make_app(tmp_path, registry=load_registry())
    try:
        refused = req(app, "POST", "/api/runs", {"kind": "sim", "request": {"seed": 1, "a0": 10**12, "k": 0.5,
                                                                               "end": 1.0}})
        assert refused.status == 400 and "200,000" in refused.json()["error"]["message"]
    finally:
        app.close()


def test_s5_the_loop_polls_the_flag_and_stops_within_a_few_events():
    import time

    from caterva.discrete.gillespie_ssa import (STOP_CHECK_EVERY, SimulationCancelled, SimulationTooLong,
                                                simulate_gillespie_ssa, simulate_gillespie_ssa_bimolecular)

    polls = []

    def stop_on_third():
        polls.append(1)
        return len(polls) >= 3

    started = time.monotonic()
    with pytest.raises(SimulationCancelled):
        simulate_gillespie_ssa(a0=3_000_000, k=1.0, end=50.0, seed=1, should_stop=stop_on_third)
    assert time.monotonic() - started < 2.0 and len(polls) == 3
    with pytest.raises(SimulationCancelled):
        simulate_gillespie_ssa_bimolecular(a0=3_000_000, b0=3_000_000, k=1e-3, end=50.0, seed=1,
                                           should_stop=lambda: True)
    with pytest.raises(SimulationTooLong):
        simulate_gillespie_ssa(a0=100_000, k=1.0, end=50.0, seed=1, max_events=500)
    assert STOP_CHECK_EVERY <= 1024


def test_s5_no_stop_flag_leaves_the_trajectory_exactly_as_it_was():
    from caterva.discrete.gillespie_ssa import simulate_gillespie_ssa

    plain = simulate_gillespie_ssa(500, 0.4, 5.0, seed=11)
    polled = simulate_gillespie_ssa(500, 0.4, 5.0, seed=11, should_stop=lambda: False, max_events=10**6)
    assert plain.data == polled.data


def test_s5_a_cancelled_sim_run_stops_inside_the_loop_and_is_cancelling_until_it_has(tmp_path, monkeypatch):
    import time

    from caterva.studio import contract
    from caterva.studio.adapters import load_registry
    from caterva.studio.jobs import JobManager

    monkeypatch.setattr(contract, "MAX_SSA_EVENTS", 10**9)  # lets a run long enough to cancel be asked for
    ws = Workspace(tmp_path / "data")
    ws.ensure()
    ws.claim("0123456789abcdef")
    manager = JobManager(ws, load_registry(), instance_id="0123456789abcdef", tick_s=0.02, keepalive_s=0.2)
    try:
        run_id = manager.submit("sim", {"seed": 5, "a0": 40_000_000, "k": 1.0, "end": 50.0})["id"]
        deadline = time.monotonic() + 30
        while manager.record(run_id)["status"] != "running" and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.3)
        started = time.monotonic()
        assert manager.cancel(run_id)["status"] == "cancelling"
        while manager.record(run_id)["status"] == "cancelling" and time.monotonic() < deadline:
            time.sleep(0.01)
        record = manager.record(run_id)
        assert record["status"] == "cancelled" and time.monotonic() - started < 10  # not abandoned, not run out
        assert not manager.ws.result_path(run_id).exists()
        names = [t.name for t in threading.enumerate() if t.name == f"caterva-run-{run_id}"]
        deadline = time.monotonic() + 5
        while names and time.monotonic() < deadline:
            time.sleep(0.01)
            names = [t.name for t in threading.enumerate() if t.name == f"caterva-run-{run_id}"]
        assert names == []  # the thread really ended
    finally:
        manager.shutdown()


def test_s5_timeouts_are_per_kind_and_sane():
    from caterva.studio.contract import RUN_KINDS
    from caterva.studio.jobs import KIND_TIMEOUTS_S, RUN_TIMEOUT_S

    assert set(KIND_TIMEOUTS_S) == set(RUN_KINDS)
    assert KIND_TIMEOUTS_S["sim"] <= 15 * 60 and KIND_TIMEOUTS_S["md.setup"] <= 15 * 60
    assert max(KIND_TIMEOUTS_S.values()) <= 2 * 60 * 60 and RUN_TIMEOUT_S <= 60 * 60
    assert KIND_TIMEOUTS_S["analyze"] > KIND_TIMEOUTS_S["sim"]


# ---------------------------------------------------------------------------
# S6: the enzyme finder cannot be asked for unbounded CPU
# ---------------------------------------------------------------------------


def test_s6_at_most_two_searches_run_at_once_and_the_rest_are_told_to_wait():
    from caterva.studio.limits import Busy, SearchGuard

    guard = SearchGuard(concurrent=2, budget_s=5.0, queue_wait_s=0.05)
    release = threading.Event()
    running, peak, lock = [0], [0], threading.Lock()

    def slow():
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        release.wait(5)
        with lock:
            running[0] -= 1
        return {"ok": True}

    outcomes: List[Any] = []

    def ask(i):
        try:
            outcomes.append(guard.run(("q", i), slow))
        except Busy as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=ask, args=(i,)) for i in range(6)]
    for thread in threads:
        thread.start()
    deadline = 50
    while sum(isinstance(o, Busy) for o in outcomes) < 4 and deadline:
        threading.Event().wait(0.05)
        deadline -= 1
    assert peak[0] == 2 and sum(isinstance(o, Busy) for o in outcomes) == 4
    release.set()
    for thread in threads:
        thread.join(10)
    assert sum(o == {"ok": True} for o in outcomes) == 2


def test_s6_one_normalised_query_is_searched_once_whatever_its_spelling(tmp_path):
    from caterva.studio.adapters import Registry

    calls: List[str] = []
    registry = Registry()
    registry.add_endpoint("find_enzymes", lambda r: calls.append(r.query["q"]) or {"candidates": [r.query["q"]]},
                          owner="compose")
    app = make_app(tmp_path, registry=registry)
    try:
        for q in ("Alcohol+Dehydrogenase", "alcohol%20%20dehydrogenase", "ALCOHOL%09DEHYDROGENASE",
                  "%EF%BC%A1lcohol+dehydrogenase"):  # the last begins with a full-width A
            assert req(app, "GET", f"/api/enzymes/find?q={q}").status == 200
        assert len(calls) == 1 and app.finder.started == 1
        assert req(app, "GET", "/api/enzymes/find?q=lactate+dehydrogenase").status == 200
        assert len(calls) == 2
    finally:
        app.close()


def test_s6_a_search_over_its_budget_is_a_503_with_retry_after_and_its_answer_is_kept(tmp_path):
    from caterva.studio.adapters import Registry
    from caterva.studio.limits import SearchGuard

    release = threading.Event()
    calls: List[int] = []

    def slow(request):
        calls.append(1)
        release.wait(10)
        return {"candidates": ["late"]}

    registry = Registry()
    registry.add_endpoint("find_enzymes", slow, owner="compose")
    app = make_app(tmp_path, registry=registry)
    app.finder = SearchGuard(budget_s=0.1)
    try:
        first = req(app, "GET", "/api/enzymes/find?q=slowly")
        assert first.status == 503 and first.header("Retry-After") == "2"
        release.set()
        deadline = 100
        while app.finder.started and not app.finder._cache and deadline:
            threading.Event().wait(0.05)
            deadline -= 1
        again = req(app, "GET", "/api/enzymes/find?q=Slowly")
        assert again.status == 200 and again.json() == {"candidates": ["late"]} and len(calls) == 1
    finally:
        release.set()
        app.close()


def test_s6_a_search_that_raises_gives_every_waiter_the_same_refusal(tmp_path):
    from caterva.studio.adapters import Registry
    from caterva.studio.contract import Malformed

    registry = Registry()

    def bad(request):
        raise Malformed("q is not searchable", field="q")

    registry.add_endpoint("find_enzymes", bad, owner="compose")
    app = make_app(tmp_path, registry=registry)
    try:
        refused = req(app, "GET", "/api/enzymes/find?q=x")
        assert refused.status == 400 and refused.json()["error"]["field"] == "q"
    finally:
        app.close()


def test_s6_the_cache_is_an_lru_of_bounded_size():
    from caterva.studio.limits import SearchGuard

    guard = SearchGuard(cache_size=2)
    for key in ("a", "b", "a", "c"):
        guard.run(key, lambda key=key: key)
    assert guard.started == 3  # "a" was answered from the cache the second time
    guard.run("b", lambda: "b")  # evicted when "c" arrived
    assert guard.started == 4


# ---------------------------------------------------------------------------
# S7: connections, streams, queued runs, kept runs, slow requests
# ---------------------------------------------------------------------------


def _finished_run_record(app: App, kind: str = "compose") -> str:
    from caterva.studio.contract import RUN_RECORD_SCHEMA
    from caterva.studio.jobs import make_run_id
    from caterva.studio.workspace import iso, utc_now

    run_id = make_run_id(kind)
    now = iso(utc_now())
    record = {"schema": RUN_RECORD_SCHEMA, "id": run_id, "kind": kind, "title": "t", "status": "done",
              "created_at": now, "started_at": now, "finished_at": now, "caterva_version": "0", "cli": [],
              "request": {}, "outcome": None, "error": None, "artifacts": [], "progress": None}
    app.ws.create_run(record, {}, owner=None)
    return run_id


def test_s7_no_more_than_sixteen_event_streams_and_a_closed_one_frees_its_slot(tmp_path):
    from caterva.studio.limits import MAX_STREAMS

    app = make_app(tmp_path)
    try:
        run_id = _finished_run_record(app)
        open_streams = []
        for _ in range(MAX_STREAMS):
            response = req(app, "GET", f"/api/runs/{run_id}/events")
            assert response.status == 200 and response.stream is not None
            open_streams.append(response)
        refused = req(app, "GET", f"/api/runs/{run_id}/events")
        assert refused.status == 503 and refused.header("Retry-After") == "2"
        assert "event streams" in refused.json()["error"]["message"]
        open_streams[0].stream.close()
        open_streams[0].stream.close()  # closing twice gives back one slot, not two
        taken = req(app, "GET", f"/api/runs/{run_id}/events")
        assert taken.status == 200
        assert req(app, "GET", f"/api/runs/{run_id}/events").status == 503
        # A stream read to its end gives its slot back too.
        list(open_streams[1].stream)
        assert req(app, "GET", f"/api/runs/{run_id}/events").status == 200
        del taken
    finally:
        app.close()


def test_s7_a_stream_that_was_never_started_still_gives_its_slot_back(tmp_path):
    from caterva.studio.limits import Gate, GuardedStream

    gate = Gate(1)
    assert gate.enter()
    stream = GuardedStream((b"x" for _ in range(3)), gate)  # a generator never advanced
    stream.close()
    assert gate.count == 0 and gate.enter()


def test_s7_too_many_waiting_runs_are_refused_with_retry_after(tmp_path):
    from caterva.studio.adapters import AdapterOutcome, AdapterSpec, Registry
    from caterva.studio.jobs import JobManager, QueueFull

    release = threading.Event()

    def run(request, ctx):
        release.wait(20)
        return AdapterOutcome(0, {}, "done")

    registry = Registry()
    registry.register(AdapterSpec(kind="compose", title="t", command="compose", needs=(), argv=lambda r: [],
                                  run=run, cli_prefix=("caterva", "compose")))
    ws = Workspace(tmp_path / "data")
    ws.ensure()
    ws.claim("0123456789abcdef")
    manager = JobManager(ws, registry, instance_id="0123456789abcdef", parallel=lambda: 1, max_pending=2,
                         tick_s=0.02)
    try:
        for _ in range(3):  # one running, two waiting
            manager.submit("compose", {})
        with pytest.raises(QueueFull) as refused:
            manager.submit("compose", {})
        assert "at most 2" in str(refused.value) and refused.value.retry_after_s == 30
    finally:
        release.set()
        manager.shutdown()


def test_s7_the_queue_refusal_is_a_503_with_retry_after_over_dispatch(tmp_path):
    from caterva.studio.adapters import AdapterOutcome, AdapterSpec, Registry

    release = threading.Event()
    registry = Registry()
    registry.register(AdapterSpec(kind="compose", title="t", command="compose", needs=(), argv=lambda r: [],
                                  run=lambda r, c: release.wait(20) and AdapterOutcome(0, {}, "x"),
                                  cli_prefix=("caterva", "compose")))
    app = make_app(tmp_path, registry=registry, job_options={"max_pending": 1})
    app.settings()  # the settings are the defaults: two runs at once
    try:
        statuses = [req(app, "POST", "/api/runs", {"kind": "compose", "request": {}}).status for _ in range(4)]
        assert statuses[:3] == [202, 202, 202] and statuses[3] == 503
        last = req(app, "POST", "/api/runs", {"kind": "compose", "request": {}})
        assert last.header("Retry-After") == "30"
    finally:
        release.set()
        app.close()


def test_s7_finished_runs_beyond_keep_runs_go_to_the_trash_and_a_live_one_never_does(tmp_path):
    from caterva.studio.adapters import AdapterOutcome, AdapterSpec, Registry
    from caterva.studio.jobs import JobManager

    registry = Registry()
    registry.register(AdapterSpec(kind="compose", title="t", command="compose", needs=(), argv=lambda r: [],
                                  run=lambda r, c: AdapterOutcome(0, {}, "x"), cli_prefix=("caterva", "compose")))
    ws = Workspace(tmp_path / "data")
    ws.ensure()
    ws.claim("0123456789abcdef")
    manager = JobManager(ws, registry, instance_id="0123456789abcdef", keep_runs=lambda: 3, tick_s=0.02)
    try:
        import time

        for _ in range(6):
            run_id = manager.submit("compose", {})["id"]
            deadline = time.monotonic() + 20
            while manager.record(run_id)["status"] != "done" and time.monotonic() < deadline:
                time.sleep(0.01)
            time.sleep(0.01)  # run ids sort by second: keep them distinct and ordered
            threading.Event().wait(1.01)
        assert len(ws.run_ids()) == 4  # the three kept, and the one accepted last
        assert len(list((tmp_path / "data" / "trash").iterdir())) == 2  # runs 5 and 6 each moved one out
    finally:
        manager.shutdown()


@pytest.mark.parametrize("value,ok", [(10, True), (5000, True), (9, False), (5001, False), (True, False),
                                      (2.5, False), ("200", False)])
def test_s7_keep_runs_is_a_setting_with_a_range(app, value, ok):
    body = {"theme": "system", "max_parallel_runs": 2, "confirm_delete": True, "keep_runs": value}
    response = req(app, "PUT", "/api/settings", body)
    assert (response.status == 200) is ok
    if not ok:
        assert response.json()["error"]["field"] == "keep_runs"
    # A page that does not know the key leaves it alone.
    kept = req(app, "PUT", "/api/settings", {"theme": "dark", "max_parallel_runs": 2, "confirm_delete": True})
    assert kept.json()["keep_runs"] == (value if ok else 200)


def test_s7_a_connection_over_the_ceiling_is_answered_503_and_closed(tmp_path):
    from caterva.studio import server as server_module

    class Quiet(server_module.StudioHTTPServer):
        def __init__(self):  # no socket: the sandbox cannot bind
            self.connections = server_module.limits.Gate(1)

        def shutdown_request(self, request):
            request.closed = True

    class FakeSocket:
        def __init__(self):
            self.sent = b""
            self.closed = False

        def settimeout(self, seconds):
            pass

        def sendall(self, data):
            self.sent += data

    quiet = Quiet()
    assert quiet.connections.enter()  # the one allowed connection is taken
    refused = FakeSocket()
    quiet.process_request(refused, ("127.0.0.1", 1))
    head, _, body = refused.sent.partition(b"\r\n\r\n")
    assert head.startswith(b"HTTP/1.1 503") and b"Retry-After: 2" in head and b"Connection: close" in head
    assert b"X-Content-Type-Options: nosniff" in head
    assert json.loads(body)["error"]["code"] == "unavailable" and refused.closed
    assert quiet.connections.count == 1


class _Drip:
    """A connection whose bytes arrive one at a time, `step` seconds apart, on a fake clock."""

    def __init__(self, data: bytes, now, step: float) -> None:
        self.data, self.pos, self.now, self.step = data, 0, now, step

    def peek(self, n=1):
        self.now[0] += self.step
        return self.data[self.pos:self.pos + 1]

    def read(self, n=-1):
        chunk = self.data[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk


def test_s7_a_request_that_drips_in_is_cut_off_by_its_total_deadline_not_its_pauses():
    import socket as socket_module

    from caterva.studio.limits import DeadlineReader

    now = [0.0]
    timeouts: List[float] = []

    class FakeSock:
        def settimeout(self, value):
            timeouts.append(value)

    # One byte a second, never a newline in the header line: every pause is far inside the 60 s idle limit.
    raw = _Drip(b"GET / HTTP/1.1\r\n" + b"X-Slow: " + b"a" * 500, now, 1.0)
    reader = DeadlineReader(raw, FakeSock(), idle_s=60.0, header_s=10.0, clock=lambda: now[0])
    reader.begin()
    assert reader.readline() == b"GET / HTTP/1.1\r\n"  # 16 s of idle time: the header clock starts after it
    with pytest.raises(socket_module.timeout):
        reader.readline()
    assert 10.0 <= now[0] - 16.0 <= 12.0  # cut off about ten seconds in, though the line never ended
    assert min(timeouts) <= 1.0 and max(timeouts) == 60.0  # each wait shrank to the time that was left


def test_s7_a_body_that_drips_in_is_cut_off_the_same_way():
    import socket as socket_module

    from caterva.studio.limits import DeadlineReader

    now = [0.0]

    class FakeSock:
        def settimeout(self, value):
            pass

    reader = DeadlineReader(_Drip(b"x" * 1000, now, 2.0), FakeSock(), idle_s=60.0, clock=lambda: now[0])
    reader.begin()
    reader.arm(30.0)
    with pytest.raises(socket_module.timeout):
        reader.read(1000)
    assert 30.0 <= now[0] <= 33.0
    reader.disarm()
    now[0] = 0.0
    quick = DeadlineReader(_Drip(b"hello world", now, 0.1), FakeSock(), idle_s=60.0, clock=lambda: now[0])
    quick.begin()
    quick.arm(30.0)
    assert quick.read(5) == b"hello"
    assert quick.read(6) == b" world"


def test_s7_the_ceilings_are_the_stated_ones():
    from caterva.studio import limits
    from caterva.studio.jobs import MAX_PENDING

    assert (limits.MAX_CONNECTIONS, limits.MAX_STREAMS, MAX_PENDING) == (64, 16, 32)
    assert limits.HEADER_DEADLINE_S <= 15 and limits.BODY_DEADLINE_S <= 60


# ---------------------------------------------------------------------------
# S9: nothing from the PDB or a request can end a ChimeraX comment
# ---------------------------------------------------------------------------


def _structure(title="Lactate dehydrogenase", name="L-lactate dehydrogenase A chain", component="OXM",
               bound_name="OXAMIC ACID"):
    from caterva.structure.search import BoundMolecule, Citation, Protein, Structure

    citation = Citation(title=title, journal="Biochemistry", year=2001, doi="10.1021/bi010000x", pubmed=None,
                        first_author="Read")
    structure = Structure(pdb_id="1I10", title=title, method="X-RAY DIFFRACTION", resolution=2.1,
                          organisms=("Homo sapiens",), uniprot=("P00338",),
                          bound=(BoundMolecule(component, bound_name, "ligand"),), citation=citation)
    return structure, Protein(accession="P00338", gene="LDHA", name=name, organism="Homo sapiens")


@pytest.mark.parametrize("evil", ["a\nopen https://example.org/x.cxc", "a\rrun /bin/sh", "a close", "a close",
                                  "a\x00b\x1bc", "a\x85b", "a\x0bb\x0cc"])
def test_s9_no_field_can_start_a_command_line(evil):
    from caterva.structure.chimerax import script

    structure, protein = _structure(title=evil, name=evil, bound_name=evil)
    text = script(structure, protein, focus=evil)
    for line in text.splitlines():
        if not line.startswith("#"):
            assert line.split(" ")[0] in ("open", "hide", "cartoon", "color", "set", "lighting", "graphics", "show",
                                          "style", "label", "view"), line
    assert not any(c in text for c in "\r\x00\x1b\x85  \x0b\x0c")
    assert "open https://example.org" not in [line for line in text.splitlines() if not line.startswith("#")]


def test_s9_an_id_that_stands_in_a_command_is_ascii_letters_and_digits_only():
    from caterva.structure.chimerax import identifier, one_line

    assert identifier("OXM; open x") == "OXMopenx" and identifier("1i10\n") == "1i10" and identifier("é") == ""
    structure, protein = _structure(component="OXM\nopen x")
    text = __import__("caterva.structure.chimerax", fromlist=["script"]).script(structure, protein)
    assert "show :OXMopenx" in text and "\nopen x" not in text
    assert one_line("a\n\n b\tc") == "a b c"


def test_s9_an_ordinary_script_is_unchanged():
    from caterva.structure.chimerax import script

    structure, protein = _structure()
    text = script(structure, protein)
    assert "# Caterva: L-lactate dehydrogenase A chain (LDHA, UniProt P00338), Homo sapiens" in text
    assert "open 1i10" in text and "show :OXM" in text and "color :OXM orange" in text


# ---------------------------------------------------------------------------
# S10: an exported bundle does not carry this computer's paths or tracebacks
# ---------------------------------------------------------------------------


def _crashed_run(app: App, home: str):
    from caterva.studio.contract import RUN_RECORD_SCHEMA
    from caterva.studio.jobs import make_run_id
    from caterva.studio.workspace import iso, utc_now

    run_id = make_run_id("compose")
    now = iso(utc_now())
    trace = f'Traceback (most recent call last):\n  File "{home}/work/caterva/x.py", line 3, in run\nValueError: bad'
    record = {"schema": RUN_RECORD_SCHEMA, "id": run_id, "kind": "compose", "title": "t", "status": "failed",
              "created_at": now, "started_at": now, "finished_at": now, "caterva_version": "0",
              "cli": ["caterva", "compose", "--out", f"{home}/Desktop/out"], "request": {"out": f"{home}/Desktop/out"},
              "outcome": None, "error": {"type": "ValueError", "message": f"bad file {home}/data.csv",
                                         "traceback": trace},
              "artifacts": [{"name": "report.md", "content_type": "text/markdown; charset=utf-8", "bytes": 10,
                             "description": "d"}], "progress": None}
    run_dir = app.ws.create_run(record, record["request"], owner=None)
    (run_dir / "artifacts").mkdir()
    (run_dir / "artifacts" / "report.md").write_text(f"made in {home}/Desktop/out\n")
    app.ws.append_event(run_id, "error", {"run_id": run_id, "seq": 1, "at": now, "error": record["error"]})
    return run_id, trace


def _zip_texts(data: bytes):
    import zipfile

    archive = zipfile.ZipFile(io.BytesIO(data))
    return {name: archive.read(name).decode("utf-8") for name in archive.namelist()}


def test_s10_a_bundle_defaults_to_no_home_folder_and_no_traceback(tmp_path):
    home = os.path.expanduser("~")
    app = make_app(tmp_path)
    try:
        run_id, trace = _crashed_run(app, home)
        response = req(app, "GET", f"/api/runs/{run_id}/bundle")
        assert response.status == 200
        files = _zip_texts(response.body)
        everything = "\n".join(files.values())
        assert home not in everything and "Traceback" not in everything and "x.py" not in everything
        assert "~/Desktop/out" in files["command.txt"] and "~/Desktop/out" in files["artifacts/report.md"]
        assert json.loads(files["run.json"])["error"]["traceback"] is None
        assert json.loads(files["run.json"])["error"]["type"] == "ValueError"
        events = [json.loads(line) for line in files["events.jsonl"].splitlines()]
        assert events[0]["data"]["error"]["traceback"] is None
        readme = files["README.txt"]
        assert "home folder is written as ~" in readme and "traceback is not" in readme
    finally:
        app.close()


def test_s10_ticking_diagnostics_keeps_the_traceback_with_paths_still_redacted(tmp_path):
    home = os.path.expanduser("~")
    app = make_app(tmp_path)
    try:
        run_id, trace = _crashed_run(app, home)
        files = _zip_texts(req(app, "GET", f"/api/runs/{run_id}/bundle?diagnostics=true").body)
        record = json.loads(files["run.json"])
        assert "ValueError: bad" in record["error"]["traceback"] and home not in "\n".join(files.values())
        assert "~/work/caterva/x.py" in record["error"]["traceback"]
        assert "tracebacks are included" in files["README.txt"].lower()
    finally:
        app.close()


def test_s10_redaction_can_be_turned_off_explicitly_and_says_so(tmp_path):
    home = os.path.expanduser("~")
    app = make_app(tmp_path)
    try:
        run_id, _ = _crashed_run(app, home)
        files = _zip_texts(req(app, "GET", f"/api/runs/{run_id}/bundle?redact_paths=false&diagnostics=true").body)
        assert home in files["command.txt"] and "written as they were" in files["README.txt"]
        for bad in ("redact_paths=yes", "diagnostics=1", "x=1"):
            assert req(app, "GET", f"/api/runs/{run_id}/bundle?{bad}").status == 400
    finally:
        app.close()


def test_s10_a_data_folder_outside_the_home_folder_is_written_as_a_placeholder(tmp_path):
    app = make_app(tmp_path)
    try:
        run_id, _ = _crashed_run(app, str(app.ws.root))  # paths inside the data folder
        files = _zip_texts(app.ws.bundle(run_id, home="/not/this/home"))
        assert str(app.ws.root) not in "\n".join(files.values())
        assert "<data dir>/Desktop/out" in files["command.txt"]
    finally:
        app.close()


# ---------------------------------------------------------------------------
# S11: the macOS shell (the sources are read as text; `swiftc -typecheck` is run by the guard
# scripts/build_studio_app.py and by hand with the flags in the contract)
# ---------------------------------------------------------------------------

SWIFT_DIR = Path(__file__).resolve().parents[2] / "macos" / "Sources"


def _swift(name: str) -> str:
    return (SWIFT_DIR / name).read_text(encoding="utf-8")


def test_s11_development_variables_count_only_in_a_development_build_with_an_explicit_switch():
    source = _swift("StudioServer.swift")
    assert "#if CATERVA_DEVELOPMENT" in source
    body = source[source.index("static func developmentEnabled"):source.index("let executable: URL")]
    assert "return false" in body and 'environment[developmentKey] == "1"' in body and "markerExists" in body
    resolve = source[source.index("static func resolve("):source.index("/// Caterva.app/Contents/Resources")]
    # the command and data-directory variables are read only behind that switch
    assert "let development = developmentEnabled(environment: environment)" in resolve
    assert "development, let raw = environment[commandKey]" in resolve and "development\n" in resolve
    env = source[source.index("func environment("):source.index("final class StudioServer")]
    for prefix in ("PYTHON", "DYLD_", "CATERVA_STUDIO_"):
        assert f'hasPrefix("{prefix}")' in env


def test_s11_only_a_development_app_is_compiled_with_the_flag_and_sets_the_switch(tmp_path):
    import sys

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        import build_studio_app as studio_app
    finally:
        sys.path.remove(str(scripts))
    release = studio_app.swiftc_command([Path("a.swift")], Path("out"), "arm64", Path("cache"))
    development = studio_app.swiftc_command([Path("a.swift")], Path("out"), "arm64", Path("cache"), development=True)
    assert "CATERVA_DEVELOPMENT" not in " ".join(release) and "CATERVA_DEVELOPMENT" in " ".join(development)
    python = tmp_path / "python"
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)
    assert studio_app.dev_environment(python, Path(__file__).resolve().parents[2], None)["CATERVA_STUDIO_DEV"] == "1"


def test_s11_reveal_is_limited_to_the_data_folder_and_what_the_person_chose():
    source = _swift("WebBridge.swift")
    assert "WebBridge.isRevealable(path, roots: revealRoots)" in source
    assert "resolvingSymlinksInPath()" in source and "hasPrefix(base.hasSuffix" in source
    assert "self?.revealRoots.append(url)" in source
    assert "controller.allowReveal(Paths.dataFolder(command))" in _swift("AppDelegate.swift")


def test_s11_only_https_and_mailto_leave_the_page():
    source = _swift("StudioWindowController.swift")
    assert '["https", "mailto"].contains' in source and '"http", "https"' not in source


def test_s11_the_web_store_does_not_outlive_the_launch_and_the_token_is_never_kept_or_logged():
    window = _swift("StudioWindowController.swift")
    assert "configuration.websiteDataStore = .nonPersistent()" in window and ".default()" not in window
    assert "self.baseURL = StudioServer.withoutFragment(url)" in window
    assert "components.fragment = nil   // never keep a fragment" in window
    server = _swift("StudioServer.swift")
    assert 'writeLog("listening at \\(StudioServer.withoutFragment(url).absoluteString)\\n")' in server
    assert 'writeLog("listening at \\(url.absoluteString)' not in server


def test_s11_the_smoke_checks_the_token_arrangement_over_a_real_socket():
    source = _swift("Smoke.swift")
    for needle in ('"/api/health"', '"X-Caterva-Session"', "refusedStatus != 401", "answered != 200",
                   "html.contains(token)", 'static let fragmentKey = "token"'):
        assert needle in source or needle.replace('"', "") in source, needle


def test_s11_swift_typechecks_with_the_build_flags(tmp_path):
    """Opt in with CATERVA_TEST_SWIFT=1 (it takes a couple of minutes); the DMG workflow compiles the
    same sources with the same flags on every release."""
    import platform
    import shutil
    import subprocess

    if os.environ.get("CATERVA_TEST_SWIFT") != "1":
        pytest.skip("set CATERVA_TEST_SWIFT=1 to typecheck the Swift sources")
    if platform.system() != "Darwin" or shutil.which("xcrun") is None:
        pytest.skip("swiftc is only on macOS")
    sources = sorted(str(p) for p in SWIFT_DIR.glob("*.swift"))
    for flags in ([], ["-D", "CATERVA_DEVELOPMENT"]):
        done = subprocess.run(["xcrun", "swiftc", "-typecheck", "-swift-version", "5", "-target",
                               "arm64-apple-macos12.0", "-module-cache-path", str(tmp_path / "modules"), *flags,
                               *sources], capture_output=True, text=True, timeout=900)
        assert done.returncode == 0, done.stderr[-2000:]
