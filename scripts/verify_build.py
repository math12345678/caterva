#!/usr/bin/env python3
"""
Terrium Build Verification Script.

Comprehensive build verification that runs all static analysis guards
and test suites to ensure the codebase is in a deployable state.

Usage:
    python scripts/verify_build.py [--quick] [--no-python] [--no-typescript] [--live]

Options:
    --quick      Run only the fast guards (skip long-running tests)
    --no-python  Skip Python tests
    --no-typescript Skip TypeScript tests
    --live       Also run network-dependent guards (live citation checks).

Exit codes:
    0: All checks passed
    1: Some checks failed
"""

from __future__ import annotations

import os
import signal
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple


REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
API_SERVER_DIR = REPO_ROOT / "Science-Agent-Pipeline" / "artifacts" / "api-server"

#: The simulation engine package. One `r` -- the importable package is
#: `Terium`, the product is `Terrium` (there is a whole guard about that).
#:
#: This constant did not exist. `run_python_tests()` referenced it twice and
#: raised `NameError: name 'TERIUM_DIR' is not defined` on the first line
#: that touched it -- so the non-`--quick` path of THIS SCRIPT crashed before
#: running a single Python test, and every check sequenced after it never
#: ran either.
#:
#: It survived because `ruff` is configured in pyproject.toml with forty-odd
#: rule families selected and is executed by nothing: not CI, not the
#: Makefile, not this file. F821 (undefined-name) finds it in under a second.
#: A linter that is configured and never run reads as coverage and is not.
TERIUM_DIR = REPO_ROOT / "Terium"


#: The interpreter running THIS script, quoted for the shell.
#:
#: Every guard below used to be spawned as a bare `python`, which is
#: whatever PATH resolves -- not the interpreter that started
#: verify_build, and not necessarily the one `make setup` built. On a
#: machine with Anaconda first on PATH the result was a run that graded
#: the tree with an environment the project never installed: the Citation
#: Metadata guard reported `cffconvert is not installed` and the
#: Documented Counts guard reported different totals, while both passed
#: when run directly through `.venv/bin/python3`.
#:
#: Neither result was wrong about the interpreter it used. They were
#: answers to a question nobody asked -- "is the tree fine under some
#: other Python" -- reported as the verdict on this one.
#:
#: `shlex.quote` because a virtualenv can sit under a path with spaces
#: and `run_command` uses `shell=True`.
PYTHON = shlex.quote(sys.executable)


def run_command(
    cmd: str,
    cwd: Path | None = None,
    timeout: int = 300,
    capture_output: bool = False
) -> Tuple[bool, str, str]:
    """Run a command and return (success, stdout, stderr).

    The child runs in its own process group (start_new_session). On
    timeout we SIGKILL that group: killing only the shell wrapper used to
    orphan the real command, which then kept the stdout/stderr pipe open
    forever and made every waiting `tail`/caller appear to hang.
    """
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            start_new_session=True,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if proc is not None and proc.pid:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        return False, "", f"Command timed out after {timeout}s: {cmd}"
    except Exception as e:
        if proc is not None and proc.pid:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        return False, "", f"Command failed with exception: {e}"
    else:
        success = proc.returncode == 0
        stdout = stdout or ""
        stderr = stderr or ""
        return success, stdout, stderr


def run_guard(
    name: str,
    cmd: str,
    cwd: Path | None = None,
    timeout: int = 120,
) -> Tuple[str, bool, str]:
    """Run a guard and return (name, success, message)."""
    print(f"  Running {name}...", end=" ", flush=True)
    success, stdout, stderr = run_command(cmd, cwd=cwd, timeout=timeout)
    
    if success:
        print("✅", flush=True)
        return name, True, stdout.strip()
    print("❌", flush=True)
    error_msg = stderr.strip() or stdout.strip() or f"Command failed: {cmd}"
    return name, False, error_msg


