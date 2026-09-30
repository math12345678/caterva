"""The recorded-answer variables belong to test configuration and nowhere else.

WHY THIS EXISTS
---------------
Three environment variables change where the literature layer's answers
come from:

    CATERVA_BRENDA_RECORDED   brenda_client.fetch_brenda_html returns a
                              recorded BRENDA page instead of fetching one
    CATERVA_HTTP_RECORDED     http_retry.retry_get answers a GET from a
                              recorded response instead of the network
    CATERVA_HTTP_RECORD       http_retry.retry_get writes live responses
                              to a directory

They exist so the API server's tests stop failing when NCBI, UniProt,
PubChem or BRENDA is slow or down. In the product they would be a defect of
exactly the kind Caterva exists to refuse: a value served to a user as
BRENDA's current answer that is in fact a file from the day someone ran a
recorder, with nothing in the response saying so. The recording's date is in
the fixture; it is not in the API response.

Nothing enforced that. A `.env` line, a Dockerfile `ENV`, a docker-compose
`environment:` entry or one `process.env[...] =` in server code would switch
the product to recorded answers and every test would still pass, because
the tests WANT the recordings.

WHAT IT CHECKS
--------------
Every tracked file that names one of the three variables must be one of:

  * a module that READS it (brenda_client.py, http_retry.py), and those two
    must only read it, never assign it;
  * the API server's test configuration (vitest.config.ts), which is the
    one place meant to set it, and which must go on setting both replay
    variables, or the tests are back on the network without anyone deciding
    that;
  * the recorder, scripts/record_http_fixtures.py, which sets them for the
    runner processes it spawns and for nothing else;
  * a test (test_*.py, *.test.ts, caterva/tests/), or documentation (*.md).

Naming is checked rather than setting, deliberately: "sets" has a dozen
spellings across Python, TypeScript, YAML, shell and Dockerfiles, and a
guard that tries to recognise each one misses the thirteenth. A file with no
business knowing the name fails however it uses it.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]

NAMES = ("CATERVA_BRENDA_RECORDED", "CATERVA_HTTP_RECORDED", "CATERVA_HTTP_RECORD")

#: Modules that read a variable. They may name it; they may never set it.
READERS = {
    "Tests/brenda_client.py": ("CATERVA_BRENDA_RECORDED",),
    "Tests/http_retry.py": ("CATERVA_HTTP_RECORDED", "CATERVA_HTTP_RECORD"),
}

VITEST_CONFIG = "Science-Agent-Pipeline/artifacts/api-server/vitest.config.ts"
RECORDER = "scripts/record_http_fixtures.py"

#: Test configuration and tooling allowed to set them.
SETTERS = {VITEST_CONFIG, RECORDER}

_NAME_PATTERN = re.compile(r"CATERVA_(?:BRENDA_RECORDED|HTTP_RECORDED|HTTP_RECORD)\b")

#: The ways the two reader modules could assign a variable instead of reading
#: it. Checked only in those two files, where the vocabulary is known.
_ASSIGNMENT = re.compile(
    r"os\.environ\s*\[[^\]]*\]\s*=(?!=)|os\.environ\.(?:setdefault|update)\s*\(|"
    r"os\.putenv\s*\("
)


def _tracked_files() -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.split("\n")
    return [rel for rel in listing if rel and "node_modules" not in rel]


def _is_test_or_doc(rel: str) -> bool:
    name = pathlib.PurePosixPath(rel).name
    return (
        name.startswith("test_") and name.endswith(".py")
        or name.endswith(".test.ts")
        or rel.startswith("caterva/tests/")
        or name.endswith(".md")
    )


def _files_naming_a_variable() -> dict[str, str]:
    found: dict[str, str] = {}
    for rel in _tracked_files():
        path = ROOT / rel
        try:
            if path.stat().st_size > 5_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _NAME_PATTERN.search(text):
            found[rel] = text
    return found


def test_only_readers_test_configuration_tests_and_docs_name_them() -> None:
    files = _tracked_files()
    assert len(files) > 500, (
        f"git ls-files returned {len(files)} files; the listing is broken and "
        "this test would pass without examining anything"
    )
    offenders = sorted(
        rel for rel in _files_naming_a_variable()
        if rel not in READERS and rel not in SETTERS and not _is_test_or_doc(rel)
    )
    assert not offenders, (
        f"{offenders} name a recorded-answer variable ({', '.join(NAMES)}). "
        "Only test configuration may set them: in the product they would serve "
        "a recorded answer as a current one. Tests/fixtures/recorded/README.md "
        "says where they belong."
    )


def test_the_readers_only_read() -> None:
    for rel, names in READERS.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for name in names:
            assert name in text, (
                f"{rel} no longer names {name}; if the reader moved, move it in "
                "READERS too, or this test stops watching it"
            )
        assert not _ASSIGNMENT.search(text), (
            f"{rel} assigns to os.environ. A module that reads a recorded-answer "
            "variable must never set one."
        )


def test_the_api_test_configuration_still_sets_both_replay_variables() -> None:
    """The other direction: without this, deleting the line from the vitest
    config puts every API test back on the network and this file still
    passes."""
    config = (ROOT / VITEST_CONFIG).read_text(encoding="utf-8")
    opening = re.search(r"\benv\s*:\s*\{", config)
    assert opening, f"{VITEST_CONFIG} has no test `env: {{...}}` block"
    env_block = config[opening.end():]
    env_block = env_block[: env_block.index("}")]
    for name in ("CATERVA_BRENDA_RECORDED", "CATERVA_HTTP_RECORDED"):
        assert re.search(rf"\b{name}\s*:", env_block), (
            f"{VITEST_CONFIG} no longer sets {name} in its test env"
        )
    assert not re.search(r"\bCATERVA_HTTP_RECORD\s*:", env_block), (
        "the API test configuration sets CATERVA_HTTP_RECORD, so every test run "
        "would rewrite the committed recordings from whatever the network said "
        "that day"
    )


def test_the_guard_recognises_an_offender() -> None:
    """A guard whose predicate never fires is not a guard."""
    assert not _is_test_or_doc("Dockerfile")
    assert not _is_test_or_doc("Science-Agent-Pipeline/artifacts/api-server/src/app.ts")
    assert not _is_test_or_doc("docker-compose.yml")
    assert _is_test_or_doc("Tests/test_http_replay.py")
    assert _NAME_PATTERN.search('ENV CATERVA_HTTP_RECORDED=/data')
    assert _NAME_PATTERN.search('process.env["CATERVA_BRENDA_RECORDED"] = x')
    assert not _NAME_PATTERN.search("CATERVA_HTTP_RECORDING_DIR")
    assert _ASSIGNMENT.search('os.environ["X"] = "1"')
    assert _ASSIGNMENT.search("os.environ.setdefault('X', '1')")
    assert not _ASSIGNMENT.search('os.environ.get("X")')
