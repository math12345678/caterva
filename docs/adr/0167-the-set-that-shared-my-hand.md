# ADR 0167: The set that shared my hand

**Status:** Accepted

**Date:** 2026-08-23

## Context

ADR 0166 measured the keyword domain classifier at **60%** and left it
unrepaired, naming the repair as a separate decision. This is that decision,
and the first thing it found was that 60% was wrong.

That record's labelled set was written *after* reading the keyword table, to
probe orderings that looked fragile. Good for finding defects. Useless as a
measure of accuracy, because the queries had absorbed the table's own
vocabulary — the author had, without intending to, written the answers into
the questions.

A second set was written first from each domain's definition and its cited
paper, without consulting the keyword list, before any tuning. On it the
committed classifier scored **17.9%**, not 60%: **21 of 28** naturally-phrased
queries matched no keyword at all and were answered `mm` by fallback.

So the baseline ADR 0166 published overstated the keyword table by roughly
forty points, and understated how much the LLM was carrying.

## Decision

**Repair the classifier, and stop trusting any set this author phrased.**

Two changes to `classifyDomainByKeyword`:

- **Specificity scoring replaces first-match-wins.** A matched term scores
  its own length and a domain's scores are summed, so a long specific phrase
  outranks a short generic one wherever each sits in the table. Table order
  survives only as the tie-break. This is what stops `"predator-prey cycles"`
  classifying as PCR on the strength of the word `"cycles"`.
- **The vocabulary widens by 120 terms**, drawn from each domain's one-line
  meaning and its cited paper — the coverage problem, which is what the
  fallbacks actually were.

`DOMAIN_MEANINGS` is lifted out of `SYSTEM_PROMPT` so the prompt is built
from it and a second consumer can read it. Verified byte-identical to the
block it replaced.

**And a third set, phrased by an LLM.** The held-out set scored **100%**
after the vocabulary widened, which is not a result but a warning: the same
person wrote the queries and the vocabulary, from the same source, so they
matched by construction. `generateProbeQueries.ts` asks an LLM for student
questions given only `DOMAIN_MEANINGS[domain]` — never the keyword table —
and commits 78 of them as a fixture. On queries this author did not phrase,
the classifier scores **79.5%**. That is the number this record stands behind.

## Verification

Ablation on the 78 LLM-authored queries, which is the only one of the three
sets that can settle anything:

| variant | correct | accuracy | fallbacks |
|---|---|---|---|
| A — first-match-wins, original vocabulary (**was committed**) | 54/78 | 69.2% | 11 |
| B — scoring, original vocabulary | 54/78 | 69.2% | 11 |
| C — scoring, wide vocabulary (**shipped**) | **62/78** | **79.5%** | 2 |
| D — first-match-wins, wide vocabulary | 59/78 | 75.6% | 3 |

**Scoring on its own bought nothing.** B is A to the query. Every point came
from vocabulary (A→D, +6.4), and scoring only became load-bearing once the
wider vocabulary gave it collisions to resolve (D→C, +3.9) — the
repressilator and two-locus confusions fall from three each to one each. The
prose justifying scoring was written before that was known; it is right about
the mechanism and was wrong about the size until the ablation ran.

**A change I made on reasoning and removed on measurement.** Keyword matching
briefly used a word-boundary regex, because plain `includes` lets `"ki"` fire
inside `"kinetics"`. The mutation harness reported that mutation **NOT
CAUGHT**, which sent me to measure rather than to write a test for it: across
all 131 labelled queries the regex changed **no classification at all**, and
left one *more* query matching nothing. Summed scoring already makes a
two-character stray hit irrelevant. It was deleted rather than tested — a
mutation nothing can catch because the code does nothing is a fact about the
code.

Mutation results, `docs/mutations/adr-0167-classifier-scoring.json`:

| id | mutation | caught |
|---|---|---|
| S1 | scoring reverts to first-match-wins | yes |
| S3 | the fallback reports itself as a genuine match | yes |

Full api-server suite: **58 files, 655 tests, all passing.** The eight tests
ADR 0166 wrote to pin the old defects failed on purpose when this landed,
each naming the defect it had pinned; they now assert the corrected routing.

## Consequences

A student with no LLM configured gets a domain right about four times in five
instead of about two in three. The trust model is untouched: this changes
which model runs, never where a number comes from.

The suite now contains a test asserting the classifier does **not** score
100% on the LLM-authored fixture. That is deliberate. A perfect score there
would mean the fixture had stopped being independent — most likely because
somebody tuned the vocabulary against it — and it should fail loudly rather
than read as success.

**What this does not check.**

- **The fixture's labels are not ground truth.** They are the domain each
  query was *commissioned* for. A model asked for a `seir` question can write
  one better answered by `sir`, and four of the sixteen misses are exactly
  that pair. Some unknown share of the 20.5% error is mislabelling, not
  misclassification, and nothing here separates them.
- **One generator, one model, one sampling.** The fixture came from
  `openai/gpt-oss-120b` at temperature 1, generated once. Another model would
  phrase differently and the score would move.
- **Still nobody's real questions.** Three sets now exist and no student
  wrote a line of any of them. That remains the largest gap between this
  number and the thing it claims to be about.
- **The two hardest confusions are untouched:** bimolecular versus
  unimolecular SSA (5 of 16 misses) and SEIR versus SIR (4 of 16). Both are
  genuine semantic nesting — one domain's description is nearly a subset of
  the other's — and no amount of keyword vocabulary separates them. That is
  an argument for the LLM path, not against it.
- **No comparison against the LLM on this fixture.** ADR 0166's +36 points
  was measured on the contaminated dev set. The LLM has not been re-scored on
  the LLM-authored queries, so the current gap between the two classifiers is
  **not known** and no claim is made about it here.
