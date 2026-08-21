# ADR 0139: "report needs an enzyme" — and rejected the enzyme you gave

**Status:** Accepted, implemented

**Date:** 2026-08-20

**Context:** `Tests/enzyme_lookup.py`, `scripts/report_lab.py`,
`scripts/report_enzyme_catalog.py`, `src/cli/scientificCLI.ts`

**Finishes:** ADR 0126, which built the name→EC lookup and wired it to
`catalog` only

**Relates to:** ADR 0124 (named this as the last guess in a first query),
ADR 0133 (`report`, the command this unblocks), ADR 0003 / 0027 / 0036 /
0086 (one fact, two copies)

## What was measured

Run as a second-year student would, against the shipped CLI:

```
$ scientific report --enzyme "lactate dehydrogenase" \
      --organism "Homo sapiens" --substrate lactate

✗ report needs an enzyme, an organism and a substrate, e.g.
    scientific report --ec 1.1.1.27 --organism "Homo sapiens" ...
exit=1
```

**The message says "needs an enzyme" and then rejects the enzyme they
gave.**

`catalog --enzyme NAME` and `simulate --resolve --enzyme E` had both
accepted a name for weeks. `report` — the one command whose entire purpose
is producing something a person can hand to a teacher (ADR 0133) — required
an EC number, which is the single piece of information a teaching-lab
student is least likely to have.

ADR 0124 named this exact gap: *"a student who knows only 'lactate
dehydrogenase' still has to get to an EC number."* ADR 0126 then built
`fetch_ec_numbers_by_name` and the refusal policy around it. Neither reached
`report`, because `report` was written afterwards and nothing connected
them.

This is the repository's other recurring shape — **built, correct, and not
connected** — and it is why `report` could not be used by the audience it
was built for.

## Decision

**One name→EC policy, in `enzyme_lookup.ec_number_for_name`, called by
both commands.**

ADR 0126 put the decision inside `report_enzyme_catalog.py`, where only
`catalog` could reach it. Copying that block into `report_lab.py` would have
produced two implementations of one refusal that agree today and drift on
the first edit — the defect found in a plausibility table (0003), a
reliability score (0027), a codegen probe (0036) and a request validator
(0086). So it moved, and the catalog script now calls it too.

**Resolving a name is not guessing it.** UniProt is asked; one answer is an
answer. The policy refuses only when a name is genuinely ambiguous, and then
it names the candidates:

> 'lactate dehydrogenase' names more than one enzyme: 1.1.1.27, 1.1.1.28.
> These are different proteins, so Terrium will not pick one for you — a
> wrong EC number is a citation for the wrong enzyme, not merely a wrong
> value. Re-run with the one you meant.

EC 1.1.1.27 is L-lactate dehydrogenase; 1.1.1.28 is D-lactate
dehydrogenase. A wrong Km is a wrong number. A wrong EC is a correctly
formatted citation for a different protein, which is the failure the whole
provenance layer exists to prevent, arriving before any of it runs.

The three-state rule holds at this step too: **"UniProt has no such enzyme"
and "UniProt could not be reached" are different outcomes.** Collapsing them
tells a student their enzyme does not exist because the network dropped.
Verified live — the sandbox has no route to UniProt, and the command
correctly reports `Could not look up 'lactate dehydrogenase' in UniProt: 403
Forbidden` rather than "no reviewed enzyme".

## Consequences

- `report` accepts `--enzyme NAME` or `--ec N`. The help text now leads with
  the name, and its worked example uses `alcohol dehydrogenase`, which is
  unambiguous — an example that triggers the tool's own refusal is a bad
  first impression, and the *ambiguous* case is what `catalog` is for.
- `Tests/test_a_name_reaches_every_command.py` — 8 tests. UniProt is
  injected throughout: a test that must reach the network to check the
  *wording of a refusal* fails for reasons unrelated to the refusal.
- Two of the eight assert the wiring rather than the behaviour: that both
  scripts import the shared policy, and that neither calls
  `fetch_ec_numbers_by_name` directly again. The second is what stops the
  inlined copy coming back.

## The import that vanished, and the test that now catches it

Mid-edit, another agent's mutation loop restored `scripts/report_lab.py`
from a snapshot taken **before** my import line was added. The call site
survived; the import did not.

The result is worse than a syntax error, because nothing notices it:

```
module still imports cleanly: True
WITHOUT THE IMPORT -> NameError: name 'EnzymeNameNotResolved' is not defined
```

A `NameError` armed on exactly the branch this ADR adds, invisible to `tsc`,
to import-time checks, and to a source-text assertion that merely looked for
`ec_number_for_name` *somewhere* in the file — which it still was, at the
call site.

So `test_the_enzyme_name_branch_actually_runs` **executes** the branch
rather than asserting text about it, and a source-level check for
`from enzyme_lookup import` was added alongside to say which line is missing
when it fires. Verified by mutation on a copy of the file — deleting the
import produces the NameError above, so the test is load-bearing.

The general lesson, and the third variant of it this week: **a check that
reads source as a string cannot see whether the code runs.** ADR 0133 found
the same thing when a document-wide `contains` matched prose explaining
itself; ADR 0136 found it when a test built its own input.

### On working in a shared tree

Recorded because it will happen again. My edits to `report_lab.py` were
silently reverted by a concurrent mutation run, and earlier the reverse
occurred — my in-flight files were swept into another agent's commit
(ADR 0134's problem, one level down). Neither agent did anything wrong;
both used ordinary tools.

The practical control, used here: **edit shared files in small regions, and
verify your change is still present after any test run**, rather than
assuming a file you wrote to is a file that still says what you wrote.
