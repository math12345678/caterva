"""Which provider to ask next, decided from what the providers actually said.

THE PROBLEM
-----------
Caterva has keys for several LLM providers, each with a free tier. Any one of
them runs out -- a daily request cap, a per-minute token ceiling -- and the
entity extraction that depends on it stops working. Chained together they
should not: when one is exhausted the next takes over, and with enough of them
the gateway stays up.

That is the whole idea and it is a good one. What makes it work or not is how
"exhausted" is decided.

WHY THIS DOES NOT HARDCODE RATE LIMITS
---------------------------------------
The obvious implementation writes each provider's free-tier limits into a
table -- 14,400 requests a day here, 20 a minute there -- and counts down
locally. Every version of that table is wrong within a month, because free
tiers change without notice, and it is wrong in the worst direction: the
gateway believes it has headroom it does not, sends the request, and fails.

Worse for this repository specifically, a hardcoded limit is a number nobody
measured, written into a project whose entire claim is that it does not do
that. A table of rate limits I asserted from memory would be the same defect
as a fabricated Km, in a different file.

So nothing here is hardcoded. Both providers whose documentation was actually
read for this module report their own remaining quota, and the ledger reads
what they report:

    Groq      x-ratelimit-remaining-requests   (requests left, per the docs
              x-ratelimit-remaining-tokens      the day's budget)
              x-ratelimit-reset-requests
              x-ratelimit-reset-tokens
              retry-after                       (on 429 only)

    OpenRouter  X-RateLimit-Remaining          (on error responses)
                X-RateLimit-Reset
                GET /api/v1/key -> limit_remaining, usage_daily

A provider that reports nothing is not assumed to be fine. It is recorded as
UNKNOWN, which is a third state and is the one this module is most careful
about -- see `Availability`.

WHY NOT ORDER BY PRICE
----------------------
The usual advice is "cheapest first". For a waterfall over free tiers that
ordering is meaningless: every tier costs zero, so a price-ordered list is an
arbitrary list wearing a justification.

What actually decides how long the gateway survives is HEADROOM. Sending the
next request to the provider with the most measured remaining quota drains all
of them evenly and postpones the first exhaustion as far as it will go. So
free providers are ordered by measured headroom, and paid providers -- which
do have meaningfully different prices -- come after them, ordered by a cost
the operator declares in configuration rather than one this file invents.

WHAT THIS MODULE IS NOT
-----------------------
It is not the transport. It decides an order and records what came back;
`litellm` makes the calls. That split is deliberate: the ordering logic is
pure Python with no network and no optional dependency, so it can be tested
exactly, and a bug in it is a bug in a function rather than in a stack.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import (
    Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple,
)

# ---------------------------------------------------------------------------
# Availability: three states, because two would lie
# ---------------------------------------------------------------------------

#: The provider reported quota remaining, and there is some.
AVAILABLE = "available"

#: The provider reported quota remaining, and it is gone. Stays here until
#: the reset time it also reported.
EXHAUSTED = "exhausted"

#: The provider reported nothing this module knows how to read.
#:
#: THE STATE THAT MATTERS. Not all providers send rate-limit headers, and a
#: provider that says nothing has not said it is fine. Folding UNKNOWN into
#: AVAILABLE would make the gateway confident about the providers it knows
#: least about; folding it into EXHAUSTED would drop working providers for
#: not being chatty. It is ordered after everything measured-available and
#: before everything measured-exhausted, and the status output says which
#: providers are in it.
UNKNOWN = "unknown"

#: The key is not set at all. Distinct from UNKNOWN: nothing was asked.
ABSENT = "absent"

AVAILABILITIES = (AVAILABLE, UNKNOWN, EXHAUSTED, ABSENT)

#: Consecutive hard failures before a provider is rested even though its
#: quota headers look fine.
#:
#: A STATED JUDGEMENT. A provider can be up, in quota, and still failing --
#: a bad gateway, a model retired out from under the config, an auth error
#: after a key rotation. Three strikes is enough to stop hammering it and
#: few enough that one flaky response does not cost a provider its place.
CONSECUTIVE_FAILURES_BEFORE_REST = 3

#: How long a provider rests after tripping that. Not read from any header,
#: because the failure was not a quota failure -- so this one IS a choice,
#: and it is named so it can be argued with.
FAILURE_REST_SECONDS = 120.0

#: A provider whose reported reset time has passed is re-tried. Clocks drift
#: and providers round, so a little slack avoids one wasted 429 per cycle.
RESET_SLACK_SECONDS = 2.0


class QuotaError(RuntimeError):
    """The ledger could not do what was asked, as distinct from a provider
    being out of quota."""


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Provider:
    """One upstream, and how to read what it says about its own limits.

    `cost_per_million_tokens` is declared by the OPERATOR in configuration,
    not by this file. A price written here would be a number nobody in this
    repository measured, and it would go stale silently. `None` means free
    or unpriced, which is the case for every tier Caterva currently uses.
    """

    name: str
    #: Environment variable holding the key. The key itself is never stored
    #: in the ledger, never logged, and never written to disk.
    key_env_var: str
    #: litellm's model identifier, e.g. "groq/llama-3.3-70b-versatile".
    model: str
    #: Header names this provider uses, normalised. Empty when the provider
    #: reports none -- which puts it in UNKNOWN rather than in AVAILABLE.
    remaining_requests_header: Optional[str] = None
    remaining_tokens_header: Optional[str] = None
    reset_requests_header: Optional[str] = None
    reset_tokens_header: Optional[str] = None
    #: Declared by the operator. None = free / unpriced.
    cost_per_million_tokens: Optional[float] = None
    #: Chat-completions endpoint.
    #:
    #: NOT WRITTEN FROM MEMORY. Every URL below is copied from the provider
    #: table in artifacts/api-server/src/lib/llmResolver.ts, which is the
    #: code that has actually been making these calls. A hostname recalled
    #: rather than checked is a host that a live key and a researcher's
    #: prompt get POSTed to on somebody's recollection, and that is a worse
    #: failure than any this module prevents.
    #:
    #: `test_endpoints_match_the_api_server_provider_table` reads that file
    #: and fails if the two ever disagree, so this cannot drift into being a
    #: remembered value later.
    api_base: Optional[str] = None
    #: Where the limits were read from, so a reader can check them.
    documentation: str = ""

    @property
    def free(self) -> bool:
        return self.cost_per_million_tokens in (None, 0.0)

    @property
    def reports_quota(self) -> bool:
        """Whether this provider tells us anything we can read.

        A provider that does not is not broken and is not excluded -- it is
        UNKNOWN, and the ordering puts it behind providers whose headroom is
        measured.
        """
        return bool(self.remaining_requests_header or self.remaining_tokens_header)


#: The providers Caterva holds keys for.
#:
#: HEADER NAMES ARE FROM EACH PROVIDER'S OWN DOCUMENTATION, read for this
#: module and cited in `documentation`. Where a provider's docs were not
#: read, its header fields are left EMPTY rather than filled in by analogy
#: with another provider -- guessing that SiliconFlow uses Groq's header
#: names would produce a confident misreading, and UNKNOWN is the honest
#: state for a provider nobody checked.
PROVIDERS: Tuple[Provider, ...] = (
    Provider(
        name="groq",
        api_base="https://api.groq.com/openai/v1/chat/completions",
        key_env_var="GROQ_API_KEY",
        model="groq/llama-3.3-70b-versatile",
        remaining_requests_header="x-ratelimit-remaining-requests",
        remaining_tokens_header="x-ratelimit-remaining-tokens",
        reset_requests_header="x-ratelimit-reset-requests",
        reset_tokens_header="x-ratelimit-reset-tokens",
        documentation="https://console.groq.com/docs/rate-limits",
    ),
    Provider(
        name="openrouter",
        api_base="https://openrouter.ai/api/v1/chat/completions",
        key_env_var="OPENROUTER_API_KEY",
        model="openrouter/meta-llama/llama-3.3-70b-instruct:free",
        # OpenRouter sends these on ERROR responses rather than on every
        # call, so a healthy run leaves them absent and this provider sits
        # in UNKNOWN until something 429s. That is the honest reading of
        # what it reports, not a gap in the parser.
        remaining_requests_header="x-ratelimit-remaining",
        reset_requests_header="x-ratelimit-reset",
        documentation="https://openrouter.ai/docs/api-reference/limits",
    ),
    Provider(
        name="mistral",
        api_base="https://api.mistral.ai/v1/chat/completions",
        key_env_var="MISTRAL_API_KEY",
        model="mistral/mistral-small-latest",
        documentation="https://docs.mistral.ai/deployment/laplateforme/tier/",
    ),
    Provider(
        name="siliconflow",
        api_base="https://api.siliconflow.com/v1/chat/completions",
        key_env_var="SILICONFLOW_API_KEY",
        model="openai/Qwen/Qwen2.5-7B-Instruct",
        documentation="https://docs.siliconflow.com/",
    ),
    Provider(
        name="tokenrouter",
        api_base="https://api.tokenrouter.io/v1/chat/completions",
        key_env_var="TOKENROUTER_API_KEY",
        model="openai/auto",
        documentation="https://tokenrouter.io",
    ),
)

PROVIDERS_BY_NAME: Mapping[str, Provider] = {p.name: p for p in PROVIDERS}

#: Where every `api_base` above came from, so a reader can check them.
API_SERVER_PROVIDER_TABLE = (
    "Science-Agent-Pipeline/artifacts/api-server/src/lib/llmResolver.ts"
)


# ---------------------------------------------------------------------------
# What a provider last told us
# ---------------------------------------------------------------------------


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def parse_duration(value: Any) -> Optional[float]:
    """A reset header, in seconds.

    Providers write these several ways and the differences are not cosmetic:
    Groq sends things like `2.5s`, `1m30s` or a bare number of seconds, and
    reading `1m30s` as 1 second would retry 89 seconds early and burn a 429
    every cycle. Returns `None` on anything unparseable rather than
    defaulting to zero, because zero means "retry immediately" and would
    turn an unreadable header into a hot loop.
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None

    bare = _as_float(text)
    if bare is not None:
        return max(bare, 0.0)

    total = 0.0
    number = ""
    seen = False
    for character in text:
        if character.isdigit() or character == ".":
            number += character
            continue
        unit = {"h": 3600.0, "m": 60.0, "s": 1.0, "d": 86400.0}.get(character)
        if unit is None or not number:
            return None
        parsed = _as_float(number)
        if parsed is None:
            return None
        total += parsed * unit
        number = ""
        seen = True
    if number:  # a trailing number with no unit, e.g. "1m30"
        return None
    return total if seen else None


