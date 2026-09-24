"""The waterfall loop, tested with the network taken out rather than mocked.

WHY A FAKE TRANSPORT AND NOT A MOCKED HTTP CLIENT
-------------------------------------------------
A transport in this gateway is a callable that returns
`(status, headers, body)`. That is the entire contract, so a test can hand the
loop a function returning a scripted tuple and exercise the real ordering, the
real recording and the real refusal -- no socket, no litellm, no patching of
someone else's internals. Every case below is a known input with a known right
answer.

litellm is NOT installed where these run, and PyPI is unreachable there. That
is a requirement rather than an inconvenience: a gateway whose fallback logic
can only be checked with a large optional dependency present is a gateway whose
fallback logic does not get checked. The two tests that touch litellm assert the
REFUSAL, and one builds a router against a stand-in module to check what would
be handed to the real one.

WHAT THESE TESTS DO NOT CLAIM
-----------------------------
That a request to any provider succeeds. No call has been made to groq,
openrouter, mistral, siliconflow or tokenrouter from here. The two
`urllib_transport` tests substitute `urlopen`, so they check that a 429's
headers survive the trip into the ledger -- not that the endpoint exists.
"""

from __future__ import annotations

import email.message
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib import error, request

import pytest

import gateway
from gateway import (
    FAILED, OK, RATE_LIMITED, REDACTED, SKIPPED, ConfigUnavailable,
    EveryProviderExhausted, GatewayError, LiteLLMUnavailable,
    alias_for, api_base_env_var, build_router, complete, default_ledger_path,
    endpoint_for, load_config, model_env_var, model_id_for, plan_router,
    provider_for_deployment, redact_secrets, response_text, try_load_config,
    urllib_transport,
)
from quota import PROVIDERS, PROVIDERS_BY_NAME, EXHAUSTED, Ledger

GROQ = PROVIDERS_BY_NAME["groq"]
OPENROUTER = PROVIDERS_BY_NAME["openrouter"]

#: A fixed clock, so a failure message never depends on when it ran.
NOW = 1000.0

#: Distinct per provider so a leak can be traced to the provider that leaked
#: it. Long enough to be redactable -- see MIN_REDACTABLE_SECRET.
def key_for(name: str) -> str:
    return f"sk-sentinel-not-a-real-key-{name}"


KEYS = {p.key_env_var: key_for(p.name) for p in PROVIDERS}

#: `.invalid` is reserved by RFC 2606 and cannot resolve, so a test that
#: somehow reached the network would fail rather than send anything anywhere.
BASES = {api_base_env_var(p): f"https://{p.name}.invalid/v1" for p in PROVIDERS}

ENVIRON: Dict[str, str] = {**KEYS, **BASES}


def answered(content: str = "hexokinase", **headers: str) -> Tuple[int, Dict[str, str], Any]:
    return (200, dict(headers), {"choices": [{"message": {
        "role": "assistant", "content": content,
    }}]})


def refused(status: int = 429, **headers: str) -> Tuple[int, Dict[str, str], Any]:
    return (status, dict(headers), {"error": {"message": "rate limit reached"}})


class FakeTransport:
    """Scripted answers, and a record of who was asked in what order.

    `calls` is the assertion surface for most tests here: whether the loop
    asked a provider AT ALL is the difference between skipping an exhausted one
    and spending a round trip discovering it is exhausted again.

    Never asserts internally. `complete()` catches everything a transport
    raises and turns it into a recorded failure, so an assertion in here would
    be swallowed and the test would report the wrong thing. Observations are
    collected and checked by the caller.
    """

    def __init__(
        self,
        responses: Mapping[str, Any],
        *,
        watch: Optional[Any] = None,
    ) -> None:
        self.responses: Dict[str, List[Any]] = {
            name: list(value) if isinstance(value, list) else [value]
            for name, value in responses.items()
        }
        self.calls: List[str] = []
        self.unscripted: List[str] = []
        self.timeouts: List[float] = []
        self.urls: List[str] = []
        self.payloads: List[Mapping[str, Any]] = []
        self.watch = watch

    def __call__(
        self, *, provider: Any, url: str, api_key: str,
        payload: Mapping[str, Any], timeout: float, **_: Any,
    ) -> Tuple[int, Mapping[str, Any], Any]:
        self.calls.append(provider.name)
        self.urls.append(url)
        self.timeouts.append(timeout)
        self.payloads.append(dict(payload))
        if self.watch is not None:
            self.watch(provider.name)

        queue = self.responses.get(provider.name)
        if not queue:
            self.unscripted.append(provider.name)
            return (500, {}, {})
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, BaseException):
            raise item
        return item


def ledger(*names: str, path: Optional[Path] = None, environ: Optional[Mapping[str, str]] = None) -> Ledger:
    """A ledger over a NAMED subset of providers, so the order is exact.

    With all five configured and nothing measured, four sit in UNKNOWN and the
    tie is broken alphabetically -- a correct order, and a fragile thing to
    write a two-hop assertion against. Two named providers make "the first one"
    and "the second one" mean something.
    """
    chosen = tuple(PROVIDERS_BY_NAME[name] for name in (names or ("groq", "openrouter")))
    return Ledger(
        path=path,
        providers=chosen,
        environ=dict(ENVIRON if environ is None else environ),
    )


MESSAGES = [{"role": "user", "content": "michaelis menten kinetics for hexokinase"}]


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


