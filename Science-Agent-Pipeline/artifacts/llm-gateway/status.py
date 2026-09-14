"""Is the waterfall ok, and how much is left -- answered for a human and for a
script.

WHAT THIS IS FOR
----------------
`quota.py` decides which provider to ask next. It cannot tell anyone whether
the gateway is in trouble, because nothing reads it out loud. This is the
read-out: one command, five providers, and an exit code a monitoring script
can branch on.

    python -m status            # for a person: the order, and why
    python -m status --json     # for a health check: the same state, parsed
    python -m status --probe    # spend quota to measure quota (opt-in)
    python -m status --reset    # forget everything and relearn

THE EXIT CODE IS THE POINT
--------------------------
0 means at least one provider is AVAILABLE or UNKNOWN -- the waterfall has
somewhere to send the next request. 1 means every provider is exhausted or has
no key, which is a real outage: extraction will fail until a reset time passes
or a key is added.

WHAT EXIT 0 DOES NOT CLAIM
--------------------------
It does not claim the next call will succeed. UNKNOWN counts toward 0 because a
provider that reported nothing has not reported that it is out -- but it has
not reported that it is fine either, and a provider that 401s on every call
sits in UNKNOWN until it has failed enough times to be rested. Exit 0 means
"there is something left to try", not "the gateway is healthy". Anything
stronger would be this file inventing confidence that nobody measured, which is
the same defect as inventing a rate limit.

WHY --probe IS OPT-IN
---------------------
Three of the five providers send no rate-limit headers at all, and OpenRouter
sends them only on error responses. For those, the ONLY way to learn anything
is to make a call and read what comes back -- which spends a request from the
budget being measured. On a 50-requests-a-day free tier, a probe on every
health check would be a meaningful fraction of the day's capacity consumed by
the monitoring rather than the work. So probing never happens by default, and
the help text says what it costs.

A probe that succeeds and reports nothing leaves the provider UNKNOWN. It does
NOT promote it to AVAILABLE. One answered call is evidence that the key works,
not a measurement of remaining headroom, and recording it as headroom would be
a number nobody measured.

WHAT THIS FILE DOES NOT CONTAIN
-------------------------------
No rate limits. Not one. Every figure printed came out of a response header or
out of the persisted ledger, and a provider that reported nothing prints as
UNKNOWN with a null headroom rather than as a guess. See `quota.py`'s header
for the full argument; the short version is that a limits table is a set of
numbers nobody here measured, in a project whose whole claim is that it does
not do that.

No LLM-supplied values either, in the sense ADR 0011 cares about. The probe
sends a throwaway prompt and DISCARDS the reply without parsing it. The only
thing read from a probe is the HTTP status and the response headers. This
command cannot introduce a model-invented number into anything, because it
never reads a model's words at all.

KEYS ARE NEVER PRINTED
----------------------
Not the value, and not a prefix. Four characters is enough to match a key
against one that leaked somewhere else, and enough to confirm a guess about
which account is in use, so "sk-abc..." is a disclosure and not a convenience.
What gets printed is the env var NAME and whether it is set, which is the part
an operator actually needs in order to fix something.

The guarantee is structural rather than a promise to be careful: every byte
this module writes is assembled into one string and passed through `redact()`,
which removes any configured key value it finds. That covers the realistic leak
path, which is not this file printing a key on purpose -- it is a provider
echoing the key back inside a 401 message that then gets reported verbatim.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any, Callable, Dict, List, Mapping, Optional, Sequence, TextIO, Tuple,
)

from quota import (
    ABSENT, AVAILABLE, EXHAUSTED, PROVIDERS, UNKNOWN, Ledger, Provider,
    Standing,
)

#: The account every provider key belongs to. Recorded here because the
#: question "whose free tier is this" comes up the moment a limit is hit, and
#: the answer otherwise lives only in someone's memory.
ACCOUNT_EMAIL = "admin.terrium@gmail.com"

#: Exit 0: at least one provider is AVAILABLE or UNKNOWN.
EXIT_OK = 0
#: Exit 1: every provider is EXHAUSTED or ABSENT. The waterfall is dry.
EXIT_DRY = 1
#: Exit 2: the question could not be answered -- a probe was asked for and the
#: transport is unavailable, or the ledger path is unusable. Kept separate from
#: 1 so a monitor never reads "I could not check" as "there is nothing left".
EXIT_CANNOT_ANSWER = 2

#: Per-probe timeout, in seconds. NOT a rate limit and not a measurement: it is
#: `request_timeout` from config.yaml, repeated here so a probe and a real call
#: give up at the same point rather than at two different ones.
DEFAULT_TIMEOUT_SECONDS = 30.0

#: Env var holding an override for where the ledger lives.
LEDGER_PATH_ENV_VAR = "TERRIUM_LLM_QUOTA_LEDGER"

#: A configured value shorter than this is not used for scrubbing output.
#:
#: Redacting a two-character secret would blank fragments of every line and
#: corrupt the JSON, which is a worse outcome than not scrubbing a value that
#: nothing prints in the first place. Stated rather than silent, because it is
#: a real hole in an otherwise structural guarantee.
MIN_SCRUBBABLE_SECRET = 8

#: Env vars whose values are scrubbed from output, beyond the provider keys.
EXTRA_SECRET_ENV_VARS = ("LITELLM_MASTER_KEY",)


class ProbeUnavailable(RuntimeError):
    """A probe was asked for and cannot be made -- no transport, not a
    provider saying no."""


# ---------------------------------------------------------------------------
# Never print a key
# ---------------------------------------------------------------------------


def secret_values(
    environ: Mapping[str, str],
    providers: Sequence[Provider] = PROVIDERS,
) -> Tuple[str, ...]:
    """Every configured key value, so output can be scrubbed of them.

    Collected from the environment rather than passed around, because the
    values this needs to remove are exactly the ones that are set -- and a
    caller who had to remember to hand them over would eventually forget.
    """
    names = [p.key_env_var for p in providers] + list(EXTRA_SECRET_ENV_VARS)
    found = []
    for name in names:
        value = str(environ.get(name, "") or "").strip()
        if len(value) >= MIN_SCRUBBABLE_SECRET:
            found.append(value)
    # Longest first, so a key that contains another key as a substring is
    # removed whole instead of being left with a hole in the middle.
    return tuple(sorted(set(found), key=len, reverse=True))


def redact(text: str, secrets: Sequence[str]) -> str:
    """Remove any configured key value from a string about to be printed.

    This exists for the case nobody writes deliberately: a provider rejecting a
    key with a message that quotes it back, reported verbatim by `--probe`.

    Longest secret first, decided here rather than trusted to the caller: if one
    key contains another as a substring, removing the short one first leaves the
    rest of the long one readable next to a `<redacted>` that makes the line
    look safe. A guarantee that depends on argument order is not a guarantee.
    """
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(secret, "<redacted>")
    return text


# ---------------------------------------------------------------------------
# The probe transport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProbeOutcome:
    """What one probe call produced -- status and headers only.

    No response body. A probe reads the envelope, never the message: see the
    module docstring on ADR 0011. Recording the model's words here would put a
    language model's output one refactor away from something that matters.
    """

    status: Optional[int] = None
    headers: Mapping[str, str] = field(default_factory=dict)
    #: Transport-level or provider-level error text, already about to be
    #: scrubbed of key values before anything prints it.
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status is not None and self.status < 400


#: A probe transport: given a provider and its key, make one minimal call.
#:
#: Injectable because the alternative is a test suite that either makes real
#: network calls -- flaky, and it spends the very quota under test -- or patches
#: a module attribute and asserts on the patch. A parameter is smaller than
#: both.
Transport = Callable[..., ProbeOutcome]


def _mapping_from(candidate: Any) -> Optional[Mapping[str, str]]:
    try:
        items = candidate.items()
    except AttributeError:
        return None
    try:
        return {str(key): value for key, value in items}
    except (TypeError, ValueError):
        return None


def _headers_from(obj: Any) -> Mapping[str, str]:
    """Dig response headers out of whatever litellm handed back.

    HONEST ABOUT ITS OWN RELIABILITY: litellm is not installed in this
    repository and PyPI is unreachable from the sandbox, so these attribute
    paths were NOT verified against a running version and the set of them is a
    guess about which one a given release uses.

    That is tolerable only because of how it fails. If every path misses, this
    returns nothing, `read_headers` finds nothing, and the provider stays
    UNKNOWN. The unverified code can lose information; it cannot manufacture a
    headroom figure or promote a provider to AVAILABLE. Failing toward UNKNOWN
    is the entire reason UNKNOWN exists.
    """
    accessors = (
        lambda: obj._hidden_params["additional_headers"],
        lambda: obj._hidden_params["response_headers"],
        lambda: obj.response.headers,
        lambda: obj.headers,
        lambda: obj.response_headers,
    )
    for accessor in accessors:
        try:
            found = _mapping_from(accessor())
        except Exception:  # noqa: BLE001 -- any accessor may simply not exist
            continue
        if found:
            return found
    return {}


def litellm_transport(
    provider: Provider,
    api_key: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ProbeOutcome:
    """One minimal real call, through the same stack the gateway itself uses.

    WHY litellm RATHER THAN A DIRECT HTTP POST: a direct POST needs each
    provider's base URL, and config.yaml declares only two of the five (the
    OpenAI-compatible ones). Writing the other three into this file would be
    three endpoints nobody in this repository verified, duplicated in a place
    that nothing would update when one moved. litellm already holds that
    mapping and is what the proxy uses, so a probe through it measures the path
    the real traffic takes instead of a parallel one that might differ.

    The cost is that litellm is an optional dependency, absent here, so this
    function is the one thing in this module that cannot be exercised by the
    test suite. It is imported lazily and refuses with an install instruction,
    and every caller injects its own transport in tests.
    """
    try:
        import litellm  # noqa: PLC0415 -- lazy on purpose; see the docstring
    except ImportError as exc:
        raise ProbeUnavailable(
            "--probe needs litellm and it is not installed. litellm is not in "
            "requirements.txt because nothing else in this repository needs "
            "it; install it where the gateway runs:\n"
            "    pip install 'litellm[proxy]'\n"
            "Everything except --probe works without it: the default and "
            "--json views read the persisted ledger and the environment, "
            "neither of which needs a transport."
        ) from exc

    # max_tokens=1 and a one-word prompt because the point is the response
    # HEADERS. Tokens spent on a reply nobody reads are tokens taken off the
    # budget this command exists to report.
    try:
        response = litellm.completion(
            model=provider.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
            timeout=timeout,
            api_key=api_key,
        )
    except Exception as exc:  # noqa: BLE001 -- litellm raises many types
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        return ProbeOutcome(
            status=int(status) if isinstance(status, int) else None,
            headers=_headers_from(exc),
            error=f"{type(exc).__name__}: {exc}",
        )

    # The reply is discarded here, deliberately and permanently. See ADR 0011.
    return ProbeOutcome(status=200, headers=_headers_from(response))


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProbeReport:
    """What one provider's probe changed, or why it was skipped."""

    provider: str
    attempted: bool
    before: str
    after: str
    status: Optional[int] = None
    error: Optional[str] = None
    note: str = ""

    def describe(self) -> str:
        if not self.attempted:
            return f"{self.provider}: not probed -- {self.note}"
        outcome = f"HTTP {self.status}" if self.status is not None else "no response"
        moved = (
            f"{self.before} -> {self.after}"
            if self.before != self.after else f"still {self.after}"
        )
        text = f"{self.provider}: {outcome}, {moved}"
        if self.note:
            text += f" -- {self.note}"
        if self.error:
            text += f" [{self.error}]"
        return text

    def to_json(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "attempted": self.attempted,
            "availability_before": self.before,
            "availability_after": self.after,
            "status": self.status,
            "error": self.error,
            "note": self.note,
        }


