"""What breaks when the waterfall is wired up wrong.

WHAT THIS FILE IS FOR
---------------------
`test_quota.py` tests the ordering decision, which is pure Python and can be
tested exactly. This file tests the two places where that decision meets the
world: `config.yaml`, which is what the proxy actually calls, and the glue that
turns an order into a request.

The bug it exists to catch is DRIFT between those two. `quota.py` orders five
providers; `config.yaml` declares five deployments. Nothing in either file
forces them to be the same five, or to name the same models. When they
disagree the gateway does not crash -- it keeps working, and the ledger
records headroom against a model the proxy is not calling. Every figure the
status output prints is then about the wrong thing, and neither file's own
tests notice. That is the most likely wiring bug here and the most invisible,
so it gets the most tests.

The second thing checked is that `config.yaml` still states no numbers nobody
measured. rpm/tpm, a price, a retry budget spent on a known 429: each would be
an assertion this repository cannot defend, and each is easy to add by
accident while "tuning" the proxy.

WHAT IS NOT CLAIMED HERE
------------------------
1. Nothing here contacts a provider. No test asserts that a key works, that a
   model still exists, or that a documented rate limit is the real one --
   those are measurements and this process cannot make them. What is checked
   is internal consistency between two files, plus the absence of invented
   numbers in one of them.
2. litellm is NOT installed here and PyPI is unreachable, so nothing builds a
   router or sends a request. The gateway tests assert the REFUSAL path
   instead: that the module imports fine without litellm and says how to
   install it rather than dying on a bare ImportError.
3. `gateway.py` and `status.py` are written separately and may not exist yet.
   They are imported INSIDE the tests. A missing module skips, and the skip
   message names the behaviour that went unchecked -- a test that vanishes
   quietly is worse than one that fails. An import that fails for any other
   reason, notably `import litellm` at module scope, FAILS rather than skips,
   because that is precisely the defect the lazy-import rule is about.
4. No test here asserts a key's value. The one test that needs keys present
   sets sentinel strings and then checks the sentinel does NOT appear in
   output.
"""

from __future__ import annotations

import importlib
import inspect
import io
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple

import pytest

import quota
from quota import PROVIDERS, PROVIDERS_BY_NAME, Ledger

try:  # PyYAML ships with litellm but is not otherwise required here.
    import yaml
except ImportError:  # pragma: no cover -- reported as a failure, see load_config
    yaml = None  # type: ignore[assignment]


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.yaml"
#: artifacts/llm-gateway -> artifacts -> Science-Agent-Pipeline
ENV_EXAMPLE_PATH = HERE.parents[1] / ".env.example"

#: The only form an api_key may take in a file that is committed.
ENV_PREFIX = "os.environ/"
ENV_REFERENCE = re.compile(re.escape(ENV_PREFIX) + r"([A-Za-z_][A-Za-z0-9_]*)")

#: Assignment lines in .env.example, commented or not. A var documented as
#: `# FOO=` is still documented -- what matters is that a reader setting up
#: the gateway is told the name exists.
ENV_ASSIGNMENT = re.compile(r"^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")

#: Prefixes real provider keys are issued with. Finding one in a committed
#: file means a credential was committed, whatever the surrounding key said.
KEY_PREFIXES = ("sk-", "sk_", "gsk_", "hf_", "Bearer ", "r8_", "csk-")

#: A leaf that looks like an opaque token: long, unbroken, mixed alphanumeric.
#: Model names and ids in this file all contain a dot or a slash or no digit,
#: so this catches a pasted secret without catching a model string.
OPAQUE_TOKEN = re.compile(r"^(?=.*[0-9])(?=.*[A-Za-z])[A-Za-z0-9_-]{24,}$")


# ---------------------------------------------------------------------------
# Reading config.yaml
# ---------------------------------------------------------------------------


def load_config() -> Mapping[str, Any]:
    """The parsed config, or a FAILURE saying why it could not be read.

    Deliberately not `importorskip`: if PyYAML is missing, skipping would take
    the committed-credential check and the drift check with it and report
    green. The checks in this file are the reason it exists, so an environment
    that cannot run them is a failure, not an exemption.
    """
    if yaml is None:
        pytest.fail(
            "PyYAML is not importable, so config.yaml cannot be parsed and "
            "the credential and drift checks in this file cannot run. "
            "Install it with: pip install pyyaml. This fails rather than "
            "skips on purpose."
        )
    text = CONFIG_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    if not isinstance(parsed, Mapping):
        pytest.fail(
            f"{CONFIG_PATH} did not parse to a mapping but to "
            f"{type(parsed).__name__}."
        )
    return parsed


