"""The waterfall's ordering, tested exactly because it is pure.

WHY THESE TESTS CAN BE EXACT
----------------------------
The ledger makes no network calls and does not import litellm. It takes
headers in and produces an order out, so every case here is a known input
with a known right answer -- no mocking of an HTTP client, no flakiness, no
"probably works".

That split was the point of putting the decision in its own module. litellm
does the transport; this decides who to ask. A bug in the ordering is a bug in
a function.

WHAT MOST OF THESE TESTS ARE ABOUT
-----------------------------------
The three-state availability. `AVAILABLE`, `EXHAUSTED` and `UNKNOWN` have to
stay apart, because a provider that reported nothing has NOT reported that it
is fine -- and folding UNKNOWN into AVAILABLE makes the gateway most confident
about the providers it knows least about.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quota import (
    ABSENT, AVAILABLE, CONSECUTIVE_FAILURES_BEFORE_REST, EXHAUSTED,
    FAILURE_REST_SECONDS, PROVIDERS, PROVIDERS_BY_NAME, UNKNOWN, Ledger,
    Provider, QuotaError, Reading, parse_duration, read_headers,
)

ALL_KEYS = {p.key_env_var: "test-key-value" for p in PROVIDERS}
GROQ = PROVIDERS_BY_NAME["groq"]


def ledger(**overrides) -> Ledger:
    environ = dict(ALL_KEYS)
    environ.update(overrides.pop("environ", {}))
    return Ledger(environ=environ, **overrides)


class TestReadingWhatProvidersActuallySend:
    """Header names are from each provider's own documentation.

    Groq documents `x-ratelimit-remaining-requests`; OpenRouter documents
    `X-RateLimit-Remaining`. A case-sensitive parser would read one and not
    the other, and the symptom would be a provider stuck in UNKNOWN forever.
    """

    def test_groq_headers_are_read(self) -> None:
        reading = read_headers(GROQ, {
            "x-ratelimit-remaining-requests": "1400",
            "x-ratelimit-remaining-tokens": "58000",
            "x-ratelimit-reset-requests": "2m30s",
            "x-ratelimit-reset-tokens": "7.5s",
        }, status=200, now=1000.0)

        assert reading.remaining_requests == 1400.0
        assert reading.remaining_tokens == 58000.0
        assert reading.reset_requests_in == 150.0
        assert reading.reset_tokens_in == 7.5

    def test_header_lookup_is_case_insensitive(self) -> None:
        # HTTP header names are case-insensitive and the two providers whose
        # docs were read disagree on case.
        upper = read_headers(GROQ, {
            "X-RateLimit-Remaining-Requests": "7",
        }, now=1000.0)
        assert upper.remaining_requests == 7.0

    def test_a_provider_that_says_nothing_reports_nothing(self) -> None:
        reading = read_headers(GROQ, {}, status=200, now=1000.0)
        assert not reading.reported_anything
        assert reading.headroom is None

    def test_headroom_is_the_smaller_of_the_two_budgets(self) -> None:
        """A provider with a million tokens left and two requests left can
        serve two more calls. Taking the larger, or an average, would report
        headroom the provider does not have.
        """
        reading = read_headers(GROQ, {
            "x-ratelimit-remaining-requests": "2",
            "x-ratelimit-remaining-tokens": "1000000",
        }, now=1000.0)
        assert reading.headroom == 2.0

    def test_retry_after_wins_over_a_reset_timer(self) -> None:
        # It is the provider telling us directly.
        reading = read_headers(GROQ, {
            "x-ratelimit-reset-requests": "600s",
            "retry-after": "30",
        }, status=429, now=1000.0)
        assert reading.available_again_at() == 1030.0

    def test_the_later_reset_wins_when_there_is_no_retry_after(self) -> None:
        # Both budgets have to refill before the call can succeed.
        reading = read_headers(GROQ, {
            "x-ratelimit-reset-requests": "10s",
            "x-ratelimit-reset-tokens": "90s",
        }, status=429, now=1000.0)
        assert reading.available_again_at() == 1090.0


class TestDurationParsing:
    """Reading `1m30s` as 1 second retries 89 seconds early and burns a 429
    every cycle, so the compound forms have to work.
    """

    def test_bare_seconds(self) -> None:
        assert parse_duration("7") == 7.0
        assert parse_duration("2.5") == 2.5

    def test_suffixed_and_compound_forms(self) -> None:
        assert parse_duration("30s") == 30.0
        assert parse_duration("2m") == 120.0
        assert parse_duration("1m30s") == 90.0
        assert parse_duration("1h5m") == 3900.0
        assert parse_duration("1d") == 86400.0

    def test_unparseable_returns_none_not_zero(self) -> None:
        """Zero means "retry immediately" and would turn an unreadable
        header into a hot loop against a provider that just said no.
        """
        for value in ("soon", "", None, "1m30", "??", "10x"):
            assert parse_duration(value) is None, value

    def test_a_negative_duration_is_clamped_not_trusted(self) -> None:
        assert parse_duration("-5") == 0.0


class TestTheThreeStatesStayApart:
    def test_a_reported_remaining_count_is_available(self) -> None:
        book = ledger()
        book.record("groq", headers={
            "x-ratelimit-remaining-requests": "500",
        }, status=200, now=1000.0)
        assert book.standing(GROQ, now=1000.0).availability == AVAILABLE

    def test_a_reported_zero_is_exhausted(self) -> None:
        book = ledger()
        book.record("groq", headers={
            "x-ratelimit-remaining-requests": "0",
            "x-ratelimit-reset-requests": "600s",
        }, status=200, now=1000.0)
        assert book.standing(GROQ, now=1000.0).availability == EXHAUSTED

    def test_silence_is_unknown_and_not_available(self) -> None:
        """THE STATE THAT MATTERS. A provider that reported nothing has not
        reported that it is fine.
        """
        book = ledger()
        standing = book.standing(PROVIDERS_BY_NAME["mistral"], now=1000.0)
        assert standing.availability == UNKNOWN
        assert "unknown rather than assumed" in standing.reason

    def test_an_unset_key_is_absent_not_unknown(self) -> None:
        # Nothing was asked, which is different from having asked and heard
        # nothing back.
        book = ledger(environ={"GROQ_API_KEY": ""})
        standing = book.standing(GROQ, now=1000.0)
        assert standing.availability == ABSENT
        assert "GROQ_API_KEY" in standing.reason

    def test_a_reset_time_with_no_count_is_unknown(self) -> None:
        book = ledger()
        book.record("groq", headers={
            "x-ratelimit-reset-requests": "60s",
        }, status=200, now=1000.0)
        assert book.standing(GROQ, now=1000.0).availability == UNKNOWN


class TestOrderingIsByHeadroomNotPrice:
    """Every free tier costs the same zero, so a price-ordered list of free
    providers is an arbitrary list wearing a justification. Draining the
    roomiest first postpones the first exhaustion as far as it goes.
    """

    def test_the_roomiest_free_provider_goes_first(self) -> None:
        book = ledger()
        book.record("groq", headers={
            "x-ratelimit-remaining-requests": "10",
        }, status=200, now=1000.0)
        book.record("openrouter", headers={
            "x-ratelimit-remaining": "900",
        }, status=200, now=1000.0)

        order = [s.provider.name for s in book.order(now=1000.0)]
        assert order.index("openrouter") < order.index("groq")

    def test_measured_available_beats_unknown(self) -> None:
        # A measured yes beats a silence.
        book = ledger()
        book.record("groq", headers={
            "x-ratelimit-remaining-requests": "1",
        }, status=200, now=1000.0)

        order = [s.provider.name for s in book.order(now=1000.0)]
        assert order.index("groq") < order.index("mistral")

    def test_unknown_beats_exhausted(self) -> None:
        book = ledger()
        book.record("groq", headers={
            "x-ratelimit-remaining-requests": "0",
            "x-ratelimit-reset-requests": "3600s",
        }, status=429, now=1000.0)

        order = [s.provider.name for s in book.order(now=1000.0)]
        assert order.index("mistral") < order.index("groq")

    def test_absent_providers_are_listed_last_not_dropped(self) -> None:
        """The list stays complete so a caller can see WHY something is
        missing rather than finding it simply gone.
        """
        book = ledger(environ={"TOKENROUTER_API_KEY": ""})
        order = book.order(now=1000.0)
        assert order[-1].provider.name == "tokenrouter"
        assert len(order) == len(PROVIDERS)

    def test_a_priced_provider_comes_after_every_free_one(self) -> None:
        priced = Provider(
            name="paid", key_env_var="PAID_KEY", model="openai/gpt-4o-mini",
            cost_per_million_tokens=0.15,
        )
        book = Ledger(
            providers=(*PROVIDERS, priced),
            environ={**ALL_KEYS, "PAID_KEY": "k"},
        )
        order = [s.provider.name for s in book.order(now=1000.0)]
        assert order[-1] == "paid" or order.index("paid") > order.index("mistral")

    def test_this_module_declares_no_prices(self) -> None:
        # A price written here would be a number nobody in this repository
        # measured, and it would go stale silently.
        assert all(p.cost_per_million_tokens is None for p in PROVIDERS)
        assert all(p.free for p in PROVIDERS)


class TestRateLimitsAndFailuresAreDifferent:
    def test_a_429_blocks_until_the_provider_s_own_reset(self) -> None:
        book = ledger()
        book.record("groq", headers={
            "x-ratelimit-remaining-requests": "0",
            "retry-after": "45",
        }, status=429, now=1000.0)

        standing = book.standing(GROQ, now=1010.0)
        assert standing.availability == EXHAUSTED
        assert standing.blocked_until == 1045.0
        assert "provider gave a reset time" in standing.reason

    def test_a_429_with_no_reset_says_the_rest_is_ours(self) -> None:
        """The provider did not say when to come back, so the interval is
        this module's choice -- and the reason says so rather than implying
        the provider asked for it.
        """
        book = ledger()
        book.record("groq", headers={}, status=429, now=1000.0)
        standing = book.standing(GROQ, now=1001.0)
        assert standing.blocked_until == 1000.0 + FAILURE_REST_SECONDS
        assert "this module's" in standing.reason

    def test_a_429_is_not_counted_as_a_malfunction(self) -> None:
        # Being out of quota is the system working, not a broken provider.
        book = ledger()
        for _ in range(5):
            book.record("groq", headers={}, status=429, now=1000.0)
        assert book.states["groq"].consecutive_failures == 0
        assert book.states["groq"].rate_limits == 5

    def test_repeated_non_rate_failures_rest_the_provider(self) -> None:
        """A provider can be up, in quota, and still failing -- a retired
        model, an auth error after a key rotation.
        """
        book = ledger()
        for _ in range(CONSECUTIVE_FAILURES_BEFORE_REST):
            book.record("groq", headers={}, status=500, now=1000.0)

        standing = book.standing(GROQ, now=1001.0)
        assert standing.availability == EXHAUSTED
        assert "not rate limits" in standing.reason

    def test_one_success_clears_the_failure_streak(self) -> None:
        book = ledger()
        book.record("groq", headers={}, status=500, now=1000.0)
        book.record("groq", headers={}, status=200, now=1001.0)
        assert book.states["groq"].consecutive_failures == 0

    def test_a_success_does_not_clear_a_quota_block(self) -> None:
        """A provider can answer one call and still report zero remaining
        for the next. The reading decides, not the outcome.
        """
        book = ledger()
        book.record("groq", headers={
            "x-ratelimit-remaining-requests": "0",
            "x-ratelimit-reset-requests": "3600s",
        }, status=200, now=1000.0)
        assert book.standing(GROQ, now=1000.0).availability == EXHAUSTED

    def test_a_block_expires_on_its_own(self) -> None:
        book = ledger()
        book.record("groq", headers={"retry-after": "30"}, status=429, now=1000.0)
        assert book.standing(GROQ, now=1005.0).availability == EXHAUSTED
        # After the reset, it is UNKNOWN rather than AVAILABLE -- the block
        # expiring is not a report of remaining quota.
        assert book.standing(GROQ, now=1100.0).availability == UNKNOWN


class TestTheRefusal:
    def test_no_provider_left_refuses_and_lists_why(self) -> None:
        """The waterfall being dry is a real outcome and the message has to
        be actionable: which providers, why each, and when the soonest comes
        back.
        """
        book = Ledger(environ={})
        with pytest.raises(QuotaError) as caught:
            book.next_provider(now=1000.0)

        message = str(caught.value)
        assert "out of water" in message
        for provider in PROVIDERS:
            assert provider.key_env_var in message or provider.name in message

    def test_next_provider_never_returns_an_exhausted_one(self) -> None:
        book = ledger()
        for name in ("groq", "openrouter"):
            book.record(name, headers={"retry-after": "600"}, status=429, now=1000.0)
        chosen = book.next_provider(now=1000.0)
        assert chosen.name not in ("groq", "openrouter")

    def test_the_chain_omits_exhausted_providers(self) -> None:
        # litellm would try them, and a call we already know will 429 costs
        # a round trip and a retry budget.
        book = ledger()
        book.record("groq", headers={"retry-after": "600"}, status=429, now=1000.0)
        assert "groq" not in book.chain(now=1000.0)

    def test_an_unknown_provider_name_is_refused(self) -> None:
        book = ledger()
        with pytest.raises(QuotaError, match="not a known provider"):
            book.record("nope", headers={}, status=200)


class TestPersistence:
    """The interesting failure is a DAILY cap: a provider that ran out at
    noon must still be known to be out at one o'clock, and a gateway
    restarted in between would otherwise send a request it knows will fail.
    """

    def test_a_block_survives_a_restart(self, tmp_path: Path) -> None:
        path = tmp_path / "quota.json"
        first = Ledger(path=path, environ=ALL_KEYS)
        first.record("groq", headers={
            "x-ratelimit-remaining-requests": "0",
            "x-ratelimit-reset-requests": "86400s",
        }, status=429, now=1000.0)
        first.save()

        second = Ledger(path=path, environ=ALL_KEYS)
        assert second.standing(GROQ, now=1001.0).availability == EXHAUSTED

    def test_the_file_holds_no_secrets(self, tmp_path: Path) -> None:
        # Counters and reset times only. A quota cache that leaked a key
        # would be a far worse bug than any it prevents.
        path = tmp_path / "quota.json"
        book = Ledger(path=path, environ=ALL_KEYS)
        book.record("groq", headers={
            "x-ratelimit-remaining-requests": "5",
        }, status=200, now=1000.0)
        book.save()

        text = path.read_text(encoding="utf-8")
        assert "test-key-value" not in text
        assert "GROQ_API_KEY" not in text
        assert "no keys, no prompts, no responses" in text

    def test_a_corrupt_ledger_does_not_take_the_gateway_down(
        self, tmp_path: Path
    ) -> None:
        """The worst a lost ledger costs is one wasted 429 per provider while
        the real state is relearned from headers. Refusing to serve because
        a cache file was truncated would be the larger failure.
        """
        path = tmp_path / "quota.json"
        path.write_text("{ this is not json", encoding="utf-8")

        book = Ledger(path=path, environ=ALL_KEYS)
        assert book.next_provider(now=1000.0) is not None
        assert hasattr(book, "corrupt_reason")

    def test_saving_is_atomic(self, tmp_path: Path) -> None:
        # Written to a temporary file and renamed, so a crash mid-write
        # leaves the previous ledger rather than a truncated one.
        path = tmp_path / "quota.json"
        book = Ledger(path=path, environ=ALL_KEYS)
        book.save()
        assert path.exists()
        assert not list(tmp_path.glob("*.tmp"))
        assert json.loads(path.read_text(encoding="utf-8"))["providers"]


class TestTheSummarySaysWhatItKnows:
    def test_it_names_the_unknown_providers_as_unknown(self) -> None:
        book = ledger()
        summary = book.summary(now=1000.0)
        assert "UNKNOWN rather than available" in summary
        assert "not the same as reporting that they are fine" in summary

    def test_it_says_nothing_is_hardcoded(self) -> None:
        summary = ledger().summary(now=1000.0)
        assert "Nothing here hardcodes a rate limit" in summary
        assert "what each provider reported about itself" in summary

    def test_it_explains_why_not_price(self) -> None:
        summary = ledger().summary(now=1000.0)
        assert "every free tier costs the same zero" in summary

    def test_it_lists_missing_keys_by_variable_name(self) -> None:
        book = ledger(environ={"MISTRAL_API_KEY": ""})
        summary = book.summary(now=1000.0)
        assert "MISTRAL_API_KEY" in summary


class TestProvidersWithoutDocumentedHeaders:
    """Header fields are left EMPTY for providers whose docs were not read,
    rather than filled in by analogy with Groq. Guessing that SiliconFlow
    uses Groq's header names would produce a confident misreading.
    """

    def test_undocumented_providers_declare_no_headers(self) -> None:
        for name in ("mistral", "siliconflow", "tokenrouter"):
            provider = PROVIDERS_BY_NAME[name]
            assert not provider.reports_quota, name

    def test_documented_providers_declare_theirs(self) -> None:
        for name in ("groq", "openrouter"):
            assert PROVIDERS_BY_NAME[name].reports_quota, name

    def test_every_provider_cites_where_its_limits_come_from(self) -> None:
        for provider in PROVIDERS:
            assert provider.documentation.startswith("http"), provider.name


class TestEndpointsComeFromTheWorkingProviderTable:
    """A hostname recalled rather than checked is a host that a live key and
    a researcher's prompt get POSTed to on somebody's recollection.

    The gateway's first draft refused to write endpoints at all for exactly
    that reason, which was the right instinct and the wrong conclusion: the
    URLs were already in this repository, in the provider table the API
    server has been making successful calls with. Copying them from there is
    not memory, and this test is what keeps it from becoming memory.
    """

    def _api_server_table(self) -> dict:
        import re
        from pathlib import Path

        from quota import API_SERVER_PROVIDER_TABLE

        # Walk up to the repository root; the gateway lives four levels down.
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = parent / API_SERVER_PROVIDER_TABLE
            if candidate.exists():
                source = candidate.read_text(encoding="utf-8")
                break
        else:  # pragma: no cover - only in a split checkout
            pytest.skip(f"{API_SERVER_PROVIDER_TABLE} is not in this checkout")

        # Each entry reads `name: {\n apiUrl: "...",` -- pair them in order.
        pairs = re.findall(
            r"^\s{2}(\w+):\s*\{\s*\n\s*apiUrl:\s*\"([^\"]+)\"",
            source,
            re.MULTILINE,
        )
        return dict(pairs)

    def test_the_table_is_readable_and_not_empty(self) -> None:
        # If the parse ever returns nothing, every comparison below would
        # pass vacuously -- which is the failure mode this file exists to
        # avoid elsewhere.
        table = self._api_server_table()
        assert len(table) >= 5, table

    def test_every_endpoint_matches_the_api_server(self) -> None:
        table = self._api_server_table()
        for provider in PROVIDERS:
            assert provider.api_base is not None, provider.name
            assert provider.name in table, (
                f"{provider.name} is in the waterfall but not in the API "
                f"server's provider table"
            )
            assert provider.api_base == table[provider.name], provider.name

    def test_every_endpoint_is_https(self) -> None:
        # A key sent over http is a key in the clear.
        for provider in PROVIDERS:
            assert (provider.api_base or "").startswith("https://"), provider.name
