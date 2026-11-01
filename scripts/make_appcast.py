#!/usr/bin/env python3
"""Write appcast.xml for one release: the file Caterva.app's updater reads.

Sparkle 2 reads an RSS feed whose <item> names the update archive, its
length, and an EdDSA signature over its bytes. The release workflow signs
Caterva-<version>-macos-arm64.zip with `sign_update` (key on stdin) and calls
this script with the signature it printed; the result is attached to the
GitHub Release beside the archive.

WHERE THE FEED IS SERVED FROM
-----------------------------
Nothing but GitHub Releases. Each release carries its own appcast.xml with
exactly one <item>, the release itself:

  stable feed      https://github.com/math12345678/caterva/releases/latest/download/appcast.xml
                   GitHub redirects `latest` to the newest release that is NOT
                   a prerelease, so a stable user never sees a candidate.
  prerelease feed  the appcast.xml of the newest release of any kind, whose
                   address the app reads from the GitHub Releases API when the
                   person turns on "Include prereleases".

WHAT AN ITEM CARRIES, AND WHERE EACH VALUE COMES FROM
-----------------------------------------------------
  sparkle:version               CFBundleVersion of the app inside the zip (the
                                build number, the commit count): what Sparkle
                                compares to decide an update is newer
  sparkle:shortVersionString    the version the person sees: 0.5.1 for v0.5.1,
                                0.5.1-rc.1 for v0.5.1-rc.1
  sparkle:minimumSystemVersion  LSMinimumSystemVersion of the same app (14.0)
  sparkle:hardwareRequirements  arm64: the app is Apple silicon only
  enclosure                     the zip's address on the release, its byte
                                length and its signature
  description                   the first paragraph of docs/releases/<tag>.md,
                                a line saying an install stops running jobs,
                                and a link to the release page

Everything read from the zip is read from the zip, not from the arguments, so
an appcast cannot describe a different build than the one it points at.

This script does not sign anything and holds no key. It refuses a tag that
does not match the version inside the archive, and an archive that does not
carry the updater's keys.

Usage:
    python3 scripts/make_appcast.py --zip dist/Caterva-0.5.1-macos-arm64.zip \\
        --signature BASE64 --tag v0.5.1 --notes docs/releases/v0.5.1.md --out appcast.xml
    python3 scripts/make_appcast.py --check appcast.xml
"""
from __future__ import annotations

import argparse
import base64
import email.utils
import html
import plistlib
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn, Optional, Sequence
from xml.etree import ElementTree

REPOSITORY = "math12345678/caterva"
RELEASES = f"https://github.com/{REPOSITORY}/releases"
STABLE_FEED = f"{RELEASES}/latest/download/appcast.xml"
SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"
TAG = re.compile(r"v(\d+\.\d+\.\d+)(-[0-9A-Za-z][0-9A-Za-z.]*)?")
ZIP_NAME = re.compile(r"Caterva-(\d+\.\d+\.\d+)-macos-arm64\.zip")
APP_INFO = "Caterva.app/Contents/Info.plist"


def _fail(message: str) -> NoReturn:
    print(f"NO APPCAST: {message}", file=sys.stderr)
    sys.exit(1)


def read_app_info(archive: Path) -> dict:
    """Info.plist of the Caterva.app inside the update archive."""
    try:
        with zipfile.ZipFile(archive) as bundle:
            return plistlib.loads(bundle.read(APP_INFO))
    except (KeyError, zipfile.BadZipFile) as exc:
        _fail(f"{archive} is not an archive of Caterva.app ({exc})")


def display_version(tag: str) -> str:
    """0.5.1 for v0.5.1; 0.5.1-rc.1 for v0.5.1-rc.1."""
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError(f"{tag!r} is not a release tag (vX.Y.Z or vX.Y.Z-suffix)")
    return match.group(1) + (match.group(2) or "")


def is_prerelease(tag: str) -> bool:
    match = TAG.fullmatch(tag)
    return bool(match and match.group(2))


SUMMARY_LIMIT = 400


