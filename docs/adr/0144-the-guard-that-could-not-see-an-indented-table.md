# ADR 0144: The guard that could not see an indented table, and three invented citations

**Status:** Accepted, implemented

**Date:** 2026-08-20

**Context:** `scripts/check_mutation_tables_reproducible.py`,
`scripts/check_documented_citations_are_real.py`, `README.md`,
`docs/mutations/adr-013*.json`, `docs/mutations/adr-014*.json`

**Relates to:** ADR 0069 (the mutation harness and why hand-run mutations
were wrong three ways), ADR 0015 (a rule nothing executes is not enforced),
ADR 0100 (König's reply)

## Two findings, one shape

Both are checks that were trusted and could not fail.

### 1. Four ADRs published mutation tables and the guard saw none of them

`CONTRIBUTING.md` promises, in writing:

> **If your ADR presents a mutation table, it needs a set file:**
> `check_mutation_tables_reproducible.py` fails the build without one.

ADRs 0136, 0139, 0141 and 0142 each published one. The guard reported all
four as presenting no mutation results, and the build stayed green.

The matcher was anchored at the start of a line:

```python
r"^\|\s*(?:#\s*\|\s*)?mutation\s*\|"
```

Markdown indents a table whenever it sits inside a bullet, which is an
ordinary way to write one and renders identically on GitHub:

```markdown
- Six mutations, each asserted to have applied before measuring:

  | mutation | result |
  |---|---|
```

Two spaces, and the guard is blind. `^[ \t]*` fixes it, and the same anchor
bug was in `MUTATION_HEADING_RE`.

**The measurement**: ADRs presenting mutation results went 63 → 67 the
moment the anchor changed. Four of those are mine. The fifth thing it
surfaced was ADR 0013, which had been invisible since it was written.

This guard's own docstring warns against exactly this failure — *"a matcher
built from one example would have found 3 of 37 and reported the other 34 as
having no table, which is the confident false negative this project has hit
before."* It was built from nine header forms and still assumed every table
starts at column zero.

**All fifteen mutations now reproduce** under `scripts/mutate.py`, in five
set files: 5 caught for 0142, 3 for 0141's TypeScript half, 3 for its Python
half, 3 for 0139, 4 for 0136. Zero not-caught, zero indeterminate.

0141 needed two set files because a set has one `test` command and its
evidence spans jest and pytest. Chaining both into one command would make
the harness read one runner's output as the other's, which is how a verdict
becomes confident and wrong.

### 2. Every citation on the front page was invented or misattributed

Caterva's whole claim is that every number carries a real reference. The
README demonstrated it three times:

| README | what it actually was |
|---|---|
| `Citation  BRENDA ref 649716` under a lactate dehydrogenase example | an **acetylcholinesterase** reference |
| `km 0.14 mM  brenda_exact  BRENDA ref 12345` | **not a reference at all** — appears in no fixture, no corpus, nowhere |
| `vmax ... BRENDA ref 649716` | the AChE reference again |

The front page of a provenance tool, inventing provenance.

This is not cosmetic. Matthias König replied to a Caterva outreach email
that it "is not a good idea to let AI just create lies about your own
achievements." A reader who checks `ref 12345` and finds nothing has that
suspicion confirmed by the project's own README, and there is no recovering
from it with a better argument later.

Replaced with `740253` (LDH Km) and `741355` (LDH kcat), both of which occur
in the committed LDH fixtures and are therefore checkable offline by anyone.

## Decision

`check_documented_citations_are_real.py`: every `BRENDA ref NNNNNN` in
README, DESIGN and CONTRIBUTING must be an id occurring in a committed
fixture. Wired into `verify_build.py` beside the other documentation guards
— an unwired guard is the "built, correct, not connected" defect that four
consecutive ADRs have now been about.

**What it deliberately does not check**, stated because a guard whose limits
are unstated gets trusted past them: *whether the reference belongs to the
enzyme in the example.* Deciding that means inferring which fixture the
surrounding prose is about, and a check that guesses cries wolf. `649716`
was a real id in the wrong place and this guard would not have caught it —
only the human question "is that an LDH reference?" did.

So it closes the flagrant case, the number nobody could ever verify, and is
honest that the subtle one still needs a reader.

## Consequences

- Mutation-tested by restoring both defects: the original `ref 12345`
  placeholder, and a plausible-looking `ref 999999`. Both fail with the file
  and line.
- An empty fixture directory fails loudly rather than passing vacuously,
  and says the cause is the fixtures rather than the README.
- `_MIN_SURFACES` floor, as in `check_non_affiliation_notice.py`: deleting
  the checklist is the easiest way to pass a check.

## Still red, and not mine to make green

`check_mutation_tables_reproducible.py` **still exits 1**, on four ADRs:

| ADR | note |
|---|---|
| 0125, 0128, 0133 | already failing before this change |
| 0013 | newly visible, hidden by the anchor bug since it was written |

Three of those were red before I touched anything, and 0013's table was
never being checked at all. They belong to their authors and to whoever
wrote 0013; grandfathering another contributor's work into
`NOT-YET-REPRODUCIBLE.txt` on their behalf would be me deciding their
evidence does not need to reproduce.

Recorded here so the red build is legible rather than mysterious: the guard
is now correct, and it is telling the truth about work that predates it.