def probe_providers(
    ledger: Ledger,
    *,
    transport: Transport,
    environ: Mapping[str, str],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    now: Optional[float] = None,
) -> List[ProbeReport]:
    """Spend one request per configured provider to learn its headroom.

    Providers with no key are skipped rather than attempted: there is nothing
    to authenticate with, the call would fail, and the failure would be
    recorded against a provider that was never in play.
    """
    moment = time.time() if now is None else now
    reports: List[ProbeReport] = []

    for provider in ledger.providers:
        before = ledger.standing(provider, now=moment).availability
        if before == ABSENT:
            reports.append(ProbeReport(
                provider=provider.name, attempted=False,
                before=before, after=before,
                note=f"{provider.key_env_var} is not set",
            ))
            continue

        api_key = str(environ.get(provider.key_env_var, "") or "").strip()
        try:
            outcome = transport(provider, api_key, timeout=timeout)
        except ProbeUnavailable:
            # No transport at all is not a fact about this provider, so
            # nothing is recorded against it and the whole probe stops.
            raise
        except Exception as exc:  # noqa: BLE001 -- a transport may raise anything
            # A broken transport IS a failed attempt against this provider as
            # far as the operator is concerned, so it is reported -- but it is
            # not recorded in the ledger, because a bug on our side is not a
            # provider malfunction and should not rest a working provider.
            reports.append(ProbeReport(
                provider=provider.name, attempted=True,
                before=before, after=before,
                error=f"{type(exc).__name__}: {exc}",
                note="the transport raised, so nothing was recorded against "
                     "this provider",
            ))
            continue

        reading = ledger.record(
            provider.name,
            headers=outcome.headers,
            status=outcome.status,
            ok=outcome.ok,
            now=moment,
        )
        after = ledger.standing(provider, now=moment).availability

        if after == UNKNOWN and outcome.ok:
            note = (
                "answered, but reported no rate-limit information, so it stays "
                "UNKNOWN -- one answered call is evidence the key works, not a "
                "measurement of what is left"
            )
        elif not reading.reported_anything:
            note = "reported no rate-limit information"
        else:
            note = "reported rate-limit information, which is now in the ledger"

        reports.append(ProbeReport(
            provider=provider.name, attempted=True,
            before=before, after=after,
            status=outcome.status, error=outcome.error, note=note,
        ))

    return reports


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def exit_code_for(standings: Sequence[Standing]) -> int:
    """0 if anything is worth trying, 1 if nothing is."""
    return EXIT_OK if any(
        standing.availability in (AVAILABLE, UNKNOWN) for standing in standings
    ) else EXIT_DRY


