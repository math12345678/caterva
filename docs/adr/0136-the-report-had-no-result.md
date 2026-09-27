# ADR 0136: The report had no result, and s0 lived in two places

**Status:** Accepted, implemented

**Date:** 2026-08-18

**Context:** `scripts/report_lab.py`, `Tests/lab_report.py`,
`Tests/test_report_command_runs_the_model.py`

**Finishes:** ADR 0133, whose Consequences say *"the CLI does not yet run
the simulation as part of `report`... wiring the engine into this command is
the next step"*

**Relates to:** ADR 0038 (a test that builds its own input cannot verify how
the input is produced), ADR 0003 / 0027 / 0036 / 0086 (one fact, two copies)

## What was found

ADR 0133 built `report` to answer the owner's sentence — *"Caterva is a
tool. People should use Caterva."* — by joining nine capabilities into one
document a student could hand to a teacher.

The document had six sections. **The fifth was Result, and it could never
render.**

`build_report(..., simulation=...)` renders a trajectory when handed one.
`scripts/report_lab.py`, the only caller that runs in production, never
passed one. So the one command whose stated purpose is *"run the simulation
and show where the numbers came from"* did the second half only, and
stopped where the reader was going to look.

### The test that should have caught it

`test_the_trajectory_is_summarised_not_dumped` passes, and has always
passed. It passes because it builds a `Trajectory()` object itself and hands
it to `build_report`.

> **A test that constructs its own input cannot verify how the input is
> produced.**

That is ADR 0038's sentence, and this is the fourth time this repository has
hit it. The unit test pins the *renderer*; nothing pinned the *call site*,
and the call site passed nothing. The fix is not a better unit test. It is a
test that drives `scripts/report_lab.py` — the real file, loaded by path so
it cannot drift from what ships.

### `s0` arrived twice, and the two consumers read different copies

Found while wiring the above. `s0` could reach the script by two routes:

| route | who read it |
|---|---|
| `payload["s0"]` | the ensemble, via `consequence_of` |
| `payload["supplied"]` | the Parameters table |

**Nothing compared them.** A caller passing 10 in one and 5 in the other got
a document whose table said 5, whose ensemble was computed at 10, and which
looked entirely self-consistent — every section correct, the document as a
whole false.

This is the defect the repository has now found in a plausibility table
(ADR 0003), a reliability score (ADR 0027), a codegen probe (ADR 0036) and a
request validator (ADR 0086). A lab report is the worst place yet for it,
because the entire document is one claim: *the numbers shown are the numbers
used.*

## Decision

**`model_inputs()` derives every number the model runs at, once.** The
ensemble and the simulation are both handed its result. Neither reads the
payload any more, so they cannot be computed at different values than the
table prints.

A quantity supplied twice with **different** values is refused, naming both
and where each came from. Precedence was rejected deliberately: silently
picking a winner keeps the defect and adds a rule to hide it. Supplied twice
and **agreeing** is fine — the guard must catch a contradiction, not a
redundancy, or no caller that legitimately sets both can ever pass.

Literature values are keyed by the **quantity** they measure, not the label
the caller chose: a parameter named `km_lactate` still resolved a km, and
the model takes a km.

**A model that did not run becomes a refusal, not a missing section.** Three
outcomes are distinguished, because they need different actions:

- `km` missing — a property of the enzyme; Caterva resolves it or refuses.
- `vmax` missing — yours to supply, or derived from kcat and [E]₀.
- `s0` missing — *yours to choose, not a property of the enzyme.*

The third is the distinction the professors' correspondence turns on.
Reporting a missing `s0` the way a missing `km` is reported sends a student
looking for a paper that cannot exist. An unrunnable model (a negative Vmax)
reports why rather than falling silent, because the values it would not
integrate at are printed directly above it.

`build_report` gained `also_refused` so caller-established refusals render
in the same section as the ones it finds itself. A second list elsewhere is
a gap with extra steps.

## Consequences

- `Tests/test_report_command_runs_the_model.py` — 8 tests through the real
  script, stubbing only its **four** network edges (BRENDA HTML, UniProt,
  taxon id, lineage). The real resolver still runs, ranks and refuses; a
  stubbed resolver would make every assertion a test of the stub. Only
  `html_provider` was injectable at the call site, so the first attempt
  failed with a live `403 Forbidden` — worth recording, because a test that
  reaches the network fails for reasons unrelated to the code under test.
- Mutation-tested, each mutation asserted to have applied before measuring:

  | mutation | result |
  |---|---|
  | don't pass the simulation (the state before this ADR) | 3 failed |
  | drop the caller's refusals | 3 failed |
  | let a conflicting value win by precedence | 1 failed |
  | read the payload again instead of the derived inputs | **survived** |

- **The fourth survivor is the finding worth keeping.** The ensemble change
  was genuinely unpinned: the fixture used by the first seven tests produces
  no ensemble, so nothing exercised it. An eighth test was added on *Danio
  rerio*, which has no Km for pyruvate in the fixture and therefore yields a
  real cross-species ensemble from the real resolution path.
- **Its first version passed under mutation too.** It asserted the ABSENCE
  of a sentence — `"could not be run" not in markdown` — and guessed the
  wording wrong; the module actually says *"cannot run the model: s0, vmax
  not supplied"*. A negative assertion against remembered prose is not an
  assertion. It now asserts positively, on the outcomes table. That is the
  failure this whole file exists to catch, occurring in the test written to
  catch it, and it was found only because the mutation was run twice.

## Not done here

**The Bakker-weighted band is still absent from the report.** ADR 0134 left
`lab_report` quoting `spread_consequence`'s enumeration only, and
established the property that makes adding the band safe. That remains the
next step and is unaffected by this change.

## An unrelated breakage observed, and deliberately not fixed

While verifying from the repository root, `report` failed with
`NameError: name 'physiological' is not defined` raised inside
`Tests/fallback_logic.py`, which is **modified in the working tree by
another agent** (+105 lines, adding `ensemble_candidates` to `KineticResult`
and reworking `_best_evidenced`). Confirmed as theirs rather than cwd or
mine: forcing the same run onto `git show HEAD:Tests/fallback_logic.py`
produces the complete document, Result section included.

Not fixed, and not reverted. Editing another agent's in-flight work is how
this session earlier destroyed a better version of
`check_non_affiliation_notice.py` and had to recover it with
`git checkout --`. It is recorded here so the author sees it rather than
being silently patched around.
