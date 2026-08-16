# ADR 0068: A source queried live is a source whose terms apply

**Status:** Accepted

**Date:** 2026-08-15

**Related:** ADR 0062 (permission is a licence), ADR 0017 (CORE full text),
`NOTICE`, `docs/LICENSING.md`, `docs/DATA_PROTECTION.md`

## What was missed

ADR 0062 audited every *package* Terrium depends on and concluded the
licensing position was clean. It audited nothing Terrium *calls*.

Three databases are queried live, from the server, on the resolution path.
None appeared in `NOTICE`. Two of them are not free-for-any-use databases,
and both say so plainly in their own terms.

**KEGG.** `resolve_substrate_from_kegg()` calls `rest.kegg.jp`. KEGG's
terms (https://www.kegg.jp/kegg/legal.html): KEGG "is not a public
database, nor is it a publicly funded database", non-academic use
"requires a commercial license", and academic users "who utilize KEGG for
providing services are requested to obtain an academic service provider
license".

**CORE.** `Tests/core_fulltext.py` calls `api.core.ac.uk/v3/search/works`.
CORE's terms (https://core.ac.uk/terms) grant commercial use of their
ODC-By *datasets* and explicitly exclude the *API*: "you need to obtain a
licence to use other CORE datasets as well as the CORE API." They then list
three conditions under which you must contact them. Terrium meets all
three — it may be monetised, it uses CORE data in a service, and that
service is literature search and discovery, CORE's own listed example.

**PubChem.** NCBI, public domain in the US. No licence condition; recorded
anyway, with the 5-requests-per-second usage policy that gets clients
blocked.

## Why the existing guards could not catch it

`check_data_source_attribution.py` (ADR 0063) is a good guard and this is
not its fault. Its docstring states the direction deliberately: everything
the `SOURCES` table claims must also be in `NOTICE`. A source *absent from
the table* is outside its reach — it verifies the entries that exist, not
that an entry exists.

Both directions are needed, and the missing one has to start from something
that cannot be forgotten. A hand-maintained list of "sources we use" is the
artefact that was already wrong.

So `Tests/test_live_data_sources_are_recorded.py` starts from **hostnames
appearing in source files**. A network call is a fact in the code; a table
entry is a fact in someone's memory.

It found CORE and PubChem on its first run. I had written it for KEGG.

## The inconsistency worth naming

`NOTICE` already recorded SABIO-RK as deliberately **not** integrated,
because its terms are non-commercial only:

> If it is ever added, it must be behind an explicit opt-in and must not be
> committed as fixtures.

That is a considered policy, correctly reasoned, for exactly this
situation. KEGG and CORE have comparable terms and were integrated anyway —
not by a decision that weighed them and disagreed, but because nobody read
them.

A policy that is applied to the source someone happened to evaluate, and
not to the sources someone happened to add, is not yet a policy.

## Decision

Record all three in `NOTICE` with their terms **quoted rather than
paraphrased**, and flag KEGG and CORE as open questions with the specific
action for each. Neither is resolved here: whether Terrium is academic or
commercial is not an engineering decision, and this repository contains an
incorporation checklist, a cap table and a fundraising tracker.

Removal is the cheap alternative for KEGG and the test says so
structurally: `resolve_substrate_from_kegg` already returns `None` on any
`httpx.HTTPError` and never guesses, so the unfiltered-BRENDA fallback
already exists. Deleting KEGG makes that the only path rather than the
error path — a quality regression on free-text enzyme queries, not a
correctness one. A test asserts that fallback still exists, so the argument
cannot quietly stop being true.

## Verification

Re-derivable as a set file — `docs/mutations/adr-0068-live-data-sources.json`:

```
python3 scripts/mutate.py --set docs/mutations/adr-0068-live-data-sources.json
```

**Re-running this table under the harness corrected it.** Three rows came
back NOT CAUGHT, and two of the three were real weaknesses in the tests:

- Deleting the KEGG section was not caught, because the scoped check
  anchored on `notice.index("KEGG")` — the first mention *anywhere* in the
  file — so renaming the heading left the slice pointing at intact text.
  It now anchors on the heading itself.
- Reframing KEGG as settled was not caught when only the sentence changed,
  because the heading still contained "UNRESOLVED" and the search covered
  the whole section. The heading was vouching for the body. They are now
  two independent checks.

The original hand-run mutations changed the heading *and* the sentence
together, so each weakness was hidden behind the other. A table nobody can
re-run is a table whose rows nobody can separate.

The third was my own set file being weaker than its description: it renamed
CORE's heading rather than removing it, and `NOT CAUGHT` was the correct
verdict on a mutation that changed nothing load-bearing. A weak mutation is
a false accusation against a working test.

Original run, seven mutations with `cmp`-verified backups:

| Mutation | Caught |
| --- | --- |
| KEGG section deleted from `NOTICE` | 2 failed |
| `NOTICE` paraphrases KEGG instead of quoting it | 1 failed |
| CORE section deleted | 1 failed |
| The KEGG error fallback removed | 1 failed |
| The file scan silently finds nothing | 1 failed |
| KEGG quietly reframed as settled | **NOT caught** |
| — after scoping the check | 1 failed |

The escape is the one worth recording. The test asserted that `NOTICE`
matched `/unresolved|open question/` **anywhere in the document**. A
mutation that renamed the KEGG heading and replaced "This is an open
question, not a settled position" with "This is fine" passed all four
tests, because the word "UNRESOLVED" still appeared — in the CORE section,
forty lines further up.

A keyword found somewhere in a 300-line file is not evidence about the
paragraph you meant. The check is now scoped to the text between the KEGG
heading and the next one.

That is the same defect as ADR 0062's vacuous set identity and the same
defect as the `undeclared_now <= KNOWN_UNLICENSED` hole: an assertion that
is satisfied by something other than the thing it was written to check.
Three times in two days, each found by mutation rather than by review.

## What this does not settle

Whether Terrium needs a KEGG licence, a CORE licence, both, or neither.
That depends on a commercial-status question the project has not answered,
and it is not a question this repository can answer by inspecting itself.
