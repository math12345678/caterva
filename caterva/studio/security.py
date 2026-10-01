"""The rules every request to the studio passes before any handler sees it.

WHY A LOCAL SERVER NEEDS THEM
-----------------------------
`caterva studio` listens on a loopback port. Loopback keeps other machines
out, and nothing else: every web page the user opens in any browser can
ask the browser to make a request to `http://127.0.0.1:<port>/`, and a page
on a domain its author controls can make the browser believe that domain
IS 127.0.0.1 (DNS rebinding), after which the browser's same-origin rule
no longer separates the two. Without the checks below, any site visited
while the studio runs could start runs, read the workspace, or delete it.

So, in the order docs/studio/CONTRACT.md section 3 gives them:

1. the Host header must name the bound address. A rebinding page's
   requests still carry its own name (`evil.example:<port>`), which is how
   they are told apart;
2. a request that carries `Origin` must come from the studio's own origin,
   or the one `--dev-origin` named; `Sec-Fetch-Site: cross-site` is refused
   whatever the Origin says. There is no CORS: no response carries an
   `Access-Control-Allow-*` header, so a foreign page cannot read one;
3. every `/api/` request must carry the per-launch session token in the
   `X-Caterva-Session` header. The token is minted at start with
   `secrets`, held in memory only, compared in constant time, and never
   accepted from a URL or a cookie, where a browser would attach it to a
   foreign page's requests on its own.

The token is written into the served index.html, which a foreign page
cannot read (no CORS, and CORP same-origin), so only the studio's own page
learns it. Any process running as the same user can read it too; that
process could read the workspace directly, so the token does not pretend
to stop it.

WHAT THIS MODULE DOES NOT DO
----------------------------
It decides; it does not answer. Each check returns the reason it refused,
or None, and the dispatch layer turns that into a response. That keeps
every rule testable as a plain function, with no socket and no server.
"""
from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Sequence, Tuple

from caterva.studio.contract import SESSION_HEADER

#: The Content Security Policy on every HTML response (CONTRACT.md 3.8).
#: The built page has no inline script or style element, so nothing here is
#: relaxed for it; a component that needs `unsafe-inline` or `eval` is
#: refused in review rather than this policy loosened.
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
    "font-src 'self'; connect-src 'self'; manifest-src 'self'; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'; object-src 'none'"
)

#: A file a run produced is served as a download, never as a document of
#: this origin: were an adapter ever to record an HTML artifact, this keeps
#: its scripts from running with the page's session.
ARTIFACT_CSP = "default-src 'none'; sandbox"

#: On every response, error responses and streams included (CONTRACT.md 3.7).
#: `Server` replaces the standard library's default, which names the Python
#: version and gives a visitor nothing they need.
BASE_HEADERS: Tuple[Tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
    ("Server", "caterva-studio"),
)

#: --host value -> the names a browser may put in Host for it. `localhost`
#: is bound as 127.0.0.1 (see server.bind_address), so both spellings of
#: that address are the same server; `::1` is its own.
_HOST_NAMES = {
    "127.0.0.1": ("127.0.0.1", "localhost"),
    "::1": ("[::1]", "localhost"),
    "localhost": ("localhost", "127.0.0.1"),
}


def mint_token() -> str:
    """A fresh session token: 32 random bytes, URL-safe base64, no padding.

    URL-safe so it can sit in an HTML attribute and a header without
    escaping; it is still never put in a URL."""
    return secrets.token_urlsafe(32)


def authorities(host: str, port: int) -> FrozenSet[str]:
    """Every Host header value that names the server bound on host:port."""
    try:
        names = _HOST_NAMES[host]
    except KeyError:
        raise ValueError(f"{host!r} is not a loopback host the studio binds") from None
    out = {f"{name}:{port}" for name in names}
    if port == 80:
        # A browser omits the default port from Host.
        out |= set(names)
    return frozenset(out)


def url_for(host: str, port: int) -> str:
    """The address the studio prints and opens: http://127.0.0.1:<port>/."""
    name = "[::1]" if host == "::1" else host
    return f"http://{name}:{port}/"


@dataclass(frozen=True)
class Guard:
    """The security rules for one running server: its address, token and
    optional development origin."""

    host: str
    port: int
    token: str = field(repr=False)
    dev_origin: Optional[str] = None

    @property
    def hosts(self) -> FrozenSet[str]:
        return authorities(self.host, self.port)

    @property
    def origins(self) -> FrozenSet[str]:
        own = {f"http://{authority}" for authority in self.hosts}
        if self.dev_origin:
            own.add(self.dev_origin)
        return frozenset(own)

    def refuse_host(self, values: Sequence[str]) -> Optional[str]:
        """Why a request's Host header(s) are refused, or None (rule 3.2)."""
        if len(values) != 1:
            return "the request must carry exactly one Host header"
        if values[0].strip().lower() not in self.hosts:
            # The value is not echoed: it is whatever a foreign page chose.
            return "the Host header does not name this server's loopback address"
        return None

    def refuse_origin(self, origins: Sequence[str], fetch_site: Sequence[str]) -> Optional[str]:
        """Why a request's Origin or Sec-Fetch-Site is refused, or None (rule 3.3)."""
        if any(v.strip().lower() == "cross-site" for v in fetch_site):
            return "a cross-site request is refused"
        if len(origins) > 1:
            return "the request carries more than one Origin header"
        if origins and origins[0].strip() not in self.origins:
            return "the request comes from an origin other than this server's own"
        return None

    def token_matches(self, values: Sequence[str]) -> bool:
        """Whether the request carries exactly the session token (rule 3.4)."""
        if len(values) != 1:
            return False
        return hmac.compare_digest(values[0].strip().encode("utf-8"), self.token.encode("utf-8"))

    def refuse_dev_session(self, origins: Sequence[str], fetch_site: Sequence[str]) -> Optional[str]:
        """Why a GET /api/dev/session is refused, or None (CONTRACT.md 5).

        The Vite server's own Node `fetch` carries neither header; a web page
        cannot avoid carrying them, so their presence marks a browser."""
        if origins:
            return "the development session is not given to a request that carries Origin"
        if any(v.strip().lower() != "none" for v in fetch_site):
            return "the development session is given only to a request made outside a web page"
        return None


__all__ = ["ARTIFACT_CSP", "BASE_HEADERS", "CSP", "Guard", "SESSION_HEADER", "authorities",
           "mint_token", "url_for"]