def run_python_guards() -> List[Tuple[str, bool, str]]:
    """Run all Python guards."""
    guards = []
    
    # Citation format guard
    guards.append(run_guard(
        "Citation Format Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_citation_format.py'}"
    ))
    
    # Engine contract guard
    guards.append(run_guard(
        "Engine Contract Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_engine_contract.py'}"
    ))
    
    # Dependencies guard
    guards.append(run_guard(
        "Dependencies Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_dependencies_declared.py'}"
    ))
    
    # Plausibility constants guard
    guards.append(run_guard(
        "Plausibility Constants Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_plausibility_constants.py'}"
    ))

    # No user input may reach a shell. The server spawns Python with the
    # argv form and passes data over stdin as JSON -- correct, and one
    # twelve-character edit (`shell: true`) from being RCE on a server that
    # has no authentication. A correct thing nobody watches is a coincidence.
    guards.append(run_guard(
        "Subprocess Safety Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_subprocess_safety.py'} --selftest"
    ))
    guards.append(run_guard(
        "Subprocess Safety Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_subprocess_safety.py'}",
        timeout=180,
    ))

    # llmResolver.ts can send the query somebody typed to one of six
    # external providers. PRIVACY.md said "no third-party requests FROM THE
    # PAGE ITSELF" -- a qualifier that made a misleading sentence technically
    # true, written by the same author one pass earlier.
    # Goes quiet if the LLM path is ever removed.
    guards.append(run_guard(
        "LLM Disclosure Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_llm_disclosure.py'} --selftest"
    ))
    guards.append(run_guard(
        "LLM Disclosure Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_llm_disclosure.py'}"
    ))

    # The waitlist form collects an email address -- personal data -- and
    # said nothing about what happens to it. Twelve passes of audit covered
    # licences, dependencies and attribution and never looked at the one
    # place the project asks a stranger for their details.
    # Goes quiet if email collection is ever removed.
    guards.append(run_guard(
        "Privacy Notice Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_privacy_notice.py'} --selftest"
    ))
    guards.append(run_guard(
        "Privacy Notice Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_privacy_notice.py'}"
    ))

    # A server with no authentication must not be published to every
    # interface. docker-compose.yml shipped "3000:3000" -- which Docker binds
    # to 0.0.0.0 -- beside NODE_ENV=production and restart: unless-stopped.
    # Goes quiet if authentication is added, same as the guard below.
    guards.append(run_guard(
        "Port Binding Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_port_binding.py'} --selftest"
    ))
    guards.append(run_guard(
        "Port Binding Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_port_binding.py'}"
    ))

    # The web server has no authentication and /api/jobs/history returns
    # every user's queries to any caller. Defensible for a localhost tool;
    # what was not defensible is that nothing said so for seven passes of
    # audit. Goes quiet if authentication is ever added.
    guards.append(run_guard(
        "Deployment Warning Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_deployment_warning.py'} --selftest"
    ))
    guards.append(run_guard(
        "Deployment Warning Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_deployment_warning.py'}"
    ))

    # Business material makes claims to people deciding whether to fund or
    # join. A number in a pitch deck is as checkable as one in the product,
    # and is read by someone with less ability to verify it.
    guards.append(run_guard(
        "Investor Claims Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_investor_claims.py'}"
    ))

    # No public page may claim an endorsement that is not on record.
    # Reviewers replied with criticism, not approval, and a landing page that
    # turned "Lisa Jeske of BRENDA reviewed this" into an implied blessing
    # would be fabricating a credential from a real correspondence.
    guards.append(run_guard(
        "Fabricated Endorsement Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_no_fabricated_endorsements.py'}"
    ))

    # The seventeen split-repo READMEs are what a stranger arriving from a
    # search result actually lands on. An audit found 2 of 17 stating the
    # licence, 3 of 17 carrying the non-affiliation notice, and 0 of 17
    # routing anyone to contributing.
    guards.append(run_guard(
        "Published Repo README Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_published_repo_readmes.py'} --selftest"
    ))
    guards.append(run_guard(
        "Published Repo README Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_published_repo_readmes.py'}"
    ))

    # The guard above checks what those seventeen READMEs *say*. This one
    # checks that the repositories carrying them ship a LICENSE and NOTICE at
    # all. Until 2026-08-16 they did not: `LICENSE` appeared once in
    # split_repos.sh, in the `main` umbrella's file list, and `NOTICE` never.
    # Seventeen repositories of Apache-2.0 source published with no licence
    # file read as all-rights-reserved -- nobody who found them could legally
    # use what they found.
    guards.append(run_guard(
        "Split-Repo Legal Files Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_split_repo_legal_files.py'} --selftest"
    ))
    guards.append(run_guard(
        "Split-Repo Legal Files Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_split_repo_legal_files.py'}"
    ))

    # Every shipping surface says Terrium is not affiliated with Tellurium.
    # Not a licensing problem -- libRoadRunner is Apache 2.0 and Terrium is a
    # legitimate consumer of it -- but a naming one. Matthias König (HU
    # Berlin) read a cold outreach email as a false claim of credit for the
    # Sauro lab's work, and a disclaimer that exists on one surface while the
    # product is read on seven is a disclaimer nobody sees.
    guards.append(run_guard(
        "Non-Affiliation Notice Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_non_affiliation_notice.py'}"
    ))

    # Every BRENDA reference printed in the documentation is one that exists.
    # The README demonstrated per-value provenance with three citations and
    # all three were wrong: `ref 12345` was a placeholder appearing nowhere,
    # and `ref 649716` is an acetylcholinesterase reference printed under a
    # lactate dehydrogenase example. A reader who checks one and finds
    # nothing has the AI-invented-claims suspicion confirmed by the project's
    # own front page, which no later argument undoes. See ADR 0144.
    guards.append(run_guard(
        "Documented Citations Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_documented_citations_are_real.py'}"
    ))

    # The importable package is `Terium` (one r); the product is `Terrium`
    # (two). `import Terrium` is always a ModuleNotFoundError, and a newcomer
    # who hits it concludes their environment is broken -- then runs
    # `make doctor`, which reports a healthy install.
    guards.append(run_guard(
        "Package Spelling Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_package_spelling.py'} --selftest"
    ))
    guards.append(run_guard(
        "Package Spelling Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_package_spelling.py'}"
    ))

    # Data-source attribution: every licence fact in the source table also
    # appears in NOTICE and reaches a model. BRENDA is CC BY 4.0 and the
    # attribution obligation travels downstream via Apache 2.0 4(d).
    guards.append(run_guard(
        "Data Source Attribution Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_data_source_attribution.py'}"
    ))

    # ADR 0008: modelCitations describes the MODEL. Two domains cited a
    # database instead, so the Michaelis-Menten models were the only ones
    # in the table with no reference to the work defining them.
    guards.append(run_guard(
        "Model Citation Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_model_citations_cite_models.py'}"
    ))

    # Every dependency carries a recorded grant of permission to use it.
    # Defaults to FAIL for an unrecorded dependency: "you must look it up",
    # not "assume it is fine". Found @replit/connectors-sdk, which ships no
    # licence at all.
    guards.append(run_guard(
        "Dependency Licence Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_dependency_licenses.py'}",
        timeout=180,
    ))

    # Publishing a build artifact changes Terrium's licence obligations.
    # The compliance position today rests on a fact nobody was watching:
    # nothing in CI publishes anything, so the LGPL (python-libsbml) and GPL
    # (stdpopsim, opt-in) terms impose nothing. A legal position that depends
    # on an unwatched fact is a coincidence, not a position.
    guards.append(run_guard(
        "Release Artifact Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_release_artifacts.py'} --selftest"
    ))
    guards.append(run_guard(
        "Release Artifact Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_release_artifacts.py'}"
    ))

    # Every relative link in a contributor doc resolves. START_HERE.md is
    # the first thing a newcomer reads and is almost entirely links; a dead
    # one tells them the project's claims about checking things are
    # decoration. Written after Terium/README.md shipped a confident,
    # plausible, wrong path to ADR 0001.
    guards.append(run_guard(
        "Doc Links Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_doc_links.py'} --selftest"
    ))
    guards.append(run_guard(
        "Doc Links Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_doc_links.py'}"
    ))

    # Documented counts guard -- test/domain counts vs reality, across every
    # present-tense contributor doc. Added Stage 7 Part 3 after three counts
    # were found stale by hand; scope widened beyond README.md on 2026-08-15
    # after three onboarding documents were found claiming "22 guards" and
    # "1,291 tests" against a real 36 and 1,735.
    #
    # The self-check runs first and separately. On a clean tree the guard
    # reports zero findings forever, so a matcher that matched nothing would
    # look identical to a matcher that worked -- which is how the narrow
    # scope survived as long as it did.
    guards.append(run_guard(
        "Documented Counts Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_documented_counts.py'} --selftest"
    ))
    guards.append(run_guard(
        "Documented Counts Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_documented_counts.py'}"
    ))

    # The equations LITERATURE_BACKING_DATABASE.md documents must be the
    # ones the engine solves. Added 2026-09-05, after an audit found four
    # model sections describing maths the engine does not compute: PCR
    # written as N0 x E^n (a DECAY formula -- 1.2e10 off the implemented
    # `(1 + efficiency) ** cycle` at 30 cycles), SIR and SEIR written
    # density-dependent while model_building.py emits beta*S*I/N (R0 wrong
    # by a factor of N), and Gillespie described as tau-leaping with an
    # "adaptive tau-selection" implementation that exists nowhere in the
    # tree. Every one was right in the code and wrong on the page.
    #
    # Prose drifts from code silently because nothing reads both. This
    # reads both, and fails if either side moves alone.
    guards.append(run_guard(
        "Documented Equations Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_documented_equations_match_engine.py'}"
        " --selftest"
    ))
    guards.append(run_guard(
        "Documented Equations Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_documented_equations_match_engine.py'}"
    ))

    # EC numbers in enzymes.ts must still be the ones IUBMB recognises.
    # Added 2026-09-05, after cytochrome c oxidase was found shipping
    # EC 1.9.3.1 -- transferred to 7.1.1.9 in 2018 when class EC 7
    # (translocases) was created. A transferred EC still resolves, so
    # nothing 404s; the lookup just silently asks the wrong question, the
    # same shape as a DOI resolving to the wrong paper (ADR 0076).
    #
    # Offline: compares against Tests/fixtures/ec_numbers_verified.json,
    # so an EC added or edited without being checked fails here. `--live`
    # re-asks Expasy and lives in the live-citation group, since only that
    # can catch a transfer made after the snapshot was taken.
    guards.append(run_guard(
        "EC Numbers Current Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_ec_numbers_current.py'} --selftest"
    ))
    guards.append(run_guard(
        "EC Numbers Current Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_ec_numbers_current.py'}"
    ))

    # Landing-page test counts. Wired here 2026-09-05: it was added earlier
    # the same day to `make guards` ALONE, which check_guard_wiring does not
    # accept as a harness -- correctly, since `make guards` is a target
    # someone chooses to run. A guard that only runs when asked is the exact
    # thing the Stage 4 amendment forbids, and this one shipped that way for
    # several commits before its own sibling guard caught it.
    #
    # Default (fast) mode only. `--full` runs all four suites (~40 min).
    guards.append(run_guard(
        "Landing Test Counts Guard (self-check)",
        f"{PYTHON} {SCRIPTS_DIR / 'check_landing_test_counts.py'} --selftest"
    ))
    guards.append(run_guard(
        "Landing Test Counts Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_landing_test_counts.py'}"
    ))

    # Python support window stated consistently across requirements.txt,
    # README, CONTRIBUTING and the Makefile gate. Offline; --online adds a
    # PyPI wheel-coverage check. Added Stage 8 after the stated REASON for
    # the window was found wrong in all three files (ADR 0014).
    guards.append(run_guard(
        "Python Support Claim Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_python_support_claim.py'}"
    ))

    # Rule 7 (never `pip install tellurium`) made executable. It was one of
    # the nine non-negotiable rules, had ADR 0001 behind it, and adding
    # terium to requirements.txt passed every guard in the repo.
    guards.append(run_guard(
        "Constitution Rules 7+8 Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_forbidden_packages.py'}"
    ))

    # The Stage 4 amendment made executable: a guard is not delivered until
    # something runs it unasked. check_rng_convention sat wired to nothing
    # for a whole stage, and check_citation_format shipped the same way --
    # both found by hand. This one catches the next occurrence, including
    # itself (it did, on its first run).
    guards.append(run_guard(
        "Guard Wiring Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_guard_wiring.py'}"
    ))

    # The Python/TypeScript process boundary, both directions. Six ADRs
    # (0027, 0038, 0039, 0041) record one defect: a field computed correctly
    # on one side and never received on the other, invisible because every
    # test sat on one side of the boundary and none on the boundary itself.
    #
    # Adding a field to KineticResult now FAILS until someone records
    # whether it crosses. That is the point -- four fields defaulted to
    # "does not cross" silently and none of their tests noticed.
    guards.append(run_guard(
        "Runner Boundary Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_runner_boundary.py'}"
    ))

    # How much of BRENDA's commentary Terrium can actually read.
    #
    # Not a correctness check -- a coverage measurement. It exists because a
    # parser that ignores text does not report how much it ignored, and two
    # real defects lived in that silence: the mutant rows of ADR 0029, and a
    # buffer molarity dropped so quietly that the field added to disclose it
    # was empty for the exact strings that motivated it.
    #
    # Wired here rather than left standalone. `check_guard_wiring.py` calls
    # an unrun guard one that "passes only when someone thinks to run it,
    # which is how check_rng_convention sat dead for a whole stage". See
    # ADR 0031.
    # Does everything the resolver computes reach a reader?
    #
    # ADR 0027 and ADR 0039 are the same defect: a field computed correctly
    # and dropped at the process boundary. Wired here rather than left
    # standalone, because check_guard_wiring.py is right that an unrun guard
    # "passes only when someone thinks to run it". See ADR 0045.
    guards.append(run_guard(
        "Findings Reach A Surface Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_findings_reach_a_surface.py'}"
    ))

    guards.append(run_guard(
        "Commentary Coverage Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_commentary_coverage.py'}"
    ))

    # Every simulation domain must be declared in all three API layers
    # (DISPATCH, SimulationDomain, SimulationParameterSchemas). ADR 0007's
    # contract test pins DISPATCH against the engine; nothing pinned the
    # TypeScript side, and on 2026-08-09 three domains were declared with
    # no engine implementation behind them while two real ones were
    # deleted from DISPATCH. Pure text parsing, so it still works when the
    # Node toolchain is what is broken.
    guards.append(run_guard(
        "Domain Parity Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_domain_parity.py'}"
    ))

    # Every hardcoded scientific number must declare its provenance. The
    # project claimed "nothing is hardcoded, everything is literature-backed"
    # while 64 numbers sat in DOMAIN_DEFAULTS unexamined, under
    # justification strings nothing verified. This makes the claim
    # falsifiable: UNVERIFIED is an allowed answer, silence is not.
    guards.append(run_guard(
        "Literature Inventory Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_literature_inventory.py'}"
    ))

    # Two guards were written and left unwired; check_guard_wiring reports
    # them and the build stayed green, which is exactly the failure the
    # Stage 4 amendment exists for. Wired here:
    #
    # check_license_consistency.py: LICENSE, CITATION.cff and package.json
    #   drifted to three different licences (LICENSE said "all rights
    #   reserved", CITATION.cff said LicenseRef-Terrium-Proprietary,
    #   package.json said MIT) and nothing read more than one of them at
    #   once. A project about provenance must agree about its own terms.
    guards.append(run_guard(
        "License Consistency Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_license_consistency.py'}"
    ))

    # check_scripts_reachable.py: four times a feature was built, tested,
    # and callable from nowhere (unregistered routes, an uncalled CLI
    # write, export scripts nothing spawned). Every runner script under
    # scripts/ must be named by something that can spawn it.
    guards.append(run_guard(
        "Scripts Reachable Guard",
        f"{PYTHON} {SCRIPTS_DIR / 'check_scripts_reachable.py'}"
    ))

    return guards


