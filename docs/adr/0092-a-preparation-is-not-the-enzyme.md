# ADR 0092: A preparation of the enzyme is not the enzyme

**Status:** Accepted, implemented. The exclusion question is now CLOSED — see below.

**Date:** 2026-08-15

**Relates to:** ADR 0029 (a mutant's constant is not the enzyme's), ADR 0031
(measuring what the parser cannot read), ADR 0024 (Jeske on reaction
conditions), ADR 0027 / 0038 (computed and not delivered)

## Context

ADR 0031 introduced `docs/commentary-residue-baseline.txt`: a record of the
BRENDA commentary Caterva cannot read, so that unread text is *reviewed*
rather than merely unparsed. Coverage has risen 73% → 92% since.

One group in that file is marked **OPEN FINDING**:

```
acrylodan
attachment polyethylene glycol side chains lysine residues does not alter Kcat
benzyl
competitive versus His tagged
immobiized
noncompetitive versus pyruvate His tagged
soluble
```

Covalent modification, affinity tags and immobilisation change kinetics.
None is a sequence change, so **ADR 0029's variant filter cannot see them.**

Measured across the corpus: **18 rows** carry such a marker, and ADR 0029
classifies every one `unstated` — eligible for selection as ordinary enzyme.

### It reaches the student

Through the real resolver, before this change:

```
resolve_kinetic_value("1.1.1.27", "Homo sapiens", "NADH", quantity="ki")
  -> value 0.00059
  -> citation notes: None
  -> search log: "BRENDA exact: 1.1.1.27, Homo sapiens, NADH (ki)"
  -> any flag mentioning the tag? False
```

That row's commentary reads *"competitive versus NADH, pH 7.5, 37 °C,
**recombinant His-tagged enzyme**"*. Caterva returned a His-tagged
construct's inhibition constant as the human LDH inhibition constant, with a
real citation attached and nothing anywhere saying what it measured.

The fact was parsed the whole time — it sits in `conditions`. It simply
never reached anyone.

This is ADR 0029 one category over. A mutant's constant is not the enzyme's;
neither is an immobilised enzyme's (diffusional limitation, altered
microenvironment), a PEGylated one's, or a tagged construct's. And it is
Jeske's own list: *"pH value, temperature, cofactors, and buffers play a
huge role"* — preparation belongs in it.

## Decision

`Tests/enzyme_preparation.py` classifies the commentary into
`native` / `immobilised` / `tagged` / `modified` / `unstated` / `absent`,
and the verdict for the winning row travels on `KineticResult.preparation`.

### `recombinant` alone is not a modification

Deliberately not matched. Recombinant expression is how most enzyme is
produced; the protein is the protein. Only the *tag* changes it, so
`"recombinant His-tagged enzyme"` is `tagged` and `"recombinant enzyme"` is
`unstated`.

Both errors are costly. Matching `recombinant` would flag most of the corpus
and train readers to skip the warning — ADR 0028's cry-wolf reasoning.
Not matching the tag is the defect above.

### Five states, because silence is not a clean bill of health

`unstated` and `native` are different facts: the second is a curator writing
"native enzyme". `is_as_isolated` is a positive test on `native` alone —
`status != "modified"` would call tagged, immobilised, unstated and absent
rows "as isolated", which is the inversion this project keeps finding.

`describe()` returns nothing for `unstated` and `absent`. A line saying
"preparation not stated" on every row is noise, and noise is how the lines
that matter stop being read.

## Whether to exclude these rows from selection

Left open when this ADR was accepted, and closed below. The record of how
it was open is kept deliberately: the reasoning that closed it only exists
because the question was written down rather than defaulted.

**As accepted:** excluding narrows what a student can resolve — for some
enzymes the only reported Ki *is* from a tagged construct — while including
keeps a preparation's constant eligible to be returned as the enzyme's. ADR
0029 chose exclusion for variants, and the argument looked like it
transferred; silently narrowing resolution is the kind of change that
should be argued for rather than slipped in beside a reporting fix.

Reporting first, then the argument. Both follow.

### Measured, so the decision is not a guess

An open question nobody returns to becomes the default nobody chose, so the
cost of exclusion was measured rather than left as an argument.

**369** candidate pools survive ADR 0029's variant filter. **360** would
still resolve with preparations excluded. Verified through the real resolver,
exactly **three** queries would go from answered to unanswerable:

| query | value | preparation |
|---|---|---|
| AChE / acetyl thiocholine / Km | 0.09 | PEGylated |
| LDH / NADH / Ki | 0.00059 | His-tagged |
| LDH / dimethoxypyrimidine inhibitor / Ki | 0.00059 | His-tagged |

