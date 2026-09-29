# ADR 0185: Three guards that passed on an empty tree

**Status:** Accepted, implemented

**Date:** 2026-08-27

**Context:** `scripts/check_package_spelling.py`,
`scripts/check_no_hardcoded_assay_conditions.py`,
`scripts/check_dependencies_declared.py`

**Follows:** [ADR 0184](0184-the-audit-adr-0183-asked-for.md), whose closing
note said the audit had covered test-result parsers only

## Context

macOS withdrew this machine's Files-and-Folders access to `~/Desktop`, where
the repository lives. With no working copy, the tree was pulled to `/tmp`
from the remote — an environment missing `node_modules`, the git metadata,
and every scientific dependency.

That is a **degraded environment**, and it is the one condition under which
"a check that cannot fail" becomes visible. This project has recorded that
defect repeatedly and never measured it across the whole guard set, because
until now there was no reason to run the guards somewhere broken.

**55 of 73 guards passed there. The 18 that did not, refused rather than
reported success** — "'could not check' and 'checked and fine' are different
facts", "the scan is broken, not the pages", "found only 0 public image(s),
below the floor of 5". That is the discipline holding under a condition
nobody designed for.

The question worth asking was about the 55.

## Method, and a correction to it

Ten of the 55 printed a success line containing no number, so a reader could
not tell "checked 300 files, all clean" from "found none, nothing to check".
Each was copied into an empty directory — `REPO_ROOT` is derived from
`__file__`, so the scan roots resolve to nothing — and run.

Six passed on nothing. **Three of those six were false positives of my own
method**, and the correction matters more than the finding:

- `check_privacy_notice` — *"the waitlist form does not exist, so nothing
  here collects an email address"*
- `check_llm_disclosure` — *"no module here can call an external LLM
  provider, so no disclosure is required. This guard stops asking."*
- `check_release_artifacts` — *"no CI workflow publishes an artifact, so no
  LGPL/GPL conveyance obligation attaches"*

These are **conditional** guards. The antecedent is absent, passing is
correct, and each says so in the sentence. They state their denominator in
prose rather than as a digit, and a heuristic that looked for digits called
them defective. Recorded because the next person to run this measurement
will make the same mistake.

## The finding

Three guards assert a universal over an empty set and present it as a result:

| guard | says, having read nothing |
|---|---|
| `check_package_spelling` | "no Python file imports `Terrium`" |
| `check_no_hardcoded_assay_conditions` | "no source file states an assay temperature or pH it did not measure" |
| `check_dependencies_declared` | "every third-party import is declared in a requirements file" |

Over zero files every universal is true. A renamed directory, a moved scan
root, or a glob that stopped matching would produce exactly these sentences,
and nothing in them tells a reader which they are looking at.

## Decision

Each gets a floor and states its denominator, which is this project's own
established remedy rather than an invention here —
`check_public_images_reviewed` already refuses with *"found only 0 public
image(s), below the floor of 5. The scan is broken, not the pages."*

```
OK: 321 Python file(s) read; none imports `Terrium`.
OK: 207 source file(s) read; none states an assay temperature or pH …
OK: 316 source file(s) scanned; every third-party import is declared …
```

The floors — 40, 60, 40 — sit far below the real counts so ordinary deletion
does not trip them. They are smoke alarms for a scan that has stopped
reaching its input, not coverage targets.

## Verification

Both directions, for all three:

- **Empty tree:** all three now refuse, naming what they read — `read only 2
  Python file(s), below the floor of 40`.
- **Real tree:** all three still pass, now with 321 / 207 / 316 stated.
- Selftests still pass where they exist.
- The full survey re-run: **55 pass / 18 not, identical to before** — the
  same 18, so nothing was newly broken.

## Consequences

- Three guards that could not fail now can.
- Three success lines carry a number a reader can sanity-check.
- The "worse than no check" class has been measured across the guard set
  once, at 73 guards, rather than found one at a time by accident.

**What this does not check.**

- ~~**Only guards that print a success line without a number were
  starved.**~~ **All 55 were starved in a follow-up, and the method had two
  faults.** First, the "empty" tree was not empty: the guards were copied
  into `scripts/`, which several of them scan, so `check_package_spelling`
  reported reading 54 files — its own siblings — and its new floor passed on
  them. Re-run one guard per tree, and then with the guard placed outside
  every directory it scans, which is the only arrangement that starves it.

  Seven passed. Four are the known-correct conditionals. A fifth,
  `check_python_bug_lints`, was a **false positive of the method again**: it
  already refuses with "none of ['Tests', 'scripts', 'Terium'] exist;
  nothing was checked", and had passed only because the guard file itself sat
  in `scripts/`, a real target with a real file to lint.

  Two were real, and both now carry floors:

  - `check_rng_convention` said *"all stochastic domains comply with ADR
    0005"* over zero `simulate_*` functions. It now states the count — 7
    today — and refuses below 3.
  - `check_prompt_injection` refuses in six ways already (npx missing,
    timeout, OSError, empty stdout, unparseable JSON, wrong shape), each
    saying a scan that did not happen is not a clean scan. It had no answer
    for a scan that ran perfectly over nothing. The floor is on the INPUT,
    because `trojan-scan` reports no denominator — its `summary` counts
    findings, and zero findings is what a clean repository is supposed to
    produce.

  Survey re-run: 55 pass / 18 not, unchanged.
- **An empty tree is one kind of broken.** A tree with the right shape and
  the wrong content — a scan root present but silently filtered to nothing
  — was not simulated.
- **The 18 that failed here were not individually reviewed.** They refused,
  which is the property under test; whether each refused for the right
  reason was not checked.
- **The floors are judgement.** 40/60/40 are chosen to be obviously below
  today's 321/207/316. Nothing measures whether they are the right cuts, and
  a scan that broke down to 50 files would still pass.