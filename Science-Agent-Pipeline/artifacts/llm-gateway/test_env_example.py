"""What a committed .env.example is allowed to contain, asserted rather than hoped.

WHY THIS FILE EXISTS
--------------------
`.env.example` is tracked. `.env` is not -- Science-Agent-Pipeline/.gitignore
lines 64-66 ignore it and line 67 (`!.env.example`) carves the template back
out. That carve-out is load-bearing and it is also a loaded gun: the one file
in the pair that a reviewer skims is the one that ships to the public remote.
A key pasted into it is a key published, and free-tier keys are drained off
GitHub within the hour.

Two things can go wrong and neither is caught by any other test:

1. A real key gets pasted in. Nothing about the file looks different
   afterwards -- it is still a list of NAME=value lines -- so review does not
   reliably catch it. A shape check does.

2. A variable quietly disappears in a rewrite. A dropped variable is not a
   broken build; it is a server nobody can configure, discovered by whoever
   next needs to set it and cannot find out that it exists.

WHAT THIS DOES NOT CLAIM
------------------------
It is not a secret scanner. It knows four shapes -- `gsk_`, `sk-`, `sk-or-`,
and a long opaque run of base64-ish characters -- and a credential in some
other shape (a bare hex token, a password, a JWT body) passes. The point is
not exhaustive detection; it is that the shapes THIS repository's five
providers actually hand out cannot land in a tracked file unnoticed. Use a
real pre-commit secret scanner as well, not instead.

It also does not check `.env` itself, which is the file that holds the real
keys. Nothing here reads it, on purpose.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

#: Repository root: this file is at
#: <root>/Science-Agent-Pipeline/artifacts/llm-gateway/test_env_example.py
REPO_ROOT = Path(__file__).resolve().parents[3]

API_SERVER_ENV_EXAMPLE = (
    REPO_ROOT / "Science-Agent-Pipeline" / "artifacts" / "api-server" / ".env.example"
)

#: Every tracked .env.example at the time this test was written. MEASURED with
#: `git ls-files | grep -i env.example` from the repository root -- not assumed,
#: and not a guess at which packages have one. It is asserted separately below
#: so that a broken file listing fails loudly instead of vacuously passing.
KNOWN_ENV_EXAMPLES = (
    "Science-Agent-Pipeline/.env.example",
    "Science-Agent-Pipeline/artifacts/api-server/.env.example",
    "caterva-site/.env.example",
)

#: Variable names present in api-server/.env.example BEFORE the 2026-09-13
#: rewrite of that file.
#:
#: MEASURED, NOT ASSUMED. Extracted from the pre-edit file with
#:
#:     grep -E '^[A-Za-z_][A-Za-z0-9_]*=' .env.example | sed 's/=.*//' | sort
#:
#: which yielded exactly these 21 names, and cross-checked against
#: `git show HEAD:Science-Agent-Pipeline/artifacts/api-server/.env.example`
#: piped through the same command -- identical output. The list is hardcoded
#: rather than recomputed from git because the git baseline moves: once this
#: change is committed, HEAD is the new file and a git-derived "before" list
#: would compare the file to itself and always pass.
#:
#: A name may be ADDED to the file freely. Removing one is what this guards,
#: because an undocumented variable is an unconfigurable server: the reader
#: has no way to learn it exists short of grepping process.env in TypeScript.
VARIABLES_BEFORE_REWRITE = (
    "CACHE_FILE",
    "GROQ_API_KEY",
    "LLM_API_KEY",
    "LLM_API_URL",
    "LLM_FORCE_JSON",
    "LLM_MODEL",
    "LLM_PROVIDER",
    "LOG_LEVEL",
    "METRICS_ADMIN_TOKEN",
    "MISTRAL_API_KEY",
    "NODE_ENV",
    "OPENAI_API_KEY",
    "OPENAI_API_URL",
    "OPENAI_MODEL",
    "OPENROUTER_API_KEY",
    "PORT",
    "SILICONFLOW_API_KEY",
    "CATERVA_PYTHON",
    "TOKENROUTER_API_KEY",
    "VIRTUAL_ENV",
    "WAITLIST_FILE",
)

ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

#: Prefixes the providers in this repository actually issue. Groq documents
#: `gsk_`; OpenAI and OpenRouter both use `sk-` forms. The trailing length
#: requirement is what separates a pasted key from prose ABOUT keys: a comment
#: may say "a Groq key starts with gsk_", and must be able to, or the file
#: cannot explain what it is protecting against.
KEY_PREFIXES = (
    re.compile(r"gsk_[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bsk-or-v1-[A-Za-z0-9]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
)

#: A long unbroken run of base64/base64url characters with no separator. Real
#: tokens look like this; hostnames, paths and prose do not, because they
#: contain `.`, `/`, or spaces well before 32 characters.
OPAQUE_BLOB = re.compile(r"[A-Za-z0-9+/=_\-]{32,}")

#: Placeholders that read like a value someone might leave in place. The old
#: api-server file shipped `your-groq-key-here`, `your-secure-random-token-here`
#: and `/path/to/cache.json`; the first two resemble credentials closely enough
#: to be mistaken for live config, and the third is an override that breaks the
#: default it replaces.
FAKE_PLACEHOLDER = re.compile(
    r"(your[-_].*|.*[-_]here|/path/to/.*|https?://api\.example\.com.*)", re.I
)


def tracked_env_examples() -> list[Path]:
    """Every tracked file named `.env.example`, from git rather than a glob.

    From git because "tracked" is the property that matters: an untracked
    scratch copy holding a real key is a local mistake, while a tracked one is
    a publication. Asking git also means a NEW .env.example added to some
    future package is covered on the day it lands, without anyone remembering
    to extend a list here.

    Falls back to walking the tree when git is unavailable, which keeps the
    shape checks running in an exported copy of the source. The fallback is
    narrower, not broader -- it cannot tell tracked from untracked -- so
    `test_the_known_env_examples_are_all_found` exists to fail if either path
    returns nothing.
    """
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z", "*.env.example", ".env.example"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout
        paths = [REPO_ROOT / name for name in listing.split("\0") if name]
        if paths:
            return sorted(paths)
    except (OSError, subprocess.SubprocessError):
        pass

    skip = {".git", "node_modules", ".venv", "dist", "__pycache__"}
    return sorted(
        path
        for path in REPO_ROOT.rglob(".env.example")
        if not skip & set(path.relative_to(REPO_ROOT).parts)
    )


def assignments(text: str) -> list[tuple[int, str, str]]:
    """(line number, name, raw value) for every NAME=value line.

    Comment lines are excluded because a comment is where the file argues for
    itself, and the value side is where a leaked credential would actually
    sit. The prefix checks still sweep the whole file -- see
    `credential_shapes_in`.
    """
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ASSIGNMENT.match(stripped)
        if match:
            found.append((number, match.group(1), match.group(2).strip()))
    return found


def looks_like_a_credential(value: str) -> bool:
    """Whether a VALUE is shaped like a live key.

    Empty is fine, and is what almost every value in these files is. Short
    words (`3000`, `info`, `development`), URLs, and filesystem paths are
    fine. What is not fine is a provider key prefix, or 32+ characters of
    unbroken opaque token.
    """
    if not value:
        return False
    unquoted = value.strip().strip("\"'")
    if not unquoted:
        return False
    if any(pattern.search(unquoted) for pattern in KEY_PREFIXES):
        return True
    return bool(OPAQUE_BLOB.fullmatch(unquoted))


def credential_shapes_in(text: str) -> list[str]:
    """Provider-key prefixes found ANYWHERE in the text, comments included.

    A key pasted into a comment is published exactly as thoroughly as one
    pasted into a value, so this half of the check does not respect the
    value-side scoping. It is limited to the prefix patterns, whose length
    requirement lets the file still name `gsk_` and `sk-` as shapes in prose.
    """
    return [
        match.group(0)
        for pattern in KEY_PREFIXES
        for match in pattern.finditer(text)
    ]


class TestTheCredentialShapeDetector:
    """The detector is tested on both sides before it is trusted on the repo.

    A shape check that cannot fail is decoration. These cases are synthetic
    and assembled from repeated characters on purpose -- no real key, and
    nothing in this file that resembles one closely enough to alarm a scanner.
    """

    @pytest.mark.parametrize(
        "value",
        [
            "gsk_" + "a" * 52,
            "sk-" + "B" * 48,
            "sk-or-v1-" + "c" * 64,
            "d4" * 24,
            "Zm9vYmFy" * 5,
        ],
    )
    def test_key_shaped_values_are_caught(self, value: str) -> None:
        assert looks_like_a_credential(value)

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "3000",
            "development",
            "info",
            "caterva-extract",
            "http://127.0.0.1:4000/v1/chat/completions",
            "https://api.openai.com/v1/chat/completions",
            "/usr/bin/python3.12",
            "gpt-4o-mini",
            "true",
        ],
    )
    def test_legitimate_values_are_not_caught(self, value: str) -> None:
        # Every one of these is a value one of the three tracked files either
        # ships now or shipped before. A check that flagged them would be
        # turned off within a week.
        assert not looks_like_a_credential(value)

    def test_a_quoted_key_is_still_a_key(self) -> None:
        assert looks_like_a_credential('"gsk_' + "e" * 52 + '"')

    def test_prose_may_name_a_prefix_without_tripping_the_scan(self) -> None:
        # The file has to be able to explain what it is protecting against.
        assert credential_shapes_in("a Groq key begins with gsk_ and OpenAI's with sk-") == []

    def test_a_key_pasted_into_a_comment_is_caught(self) -> None:
        pasted = "# GROQ_API_KEY=gsk_" + "f" * 52
        assert credential_shapes_in(pasted)


class TestNoTrackedEnvExampleHoldsACredential:
    """The check this file exists for."""

    def test_the_known_env_examples_are_all_found(self) -> None:
        """Guards the enumeration itself.

        Without this, a `git ls-files` that returned nothing would make every
        other test in the class pass over an empty list.
        """
        found = {
            str(path.relative_to(REPO_ROOT)) for path in tracked_env_examples()
        }
        missing = set(KNOWN_ENV_EXAMPLES) - found
        assert not missing, f"env.example files not enumerated: {sorted(missing)}"

    def test_no_assigned_value_is_key_shaped(self) -> None:
        offenders = []
        for path in tracked_env_examples():
            text = path.read_text(encoding="utf-8")
            for number, name, value in assignments(text):
                if looks_like_a_credential(value):
                    # Report the variable and line, never the value.
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{number} {name}")
        assert not offenders, (
            "a tracked .env.example holds something shaped like a real key; "
            f"rotate it, then empty it: {offenders}"
        )

    def test_no_key_prefix_appears_anywhere_including_comments(self) -> None:
        offenders = []
        for path in tracked_env_examples():
            if credential_shapes_in(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(REPO_ROOT)))
        assert not offenders, f"provider key prefix with a key-length tail in: {offenders}"

    def test_no_value_is_a_fake_looking_placeholder(self) -> None:
        """`your-groq-key-here` is not a key, but it is a key-shaped hole.

        It reads like live config in a diff, it teaches the next person that
        populated values are normal in this file, and for CATERVA_PYTHON and
        CACHE_FILE a populated placeholder actively overrides a working
        default. Empty says "unset" without ambiguity.
        """
        offenders = []
        for path in tracked_env_examples():
            for number, name, value in assignments(path.read_text(encoding="utf-8")):
                if value and FAKE_PLACEHOLDER.fullmatch(value.strip("\"'")):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{number} {name}={value}"
                    )
        assert not offenders, f"placeholder values should be empty: {offenders}"


class TestEveryVariableSurvivedTheRewrite:
    """A dropped variable is a silently unconfigurable server.

    Nothing fails at startup when a variable stops being documented. The
    server keeps reading process.env; only the reader loses. That failure mode
    is invisible to every other test in this repository, which is why the
    pre-rewrite list is pinned here.
    """

    def test_the_file_is_where_this_test_expects(self) -> None:
        assert API_SERVER_ENV_EXAMPLE.is_file(), API_SERVER_ENV_EXAMPLE

    def test_no_documented_variable_was_dropped(self) -> None:
        present = {
            name
            for _, name, _ in assignments(
                API_SERVER_ENV_EXAMPLE.read_text(encoding="utf-8")
            )
        }
        missing = sorted(set(VARIABLES_BEFORE_REWRITE) - present)
        assert not missing, (
            "variables documented before the rewrite are gone, so nobody can "
            f"discover them: {missing}"
        )

    def test_each_survivor_is_a_real_assignment_not_only_prose(self) -> None:
        """A variable mentioned in a comment is not a variable you can set.

        The dropped-variable failure has a near miss: a rewrite that describes
        LOG_LEVEL in a paragraph but never leaves a `LOG_LEVEL=` line to
        uncomment. `assignments()` ignores comments, so this is already what
        the test above measures -- asserted separately so the intent survives
        a refactor of the helper.
        """
        lines = API_SERVER_ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        for name in VARIABLES_BEFORE_REWRITE:
            assert any(
                line.strip().startswith(f"{name}=") and not line.strip().startswith("#")
                for line in lines
            ), f"{name} is documented but has no assignable line"

    def test_the_litellm_master_key_was_added(self) -> None:
        # The one name this rewrite adds. Asserted so that "keep everything"
        # and "add the gateway wiring" are both checked, rather than the
        # addition riding along untested.
        present = {
            name
            for _, name, _ in assignments(
                API_SERVER_ENV_EXAMPLE.read_text(encoding="utf-8")
            )
        }
        assert "LITELLM_MASTER_KEY" in present


class TestTheADR0011BoundaryIsStatedWithTheKeys:
    """The boundary has to be stated where someone is about to paste a key.

    ADR 0011 is why this project can be handed to a lab: an LLM routes the
    query and extracts entities, and it never supplies a parameter VALUE. That
    is a rule about what the keys below a heading are FOR, so a mention in a
    footer is not enough -- the person adding a sixth provider is reading the
    LLM section and nothing else.
    """

    def llm_section(self) -> str:
        text = API_SERVER_ENV_EXAMPLE.read_text(encoding="utf-8")
        start = text.index("# LLM PROVIDERS")
        end = text.index("# CACHING", start)
        return text[start:end]

    def test_the_llm_section_exists_and_is_bounded(self) -> None:
        section = self.llm_section()
        assert len(section) > 500, "the LLM section is too short to state anything"

    def test_adr_0011_is_cited_in_the_llm_section(self) -> None:
        assert "ADR 0011" in self.llm_section()

    def test_the_section_says_an_llm_never_supplies_a_parameter_value(self) -> None:
        section = self.llm_section().lower()
        assert "never a source for a parameter value" in section or (
            "never" in section and "parameter value" in section
        )

    def test_the_section_records_that_the_resolver_hard_blocks_llm_origin(self) -> None:
        # The 2026-08-06 amendment is the operative half. Without it a reader
        # could conclude an llm-origin parameter is merely labelled honestly
        # and still runs.
        assert "hard-block" in self.llm_section().lower()

    def test_the_permitted_uses_are_named(self) -> None:
        section = self.llm_section().lower()
        assert "entity extraction" in section
        assert "domain classification" in section

    def test_the_adr_that_is_cited_actually_exists(self) -> None:
        # A citation to a file that is not there is the defect this whole
        # repository is about. Cheap to check, so checked.
        adr = REPO_ROOT / "docs" / "adr" / "0011-llm-parameter-origin.md"
        assert adr.is_file(), adr
        assert "hard-blocks `llm`" in adr.read_text(encoding="utf-8")


class TestTheWaterfallWiringIsDocumented:
    """The gateway is useless if nobody can find out how to point at it."""

    def env_text(self) -> str:
        return API_SERVER_ENV_EXAMPLE.read_text(encoding="utf-8")

    def test_the_proxy_address_is_given(self) -> None:
        # 127.0.0.1 and not 0.0.0.0: the proxy holds five upstream keys.
        assert "127.0.0.1:4000" in self.env_text()

    def test_the_model_name_matches_the_gateway_config(self) -> None:
        text = self.env_text()
        assert "caterva-extract" in text
        config = REPO_ROOT / "Science-Agent-Pipeline" / "artifacts" / "llm-gateway" / "config.yaml"
        # Asserted against config.yaml rather than a remembered string: the
        # name only works because every deployment there answers to it.
        assert "model_name: caterva-extract" in config.read_text(encoding="utf-8")

    def test_the_account_email_is_recorded(self) -> None:
        # A key with no known owner cannot be rotated.
        assert "admin.terrium@gmail.com" in self.env_text()