def run_typescript_guards() -> List[Tuple[str, bool, str]]:
    """TypeScript static analysis. Runs in EVERY mode, including --quick.

    Deliberately a guard rather than a test: until this existed, nothing in
    the aggregate verifier type-checked TypeScript at all, and the
    TypeScript test run (`npm test`) was skipped by --quick. So --quick
    could print "ALL CHECKS PASSED / deployable state" over a tree that did
    not compile -- which it did, repeatedly, on 2026-08-09.

    Type-checking is cheap, deterministic and offline, so there is no
    reason for it to live behind the slow-test flag. See
    check_typescript_compiles.py for the full rationale.
    """
    return [
        run_guard(
            "TypeScript Compile Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_typescript_compiles.py'}",
            timeout=300,
        ),
        # The generated API contract must use syntax the installed zod
        # actually has. orval's `version: "auto"` read zod 3.25's `zod/v4`
        # SUBPATH as "v4 is available" and emitted `zod.iso.datetime(...)`
        # while importing from plain "zod", where `iso` is undefined -- a
        # contract that threw on import, produced by the documented codegen
        # command. `tsc --noEmit` is structurally blind to it: zod 3.25
        # DECLARES `iso` in its types and does not export it at runtime.
        # See ADR 0030.
        #
        # MOVED into this group on 2026-08-29: it loads the generated
        # client under node against the installed zod, so it needs the
        # same toolchain the compile guard needs, and it sat in an
        # always-on group -- red in CI's Python job (no node_modules) and
        # green on every developer machine, the exact split ADR 0167's
        # flag fix was about. `--no-typescript` gating it is the flag
        # meaning what it says: this IS a TypeScript-toolchain check.
        run_guard(
            "Generated Client Loads Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_generated_client_loads.py'}",
            timeout=300,
        ),
        # The TypeScript half of check_no_silent_skips. That guard counts
        # pytest's "N skipped" line, so ~600 TypeScript tests across two
        # runners were invisible to it AND to check_documented_counts: a
        # whole suite could stop being collected and no number anywhere
        # would move. Asks each runner which FILES it will run (~2s each,
        # no imports) and compares against what is on disk.
        #
        # MOVED here 2026-08-29, third of three: it shells out to
        # `npx jest --listTests` and `npx vitest list`, which need the
        # installed runners — CI's Python job has system npx and no
        # node_modules, so this was red there and green on every developer
        # machine. The sweep that found it also checked every other guard
        # verify_build runs for node/npx/pnpm use: none remain outside
        # this group (check_prompt_injection uses npx for trojan-scan and
        # runs fine on a bare runner — measured, its findings appear in
        # the CI log).
        run_guard(
            "TypeScript Suite Discovery Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_typescript_suites_discovered.py'}",
            timeout=240,
        ),
    ]


