"""Redaction and secret scrubbing: pure functions, no I/O.

Two different jobs live here, and they are kept apart on purpose.

`redact_text` runs on everything that is about to leave the machine in an
assistant request. It writes the home folder as `~`, every other absolute
path as `[path]`, the account's user name as `[user]`, e-mail addresses as
`[email]` and anything shaped like an API key as `[key]`. It is applied to
the payload BEFORE the person is shown it, so the preview is the redacted
text and what is sent is that same string.

`scrub` runs on everything the studio is about to WRITE or SHOW that could
carry a secret: an error message, a log line, an audit record. It removes
key-shaped strings and, exactly, any secret value this process was handed
(the configured key, which is held in memory only). A provider's error body
sometimes echoes the key it rejected; this is what stops that reaching the
page or the disk.

Neither is a guarantee about what a person TYPED into their own question or
put in their own file. The consent preview exists so they can see it.
"""
from __future__ import annotations

import getpass
import os
import re
from typing import Iterable, Optional, Pattern, Sequence, Tuple

#: Shapes of provider keys. Ordered: the specific ones before the generic.
#: Each pattern is anchored on a prefix the provider documents, or on a long
#: unbroken run that no sentence contains.
KEY_PATTERNS: Tuple[Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"sk-or-v1-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gsk_[A-Za-z0-9]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"xai-[A-Za-z0-9]{16,}"),
    re.compile(r"pplx-[A-Za-z0-9]{16,}"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{16,}=*"),
    re.compile(r"(?i)\b(?:x-api-key|api[-_ ]?key|authorization)\s*[:=]\s*[^\s\"',;]{8,}"),
    # A long run of hexadecimal digits: a token, a hash used as a secret.
    re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{32,}(?![0-9A-Za-z])"),
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
#: An absolute path on macOS/Linux with at least two components, or a
#: Windows drive path. A lone "/s" (a unit) or "1/s" is not one.
_UNIX_PATH = re.compile(r"(?<![\w.:/])(?:~|/)(?:[^\s\"'<>|:*?()\[\]{},;]+/)+[^\s\"'<>|:*?()\[\]{},;]*")
_UNIX_PATH2 = re.compile(r"(?<![\w.:/])/(?:Users|home|private|var|tmp|Volumes|opt|etc|usr|mnt|root)\b[^\s\"'<>|]*")
_WIN_PATH = re.compile(r"\b[A-Za-z]:\\(?:[^\s\"'<>|\\]+\\?)+")
_URL = re.compile(r"https?://[^\s\"'<>)\]]+")

PLACEHOLDER_KEY = "[key]"
PLACEHOLDER_PATH = "[path]"
PLACEHOLDER_USER = "[user]"
PLACEHOLDER_EMAIL = "[email]"


def looks_like_key(text: str) -> bool:
    return any(p.search(text) for p in KEY_PATTERNS)


def find_keys(text: str) -> list:
    """Every key-shaped substring of `text`."""
    out = []
    for pattern in KEY_PATTERNS:
        out.extend(m.group(0) for m in pattern.finditer(text))
    return out


def scrub(text: str, secrets: Iterable[str] = ()) -> str:
    """`text` with every key-shaped string and every known secret removed.

    `secrets` are exact values (the configured key); a value shorter than 6
    characters is ignored so a test key of "a" cannot blank a sentence."""
    if not isinstance(text, str):
        text = str(text)
    for secret in sorted((s for s in secrets if isinstance(s, str) and len(s) >= 6), key=len, reverse=True):
        text = text.replace(secret, PLACEHOLDER_KEY)
    for pattern in KEY_PATTERNS:
        text = pattern.sub(PLACEHOLDER_KEY, text)
    return text


def _user_names(extra: Sequence[str]) -> list:
    names = set(n for n in extra if n)
    for getter in (getpass.getuser, lambda: os.environ.get("USER", ""), lambda: os.environ.get("LOGNAME", "")):
        try:
            value = getter()
        except Exception:  # noqa: BLE001 - getuser raises on odd environments
            value = ""
        if value:
            names.add(value)
    home = os.path.basename(os.path.expanduser("~").rstrip("/\\"))
    if home:
        names.add(home)
    # Very short names would blank ordinary words ("al", "jo").
    return sorted((n for n in names if len(n) >= 3 and n.lower() not in ("root", "user", "home", "admin")),
                  key=len, reverse=True)


def redact_text(text: str, *, home: Optional[str] = None, data_dir: Optional[str] = None,
                user_names: Sequence[str] = (), secrets: Iterable[str] = (), keep_urls: bool = True) -> str:
    """The text as it may leave the machine."""
    home = os.path.expanduser("~") if home is None else home
    out = scrub(text, secrets)
    # Specific folders first, so a data folder is named, not just "a path".
    for folder, label in ((data_dir, "[data dir]"), (home, "~")):
        if folder and len(folder.rstrip("/\\")) > 1:
            out = out.replace(folder.rstrip("/\\"), label)
    out = _WIN_PATH.sub(PLACEHOLDER_PATH, out)
    # Keep a URL out of the path pattern: "https://host/a/b" is not a file.
    urls: list = []

    def hold(match: "re.Match[str]") -> str:
        urls.append(match.group(0))
        return f"\x00url{len(urls) - 1}\x00"

    out = _URL.sub(hold, out)
    out = _UNIX_PATH2.sub(PLACEHOLDER_PATH, out)
    out = _UNIX_PATH.sub(PLACEHOLDER_PATH, out)
    for index, url in enumerate(urls):
        out = out.replace(f"\x00url{index}\x00", url if keep_urls else "[link]")
    out = _EMAIL.sub(PLACEHOLDER_EMAIL, out)
    for name in _user_names(user_names):
        out = re.sub(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", PLACEHOLDER_USER, out, flags=re.I)
    return out


__all__ = ["KEY_PATTERNS", "PLACEHOLDER_KEY", "PLACEHOLDER_PATH", "PLACEHOLDER_USER", "find_keys", "looks_like_key",
           "redact_text", "scrub"]