@dataclass(frozen=True)
class Reading:
    """One provider's own account of its remaining quota, at a moment.

    Every field is `None` when the provider did not say. None is not zero:
    "did not report" and "reported none left" send the gateway to different
    providers, and conflating them is how a working provider gets dropped or
    an exhausted one gets hammered.
    """

    provider: str
    at: float
    remaining_requests: Optional[float] = None
    remaining_tokens: Optional[float] = None
    #: Seconds from `at` until the respective budget refills.
    reset_requests_in: Optional[float] = None
    reset_tokens_in: Optional[float] = None
    #: True when the call this reading came from was rejected for rate.
    rate_limited: bool = False
    #: `retry-after`, when the provider sent one.
    retry_after: Optional[float] = None

    @property
    def reported_anything(self) -> bool:
        return any(
            value is not None
            for value in (
                self.remaining_requests,
                self.remaining_tokens,
                self.reset_requests_in,
                self.reset_tokens_in,
                self.retry_after,
            )
        )

    @property
    def headroom(self) -> Optional[float]:
        """The smaller of the two remaining budgets, when both are known.

        The SMALLER, because a provider with a million tokens left and two
        requests left can serve two more calls. Taking the larger -- or an
        average -- would report headroom the provider does not have, which
        is the one error this whole module exists to avoid.
        """
        values = [
            value for value in (self.remaining_requests, self.remaining_tokens)
            if value is not None
        ]
        return min(values) if values else None

    def available_again_at(self) -> Optional[float]:
        """When this provider is worth trying again, in epoch seconds.

        `retry-after` wins when present: it is the provider telling us
        directly. Otherwise the later of the two reset timers, because both
        budgets have to refill before the call can succeed.
        """
        if self.retry_after is not None:
            return self.at + self.retry_after
        resets = [
            value for value in (self.reset_requests_in, self.reset_tokens_in)
            if value is not None
        ]
        return self.at + max(resets) if resets else None