def config_text() -> str:
    return CONFIG_PATH.read_text(encoding="utf-8")


@dataclass(frozen=True)
class Deployment:
    """One `model_list` entry, read the way litellm reads it."""

    position: int
    model_name: str
    model: str
    api_key: str
    api_base: Optional[str]
    identifier: Optional[str]

    @property
    def env_var(self) -> Optional[str]:
        """The env var this deployment's key comes from, or None if the key
        is inline -- which is the committed-credential case."""
        if self.api_key.startswith(ENV_PREFIX):
            return self.api_key[len(ENV_PREFIX):]
        return None


def deployments() -> List[Deployment]:
    config = load_config()
    entries = config.get("model_list")
    if not isinstance(entries, list) or not entries:
        pytest.fail(
            "config.yaml declares no model_list, so the proxy has no backends."
        )

    found: List[Deployment] = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            pytest.fail(f"model_list[{position}] is not a mapping.")
        params = entry.get("litellm_params")
        if not isinstance(params, Mapping):
            pytest.fail(f"model_list[{position}] has no litellm_params mapping.")
        info = entry.get("model_info")
        found.append(
            Deployment(
                position=position,
                model_name=str(entry.get("model_name", "")),
                model=str(params.get("model", "")),
                api_key=str(params.get("api_key", "")),
                api_base=(
                    str(params["api_base"])
                    if params.get("api_base") is not None else None
                ),
                identifier=(
                    str(info.get("id"))
                    if isinstance(info, Mapping) and info.get("id") else None
                ),
            )
        )
    return found


def deployments_by_env_var() -> Dict[str, List[Deployment]]:
    """Deployments keyed by the env var they read, which is the only reliable
    join onto `quota.PROVIDERS`.

    NOT keyed by the model string: SiliconFlow and TokenRouter are both
    reached through litellm's `openai/` provider with an explicit api_base, so
    a prefix-of-the-model-string join would put them in the same bucket and
    the drift check would pass while pointing at nothing.
    """
    grouped: Dict[str, List[Deployment]] = {}
    for deployment in deployments():
        name = deployment.env_var
        if name is not None:
            grouped.setdefault(name, []).append(deployment)
    return grouped


