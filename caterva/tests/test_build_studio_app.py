"""The macOS app's build: what goes into Caterva.app and what it may say.

scripts/build_studio_app.py, the studio parts of scripts/build_app.py and
the Swift shell under macos/ only run on a Mac with the Command Line Tools,
in the studio-dmg workflow. These tests hold, on any machine, the parts that
decide what a person downloads and reads:

- the Info.plist carries the package's version and nothing left unfilled;
- the DMG's README and the first-run sheet never claim a signature or
  notarisation the app does not have (the repository holds no Developer ID);
- a frozen folder without its licences or without the built page is
  refused, and `caterva studio --self-test` output is read line by line,
  not by exit status alone;
- the shell speaks the contract's protocol: the URL line, the token
  placeholder, the session meta tag and the bridge's name are the values
  caterva/studio/contract.py fixes, so the two sides cannot drift apart.
"""
from __future__ import annotations

import importlib.util
import os
import plistlib
import re
import stat
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from caterva.studio import contract  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


studio_app = _load("build_studio_app")
build_app = _load("build_app")

TEMPLATE = (REPO / "macos" / "Info.plist").read_text(encoding="utf-8")
SWIFT = {path.name: path.read_text(encoding="utf-8") for path in (REPO / "macos" / "Sources").glob("*.swift")}


# --- Info.plist ------------------------------------------------------------

def test_info_plist_carries_the_package_version():
    version = studio_app.package_version()
    import caterva

    assert version == caterva.__version__
    data = plistlib.loads(studio_app.render_info_plist(TEMPLATE, version, "1234"))
    assert data["CFBundleShortVersionString"] == version
    assert data["CFBundleVersion"] == "1234"
    assert data["CFBundleExecutable"] == "Caterva"
    assert data["CFBundleIconFile"] == "Caterva"
    assert "LSEnvironment" not in data


def test_info_plist_allows_local_networking_and_nothing_wider():
    data = plistlib.loads(studio_app.render_info_plist(TEMPLATE, "1.2.3", "1"))
    assert data["NSAppTransportSecurity"] == {"NSAllowsLocalNetworking": True}


def test_info_plist_refuses_a_placeholder_left_unfilled():
    with pytest.raises(ValueError, match="@EXTRA@"):
        studio_app.render_info_plist(TEMPLATE + "<!-- @EXTRA@ -->", "1.2.3", "1")


@pytest.mark.parametrize("version", ["0.4.0rc1", "v0.4.0", "0.4.0.1", ""])
def test_info_plist_refuses_a_version_macos_would_not_accept(version):
    with pytest.raises(ValueError, match="version"):
        studio_app.render_info_plist(TEMPLATE, version, "1")


def test_a_development_app_carries_its_command_in_ls_environment(tmp_path):
    python = tmp_path / "python"
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)
    env = studio_app.dev_environment(python, REPO, tmp_path / "data")
    data = plistlib.loads(studio_app.render_info_plist(TEMPLATE, "1.2.3", "1", env))
    assert data["LSEnvironment"]["CATERVA_STUDIO_CWD"] == str(REPO)
    assert data["LSEnvironment"]["CATERVA_STUDIO_DATA_DIR"] == str(tmp_path / "data")
    assert data["LSEnvironment"]["CATERVA_STUDIO_COMMAND"] == (
        f'["{python}", "-m", "caterva.app", "studio"]'
    )


def test_a_development_app_refuses_a_folder_that_is_not_a_checkout(tmp_path):
    with pytest.raises(SystemExit):
        studio_app.dev_environment(Path(sys.executable), tmp_path, None)


# --- what a person reads before opening the app -----------------------------

@pytest.mark.parametrize("relative", ["macos/dmg/README.txt", "macos/Resources/first-run.txt"])
def test_the_texts_claim_no_signature_and_say_how_to_open_it(relative):
    text = (REPO / relative).read_text(encoding="utf-8")
    assert studio_app.unsigned_wording_problems(text, relative) == []
    assert "Control-click" in text
    assert "Open Anyway" in text
    assert "://caterva.app" not in text.lower()


