#!/usr/bin/env python3
"""Record the real NCBI, UniProt and PubChem answers the API tests need.

    python scripts/record_http_fixtures.py          # record live, verify offline, commit-ready
    python scripts/record_http_fixtures.py --check  # verify the committed recordings offline

WHY THIS EXISTS
---------------
The API server's tests run the real science_agent_runner.py, unmocked, and
until these recordings existed each of their lookups asked NCBI Taxonomy,
UniProt and PubChem live: one human hexokinase Km lookup makes 15 distinct
requests (2 NCBI, 1 UniProt, 12 PubChem, recorded 2026-09-30). They
timed out in CI whenever one of those services was slow, which reads
exactly like a regression and is not one. BRENDA was already replayed for
them (Tests/fixtures/recorded/brenda_*.html.gz, CATERVA_BRENDA_RECORDED);
this does the same for everything else that goes through
Tests/http_retry.py retry_get (CATERVA_HTTP_RECORDED).

WHAT IT DOES
------------
1. Runs the runner once per payload in PAYLOADS below, live, with
   CATERVA_HTTP_RECORD pointing at a fresh directory per payload, so the
   files each payload needed are known exactly. BRENDA comes from its own
   recordings throughout; any BRENDA page fetched live instead is an error,
   because it belongs in brenda_<ec>.html.gz with its hash in the README,
   not in a hashed file nobody can find.
2. Runs every payload again from the recordings with the network made
   impossible, and requires three things of each run: no request tried to
   reach the network, the recordings it read are exactly the ones it
   recorded, and its answer is the live run's answer. A recording set that
   only works while the network is up would prove nothing.

   The first requirement is the one that matters, and the answer cannot
   stand in for it. The runner absorbs a failed PubChem lookup: with
   PubChem's recorded answer for "LY-2121260" deleted, the three hexokinase
   payloads that need it each tried PubChem four times, failed, and still
   gave their recorded answers. The first version of this check compared
   answers alone, and passed that recording set, which would have sent the
   request live in CI. Each offline run therefore goes through
   _OFFLINE_RUNNER below, which replaces httpx's transport with one that
   logs the URL and raises, and logs every recording that answers; every
   proxy variable also points at a closed port, for any client that does
   not go through httpx.
3. Replaces Tests/fixtures/recorded/http/ with exactly that set, and writes
   MANIFEST.json: each payload, the tests that send it, the files it needs
   and the answer the live run gave, which Tests/test_http_replay.py holds
   the offline replay to.

`--check` fetches nothing. It runs step 2 on the committed recordings,
holding each payload to the answer and the recordings MANIFEST.json lists
for it, and checks that MANIFEST.json lists exactly the files present.

WHERE PAYLOADS COMES FROM
-------------------------
Not from a guess at what the tests do. Every API test file was run with
CATERVA_PYTHON pointed at a wrapper that logged each payload the runner was
handed, on the day these were recorded. The route tests that need a
listening socket, which the sandbox they were found in refused (listen
EPERM), were reproduced by calling resolveQuery and groundAnnotatedModel
with the exact queries and models those tests post. The path is
queryResolver.ts / modelGrounding.ts ->
scienceAgent.ts resolveKineticValue -> spawnScienceAgent, and the JSON
below is what spawnScienceAgent wrote to stdin. When an API test starts
sending a new payload, add it here and re-run; until then that payload
goes live, the same as an unrecorded BRENDA page.

API keys are removed from the environment before recording (NCBI_API_KEY,
CORE_API_KEY), so the recorded requests are the keyless ones CI sends, and
http_retry refuses to record any request that carries a key regardless.
KEGG stays off (CATERVA_ENABLE_KEGG unset), as it is by default.
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = ROOT / "Tests"
RUNNER = ROOT / "Science-Agent-Pipeline" / "artifacts" / "api-server" / "src" / "lib" / "science_agent_runner.py"
BRENDA_RECORDED = TESTS / "fixtures" / "recorded"
HTTP_RECORDED = BRENDA_RECORDED / "http"
MANIFEST = HTTP_RECORDED / "MANIFEST.json"

BRENDA_ENZYME_URL = "https://www.brenda-enzymes.org/enzyme.php"

#: A port nothing listens on. Every proxy variable points here during the
#: offline check, so a request from a client other than httpx (which
#: _OFFLINE_RUNNER stops itself) fails with a connection error instead of
#: quietly going live.
CLOSED_PROXY = "http://127.0.0.1:9"

#: The runner, run offline and watched. Started as
#: `python -c _OFFLINE_RUNNER <report.json> <runner.py>` with stdin and the
#: environment exactly as for the runner itself; the runner's stdout is
#: untouched, and what was attempted and read goes to <report.json>.
#:
#: - httpx.HTTPTransport.handle_request, where every httpx.get ends up, is
#:   replaced with one that logs the URL and raises httpx.ConnectError, the
#:   error a real outage gives, so the runner takes the path it would take in
#:   CI if the recording were missing. That log is the verdict: an answer
#:   that matches is not enough, because the runner absorbs a failed lookup.
#: - http_retry._replayed is wrapped to log each recording that answers,
#:   which is held to the payload's list in MANIFEST.json.
#: - http_retry's backoff sleeps are skipped, so a missing recording costs
#:   milliseconds rather than retry_get's 1 s + 2 s + 4 s.
#:
#: The report is written at exit, whatever the runner does (it calls
#: sys.exit(1) on an error).
_OFFLINE_RUNNER = r"""
import atexit, json, os, runpy, sys, time
import httpx
import http_retry