def run_hygiene_guard() -> List[Tuple[str, bool, str]]:
    """Fail when build output or vendored dependencies are committed.

    Three times in one session derived files entered or nearly entered git:
    node_modules/ (unignored), coverage/ (unignored), and dist/ -- 41
    compiled .js files that WERE committed after tsconfig gained an outDir.

    A compiled mirror of the source tree is the largest possible instance
    of the duplicate-source-of-truth problem this codebase has spent
    seventeen parts removing.
    """
    return [
        run_guard(
            "Generated Files Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_no_generated_files_tracked.py'}",
            timeout=180,
        )
    ]


def run_orphan_guard() -> List[Tuple[str, bool, str]]:
    """Fail when a source module is imported by nothing.

    This repository is written to by several AI agents concurrently, and
    the incentive they all share is to ADD. Nothing punished code that was
    never called, so a single commit landed 2,009 lines across seven
    modules with zero importers -- and every guard passed, because
    unreachable code compiles fine and cannot break a test.

    The cost is not disk space. It is that the repo accumulated four
    parallel implementations of Michaelis-Menten and three of BRENDA
    lookup, with no way to tell which one the product uses. Every serious
    defect this project has found lived in the copy nobody was watching.
    """
    return [
        run_guard(
            "Orphan Module Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_no_orphan_modules.py'}",
            timeout=120,
        )
    ]


