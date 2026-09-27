# ADR 0149 — Using the tool as a student

**Date:** 2026-08-21
**Status:** Accepted

## Context

The owner asked for a test run of Caterva — both surfaces, CLI and web. Not
a code review. Running it.

Every finding below comes from typing the commands a student would type,
including the ones printed in the tool's own help text.

## Finding 1 — the flagship command could not run at all

The exact invocation from `report`'s help:

```
$ scientific report --ec 1.1.1.27 --organism "Homo sapiens" \
      --substrate "(S)-lactate" --s0 10mM --vmax 0.25mM/s --seed 1
✗ Could not resolve 'km': 403 Forbidden
```

That is the whole run.

`ensemble` has taken `--fixture` since it was written. `report` — the
command this project chose as its product, "one command, one document a
student can hand in" — had no path that did not require four live services
at that instant. It could not be demonstrated, and **no test exercised it
end to end**, because no test could.

Fifth consecutive instance of the same shape (ADR 0136, 0139, 0141, 0142):
parts that each work, and nothing wiring them at the seam.

### The status was pointing at the wrong host

The 403 came from **NCBI Taxonomy**, not BRENDA. `resolve_kinetic_value`
also consults UniProt, NCBI and a literature search, and the message named
the parameter and the HTTP code and not the service. A student reading
*"Could not resolve 'km': 403 Forbidden"* goes and checks whether BRENDA is
down. It was not.

## Decision — `--fixture` on `report`, and it means fully offline

A fixture run makes **no network requests at all**. The first attempt
replaced only the BRENDA fetch and still died on NCBI, which is the whole
lesson repeated one layer down: the student reaching for a saved page is
usually the student with no network.

**What that costs is recorded, not absorbed.** Organism relatedness is
graded from an NCBI lineage; without it the axis is `not_assessed` — the
honest third state, not a pass — and the document says so in its own *"What
Caterva would not do"* section:

> Caterva did not verify the organism against NCBI Taxonomy or UniProt, and
> ran no literature search: you supplied a saved BRENDA page with
> `--fixture`, so this run made no network requests at all. Organism
> relatedness is therefore NOT ASSESSED rather than matched.

A report that quietly skipped that check would be indistinguishable from one
where the organism matched.

### The EC is verified, not assumed from the filename

Nothing about a path stops somebody passing `brenda_ldh_fixture.html` while
asking about EC 2.7.1.1. The resolver would parse lactate dehydrogenase
rows, find them, and report them under hexokinase's name **with real
reference numbers attached** — a real citation for the wrong protein, which
ADR 0126 already refuses at the name-to-EC step. An offline path that
reintroduced it one step later would have bought testability with
trustworthiness.

So the page's own EC is read and compared. A page carrying no EC is refused
too: *"I could not identify it"* must not pass as *"it matches"*.

## Finding 2 — four of five models in the web dropdown never worked

Measured against `/api/simulate`:

| dropdown option | API |
|---|---|
| `michaelis-menten` | job queued |
| `competitive-inhibition` | Validation failed |
| `non-competitive-inhibition` | Validation failed |
| `product-inhibition` | Validation failed |
| `allosteric` | Validation failed |

These are real Caterva domains; the query classifier does not know these
labels. **The classifier gap is not fixed here** — the four options are
disabled and labelled, because offering a control that cannot work is the UI
form of a check that cannot fail: it is trusted.

## Finding 3 — the page threw away the only useful error

`dashboard.html` line 610:

```js
if (!response.ok) throw new Error('Simulation request failed');
```

One line after a response body naming the field, the reason, and **every
model the pipeline accepts**. Computed, delivered over the wire, and
discarded before a human could read it — the house defect, in the UI layer.
Now the API's own message is shown, with an unreadable body reported as
*"could not be read as JSON"* rather than given an invented cause.

## Finding 4 — `--out /tmp/report.md` wrote to the wrong place

`path.join(process.cwd(), destination)` glues an absolute path onto the
working directory. `path.resolve` handles both and changes nothing for a
relative one.

## Corrected in the course of this pass

The first reading of the API's `velocity: 4.1e-06` was that the web surface
repeated ADR 0141's 60,000× unit error. **That was wrong**, and correcting
it matters more than the original claim: the dashboard's field is labelled
`Vmax (μM/min)`, and the engine read μM/min. The two agree.

What is true is narrower and still worth recording: **`openapi.yaml`
declares no units anywhere**, and the response's `velocity` and `time`
carry none. The dashboard is honest because its HTML label is; a direct API
caller passing `0.25` meaning mM/s — which is what this CLI's own `--vmax`
help teaches — gets a silently different answer with nothing to catch it.
Open, and named here rather than left as a suspicion.

## Verification

- Six tests in `Tests/test_report_runs_offline.py`, no network, no skipif —
  a fixture path that needs a network to test does not work.
- **Mutation, twice, on the real tree.** Removing the EC-match check failed
  `test_one_enzymes_page_is_refused_for_another_enzymes_question`; removing
  the offline note from `also_refused` failed
  `test_the_document_says_the_organism_was_not_verified`. Both restores
  verified by `diff` against a pristine copy.
- `test_a_live_run_carries_no_offline_note` exists so a note hardcoded into
  every report cannot satisfy the test above it.
- `npx tsc --noEmit` clean.

## Consequences

- The flagship command runs, is demonstrable, and is now covered end to end.
- A document produced offline states what it did not check, in the section a
  reader checks before trusting it.
- Test count +6.
- **Open:** the query classifier's four unknown labels, and the missing unit
  contract on the HTTP API.

## Related

- [ADR 0126](0126-a-name-is-not-an-enzyme.md) — the refusal this
  fixture path had to avoid reintroducing
- [ADR 0141](0141-the-number-you-typed-became-null.md) — the units work on
  the CLI that the HTTP surface has not had
