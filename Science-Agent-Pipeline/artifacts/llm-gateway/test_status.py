"""The read-out, tested the way the ledger is: exactly, and without a network.

WHY THESE TESTS CAN BE EXACT
----------------------------
`main()` takes argv, the environment, both output streams, the clock and the
probe transport as parameters. So a test drives the real CLI -- the same
argument parsing, the same formatting, the same exit code -- with no
subprocess, no monkeypatching and no HTTP. What is asserted here is the actual
output a person or a monitor would see.

THE FOUR THINGS THAT MATTER
---------------------------
1. THE EXIT CODE. It is the only part of this command a script reads. 0 must
   mean "something left to try" and 1 must mean "nothing is", with a third code
   for "could not check" -- because a monitor that reads a failed check as an
   outage pages someone at 3am for a missing dependency.
2. NO KEY IN THE OUTPUT, under every flag combination. Not the value and not a
   prefix. The realistic leak is not this code printing a key deliberately; it
   is a provider rejecting a key with a 401 that quotes it back, reported
   verbatim. One test below makes the fake transport do exactly that.
3. UNKNOWN STAYS UNKNOWN. A probe that succeeds and reports no headers must not
   promote a provider to AVAILABLE, and an unmeasured provider's headroom must
   be null rather than a figure taken from documentation. That is the same rule
   `quota.py` is built around, applied to the output format.
4. THESE TESTS PASS WITHOUT litellm INSTALLED, which is the condition of this
   sandbox and of any machine that has not installed the optional proxy. The
   probe path is exercised through an injected fake; the real transport is
   asserted only to refuse politely.
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pytest

from quota import (
    ABSENT, AVAILABLE, EXHAUSTED, PROVIDERS, PROVIDERS_BY_NAME, UNKNOWN, Ledger,
)
from status import (
    ACCOUNT_EMAIL, EXIT_CANNOT_ANSWER, EXIT_DRY, EXIT_OK,
    MIN_SCRUBBABLE_SECRET, ProbeOutcome, ProbeUnavailable, build_parser,
    litellm_transport, main, redact, secret_values,
)

LITELLM_INSTALLED = importlib.util.find_spec("litellm") is not None

#: Deliberately opaque, and deliberately not containing any provider name or
#: any other string that legitimately appears in the output -- so that finding
#: one of these in stdout can only mean a leak, never a coincidence.
KEY_VALUES = {
    "groq": "sk-7Qv3ZtR9mKpLxA2bNcJd",
    "openrouter": "sk-or-v1-4Hs8WdY6nJfTuE1gQz",
    "mistral": "9cVbN2mXsQ7wLpZaEr4Ty",
    "siliconflow": "sk-3Tg6YhU8jKlO1pAsDfGh",
    "tokenrouter": "tr-2Zx5Cv8Bn4MqWe7RtYuI",
}
ALL_KEYS = {
    PROVIDERS_BY_NAME[name].key_env_var: value
    for name, value in KEY_VALUES.items()
}
GROQ = PROVIDERS_BY_NAME["groq"]
NOW = 1000.0


def run(
    argv: Sequence[str],
    *,
    path: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
    transport: Any = None,
    now: float = NOW,
) -> Tuple[int, str, str]:
    """Drive the real CLI and return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    args = list(argv)
    if path is not None:
        args += ["--ledger", str(path)]
    code = main(
        args,
        environ=dict(ALL_KEYS if environ is None else environ),
        transport=transport,
        stdout=out,
        stderr=err,
        now=now,
    )
    return code, out.getvalue(), err.getvalue()


def seed(
    path: Path,
    entries: Mapping[str, Tuple[Mapping[str, str], Optional[int]]],
    *,
    environ: Optional[Mapping[str, str]] = None,
    now: float = NOW,
) -> None:
    """Write a ledger file as if those calls had already happened."""
    book = Ledger(path=path, environ=dict(ALL_KEYS if environ is None else environ))
    for name, (headers, status) in entries.items():
        book.record(name, headers=headers, status=status, now=now)
    book.save()


def fake_transport(
    outcomes: Optional[Mapping[str, ProbeOutcome]] = None,
    *,
    calls: Optional[List[Tuple[str, str, float]]] = None,
    default: Optional[ProbeOutcome] = None,
):
    """A probe transport that answers from a table instead of the network."""
    table = dict(outcomes or {})
    fallback = default or ProbeOutcome(status=200, headers={})

    def transport(provider, api_key, *, timeout):
        if calls is not None:
            calls.append((provider.name, api_key, timeout))
        return table.get(provider.name, fallback)

    return transport