def default_ledger_path(environ: Mapping[str, str]) -> Path:
    """Where the ledger lives when nobody says.

    Under the cache directory rather than beside this file, because the ledger
    is regenerable state -- quota.py says so in the file it writes -- and a
    tracked source directory is the wrong place for a file that changes on
    every call.
    """
    override = str(environ.get(LEDGER_PATH_ENV_VAR, "") or "").strip()
    if override:
        return Path(override).expanduser()
    cache = str(environ.get("XDG_CACHE_HOME", "") or "").strip()
    base = Path(cache).expanduser() if cache else Path.home() / ".cache"
    return base / "terrium" / "llm-quota.json"


def key_lines(ledger: Ledger) -> List[str]:
    lines = [
        "Keys -- the variable NAME and whether it is set. A value is never "
        "printed,",
        "not even the first few characters: a prefix is enough to match a key "
        "against",
        "one that leaked somewhere else, and enough to confirm a guess.",
    ]
    width = max(len(p.key_env_var) for p in ledger.providers)
    for provider in ledger.providers:
        state = "set" if ledger.configured(provider) else "NOT SET"
        lines.append(f"  {provider.key_env_var:<{width}}  {state}")
    return lines


def human_report(
    ledger: Ledger,
    standings: Sequence[Standing],
    *,
    now: float,
    probe_reports: Optional[Sequence[ProbeReport]] = None,
    reset_note: str = "",
) -> str:
    lines: List[str] = ["Terrium LLM waterfall -- status"]
    lines.append(f"account: {ACCOUNT_EMAIL}")
    lines.append(f"ledger:  {ledger.path if ledger.path else '(none -- in memory)'}")
    if getattr(ledger, "corrupt_reason", None):
        lines.append(
            f"NOTE: the ledger file could not be read ({ledger.corrupt_reason}). "
            "State was relearned from scratch, which costs at most one wasted "
            "call per provider."
        )
    if reset_note:
        lines.append(reset_note)
    lines.append("")
    lines.extend(key_lines(ledger))
    lines.append("")

    if probe_reports is not None:
        attempted = sum(1 for report in probe_reports if report.attempted)
        lines.append(
            f"Probe: {attempted} request(s) spent to measure headroom. That "
            "capacity is gone from today's budget."
        )
        for report in probe_reports:
            lines.append("  - " + report.describe())
        lines.append("")

    lines.append(ledger.summary(now=now))
    lines.append("")

    code = exit_code_for(standings)
    if code == EXIT_OK:
        lines.append(
            "exit 0: at least one provider is AVAILABLE or UNKNOWN, so there "
            "is somewhere to send the next request. This does NOT claim the "
            "next call will succeed -- UNKNOWN means the provider has said "
            "nothing either way."
        )
    else:
        lines.append(
            "exit 1: every provider is exhausted or has no key. Extraction "
            "will fail until the earliest reset above passes, or until another "
            "key is set."
        )
    unmeasured = [s for s in standings if s.headroom is None
                  and s.availability != ABSENT]
    if unmeasured:
        lines.append(
            f"{len(unmeasured)} provider(s) show no headroom figure because "
            "none was reported. Nothing here substitutes a documented or "
            "remembered rate limit for a measured one -- run --probe to make "
            "a provider report, at the cost of a request."
        )
    return "\n".join(lines)


