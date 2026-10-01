"""The built page: serving it from caterva/studio/static, with the session token written in.

WHY THE TOKEN GOES INTO THE HTML
--------------------------------
Every /api/ request must carry the per-launch token (security.py). The
page has to learn it somehow, and every other channel is worse: a query
string lands in history and logs, a cookie is attached by the browser to a
foreign page's requests too, and a separate endpoint would itself need
protecting. index.html is fetched by the page's own tab and cannot be read
by a foreign one (no CORS, CORP same-origin), so the server replaces the
one placeholder in `<meta name="caterva-session" content="...">` as it
serves the file, per request, from memory. The token is never written to
disk.

If the placeholder is not there, the directory holds a page that was not
built from this package, and serving it would hand the user a page that
cannot talk to the server while looking as if it could. That is a 500 with
that sentence, not a page without a token.

WHAT IS REFUSED
---------------
Anything outside the static directory. A path is percent-decoded once,
split on "/", and refused (404) when a segment is `.` or `..`, starts with
a dot, or holds a backslash or NUL; what remains is joined under the
directory, resolved (following symlinks), and must still be inside it.
There is no directory listing: `/` and the page's own client-side routes
answer index.html; a request that names a file (its last segment has a
dot) and misses answers 404, because a stylesheet answered with HTML fails
more confusingly than a missing one.

THE PAGE THAT IS NOT BUILT
--------------------------
The page is built by Vite at release time and never committed, so a fresh
checkout has none. Then `/` answers a small page of this module's own
saying so and naming the build command, rather than a 404 that looks like
a broken server. It has no script, and its one style element is allowed
by hash in its own CSP, so the policy stays strict.
"""
from __future__ import annotations

import base64
import hashlib
import html
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from caterva.studio.contract import SESSION_META_NAME, TOKEN_PLACEHOLDER
from caterva.studio.security import CSP

#: Where Vite writes the page (vite.config.ts `build.outDir`).
STATIC_DIR = Path(__file__).resolve().parent / "static"

#: The build command a reader of the not-built page should run
#: (CONTRACT.md section 19).
BUILD_COMMAND = "pnpm --filter @workspace/caterva-studio run build"

#: Types the standard library guesses differently across platforms, or not
#: at all. `.js` must be a JavaScript type or the browser refuses a module.
_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
}

#: Vite names every file under assets/ by its content hash, so a browser
#: may keep it for a year; a new build has new names.
IMMUTABLE = "public, max-age=31536000, immutable"

_META = re.compile(
    r"<meta\s+name=\"" + re.escape(SESSION_META_NAME) + r"\"\s+content=\""
    + re.escape(TOKEN_PLACEHOLDER) + r"\"\s*/?>"
)

_NOT_BUILT_STYLE = (
    "body{margin:0;background:#fdf8ee;color:#2a2d35;font:16px/1.55 Georgia,serif}"
    "main{max-width:36rem;margin:12vh auto;padding:0 1.5rem}"
    "h1{font-weight:400;letter-spacing:.2em;text-transform:lowercase;font-size:1.4rem}"
    "code,pre{font:14px/1.5 ui-monospace,Menlo,monospace}"
    "pre{background:#f3ecdc;padding:.8rem 1rem;overflow-x:auto;border-radius:4px}"
    "p.quiet{color:#5a5e68}"
    "@media (prefers-color-scheme:dark){body{background:#2a2d35;color:#f0ebe0}"
    "pre{background:#353945}p.quiet{color:#b9b4a8}}"
)
_NOT_BUILT_STYLE_HASH = base64.b64encode(hashlib.sha256(_NOT_BUILT_STYLE.encode("utf-8")).digest()).decode("ascii")
NOT_BUILT_CSP = CSP.replace("style-src 'self'", f"style-src 'sha256-{_NOT_BUILT_STYLE_HASH}'")


class NotFromThisPackage(RuntimeError):
    """index.html exists but has no token placeholder in its session meta tag."""


@dataclass(frozen=True)
class StaticFile:
    """One answer from the static directory, before the security headers."""

    status: int
    body: bytes
    content_type: str
    cache_control: str
    #: The CSP for an HTML answer, None for anything else.
    csp: Optional[str] = None
    extra: Tuple[Tuple[str, str], ...] = field(default=())


def content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _TYPES:
        return _TYPES[suffix]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def safe_segments(decoded_path: str) -> Optional[List[str]]:
    """The path's segments, or None when any is refused outright.

    `decoded_path` has been percent-decoded once. Empty segments (from
    `//` or a trailing slash) are dropped rather than refused, since they
    name nothing."""
    if "\x00" in decoded_path or "\\" in decoded_path:
        return None
    segments = [s for s in decoded_path.split("/") if s != ""]
    for segment in segments:
        if segment in (".", "..") or segment.startswith("."):
            return None
    return segments