def run_vacuous_test_guard() -> List[Tuple[str, bool, str]]:
    """Fail when a test's only assertions sit inside a conditional.

    Sibling of the orphan guard, and the same blind spot from the other
    side. The orphan guard catches code nothing runs; this one catches
    tests that run but cannot fail:

        if (provenance) {
          expect(provenance.origin).not.toBe("resolved");
        }

    -- where `provenance` is `undefined` by design, so the assertion never
    executes. And its twin, which accommodates instead of skipping:

        if (empty) expect(validated).toBe(false);
        else       expect(validated).toBe(true);

    -- which has an answer ready for both outcomes and so claims nothing.

    Neither can go red, and both count toward the test total, so they read
    as coverage. The first sweep found twelve, including three route tests
    that returned on `status === "failed"` with the comment "acceptable if
    the Python environment isn't configured" -- passing both when the
    simulation worked and when it didn't. Making one of them honest
    revealed that its query had been failing on every run since it was
    written.
    """
    return [
        run_guard(
            "Vacuous Test Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_no_vacuous_tests.py'}",
            timeout=120,
        ),
        # Third member of the same family. The orphan guard catches code
        # nothing runs; the vacuous guard catches tests that run but cannot
        # fail; this one catches tests that do not run at all and say
        # nothing about it.
        #
        # `.only` is the acute case: one committed `describe.only` disables
        # every sibling in its file and the suite still reports green.
        # `.skip` is the chronic one -- legitimate when the engine is
        # genuinely absent, but silent, which is how nineteen popgen tests
        # went dark for a whole stage (Part 21) before a count guard
        # noticed. The rule is not "never skip"; it is "never skip
        # quietly".
        run_guard(
            "Disabled Test Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_no_disabled_tests.py'}",
            timeout=120,
        ),
        # And the same idea aimed at documentation. An example is a promise
        # about how the product behaves; nothing was checking that the
        # promises were true. The first run found that ten of the eleven
        # endpoints in the documented Python client did not exist -- a
        # reader following the quick start would have got a 404 on nearly
        # every call and concluded the product was broken.
        # The MuleRun site loads ONE script from index.html; that module
        # imports 27 more. An HTML-only check would report "13 assets, all
        # present" on a page where 27 of 28 JS files could be deleted
        # without complaint -- the reassuring number would be the problem.
        run_guard(
            "Static Asset Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_static_assets.py'} "
            f"{SCRIPTS_DIR.parent / 'mule' / 'index.html'}",
            timeout=60,
        ),
        run_guard(
            "Example Endpoint Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_example_endpoints.py'}",
            timeout=120,
        ),
        # ------------------------------------------------------------------
        # Six guards below were written, correct, and wired to NOTHING.
        # `check_guard_wiring.py` named all six on the same run. That is the
        # exact failure the Stage 4 amendment was written for -- a guard that
        # runs nowhere passes trivially whenever someone runs it by hand, so
        # the only symptom is silence -- and it had recurred six times over.
        #
        # Two of them (`check_commands_runnable`, `check_scripts_reachable`)
        # were added in this same effort. Writing a guard and not wiring it
        # is the defect the guard-wiring guard exists to catch, committed by
        # the person who had just been reading its output.
        # ------------------------------------------------------------------
        # Documentation promises a command; this runs it.
        run_guard(
            "Documented Command Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_commands_runnable.py'}",
            timeout=120,
        ),
        # The other direction: a command or flag that works and is in no
        # help text. It found `sweep` and `history` -- two whole working
        # commands -- plus seven flags of `simulate --resolve`.
        run_guard(
            "CLI Surface Documentation Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_cli_surface_documented.py'}",
            timeout=60,
        ),
        # A script nothing invokes. Dead code is not merely unused, it is
        # unexercised, and unexercised code is where confidently wrong
        # numbers live.
        run_guard(
            "Script Reachability Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_scripts_reachable.py'}",
            timeout=180,
        ),
        # An ADR that exists and is in no index is an ADR nobody reads.
        run_guard(
            "ADR Index Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_adr_index.py'}",
            timeout=60,
        ),
        # One licence claim in one place, everywhere. The relicensing to
        # Apache 2.0 touched enough files that a stale "MIT" is a legal
        # statement, not a typo.
        run_guard(
            "Licence Consistency Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_license_consistency.py'}",
            timeout=60,
        ),
        # CITATION.cff is how a result cites the tool that produced it, and
        # it now travels inside every exported COMBINE archive. An invalid
        # one fails SILENTLY -- GitHub just stops showing the citation
        # button -- so nothing else would report it.
        run_guard(
            "Citation Metadata Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_citation_cff.py'}",
            timeout=60,
        ),
        # A computed finding that reaches no surface has not been reported.
        # `scientific domains` prints fifteen copy-pasteable commands, and a
        # student's first act is to paste one. Shape assertions passed while
        # `wf --n 100 --p0 0.5` was in the catalogue and neither flag exists.
        # The only thing that settles it is running them. See ADR 0122.
        run_guard(
            "Domain Examples Run",
            f"{PYTHON} {SCRIPTS_DIR / 'check_domain_examples_run.py'}",
            timeout=180,
        ),
        run_guard(
            "Finding Reachability Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_findings_reach_a_surface.py'}",
            timeout=120,
        ),
        # ...and one that reaches only ONE of the two front ends has been
        # reported to half the users. Found by hand twice (ADR 0106, 0109),
        # the second time only because an unrelated fix made a leaf name
        # collide. Nothing was looking.
        #
        # Wired one pass late, on purpose. The first attempt was unwired
        # again the same day: mutation testing returned 0 caught, 3 not
        # caught, because against a green tree every failure path is
        # unreachable and deleting one changes nothing. A guard whose
        # refusals have never been observed to fire does not go into a
        # harness everyone runs. `--selftest` supplies the failing input,
        # and all three mutations are caught now. See ADR 0111.
        run_guard(
            "Both Front Ends Guard (self-check)",
            f"{PYTHON} {SCRIPTS_DIR / 'check_both_front_ends_read_it.py'} --selftest",
            timeout=60,
        ),
        run_guard(
            "Both Front Ends Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_both_front_ends_read_it.py'}",
            timeout=180,
        ),
        # The classifier deciding which fields get checked AT ALL. A bug
        # there is silent by construction -- the field is not reported
        # undelivered and not reported delivered, it stops being asked
        # about. Its first version excused ADR 0039's original defect. See
        # ADR 0100.
        run_guard(
            "Finding Reachability Self-Check",
            f"{PYTHON} {SCRIPTS_DIR / 'check_findings_reach_a_surface.py'} --selftest",
            timeout=60,
        ),
        # Another agent's guard, arrived unwired during this same pass and
        # wired here rather than left for them: a number hardcoded into a
        # page reads exactly like a measured one. Verified passing (exit 0,
        # 5 metrics across 1 page) before wiring -- adding a red guard to a
        # shared harness makes it everyone's problem and nobody's.
        run_guard(
            "Unsourced UI Number Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_no_unsourced_ui_numbers.py'}",
            timeout=120,
        ),
        # A thrown object literal is not an Error, so every consumer using
        # `e instanceof Error ? e.message : String(e)` records the literal
        # text "[object Object]" -- which is what users saw for every failed
        # simulation. TypeScript permits the throw and the hardened readers
        # make it behaviourally invisible, so no unit test can fail on it.
        # See ADR 0065.
        # The mutation harness itself. Its self-test asserts that a mutation
        # which does not apply, or a suite that does not run, is reported
        # INDETERMINATE rather than "not caught" -- the three ways the
        # hand-run harness produced a wrong answer. See ADR 0069.
        run_guard(
            "Mutation Harness Self-Check",
            f"{PYTHON} {SCRIPTS_DIR / 'mutate.py'} --selftest",
            timeout=120,
        ),
        # A mutation table is the evidence a reader is asked to accept, and
        # the harness that produced every table before ADR 0069 had been
        # wrong three separate ways. New records must ship theirs as a
        # re-runnable set file; the 34 that predate the harness are itemised
        # in docs/mutations/NOT-YET-REPRODUCIBLE.txt, which this guard forces
        # to shrink rather than merely exist.
        run_guard(
            "Mutation Table Reproducibility Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_mutation_tables_reproducible.py'}",
            timeout=120,
        ),
        # It shipped with no self-test, enforcing on other people's records a
        # rule it did not meet itself. The eighth case is the load-bearing
        # one: a set file may satisfy the guard by naming a command instead
        # of mutations, and an alternative route nobody checks is a hole, not
        # an alternative. See ADR 0098.
        run_guard(
            "Mutation Table Guard Self-Check",
            f"{PYTHON} {SCRIPTS_DIR / 'check_mutation_tables_reproducible.py'} --selftest",
            timeout=120,
        ),
        # The self-check carries ADR 0079's failing input: a sibling guard's
        # comment-stripper deleted from the `//` in `https://` onward,
        # removing the licence URI from the text being searched for it. This
        # guard strips `//` too and is safe only because it blanks
        # WHOLE-LINE comments -- a distinction that was defended in a
        # comment and never tested until now.
        # An exported function nothing calls was computed for nobody --
        # ADR 0039's defect at the scale of a capability. Found by hand three
        # times (sbml-builder, rankModelsByFit, compareModelPair) before
        # anything checked for it. See ADR 0089.
        # Another agent's, arrived unwired. Verified green (exit 0, four
        # disclosed CDN hosts) BEFORE wiring -- that is the part of the
        # precedent that matters. Wiring a guard nobody has confirmed turns
        # an unknown into everyone's red build, which is what the precedent
        # exists to prevent.
        run_guard(
            "Third-Party Request Disclosure Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_third_party_requests_disclosed.py'}",
            timeout=120,
        ),
        # ruff is configured in pyproject.toml with forty-odd rule families
        # and was executed by NOTHING. F821 found `TERIUM_DIR` undefined in
        # THIS FILE -- so the non-`--quick` path crashed with a NameError
        # before running a single Python test, and every check after it
        # never ran. A linter configured and never invoked reads as coverage
        # and is not. See ADR 0093.
        run_guard(
            "Python Bug-Lint Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_python_bug_lints.py'}",
            timeout=180,
        ),
        run_guard(
            "Unwired Export Guard (self-check)",
            f"{PYTHON} {SCRIPTS_DIR / 'check_exports_reach_a_caller.py'} --selftest",
            timeout=120,
        ),
        run_guard(
            "Unwired Export Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_exports_reach_a_caller.py'}",
            timeout=120,
        ),
        run_guard(
            "Thrown Value Guard (self-check)",
            f"{PYTHON} {SCRIPTS_DIR / 'check_thrown_values_are_errors.py'} --selftest",
            timeout=120,
        ),
        run_guard(
            "Thrown Value Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_thrown_values_are_errors.py'}",
            timeout=120,
        ),
        # Also another agent's, also arrived unwired, also verified green
        # (exit 0) before wiring. A source file stating an assay pH or
        # temperature it did not measure is the hardcoding rule at its
        # sharpest -- those two numbers are exactly what STRENDA asks a
        # measurement to carry, so inventing them forges the provenance
        # rather than merely omitting it.
        run_guard(
            "Hardcoded Assay Condition Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_no_hardcoded_assay_conditions.py'}",
            timeout=120,
        ),
    ]


