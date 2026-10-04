"""In-app updates for Caterva.app: the feed, the archive, the build and the release rules.

The updater itself (Sparkle inside the Swift shell) only runs on a Mac, with a
window; scripts/build_studio_app.py builds it in the studio-dmg workflow. These
tests hold, on any machine, what decides whether an update can be trusted and
found:

- scripts/make_appcast.py describes the archive it is given, from the archive's
  own Info.plist, and refuses a tag, a name, a feed or a signature that does
  not fit;
- scripts/fetch_sparkle.py refuses anything but the pinned archive;
- the build links, embeds and seals Sparkle in the order the bundle needs;
- the shell, the page and the contract agree on the bridge messages;
- release.yml signs only on tag builds, reads the key from standard input,
  stops when it is missing, and no other workflow can see it.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import plistlib
import re
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


appcast = _load("make_appcast")
sparkle = _load("fetch_sparkle")
studio_app = _load("build_studio_app")
release_guard = _load("check_release_artifacts")

SWIFT = {path.name: path.read_text(encoding="utf-8") for path in (REPO / "macos" / "Sources").glob("*.swift")}
RELEASE = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
DMG_WORKFLOW = (REPO / ".github" / "workflows" / "studio-dmg.yml").read_text(encoding="utf-8")
TEMPLATE = (REPO / "macos" / "Info.plist").read_text(encoding="utf-8")
SIGNATURE = base64.b64encode(bytes(range(64))).decode()
PUBLIC_KEY = base64.b64encode(bytes(range(32))).decode()


def _archive(tmp_path: Path, version: str = "0.5.1", build: str = "412", feed: str | None = None,
             name: str | None = None) -> Path:
    info = {
        "CFBundleShortVersionString": version,
        "CFBundleVersion": build,
        "LSMinimumSystemVersion": "14.0",
        "SUFeedURL": feed or appcast.STABLE_FEED,
        "SUPublicEDKey": PUBLIC_KEY,
    }
    path = tmp_path / (name or f"Caterva-{version}-macos-arm64.zip")
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("Caterva.app/Contents/Info.plist", plistlib.dumps(info))
        bundle.writestr("Caterva.app/Contents/MacOS/Caterva", b"binary")
    return path


NOTES = "# Caterva v0.5.1\n\n**Caterva.app updates itself.** See [the notes](x) for `more`.\n\n## Later\n\nNot this.\n"


def _write(tmp_path: Path, *extra: str, tag: str = "v0.5.1", archive: Path | None = None) -> Path:
    archive = archive or _archive(tmp_path)
    notes = tmp_path / "notes.md"
    notes.write_text(NOTES, encoding="utf-8")
    out = tmp_path / "appcast.xml"
    code = appcast.main(["--zip", str(archive), "--signature", SIGNATURE, "--tag", tag, "--notes", str(notes),
                         "--out", str(out), "--pub-date", "2026-10-04T12:00:00+00:00", *extra])
    assert code == 0
    return out


# --- the appcast -------------------------------------------------------------

def test_the_appcast_describes_the_archive_it_is_given(tmp_path):
    out = _write(tmp_path)
    root = ElementTree.fromstring(out.read_text(encoding="utf-8"))
    ns = {"s": appcast.SPARKLE_NS}
    (item,) = root.findall("./channel/item")
    assert item.find("s:version", ns).text == "412"
    assert item.find("s:shortVersionString", ns).text == "0.5.1"
    assert item.find("s:minimumSystemVersion", ns).text == "14.0"
    assert item.find("s:hardwareRequirements", ns).text == "arm64"
    assert item.find("pubDate").text == "Sun, 04 Oct 2026 12:00:00 GMT"
    enclosure = item.find("enclosure")
    assert enclosure.get("url") == ("https://github.com/math12345678/caterva/releases/download/v0.5.1/"
                                    "Caterva-0.5.1-macos-arm64.zip")
    assert enclosure.get("length") == str((tmp_path / "Caterva-0.5.1-macos-arm64.zip").stat().st_size)
    assert enclosure.get(f"{{{appcast.SPARKLE_NS}}}edSignature") == SIGNATURE
    assert appcast.check_appcast(out.read_text(encoding="utf-8")) == []


def test_the_release_notes_summary_is_the_first_paragraph_in_plain_words(tmp_path):
    text = _write(tmp_path).read_text(encoding="utf-8")
    assert "Caterva.app updates itself. See the notes for more." in text
    assert "Not this." not in text
    assert "stops any run in progress" in text
    assert "releases/tag/v0.5.1" in text


def test_a_candidate_is_shown_by_its_tag_and_ordered_by_its_build(tmp_path):
    text = _write(tmp_path, tag="v0.5.1-rc.1").read_text(encoding="utf-8")
    assert "<sparkle:shortVersionString>0.5.1-rc.1</sparkle:shortVersionString>" in text
    assert "<sparkle:version>412</sparkle:version>" in text
    assert "/download/v0.5.1-rc.1/Caterva-0.5.1-macos-arm64.zip" in text
    assert appcast.is_prerelease("v0.5.1-rc.1") and not appcast.is_prerelease("v0.5.1")


def test_notes_cannot_break_out_of_the_description():
    nasty = "# t\n\n</p><script>alert(1)</script> ]]> done\n"
    text = appcast.build_appcast(tag="v0.5.1", build="1", minimum_system="14.0", length=5, signature=SIGNATURE,
                                 notes=nasty, published=datetime(2026, 10, 4, tzinfo=timezone.utc),
                                 archive_name="Caterva-0.5.1-macos-arm64.zip")
    root = ElementTree.fromstring(text)
    description = root.find("./channel/item/description").text
    assert "<script>" not in description and "&lt;script&gt;" in description
    assert appcast.check_appcast(text) == []


def test_a_long_first_paragraph_is_cut_at_a_sentence():
    text = "One sentence here. " * 40
    short = appcast.shorten(text)
    assert len(short) <= appcast.SUMMARY_LIMIT and short.endswith(".")
    assert appcast.shorten("short") == "short"


@pytest.mark.parametrize("tag", ["0.5.1", "v0.5", "v0.5.1.2", "v0.5.1-", "main", "v0.5.1 rc"])
def test_a_tag_that_is_not_a_release_tag_is_refused(tag):
    with pytest.raises(ValueError):
        appcast.display_version(tag)


def test_the_tag_must_match_the_version_inside_the_archive(tmp_path):
    with pytest.raises(SystemExit):
        _write(tmp_path, tag="v0.6.0")


def test_the_archive_must_be_named_for_its_version(tmp_path):
    with pytest.raises(SystemExit):
        _write(tmp_path, archive=_archive(tmp_path, name="Caterva-0.5.1-macos-x86_64.zip"))


def test_a_test_build_is_never_described(tmp_path):
    with pytest.raises(SystemExit):
        _write(tmp_path, archive=_archive(tmp_path, feed="http://127.0.0.1:8000/appcast.xml"))


def test_a_local_test_feed_is_allowed_only_on_loopback(tmp_path):
    local = _archive(tmp_path, feed="http://127.0.0.1:8000/appcast.xml")
    out = _write(tmp_path, "--download-prefix", "http://127.0.0.1:8000/", archive=local)
    text = out.read_text(encoding="utf-8")
    assert 'url="http://127.0.0.1:8000/Caterva-0.5.1-macos-arm64.zip"' in text
    assert appcast.check_appcast(text) != []
    assert appcast.check_appcast(text, local_test=True) == []
    with pytest.raises(SystemExit):
        _write(tmp_path, "--download-prefix", "http://example.com/", archive=local)


@pytest.mark.parametrize("signature", ["", "not base64!", base64.b64encode(b"short").decode()])
def test_a_signature_that_is_not_64_bytes_is_refused(tmp_path, signature):
    notes = tmp_path / "notes.md"
    notes.write_text(NOTES, encoding="utf-8")
    with pytest.raises(SystemExit):
        appcast.main(["--zip", str(_archive(tmp_path)), "--signature", signature or "x", "--tag", "v0.5.1",
                      "--notes", str(notes), "--out", str(tmp_path / "a.xml")])


def test_the_signed_length_must_be_the_archives_size(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text(NOTES, encoding="utf-8")
    with pytest.raises(SystemExit):
        appcast.main(["--zip", str(_archive(tmp_path)), "--signature", SIGNATURE, "--length", "1", "--tag", "v0.5.1",
                      "--notes", str(notes), "--out", str(tmp_path / "a.xml")])


def test_the_check_names_what_is_wrong_with_a_feed(tmp_path):
    good = _write(tmp_path).read_text(encoding="utf-8")
    assert appcast.check_appcast("<rss")[0].startswith("not well-formed")
    foreign = good.replace("github.com/math12345678", "example.com/someone")
    assert any("not this repository" in p for p in appcast.check_appcast(foreign))
    unsigned = re.sub(r'sparkle:edSignature="[^"]*"', 'sparkle:edSignature=""', good)
    assert any("edSignature" in p for p in appcast.check_appcast(unsigned))
    assert any("DSA" in p for p in appcast.check_appcast(good.replace("<item>", '<item dsa="sparkle:dsaSignature">')))
    assert appcast.check_appcast(good.replace("<item>", "<item/><item>"))[0].startswith("expected exactly one item")


def _swift_stable() -> str:
    match = re.search(r'static let stable = "([^"]+)"', SWIFT["Updater.swift"])
    repo = re.search(r'static let repository = "([^"]+)"', SWIFT["Updater.swift"]).group(1)
    return match.group(1).replace("\\(repository)", repo)


def test_the_stable_feed_is_the_one_the_app_and_the_appcast_agree_on():
    plist = plistlib.loads(TEMPLATE.encode("utf-8").replace(b"@VERSION@", b"1.0.0").replace(b"@BUILD@", b"1"))
    assert plist["SUFeedURL"] == appcast.STABLE_FEED == _swift_stable() == (
        "https://github.com/math12345678/caterva/releases/latest/download/appcast.xml")


# --- the app's Info.plist ------------------------------------------------------

def test_the_plist_carries_the_updater_keys_and_a_real_public_key():
    data = plistlib.loads(studio_app.render_info_plist(TEMPLATE, "0.5.1", "412"))
    for key in studio_app.UPDATE_PLIST_KEYS:
        assert key in data
    assert len(base64.b64decode(data["SUPublicEDKey"], validate=True)) == 32
    assert data["SUEnableAutomaticChecks"] is True
    assert data["SUScheduledCheckInterval"] == 86400
    assert data["SUAllowsAutomaticUpdates"] is False
    assert data["SUVerifyUpdateBeforeExtraction"] is True
    assert data["NSAppTransportSecurity"] == {"NSAllowsLocalNetworking": True}
    assert data["LSMinimumSystemVersion"] == "14.0"


def test_a_plist_without_the_updater_keys_is_refused():
    without = TEMPLATE.replace("<key>SUFeedURL</key>", "<key>SUFeedURLX</key>")
    with pytest.raises(ValueError, match="SUFeedURL"):
        studio_app.render_info_plist(without, "0.5.1", "1")
    with pytest.raises(ValueError, match="32 bytes|base64"):
        studio_app.render_info_plist(TEMPLATE, "0.5.1", "1", None, {"SUPublicEDKey": "AAAA"})


def test_a_test_feed_and_key_replace_the_real_ones_only_when_asked():
    data = plistlib.loads(studio_app.render_info_plist(
        TEMPLATE, "0.5.1", "1", None, {"SUFeedURL": "http://127.0.0.1:8000/appcast.xml", "SUPublicEDKey": PUBLIC_KEY}))
    assert data["SUFeedURL"] == "http://127.0.0.1:8000/appcast.xml" and data["SUPublicEDKey"] == PUBLIC_KEY
    assert "--update-feed" in (REPO / "scripts" / "build_studio_app.py").read_text(encoding="utf-8")
    assert "--update-feed" not in DMG_WORKFLOW and "--update-feed" not in RELEASE


def test_the_version_is_the_one_the_release_notes_are_for():
    version = studio_app.package_version()
    assert (REPO / "docs" / "releases" / f"v{version}.md").is_file()
    assert f"## [{version}]" in (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"version: {version}" in (REPO / "CITATION.cff").read_text(encoding="utf-8")


# --- Sparkle in the build ----------------------------------------------------

def test_sparkle_is_pinned_to_a_version_and_a_sha256():
    assert re.fullmatch(r"\d+\.\d+\.\d+", sparkle.SPARKLE_VERSION)
    assert re.fullmatch(r"[0-9a-f]{64}", sparkle.SPARKLE_SHA256)
    assert sparkle.SPARKLE_URL == (f"https://github.com/sparkle-project/Sparkle/releases/download/"
                                   f"{sparkle.SPARKLE_VERSION}/Sparkle-{sparkle.SPARKLE_VERSION}.tar.xz")
    notice = (REPO / "NOTICE").read_text(encoding="utf-8")
    assert f"Sparkle {sparkle.SPARKLE_VERSION}" in notice and sparkle.SPARKLE_SHA256 in notice
    assert sparkle.SPARKLE_SHA256 in (REPO / "docs" / "studio" / "README.md").read_text(encoding="utf-8")


def test_only_the_pinned_archive_is_accepted(tmp_path):
    data = tmp_path / "Sparkle.tar.xz"
    data.write_bytes(b"not sparkle")
    assert "not the pinned" in sparkle.archive_problem(data)
    assert sparkle.archive_problem(data, hashlib.sha256(b"not sparkle").hexdigest()) is None
    assert "not a file" in sparkle.archive_problem(tmp_path / "missing")


def test_an_archive_that_leaves_its_folder_is_refused(tmp_path):
    assert sparkle.unsafe_members(["Sparkle.framework/x", "../evil", "/abs"]) == ["../evil", "/abs"]
    bad = tmp_path / "bad.tar.xz"
    with tarfile.open(bad, "w:xz") as bundle:
        link = tarfile.TarInfo("Sparkle.framework/Versions/Current")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../../../outside"
        bundle.addfile(link)
    with pytest.raises(SystemExit):
        sparkle.extract(bad, tmp_path / "out")
    good = tmp_path / "good.tar.xz"
    with tarfile.open(good, "w:xz") as bundle:
        body = b"x"
        entry = tarfile.TarInfo("LICENSE")
        entry.size = len(body)
        bundle.addfile(entry, io.BytesIO(body))
        link = tarfile.TarInfo("Sparkle.framework/Versions/Current")
        link.type = tarfile.SYMTYPE
        link.linkname = "B"
        bundle.addfile(link)
    sparkle.extract(good, tmp_path / "ok")
    assert (tmp_path / "ok" / "LICENSE").is_file()
    assert (tmp_path / "ok" / "Sparkle.framework" / "Versions" / "Current").is_symlink()


def test_a_tree_missing_a_required_file_is_reported(tmp_path):
    assert set(sparkle.missing_files(tmp_path)) == set(sparkle.REQUIRED)
    for name in sparkle.REQUIRED:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    assert sparkle.missing_files(tmp_path) == []


def test_the_shell_is_compiled_and_linked_against_sparkle(tmp_path):
    command = studio_app.swiftc_command([Path("a.swift")], Path("out"), "arm64", Path("cache"), sparkle=Path("/s"))
    assert command[command.index("-F") + 1] == "/s"
    assert command[command.index("-framework") + 1] == "Sparkle"
    at = command.index("-rpath")
    assert command[at + 1] == "-Xlinker" and command[at + 2] == "@executable_path/../Frameworks"
    assert "-F" not in studio_app.swiftc_command([Path("a.swift")], Path("out"), "arm64", Path("cache"))
    assert studio_app.FRAMEWORK_RPATH == "@executable_path/../Frameworks"


def _fake_sparkle(root: Path) -> Path:
    framework = root / "Sparkle.framework"
    version = framework / "Versions" / "B"
    for name in ("Sparkle", "Autoupdate", "XPCServices/Downloader.xpc/x", "Updater.app/Contents/MacOS/Updater"):
        (version / name).parent.mkdir(parents=True, exist_ok=True)
        (version / name).write_text("x", encoding="utf-8")
    (framework / "Versions" / "Current").symlink_to("B")
    (framework / "XPCServices").symlink_to("Versions/Current/XPCServices")
    (root / "LICENSE").write_text("MIT and others", encoding="utf-8")
    return root


def test_the_framework_is_embedded_without_xpc_services_and_with_its_licence(tmp_path):
    app = tmp_path / "Caterva.app"
    (app / "Contents" / "Resources").mkdir(parents=True)
    studio_app.embed_sparkle(app, _fake_sparkle(tmp_path / "dist"))
    framework = app / "Contents" / "Frameworks" / "Sparkle.framework"
    assert (framework / "Versions" / "B" / "Sparkle").is_file()
    assert (framework / "Versions" / "Current").is_symlink()
    assert not (framework / "XPCServices").exists() and not (framework / "XPCServices").is_symlink()
    assert not (framework / "Versions" / "B" / "XPCServices").exists()
    assert (app / "Contents" / "Resources" / "licenses" / "Sparkle-LICENSE.txt").read_text(encoding="utf-8") == "MIT and others"


def test_sparkles_code_is_sealed_inside_out(tmp_path):
    app = tmp_path / "Caterva.app"
    (app / "Contents" / "Resources").mkdir(parents=True)
    studio_app.embed_sparkle(app, _fake_sparkle(tmp_path / "dist"))
    order = [path.name for path in studio_app.sparkle_code(app)]
    assert order == ["Autoupdate", "Updater.app", "Sparkle.framework"]


def test_every_seal_is_adhoc_and_the_bundle_is_verified_strictly(monkeypatch, tmp_path):
    app = tmp_path / "Caterva.app"
    (app / "Contents" / "Resources").mkdir(parents=True)
    studio_app.embed_sparkle(app, _fake_sparkle(tmp_path / "dist"))
    calls = []
    monkeypatch.setattr(studio_app, "_run", lambda command, **kw: calls.append([str(c) for c in command]))
    studio_app.seal(app)
    signs = [c for c in calls if "--sign" in c]
    assert len(signs) == 4 and all(c[c.index("--sign") + 1] == "-" for c in signs)
    assert signs[-1][-1] == str(app) and "--deep" in signs[-1]
    assert [Path(c[-1]).name for c in signs[:-1]] == ["Autoupdate", "Updater.app", "Sparkle.framework"]
    assert calls[-1][:5] == ["codesign", "--verify", "--deep", "--strict", "--verbose=2"]
    assert not any("Developer ID" in " ".join(c) or "--options" in c for c in calls)


def test_the_update_archive_must_hold_the_app_and_nothing_beside_it(tmp_path):
    def build(extra: dict[str, bytes], version="0.5.1", sparkle_binary=True) -> Path:
        path = tmp_path / "z.zip"
        info = {"CFBundleShortVersionString": version, **{k: "x" for k in studio_app.UPDATE_PLIST_KEYS}}
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("Caterva.app/Contents/Info.plist", plistlib.dumps(info))
            if sparkle_binary:
                bundle.writestr("Caterva.app/Contents/Frameworks/Sparkle.framework/Versions/B/Sparkle", b"x")
            for name, body in extra.items():
                bundle.writestr(name, body)
        return path

    assert studio_app.zip_problems(build({}), "0.5.1") == []
    assert any("nothing beside" in p for p in studio_app.zip_problems(build({"README.txt": b"x"}), "0.5.1"))
    assert any("version" in p for p in studio_app.zip_problems(build({}, version="0.5.0"), "0.5.1"))
    assert any("Sparkle.framework" in p for p in studio_app.zip_problems(build({}, sparkle_binary=False), "0.5.1"))
    assert studio_app.zip_name("0.5.1") == "Caterva-0.5.1-macos-arm64.zip"
    assert appcast.ZIP_NAME.fullmatch(studio_app.zip_name("0.5.1"))


def test_a_development_app_is_never_made_into_an_update_archive():
    source = (REPO / "scripts" / "build_studio_app.py").read_text(encoding="utf-8")
    assert "args.dev and (args.dmg or args.zip)" in source


# --- the shell, the page and the contract ------------------------------------

BRIDGE_ACTIONS = ("updateStatus", "checkForUpdates", "setUpdateOptions", "reportActiveRuns")


def test_the_new_bridge_messages_are_in_the_shell_the_page_and_the_contract():
    page = (REPO / "Science-Agent-Pipeline/artifacts/caterva-studio/src/lib/desktop.ts").read_text(encoding="utf-8")
    contract = (REPO / "docs/studio/CONTRACT.md").read_text(encoding="utf-8")
    for action in BRIDGE_ACTIONS:
        assert f'action: "{action}"' in page, action
        assert f'case "{action}":' in SWIFT["WebBridge.swift"], action
        assert action in SWIFT["WebBridge.swift"].split("static let actions")[1].split("]")[0], action
        assert action in contract, action


def test_the_updater_is_off_in_a_development_build_and_in_the_menu_of_a_release_build():
    assert "isDevelopment" in SWIFT["Updater.swift"] and "does not update itself" in SWIFT["Updater.swift"]
    assert "CATERVA_DEVELOPMENT" in SWIFT["AppDelegate.swift"]
    assert 'item("Check for Updates…", #selector(AppDelegate.checkForUpdates(_:))' in SWIFT["AppDelegate.swift"]
    assert "updates.start()" in SWIFT["AppDelegate.swift"]


def test_an_update_stops_the_server_by_quitting_the_way_quit_does():
    """Sparkle ends the app with a normal terminate, which is where the server is stopped."""
    delegate = SWIFT["AppDelegate.swift"]
    assert "applicationShouldTerminate" in delegate and "server.stop()" in delegate
    assert "shouldPostponeRelaunchForUpdate" in SWIFT["Updater.swift"]
    assert "SUEnableInstallerLauncherService" not in TEMPLATE


def test_the_shell_never_follows_an_address_the_release_list_names_outside_the_repository():
    source = SWIFT["Updater.swift"]
    assert 'url.host == "github.com"' in source and 'url.scheme == "https"' in source
    assert "releases/download/" in source
    assert "isAcceptable(" in SWIFT["UpdaterSelfTest.swift"]
    assert "--updater-selftest" in SWIFT["main.swift"]


def test_the_shell_sends_nothing_about_the_person_to_github():
    source = SWIFT["Updater.swift"]
    assert "sendsSystemProfile" not in source
    assert "https://api.github.com/repos/\\(repository)/releases" in source and 'repository = "math12345678/caterva"' in source
    assert 'forHTTPHeaderField: "Authorization"' not in source


def test_the_copy_about_updates_never_claims_a_signature_or_notarisation():
    for relative in ("macos/dmg/README.txt", "macos/Resources/first-run.txt"):
        text = (REPO / relative).read_text(encoding="utf-8")
        assert studio_app.unsigned_wording_problems(text, relative) == []
    readme = (REPO / "macos/dmg/README.txt").read_text(encoding="utf-8")
    assert "install this\n    copy by hand" in readme
    assert "first install" in readme
    for relative in ("macos/dmg/README.txt", "macos/Resources/first-run.txt",
                     "Science-Agent-Pipeline/artifacts/caterva-studio/src/components/settings/UpdatesSection.tsx",
                     "docs/releases/v0.5.1.md"):
        text = (REPO / relative).read_text(encoding="utf-8")
        assert "—" not in text and " -- " not in text, relative


# --- the release workflows ---------------------------------------------------

def _workflows() -> dict[str, str]:
    return {w.name: w.read_text(encoding="utf-8") for w in sorted((REPO / ".github" / "workflows").glob("*.y*ml"))}


def test_the_workflows_are_valid_yaml_and_the_update_job_is_wired():
    yaml = pytest.importorskip("yaml")
    document = yaml.safe_load(RELEASE)
    jobs = document["jobs"]
    assert "update-feed" in jobs and "update-feed" in jobs["publish"]["needs"]
    assert jobs["update-feed"]["needs"] == ["studio-dmg"]
    assert jobs["update-feed"]["permissions"] == {"contents": "read"}
    assert "github.event_name == 'push'" in jobs["update-feed"]["if"]
    assert yaml.safe_load(DMG_WORKFLOW)["jobs"]["dmg"]


def test_only_release_yml_names_the_update_key_and_never_for_pull_requests():
    for name, text in _workflows().items():
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        assert "pull_request_target" not in code, name
        if "SPARKLE_ED_PRIVATE_KEY" in code:
            assert name == "release.yml"
    code = "\n".join(line for line in RELEASE.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"^\s*pull_request\b", code, re.M)
    assert re.search(r"^\s*tags:", code, re.M)


def test_the_key_is_set_on_the_signing_step_alone_and_read_from_standard_input():
    yaml = pytest.importorskip("yaml")
    document = yaml.safe_load(RELEASE)
    assert "SPARKLE_ED_PRIVATE_KEY" not in str(document.get("env", {}))
    holders = []
    for job_id, job in document["jobs"].items():
        assert "SPARKLE_ED_PRIVATE_KEY" not in str(job.get("env", {})), job_id
        for step in job.get("steps", []):
            if "SPARKLE_ED_PRIVATE_KEY" in str(step.get("env", {})):
                holders.append((job_id, step["name"]))
    assert holders == [("update-feed", "Sign the update archive and write appcast.xml")]
    assert "--ed-key-file -" in RELEASE
    assert not re.search(r"sign_update[^\n]*\s(-s|--private-key)\s", RELEASE)
    assert not re.search(r"echo[^\n]*\$\{?SPARKLE_ED_PRIVATE_KEY", RELEASE)


def test_a_missing_key_fails_the_release_with_a_plain_message():
    assert '-z "${SPARKLE_ED_PRIVATE_KEY:-}"' in RELEASE
    after = RELEASE.split('-z "${SPARKLE_ED_PRIVATE_KEY:-}"', 1)[1][:900]
    assert "::error::" in after and "is not set" in after and "never published" in after and "exit 1" in after


def test_a_key_that_does_not_match_the_apps_public_key_stops_the_release():
    assert "verify-update-signature" in RELEASE
    assert "SUPublicEDKey" in RELEASE
    assert "macos/Updater/VerifyUpdateSignature.swift" in RELEASE
    source = (REPO / "macos" / "Updater" / "VerifyUpdateSignature.swift").read_text(encoding="utf-8")
    assert "Curve25519.Signing.PublicKey" in source and "isValidSignature" in source


def test_the_release_publishes_the_archive_and_the_appcast_and_sums_them():
    assert release_guard.update_publication_problems(RELEASE) == []
    assert "release/Caterva-*-macos-arm64.zip" in RELEASE
    assert "find staged -type f -name appcast.xml" in RELEASE
    assert "--zip" in DMG_WORKFLOW and "Caterva-*-macos-arm64.zip" in DMG_WORKFLOW
    assert "--updater-selftest" in DMG_WORKFLOW


def test_the_guard_refuses_what_it_should_and_passes_the_repository():
    assert release_guard.update_problems() == []
    assert release_guard.secret_use_problems({"tests.yml": "env:\n  K: ${{ secrets.SPARKLE_ED_PRIVATE_KEY }}\n"})
    assert release_guard.secret_use_problems({"x.yml": "on:\n  pull_request_target:\n"})
    assert release_guard.sparkle_notice_problems("", 'SPARKLE_VERSION = "2.10.0"\n', True)
    assert not release_guard.sparkle_notice_problems("", "", False)
    assert release_guard.update_publication_problems("name: Release\n")


def test_the_pinned_licence_set_is_in_notice():
    notice = (REPO / "NOTICE").read_text(encoding="utf-8")
    for term in release_guard.SPARKLE_NOTICE_TERMS:
        assert term in notice, term
