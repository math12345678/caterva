# ADR 0042: The dashboard was inventing numbers

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0012/0013 (never default a parameter — this applies the
same rule to a screen), ADR 0040 (the findings that never reached the
student), ADR 0024

## Context

ADR 0040 fixed the CLI and closed with an open question: *the web UI is
unexamined, and claiming otherwise without looking would be the mistake this
ADR is about.*

Looking was worse than expected.

`src/web/dashboard.html` is titled **"Caterva - Scientific Enzyme Kinetics
Simulator"**. It has a Run Simulation card taking an enzyme and a substrate.
For anyone who does not use the CLI, it is the product.

It displayed seven numbers as static HTML — no `id`, nothing capable of
updating them:

| Label | Shown | Reality |
|---|---|---|
| Tests Passing | `178/178` | the repo has ~1,631 |
| Coverage | `84.04%` | no live source |
| Uptime | `99.9%` | nothing in this project measures uptime |
| Sources | `3` | — |
| Parameters | `6` | — |
| **Avg Impact Factor** | **`19.79`** | nothing computes this for the UI |
| Avg Citations | `904` | — |

Beside them, in the same `metric-value` style, sat four genuinely live
metrics: `totalRuns`, `avgConfidence`, `avgTime`, `successRate`. **A reader
could not tell which was which.**

`Avg Impact Factor 19.79` is the one to sit with. Specific to two decimal
places. Framed as a measurement. Typed by hand. A student reading it has no
way to distinguish it from the resolved Km three cards down — which is real,
cited, carries its assay conditions, and was refused outright if it could not
be sourced.

**The resolver behind this page refuses to default a Km. The page invented
seven numbers.** That is the project's own thesis failing on its own front
page, and it is precisely what Lisa Jeske described: a student reads a number
off a screen and believes it.

## Decision

### The fabricated numbers are gone

Not replaced with better guesses — removed, with the reason left in the
markup where the next person will find it.

The Literature Database card now says plainly that it has no endpoint for the
inventory and points at `scientific resolve`. That is worse-looking and more
honest: **a number with no source does not belong on a screen, and that is
the rule the resolver already applies to a Km.**

### One metric replaced them, and it is wired

`Health` reads `/api/health` at load. Replacing invented numbers with another
invented number would be the same mistake wearing a fix.

A failed fetch shows `unreachable`, never `ok`. The optimistic reading of a
failed check is how a green "✓ Operational" ends up sitting above a server
that is down.

### A guard, because removal is not durable

`scripts/check_no_unsourced_ui_numbers.py`. Every displayed metric must
either be **written by code at run time** or be **allowlisted with a reason**.
There is no third category, and *"it was true when I typed it"* is not a
source.

`ALLOWLIST` is empty on purpose. Every entry is a promise the number is true
and stays true — and all seven that motivated this guard were things somebody
believed when they typed them.

**An `id` alone is not enough.** An element nothing writes to is exactly as
static as one with no `id`, and looks more trustworthy for having a hook.

## Verification, and a fourth unfalsifiable branch

Three mutations. The first was caught immediately: reintroduce
`Avg Impact Factor 19.79` and the guard names it.

**The other two were not, and the reason is the same defect one level up.**

The guard extracted "the script" as `text[text.index("<script"):]` — everything
after the first `<script>` tag. The dashboard loads Chart.js from a CDN in its
`<head>`, so that slice was *the entire document below it, including every
metric element*. Every `id` matched itself. The id-branch could never fail.

An unfalsifiable branch, inside a guard written to catch displays that cannot
be checked. Caught only by mutating a live `id` to `neverWritten` with a value
of `99.9%` and watching it report OK.

Fixed by extracting the *contents* of `<script>` elements rather than
everything after the first tag. With that:

| Mutation | Result |
|---|---|
| reintroduce a static `Avg Impact Factor 19.79` | caught |
| a live id renamed to `neverWritten`, value `99.9%` | caught **after the fix** |
| `totalRuns` renamed in the HTML only, value `42` | caught **after the fix** |

That is the fifth check this session that could not fail, and the fourth
found in my own work. The pattern is consistent enough to name: **a check
that reads its subject with a loose boundary tends to include itself.** The
parity test included both implementations. The verification config included
its own copy of the settings. This included the HTML it was checking.

## Consequences

- Seven numbers removed from the student-facing page.
- `Health` is new and sourced.
- `check_no_unsourced_ui_numbers.py` is new; the guard count rises by one.
- `mule/` — the marketing site — is **not** checked. Marketing copy makes
  claims about the project rather than readings from it, and conflating the
  two would either flood the guard with false positives or dilute it into a
  spell check. Named rather than implied.
- The dashboard still shows none of ADR 0028/0029/0032's findings. ADR 0040
  fixed the CLI; this fixed the page's honesty, not its completeness. The
  simulation card renders a value, a confidence and a time — no citation, no
  assay conditions, no variant. That is the next piece of work and it is
  larger than this one.

## What this does not claim

The dashboard is now free of *invented* numbers. It is not yet a good
scientific interface. Removing a fabrication is a lower bar than showing
provenance, and clearing the lower bar first is deliberate: a page that shows
nothing is recoverable, and a page that shows convincing fiction teaches a
student the wrong lesson about where numbers come from.
