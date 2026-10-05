"""Redaction (what may leave the machine) and scrubbing (what may be written or shown).

The key-shaped strings below are made up for the test: they have the SHAPE of a
provider's key (a documented prefix and length) and open no account.
"""
from __future__ import annotations

import pytest

from caterva.assistant.redact import KEY_PATTERNS, find_keys, looks_like_key, redact_text, scrub

HOME = "/Users/ada"

KEYS = [
    "sk-ant-api03-AbCdEfGhIjK" "lMnOpQrStUvWxYz0123456789",
    "sk-proj-AbCdEfGhIjKlMnOp" "QrStUvWxYz0123456789abcd",
    "sk-AbCdEfGhIjKlMnOpQr" "StUvWxYz0123456789abcd",
    "sk-or-v1-0123456789abcdef012" "3456789abcdef0123456789abcdef",
    "gsk_AbCdEfGhIjKlMnOp" "QrStUvWxYz0123456789",
    "AIzaSyA1234567890abc" "defghijklmnopqrstuvw",
    "xai-AbCdEfGhIjKlMn" "OpQrStUvWxYz012345",
    "hf_AbCdEfGhIjKlMnOp" "QrStUvWxYz0123456789",
    "ghp_AbCdEfGhIjKlMnOp" "QrStUvWxYz0123456789",
    "AKIAABCDEF" "GHIJKLMNOP",
    "0123456789abcdef" "0123456789abcdef",
    "0123456789ABCDEF01234567" "89ABCDEF0123456789ABCDEF",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NT" "Y3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r",
    "Bearer abcdefghijklmn" "opqrstuvwxyz0123456789",
    "x-api-key: abcdef" "ghijklmnop12345678",
]


@pytest.mark.parametrize("key", KEYS)
def test_key_shapes_are_found_and_scrubbed(key):
    text = f"the provider said it rejected {key} for this account"
    assert looks_like_key(text)
    assert find_keys(text)
    assert key.split(" ")[-1] not in scrub(text)
    assert key.split(" ")[-1] not in redact_text(text, home=HOME)


def test_ordinary_science_is_not_a_key():
    for text in ["Km 0.03 mM and kcat 100 1/s", "BRENDA ref 286469", "EC 1.1.1.27 in Homo sapiens",
                 "the sk value", "task-1 and sk-1", "1I10 and 1L63", "k_cat / K_m = 1e6 1/(M s)"]:
        assert scrub(text) == text, text


def test_an_exact_secret_is_removed_even_when_it_has_no_known_shape():
    secret = "plain-secret-without-shape-77"
    assert secret not in scrub(f"error: bad key {secret}", [secret])
    assert scrub("abc", ["a"]) == "abc", "a one-letter 'secret' must not blank ordinary words"


def test_paths_the_home_folder_and_the_user_name_are_redacted():
    text = (f"Open {HOME}/Desktop/Coding/data/patient_smith.csv and ~/notes/run.txt, "
            f"as ada, in C:\\Users\\ada\\lab\\x.csv; the data is at /private/var/folders/xy/T/caterva/data/runs")
    out = redact_text(text, home=HOME, data_dir="/private/var/folders/xy/T/caterva/data", user_names=["ada"])
    assert "patient_smith" not in out and "/Users" not in out and "Desktop" not in out
    assert "C:\\Users" not in out and "lab" not in out.replace("<", "")
    assert "ada" not in out.replace("[user]", "")
    assert "[path]" in out and "[user]" in out


def test_a_unit_is_not_a_path_and_a_url_keeps_its_slashes():
    text = "kcat 100 1/s, Km 0.03 mM, rate 3 mM/s, https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27"
    assert redact_text(text, home=HOME) == text


def test_email_addresses_are_redacted():
    assert "ada@example.org" not in redact_text("write to ada@example.org about it", home=HOME)


def test_the_user_name_inside_a_word_is_left_alone():
    out = redact_text("Adaptation and canada", home=HOME, user_names=["ada"])
    assert out == "Adaptation and canada"


def test_redaction_is_idempotent():
    text = f"{HOME}/a/b.csv and sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
    once = redact_text(text, home=HOME)
    assert redact_text(once, home=HOME) == once


def test_there_is_a_pattern_for_every_documented_prefix():
    prefixes = ("sk-ant-", "sk-", "gsk_", "AIza")
    for prefix in prefixes:
        assert any(p.pattern.startswith(prefix) or prefix in p.pattern for p in KEY_PATTERNS), prefix
