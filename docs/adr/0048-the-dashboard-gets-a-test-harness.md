# ADR 0048: The dashboard gets a test harness

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0044 (the pre-filled default this now protects against),
ADR 0042, ADR 0012/0013

## Context

ADR 0044 removed `km value="5.2"` from the simulation form and closed with
an admission:

> There is also no test that the refusal fires. The guard proves the form is
> not pre-filled; nothing proves the alert appears when a field is empty. The
> dashboard has no test harness at all.

That gap is the reason the defect existed. The guard clause
`if (!km || !vmax || !s0)` had been sitting in `runSimulation()` unreachable
— the form shipped pre-filled, so `km` was never empty and the branch never
ran. **A refusal behind a default is a refusal nothing exercises**, and with
no harness there was nothing that could have noticed.

Removing the default without adding a test would leave the same arrangement
one edit away from returning.

## Decision

`src/web/__tests__/dashboardParameterGate.test.ts` reads the **real**
`dashboard.html`, extracts its inline script, and evaluates it in a Node
`vm` context against a stub DOM.

### Why a VM and not jsdom

Two other options were tried and rejected on evidence:

**jsdom** is not installed, and `npm install` fails here — the sandbox
cannot unlink inside `node_modules`. Adding a dependency that only one
environment can install is not a harness, it is a harness-shaped gap.

**Extracting the script to a file** the test could `require` would break the
page. `server.ts` serves `dashboard.html` at `/` and 404s everything else, so
a `<script src="...">` would fail in production. Fixing that means adding
static file serving — a security-relevant change smuggled in behind a test.

The VM reads the script out of the shipped HTML. It therefore exercises the
code that actually runs, not a copy of it — and a copy is the defect this
project has now hit five separate times.

### What it asserts

The refusal, from both sides:

- an empty `km`, `vmax` or `s0` alerts **and does not call `/api/simulate`**
- a complete form **does** call it

The second is not padding. Without it a gate that refused everything would
satisfy every other test in the file.

The message is asserted too — that it names which parameters are missing, and
that it says a measurement will not be invented. **The reason matters more
than the refusal**: a student who reads "required field" types a plausible
number, which is the outcome ADR 0044 exists to prevent.

## Verification, and a sixth test that could not fail

Four mutations. Three caught immediately:

| Mutation | Result |
|---|---|
| delete the refusal entirely | 6 failures |
| warn but submit anyway (a caveat, not a refusal) | 3 failures |
| re-add `km value="5.2"` | 1 failure |
| short-circuit after the first missing parameter | **passed** |

The fourth is the one worth keeping. `it('names ALL the missing parameters')`
set `km` and `vmax` empty and asserted the alert contained both. Under the
short-circuit mutation only `Km` reaches the missing-list — but the test
still passed, because the explanatory prose in the same message reads *"Km
and Vmax are measurements — this page will not invent one for you."*

**The assertion was reading the sentence that never changes.**

Identical in shape to ADR 0042's `not.toMatch(/PubChem \d/)`, which was
satisfied by the output `PubChem undefined`. Both times the test looked at
the whole blob when it meant to look at one clause.

Fixed by scoping the assertion to the `Cannot simulate: ...` clause with a
regex. With that, the mutation fails.

That is the sixth unfalsifiable check this session and the fifth in my own
work. The running lesson, restated because it keeps arriving in new costume:
**a check that reads its subject with a loose boundary tends to match
something other than what it meant.**

## Consequences

- The dashboard has tests. It is the last surface in the project that did
  not, and it was the one a student is most likely to use.
- The suite overlaps `check_no_unsourced_ui_numbers.py` on "the form carries
  no measured defaults", deliberately. The guard runs in CI over the file;
  the test runs in the suite a developer runs locally. Two failures are
  cheaper than one missed.
- The harness fails loudly if it finds no inline script, rather than testing
  an empty string. A harness that silently tests nothing is the failure mode
  the file is about.

## What it cannot do

It does not render. Layout, CSS and event wiring are untested — a button
whose `onclick` was misspelled passes everything here, and so would a form
field that exists in the DOM but is invisible behind a CSS rule.

This covers the parameter gate specifically, because that gate is the
project's central rule at the surface a student uses. Saying what is
uncovered is the point; the previous state of this page was "no tests" and
the honest description of the new state is "one behaviour tested", not
"tested".