def test_the_wording_check_catches_a_claim():
    problems = studio_app.unsigned_wording_problems(
        "Install it. Caterva is notarised by Apple. It is not signed with a Developer ID.", "x")
    assert problems == ["x: 'Caterva is notarised by Apple.' claims a signature or notarisation"]


def test_the_dmg_name_is_the_one_release_yml_looks_for():
    name = studio_app.dmg_name("0.4.0")
    assert name == "Caterva-0.4.0-macos-arm64.dmg"
    release = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "release/Caterva-*-macos-arm64.dmg" in release
    assert re.fullmatch(r"Caterva-\d+\.\d+\.\d+-macos-arm64\.dmg", name)


# --- the frozen folder ------------------------------------------------------

def _frozen(tmp_path: Path, page: str | None) -> Path:
    folder = tmp_path / "caterva"
    (folder / "licenses").mkdir(parents=True)
    exe = folder / "caterva"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    for name in ("LICENSE", "NOTICE", "licenses/README.txt"):
        (folder / name).write_text("terms\n", encoding="utf-8")
    if page is not None:
        static = folder / "_internal" / "caterva" / "studio" / "static"
        (static / "assets").mkdir(parents=True)
        (static / "index.html").write_text(page, encoding="utf-8")
        (static / "assets" / "index-abc123.js").write_text("export {}\n", encoding="utf-8")
    return folder


def test_a_frozen_folder_with_its_page_and_licences_is_accepted(tmp_path):
    page = f'<meta name="{contract.PAGE_MARKER_NAME}" content="{contract.PAGE_MARKER_CONTENT}">'
    folder = _frozen(tmp_path, page)
    assert studio_app.frozen_problems(folder) == []
    assert build_app.studio_page_problem(folder) is None


def test_a_frozen_folder_without_the_page_is_refused(tmp_path):
    folder = _frozen(tmp_path, None)
    assert any("index.html is missing" in p for p in studio_app.frozen_problems(folder))
    assert "missing" in build_app.studio_page_problem(folder)
    assert studio_app.frozen_problems(folder, require_page=False) == []


def test_a_page_without_the_page_marker_is_refused(tmp_path):
    folder = _frozen(tmp_path, "<html>someone else's page</html>")
    assert any("caterva-studio-page" in p for p in studio_app.frozen_problems(folder))
    assert "page marker" in build_app.studio_page_problem(folder)


def test_a_frozen_folder_without_its_licences_is_refused(tmp_path):
    folder = _frozen(tmp_path, None)
    os.remove(folder / "NOTICE")
    problems = studio_app.frozen_problems(folder, require_page=False)
    assert len(problems) == 1 and "NOTICE is missing" in problems[0]


# --- reading the self-tests -------------------------------------------------

PASSED_BUILT = """ok   start: listening on http://127.0.0.1:50123/
ok   /api/health: 200, version 0.4.0, api_version 1
ok   /api/health without the session token: HTTP 401 (401 expected)
ok   /: HTTP 200, the built page with the session token written in
ok   stop: the server stopped cleanly
"""
PASSED_NOT_BUILT = PASSED_BUILT.replace(
    "the built page with the session token written in",
    "the page is not built here, so the server's own page explaining how to build it")


def test_a_passing_self_test_with_the_page_is_accepted():
    assert build_app.studio_self_test_problems(0, PASSED_BUILT, require_page=True) == []


def test_the_not_built_page_passes_only_when_the_page_is_not_required():
    assert build_app.studio_self_test_problems(0, PASSED_NOT_BUILT, require_page=False) == []
    problems = build_app.studio_self_test_problems(0, PASSED_NOT_BUILT, require_page=True)
    assert problems == ["the server served its not-built page; this folder must carry the built page"]


def test_exit_zero_with_a_failed_line_is_refused():
    out = PASSED_BUILT.replace("ok   /api/health without", "FAIL /api/health without")
    problems = build_app.studio_self_test_problems(0, out, require_page=True)
    assert problems == ["failed checks: FAIL /api/health without the session token: HTTP 401 (401 expected)"]


