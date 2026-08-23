# ADR 0161 — The subtle half was decidable after all

**Date:** 2026-08-22
**Status:** Accepted
**Completes:** [ADR 0144](0144-the-guard-that-could-not-see-an-indented-table.md)

## Context

ADR 0144 found `BRENDA ref 649716` — an **acetylcholinesterase** reference —
printed on the README's front page under a **lactate dehydrogenase**
example. A real id, a real paper, the wrong protein, on the front page of a
provenance tool.

It shipped `check_documented_citations_are_real.py`, which closed the
flagrant half: a documented ref must occur in a committed fixture, so `ref
12345` — which existed nowhere — cannot come back. And it was explicit about
what it left open:

> That the reference belongs to the enzyme in the example. Deciding that
> would mean parsing which fixture the surrounding prose is about, and a
> check that guesses is a check that cries wolf. `649716` was a real id in
> the wrong place, and this guard would not have caught it — only the human
> question "is that an LDH reference?" did.

Stating a limit rather than hoping over it is why that guard is trustworthy.
`scripts/evidence_table.py` then listed the open half as *"the project's
central claim and its weakest guard, and it needs live BRENDA."*

**That last clause was wrong**, and finding out is what produced this.

## What made it decidable

Measured across the eleven committed fixtures: **no reference id occurs
under more than one EC number.** 75 refs, zero ambiguous. So "which enzyme
does this reference belong to" has a definite offline answer — the ADR 0144
guard already had the data and threw it away, flattening every fixture into
one set of ids.

The other side — which enzyme the prose is about — is *not* inferred.
`ENZYME_NAMES` is an explicit five-entry table of the names the
documentation actually uses, and a citation is checked only when one of them
appears within twelve lines above it. Anything else is reported as **not
checked**, with a count.

Three states, and the third is the one that keeps this honest:

```
prose names a known enzyme, ref's fixture agrees   -> checked
prose names a known enzyme, ref's fixture differs  -> FAIL
prose names no enzyme this table knows             -> not checked
```

## The first run checked three of eight

Five citations had no enzyme named within reach. A guard reporting "OK" on
three of eight would be the shape this repository exists to refuse, so it
prints the five and says what would fix them.

Then I did what it said. `docs/readmes/main.md`,
`docs/readmes/backend-main.md` and `docs/DESIGN.md` each showed a provenance
block — `km 0.14 mM ... BRENDA ref 740253` — **without naming the enzyme
anywhere near it.** A reader could not tell which protein those numbers
described either. One label per block, and coverage went 3 → 8 with nothing
unchecked.

The guard did not just check the docs; asking it to made them better. That
is the argument for a check whose failure mode is "tell me what you cannot
see" rather than "pass quietly".

## Verification

- `--selftest` builds the historical defect from the fixtures themselves —
  a real AChE ref under a lactate dehydrogenase heading — and asserts it
  would be flagged. It also asserts the guard reports *no enzyme* rather
  than picking one from unrelated text.
- **Mutation on the real tree:** replacing `ref 740253` with `ref 649716` in
  `docs/readmes/main.md` reproduces ADR 0144's exact defect, and the guard
  names it: *"cites ref 649716 under 'lactate dehydrogenase' (EC 1.1.1.27),
  but that reference appears only on the BRENDA page(s) for EC 3.1.1.7."*
  Restored, verified by `diff`.
- Wired into CI **and** `make guards`. It touches no network, so there is no
  honest reason it cannot run on a laptop — and "I did not give it a local
  route" is not "cannot reasonably run locally" (ADR 0130).

## Consequences

- The project's central claim — a citation means what it says — now has a
  guard behind both halves.
- Guard count 71 → 72.
- `evidence_table.py`'s "needs live BRENDA" entry is deleted and replaced
  with a measured row. A list of open questions is only useful if things
  leave it.
- **Still genuinely open:** whether a ref describes the *value* it is
  attached to — that 0.14 mM is the Km on that page — which needs the row,
  not just the reference. Named rather than implied.

## Related

- [ADR 0144](0144-the-guard-that-could-not-see-an-indented-table.md) — the
  defect, and the guard that closed half of it while saying so
- [ADR 0126](0126-a-name-is-not-an-enzyme.md) — the other place a real
  identifier for the wrong protein was refused