def read_headers(
    provider: Provider,
    headers: Mapping[str, Any],
    *,
    status: Optional[int] = None,
    now: Optional[float] = None,
) -> Reading:
    """Turn one response's headers into a `Reading`.

    Header lookup is case-insensitive, because HTTP header names are and the
    two providers whose docs were read disagree on case -- Groq documents
    `x-ratelimit-remaining-requests` and OpenRouter `X-RateLimit-Remaining`.
    A case-sensitive parser would silently read one provider and not the
    other, and the symptom would be a provider permanently stuck in UNKNOWN.
    """
    moment = time.time() if now is None else now
    lowered = {str(key).lower(): value for key, value in headers.items()}

    def field(name: Optional[str]) -> Optional[str]:
        return lowered.get(name.lower()) if name else None

    return Reading(
        provider=provider.name,
        at=moment,
        remaining_requests=_as_float(field(provider.remaining_requests_header)),
        remaining_tokens=_as_float(field(provider.remaining_tokens_header)),
        reset_requests_in=parse_duration(field(provider.reset_requests_header)),
        reset_tokens_in=parse_duration(field(provider.reset_tokens_header)),
        rate_limited=status == 429,
        retry_after=parse_duration(lowered.get("retry-after")),
    )


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------


@dataclass
class ProviderState:
    """What the ledger remembers about one provider between calls."""

    provider: str
    last_reading: Optional[Reading] = None
    #: Epoch seconds before which not to try. Set from a reading's reset, or
    #: from a failure rest.
    blocked_until: Optional[float] = None
    consecutive_failures: int = 0
    calls: int = 0
    successes: int = 0
    rate_limits: int = 0
    failures: int = 0
    #: Why it is blocked, in words, so the status output can say.
    blocked_reason: str = ""

    def to_json(self) -> Dict[str, Any]:
        reading = self.last_reading
        return {
            "provider": self.provider,
            "blocked_until": self.blocked_until,
            "blocked_reason": self.blocked_reason,
            "consecutive_failures": self.consecutive_failures,
            "calls": self.calls,
            "successes": self.successes,
            "rate_limits": self.rate_limits,
            "failures": self.failures,
            "last_reading": None if reading is None else {
                "at": reading.at,
                "remaining_requests": reading.remaining_requests,
                "remaining_tokens": reading.remaining_tokens,
                "reset_requests_in": reading.reset_requests_in,
                "reset_tokens_in": reading.reset_tokens_in,
                "rate_limited": reading.rate_limited,
                "retry_after": reading.retry_after,
            },
        }

    @classmethod
    def from_json(cls, blob: Mapping[str, Any]) -> "ProviderState":
        raw = blob.get("last_reading")
        reading = None
        if isinstance(raw, Mapping):
            reading = Reading(
                provider=str(blob.get("provider", "")),
                at=float(raw.get("at", 0.0)),
                remaining_requests=raw.get("remaining_requests"),
                remaining_tokens=raw.get("remaining_tokens"),
                reset_requests_in=raw.get("reset_requests_in"),
                reset_tokens_in=raw.get("reset_tokens_in"),
                rate_limited=bool(raw.get("rate_limited", False)),
                retry_after=raw.get("retry_after"),
            )
        return cls(
            provider=str(blob.get("provider", "")),
            last_reading=reading,
            blocked_until=blob.get("blocked_until"),
            blocked_reason=str(blob.get("blocked_reason", "")),
            consecutive_failures=int(blob.get("consecutive_failures", 0)),
            calls=int(blob.get("calls", 0)),
            successes=int(blob.get("successes", 0)),
            rate_limits=int(blob.get("rate_limits", 0)),
            failures=int(blob.get("failures", 0)),
        )