def run_injection_guard() -> List[Tuple[str, bool, str]]:
    """Scan for prompt injections aimed at an AI agent.

    Several AI coding agents commit to this repository concurrently and
    read each other's files, so prose is an execution surface here: a
    sentence written to manipulate a reader rather than inform one can
    change what the next agent does. That is a supply-chain risk with a
    text payload, and it belongs in the same place as the other guards.

    Runs in both quick and full mode. It is fully offline (trojan-scan
    makes no network calls) and takes ~30s, and a repository that several
    agents write to unattended is exactly the one that should not defer
    this to a mode nobody runs.
    """
    return [
        run_guard(
            "Prompt Injection Guard",
            f"{PYTHON} {SCRIPTS_DIR / 'check_prompt_injection.py'}",
            timeout=360,
        )
    ]


def run_python_tests(quick: bool = False) -> List[Tuple[str, bool, str]]:
    """Run Python tests."""
    tests: List[Tuple[str, bool, str]] = []

    if quick:
        # Run a representative sample of tests
        test_files = [
            "tests/test_validation.py",
            "tests/test_engine_api.py",
            "tests/test_rng_convention.py",
        ]
        tests.extend(
            run_guard(
                f"Python Test: {test_file}",
                f"{PYTHON} -m pytest {test_file} -v",
                cwd=TERIUM_DIR
            )
            for test_file in test_files
        )
    else:
        # Run all Python tests
        tests.append(run_guard(
            "Python All Tests",
            "python -m pytest tests/ -x --tb=short",
            cwd=TERIUM_DIR,
            timeout=600  # 10 minutes for full test suite
        ))
    
    return tests