class TestAKeyNeverReachesTheText:
    """The one failure here that cannot be walked back.

    A wrong order costs a round trip. A leaked key is five accounts on one
    address -- admin.terrium@gmail.com holds all of them -- so rotating one
    means rotating the waterfall.
    """

    def test_a_key_value_is_substituted_out(self) -> None:
        secret = key_for("groq")
        text = f"POST https://x.invalid/v1?api_key={secret} failed"
        assert secret not in redact_secrets(text, [secret])
        assert REDACTED in redact_secrets(text, [secret])

    def test_the_longest_secret_goes_first(self) -> None:
        # A short key that is a prefix of a longer one must not leave the rest
        # of the longer one behind.
        short, long = "abcdefgh", "abcdefghijklmnop"
        cleaned = redact_secrets(f"key={long}", [short, long])
        assert "ijklmnop" not in cleaned
        assert cleaned == f"key={REDACTED}"

    def test_a_value_too_short_to_be_distinctive_is_left_alone(self) -> None:
        """Stated, not hidden. Replacing every occurrence of a 3-character
        string would mangle ordinary prose, and a key that short is not a key.
        """
        assert redact_secrets("the cat sat", ["cat"]) == "the cat sat"

    def test_blank_and_whitespace_secrets_are_ignored(self) -> None:
        # An unset key is the empty string, and redacting "" would replace
        # every character boundary in the message.
        assert redact_secrets("hello", ["", "   ", None]) == "hello"

    def test_no_exception_this_module_raises_carries_a_key(self) -> None:
        """The sweep. Every refusal path, one sentinel, one assertion.

        Not a formality: providers put keys in URLs, and urllib error text can
        carry the request it failed on.
        """
        secret = key_for("groq")
        raised: List[BaseException] = []

        # 1. litellm absent.
        with pytest.raises(LiteLLMUnavailable) as one:
            build_router(environ=dict(ENVIRON), now=NOW)
        raised.append(one.value)

        # 2. every provider out of quota.
        book = ledger()
        transport = FakeTransport({
            "groq": refused(429, **{"retry-after": "600"}),
            "openrouter": refused(429, **{"retry-after": "600"}),
        })
        with pytest.raises(EveryProviderExhausted) as two:
            complete(MESSAGES, ledger=book, transport=transport,
                     environ=dict(ENVIRON), now=NOW)
        raised.append(two.value)

        # 3. no endpoint declared anywhere.
        with pytest.raises(EveryProviderExhausted) as three:
            complete(MESSAGES, ledger=ledger(environ=KEYS), transport=transport,
                     environ=dict(KEYS), now=NOW)
        raised.append(three.value)

        # 4. a transport whose OWN message contains the key.
        leaky = FakeTransport({
            "groq": RuntimeError(f"POST https://groq.invalid/v1?key={secret}"),
            "openrouter": RuntimeError(f"connect failed, Authorization: Bearer {secret}"),
        })
        with pytest.raises(EveryProviderExhausted) as four:
            complete(MESSAGES, ledger=ledger(), transport=leaky,
                     environ=dict(ENVIRON), now=NOW)
        raised.append(four.value)

        # 5. a config that is not there.
        with pytest.raises(ConfigUnavailable) as five:
            load_config("/nonexistent/config.yaml")
        raised.append(five.value)

        # 6. messages that are not messages.
        with pytest.raises(GatewayError) as six:
            complete([], ledger=ledger(), environ=dict(ENVIRON), now=NOW)
        raised.append(six.value)

        for exception in raised:
            text = str(exception)
            for value in KEYS.values():
                assert value not in text, (
                    f"{type(exception).__name__} carries a key value: {text}"
                )

    def test_a_transport_exception_is_redacted_in_the_attempt_record(self) -> None:
        secret = key_for("groq")
        transport = FakeTransport({
            "groq": RuntimeError(f"URLError for https://groq.invalid/v1?key={secret}"),
            "openrouter": answered(),
        })
        result = complete(MESSAGES, ledger=ledger(), transport=transport,
                          environ=dict(ENVIRON), now=NOW)

        detail = result.attempts[0].detail
        assert secret not in detail
        assert REDACTED in detail
        assert "RuntimeError" in detail
        assert secret not in result.describe()

    def test_the_completion_repr_carries_no_key(self) -> None:
        # The Authorization header is built inside the transport and is not
        # carried back out, so there is nothing for a repr to leak.
        transport = FakeTransport({"groq": answered()})
        result = complete(MESSAGES, ledger=ledger(), transport=transport,
                          environ=dict(ENVIRON), now=NOW)
        for value in KEYS.values():
            assert value not in repr(result)


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