@dataclass(frozen=True)
class Standing:
    """One provider's place in the queue, and why it is there."""

    provider: Provider
    availability: str
    headroom: Optional[float]
    blocked_until: Optional[float]
    reason: str

    def describe(self) -> str:
        text = f"{self.provider.name}: {self.availability}"
        if self.headroom is not None:
            text += f", headroom {self.headroom:g}"
        if self.blocked_until is not None:
            text += f", retry in {max(self.blocked_until - time.time(), 0):.0f}s"
        return f"{text} -- {self.reason}" if self.reason else text


class Ledger:
    """Per-provider quota state, persisted, with the ordering decision.

    Persisted because the interesting failure is a DAILY cap: a provider
    that ran out at noon must still be known to be out at one o'clock, and a
    gateway restarted in between would otherwise send a request it knows will
    fail. The file holds counters and reset times only -- never a key, never
    a prompt, never a response.
    """

    def __init__(
        self,
        *,
        path: Optional[Path] = None,
        providers: Sequence[Provider] = PROVIDERS,
        environ: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.path = path
        self.providers = tuple(providers)
        self.environ = os.environ if environ is None else environ
        self.states: Dict[str, ProviderState] = {
            provider.name: ProviderState(provider=provider.name)
            for provider in self.providers
        }
        if path is not None and path.exists():
            self._load(path)

    # -- persistence ---------------------------------------------------

    def _load(self, path: Path) -> None:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # A corrupt ledger is not a reason to refuse service: the worst
            # it costs is one wasted 429 per provider while the real state
            # is relearned from headers. Losing the gateway because a cache
            # file was truncated would be the larger failure.
            self.corrupt_reason = f"{type(exc).__name__}: {exc}"
            return
        for entry in blob.get("providers", []):
            if not isinstance(entry, Mapping):
                continue
            state = ProviderState.from_json(entry)
            if state.provider in self.states:
                self.states[state.provider] = state

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "_note": (
                "Quota state for the LLM waterfall. Counters and reset times "
                "only -- no keys, no prompts, no responses. Safe to delete: "
                "the gateway relearns from response headers."
            ),
            "written_at": time.time(),
            "providers": [state.to_json() for state in self.states.values()],
        }
        # Written via a temporary file and renamed, so a crash mid-write
        # leaves the previous ledger rather than a truncated one.
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    # -- recording -----------------------------------------------------

    def configured(self, provider: Provider) -> bool:
        return bool(str(self.environ.get(provider.key_env_var, "")).strip())

    def record(
        self,
        provider_name: str,
        *,
        headers: Optional[Mapping[str, Any]] = None,
        status: Optional[int] = None,
        ok: Optional[bool] = None,
        now: Optional[float] = None,
    ) -> Reading:
        """Record one call's outcome and return what the provider reported."""
        provider = PROVIDERS_BY_NAME.get(provider_name)
        if provider is None:
            raise QuotaError(
                f"{provider_name!r} is not a known provider. Known: "
                f"{', '.join(sorted(PROVIDERS_BY_NAME))}."
            )
        moment = time.time() if now is None else now
        state = self.states[provider_name]
        state.calls += 1

        reading = read_headers(
            provider, headers or {}, status=status, now=moment
        )
        if reading.reported_anything:
            state.last_reading = reading

        succeeded = ok if ok is not None else (status is not None and status < 400)
        if succeeded:
            state.successes += 1
            state.consecutive_failures = 0
            # A success does NOT clear a block set from a reading: a provider
            # can answer one call and still report zero remaining for the
            # next. The reading decides, not the outcome.
        elif status == 429 or reading.rate_limited:
            state.rate_limits += 1
            state.consecutive_failures = 0  # a 429 is not a malfunction
            until = reading.available_again_at()
            if until is not None:
                state.blocked_until = until
                state.blocked_reason = (
                    "rate limited; provider gave a reset time"
                )
            else:
                # Rate limited with no reset information. Resting for the
                # stated failure interval is a choice and is named as one --
                # the alternative is retrying immediately into a known 429.
                state.blocked_until = moment + FAILURE_REST_SECONDS
                state.blocked_reason = (
                    "rate limited and reported no reset time, so the rest is "
                    f"this module's {FAILURE_REST_SECONDS:g}s default rather "
                    "than the provider's own figure"
                )
        else:
            state.failures += 1
            state.consecutive_failures += 1
            if state.consecutive_failures >= CONSECUTIVE_FAILURES_BEFORE_REST:
                state.blocked_until = moment + FAILURE_REST_SECONDS
                state.blocked_reason = (
                    f"{state.consecutive_failures} consecutive failures that "
                    f"were not rate limits -- in quota and still not working"
                )
        return reading

    # -- the decision --------------------------------------------------

    def standing(self, provider: Provider, *, now: Optional[float] = None) -> Standing:
        moment = time.time() if now is None else now
        state = self.states[provider.name]

        if not self.configured(provider):
            return Standing(
                provider, ABSENT, None, None,
                f"{provider.key_env_var} is not set",
            )

        if state.blocked_until is not None:
            if moment < state.blocked_until - RESET_SLACK_SECONDS:
                return Standing(
                    provider, EXHAUSTED, None, state.blocked_until,
                    state.blocked_reason,
                )
            # The block has expired. Clear it and let the next reading
            # decide again, rather than carrying a stale reason forward.
            state.blocked_until = None
            state.blocked_reason = ""

        reading = state.last_reading
        if reading is None or not reading.reported_anything:
            return Standing(
                provider, UNKNOWN, None, None,
                "no rate-limit information reported yet"
                if provider.reports_quota else
                "this provider does not report rate-limit headers, so its "
                "headroom is unknown rather than assumed",
            )

        headroom = reading.headroom
        if headroom is None:
            return Standing(
                provider, UNKNOWN, None, None,
                "reported a reset time but no remaining count",
            )
        if headroom <= 0:
            return Standing(
                provider, EXHAUSTED, 0.0, reading.available_again_at(),
                "reported zero remaining",
            )
        return Standing(
            provider, AVAILABLE, headroom, None,
            "reported remaining quota",
        )


    def order(self, *, now: Optional[float] = None) -> List[Standing]:
        """Every provider, best first.

        THE ORDERING, and the reasoning for it:

        1. Measured-available free providers, MOST HEADROOM FIRST. Not
           cheapest-first -- every free tier costs the same zero, so price
           cannot order them. Draining the roomiest first spreads the load
           and pushes the first exhaustion as late as it will go, which is
           the actual goal.
        2. Then UNKNOWN providers, which have not said they are fine and
           have not said they are not. They go after everything measured
           because a measured yes beats a silence.
        3. Then priced providers, cheapest first, using the cost the
           OPERATOR declared -- this file states no prices.
        4. Exhausted and absent last, so the list is always complete and a
           caller can see why something is missing rather than finding it
           gone.
        """
        standings = [self.standing(p, now=now) for p in self.providers]

        def key(standing: Standing) -> Tuple[int, float, float, str]:
            provider = standing.provider
            cost = (
                provider.cost_per_million_tokens
                if provider.cost_per_million_tokens is not None else 0.0
            )
            if standing.availability == AVAILABLE and provider.free:
                # Negated headroom so that larger sorts earlier.
                return (0, -(standing.headroom or 0.0), 0.0, provider.name)
            if standing.availability == UNKNOWN and provider.free:
                return (1, 0.0, 0.0, provider.name)
            if standing.availability in (AVAILABLE, UNKNOWN):
                return (2, 0.0, cost, provider.name)
            if standing.availability == EXHAUSTED:
                return (3, 0.0, cost, provider.name)
            return (4, 0.0, cost, provider.name)

        return sorted(standings, key=key)

    def next_provider(self, *, now: Optional[float] = None) -> Provider:
        """The one to try. Refuses rather than returning an exhausted one."""
        order = self.order(now=now)
        for standing in order:
            if standing.availability in (AVAILABLE, UNKNOWN):
                return standing.provider
        raise QuotaError(
            "every configured provider is exhausted or unconfigured, so there "
            "is nothing to try:\n  "
            + "\n  ".join(s.describe() for s in order)
            + "\nThe waterfall is out of water. Add another provider's key, "
            "or wait for the earliest reset above."
        )

    def chain(self, *, now: Optional[float] = None) -> List[str]:
        """Provider names in fallback order, exhausted ones dropped.

        What `litellm`'s fallback list wants. Exhausted providers are
        omitted rather than placed last: litellm would try them, and a call
        we already know will 429 costs a round trip and a retry budget.
        """
        return [
            standing.provider.name
            for standing in self.order(now=now)
            if standing.availability in (AVAILABLE, UNKNOWN)
        ]

    def summary(self, *, now: Optional[float] = None) -> str:
        order = self.order(now=now)
        lines = [f"{len(order)} provider(s), best first:"]
        for standing in order:
            lines.append("  - " + standing.describe())

        unknown = [s for s in order if s.availability == UNKNOWN]
        if unknown:
            lines.append(
                f"{len(unknown)} provider(s) are UNKNOWN rather than "
                f"available: they have not reported rate-limit information, "
                f"which is not the same as reporting that they are fine. "
                f"They are tried after every provider whose headroom was "
                f"measured."
            )

        absent = [s for s in order if s.availability == ABSENT]
        if absent:
            lines.append(
                f"{len(absent)} provider(s) have no key set: "
                + ", ".join(s.provider.key_env_var for s in absent)
                + "."
            )

        lines.append(
            "Ordering is by MEASURED headroom, not by price: every free tier "
            "costs the same zero, so a price-ordered list of free providers "
            "would be arbitrary. Nothing here hardcodes a rate limit -- the "
            "numbers come from what each provider reported about itself."
        )
        return "\n".join(lines)


__all__ = [
    "AVAILABLE", "EXHAUSTED", "UNKNOWN", "ABSENT", "AVAILABILITIES",
    "CONSECUTIVE_FAILURES_BEFORE_REST", "FAILURE_REST_SECONDS",
    "RESET_SLACK_SECONDS",
    "Provider", "PROVIDERS", "PROVIDERS_BY_NAME",
    "Reading", "ProviderState", "Standing", "Ledger", "QuotaError",
    "read_headers", "parse_duration", "API_SERVER_PROVIDER_TABLE",
]