def run_typescript_tests() -> List[Tuple[str, bool, str]]:
    """Run TypeScript tests."""
    tests = []
    
    # Run npm test
    tests.append(run_guard(
        "TypeScript Tests",
        "npm test",
        cwd=API_SERVER_DIR,
        timeout=300
    ))
    
    return tests


def run_live_citation_guard() -> List[Tuple[str, bool, str]]:
    """Run the live citation-verification guard (network required).

    verify_citations_live.py re-fetches every golden-set BRENDA page, PMID,
    and DOI the resolvers cite, plus every static modelCitations URL. It is
    a report, not a gate -- literature pages get restructured -- so it is
    opt-in via --live rather than part of the always-run guard set.
    """
    return [
        run_guard(
            "Live Citation Verification",
            f"{PYTHON} {SCRIPTS_DIR / 'verify_citations_live.py'}",
            timeout=180,
        ),
        # Same rationale, different namespace: an EC number can be
        # transferred by IUBMB after the offline snapshot was taken, and
        # only asking Expasy can find that out.
        run_guard(
            "Live EC Number Verification",
            f"{PYTHON} {SCRIPTS_DIR / 'check_ec_numbers_current.py'} --live",
            timeout=180,
        ),
    ]


def run_rng_guard() -> List[Tuple[str, bool, str]]:
    """Run RNG convention guard."""
    guards = []
    
    rng_guard = SCRIPTS_DIR / "check_rng_convention.py"
    if rng_guard.exists():
        guards.append(run_guard(
            "RNG Convention Guard",
            f"{PYTHON} {rng_guard}"
        ))
    
    return guards


