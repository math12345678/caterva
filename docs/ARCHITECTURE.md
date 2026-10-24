# Caterva: the shape of the system

One page, present tense, kept short on purpose. Each section names the
decision record that decided it; the records say what was *not* done and
what it cost, which this page does not repeat. Counts (tests, guards,
records) live in `README.md`, where a guard holds them to the tree; none are
stated here.

## What it is

Caterva builds mechanistic models of enzyme kinetics in which every number
says where it came from -- a cited measurement, a value you chose, a
computation, or a placeholder nobody measured -- and refuses to say more
than the evidence supports. A refusal that names what it refused and why is
the product working, not failing (ADR 0024).

## The layers, in the order a request passes through them

1. **A grammar of mechanisms** (`caterva/compose/`). A model is recognised
   from the *shape* of what you describe, never from its subject: "two
   genes repressing each other" builds, "glycolysis" is refused with the
   reason (ADR 0173). A model is a value: one reaction network as data, one
   Antimony compiler, and provenance judged at the compile boundary, where a
   quantity with no source is refused (ADR 0170).

2. **The literature layer** (modules under `Tests/`, reached from the
   package through `caterva/checkout.py`'s `literature_module`, and copied
   into `caterva/_literature/` by a release build). It reads BRENDA pages
   into rows, removes variants before any selection (ADR 0029), narrows to
   a Pareto frontier on ordinal evidence axes with no weights (ADR 0047),
   keeps each row's assay conditions and lets a condition mismatch become a
   search (ADR 0172, 0176). It has been reachable from the command people
   type since ADR 0178; before that it worked and nothing a person typed
   called it.

3. **The search over a parameter set** (`caterva/agents/`). A blackboard: a
   finding becomes a constraint only when some agent can act on it, and a
   guard reads the agents' source to enforce that (ADR 0171).

4. **Claims over pinned evidence** (`caterva/evidence/`, `caterva/check/`).
   With `--claims DIR`, every BRENDA page the search read is pinned as a
   dated snapshot, each constant becomes a claim whose identity is the hash
   of its derivation, a refusal is recorded as a claim, and `caterva verify`
   re-checks the bundle offline with a program that imports nothing of the
   code that wrote it. `caterva why` prints a claim's derivation down to the
   bytes (ADR 0179). The search itself still fetches live: a snapshot is a
   record of what was read, never a cache served as current.

5. **Caterva Studio** (`caterva/studio/`). A local server on 127.0.0.1 and
   a page that marks each number by its origin. Its contract with the page
   is `docs/studio/CONTRACT.md`; a parity test per screen holds the
   studio's numbers equal to the command's.

6. **A language model may propose, never supply** (ADR 0011). In the API
   server's resolver a model routes the question and extracts names. A value
   it produces is its own origin and never reaches a model; an EC number it
   produces is dropped unless the query text itself contains it, and the
   enzyme name is resolved by the one name policy every command shares
   (ADR 0179). The Studio assistant (`docs/studio/ASSISTANT.md`) is off by
   default and every sentence it writes is checked against the run's own
   result before it is shown.

## The rules the guards keep

- A guard is not delivered until something runs it unasked
  (`scripts/check_guard_wiring.py`; ADR 0015 made the constitution
  executable).
- A number in a present-tense document is held to the tree: test, guard and
  record counts, BRENDA reference ids on the README (each must occur in a
  committed fixture), and DOIs (a placeholder under an example prefix is
  refused).
- The checker in `caterva/check/` imports only the standard library, so a
  defect in the producer cannot be reproduced in the thing that checks it.
- Recorded pages and recorded answers are read by tests and by nothing
  else; a file outside test configuration that so much as names the
  variables fails a test.
- Nothing is shipped under a claim stronger than what was measured: the
  words are "re-checkable" and "within stated tolerances", and a check that
  could not run is reported as not run, never as passed.

## Releases

A pushed tag is a workflow: it builds the wheel and the app folder, rebuilds
them to compare checksums, runs the installed copy from an empty directory
on three platforms, and only then publishes. The app folder conveys libSBML
and NOTICE says how each LGPL obligation is met (ADR 0177). A release
candidate goes first; the plain tag follows a candidate that shipped every
artifact.

## Where to look

| question | where |
|---|---|
| what to type, and how to read a report | `docs/USING_CATERVA.md` |
| why a design is the way it is | `docs/adr/README.md` |
| what a tagged version contains and does not | `docs/releases/` |
| the Studio's page/server contract | `docs/studio/CONTRACT.md` |
| what reviewers outside the project said | `docs/EXPERT_FEEDBACK.md` |
| the engineering rules, stated once | `docs/CONSTITUTION.md` |