def json_payload(
    ledger: Ledger,
    standings: Sequence[Standing],
    *,
    now: float,
    probe_reports: Optional[Sequence[ProbeReport]] = None,
    reset: bool = False,
) -> Dict[str, Any]:
    providers: List[Dict[str, Any]] = []
    for standing in standings:
        provider = standing.provider
        state = ledger.states[provider.name]
        reading = state.last_reading
        providers.append({
            "name": provider.name,
            "availability": standing.availability,
            # null, never a guess: a provider that reported no remaining count
            # has no headroom figure, and inventing one from a documented tier
            # is the failure this whole gateway is built to avoid.
            "headroom": standing.headroom,
            "reason": standing.reason,
            "blocked_until": standing.blocked_until,
            "retry_in_seconds": (
                None if standing.blocked_until is None
                else max(standing.blocked_until - now, 0.0)
            ),
            "key_env_var": provider.key_env_var,
            "key_set": ledger.configured(provider),
            "model": provider.model,
            "reports_quota_headers": provider.reports_quota,
            "documentation": provider.documentation,
            "calls": state.calls,
            "successes": state.successes,
            "rate_limits": state.rate_limits,
            "failures": state.failures,
            "consecutive_failures": state.consecutive_failures,
            "last_reading_at": None if reading is None else reading.at,
        })

    counts = {name: 0 for name in (AVAILABLE, UNKNOWN, EXHAUSTED, ABSENT)}
    for standing in standings:
        counts[standing.availability] = counts.get(standing.availability, 0) + 1

    code = exit_code_for(standings)
    return {
        "generated_at": now,
        "account": ACCOUNT_EMAIL,
        "ledger_path": None if ledger.path is None else str(ledger.path),
        "ledger_was_reset": reset,
        "ledger_unreadable": getattr(ledger, "corrupt_reason", None),
        "exit_code": code,
        "ok": code == EXIT_OK,
        "counts": counts,
        "providers": providers,
        "chain": ledger.chain(now=now),
        "probe": (
            None if probe_reports is None
            else [report.to_json() for report in probe_reports]
        ),
        "claims": {
            # Restated in the machine-readable output so a consumer does not
            # have to read the prose to find out what these fields mean.
            "unknown_is_not_available": True,
            "ok_means": "at least one provider is available or unknown; not "
                        "that the next call will succeed",
            "headroom_source": "provider-reported response headers only; null "
                               "means the provider reported nothing",
            "hardcoded_rate_limits": False,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="status",
        description=(
            "Report the state of Terrium's LLM provider waterfall. Exits 0 "
            "when at least one provider is available or unknown, 1 when every "
            "provider is exhausted or has no key, 2 when the question could "
            "not be answered."
        ),
        epilog=(
            "Keys are never printed -- not the value and not a prefix. Only "
            f"the variable name and whether it is set. Account: "
            f"{ACCOUNT_EMAIL}."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit the same state as JSON, for a health check.",
    )
    parser.add_argument(
        "--probe", action="store_true",
        help=(
            "SPENDS QUOTA TO MEASURE QUOTA: sends one minimal request to each "
            "provider that has a key, and reads the rate-limit headers that "
            "come back. Opt-in because it spends quota -- three of the five "
            "providers report nothing except on a real call, so this is the "
            "only way to move them out of UNKNOWN, and the requests it spends "
            "come off the same free-tier budget the gateway needs. The reply "
            "is discarded unread; only the status and headers are used."
        ),
    )
    parser.add_argument(
        "--reset", action="store_true",
        help=(
            "delete the persisted ledger and report from a clean slate. Costs "
            "at most one wasted call per provider while the real state is "
            "relearned from headers."
        ),
    )
    parser.add_argument(
        "--ledger", metavar="PATH", default=None,
        help=(
            "where the ledger lives. Defaults to "
            f"${LEDGER_PATH_ENV_VAR} if set, else a file under the user cache "
            "directory."
        ),
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, metavar="SECONDS",
        help=(
            "per-probe timeout. Default matches request_timeout in config.yaml "
            f"({DEFAULT_TIMEOUT_SECONDS:g}s) so a probe gives up where a real "
            "call would."
        ),
    )
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    transport: Optional[Transport] = None,
    environ: Optional[Mapping[str, str]] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
    now: Optional[float] = None,
) -> int:
    """Run the CLI and return an exit code.

    Everything the process touches is a parameter with a default: argv, the
    environment, both streams, the clock and the transport. That is what lets
    the test suite assert on real output -- including the promise that no key
    value appears in it -- without a subprocess, a monkeypatch or a network.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    environ = os.environ if environ is None else environ
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    moment = time.time() if now is None else now
    secrets = secret_values(environ)

    def write(stream: TextIO, text: str) -> None:
        # One assembled string, scrubbed once, written once. Redacting in
        # chunks could miss a key value that straddled two writes.
        stream.write(redact(text, secrets) + "\n")

    parser = build_parser()
    if "--help" in argv or "-h" in argv:
        # Printed to the injected stream rather than through parser.parse_args,
        # so the help text is testable as output instead of as a SystemExit.
        write(out, parser.format_help())
        return EXIT_OK
    args = parser.parse_args(argv)

    path = (
        Path(args.ledger).expanduser() if args.ledger
        else default_ledger_path(environ)
    )

    reset_note = ""
    if args.reset:
        try:
            if path.exists():
                path.unlink()
                reset_note = f"ledger cleared: {path}"
            else:
                reset_note = f"nothing to clear: {path} does not exist"
        except OSError as exc:
            write(err, f"could not clear the ledger at {path}: {exc}")
            return EXIT_CANNOT_ANSWER

    ledger = Ledger(path=path, environ=environ)

    probe_reports: Optional[List[ProbeReport]] = None
    if args.probe:
        chosen = litellm_transport if transport is None else transport
        try:
            probe_reports = probe_providers(
                ledger, transport=chosen, environ=environ,
                timeout=args.timeout, now=moment,
            )
        except ProbeUnavailable as exc:
            write(err, str(exc))
            return EXIT_CANNOT_ANSWER
        try:
            ledger.save()
        except OSError as exc:
            # The measurement still happened and is still worth reporting; it
            # just will not survive this process. Said out loud rather than
            # swallowed, because a ledger that silently never persists turns
            # every run into a fresh probe.
            write(err, f"warning: measured state could not be saved to {path}: {exc}")

    standings = ledger.order(now=moment)
    if args.json:
        payload = json_payload(
            ledger, standings, now=moment,
            probe_reports=probe_reports, reset=args.reset,
        )
        write(out, json.dumps(payload, indent=2, sort_keys=True))
    else:
        write(out, human_report(
            ledger, standings, now=moment,
            probe_reports=probe_reports, reset_note=reset_note,
        ))
    return exit_code_for(standings)


__all__ = [
    "ACCOUNT_EMAIL", "DEFAULT_TIMEOUT_SECONDS", "EXIT_CANNOT_ANSWER",
    "EXIT_DRY", "EXIT_OK", "LEDGER_PATH_ENV_VAR", "MIN_SCRUBBABLE_SECRET",
    "ProbeOutcome", "ProbeReport", "ProbeUnavailable", "Transport",
    "build_parser", "default_ledger_path", "exit_code_for", "human_report",
    "json_payload", "key_lines", "litellm_transport", "main",
    "probe_providers", "redact", "secret_values",
]


if __name__ == "__main__":
    sys.exit(main())