**And the first is golden tuple G2.** The hand-verified reference set pins
Km 0.09 for human AChE, and that row is PEGylated — the same shape ADR 0029
found, where "the golden set had an isozyme pinned as the expected answer".

### The commentary answers it, and a blanket rule would have got it wrong

G2's row reads:

> pH 8, 27 °C, attachment of polyethylene glycol side chains to lysine
> residues **does not alter the Km value**

The curator states the modification had no effect *on Km*. Excluding it
would have deleted a value the source itself calls equivalent to the free
enzyme's — and the residue baseline predicted exactly this: *"the one case
where the commentary tells us a difference does not matter."*

So `PreparationVerdict` gains `stated_not_to_affect`, and `differs_for()`
takes the quantity being resolved.

**Quantity-specific, and that is the whole point.** The same PEGylated AChE
row carries this clause for Km in one table and for Kcat in another, so the
statement is about a *measurement*, not about the protein. A row saying "does
not alter the Km value" says nothing about its Ki, and `differs_for("ki")`
returns True on it.

The two facts stay separate: `status` remains `modified` (the enzyme WAS
altered) and `stated_not_to_affect` records the curator's claim. Collapsing
them into `native` would lose the first, and the first is what lets a reader
judge the second. A mutation doing exactly that fails three tests.

This narrows the open question usefully. The remaining cost of exclusion is
**two Ki values**, both His-tagged, neither carrying a no-effect statement —
a much smaller decision than it looked before it was measured.

### Closed: do NOT exclude by default, and the literature is why

The obvious move was to mirror ADR 0029 — exclude by default, opt in with
`allow_preparations`. Before doing that, its justification was checked
rather than assumed, and **it does not transfer.**

ADR 0029 argues that active-site substitutions sit at the extremes of the
distribution because they are *chosen precisely because they change the
number*. Nobody adds a purification tag in order to change the kinetics.

The literature is sharper than that. Miskovic et al. (2024) put the same
His-tag on **both termini of one enzyme** (adenylosuccinate synthetase) and
report:

> The addition of the His-tag on the C-terminus was proven to have a
> negligible effect on the characteristics of this enzyme. This paper shows
> that the same enzyme with the His-tag fused on its N-terminus has a high
> tendency to precipitate […] enzyme kinetics measurements showed **reduced
> enzyme activity, but preserved affinity for the substrates** […] testing
> the influence of the tag on protein properties should not be overlooked.

*Int J Mol Sci* 25(14), 7613. doi:10.3390/ijms25147613 (PMID 39062851),
retrieved via PubMed.

Three things follow, and each argues against a blanket rule:

1. **The effect depends on placement, and BRENDA does not record it.**
   "recombinant His-tagged enzyme" does not say which terminus. So the
   honest state is *unknown* — not "probably harmful", which exclusion
   would assert.
2. **The effect is quantity-dependent.** Where the tag did harm, it reduced
   *activity* and **preserved substrate affinity**. Both values Caterva
   would lose are **Ki** — affinity constants, the quantity that survived
   in the one case measured end to end.
3. **The original defect was silence, and silence is fixed.** The value now
   arrives flagged, naming the tag and quoting the commentary. Exclusion is
   a second, stronger remedy for a problem the first remedy already
   addresses.

So: reported, not withheld. Excluding would refuse two real, correctly
cited values on a mechanism the literature says is *conditional on a
detail the source does not state* — which is closer to inventing a finding
than to refusing one.

The flag now carries this: it says the effect depends on where the tag
sits and that the commentary does not say. A reader who needs to know can
follow the citation to the paper that measured it.

**What would reopen this:** a corpus where BRENDA records tag placement, or
a value where the tagged row is the *only* source for a kcat rather than a
Ki. Neither exists today; both are checkable.

#### And the exception had to cross the boundary too

Adding `differs_for()` on the Python side created a disagreement an hour
later: the resolver's log went silent on G2 while `preparationFlags()` in
`queryResolver.ts` still read only `status`, so the API would have flagged
a modification the source says did not occur *for this quantity*. Two
renderers of one fact, disagreeing — ADR 0003 and ADR 0027's shape, in a
change made to fix a reporting defect.

The data was crossing the whole time: `model_dump()` emits
`stated_not_to_affect` and the TypeScript type simply ignored it. That is
the quieter version of the boundary bug — not a field that fails to cross,
but one that crosses and is not read.

#### And then the rule itself was implemented twice

The first repair had both sides apply the same quantity-matched rule. They
agreed — and that is still ADR 0027, which is not about disagreement but
about *two implementations*. They agree right up until one is edited.