class TestTheWaterfallMovesOnAndRecordsWhyItMoved:
    def test_a_429_from_the_first_provider_moves_to_the_second(self) -> None:
        book = ledger()
        transport = FakeTransport({
            "groq": refused(429, **{"retry-after": "45"}),
            "openrouter": answered("hexokinase, glucose, human"),
        })

        result = complete(MESSAGES, ledger=book, transport=transport,
                          environ=dict(ENVIRON), now=NOW)

        assert transport.calls == ["groq", "openrouter"]
        assert transport.unscripted == []
        assert result.provider == "openrouter"
        assert result.text == "hexokinase, glucose, human"
        assert result.status == 200

    def test_the_reset_in_the_429_headers_is_what_blocks_the_provider(self) -> None:
        """The point of recording from headers rather than counting locally:
        the interval comes from the provider, not from this repository.
        """
        book = ledger()
        transport = FakeTransport({
            "groq": refused(429, **{
                "x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "1m30s",
            }),
            "openrouter": answered(),
        })

        complete(MESSAGES, ledger=book, transport=transport,
                 environ=dict(ENVIRON), now=NOW)

        state = book.states["groq"]
        assert state.rate_limits == 1
        assert state.last_reading is not None
        assert state.last_reading.reset_requests_in == 90.0
        assert state.blocked_until == NOW + 90.0
        assert book.standing(GROQ, now=NOW).availability == EXHAUSTED

    def test_the_attempt_record_says_when_the_provider_comes_back(self) -> None:
        book = ledger()
        transport = FakeTransport({
            "groq": refused(429, **{"retry-after": "45"}),
            "openrouter": answered(),
        })
        result = complete(MESSAGES, ledger=book, transport=transport,
                          environ=dict(ENVIRON), now=NOW)

        first, second = result.attempts
        assert (first.provider, first.outcome, first.status) == ("groq", RATE_LIMITED, 429)
        assert "45s" in first.detail
        assert (second.provider, second.outcome) == ("openrouter", OK)

    def test_the_ledger_is_recorded_before_the_next_hop_is_chosen(self) -> None:
        """The whole mechanism, asserted directly.

        At the moment the loop asks the SECOND provider, the first provider's
        429 must already be in the ledger. If it were recorded afterwards, the
        hop would have been chosen from state that had not heard about the
        rate limit -- and the provider that just said no could be asked again.
        """
        book = ledger()
        observed: List[Any] = []

        def watch(name: str) -> None:
            if name == "openrouter":
                observed.append((
                    book.states["groq"].rate_limits,
                    book.states["groq"].blocked_until,
                    book.standing(GROQ, now=NOW).availability,
                ))

        transport = FakeTransport({
            "groq": refused(429, **{"retry-after": "600"}),
            "openrouter": answered(),
        }, watch=watch)
        complete(MESSAGES, ledger=book, transport=transport,
                 environ=dict(ENVIRON), now=NOW)

        assert observed == [(1, NOW + 600.0, EXHAUSTED)]

    def test_a_provider_reporting_zero_remaining_is_skipped_on_the_next_call(self) -> None:
        """Skipped WITHOUT being tried. It answered this call and said it has
        nothing left; asking it again would spend a round trip to be told what
        it already told us.
        """
        book = ledger()
        transport = FakeTransport({
            "groq": answered(**{
                "x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "3600s",
            }),
            "openrouter": answered("second call"),
        })

        first = complete(MESSAGES, ledger=book, transport=transport,
                         environ=dict(ENVIRON), now=NOW)
        assert first.provider == "groq"
        assert transport.calls == ["groq"]

        second = complete(MESSAGES, ledger=book, transport=transport,
                          environ=dict(ENVIRON), now=NOW)
        assert second.provider == "openrouter"
        assert transport.calls == ["groq", "openrouter"], (
            "groq was asked again after reporting zero remaining"
        )

    def test_a_transport_that_raises_is_a_failure_and_the_loop_continues(self) -> None:
        book = ledger()
        transport = FakeTransport({
            "groq": TimeoutError("timed out"),
            "openrouter": answered(),
        })

        result = complete(MESSAGES, ledger=book, transport=transport,
                          environ=dict(ENVIRON), now=NOW)

        assert result.provider == "openrouter"
        assert result.attempts[0].outcome == FAILED
        assert book.states["groq"].failures == 1
        assert book.states["groq"].consecutive_failures == 1
        # A connection that never landed said nothing about quota, so it is
        # not a rate limit and does not block the provider.
        assert book.states["groq"].rate_limits == 0
        assert book.states["groq"].blocked_until is None

    def test_a_200_carrying_no_content_is_a_failure_not_an_answer(self) -> None:
        """Returning "" would surface later as a JSON parse error in the
        caller, with nothing pointing at the provider that sent nothing.
        """
        book = ledger()
        transport = FakeTransport({
            "groq": (200, {}, {"choices": [{"message": {"content": "  "}}]}),
            "openrouter": answered(),
        })

        result = complete(MESSAGES, ledger=book, transport=transport,
                          environ=dict(ENVIRON), now=NOW)

        assert result.provider == "openrouter"
        assert result.attempts[0].outcome == FAILED
        assert "no message content" in result.attempts[0].detail
        assert book.states["groq"].successes == 0
        assert book.states["groq"].failures == 1

    def test_no_provider_is_asked_twice_in_one_call(self) -> None:
        """A plain 500 does NOT block a provider in the ledger, and should not
        -- one bad response is not a dead provider. So the loop, not the
        ledger, is what stops it being retried forever within one call.
        """
        book = ledger()
        transport = FakeTransport({
            "groq": (500, {}, {}),
            "openrouter": (503, {}, {}),
        })

        with pytest.raises(EveryProviderExhausted):
            complete(MESSAGES, ledger=book, transport=transport,
                     environ=dict(ENVIRON), now=NOW)

        assert transport.calls == ["groq", "openrouter"]

    def test_the_provider_that_answers_first_ends_the_call(self) -> None:
        book = ledger()
        transport = FakeTransport({"groq": answered(), "openrouter": answered()})
        complete(MESSAGES, ledger=book, transport=transport,
                 environ=dict(ENVIRON), now=NOW)
        assert transport.calls == ["groq"]

    def test_measured_headroom_decides_which_provider_is_asked_first(self) -> None:
        # The ordering is quota.py's; this checks that the loop uses it rather
        # than the order the providers happen to be listed in.
        book = ledger()
        book.record("openrouter", headers={"x-ratelimit-remaining": "900"},
                    status=200, now=NOW)
        transport = FakeTransport({"groq": answered(), "openrouter": answered()})

        complete(MESSAGES, ledger=book, transport=transport,
                 environ=dict(ENVIRON), now=NOW)

        assert transport.calls == ["openrouter"]

    def test_messages_must_be_messages(self) -> None:
        for bad in ([], "a string", [{"content": "no role"}], None):
            with pytest.raises(GatewayError):
                complete(bad, ledger=ledger(), transport=FakeTransport({}),
                         environ=dict(ENVIRON), now=NOW)

    def test_no_sampling_parameters_are_invented(self) -> None:
        """A temperature set here would change every caller's results without
        the caller knowing. What the caller sends is what goes.
        """
        transport = FakeTransport({"groq": answered()})
        complete(MESSAGES, ledger=ledger(), transport=transport,
                 environ=dict(ENVIRON), now=NOW)
        sent = transport.payloads[0]
        assert set(sent) == {"model", "messages"}

        complete(MESSAGES, ledger=ledger(), transport=transport,
                 environ=dict(ENVIRON), now=NOW,
                 extra_body={"temperature": 0.0, "response_format": {"type": "json_object"}})
        assert transport.payloads[1]["temperature"] == 0.0


# ---------------------------------------------------------------------------
# The refusal
# ---------------------------------------------------------------------------


