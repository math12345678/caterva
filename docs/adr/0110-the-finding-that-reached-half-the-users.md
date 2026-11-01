# ADR 0110: The finding that reached half the users

**Status:** Accepted, implemented. **The guard was unwired here and is wired
now — see [ADR 0112](0112-the-input-where-the-refusals-fire.md), which built
the failing input the mutations needed.**

**Date:** 2026-08-17

**Context:** `scripts/check_both_front_ends_read_it.py`,
`docs/one-sided-findings.txt`

**Follows:** [ADR 0106](0106-the-papers-nobody-was-shown.md) and
[ADR 0109](0109-the-second-front-end.md), the same defect on each front end.

## Two by hand, and the second was luck

The runner emits one JSON document. Two independent consumers read it — the
API/web pipe and the CLI pipe. A key read by one and not the other is a
finding rendered to half the users.

`literatureCandidates` was that, twice: unread on the API path (ADR 0106),
then unread on the CLI path a pass later (ADR 0109), where the command
additionally printed *"BRENDA and PubMed were searched and returned
nothing"* — false precisely when the fallback worked.

Two is short of the three this project usually waits for before writing a
check. The reason to write it now is that **the second instance was found by
accident**, when an unrelated fix made a leaf name collide. Nothing was
looking, and nothing would have.

## What the measurement found

**79 keys emitted. 55 read by both front ends. 24 read by one, or neither.**

The 24 are not obscure. They include:

- **`selectionTie`** — Bakker's finding that the evidence did not choose.
  `selectionTieFlags` renders it on the API path; the CLI never mentions it.
  A CLI user is handed the lowest of six equally well-evidenced rows
  spanning 306-fold, with nothing saying so.
- **`selectedForm`** — which named form the returned value actually is
  (ADR 0052). API only.
- **`preparation`** — the His-tagged enzyme that is not the free enzyme
  (ADR 0092). API only.
- **`column_taxon`, `commentary_taxon`** — ADR 0037's organism discrepancy
  detail, read by **neither**. The only two with that status, which makes
  them the first worth looking at.

Jeske's factors and Bakker's axes were built once and delivered to one
audience.

## Scope was wrong on the first attempt, again

The first version read `scienceAgent.ts` and `literatureResolver.ts` alone
and reported **34**. Nine of those were the matcher's fault: each pipe spans
several files, and `Effector`'s fields live in `provenance.ts` while
`scienceAgent.ts` merely imports the type.

That is the third time in four passes that a matcher narrower than the thing
it measures produced accusations rather than an admission of blindness
(ADR 0102, ADR 0104, here). Whole-tree scope, stated in the docstring
because it was got wrong first.

## This baseline is debt, not decisions

`docs/undelivered-fields-baseline.txt` holds decisions somebody checked.
`docs/one-sided-findings.txt` deliberately does **not** claim that. Two
entries were verified by reading the renderers; twenty-two were counted.
Writing "reviewed" beside them would make the file a rubber stamp with
better formatting.

So the contract is ADR 0072's: it **stops the debt growing**. A key that
becomes one-sided and is not listed fails the check. The 24 are a number
somebody can decide about, not a claim that anybody has — and the guard's
success message says exactly that, after a first draft claimed the entries
were "recorded as deliberately reaching one", which is the other file's
contract and would have been the overclaim this guard exists to find.

### The matcher under-reports, and that is the safe direction

`selected` was written into the baseline and the guard rejected it: both
sides "read" it, because `selected` is also an ordinary local variable.
Short generic keys — `raw`, `status`, `low`, `high`, `notes`, `tokens` —
collide with incidental identifiers, so **24 is a floor, not a total**. The
bias is deliberate: a false accusation teaches people to distrust the check;
a missed one is the status quo.

The rule caught a real error in this file's own first draft, which is the
best evidence available that it works.

## The guard is written, green, and NOT wired

Mutation testing returned **0 caught, 3 not caught** — and the guard is not
what is wrong. All three mutations delete a failure path, and the guard is
currently green: every one-sided key is listed, so `unreviewed` is empty,
`stale` is empty, both sides are non-empty. **Removing a check that is not
firing changes no output**, so no verdict can be had.

Same structure as [ADR 0100](0100-the-container-was-not-the-contents.md)'s
G2 and [ADR 0104](0104-the-title-of-the-paper.md)'s T3: a mutation that is a
no-op against the current input cannot be caught, and recording it as caught
would be a verdict the harness never established.

The fix is not a better mutation. It is a `--selftest` that builds a
temporary tree **with the failure present** — a new one-sided key, a stale
baseline entry, an empty side — the way `check_exports_reach_a_caller.py`
does. Then the three mutations become expressible.

Until that exists the guard stays out of `verify_build.py`, because this
project's standing rule is that **a guard whose refusals have never been
observed to fire does not go into a harness everyone runs**. It was wired,
the mutation run said no, and it was unwired again — which is the rule doing
its job on the person who wrote it.

`check_guard_wiring.py` would normally fail an unwired guard; the comment at
the wiring site records why it is absent and what unblocks it, so the gap is
a stated decision rather than an omission.

## Consequences

- 24 findings are known to reach one front end only, counted and named.
  `selectionTie` and `selectedForm` are confirmed gaps, not decisions.
- The guard runs by hand today:
  `python3 scripts/check_both_front_ends_read_it.py`
- Next pass: the `--selftest`, then wire it, then the mutations. After that,
  wiring `selectionTie` into the CLI is the first debt worth paying.

## Related

- [ADR 0106](0106-the-papers-nobody-was-shown.md),
  [ADR 0109](0109-the-second-front-end.md) — the two hand-found instances
- [ADR 0072](0072-evidence-that-can-be-re-derived.md) — the
  stop-the-debt-growing contract reused here
- [ADR 0102](0102-the-probe-nobody-read.md) — a matcher narrower than what
  it measures