def shorten(text: str, limit: int = SUMMARY_LIMIT) -> str:
    """`text` cut at the last sentence end within `limit` characters (or at a word, with an ellipsis)."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if end > limit // 2:
        return cut[: end + 1]
    return cut.rsplit(" ", 1)[0] + "..."


def summary_of(notes: str) -> str:
    """The first paragraph that is not a heading, as plain text.

    Markdown emphasis, code marks and link targets are dropped; the full
    notes are one link away on the release page.
    """
    for paragraph in re.split(r"\n\s*\n", notes.strip()):
        text = paragraph.strip()
        if not text or text.startswith("#"):
            continue
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[*_`]+", "", text)
        return shorten(" ".join(text.split()))
    return ""


def description_html(version: str, summary: str, release_url: str) -> str:
    parts = [f"<h3>Caterva {html.escape(version)}</h3>"]
    if summary:
        parts.append(f"<p>{html.escape(summary)}</p>")
    parts.append("<p>Installing this update closes Caterva and stops any run in progress. "
                 "Your runs and settings are kept; they are not part of the app.</p>")
    parts.append(f'<p><a href="{html.escape(release_url, quote=True)}">The full release notes</a></p>')
    return "".join(parts)


def _text(element: ElementTree.Element, tag: str, value: str) -> None:
    child = ElementTree.SubElement(element, tag)
    child.text = value


def build_appcast(*, tag: str, build: str, minimum_system: str, length: int,
                  signature: str, notes: str, published: datetime, archive_name: str,
                  download_prefix: Optional[str] = None) -> str:
    """The appcast text for one release. Pure: no files, no clock.

    `download_prefix` (a local update test only) replaces the release's
    download address with another folder's, e.g. http://127.0.0.1:8000/.
    """
    version = display_version(tag)
    release_url = f"{RELEASES}/tag/{tag}"
    enclosure_url = (download_prefix + archive_name) if download_prefix else f"{RELEASES}/download/{tag}/{archive_name}"
    ElementTree.register_namespace("sparkle", SPARKLE_NS)
    rss = ElementTree.Element("rss", {"version": "2.0"})
    channel = ElementTree.SubElement(rss, "channel")
    _text(channel, "title", "Caterva")
    _text(channel, "link", f"https://github.com/{REPOSITORY}")
    _text(channel, "description", "Updates for Caterva.app")
    _text(channel, "language", "en")
    item = ElementTree.SubElement(channel, "item")
    _text(item, "title", f"Caterva {version}")
    _text(item, "pubDate", email.utils.format_datetime(published.astimezone(timezone.utc), usegmt=True))
    _text(item, f"{{{SPARKLE_NS}}}version", build)
    _text(item, f"{{{SPARKLE_NS}}}shortVersionString", version)
    _text(item, f"{{{SPARKLE_NS}}}minimumSystemVersion", minimum_system)
    _text(item, f"{{{SPARKLE_NS}}}hardwareRequirements", "arm64")
    _text(item, "link", release_url)
    _text(item, "description", "@@DESCRIPTION@@")
    ElementTree.SubElement(item, "enclosure", {
        "url": enclosure_url,
        "length": str(length),
        "type": "application/octet-stream",
        f"{{{SPARKLE_NS}}}edSignature": signature,
    })
    ElementTree.indent(rss, space="  ")
    body = ElementTree.tostring(rss, encoding="unicode")
    cdata = description_html(version, summary_of(notes), release_url).replace("]]>", "]]&gt;")
    body = body.replace("@@DESCRIPTION@@", f"<![CDATA[{cdata}]]>")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + body + "\n"


def check_appcast(text: str, local_test: bool = False) -> list[str]:
    """What is wrong with an appcast, or an empty list. Used on the file this script wrote.

    `local_test` accepts an enclosure outside this repository's releases (an
    update test against a folder served on 127.0.0.1); a release never does.
    """
    problems: list[str] = []
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        return [f"not well-formed XML: {exc}"]
    items = root.findall("./channel/item")
    if len(items) != 1:
        return [f"expected exactly one item, found {len(items)}"]
    item = items[0]
    ns = {"sparkle": SPARKLE_NS}
    for field in ("sparkle:version", "sparkle:shortVersionString", "sparkle:minimumSystemVersion", "pubDate", "link"):
        node = item.find(field, ns)
        if node is None or not (node.text or "").strip():
            problems.append(f"item has no {field}")
    enclosure = item.find("enclosure")
    if enclosure is None:
        return problems + ["item has no enclosure"]
    url = enclosure.get("url", "")
    release_form = rf"{re.escape(RELEASES)}/download/v[^/]+/Caterva-\d+\.\d+\.\d+-macos-arm64\.zip"
    local_form = r"http://127\.0\.0\.1:\d+/Caterva-\d+\.\d+\.\d+-macos-arm64\.zip"
    if not re.fullmatch(release_form + (f"|{local_form}" if local_test else ""), url):
        problems.append(f"enclosure url is not this repository's release download: {url!r}")
    if not enclosure.get("length", "").isdigit() or int(enclosure.get("length", "0")) <= 0:
        problems.append("enclosure length is not a positive number")
    signature = enclosure.get(f"{{{SPARKLE_NS}}}edSignature", "")
    try:
        if len(base64.b64decode(signature, validate=True)) != 64:
            problems.append("edSignature is not 64 bytes")
    except ValueError:
        problems.append("edSignature is not base64")
    if "sparkle:dsaSignature" in text:
        problems.append("a DSA signature is present; Caterva uses EdDSA only")
    return problems


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zip", help="the update archive, Caterva-<version>-macos-arm64.zip")
    parser.add_argument("--signature", help="the EdDSA signature `sign_update` printed for that archive (base64)")
    parser.add_argument("--length", type=int, help="the length `sign_update` printed; must equal the archive's size")
    parser.add_argument("--tag", help="the release tag, vX.Y.Z or vX.Y.Z-rc.N")
    parser.add_argument("--notes", help="docs/releases/<tag>.md (the plain tag's, for a candidate)")
    parser.add_argument("--out", default="appcast.xml")
    parser.add_argument("--download-prefix", help="TEST ONLY: where the archive is served from, http://127.0.0.1:PORT/ "
                        "(an update test against a local feed); the app inside must then carry that feed too")
    parser.add_argument("--pub-date", help="an ISO 8601 time (default: now, UTC); for tests")
    parser.add_argument("--check", metavar="FILE", help="validate an appcast instead of writing one")
    args = parser.parse_args(argv)

    if args.check:
        problems = check_appcast(Path(args.check).read_text(encoding="utf-8"), local_test=bool(args.download_prefix))
        for problem in problems:
            print(f"APPCAST PROBLEM: {problem}", file=sys.stderr)
        if not problems:
            print(f"{args.check}: one item, signed, pointing at this repository's release")
        return 1 if problems else 0

    for name in ("zip", "signature", "tag", "notes"):
        if not getattr(args, name):
            parser.error(f"--{name} is required")
    archive = Path(args.zip)
    try:
        display = display_version(args.tag)
    except ValueError as exc:
        _fail(str(exc))
    info = read_app_info(archive)
    base = TAG.fullmatch(args.tag).group(1)  # type: ignore[union-attr]
    if info.get("CFBundleShortVersionString") != base:
        _fail(f"{archive.name} holds Caterva {info.get('CFBundleShortVersionString')}, but the tag {args.tag} is version {base}")
    match = ZIP_NAME.fullmatch(archive.name)
    if not match or match.group(1) != base:
        _fail(f"the archive must be named Caterva-{base}-macos-arm64.zip, not {archive.name}")
    for key in ("CFBundleVersion", "LSMinimumSystemVersion", "SUPublicEDKey", "SUFeedURL"):
        if not info.get(key):
            _fail(f"the app inside {archive.name} has no {key} in its Info.plist")
    local_test = bool(args.download_prefix)
    if local_test and not re.fullmatch(r"http://127\.0\.0\.1:\d+/", args.download_prefix):
        _fail("--download-prefix must look like http://127.0.0.1:PORT/")
    if not local_test and info["SUFeedURL"] != STABLE_FEED:
        _fail(f"the app inside {archive.name} reads its updates from {info['SUFeedURL']}, not from {STABLE_FEED}; "
              "a test build is never published")
    length = archive.stat().st_size
    if args.length is not None and args.length != length:
        _fail(f"the signed length {args.length} is not the archive's size {length}")
    try:
        if len(base64.b64decode(args.signature, validate=True)) != 64:
            _fail("the signature is not 64 bytes of base64 (an EdDSA signature)")
    except ValueError:
        _fail("the signature is not base64")
    notes_path = Path(args.notes)
    if not notes_path.is_file():
        _fail(f"{notes_path} does not exist; a release has notes")
    published = datetime.fromisoformat(args.pub_date) if args.pub_date else datetime.now(timezone.utc)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    text = build_appcast(tag=args.tag, build=str(info["CFBundleVersion"]),
                         minimum_system=str(info["LSMinimumSystemVersion"]), length=length,
                         signature=args.signature, notes=notes_path.read_text(encoding="utf-8"),
                         published=published, archive_name=archive.name,
                         download_prefix=args.download_prefix)
    problems = check_appcast(text, local_test=local_test)
    if problems:
        _fail("; ".join(problems))
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"wrote {args.out}: Caterva {display} (build {info['CFBundleVersion']}), {length} bytes, "
          f"{'prerelease' if is_prerelease(args.tag) else 'stable'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
