"""Certificate authorities for the standard library's HTTPS, in a frozen app.

`requests` and `httpx` check a server's certificate against the `certifi`
bundle, which ships inside every download. The standard library's `ssl`
module does not: it reads the certificate file its OpenSSL was built to look
for, and a frozen app was built on a machine whose path is not the user's.
On a Mac that path is missing, so every `urllib` HTTPS request failed with
CERTIFICATE_VERIFY_FAILED while the literature lookups beside it worked. The
studio's reachability check was one of those requests, so the status bar said
the network was down on a network that was up.

`trust_bundled_certificates` points OpenSSL at the bundle when, and only
when, nothing else has been chosen: a certificate setting the user made, or a
certificate file the build's default path really finds, is left alone.
"""
from __future__ import annotations

import os
import ssl
from typing import MutableMapping, Optional

#: Settings a person or an IT department makes on purpose; any of them wins.
USER_CERTIFICATE_SETTINGS = ("SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")


def bundled_ca_file() -> Optional[str]:
    """The `certifi` bundle that ships with Caterva, or None if it cannot be found."""
    try:
        import certifi
    except ImportError:
        return None
    path = certifi.where()
    return path if os.path.isfile(path) else None


def default_certificates_exist() -> bool:
    """True when this Python's own default certificate file or folder is really there."""
    paths = ssl.get_default_verify_paths()
    if any(p and os.path.isfile(p) for p in (paths.cafile, paths.openssl_cafile)):
        return True
    for folder in (paths.capath, paths.openssl_capath):
        if folder and os.path.isdir(folder) and os.listdir(folder):
            return True
    return False


def trust_bundled_certificates(environ: MutableMapping[str, str] = os.environ) -> Optional[str]:
    """Use the bundled certificates for `ssl` and `urllib` when nothing else is set up.

    Returns the file it chose, or None when it changed nothing. Call it before
    the first HTTPS request: a default context reads the setting when it is made.
    """
    if any(environ.get(name) for name in USER_CERTIFICATE_SETTINGS) or default_certificates_exist():
        return None
    bundle = bundled_ca_file()
    if bundle is None:
        return None
    environ["SSL_CERT_FILE"] = bundle
    return bundle


def client_context() -> ssl.SSLContext:
    """A verifying TLS context for an HTTPS client that can always find certificate authorities.

    A certificate setting the user made on purpose wins (a file or a folder, from any of
    `USER_CERTIFICATE_SETTINGS`, including the ones `ssl` itself does not read). Otherwise this Python's own
    default certificates are used when they are really there, and the bundled `certifi` file when they are not.
    `httpx` takes it as `verify=` (the studio's assistant, which is the only code in the studio that sends text to
    a server the person did not start themselves); `urllib` takes it as `context=`."""
    for name in USER_CERTIFICATE_SETTINGS:
        value = os.environ.get(name)
        if value and os.path.exists(value):
            return ssl.create_default_context(cafile=value) if os.path.isfile(value) \
                else ssl.create_default_context(capath=value)
    bundle = None if default_certificates_exist() else bundled_ca_file()
    return ssl.create_default_context(cafile=bundle)


__all__ = ["USER_CERTIFICATE_SETTINGS", "bundled_ca_file", "client_context", "default_certificates_exist",
           "trust_bundled_certificates"]