def print_results(
    title: str,
    results: List[Tuple[str, bool, str]]
) -> int:
    """Print results and return number of failures."""
    print(f"\n{title}:")
    print("-" * 50)
    
    failures = 0
    for name, success, message in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {name}")
        if not success and message:
            print(f"    Error: {message}")
            failures += 1
    
    return failures


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Terrium Build Verification Script"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only fast checks (skip long-running tests)"
    )
    parser.add_argument(
        "--no-python",
        action="store_true",
        help="Skip Python tests"
    )
    parser.add_argument(
        "--no-typescript",
        action="store_true",
        help="Skip TypeScript tests"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Also run network-dependent guards (live citation checks)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("TERRIUM BUILD VERIFICATION")
    print("=" * 60)
    
    start_time = time.time()
    total_failures = 0
    
    # Run guards
    print("\n🛡️  STATIC ANALYSIS GUARDS")
    
    # Python guards
    python_guards = run_python_guards()
    total_failures += print_results("Python Guards", python_guards)
    
    # RNG guard
    rng_results = run_rng_guard()
    if rng_results:
        total_failures += print_results("RNG Guard", rng_results)

    # TypeScript compile guard. Honours --no-typescript, but is NOT gated
    # on --quick: "deployable" has to mean the code compiles, and that
    # claim was being made without checking it.
    if not args.no_typescript:
        ts_guards = run_typescript_guards()
        total_failures += print_results("TypeScript Guards", ts_guards)

    # EVERYTHING BELOW IS OUTSIDE THAT `if`, AND USED NOT TO BE.
    #
    # Four groups sat inside the --no-typescript branch, so the flag
    # documented as "Skip TypeScript tests" also switched off the
    # prompt-injection scan, the orphan-module check, the 22-guard test
    # honesty group -- ADR index, mutation-table reproducibility, CLI
    # surface, licence consistency, bug-lints among them -- and the check
    # that build output has not been committed. One of the twenty-five is
    # about TypeScript compiling.
    #
    # Measured: `--quick` reported 9 failures and `--quick --no-typescript`
    # reported 4 on the same tree, and the five that vanished included ADR
    # Index, Mutation Table Reproducibility and Prompt Injection. A flag
    # that makes a tree look cleaner by not looking is the shape this
    # repository exists to refuse.
    #
    # Two of them carry comments insisting they run in every mode. Those
    # comments were true about the intent and false about the code, which
    # is worse than no comment: they are the reason nobody re-read the
    # indentation.
    #
    # None of the four needs Node. The Node dependency is inside
    # check_typescript_compiles.py, which correctly reports every
    # workspace as NOT type-checked when there is no local typescript --
    # so gating THAT on the flag is right, and gating these on it was an
    # indentation error with a rationale written over the top.

    # Offline, ~30s, and this repository is written to unattended by
    # several AI agents that read each other's files -- so it runs in
    # every mode rather than behind the slow-test flag.
    injection_guards = run_injection_guard()
    total_failures += print_results("Prompt Injection Guard", injection_guards)

    orphan_guards = run_orphan_guard()
    total_failures += print_results("Orphan Module Guard", orphan_guards)

    # Runs in quick mode too: it is a syntactic scan of the test files,
    # costs under a second, and the thing it catches is invisible in a
    # test summary by construction. A guard against tests that cannot
    # fail is worth little if it only runs in the slow path.
    vacuous_guards = run_vacuous_test_guard()
    total_failures += print_results("Test Honesty Guards", vacuous_guards)

    hygiene_guards = run_hygiene_guard()
    total_failures += print_results("Generated Files Guard", hygiene_guards)

    # Live citation guard (network; opt-in so offline builds stay green)
    if args.live:
        print("\n🛡️  LIVE LITERATURE GUARD")
        live_results = run_live_citation_guard()
        total_failures += print_results("Live Citation Guard", live_results)
    
    # Run tests if not quick mode or explicitly requested
    if not args.quick:
        # Python tests
        if not args.no_python:
            print("\n🧪  PYTHON TESTS")
            python_tests = run_python_tests(quick=False)
            total_failures += print_results("Python Tests", python_tests)
        
        # TypeScript tests
        if not args.no_typescript:
            print("\n🧪  TYPESCRIPT TESTS")
            ts_tests = run_typescript_tests()
            total_failures += print_results("TypeScript Tests", ts_tests)
    else:
        print("\n📝  Running in quick mode - skipped long tests")
    
    # Summary
    end_time = time.time()
    duration = end_time - start_time
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if total_failures == 0:
        print(f"✅ ALL CHECKS PASSED in {duration:.1f}s")
        print("\n🎉 The codebase is in a deployable state!")
        return 0
    print(f"❌ {total_failures} CHECK(S) FAILED in {duration:.1f}s")
    print("\n⚠️  Please fix the issues above before deploying.")
    return 1


if __name__ == '__main__':
    sys.exit(main())