So the judgement is made once, in the module that owns it:
`enzyme_preparation.differs_for(quantity)`. The runner emits
`warrantsWarning` and `queryResolver.ts` reads it. The inputs (`status`,
`stated_not_to_affect`) still travel, so a client can render differently —
what it must not do is decide again.

#### Which moved the risk instead of removing it

Mutation: make the runner emit `"warrantsWarning": True` unconditionally, so
golden tuple G2 warns about a modification its own commentary says did not
occur.

**Both suites stayed green.** Python tests `differs_for`, not the emission.
TypeScript mocks the runner and supplies the field itself. Both sides
tested, the join untested — the exact shape
`poolFindingsReachTheUser.test.ts` was written about.

`Tests/test_preparation_crosses_the_boundary.py` reads the emitted JSON and
asserts the decision against the rule (`emitted["warrantsWarning"] is
result.preparation.differs_for(quantity)`) rather than against a literal, so
the two cannot drift. Both mutations now fail it.

Three repairs, and the defect moved each time before it went away: computed
but not delivered → delivered to the log only → delivered twice → delivered
once and unverified at the seam. Worth recording because each repair looked
complete.

## Verification

`Tests/test_enzyme_preparation.py` (21). Every commentary string tested is
real text from this repository's fixtures, not an invented example.

Six mutations, all caught:

| Mutation | Failures |
|---|---|
| the verdict never reaches the result field (log only) | 2 |
| `recombinant` alone counted as a tag | 3 |
| `unstated` reported as `native` | 4 |
| the no-effect clause is ignored (G2 would warn spuriously) | 3 |
| the exception ignores the quantity (a Km statement excuses Ki) | 1 |
| `status` collapsed into the exception (the modification fact is lost) | 3 |

### The first version delivered it to nobody

It appended to `search_log` and stopped there. `queryResolver.ts` says
plainly:

> `provenance.flags` is what the CLI and the web UI render. The resolver's
> diagnostic `logs` are not — and for four ADRs these findings reached only
> the logs, which is the same as reaching nobody.

Mine would have been the fifth. Caught by asking the question this project
asks of everything else — *does it reach the reader?* — of my own change,
one step after writing it. The verdict is now a field, and
`test_it_travels_as_a_FIELD_not_only_a_log_line` asserts on the result
object rather than the log.

`_preparation_of()` is the single derivation point, so the field and the log
line cannot disagree — deriving it twice would be ADR 0027 exactly.

### It travels the whole way, and two guards already watched the seams

The runner emits `preparation` beside `variant`; `ScienceAgentResult`
carries it; `queryResolver.ts` turns it into a `provenance.flags` entry,
which is what the CLI and web UI render. `preparationFlag.test.ts` asserts
on the FLAGS, following `poolFindingsReachTheUser.test.ts` — written because
four ADRs' findings were computed correctly and dropped at the process
boundary while "each one tested the computation; none tested the boundary".

Three more mutations on that chain, and the results are worth separating:

| Mutation | Caught by |
|---|---|
| the flag is never pushed | `preparationFlag.test.ts` (1 failure) |
| `native`/`unstated` flagged too | **nothing, at first** — see below |
| the runner stops emitting `preparation` | `check_findings_reach_a_surface.py`, naming the field |

The third is the reassuring one. My mutation run reported it uncaught,
because I had only re-run the two test suites — the guard that executes the
runner and walks every `KineticResult` field to a reader was catching it the
whole time. It exists because ADR 0027 and ADR 0038 were this defect, and it
did its job on the first new field added since.

### The silence tests checked the vocabulary, not the silence

The second mutation made the flag builder fall back to `"an enzyme"` for
every status, so all 263 commentaries would carry a flag. **Both silence
tests passed**, because they matched `/TAGGED|IMMOBILISED|COVALENTLY/` and
the fallback contains none of those words.

They now match the sentence every preparation flag ends with. A test that
asserts an absence has to name the thing that must be absent, not three
examples of it.

## Consequences

- `KineticResult.preparation` is new and populated on both the exact-match
  and cross-species tiers.
- No selection behaviour changes; no golden value moves. 801 literature
  tests pass.
- The residue baseline's OPEN FINDING group is now read rather than merely
  reviewed. `benzyl` and `soluble` remain in the accepted tail — `benzyl`
  names a chemical group inside substrate names, and `soluble` is matched
  only in the phrase "soluble enzyme".
- The exclusion policy is open. Until it is decided, a tagged or immobilised
  value can still be returned — but never again without saying so.
