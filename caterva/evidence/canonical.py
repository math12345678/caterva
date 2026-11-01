"""One byte string per value, so one identity per derivation.

WHY THIS EXISTS
---------------
A claim's identity (ADR 0179) is the digest of what derived it: the rule,
the inputs, the certificates, the settings. Two programs that agree about
those must compute the same digest, and the independent checker
(`caterva/check/`, which imports none of this) re-derives every id from the
stored fields. That only works if the serialisation is fixed down to the
byte: key order, separators, escaping, and above all what a number is.

WHAT IS REFUSED, AND WHY
------------------------
Floats. `json.dumps(0.1)` is deterministic within one interpreter, but a
float that has been through an ODE solver, a unit conversion or a different
libm is not the same float, and two ids that differ because of a last-digit
rounding would make every re-check a false alarm. So every number that
enters an identity is a decimal STRING (`"6"`, `"40.1"`, `"1e-9"`), written
by whoever read it and compared by the checker with Decimal arithmetic.
Integers are allowed: a rule version or a byte offset is exact. Booleans
and None are allowed for the same reason. A dict key that is not a string is
refused too, because `json.dumps` would silently spell it as one.

The definition, which the checker repeats word for word:

    json.dumps(obj, sort_keys=True, separators=(",", ":"),
               ensure_ascii=False, allow_nan=False).encode("utf-8")

and a digest is `"sha256:" + hexdigest` of those bytes.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

#: A digest as every identity and reference spells it.
Digest = str

DIGEST_PREFIX = "sha256:"


def refuse_floats(obj: Any, path: str = "$") -> None:
    """Raise TypeError naming the first float (or non-string key) in `obj`.

    Walks mappings and sequences; strings, integers, booleans and None pass.
    """
    if isinstance(obj, bool) or obj is None or isinstance(obj, (str, int)):
        return
    if isinstance(obj, float):
        raise TypeError(
            f"{path} is a float ({obj!r}); every number in an identity is a "
            "decimal string, so that two readings of one page cannot differ "
            "by a rounding (caterva/evidence/canonical.py)"
        )
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} has a key that is not a string: {key!r}")
            refuse_floats(value, f"{path}.{key}")
        return
    if isinstance(obj, Sequence) and not isinstance(obj, (bytes, bytearray)):
        for index, value in enumerate(obj):
            refuse_floats(value, f"{path}[{index}]")
        return
    raise TypeError(f"{path} is a {type(obj).__name__}, which canonical JSON does not carry")


def canonical_bytes(obj: Any) -> bytes:
    """The one serialisation of `obj`. Refuses floats (TypeError)."""
    refuse_floats(obj)
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def digest(data: bytes) -> Digest:
    """`"sha256:<64 hex>"` of `data`."""
    return DIGEST_PREFIX + hashlib.sha256(data).hexdigest()


def is_digest(text: Any) -> bool:
    """True for a well-formed digest string; no other spelling is accepted."""
    return (
        isinstance(text, str)
        and text.startswith(DIGEST_PREFIX)
        and len(text) == len(DIGEST_PREFIX) + 64
        and all(c in "0123456789abcdef" for c in text[len(DIGEST_PREFIX):])
    )


def digest_hex(value: Digest) -> str:
    """The 64 hex characters of a digest, as blob file names use them."""
    if not is_digest(value):
        raise ValueError(f"{value!r} is not a digest of the form sha256:<64 hex>")
    return value[len(DIGEST_PREFIX):]


__all__ = [
    "DIGEST_PREFIX",
    "Digest",
    "canonical_bytes",
    "digest",
    "digest_hex",
    "is_digest",
    "refuse_floats",
]