class StaticSite:
    """The built page under `root` (default caterva/studio/static)."""

    def __init__(self, root: Path = STATIC_DIR) -> None:
        self.root = Path(root)

    @property
    def index(self) -> Path:
        return self.root / "index.html"

    def built(self) -> Tuple[bool, Optional[str]]:
        """(built, why not). Built means index.html exists and carries the
        token placeholder in its session meta tag (Capabilities.ui)."""
        if not self.index.is_file():
            return False, (
                f"the page has not been built: {self.index} does not exist. Build it with "
                f"`{BUILD_COMMAND}` from Science-Agent-Pipeline/"
            )
        try:
            text = self.index.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return False, f"{self.index} cannot be read: {exc}"
        if not _META.search(text):
            return False, f"{self.index} was not built from this package: it has no session placeholder"
        return True, None

    def index_with_token(self, token: str) -> bytes:
        """index.html with the placeholder replaced by `token`.

        Raises FileNotFoundError when there is no build and
        NotFromThisPackage when the placeholder is missing."""
        text = self.index.read_text(encoding="utf-8")
        match = _META.search(text)
        if match is None:
            raise NotFromThisPackage(
                "the page in the static directory was not built from this package: its "
                f"<meta name=\"{SESSION_META_NAME}\"> tag has no session placeholder"
            )
        tag = match.group(0).replace(TOKEN_PLACEHOLDER, token)
        return (text[: match.start()] + tag + text[match.end():]).encode("utf-8")

    def not_built_page(self) -> StaticFile:
        """The server's own page for a checkout whose page is not built."""
        body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Caterva Studio: the page is not built</title>
<style>{_NOT_BUILT_STYLE}</style>
</head>
<body>
<main>
<h1>caterva studio</h1>
<p>The server is running and its API answers, but the page it serves has
not been built in this checkout. It looked for it here:</p>
<pre>{html.escape(str(self.index))}</pre>
<p>Build it once, from the repository's <code>Science-Agent-Pipeline/</code> folder:</p>
<pre>pnpm install --frozen-lockfile --filter @workspace/caterva-studio...
{html.escape(BUILD_COMMAND)}</pre>
<p>Then reload this page. The build is not committed to the repository:
it is made at release time, and the downloadable app carries it.</p>
<p class="quiet">docs/studio/USING_STUDIO.md has the whole recipe.</p>
</main>
</body>
</html>
"""
        return StaticFile(200, body.encode("utf-8"), "text/html; charset=utf-8", "no-store",
                          csp=NOT_BUILT_CSP)

    def lookup(self, decoded_path: str) -> Tuple[str, Optional[Path]]:
        """What a non-API path names: ("file", path), ("index", None),
        ("missing", None) for a file request that misses, or ("refused", None)."""
        segments = safe_segments(decoded_path)
        if segments is None:
            return "refused", None
        if not segments:
            return "index", None
        root = self.root.resolve()
        candidate = root.joinpath(*segments)
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            return "refused", None
        if not resolved.is_relative_to(root):
            return "refused", None
        if resolved.is_file():
            if resolved == (root / "index.html"):
                return "index", None
            return "file", resolved
        if "." in segments[-1] or segments[0] == "assets":
            return "missing", None
        return "index", None

    def serve(self, decoded_path: str, token: str) -> StaticFile:
        """The answer to GET `decoded_path` (not under /api/)."""
        what, path = self.lookup(decoded_path)
        if what in ("refused", "missing"):
            return _not_found()
        if what == "index":
            if not self.index.is_file():
                return self.not_built_page()
            body = self.index_with_token(token)
            return StaticFile(200, body, "text/html; charset=utf-8", "no-store", csp=CSP)
        assert path is not None
        body = path.read_bytes()
        ctype = content_type(path)
        cache = IMMUTABLE if path.is_relative_to(self.root.resolve() / "assets") else "no-cache"
        csp = CSP if ctype.startswith("text/html") else None
        return StaticFile(200, body, ctype, cache, csp=csp)


def _not_found() -> StaticFile:
    return StaticFile(404, b"Not found\n", "text/plain; charset=utf-8", "no-store")


__all__ = ["BUILD_COMMAND", "IMMUTABLE", "NOT_BUILT_CSP", "NotFromThisPackage", "STATIC_DIR", "StaticFile",
           "StaticSite", "content_type", "safe_segments"]