class TestTheRefusalSurfacesTheSummary:
    def test_every_provider_exhausted_raises_with_the_ledger_summary(self) -> None:
        book = ledger()
        transport = FakeTransport({
            "groq": refused(429, **{"retry-after": "600"}),
            "openrouter": refused(429, **{"retry-after": "40"}),
        })

        with pytest.raises(EveryProviderExhausted) as caught:
            complete(MESSAGES, ledger=book, transport=transport,
                     environ=dict(ENVIRON), now=NOW)

        message = str(caught.value)
        assert book.summary(now=NOW) in message
        assert "provider(s), best first" in message
        assert caught.value.summary
        assert [a.outcome for a in caught.value.attempts] == [RATE_LIMITED, RATE_LIMITED]

    def test_the_refusal_names_the_provider_that_comes_back_first(self) -> None:
        """Which one, and in how many seconds, so an operator knows whether to
        wait or to go and add a key.
        """
        book = ledger()
        transport = FakeTransport({
            "groq": refused(429, **{"retry-after": "600"}),
            "openrouter": refused(429, **{"retry-after": "40"}),
        })
        with pytest.raises(EveryProviderExhausted) as caught:
            complete(MESSAGES, ledger=book, transport=transport,
                     environ=dict(ENVIRON), now=NOW)

        message = str(caught.value)
        assert "Soonest back: openrouter" in message
        assert "40s" in message

    def test_a_missing_endpoint_is_reported_not_guessed(self) -> None:
        """A base URL written from memory is a host a prompt and a key get
        sent to on somebody's recollection. So it is not written.
        """
        transport = FakeTransport({"groq": answered(), "openrouter": answered()})
        with pytest.raises(EveryProviderExhausted) as caught:
            complete(MESSAGES, ledger=ledger(environ=KEYS), transport=transport,
                     environ=dict(KEYS), now=NOW)

        message = str(caught.value)
        assert transport.calls == [], "a call was made with no declared endpoint"
        assert "GROQ_API_BASE" in message
        assert "OPENROUTER_API_BASE" in message
        assert "no provider in the waterfall has a declared endpoint" in message

    def test_the_refusal_offers_litellm_as_the_third_way(self) -> None:
        # litellm carries its own table of provider base URLs. Installing it is
        # a real remedy for the missing-endpoint case, so the refusal says so.
        with pytest.raises(EveryProviderExhausted) as caught:
            complete(MESSAGES, ledger=ledger(environ=KEYS),
                     transport=FakeTransport({}), environ=dict(KEYS), now=NOW)
        assert "pip install 'litellm[proxy]'" in str(caught.value)

    def test_a_skipped_provider_is_not_recorded_against_its_quota(self) -> None:
        # Nothing was asked, so nothing was learned. Writing a failure here
        # would block a provider for a reason that has nothing to do with it.
        book = ledger(environ=KEYS)
        with pytest.raises(EveryProviderExhausted) as caught:
            complete(MESSAGES, ledger=book, transport=FakeTransport({}),
                     environ=dict(KEYS), now=NOW)

        assert [a.outcome for a in caught.value.attempts] == [SKIPPED, SKIPPED]
        assert book.states["groq"].calls == 0
        assert book.states["groq"].failures == 0


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestTheLedgerIsPersistedEachCall:
    def test_the_ledger_file_is_written_before_the_next_hop(self, tmp_path: Path) -> None:
        """Not merely "saved at the end". A process that dies between hops must
        leave the 429 it already knows about on disk, or the next start asks
        the provider that just refused.
        """
        path = tmp_path / "ledger.json"
        book = ledger(path=path)
        seen: List[Any] = []

        def watch(name: str) -> None:
            if name == "openrouter":
                blob = json.loads(path.read_text(encoding="utf-8"))
                states = {entry["provider"]: entry for entry in blob["providers"]}
                seen.append((states["groq"]["rate_limits"], states["groq"]["blocked_until"]))

        transport = FakeTransport({
            "groq": refused(429, **{"retry-after": "600"}),
            "openrouter": answered(),
        }, watch=watch)
        complete(MESSAGES, ledger=book, transport=transport,
                 environ=dict(ENVIRON), now=NOW)

        assert seen == [(1, NOW + 600.0)], "the 429 was not on disk before the next hop"

    def test_both_hops_are_on_disk_when_the_call_returns(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        book = ledger(path=path)
        transport = FakeTransport({
            "groq": refused(429, **{"retry-after": "600"}),
            "openrouter": answered(),
        })
        complete(MESSAGES, ledger=book, transport=transport,
                 environ=dict(ENVIRON), now=NOW)

        blob = json.loads(path.read_text(encoding="utf-8"))
        states = {entry["provider"]: entry for entry in blob["providers"]}
        assert states["groq"]["rate_limits"] == 1
        assert states["openrouter"]["successes"] == 1

    def test_the_persisted_file_holds_no_key(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        transport = FakeTransport({"groq": answered()})
        complete(MESSAGES, ledger=ledger(path=path), transport=transport,
                 environ=dict(ENVIRON), now=NOW)

        text = path.read_text(encoding="utf-8")
        for value in KEYS.values():
            assert value not in text

    def test_a_ledger_that_cannot_be_written_degrades_rather_than_fails(
        self, tmp_path: Path
    ) -> None:
        """An unwritable cache costs one wasted 429 per provider after a
        restart. Failing the call would cost the call.
        """
        blocker = tmp_path / "not-a-directory"
        blocker.write_text("", encoding="utf-8")
        book = ledger(path=blocker / "ledger.json")

        result = complete(MESSAGES, ledger=book, transport=FakeTransport({"groq": answered()}),
                          environ=dict(ENVIRON), now=NOW)

        assert result.provider == "groq"
        assert any("ledger not persisted" in note for note in result.notes)

    def test_the_default_ledger_path_is_outside_the_repository(self) -> None:
        # A runtime file written into a tracked directory eventually gets
        # committed. This one lives in the user cache instead.
        default = default_ledger_path({})
        assert default.name == "llm-quota-ledger.json"
        assert Path(__file__).resolve().parent not in default.parents

    def test_the_ledger_path_can_be_declared(self, tmp_path: Path) -> None:
        declared = tmp_path / "somewhere" / "ledger.json"
        assert default_ledger_path({gateway.LEDGER_PATH_ENV_VAR: str(declared)}) == declared
        assert default_ledger_path({"XDG_CACHE_HOME": str(tmp_path)}) == (
            tmp_path / "terrium" / "llm-quota-ledger.json"
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class TestEndpointsAreDeclaredNotInvented:
    def test_nothing_is_known_without_a_declaration(self) -> None:
        for provider in PROVIDERS:
            assert endpoint_for(provider, config=None, environ={}) is None, provider.name

    def test_this_module_states_no_provider_hostname(self) -> None:
        """The assertion behind the design. If a hostname appears here later,
        somebody wrote from memory a host that keys and prompts get sent to.
        """
        source = Path(gateway.__file__).read_text(encoding="utf-8")
        for hostname in (
            "api.groq.com", "openrouter.ai", "api.mistral.ai",
            "api.siliconflow.com", "api.tokenrouter.io",
        ):
            assert hostname not in source, (
                f"gateway.py names {hostname}. Endpoints are declared in "
                f"<PROVIDER>_API_BASE or in config.yaml, not here."
            )

    def test_the_environment_declares_an_endpoint(self) -> None:
        url = endpoint_for(GROQ, environ={"GROQ_API_BASE": "https://groq.invalid/openai/v1"})
        assert url == "https://groq.invalid/openai/v1/chat/completions"

    def test_a_trailing_slash_does_not_double_the_path(self) -> None:
        assert endpoint_for(GROQ, environ={"GROQ_API_BASE": "https://groq.invalid/v1/"}) == (
            "https://groq.invalid/v1/chat/completions"
        )

    def test_an_operator_who_declared_the_full_endpoint_meant_it(self) -> None:
        declared = "https://groq.invalid/v1/chat/completions"
        assert endpoint_for(GROQ, environ={"GROQ_API_BASE": declared}) == declared

    def test_the_environment_wins_over_the_config(self) -> None:
        config = {"model_list": [{
            "model_name": "terrium-extract",
            "litellm_params": {
                "model": "groq/llama-3.3-70b-versatile",
                "api_key": "os.environ/GROQ_API_KEY",
                "api_base": "https://from-config.invalid/v1",
            },
        }]}
        url = endpoint_for(GROQ, config=config,
                           environ={"GROQ_API_BASE": "https://from-env.invalid/v1"})
        assert url.startswith("https://from-env.invalid/")

    def test_an_api_base_in_the_config_is_used(self) -> None:
        config = {"model_list": [{
            "model_name": "terrium-extract",
            "litellm_params": {
                "model": "openai/Qwen/Qwen2.5-7B-Instruct",
                "api_key": "os.environ/SILICONFLOW_API_KEY",
                "api_base": "https://declared.invalid/v1",
            },
        }]}
        url = endpoint_for(PROVIDERS_BY_NAME["siliconflow"], config=config, environ={})
        assert url == "https://declared.invalid/v1/chat/completions"

    def test_complete_reads_no_file_unless_asked(self) -> None:
        """An implicit config read deciding where a researcher's query gets
        POSTed is not a surprise this module should have. With keys set and no
        endpoint declared, nothing is sent -- even though config.yaml on disk
        declares two api_base values.
        """
        transport = FakeTransport({name: answered() for name in PROVIDERS_BY_NAME})
        with pytest.raises(EveryProviderExhausted):
            complete(MESSAGES, ledger=ledger("siliconflow", environ=KEYS),
                     transport=transport, environ=dict(KEYS), now=NOW)
        assert transport.calls == []

    def test_a_config_endpoint_is_used_when_the_caller_passes_one(self) -> None:
        config = {"model_list": [{
            "model_name": "terrium-extract",
            "litellm_params": {
                "model": "openai/Qwen/Qwen2.5-7B-Instruct",
                "api_key": "os.environ/SILICONFLOW_API_KEY",
                "api_base": "https://declared.invalid/v1",
            },
        }]}
        transport = FakeTransport({"siliconflow": answered()})
        result = complete(MESSAGES, ledger=ledger("siliconflow", environ=KEYS),
                          transport=transport, config=config,
                          environ=dict(KEYS), now=NOW)
        assert result.provider == "siliconflow"
        assert transport.urls == ["https://declared.invalid/v1/chat/completions"]


class TestModelIdsComeFromTheProviderOrTheOperator:
    def test_the_litellm_routing_prefix_is_stripped_for_a_raw_endpoint(self) -> None:
        assert model_id_for(GROQ, environ={}) == "llama-3.3-70b-versatile"
        assert model_id_for(OPENROUTER, environ={}) == (
            "meta-llama/llama-3.3-70b-instruct:free"
        )
        assert model_id_for(PROVIDERS_BY_NAME["siliconflow"], environ={}) == (
            "Qwen/Qwen2.5-7B-Instruct"
        )

    def test_an_operator_can_declare_the_id_instead(self) -> None:
        # Stripping the first segment is right for these five and is not a
        # universal rule, so it is overridable rather than assumed.
        assert model_id_for(GROQ, environ={model_env_var(GROQ): "llama-3.1-8b-instant"}) == (
            "llama-3.1-8b-instant"
        )

    def test_the_call_sends_the_provider_s_own_id(self) -> None:
        transport = FakeTransport({"groq": answered()})
        complete(MESSAGES, ledger=ledger(), transport=transport,
                 environ=dict(ENVIRON), now=NOW)
        assert transport.payloads[0]["model"] == "llama-3.3-70b-versatile"

    def test_a_caller_can_override_per_provider(self) -> None:
        transport = FakeTransport({"groq": answered()})
        complete(MESSAGES, ledger=ledger(), transport=transport,
                 environ=dict(ENVIRON), now=NOW,
                 model_overrides={"groq": "llama-3.1-8b-instant"})
        assert transport.payloads[0]["model"] == "llama-3.1-8b-instant"


# ---------------------------------------------------------------------------
# The stdlib transport
# ---------------------------------------------------------------------------


def _headers(pairs: Mapping[str, str]) -> email.message.Message:
    message = email.message.Message()
    for name, value in pairs.items():
        message[name] = value
    return message


class _FakeResponse:
    def __init__(self, status: int, headers: Mapping[str, str], body: Any) -> None:
        self.status = status
        self.headers = _headers(headers)
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_: Any) -> bool:
        return False


class TestTheStdlibTransport:
    """The no-litellm path, with `urlopen` substituted.

    These do not claim any endpoint exists. They claim the one thing the loop
    depends on: that a 429's headers survive the trip into the ledger.
    """

    def test_a_success_returns_status_headers_and_body(self, monkeypatch) -> None:
        monkeypatch.setattr(request, "urlopen", lambda *a, **k: _FakeResponse(
            200, {"x-ratelimit-remaining-requests": "42"},
            {"choices": [{"message": {"content": "hexokinase"}}]},
        ))
        status, headers, body = urllib_transport(
            provider=GROQ, url="https://groq.invalid/v1/chat/completions",
            api_key=key_for("groq"), payload={"model": "m", "messages": MESSAGES},
            timeout=1.0,
        )
        assert status == 200
        assert headers["x-ratelimit-remaining-requests"] == "42"
        assert response_text(body) == "hexokinase"

    def test_a_429_keeps_its_headers_instead_of_raising(self, monkeypatch) -> None:
        """HTTPError is where `retry-after` and `x-ratelimit-*` live. A
        transport that let it propagate would throw away exactly the numbers
        the ledger runs on, and every 429 would become an unexplained failure.
        """
        raised = error.HTTPError(
            "https://groq.invalid/v1/chat/completions", 429, "Too Many Requests",
            _headers({"retry-after": "45", "x-ratelimit-remaining-requests": "0"}),
            io.BytesIO(b'{"error": {"message": "slow down"}}'),
        )

        def boom(*_: Any, **__: Any) -> Any:
            raise raised

        monkeypatch.setattr(request, "urlopen", boom)
        status, headers, _body = urllib_transport(
            provider=GROQ, url="https://groq.invalid/v1/chat/completions",
            api_key=key_for("groq"), payload={"model": "m", "messages": MESSAGES},
            timeout=1.0,
        )
        assert status == 429
        assert headers["retry-after"] == "45"

        # And the ledger reads it the same way it reads any other 429.
        book = ledger()
        book.record("groq", headers=headers, status=status, now=NOW)
        assert book.states["groq"].blocked_until == NOW + 45.0

    def test_an_unparseable_body_still_yields_the_status_and_headers(self, monkeypatch) -> None:
        raised = error.HTTPError(
            "https://groq.invalid/v1/chat/completions", 503, "Service Unavailable",
            _headers({"retry-after": "5"}), io.BytesIO(b"<html>nginx</html>"),
        )

        def boom(*_: Any, **__: Any) -> Any:
            raise raised

        monkeypatch.setattr(request, "urlopen", boom)
        status, headers, body = urllib_transport(
            provider=GROQ, url="https://groq.invalid/v1/chat/completions",
            api_key="k", payload={"model": "m", "messages": MESSAGES}, timeout=1.0,
        )
        assert (status, body) == (503, {})
        assert headers["retry-after"] == "5"


class TestResponseText:
    def test_the_assistant_message_is_the_answer(self) -> None:
        assert response_text({"choices": [{"message": {"content": "x"}}]}) == "x"

    def test_anything_else_is_not_an_answer(self) -> None:
        for body in (
            None, "a string", {}, {"choices": []}, {"choices": [{}]},
            {"choices": [{"message": {"content": ""}}]},
            {"choices": [{"message": {"content": "   "}}]},
            {"error": {"message": "nope"}},
        ):
            assert response_text(body) is None, body


# ---------------------------------------------------------------------------
# litellm: absent here, so the refusal is what gets tested
# ---------------------------------------------------------------------------


class _FakeRouter:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _FakeLitellm:
    Router = _FakeRouter


class TestLitellmIsOptional:
    def test_importing_the_gateway_does_not_import_litellm(self) -> None:
        assert "gateway" in sys.modules
        assert "litellm" not in sys.modules, (
            "litellm was imported at module scope, which makes the gateway "
            "untestable without a large optional dependency"
        )

    def test_build_router_refuses_with_the_install_command(self) -> None:
        with pytest.raises(LiteLLMUnavailable) as caught:
            build_router(environ=dict(ENVIRON), now=NOW)
        message = str(caught.value)
        assert "pip install 'litellm[proxy]'" in message
        assert "litellm" in message

    def test_the_direct_path_needs_no_litellm_at_all(self) -> None:
        result = complete(MESSAGES, ledger=ledger(),
                          transport=FakeTransport({"groq": answered()}),
                          environ=dict(ENVIRON), now=NOW)
        assert result.text == "hexokinase"
        assert "litellm" not in sys.modules

    def test_the_litellm_transport_refuses_rather_than_raising_importerror(self) -> None:
        with pytest.raises(LiteLLMUnavailable):
            gateway.litellm_transport(
                provider=GROQ, url=None, api_key="k",
                payload={"model": "m", "messages": MESSAGES}, timeout=1.0,
            )


# ---------------------------------------------------------------------------
# The router plan
# ---------------------------------------------------------------------------


def fake_config(*names: str, **settings: Any) -> Dict[str, Any]:
    chosen = names or tuple(p.name for p in PROVIDERS)
    return {
        "model_list": [
            {
                "model_name": "terrium-extract",
                "litellm_params": {
                    "model": PROVIDERS_BY_NAME[name].model,
                    "api_key": f"os.environ/{PROVIDERS_BY_NAME[name].key_env_var}",
                },
                "model_info": {"id": f"{name}-deployment"},
            }
            for name in chosen
        ],
        "litellm_settings": {"num_retries": 2, "request_timeout": 30, **settings},
        "router_settings": {"routing_strategy": "simple-shuffle"},
    }


class TestTheRouterPlanFollowsTheMeasuredOrder:
    def test_the_head_of_the_chain_keeps_the_name_the_application_asks_for(self) -> None:
        book = ledger("groq", "openrouter")
        book.record("openrouter", headers={"x-ratelimit-remaining": "900"},
                    status=200, now=NOW)

        plan = plan_router(fake_config("groq", "openrouter"), ledger=book,
                           environ=dict(ENVIRON), now=NOW)

        assert plan.chain == ("openrouter", "groq")
        assert plan.model_list[0]["model_name"] == "terrium-extract"
        assert plan.model_list[0]["litellm_params"]["model"] == OPENROUTER.model

    def test_every_other_provider_gets_its_own_name_so_nothing_is_shuffled(self) -> None:
        """config.yaml sets `simple-shuffle`, which is right for the proxy and
        would shuffle away any order put in model_list. One deployment per
        model_name leaves nothing to shuffle, so the measured order holds.
        """
        plan = plan_router(fake_config("groq", "openrouter"), ledger=ledger(),
                           environ=dict(ENVIRON), now=NOW)

        names = [entry["model_name"] for entry in plan.model_list]
        assert names == ["terrium-extract", alias_for("terrium-extract", "openrouter")]
        assert len(set(names)) == len(names)

    def test_the_fallback_chain_is_the_measured_order(self) -> None:
        book = ledger("groq", "openrouter", "mistral")
        book.record("mistral", headers={}, status=200, now=NOW)  # still UNKNOWN
        book.record("groq", headers={"x-ratelimit-remaining-requests": "5"},
                    status=200, now=NOW)

        plan = plan_router(fake_config("groq", "openrouter", "mistral"), ledger=book,
                           environ=dict(ENVIRON), now=NOW)

        # groq measured AVAILABLE leads; the two UNKNOWN ones follow in the
        # order quota.py puts them, and the fallbacks list says so explicitly.
        assert plan.chain[0] == "groq"
        assert plan.fallbacks == ({"terrium-extract": [
            alias_for("terrium-extract", plan.chain[1]),
            alias_for("terrium-extract", plan.chain[2]),
        ]},)

    def test_an_exhausted_provider_is_dropped_and_the_reason_kept(self) -> None:
        """litellm would try it, and a call already known to 429 costs a round
        trip and a retry budget. Dropped, not hidden: the reason is reported.
        """
        book = ledger("groq", "openrouter")
        book.record("groq", headers={"retry-after": "600"}, status=429, now=NOW)

        plan = plan_router(fake_config("groq", "openrouter"), ledger=book,
                           environ=dict(ENVIRON), now=NOW)

        assert "groq" not in plan.chain
        assert len(plan.model_list) == 1
        assert any("groq" in reason for reason in plan.dropped)
        assert plan.fallbacks == ()

    def test_a_provider_with_no_key_is_dropped_with_its_variable_named(self) -> None:
        environ = {**ENVIRON, "GROQ_API_KEY": ""}
        plan = plan_router(fake_config("groq", "openrouter"),
                           ledger=ledger("groq", "openrouter", environ=environ),
                           environ=environ, now=NOW)
        assert "groq" not in plan.chain
        assert any("GROQ_API_KEY" in reason for reason in plan.dropped)

    def test_an_unmeasured_deployment_is_kept_last_rather_than_deleted(self) -> None:
        # An operator's deployment is not this function's to delete, and a
        # provider quota.py does not know cannot be ordered by headroom.
        config = fake_config("groq")
        config["model_list"].append({
            "model_name": "terrium-extract",
            "litellm_params": {"model": "openai/gpt-4o-mini", "api_key": "os.environ/SOMETHING_ELSE"},
        })

        plan = plan_router(config, ledger=ledger(), environ=dict(ENVIRON), now=NOW)

        assert plan.model_list[-1]["model_name"] == "terrium-extract-unmeasured-1"
        assert any("matches no provider" in note for note in plan.notes)

    def test_a_retry_policy_that_is_not_applied_says_so(self) -> None:
        config = fake_config("groq", retry_policy={"RateLimitErrorRetries": 0})
        plan = plan_router(config, ledger=ledger(), environ=dict(ENVIRON), now=NOW)
        assert any("retry_policy is NOT applied" in note for note in plan.notes)
        assert "retry_policy" not in plan.router_kwargs

    def test_router_settings_come_from_the_config_not_from_this_module(self) -> None:
        plan = plan_router(fake_config("groq"), ledger=ledger(),
                           environ=dict(ENVIRON), now=NOW)
        assert plan.router_kwargs["num_retries"] == 2
        assert plan.router_kwargs["timeout"] == 30
        assert plan.router_kwargs["routing_strategy"] == "simple-shuffle"

    def test_no_provider_left_refuses_with_the_summary(self) -> None:
        with pytest.raises(EveryProviderExhausted) as caught:
            plan_router(fake_config("groq", "openrouter"),
                        ledger=Ledger(environ={}), environ={}, now=NOW)
        assert "provider(s), best first" in str(caught.value)

    def test_an_empty_model_list_is_refused(self) -> None:
        with pytest.raises(ConfigUnavailable, match="empty model_list"):
            plan_router({"model_list": []}, ledger=ledger(), environ=dict(ENVIRON), now=NOW)

    def test_build_router_hands_the_plan_to_litellm(self) -> None:
        # The only way to check what would reach the real Router, given it
        # cannot be installed here.
        book = ledger("groq", "openrouter")
        book.record("openrouter", headers={"x-ratelimit-remaining": "900"},
                    status=200, now=NOW)

        router = build_router(config=fake_config("groq", "openrouter"), ledger=book,
                              environ=dict(ENVIRON), now=NOW,
                              litellm_module=_FakeLitellm())

        assert [d["model_name"] for d in router.kwargs["model_list"]] == [
            "terrium-extract", alias_for("terrium-extract", "groq"),
        ]
        assert router.kwargs["fallbacks"] == [
            {"terrium-extract": [alias_for("terrium-extract", "groq")]}
        ]
        assert router.kwargs["num_retries"] == 2
        assert router.terrium_plan.chain == ("openrouter", "groq")


class TestDeploymentMatching:
    def test_a_deployment_is_matched_on_its_key_variable(self) -> None:
        """The unambiguous signal: each provider owns exactly one variable
        name. Two deployments can share an `openai/...` model and be different
        hosts, so the model id is only the fallback.
        """
        assert provider_for_deployment({"litellm_params": {
            "api_key": "os.environ/TOKENROUTER_API_KEY", "model": "openai/auto",
        }}) == "tokenrouter"

    def test_a_deployment_is_matched_on_its_model_when_there_is_no_key_reference(self) -> None:
        assert provider_for_deployment({"litellm_params": {
            "model": "groq/llama-3.3-70b-versatile",
        }}) == "groq"

    def test_an_unknown_deployment_matches_nothing(self) -> None:
        assert provider_for_deployment({"litellm_params": {
            "model": "openai/gpt-4o-mini", "api_key": "os.environ/OPENAI_API_KEY",
        }}) is None
        assert provider_for_deployment({"model_name": "x"}) is None


# ---------------------------------------------------------------------------
# config.yaml, as it actually is
# ---------------------------------------------------------------------------


class TestAgainstTheRealConfig:
    """Reads the config.yaml in this directory, so the plan is checked against
    the file the proxy is actually started with rather than a fixture.
    """

    def config(self) -> Dict[str, Any]:
        pytest.importorskip("yaml", reason="PyYAML is in requirements-dev.txt")
        return load_config()

    def test_the_gateway_reads_the_config_beside_it(self) -> None:
        assert gateway.DEFAULT_CONFIG_PATH == Path(__file__).resolve().with_name("config.yaml")

    def test_every_deployment_in_it_maps_to_a_known_provider(self) -> None:
        config = self.config()
        matched = [provider_for_deployment(d) for d in gateway.deployments(config)]
        assert matched == ["groq", "openrouter", "mistral", "siliconflow", "tokenrouter"]

    def test_the_two_providers_it_declares_an_api_base_for_are_usable_directly(self) -> None:
        # The other three need <PROVIDER>_API_BASE, because this repository
        # does not write a hostname it did not read from a declaration.
        config = self.config()
        declared = {
            p.name for p in PROVIDERS
            if endpoint_for(p, config=config, environ={}) is not None
        }
        assert declared == {"siliconflow", "tokenrouter"}

    def test_the_plan_over_the_real_config_uses_the_name_the_app_asks_for(self) -> None:
        plan = plan_router(self.config(), ledger=Ledger(environ=dict(ENVIRON)),
                           environ=dict(ENVIRON), now=NOW)
        assert plan.primary_model_name == "terrium-extract"
        assert len(plan.model_list) == len(PROVIDERS)
        assert plan.notes == () or all("retry_policy" in n or "matches no" in n for n in plan.notes)

    def test_the_timeout_comes_from_the_config_not_from_this_module(self) -> None:
        config = self.config()
        transport = FakeTransport({"siliconflow": answered()})
        complete(MESSAGES, ledger=ledger("siliconflow", environ=KEYS),
                 transport=transport, config=config, environ=dict(KEYS), now=NOW)
        assert transport.timeouts == [float(config["litellm_settings"]["request_timeout"])]

    def test_a_missing_config_is_reported_with_its_path(self) -> None:
        with pytest.raises(ConfigUnavailable, match="nonexistent"):
            load_config("/nonexistent/config.yaml")

    def test_try_load_config_returns_a_note_instead_of_raising(self) -> None:
        config, note = try_load_config("/nonexistent/config.yaml")
        assert config is None
        assert "nonexistent" in note

    def test_the_config_is_parsed_safely(self) -> None:
        # A loader that can construct arbitrary Python objects from YAML is not
        # something to point at a path a caller supplies.
        source = Path(gateway.__file__).read_text(encoding="utf-8")
        assert "yaml.safe_load" in source
        assert "yaml.load(" not in source


# ---------------------------------------------------------------------------
# ADR 0011
# ---------------------------------------------------------------------------


class TestTheGatewaySuppliesNoParameterValues:
    """ADR 0011 hard-blocks a parameter whose origin is a language model.

    The gateway is for entity extraction and domain classification. A Km that
    came out of a prompt is not a measurement, and this module must not become
    the route around that. These check what can be checked: that the module
    does not ANNOUNCE itself as a parameter source and offers no helper for
    turning model output into one.
    """

    def test_the_module_mints_no_parameter_origin(self) -> None:
        source = Path(gateway.__file__).read_text(encoding="utf-8")
        for forbidden in ('origin="llm"', "origin='llm'", '"origin": "llm"'):
            assert forbidden not in source

    def test_the_module_offers_no_number_extraction_helper(self) -> None:
        for name in gateway.__all__:
            lowered = name.lower()
            assert "parameter" not in lowered, name
            assert "origin" not in lowered, name
            assert "km" != lowered, name

    def test_the_module_says_what_it_is_for_and_cites_the_adr(self) -> None:
        doc = gateway.__doc__ or ""
        assert "ADR 0011" in doc
        assert "entity extraction" in doc.lower()

    def test_the_completion_is_text_and_nothing_more_structured(self) -> None:
        result = complete(MESSAGES, ledger=ledger(),
                          transport=FakeTransport({"groq": answered("2.4 mM")}),
                          environ=dict(ENVIRON), now=NOW)
        assert isinstance(result.text, str)
        # The raw body is passed through untouched; nothing here interprets a
        # number out of it.
        assert result.text == "2.4 mM"
