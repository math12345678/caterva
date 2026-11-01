# ADR 0118: The name the database uses

**Status:** Accepted, implemented

**Date:** 2026-08-18

**Context:** `Tests/fallback_logic.py`,
`Science-Agent-Pipeline/artifacts/api-server/src/lib/queryResolver.ts`

**Relates to:** ADR 0024 (cross-species refusals name the organisms
available — the same idea, one field over)

## How this was found

The owner said Caterva did not feel like it was fixing a problem. Rather
than argue, I used it the way a student would.

The live path could not run here — BRENDA returns 403 to this sandbox — so
the measurement was made through the real resolver against the LDH fixture:

```
substrate="lactate"    -> found=True,  value=10.73
substrate="L-lactate"  -> found=False, source="not_found"
```

Both name the same compound. BRENDA's label is **`(S)-lactate`**: "lactate"
matches as a substring and "L-lactate" does not. And the message the student
received was:

> Could not resolve a real KM value from BRENDA/KEGG/PubMed

which reads as *the literature has nothing*, and is false. The data is in
the table that was already fetched and parsed. A student asking a reasonable
question gets a wall, concludes the tool has no data for the most-studied
enzyme in the corpus, and stops.

That is a fair description of "not fixing a problem", and it is not a
scientific failure — every refusal in this codebase is individually
defensible. It is that the refusals never learned to point anywhere.

## What was already right, and where it stopped

`cross_species_withheld` and `variant_withheld` both name what they refused,
for reasons written into `queryResolver.ts`:

> A refusal that cannot name what it refused leaves the opt-in it demands
> unexercisable.

Substrates were the field left out — and they are the field a reader is far
**more** likely to get wrong. An organism has one binomial name. A
metabolite has a dozen aliases, and the one BRENDA chose carries a stereo
descriptor a student has no way to guess.

## Decision

A `not_found` result now carries `substrates_available`: the substrate
labels the EC number's table actually holds. The table is already fetched,
so this costs one re-parse and no network.

**No substitution.** `enzyme_lookup.expand_substrates_with_synonyms` exists
and is called by nothing but its own test. It could have been wired here and
deliberately was not:

- it costs a PubChem request per name, on the hot path of every lookup;
- PubChem synonymy is not substrate identity. "lactate" and "lactic acid"
  are the same compound; a synonym list also carries salts, stereoisomers
  and esters, and silently matching one returns a measurement of a
  **different molecule** under the name the student asked for. That is ADR
  0024's cross-species error wearing another costume.

A list of real labels cannot be wrong. A guessed match can, and would be
wrong in the direction this project exists to refuse.

**It stays quiet when it would mislead.** If the requested substrate IS in
the table, the miss was about the organism or the quantity, and naming
substrates would point the reader at the wrong thing — ADR 0028's cry-wolf
shape. The comparison is case-insensitive on both sides.

**It cannot make things worse.** The hint runs on a path that has already
failed, so a failure inside it is caught and logged rather than raised: a
diagnostic that turns "no value found" into a stack trace has helped nobody.
It is also emitted *before* the "genuine gap" conclusion, because two
existing tests read the last log line for the verdict and they are right to
— a reader scanning the end wants the answer, not the advice.

## What mutation caught

Four, two of them tests of mine that were worth nothing as written:

1. Computing the hint and not attaching it — caught.
2. Re-parsing with the substrate filter still on — caught.
3. **Removing the cry-wolf guard — not caught.** The test named for it asked
   for `pyruvate` in *Danio rerio*, which returns `cross_species_withheld`,
   a branch that never calls the helper. It passed because of the source
   branch, not the guard. Now asserted directly against the helper.
4. **Making the comparison case-sensitive — not caught.** The test asked for
   `PYRUVATE`, whose label is already lower-case, so both spellings agreed.
   `NAD+` is the label that actually carries capitals, and it is the one
   that exercises it.

## Consequences

- A student who types a reasonable synonym is told which names exist instead
  of being told the literature is empty.
- The message reaches the API surface (`substratesAvailable`) and the
  provenance note, not only the diagnostic log.
- The runner's JSON contract gained a field; three shape assertions in
  `test_runner_contract.py` were updated deliberately rather than loosened.
- Still open, and the more valuable half: BRENDA's own labels are
  discoverable only after a failed query. A student should be able to ask
  what an enzyme reports *before* asking for a value.
