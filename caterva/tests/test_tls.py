"""The standard library's HTTPS must find certificate authorities in a frozen app (caterva/tls.py)."""
import ssl
import subprocess
import sys
from pathlib import Path

import certifi
import pytest

from caterva import tls
from caterva.studio import capabilities

REPO = Path(__file__).resolve().parents[2]


def _no_default_certificates(monkeypatch):
    monkeypatch.setattr(tls, "default_certificates_exist", lambda: False)


def test_the_bundle_is_chosen_when_the_build_default_is_missing(monkeypatch):
    _no_default_certificates(monkeypatch)
    environ = {}
    assert tls.trust_bundled_certificates(environ) == certifi.where()
    assert environ == {"SSL_CERT_FILE": certifi.where()}


@pytest.mark.parametrize("name", tls.USER_CERTIFICATE_SETTINGS)
def test_a_certificate_setting_the_user_made_is_left_alone(monkeypatch, name):
    _no_default_certificates(monkeypatch)
    environ = {name: "/somewhere/else.pem"}
    assert tls.trust_bundled_certificates(environ) is None
    assert environ == {name: "/somewhere/else.pem"}


def test_a_default_that_really_exists_is_left_alone(monkeypatch):
    monkeypatch.setattr(tls, "default_certificates_exist", lambda: True)
    environ = {}
    assert tls.trust_bundled_certificates(environ) is None
    assert environ == {}


def test_nothing_is_chosen_when_the_bundle_cannot_be_found(monkeypatch):
    _no_default_certificates(monkeypatch)
    monkeypatch.setattr(tls, "bundled_ca_file", lambda: None)
    environ = {}
    assert tls.trust_bundled_certificates(environ) is None and environ == {}


def test_a_default_context_made_after_the_call_trusts_the_bundle():
    """The real mechanism: a fresh Python with no certificate file of its own, told only by SSL_CERT_FILE."""
    code = (
        "import ssl, sys\n"
        "ctx = ssl.create_default_context()\n"
        "print(ctx.cert_store_stats()['x509_ca'])\n"
    )
    env = {"PATH": "/usr/bin:/bin", "SSL_CERT_FILE": certifi.where(), "SSL_CERT_DIR": "/nonexistent"}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60)
    assert done.returncode == 0, done.stderr
    assert int(done.stdout.strip()) > 50  # certifi carries well over a hundred authorities


def test_the_client_context_verifies_and_carries_authorities(monkeypatch):
    _no_default_certificates(monkeypatch)
    context = tls.client_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True
    assert context.cert_store_stats()["x509_ca"] > 50


def test_the_app_entry_point_sets_the_certificates_before_any_command(monkeypatch):
    from caterva import app

    called = []
    monkeypatch.setattr(tls, "trust_bundled_certificates", lambda *a, **k: called.append(1))
    assert app.main(["--version"]) == 0
    assert called == []  # --version needs no network and runs nothing
    monkeypatch.setitem(app.COMMANDS, "probe-tls-test", ("caterva.tls", "x"))
    monkeypatch.setattr("caterva.tls.main", lambda rest, prog=None: 0, raising=False)
    assert app.main(["probe-tls-test"]) == 0
    assert called == [1]


def test_a_certificate_failure_is_explained_in_the_status(monkeypatch):
    def refuse(request, timeout, context=None):
        raise capabilities.urllib.error.URLError(ssl.SSLCertVerificationError(
            1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate"))

    monkeypatch.setattr(capabilities.urllib.request, "urlopen", refuse)
    reason = capabilities.https_head("rest.uniprot.org", 5)
    assert "certificate could not be verified" in reason and "proxy" in reason
    assert "CERTIFICATE_VERIFY_FAILED" not in reason


def test_the_reachability_check_passes_the_verifying_context(monkeypatch):
    seen = {}

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake(request, timeout, context=None):
        seen["context"] = context
        return Answer()

    monkeypatch.setattr(capabilities.urllib.request, "urlopen", fake)
    assert capabilities.https_head("rest.uniprot.org", 5) is None
    assert isinstance(seen["context"], ssl.SSLContext) and seen["context"].verify_mode == ssl.CERT_REQUIRED