def test_exit_zero_that_checked_nothing_is_refused():
    problems = build_app.studio_self_test_problems(0, "", require_page=False)
    assert "no passing /api/health check was reported" in problems
    assert "no passing check of / was reported" in problems


def test_a_failing_exit_status_is_refused_even_when_every_line_passed():
    assert build_app.studio_self_test_problems(1, PASSED_BUILT, require_page=True) == ["exit 1"]


def test_the_shell_smoke_passes_only_on_its_ok_line():
    ok = "caterva smoke: url http://127.0.0.1:5/ after 1.0 s\ncaterva smoke: OK\n"
    assert studio_app.smoke_passed(ok)
    assert not studio_app.smoke_passed("caterva smoke: FAIL the server printed no address\ncaterva smoke: OK\n")
    assert not studio_app.smoke_passed("caterva smoke: FAILED; log: x\n")
    assert not studio_app.smoke_passed("")


# --- the shell and the contract --------------------------------------------

def test_the_shell_reads_the_url_line_the_server_prints():
    assert f'static let urlPrefix = "{contract.URL_LINE_PREFIX}"' in SWIFT["StudioServer.swift"]
    assert '"--port", String(port), "--no-browser", "--print-url"' in SWIFT["StudioServer.swift"]


def test_the_shell_smoke_knows_the_page_marker_and_the_token_fragment():
    marker = f'<meta name="{contract.PAGE_MARKER_NAME}" content="{contract.PAGE_MARKER_CONTENT}"'
    assert f'static let marker = "name=\\"{contract.PAGE_MARKER_NAME}\\""' in SWIFT["Smoke.swift"]
    assert f'static let fragmentKey = "{contract.TOKEN_FRAGMENT_KEY}"' in SWIFT["Smoke.swift"]
    assert build_app.PAGE_MARKER == marker
    assert studio_app.PAGE_MARKER == marker


def test_the_bridge_answers_the_page_by_the_name_and_actions_the_page_uses():
    page = (REPO / "Science-Agent-Pipeline" / "artifacts" / "caterva-studio" / "src" / "lib" / "desktop.ts").read_text(
        encoding="utf-8")
    assert 'static let name = "caterva"' in SWIFT["WebBridge.swift"]
    assert "messageHandlers?.caterva" in page
    for action in ("chooseDirectory", "chooseFile", "reveal"):
        assert f'action: "{action}"' in page
        assert f'case "{action}":' in SWIFT["WebBridge.swift"]


def test_the_shell_runs_the_bundled_server_where_the_build_puts_it():
    assert 'appendingPathComponent("caterva/caterva")' in SWIFT["StudioServer.swift"]
    assert 'contents / "Resources" / "caterva"' in (REPO / "scripts" / "build_studio_app.py").read_text(encoding="utf-8")


def test_the_window_keeps_the_contract_minimum_size():
    assert "NSSize(width: 1024, height: 680)" in SWIFT["StudioWindowController.swift"]


def test_every_resource_the_shell_loads_is_copied_into_the_bundle():
    loaded = set(re.findall(r'url\(forResource: "([^"]+)", withExtension: "([^"]+)"\)', "".join(SWIFT.values())))
    assert loaded == {("first-run", "txt")}
    assert {f"{name}.{ext}" for name, ext in loaded} <= set(studio_app.RESOURCES)
    for name in studio_app.RESOURCES:
        assert (REPO / "macos" / "Resources" / name).is_file()


def test_the_swift_compile_targets_the_minimum_macos_the_plist_declares():
    data = plistlib.loads(studio_app.render_info_plist(TEMPLATE, "1.2.3", "1"))
    command = studio_app.swiftc_command([Path("a.swift")], Path("out"), "arm64", Path("cache"))
    assert f"arm64-apple-macos{data['LSMinimumSystemVersion']}" in command
    assert command[:2] == ["xcrun", "swiftc"]