def _walk(node: Any, path: str = "") -> Iterator[Tuple[str, Any, Any]]:
    """Every (path, key, value) in the parsed document.

    `key` is None for list elements. Used by the tests that have to assert
    something about the WHOLE file -- an rpm hidden under router_settings is
    the same invented number as one in a deployment.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            yield here, key, value
            yield from _walk(value, here)
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            here = f"{path}[{index}]"
            yield here, None, value
            yield from _walk(value, here)


def _string_leaves(node: Any, path: str = "") -> Iterator[Tuple[str, str]]:
    for here, _key, value in _walk(node, path):
        if isinstance(value, str):
            yield here, value


def documented_env_vars() -> set:
    if not ENV_EXAMPLE_PATH.exists():
        pytest.fail(
            f"{ENV_EXAMPLE_PATH} does not exist, so there is nowhere for the "
            "gateway's environment variables to be documented."
        )
    names = set()
    for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        match = ENV_ASSIGNMENT.match(line)
        if match:
            names.add(match.group(1))
    return names


# ---------------------------------------------------------------------------
# Importing the modules someone else is writing
# ---------------------------------------------------------------------------


def _load_optional(module_name: str, *, unchecked: str) -> Any:
    """Import a module that may not exist yet.

    Skips when the module is ABSENT, saying what went unchecked. FAILS when
    the module exists and its import blows up on something else -- above all
    on litellm, which must be imported lazily inside a function. A gateway
    that cannot be imported without litellm installed is the exact defect
    these tests are for, and swallowing it as a skip would hide it.
    """
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        missing = getattr(exc, "name", None)
        if missing == module_name:
            pytest.skip(
                f"{module_name}.py does not exist yet, so THIS IS NOT BEING "
                f"CHECKED: {unchecked}"
            )
        pytest.fail(
            f"{module_name}.py exists but importing it failed on "
            f"{missing!r}: {exc}. litellm is not installed here and PyPI is "
            "unreachable, so every litellm import must be lazy -- inside the "
            "function that needs it, in a try/except ImportError that refuses "
            "with an install instruction."
        )


class _Unsuppliable(Exception):
    """A required parameter this file cannot invent a value for."""

    def __init__(self, parameter: str) -> None:
        super().__init__(parameter)
        self.parameter = parameter


#: A fixed clock, so a failure message never depends on when it ran.
NOW = 1000.0

#: Set as every provider key where a test needs keys PRESENT. Nothing here
#: asserts a key's value; the one test that uses this asserts the sentinel is
#: absent from the output.
SENTINEL_KEY = "SENTINEL-not-a-real-key-0000"

SENTINEL_ENVIRON = {p.key_env_var: SENTINEL_KEY for p in PROVIDERS}


def _argument_for(name: str, *, ledger: Ledger, streams: Dict[str, Any]) -> Any:
    """A harmless value for a parameter, chosen from its name.

    `gateway.py` and `status.py` are written separately and their signatures
    are not this file's to fix. Binding by parameter NAME rather than by
    position means a renamed or reordered argument produces a loud skip naming
    the parameter, instead of a call that passes the wrong thing and reports a
    refusal that was really a TypeError.
    """
    lowered = name.lower()
    if lowered == "argv":
        # A CLI entry point called with no argv reads sys.argv, which under
        # pytest is pytest's own command line. Hand it an empty one.
        return []
    if lowered in ("stdout", "stderr"):
        return streams.setdefault(lowered, io.StringIO())
    if lowered in ("environ", "env"):
        return dict(SENTINEL_ENVIRON)
    if "ledger" in lowered or lowered == "book":
        return ledger
    if lowered == "standings":
        return list(ledger.order(now=NOW))
    if lowered == "now":
        return NOW
    if "message" in lowered:
        return [{"role": "user", "content": "hexokinase michaelis menten"}]
    if any(word in lowered for word in ("prompt", "text", "query", "content")):
        return "hexokinase michaelis menten"
    if "config" in lowered or "path" in lowered:
        return str(CONFIG_PATH)
    if "model" in lowered:
        return "terrium-extract"
    raise _Unsuppliable(name)


def _bind(function: Callable[..., Any], *, ledger: Ledger) -> Tuple[list, dict, dict]:
    """Arguments for `function`, supplying every REQUIRED parameter.

    Optional parameters are supplied only when they are the ones that decide
    whether the call touches the process: argv, the streams, the environment
    and the clock. A `transport` is deliberately left at its default so no
    test here can make a network call.
    """
    streams: Dict[str, Any] = {}
    positional: list = []
    keyword: dict = {}
    for name, parameter in inspect.signature(function).parameters.items():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        required = parameter.default is inspect.Parameter.empty
        controls_the_process = name.lower() in (
            "argv", "stdout", "stderr", "environ", "env", "now"
        )
        if not required and not controls_the_process:
            continue
        value = _argument_for(name, ledger=ledger, streams=streams)
        if parameter.kind is parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keyword[name] = value
    return positional, keyword, streams


def _assert_refuses_with_install_instruction(
    function: Callable[..., Any], *, label: str
) -> None:
    try:
        positional, keyword, _streams = _bind(
            function, ledger=Ledger(environ=dict(SENTINEL_ENVIRON))
        )
    except _Unsuppliable as exc:
        pytest.skip(
            f"cannot supply {label}'s required parameter {exc.parameter!r}, so "
            "THIS IS NOT BEING CHECKED: that it refuses with an install "
            "instruction when litellm is absent"
        )
    with pytest.raises(Exception) as caught:
        function(*positional, **keyword)
    message = str(caught.value).lower()
    assert "litellm" in message, (
        f"{label} failed without litellm installed and the error does not "
        f"mention litellm, so an operator cannot tell what is wrong: "
        f"{caught.value!r}"
    )
    assert "install" in message, (
        f"{label} failed without litellm installed and the error does not say "
        "how to install it. The rule is refuse with an install instruction, "
        f"not raise a bare ImportError. Got: {caught.value!r}"
    )


# ---------------------------------------------------------------------------
# config.yaml: no committed credential
# ---------------------------------------------------------------------------


class TestConfigCommitsNoCredential:
    """`config.yaml` is tracked. An inline key in it is a published key.

    All five accounts are the same account -- admin.terrium@gmail.com -- so a
    single leaked key is not one provider's problem, and rotating it means
    rotating the whole waterfall.
    """

    def test_config_is_valid_yaml(self) -> None:
        config = load_config()
        assert "model_list" in config
        assert isinstance(config["model_list"], list)

    def test_every_deployment_reads_its_key_from_the_environment(self) -> None:
        inline = [
            (d.position, d.model) for d in deployments()
            if not d.api_key.startswith(ENV_PREFIX)
        ]
        assert not inline, (
            "these deployments do not use os.environ/NAME for api_key, so "
            f"whatever is there is committed: {inline}"
        )

    def test_every_referenced_env_var_is_named_like_one(self) -> None:
        # `os.environ/ gsk_abc` would satisfy the prefix and still be a key.
        for deployment in deployments():
            name = deployment.env_var
            assert name and re.fullmatch(r"[A-Z][A-Z0-9_]*", name), (
                f"model_list[{deployment.position}] api_key is "
                f"{deployment.api_key!r}, which is not os.environ/ plus an "
                "environment variable name"
            )

    def test_no_value_in_the_file_carries_a_provider_key_prefix(self) -> None:
        """Checked over every string in the document, not just api_key.

        A key pasted into `api_base`, into an `extra_headers` block, or into a
        second `model_list` entry is committed just the same, and only the
        first of those is somewhere anyone would look.
        """
        offenders = [
            (path, value[:6] + "...")
            for path, value in _string_leaves(load_config())
            if value.startswith(KEY_PREFIXES)
        ]
        assert not offenders, f"values look like provider keys: {offenders}"

    def test_no_value_in_the_file_looks_like_an_opaque_token(self) -> None:
        offenders = [
            (path, f"{len(value)} chars")
            for path, value in _string_leaves(load_config())
            if OPAQUE_TOKEN.fullmatch(value)
        ]
        assert not offenders, (
            "these values are long unbroken alphanumeric strings, which is "
            f"what a pasted secret looks like: {offenders}"
        )

    def test_the_master_key_is_read_from_the_environment_with_no_default(self) -> None:
        """A master key with a default is a master key everybody has.

        The proxy stands in front of five upstream accounts. An open port on a
        laptop with a guessable key is an open relay to all of them.
        """
        general = load_config().get("general_settings")
        assert isinstance(general, Mapping), "config.yaml declares no general_settings"
        master_key = general.get("master_key")
        assert isinstance(master_key, str) and master_key.startswith(ENV_PREFIX), (
            f"master_key must be {ENV_PREFIX}NAME with no literal fallback, got "
            f"{master_key!r}"
        )
        assert master_key[len(ENV_PREFIX):], "master_key names no environment variable"

    def test_every_env_var_the_config_references_is_documented(self) -> None:
        """An undocumented var is a gateway that starts and cannot reach a
        provider, with nothing to tell the operator which key is missing."""
        referenced = set(ENV_REFERENCE.findall(config_text()))
        assert referenced, "config.yaml references no environment variables at all"
        undocumented = sorted(referenced - documented_env_vars())
        assert not undocumented, (
            f"referenced by config.yaml and not documented in "
            f"{ENV_EXAMPLE_PATH.name}: {undocumented}"
        )

    def test_every_provider_key_variable_is_documented(self) -> None:
        documented = documented_env_vars()
        undocumented = sorted(
            p.key_env_var for p in PROVIDERS if p.key_env_var not in documented
        )
        assert not undocumented, (
            f"named by quota.PROVIDERS and not documented in "
            f"{ENV_EXAMPLE_PATH.name}: {undocumented}"
        )


# ---------------------------------------------------------------------------
# config.yaml: no number nobody measured
# ---------------------------------------------------------------------------


class TestConfigStatesNoInventedNumber:
    """Every rate limit written here would be one nobody measured.

    It would also go stale silently -- free tiers change without notice -- and
    it would be wrong in the worst direction, the proxy believing it has
    headroom it does not. litellm learns the limit the only reliable way, by
    being told 429; `quota.py` records what the provider said alongside it.
    """

    def test_no_deployment_declares_rpm_or_tpm(self) -> None:
        offenders = [
            (path, value)
            for path, key, value in _walk(load_config())
            if isinstance(key, str) and key.lower() in {"rpm", "tpm"}
        ]
        assert not offenders, (
            "rpm/tpm are numbers nobody here measured and they are wrong in "
            f"the worst direction when stale: {offenders}"
        )

    def test_no_deployment_declares_a_price(self) -> None:
        """`quota.py` orders priced providers by a cost the OPERATOR declares.
        A price written into this file competes with that while looking
        authoritative, and every free tier here costs zero anyway.
        """
        offenders = [
            (path, value)
            for path, key, value in _walk(load_config())
            if isinstance(key, str)
            and ("cost" in key.lower() or "price" in key.lower())
        ]
        assert not offenders, f"config.yaml declares a price: {offenders}"

    def test_the_routing_strategy_does_not_need_limits_the_file_withholds(self) -> None:
        """usage- and cost-based routing rank deployments by declared limits or
        prices. This file declares neither, on purpose, so selecting one of
        those strategies would either do nothing or rank by defaults nobody
        measured -- and it would compete with `quota.py`'s live ordering.
        """
        settings = load_config().get("router_settings")
        assert isinstance(settings, Mapping), "config.yaml declares no router_settings"
        strategy = str(settings.get("routing_strategy", ""))
        needs_numbers = {
            "usage-based-routing",
            "usage-based-routing-v2",
            "cost-based-routing",
            "lowest-cost",
        }
        assert strategy not in needs_numbers, (
            f"routing_strategy {strategy!r} ranks deployments by limits or "
            "prices that this file deliberately does not declare"
        )

    def test_a_known_429_does_not_spend_the_retry_budget(self) -> None:
        """Being out of quota is the system working as designed. Retrying into
        it costs a round trip and the retries the NEXT provider needs, and the
        next provider is free.
        """
        settings = load_config().get("litellm_settings")
        assert isinstance(settings, Mapping), "config.yaml declares no litellm_settings"
        policy = settings.get("retry_policy")
        assert isinstance(policy, Mapping), (
            "config.yaml declares no retry_policy, so a 429 gets the same "
            "num_retries as a 500"
        )
        assert policy.get("RateLimitErrorRetries") == 0, (
            "RateLimitErrorRetries must be 0: a 429 means move on, not try "
            f"again. Got {policy.get('RateLimitErrorRetries')!r}"
        )

    def test_an_auth_failure_is_not_retried_either(self) -> None:
        # A rotated or missing key does not fix itself between attempts, and
        # this is the failure a new provider is most likely to have.
        policy = load_config()["litellm_settings"]["retry_policy"]
        assert policy.get("AuthenticationErrorRetries") == 0, (
            "a bad key does not become good on retry; got "
            f"{policy.get('AuthenticationErrorRetries')!r}"
        )

    def test_prompts_and_responses_are_never_logged(self) -> None:
        """Terrium's queries can contain a researcher's unpublished subject.

        A gateway that wrote them to disk would be a disclosure the rest of
        the project is careful to avoid, and it would be one nobody noticed
        because the gateway would keep working.
        """
        settings = load_config()["litellm_settings"]
        logging_off = settings.get("turn_off_message_logging")
        assert logging_off is True, (
            "turn_off_message_logging must be the boolean true, got "
            f"{logging_off!r} ({type(logging_off).__name__})"
        )

    def test_the_file_still_says_why_it_holds_no_limits(self) -> None:
        # The rationale is the thing that stops the next person adding rpm.
        text = config_text()
        assert "NO RATE LIMIT IS WRITTEN IN THIS FILE" in text
        assert "ADR 0011" in text
        assert "parameter" in text


# ---------------------------------------------------------------------------
# The drift that nothing else catches
# ---------------------------------------------------------------------------


class TestQuotaAndConfigDescribeTheSameWaterfall:
    """`quota.py` decides an order; `config.yaml` is what gets called.

    Nothing structural ties them together: the ledger holds five `Provider`
    records and the proxy holds five deployments, and they are matched only by
    someone having typed the same thing twice. Drift does not raise. The
    gateway keeps answering while the ledger's accounting describes a provider
    or a model that is not being used, and every number the status output
    prints is then about the wrong thing.

    All five keys belong to one account, admin.terrium@gmail.com.
    """

    def test_every_provider_in_the_waterfall_has_a_deployment(self) -> None:
        available = deployments_by_env_var()
        missing = sorted(
            f"{p.name} ({p.key_env_var})"
            for p in PROVIDERS if p.key_env_var not in available
        )
        assert not missing, (
            "quota.py orders these providers and config.yaml has no deployment "
            f"for them, so the waterfall names a provider the proxy cannot "
            f"reach: {missing}"
        )

    def test_every_deployment_is_a_provider_the_waterfall_knows(self) -> None:
        known = {p.key_env_var for p in PROVIDERS}
        extra = sorted(
            f"model_list[{d.position}] {d.model} ({d.env_var})"
            for d in deployments()
            if d.env_var not in known
        )
        assert not extra, (
            "config.yaml declares these deployments and quota.py has no "
            "Provider for them, so they are called and never accounted for -- "
            f"no headroom read, no exhaustion recorded: {extra}"
        )

    def test_no_provider_has_two_deployments(self) -> None:
        """Two backends behind one provider name would make the ledger's
        counters ambiguous: one 429 recorded against `groq` could have come
        from either, and the reset time read from one would rest both.
        """
        doubled = {
            name: [d.model for d in found]
            for name, found in deployments_by_env_var().items()
            if len(found) > 1
        }
        assert not doubled, f"more than one deployment per provider key: {doubled}"

    def test_the_model_string_is_the_same_on_both_sides(self) -> None:
        """THE CONTRACT. `Provider.model` is what the ledger records against;
        the deployment's `model` is what litellm calls.

        When they disagree nothing fails. The ledger reads Groq's headers and
        files them under `groq/llama-3.3-70b-versatile` while the proxy calls
        some other Groq model with its own separate budget, so the headroom
        accounting is silently about the wrong thing and the ordering is made
        from figures that do not describe the calls being sent.
        """
        available = deployments_by_env_var()
        mismatched = []
        for provider in PROVIDERS:
            found = available.get(provider.key_env_var)
            if not found:
                continue  # covered by the missing-deployment test
            deployed = found[0].model
            if deployed != provider.model:
                mismatched.append(
                    f"{provider.name}: quota.py says {provider.model!r}, "
                    f"config.yaml calls {deployed!r}"
                )
        assert not mismatched, (
            "the ledger records headroom against one model while the proxy "
            f"calls another: {mismatched}"
        )

    def test_every_deployment_answers_to_one_model_name(self) -> None:
        """litellm fails over between deployments that share a `model_name`.

        A typo in one entry's name does not error -- that provider simply
        drops out of the chain, and the waterfall is four deep instead of five
        with nothing to say so.
        """
        names = {d.model_name for d in deployments()}
        assert len(names) == 1, (
            "deployments must share one model_name or they are not one "
            f"logical model and do not fail over: {sorted(names)}"
        )
        only = names.pop()
        assert only, "model_name is empty"

    def test_the_fallback_list_names_a_model_that_exists(self) -> None:
        declared = {d.model_name for d in deployments()}
        fallbacks = load_config()["litellm_settings"].get("fallbacks")
        assert isinstance(fallbacks, list) and fallbacks, (
            "config.yaml declares no fallbacks, so the chain is implicit in "
            "file order"
        )
        referenced = set()
        for entry in fallbacks:
            if not isinstance(entry, Mapping):
                pytest.fail(f"fallbacks entry is not a mapping: {entry!r}")
            for key, value in entry.items():
                referenced.add(str(key))
                for target in value or []:
                    referenced.add(str(target))
        unknown = sorted(referenced - declared)
        assert not unknown, (
            f"fallbacks names models no deployment answers to: {unknown}. "
            "A typo here disables fallback silently."
        )

    def test_deployment_identifiers_are_distinct(self) -> None:
        # litellm's cooldowns and failure counts are per deployment id. Two
        # providers sharing an id would rest each other.
        identifiers = [d.identifier for d in deployments()]
        assert all(identifiers), (
            "every deployment needs model_info.id so a failure can be "
            f"attributed to one provider: {identifiers}"
        )
        assert len(set(identifiers)) == len(identifiers), (
            f"duplicate model_info.id: {identifiers}"
        )

    def test_openai_compatible_providers_declare_their_own_api_base(self) -> None:
        """SiliconFlow and TokenRouter are reached through litellm's `openai/`
        provider. Without an explicit `api_base` the call goes to
        api.openai.com carrying a SiliconFlow key -- a 401 from a provider
        that is up, attributed to the wrong host, on a line that looks right.
        """
        for deployment in deployments():
            if not deployment.model.startswith("openai/"):
                continue
            base = deployment.api_base
            assert base, (
                f"model_list[{deployment.position}] uses {deployment.model!r} "
                "with no api_base, so the request goes to OpenAI with another "
                "provider's key"
            )
            assert base.startswith("https://"), (
                f"api_base {base!r} is not https, so the key travels in clear"
            )
            assert "api.openai.com" not in base, (
                f"{deployment.env_var} points at OpenAI: {base!r}"
            )

    def test_the_live_chain_only_names_providers_the_proxy_can_reach(self) -> None:
        """The runtime form of the drift check.

        `chain()` is what a caller hands to litellm. A name in it with no
        deployment is a fallback target that does not exist.
        """
        environ = {p.key_env_var: "SENTINEL-not-a-real-key-0000" for p in PROVIDERS}
        ledger = Ledger(environ=environ)
        reachable = {
            PROVIDERS_BY_NAME[p.name].name
            for p in PROVIDERS
            if p.key_env_var in deployments_by_env_var()
        }
        chain = ledger.chain(now=1000.0)
        assert chain, "the ledger produced an empty chain with every key set"
        unreachable = sorted(set(chain) - reachable)
        assert not unreachable, (
            f"chain() offers providers config.yaml cannot call: {unreachable}"
        )

    def test_the_next_provider_chosen_has_a_deployment(self) -> None:
        environ = {p.key_env_var: "SENTINEL-not-a-real-key-0000" for p in PROVIDERS}
        chosen = Ledger(environ=environ).next_provider(now=1000.0)
        assert chosen.key_env_var in deployments_by_env_var(), (
            f"the ledger chose {chosen.name}, which config.yaml has no "
            "deployment for"
        )

    def test_a_provider_with_no_key_is_still_a_deployment(self) -> None:
        """A missing key is an ABSENT provider, not a reason to delete its
        deployment. Deleting it is how the two files drift: the ledger keeps
        ordering a provider the proxy no longer has.
        """
        environ = {p.key_env_var: "SENTINEL-not-a-real-key-0000" for p in PROVIDERS}
        environ.pop("MISTRAL_API_KEY", None)
        ledger = Ledger(environ=environ)
        standings = {s.provider.name: s.availability for s in ledger.order(now=1000.0)}
        assert standings["mistral"] == quota.ABSENT
        assert "MISTRAL_API_KEY" in deployments_by_env_var()


# ---------------------------------------------------------------------------
# gateway.py -- imported lazily, skipped loudly
# ---------------------------------------------------------------------------


GATEWAY_UNCHECKED = (
    "that the gateway imports without litellm installed, and that "
    "build_router/complete refuse with an install instruction instead of "
    "raising a bare ImportError"
)


class TestTheGatewayWorksWithoutLitellm:
    """litellm is not installed here and PyPI is unreachable.

    So the only path these tests can exercise is the refusal, and the refusal
    is worth exercising: it is what an operator meets first. A bare
    ModuleNotFoundError from deep inside a call tells them nothing; an error
    naming litellm and the install command tells them everything.

    None of these tests assert that a request succeeds. That cannot be tested
    from this sandbox and is not claimed.
    """

    def test_the_gateway_imports_without_litellm_installed(self) -> None:
        had_litellm = "litellm" in sys.modules
        module = _load_optional("gateway", unchecked=GATEWAY_UNCHECKED)
        assert module is not None
        if not had_litellm:
            assert "litellm" not in sys.modules, (
                "importing gateway.py imported litellm at module scope. It "
                "must be imported inside the function that needs it, so the "
                "module is usable -- and testable -- without it."
            )

    def test_build_router_refuses_with_an_install_instruction(self) -> None:
        module = _load_optional("gateway", unchecked=GATEWAY_UNCHECKED)
        build_router = getattr(module, "build_router", None)
        if not callable(build_router):
            pytest.skip(
                "gateway.py defines no callable build_router, so THIS IS NOT "
                "BEING CHECKED: that building a router without litellm "
                "refuses with an install instruction"
            )
        _assert_refuses_with_install_instruction(build_router, label="build_router")

    def test_complete_refuses_with_an_install_instruction(self) -> None:
        module = _load_optional("gateway", unchecked=GATEWAY_UNCHECKED)
        complete = getattr(module, "complete", None)
        if not callable(complete):
            pytest.skip(
                "gateway.py defines no callable complete, so THIS IS NOT "
                "BEING CHECKED: that completing without litellm refuses with "
                "an install instruction rather than raising ImportError"
            )
        _assert_refuses_with_install_instruction(complete, label="complete")

    def test_the_gateway_points_at_this_config(self) -> None:
        """A gateway that reads a different config.yaml makes every check in
        this file about a file nobody uses."""
        module = _load_optional("gateway", unchecked=GATEWAY_UNCHECKED)
        for attribute in ("CONFIG_PATH", "DEFAULT_CONFIG_PATH", "CONFIG"):
            value = getattr(module, attribute, None)
            if value is None:
                continue
            resolved = Path(str(value)).resolve()
            assert resolved == CONFIG_PATH, (
                f"gateway.{attribute} is {resolved}, not the config.yaml these "
                f"tests check ({CONFIG_PATH})"
            )
            return
        pytest.skip(
            "gateway.py names no config path attribute (CONFIG_PATH / "
            "DEFAULT_CONFIG_PATH / CONFIG), so THIS IS NOT BEING CHECKED: "
            "that the gateway loads the config.yaml this file validates"
        )

    def test_the_gateway_supplies_no_parameter_values(self) -> None:
        """ADR 0011 hard-blocks origin `llm`.

        The gateway is for entity extraction and domain classification. It is
        not a source of parameter VALUES: a Km that came out of a language
        model is not a measurement, and labelling one `default` was the defect
        ADR 0011 exists to fix. This checks only that the module does not
        ANNOUNCE itself as a parameter source -- it cannot prove a negative
        about what a caller does with the text that comes back.
        """
        module = _load_optional("gateway", unchecked=GATEWAY_UNCHECKED)
        source_path = getattr(module, "__file__", None)
        if not source_path:
            pytest.skip(
                "gateway module has no __file__, so THIS IS NOT BEING "
                "CHECKED: that it declares no parameter-value origin"
            )
        source = Path(source_path).read_text(encoding="utf-8")
        for forbidden in ('origin="llm"', "origin='llm'", '"origin": "llm"'):
            assert forbidden not in source, (
                f"gateway.py contains {forbidden!r}. ADR 0011 blocks origin "
                "'llm' at the resolver; the gateway must not mint one."
            )


# ---------------------------------------------------------------------------
# status.py -- imported lazily, skipped loudly
# ---------------------------------------------------------------------------


STATUS_UNCHECKED = (
    "that a status render never prints a key VALUE, and never calls a "
    "provider that reported nothing AVAILABLE"
)

#: Renderers in the order they are preferred. A pure text function is tried
#: before the CLI entry point, because the CLI may exit rather than return.
STATUS_RENDERERS = (
    "human_report", "render", "report", "status_text", "summary", "describe", "main",
)


def _render_status(module: Any) -> str:
    """Whatever this module calls its renderer, as text.

    Probed rather than hardcoded, so a rename does not quietly drop the
    key-leak check: if nothing can be called, the test SKIPS with a message
    saying which check did not run. Output is collected from the return value
    and from any stream the renderer was handed, and nothing is read from the
    real stdout -- a renderer that writes to the terminal instead of a stream
    it was given is still captured by pytest, so `capsys` is folded in by the
    caller.
    """
    ledger = Ledger(environ=dict(SENTINEL_ENVIRON))
    attempted: List[str] = []
    for name in STATUS_RENDERERS:
        function = getattr(module, name, None)
        if not callable(function):
            continue
        try:
            positional, keyword, streams = _bind(function, ledger=ledger)
        except _Unsuppliable as exc:
            attempted.append(f"{name} (cannot supply {exc.parameter!r})")
            continue
        try:
            returned = function(*positional, **keyword)
        except (TypeError, SystemExit) as exc:
            attempted.append(f"{name} ({type(exc).__name__}: {exc})")
            continue
        text = returned if isinstance(returned, str) else ""
        for stream in streams.values():
            text += stream.getvalue()
        if text.strip():
            return text
        attempted.append(f"{name} (returned and wrote nothing)")
    pytest.skip(
        "status.py exposes no renderer this file can call -- tried "
        f"{attempted or list(STATUS_RENDERERS)} -- so THIS IS NOT BEING "
        f"CHECKED: {STATUS_UNCHECKED}"
    )


class TestStatusTellsTheTruthAndKeepsTheKeys:
    """The status output is what an operator pastes into an issue.

    So it has two obligations that nothing else in the gateway has: it must
    not contain a key value, and it must not round UNKNOWN up to available.
    Both are checked against a ledger with every key set to a sentinel and
    nothing recorded, which is the state a fresh gateway is actually in.
    """

    def test_status_never_prints_a_key_value(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        module = _load_optional("status", unchecked=STATUS_UNCHECKED)
        # Both paths covered: a renderer handed an environ, and one reading
        # os.environ itself.
        for provider in PROVIDERS:
            monkeypatch.setenv(provider.key_env_var, SENTINEL_KEY)
        monkeypatch.setenv("LITELLM_MASTER_KEY", SENTINEL_KEY)

        text = _render_status(module) + capsys.readouterr().out
        assert SENTINEL_KEY not in text, (
            "the status output contains the VALUE of an API key. It may name "
            "the environment variable -- that is useful -- but never what is "
            "in it."
        )

    def test_status_does_not_call_an_unreported_provider_available(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        """With every key set and nothing recorded, every provider is UNKNOWN.

        A status page that renders that as available is the exact confusion
        the three states exist to prevent: it would be most confident about
        the providers it knows least about. This asserts the word is there,
        not the layout -- the wording is status.py's to choose.
        """
        module = _load_optional("status", unchecked=STATUS_UNCHECKED)
        for provider in PROVIDERS:
            monkeypatch.setenv(provider.key_env_var, SENTINEL_KEY)

        text = (_render_status(module) + capsys.readouterr().out).lower()
        assert "unknown" in text, (
            "no provider has reported anything, so every one of them is "
            "UNKNOWN -- the output has to say so rather than implying they "
            f"are fine. Got: {text[:400]!r}"
        )

    def test_status_names_every_provider_the_config_declares(
        self, monkeypatch: pytest.MonkeyPatch, capsys: Any
    ) -> None:
        """A provider missing from the status output is a provider nobody
        notices has stopped working."""
        module = _load_optional("status", unchecked=STATUS_UNCHECKED)
        for provider in PROVIDERS:
            monkeypatch.setenv(provider.key_env_var, SENTINEL_KEY)

        text = (_render_status(module) + capsys.readouterr().out).lower()
        missing = [
            p.name for p in PROVIDERS
            if p.key_env_var in deployments_by_env_var() and p.name not in text
        ]
        assert not missing, (
            f"deployed providers absent from the status output: {missing}"
        )