def echoing_transport():
    """A transport that leaks the key the way a real provider does.

    Providers reject a bad key with a message that quotes it back. That message
    is the one string in this whole command that plausibly contains a secret,
    so it is what the redaction tests push through.
    """

    def transport(provider, api_key, *, timeout):
        return ProbeOutcome(
            status=401,
            headers={"x-ratelimit-remaining-requests": "5"},
            error=f"AuthenticationError: invalid api key {api_key!r}",
        )

    return transport


ALL_EXHAUSTED = {
    provider.name: ({"retry-after": "86400"}, 429) for provider in PROVIDERS
}


class TestTheExitCodeIsTheContract:
    """The exit code is the only part of this command a script reads, so it
    carries the whole health check.
    """

    def test_a_measured_provider_exits_zero(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        seed(path, {"groq": ({"x-ratelimit-remaining-requests": "500"}, 200)})
        code, stdout, _ = run([], path=path)
        assert code == EXIT_OK
        assert "groq: available" in stdout

    def test_everything_exhausted_exits_one(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        seed(path, ALL_EXHAUSTED)
        code, stdout, _ = run([], path=path)
        assert code == EXIT_DRY
        assert "exit 1" in stdout
        assert "until the earliest reset above passes" in stdout

    def test_no_keys_at_all_exits_one(self, tmp_path: Path) -> None:
        # Nothing is exhausted; there is simply nothing configured. Same
        # practical outcome for a caller, so the same code.
        code, _, _ = run([], path=tmp_path / "ledger.json", environ={})
        assert code == EXIT_DRY

    def test_all_unknown_exits_zero_and_claims_nothing_more(
        self, tmp_path: Path
    ) -> None:
        """UNKNOWN counts toward 0 because a provider that reported nothing has
        not reported that it is out. The output has to say that exit 0 is not a
        promise, or the code quietly becomes one.
        """
        code, stdout, _ = run([], path=tmp_path / "ledger.json")
        assert code == EXIT_OK
        assert "does NOT claim the next call will succeed" in stdout

    def test_a_check_that_could_not_run_exits_two_not_one(
        self, tmp_path: Path
    ) -> None:
        """"I could not check" must never be read as "there is nothing left".
        One wakes somebody up for an outage that is not happening.
        """

        def refusing(provider, api_key, *, timeout):
            raise ProbeUnavailable("no transport available: pip install ...")

        code, _, stderr = run(
            ["--probe"], path=tmp_path / "ledger.json", transport=refusing
        )
        assert code == EXIT_CANNOT_ANSWER
        assert code not in (EXIT_OK, EXIT_DRY)
        assert "no transport available" in stderr

    def test_an_unreadable_ledger_still_answers(self, tmp_path: Path) -> None:
        # Losing the command because a cache file was truncated would be a
        # worse failure than the one wasted call relearning costs.
        path = tmp_path / "ledger.json"
        path.write_text("{ not json at all", encoding="utf-8")
        code, stdout, _ = run([], path=path)
        assert code == EXIT_OK
        assert "could not be read" in stdout


class TestTheJsonIsForAHealthCheck:
    def test_it_parses_and_names_every_provider(self, tmp_path: Path) -> None:
        code, stdout, _ = run(["--json"], path=tmp_path / "ledger.json")
        payload = json.loads(stdout)
        names = {entry["name"] for entry in payload["providers"]}
        assert names == {provider.name for provider in PROVIDERS}
        assert payload["account"] == ACCOUNT_EMAIL
        assert code == EXIT_OK

    def test_the_payload_carries_the_same_exit_code(self, tmp_path: Path) -> None:
        # Two sources of truth for "is it ok" would eventually disagree.
        path = tmp_path / "ledger.json"
        seed(path, ALL_EXHAUSTED)
        code, stdout, _ = run(["--json"], path=path)
        payload = json.loads(stdout)
        assert payload["exit_code"] == code == EXIT_DRY
        assert payload["ok"] is False

    def test_every_provider_reports_a_complete_row(self, tmp_path: Path) -> None:
        _, stdout, _ = run(["--json"], path=tmp_path / "ledger.json")
        for entry in json.loads(stdout)["providers"]:
            assert entry["availability"] in (AVAILABLE, UNKNOWN, EXHAUSTED, ABSENT)
            assert entry["key_env_var"].endswith("_API_KEY")
            assert entry["key_set"] is True
            assert entry["reason"]
            assert entry["documentation"].startswith("http")

    def test_an_unmeasured_provider_has_a_null_headroom_not_a_guess(
        self, tmp_path: Path
    ) -> None:
        """THE ANTI-HARDCODING TEST. Every provider here publishes a free-tier
        limit somewhere, and filling one in from documentation would make the
        output look complete while reporting a number nobody measured -- wrong
        in the worst direction, since it claims headroom that may be gone.
        """
        _, stdout, _ = run(["--json"], path=tmp_path / "ledger.json")
        payload = json.loads(stdout)
        for entry in payload["providers"]:
            assert entry["headroom"] is None, entry["name"]
            assert entry["last_reading_at"] is None, entry["name"]
        assert payload["claims"]["hardcoded_rate_limits"] is False

    def test_a_measured_headroom_is_the_reported_number(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "ledger.json"
        seed(path, {"groq": ({
            "x-ratelimit-remaining-requests": "42",
            "x-ratelimit-remaining-tokens": "90000",
        }, 200)})
        _, stdout, _ = run(["--json"], path=path)
        groq = next(
            entry for entry in json.loads(stdout)["providers"]
            if entry["name"] == "groq"
        )
        # The smaller of the two budgets, because that is what limits the
        # next call.
        assert groq["headroom"] == 42.0

    def test_it_states_that_unknown_is_not_available(self, tmp_path: Path) -> None:
        _, stdout, _ = run(["--json"], path=tmp_path / "ledger.json")
        payload = json.loads(stdout)
        assert payload["claims"]["unknown_is_not_available"] is True
        assert "not that the next call will succeed" in payload["claims"]["ok_means"]

    def test_the_chain_omits_exhausted_providers(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        seed(path, {"groq": ({"retry-after": "3600"}, 429)})
        _, stdout, _ = run(["--json"], path=path)
        payload = json.loads(stdout)
        assert "groq" not in payload["chain"]
        assert payload["counts"][EXHAUSTED] == 1


FLAG_COMBINATIONS = [
    [],
    ["--json"],
    ["--probe"],
    ["--probe", "--json"],
    ["--reset"],
    ["--reset", "--json"],
    ["--reset", "--probe", "--json"],
    ["--help"],
]


class TestNoKeyEverAppearsInOutput:
    """A key value in a terminal is a key value in a scrollback buffer, a CI
    log and a screenshot.
    """

    @pytest.mark.parametrize("flags", FLAG_COMBINATIONS, ids=lambda f: " ".join(f) or "(none)")
    def test_no_flag_combination_prints_a_key(
        self, tmp_path: Path, flags: List[str]
    ) -> None:
        path = tmp_path / "ledger.json"
        seed(path, {"groq": ({"x-ratelimit-remaining-requests": "7"}, 200)})
        _, stdout, stderr = run(
            flags, path=path, transport=echoing_transport()
        )
        # --reset removes the file, so it only contributes when it survived.
        persisted = path.read_text(encoding="utf-8") if path.exists() else ""
        everything = stdout + stderr + persisted
        for value in KEY_VALUES.values():
            assert value not in everything, f"{flags} leaked a key"

    def test_not_even_a_prefix(self, tmp_path: Path) -> None:
        """Four characters is enough to match a key against one that leaked
        elsewhere, and enough to confirm a guess about which account is in use.
        A truncated key is a disclosure, not a convenience.
        """
        _, stdout, stderr = run(
            ["--probe"],
            path=tmp_path / "ledger.json",
            transport=echoing_transport(),
        )
        for value in KEY_VALUES.values():
            for length in (4, 8, 12):
                assert value[:length] not in stdout + stderr, value[:length]

    def test_a_provider_echoing_the_key_back_is_scrubbed(
        self, tmp_path: Path
    ) -> None:
        """The realistic leak path. The 401 text is reported verbatim because
        an operator needs to see it, which is exactly why it goes through the
        scrubber first.
        """
        _, stdout, _ = run(
            ["--probe"],
            path=tmp_path / "ledger.json",
            transport=echoing_transport(),
        )
        assert "AuthenticationError" in stdout  # the message did get reported
        assert "<redacted>" in stdout
        assert KEY_VALUES["groq"] not in stdout

    def test_the_variable_name_is_printed_because_that_is_the_useful_part(
        self, tmp_path: Path
    ) -> None:
        _, stdout, _ = run([], path=tmp_path / "ledger.json")
        for provider in PROVIDERS:
            assert provider.key_env_var in stdout

    def test_an_unset_key_is_named_as_unset(self, tmp_path: Path) -> None:
        environ = dict(ALL_KEYS)
        environ[GROQ.key_env_var] = ""
        _, stdout, _ = run([], path=tmp_path / "ledger.json", environ=environ)
        assert "GROQ_API_KEY" in stdout
        assert "NOT SET" in stdout

    def test_the_ledger_file_holds_no_secrets_either(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        run(
            ["--probe"], path=path,
            transport=fake_transport({
                "groq": ProbeOutcome(
                    status=200,
                    headers={"x-ratelimit-remaining-requests": "12"},
                ),
            }),
        )
        text = path.read_text(encoding="utf-8")
        for value in KEY_VALUES.values():
            assert value not in text
        assert "GROQ_API_KEY" not in text


class TestRedactionIsStructuralNotDiligence:
    def test_it_collects_the_configured_keys(self) -> None:
        found = secret_values(ALL_KEYS)
        assert set(found) == set(KEY_VALUES.values())

    def test_longer_secrets_are_removed_first(self) -> None:
        # A key that contains another key as a substring must be removed
        # whole, not left as a hole with the ends still readable.
        text = "value=abcdefghij-extra"
        assert redact(text, ("abcdefghij", "abcdefghij-extra")) == "value=<redacted>"

    def test_a_short_value_is_not_used_for_scrubbing_and_that_is_stated(
        self,
    ) -> None:
        """A documented hole rather than a silent one: scrubbing a two-character
        secret would blank fragments of every line and corrupt the JSON. Nothing
        prints a key value in the first place -- the scrubber is the backstop,
        not the mechanism.
        """
        short = "x" * (MIN_SCRUBBABLE_SECRET - 1)
        assert secret_values({GROQ.key_env_var: short}) == ()

    def test_an_unset_environment_has_nothing_to_scrub(self) -> None:
        assert secret_values({}) == ()


class TestProbeMovesAProviderOutOfUnknown:
    """Three of the five providers report nothing except on a real call, so a
    probe is the only thing that can measure them. It is opt-in because it
    spends the budget it measures.
    """

    def test_measured_headers_promote_a_provider(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        _, before, _ = run(["--json"], path=path)
        assert all(
            entry["availability"] == UNKNOWN
            for entry in json.loads(before)["providers"]
        )

        _, stdout, _ = run(
            ["--probe", "--json"], path=path,
            transport=fake_transport({
                "groq": ProbeOutcome(status=200, headers={
                    "x-ratelimit-remaining-requests": "1399",
                    "x-ratelimit-remaining-tokens": "58000",
                }),
            }),
        )
        groq = next(
            entry for entry in json.loads(stdout)["providers"]
            if entry["name"] == "groq"
        )
        assert groq["availability"] == AVAILABLE
        assert groq["headroom"] == 1399.0

    def test_an_answered_call_reporting_nothing_stays_unknown(
        self, tmp_path: Path
    ) -> None:
        """The honest outcome, and the one it would be tempting to round up.
        One answered call is evidence the key works; it is not a measurement of
        what is left, and recording it as headroom would invent a number.
        """
        _, stdout, _ = run(
            ["--probe", "--json"], path=tmp_path / "ledger.json",
            transport=fake_transport(default=ProbeOutcome(status=200, headers={})),
        )
        payload = json.loads(stdout)
        for entry in payload["providers"]:
            assert entry["availability"] == UNKNOWN, entry["name"]
            assert entry["headroom"] is None, entry["name"]
        assert any(
            "not a measurement" in (report["note"] or "")
            for report in payload["probe"]
        )

    def test_a_429_during_a_probe_is_recorded_as_exhausted(
        self, tmp_path: Path
    ) -> None:
        _, stdout, _ = run(
            ["--probe", "--json"], path=tmp_path / "ledger.json",
            transport=fake_transport({
                "groq": ProbeOutcome(
                    status=429,
                    headers={"x-ratelimit-remaining-requests": "0",
                             "retry-after": "600"},
                ),
            }),
        )
        groq = next(
            entry for entry in json.loads(stdout)["providers"]
            if entry["name"] == "groq"
        )
        assert groq["availability"] == EXHAUSTED
        assert groq["retry_in_seconds"] == 600.0

    def test_a_provider_with_no_key_is_not_probed(self, tmp_path: Path) -> None:
        # There is nothing to authenticate with, and a failure recorded against
        # a provider that was never in play is a lie in the ledger.
        environ = dict(ALL_KEYS)
        environ[PROVIDERS_BY_NAME["mistral"].key_env_var] = ""
        calls: List[Tuple[str, str, float]] = []
        _, stdout, _ = run(
            ["--probe", "--json"], path=tmp_path / "ledger.json",
            environ=environ, transport=fake_transport(calls=calls),
        )
        assert "mistral" not in [name for name, _, _ in calls]
        report = next(
            entry for entry in json.loads(stdout)["probe"]
            if entry["provider"] == "mistral"
        )
        assert report["attempted"] is False
        assert "MISTRAL_API_KEY is not set" in report["note"]

    def test_the_transport_receives_the_key_and_the_timeout(
        self, tmp_path: Path
    ) -> None:
        calls: List[Tuple[str, str, float]] = []
        run(
            ["--probe", "--timeout", "3.5"], path=tmp_path / "ledger.json",
            transport=fake_transport(calls=calls),
        )
        assert len(calls) == len(PROVIDERS)
        by_name = {name: (key, timeout) for name, key, timeout in calls}
        assert by_name["groq"] == (KEY_VALUES["groq"], 3.5)

    def test_what_a_probe_measured_survives_into_the_next_run(
        self, tmp_path: Path
    ) -> None:
        # Otherwise every health check would have to probe again, which is the
        # cost this command exists to keep down.
        path = tmp_path / "ledger.json"
        run(
            ["--probe"], path=path,
            transport=fake_transport({
                "groq": ProbeOutcome(status=200, headers={
                    "x-ratelimit-remaining-requests": "88",
                }),
            }),
        )
        _, stdout, _ = run(["--json"], path=path)
        groq = next(
            entry for entry in json.loads(stdout)["providers"]
            if entry["name"] == "groq"
        )
        assert groq["availability"] == AVAILABLE
        assert groq["headroom"] == 88.0

    def test_the_human_output_says_the_probe_cost_something(
        self, tmp_path: Path
    ) -> None:
        _, stdout, _ = run(
            ["--probe"], path=tmp_path / "ledger.json",
            transport=fake_transport(),
        )
        assert "5 request(s) spent" in stdout
        assert "gone from today's budget" in stdout

    def test_a_transport_that_raises_does_not_rest_a_working_provider(
        self, tmp_path: Path
    ) -> None:
        """A bug on our side is not a provider malfunction. Recording it as one
        would take a healthy provider out of the chain for two minutes because
        of our own error.
        """

        def broken(provider, api_key, *, timeout):
            raise ValueError("transport is misconfigured")

        _, stdout, _ = run(
            ["--probe", "--json"], path=tmp_path / "ledger.json",
            transport=broken,
        )
        payload = json.loads(stdout)
        for entry in payload["providers"]:
            assert entry["calls"] == 0, entry["name"]
            assert entry["availability"] == UNKNOWN, entry["name"]
        assert all(
            "nothing was recorded" in (report["note"] or "")
            for report in payload["probe"]
        )

    def test_probing_is_not_the_default(self, tmp_path: Path) -> None:
        # The whole reason it is a flag: a health check on a cron would spend a
        # meaningful fraction of a 50-a-day free tier on monitoring.
        calls: List[Tuple[str, str, float]] = []
        run([], path=tmp_path / "ledger.json", transport=fake_transport(calls=calls))
        assert calls == []


class TestReset:
    def test_reset_deletes_the_file(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        seed(path, {"groq": ({"retry-after": "86400"}, 429)})
        assert path.exists()

        code, stdout, _ = run(["--reset"], path=path)
        assert not path.exists()
        assert "ledger cleared" in stdout
        assert code == EXIT_OK

    def test_reset_reports_from_a_clean_slate(self, tmp_path: Path) -> None:
        """A reset has to actually forget, not merely delete the file and then
        print what was already loaded into memory.
        """
        path = tmp_path / "ledger.json"
        seed(path, ALL_EXHAUSTED)
        code, stdout, _ = run(["--reset", "--json"], path=path)
        payload = json.loads(stdout)
        assert payload["ledger_was_reset"] is True
        for entry in payload["providers"]:
            assert entry["availability"] == UNKNOWN, entry["name"]
            assert entry["calls"] == 0, entry["name"]
        assert code == EXIT_OK

    def test_reset_on_a_missing_file_is_not_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "never-existed.json"
        code, stdout, _ = run(["--reset"], path=path)
        assert code == EXIT_OK
        assert "nothing to clear" in stdout

    def test_reset_does_not_write_a_new_file_on_its_own(
        self, tmp_path: Path
    ) -> None:
        # Reporting is read-only. Only a probe has something new to persist.
        path = tmp_path / "ledger.json"
        seed(path, {"groq": ({"x-ratelimit-remaining-requests": "5"}, 200)})
        run(["--reset"], path=path)
        assert not path.exists()


class TestTheHelpTextSaysWhatThingsCost:
    def test_it_says_probe_spends_quota(self, tmp_path: Path) -> None:
        """Opt-in is not enough on its own. Someone reading --help has to learn
        that measuring the budget consumes it, or they will put it on a cron.
        """
        code, stdout, _ = run(["--help"])
        assert code == EXIT_OK
        assert "spends quota" in stdout.lower()
        assert "opt-in" in stdout.lower()

    def test_the_help_text_is_also_reachable_from_the_parser(self) -> None:
        help_text = build_parser().format_help()
        assert "spends quota" in help_text.lower()

    def test_it_says_keys_are_never_printed(self) -> None:
        help_text = build_parser().format_help()
        assert "never printed" in help_text
        assert ACCOUNT_EMAIL in help_text

    def test_it_documents_all_three_exit_codes(self) -> None:
        help_text = build_parser().format_help()
        for phrase in ("Exits 0", "1 when every", "2 when the question"):
            assert phrase in help_text

    def test_help_prints_no_keys(self) -> None:
        _, stdout, _ = run(["--help"])
        for value in KEY_VALUES.values():
            assert value not in stdout


class TestItWorksWithoutLitellm:
    """A hard requirement, not a preference. litellm is not in
    requirements.txt, PyPI is unreachable from this sandbox, and the gateway's
    status must still be checkable on a machine that never installed the proxy.
    """

    def test_importing_this_module_does_not_need_litellm(self) -> None:
        # Guaranteed by the whole file having been imported already, and stated
        # so the requirement is visible in the suite rather than implied.
        import status
        assert status.litellm_transport is litellm_transport

    def test_every_view_except_probe_works_without_a_transport(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "ledger.json"
        for flags in ([], ["--json"], ["--reset"], ["--help"]):
            code, stdout, stderr = run(flags, path=path, transport=None)
            assert code == EXIT_OK, (flags, stderr)
            assert stdout

    @pytest.mark.skipif(
        LITELLM_INSTALLED,
        reason="litellm is installed, so the refusal path cannot be reached "
               "and calling the real transport would make a network request",
    )
    def test_the_default_transport_refuses_with_an_install_instruction(
        self,
    ) -> None:
        with pytest.raises(ProbeUnavailable) as caught:
            litellm_transport(GROQ, "irrelevant", timeout=1.0)
        message = str(caught.value)
        assert "pip install" in message
        assert "litellm" in message
        # And it says what still works, so the refusal is actionable rather
        # than a dead end.
        assert "--json" in message

    @pytest.mark.skipif(
        LITELLM_INSTALLED,
        reason="litellm is installed, so --probe would make a real network "
               "call and spend real quota",
    )
    def test_probe_without_litellm_exits_two_and_says_how_to_fix_it(
        self, tmp_path: Path
    ) -> None:
        code, _, stderr = run(
            ["--probe"], path=tmp_path / "ledger.json", transport=None
        )
        assert code == EXIT_CANNOT_ANSWER
        assert "pip install 'litellm[proxy]'" in stderr

    def test_the_refusal_does_not_print_a_key(self, tmp_path: Path) -> None:
        def refusing(provider, api_key, *, timeout):
            raise ProbeUnavailable(f"cannot probe with {api_key}")

        _, stdout, stderr = run(
            ["--probe"], path=tmp_path / "ledger.json", transport=refusing
        )
        assert KEY_VALUES["groq"] not in stdout + stderr
        assert "<redacted>" in stderr
