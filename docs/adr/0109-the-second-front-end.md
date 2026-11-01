# ADR 0109: The second front end

**Status:** Accepted, implemented

**Date:** 2026-08-17

**Context:** `src/literature/literatureResolver.ts`, `src/cli/commandResolve.ts`,
`Tests/fixtures/offline_runner/stub_literature_runner.py`

**Follows:** [ADR 0106](0106-the-papers-nobody-was-shown.md), which fixed
this on the API path and did not look at the CLI.

## The most reassuring sentence the CLI prints was false

```
○ No km found for lactate dehydrogenase / pyruvate / Homo sapiens.
  BRENDA and PubMed were searched and returned nothing. This is an
  answer, not a failure — no value has been invented to fill the gap.
```

PubMed had not returned nothing. When BRENDA holds no value the Python
resolver searches PubMed and CORE and returns
`source: "literature_candidates"` with the papers it found — and
`literatureResolver.ts` parsed that response into
`{ found: false, quantity, logs }`, never reading `literatureCandidates` at
all. The list was discarded one function before the sentence denying it
existed.

**The line is untrue in exactly the case where the student most needs
somewhere to go next**, and it is the line written to sound trustworthy.
That is worse than the API version of this defect, which merely said
"could not resolve": this one makes a specific, checkable claim about what
was searched and what came back.

ADR 0106 fixed the API path a pass earlier. Finding the same defect here is
the standing lesson, now recorded a fourth time: **a lesson applied only
where it was first learned is a lesson half-taken.**

## Two facts, two messages

`UnresolvedKinetic` gains `candidates`, and the not-found branch renders
them with a locator each — PMID, DOI or URL, because PubMed's esummary never
supplies a DOI and CORE has no PMID, so covering one source silently strips
the provenance from every paper that came from the other.

The original sentence is kept **for the case where it is true**. A search
that found nothing and a search that found something nobody used are two
different facts, and ADR 0065's rule is that they must not share a
rendering. `--json` carries the papers too: a script driving
`resolve --json` is exactly the caller who would go and fetch them.

`parseCandidatePapers` drops entries with no title (unshowable) and entries
with no locator (uncheckable). The count printed to the student comes from
the filtered list, so it can never promise more papers than it names.

## The tests proved the wrong half of the pipe

The first test file mocked `resolveKinetic` and asserted on rendered output.
Seven cases, all green. The mutation harness answered within one run:

```
C1: the candidates are dropped at the boundary again ... NOT CAUGHT
C3: a candidate with no locator is rendered anyway    ... NOT CAUGHT
```

Both mutate `literatureResolver.ts`. **The CLI tests mock it**, so the
parsing this change actually fixed never executed. They proved the command
renders papers it is handed, and proved nothing about whether anything hands
them over — while the bug was, in both passes, precisely that nothing did.

[ADR 0027](0027-one-reliability-score-not-two.md) says this in one line: *a
test that pins a component tells you nothing about the wiring.* I wrote a
component test for a wiring defect, and only the harness noticed.

`offlineResolverEndToEnd.test.ts` already existed for this, and its own
docstring names the reason: *"Deliberately NOT a module mock… the boundary
where every bug in this path has actually been."* The stub runner gained a
`literature_candidates` fixture — including one title-less and one
locator-less entry, so a test can tell "rendered what it was given" from
"filtered first", which four good rows cannot.

| # | mutation | result |
|---|---|---|
| C1 | candidates dropped at the boundary again (the original defect) | caught |
| C2 | the false sentence printed even when papers were found | caught |
| C3 | a candidate with no locator rendered anyway | caught |

`python3 scripts/mutate.py --set docs/mutations/adr-0109-cli-candidate-papers.json`

C2 is worth its place: it prints the papers **and** the false sentence,
which is the shape a careless fix produces — a screen contradicting itself.
A test that only checked the papers appear would pass it.

## Consequences

- The CLI shows the papers, in prose and in `--json`, and stops claiming an
  empty search when the search was not empty.
- `UnresolvedKinetic.candidates` is required, not optional: one construction
  site, so absence would be a silent `undefined.length` rather than a
  compile error, and `strict` is only a safety net if the field is there to
  be checked.
- Filtering means an empty list now has two causes — nothing found, or
  nothing usable. The renderer must not restate the second as the first,
  which is the same distinction this ADR exists to draw.

## Related

- [ADR 0106](0106-the-papers-nobody-was-shown.md) — the same defect, first
  front end
- [ADR 0027](0027-one-reliability-score-not-two.md) — a component test says
  nothing about the wiring
- [ADR 0065](0065-object-object.md) — two facts must not share a rendering