report, runner = sys.argv[1], sys.argv[2]
attempts, read = [], set()

def no_network(self, request):
    attempts.append(str(request.url))
    raise httpx.ConnectError("network disabled by record_http_fixtures.py", request=request)

httpx.HTTPTransport.handle_request = no_network

replayed = http_retry._replayed

def counted(key):
    response = replayed(key)
    if response is not None:
        read.add(http_retry.recording_name(key))
    return response

http_retry._replayed = counted

class _NoSleep:
    def __getattr__(self, name):
        return getattr(time, name)
    @staticmethod
    def sleep(seconds):
        pass

http_retry.time = _NoSleep()

def write_report():
    with open(report, "w", encoding="utf-8") as out:
        json.dump({"attempts": attempts, "read": sorted(read)}, out)

atexit.register(write_report)
sys.argv = [runner]
sys.path[0] = os.path.dirname(runner)
runpy.run_path(runner, run_name="__main__")
"""

#: Variables removed from the runner's environment while recording. The two
#: keys would change the requests (NCBI's is a query parameter, CORE's a
#: header) and http_retry would refuse to record them anyway; the rest would
#: make the run read or write somewhere other than intended.
_UNSET = (
    "NCBI_API_KEY", "CORE_API_KEY", "CATERVA_ENABLE_KEGG",
    "CATERVA_HTTP_RECORDED", "CATERVA_HTTP_RECORD",
)

_HEXOKINASE_HUMAN_KM = {
    "enzymeName": "hexokinase", "substrate": "glucose", "organism": "Homo sapiens",
    "ecNumber": "2.7.1.1", "parameterType": "", "quantity": "km",
    "allowCrossSpecies": False, "allowVariants": False,
}


def _name_only(name: str, organism: str = "Homo sapiens") -> dict:
    """A payload that names an enzyme and gives no EC number.

    The runner resolves an EC number for these by UniProt name search, once
    restricted to the organism and once not. For every name below UniProt
    held nothing when recorded, so the answer is ec_not_resolved; that
    refusal is what the tests assert on, and it takes an NCBI Taxonomy
    esearch and those two UniProt searches to reach.
    """
    return {
        "enzymeName": name, "substrate": "", "organism": organism,
        "parameterType": "", "quantity": "km",
        "allowCrossSpecies": False, "allowVariants": False,
    }


#: (the API tests that send it, the payload spawnScienceAgent writes).
PAYLOADS: list[tuple[tuple[str, ...], dict]] = [
    # The flagship lookup: "michaelis menten kinetics for hexokinase" and its
    # variants resolve a human hexokinase Km before refusing for want of
    # [E]0, or completing when the query states it.
    (
        (
            "gapClassification.test.ts",
            "frontDoorCoverage.test.ts",
            "frontDoorRouteCoverage.test.ts",
            "literatureHitRate.test.ts",
            "organismFromQuery.test.ts",
            "scenarioDefaults.test.ts",
            "responseParameterCompleteness.test.ts",
        ),
        _HEXOKINASE_HUMAN_KM,
    ),
    # responseParameterCompleteness: "... with 50 nM enzyme ..." bridges
    # Vmax = kcat x [E]0, so a kcat lookup follows the Km one. 50 nM is
    # 5e-5 mM; the float is the one the TypeScript resolver computes and
    # sends, to the bit.
    (
        ("responseParameterCompleteness.test.ts",),
        {**_HEXOKINASE_HUMAN_KM, "quantity": "kcat", "enzymeConc": 4.9999999999999996e-05},
    ),
    # organismFromQuery: "simulate hexokinase in E. coli ..." and "... in
    # yeast ..." must look the organism up rather than default to human.
    (
        ("organismFromQuery.test.ts",),
        {**_HEXOKINASE_HUMAN_KM, "organism": "Escherichia coli"},
    ),
    (
        ("organismFromQuery.test.ts",),
        {**_HEXOKINASE_HUMAN_KM, "organism": "Saccharomyces cerevisiae"},
    ),
    # customModelRoute: an Antimony model annotated
    # `km enzyme="hexokinase" substrate="glucose" ... resolve` with no EC and
    # no organism; modelGrounding takes the organism from enzymes.ts and the
    # runner resolves the EC by UniProt name search.
    (
        ("customModelRoute.test.ts",),
        {
            "enzymeName": "hexokinase", "substrate": "glucose", "organism": "Homo sapiens",
            "parameterType": "", "quantity": "km",
            "allowCrossSpecies": False, "allowVariants": False,
        },
    ),
    # customModelRoute: `km enzyme="not a real enzyme at all" ... resolve`
    # must fail the run rather than simulate a placeholder.
    (("customModelRoute.test.ts",), _name_only("not a real enzyme at all")),
    # gapClassification: "michaelis menten kinetics for a MAP kinase cascade".
    (("gapClassification.test.ts",), _name_only("menten map cascade")),
    # frontDoorCoverage (and frontDoorRouteCoverage, which imports its
    # QUERIES and so runs its describe block too): the words the keyword
    # extractor takes for an enzyme name in six of the twenty questions.
    (
        ("frontDoorCoverage.test.ts", "frontDoorRouteCoverage.test.ts"),
        _name_only("map cascade negative feedback"),
    ),
    (
        ("frontDoorCoverage.test.ts", "frontDoorRouteCoverage.test.ts"),
        _name_only("at high concentration"),
    ),
    (
        ("frontDoorCoverage.test.ts", "frontDoorRouteCoverage.test.ts"),
        _name_only("enzymes competing same"),
    ),
    (
        ("frontDoorCoverage.test.ts", "frontDoorRouteCoverage.test.ts"),
        _name_only("sequential feedback amino acid synthesis"),
    ),
    (
        ("frontDoorCoverage.test.ts", "frontDoorRouteCoverage.test.ts"),
        _name_only("open constant inflow"),
    ),
    (
        ("frontDoorCoverage.test.ts", "frontDoorRouteCoverage.test.ts"),
        _name_only("allosteric activation by its product"),
    ),
]

#: The fields of the runner's answer the offline replay is held to. The
#: whole answer is compared by the offline check in this script; the
#: manifest keeps the fields a reader and Tests/test_http_replay.py need,
#: rather than every log line.
ANSWER_FIELDS = (
    "ok", "found", "source", "km", "ki", "kcat", "vmax", "unit", "organism",
    "taxonId", "requestedTaxonId", "citation", "ecCandidates",
)


def _runner_env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _UNSET}
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (os.environ.get("PYTHONPATH"), str(ROOT), str(TESTS)) if p
    )
    env["CATERVA_BRENDA_RECORDED"] = str(BRENDA_RECORDED)
    env.update(extra)
    return env


def _offline_env(recorded: pathlib.Path) -> dict:
    env = _runner_env(CATERVA_HTTP_RECORDED=str(recorded))
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env[name] = CLOSED_PROXY
    for name in ("NO_PROXY", "no_proxy"):
        env.pop(name, None)
    return env


def run_runner(payload: dict, env: dict, command: list[str] | None = None) -> dict:
    """One real runner process, exactly as spawnScienceAgent starts it
    (or through `command`, which must run the same script)."""
    proc = subprocess.run(
        command or [sys.executable, str(RUNNER)],
        input=json.dumps(payload), capture_output=True, text=True,
        cwd=ROOT, env=env, timeout=600, check=False,
    )
    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        raise SystemExit(
            f"the runner printed no JSON for {payload} (exit {proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        ) from None


def run_runner_offline(payload: dict, recorded: pathlib.Path) -> tuple[dict, list[str], set[str]]:
    """The runner from the recordings alone: its answer, every URL it tried
    to fetch (which must be none), and the recordings that answered."""
    with tempfile.TemporaryDirectory(prefix="caterva-http-offline-") as scratch:
        report = pathlib.Path(scratch) / "report.json"
        output = run_runner(
            payload, _offline_env(recorded),
            [sys.executable, "-c", _OFFLINE_RUNNER, str(report), str(RUNNER)],
        )
        seen = json.loads(report.read_text(encoding="utf-8"))
    return output, seen["attempts"], set(seen["read"])


def answer_of(output: dict) -> dict:
    return {field: output[field] for field in ANSWER_FIELDS if field in output}


def _key_of(path: pathlib.Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))["key"]


def _check_offline(entries: list[dict], recorded: pathlib.Path) -> list[str]:
    """Every payload, from the recordings alone, tries no request, reads
    exactly its own recordings, and gives its recorded answer."""
    failures = []
    for entry in entries:
        output, attempts, read = run_runner_offline(entry["payload"], recorded)
        if attempts:
            failures.append(
                f"{entry['payload']}: tried the network for {len(attempts)} request(s) "
                f"with no recording: {sorted(set(attempts))}"
            )
        listed = set(entry["recordings"])
        if read != listed:
            failures.append(
                f"{entry['payload']}: read recordings not listed for it: {sorted(read - listed)}; "
                f"listed but not read: {sorted(listed - read)}"
            )
        expected = entry.get("_live_output")
        if expected is not None and output != expected:
            differing = sorted(
                k for k in set(output) | set(expected) if output.get(k) != expected.get(k)
            )
            failures.append(f"{entry['payload']}: offline answer differs in {differing}")
        elif answer_of(output) != entry["answer"]:
            failures.append(
                f"{entry['payload']}: offline answer {answer_of(output)} != recorded {entry['answer']}"
            )
    return failures


def record() -> int:
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    with tempfile.TemporaryDirectory(prefix="caterva-http-record-") as scratch:
        scratch_dir = pathlib.Path(scratch)
        staging = scratch_dir / "all"
        staging.mkdir()
        entries = []
        for index, (needed_by, payload) in enumerate(PAYLOADS):
            own = scratch_dir / f"payload-{index}"
            output = run_runner(payload, _runner_env(CATERVA_HTTP_RECORD=str(own)))
            if not output.get("ok"):
                print(f"FAILED live: {payload}\n  {output}", file=sys.stderr)
                return 1
            files = sorted(p.name for p in own.glob("*.json.gz")) if own.is_dir() else []
            for name in files:
                shutil.copyfile(own / name, staging / name)
            leaked = [
                _key_of(staging / name) for name in files
                if _key_of(staging / name)["url"] == BRENDA_ENZYME_URL
            ]
            if leaked:
                print(
                    f"FAILED: {payload} fetched a BRENDA page live ({leaked}). "
                    "Record it as Tests/fixtures/recorded/brenda_<ec>.html.gz "
                    "(see the README there) and run this again.",
                    file=sys.stderr,
                )
                return 1
            entries.append({
                "needed_by": list(needed_by),
                "payload": payload,
                "answer": answer_of(output),
                "recordings": files,
                "_live_output": output,
            })
            print(f"recorded {len(files):2d} responses for {payload.get('enzymeName')!r} "
                  f"({payload.get('organism')}, {payload.get('quantity')}): "
                  f"found={output.get('found')} source={output.get('source')}")

        failures = _check_offline(entries, staging)
        if failures:
            print("FAILED: the recordings do not replay the live runs offline:",
                  file=sys.stderr)
            for failure in failures:
                print(f"  {failure}", file=sys.stderr)
            return 1

        HTTP_RECORDED.mkdir(parents=True, exist_ok=True)
        for old in HTTP_RECORDED.glob("*.json.gz"):
            old.unlink()
        for new in sorted(staging.glob("*.json.gz")):
            shutil.copyfile(new, HTTP_RECORDED / new.name)
        for entry in entries:
            entry.pop("_live_output")
        MANIFEST.write_text(json.dumps({
            "recorded": today,
            "runner": str(RUNNER.relative_to(ROOT)),
            "payloads": entries,
        }, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    total = sum(p.stat().st_size for p in HTTP_RECORDED.glob("*.json.gz"))
    count = len(list(HTTP_RECORDED.glob("*.json.gz")))
    print(f"\n{count} recordings, {total} bytes, in {HTTP_RECORDED.relative_to(ROOT)}; "
          f"all {len(entries)} payloads {_REPLAYED}.")
    return 0


_REPLAYED = (
    "replay offline: none tried the network, each read exactly the recordings "
    "listed for it, and each gave its live answer"
)


def check() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures = []
    listed = {name for entry in manifest["payloads"] for name in entry["recordings"]}
    present = {p.name for p in HTTP_RECORDED.glob("*.json.gz")}
    if listed != present:
        failures.append(
            f"MANIFEST.json and {HTTP_RECORDED.relative_to(ROOT)} disagree: listed but "
            f"missing {sorted(listed - present)}; present but unlisted {sorted(present - listed)}"
        )
    failures += _check_offline(manifest["payloads"], HTTP_RECORDED)
    for failure in failures:
        print(f"FAILED: {failure}", file=sys.stderr)
    if not failures:
        print(f"all {len(manifest['payloads'])} payloads {_REPLAYED} "
              f"(recorded {manifest['recorded']}).")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true",
                        help="verify the committed recordings offline; fetch nothing")
    args = parser.parse_args()
    return check() if args.check else record()


if __name__ == "__main__":
    sys.exit(main())
