# ADR 0171: The questions nobody collected

**Status:** Accepted

**Date:** 2026-08-23

## Context

Five labelled query sets exist. No student wrote a line of any of them.

ADR 0167 said so. ADR 0169 said so. ADR 0170 said so and then closed off the
last route that avoided the problem: vocabulary proposed by a model is fluent
invention — *"buzzing genes"*, *"gene pendulum"* — and 97% of it never
matched a real query.

What is actually unknown is narrow and important. The keyword classifier
scores between **57% and 90%** depending only on which model phrased the
questions. That spread is wider than every improvement made to it. **Which
end of it a real student experiences is not known**, and no further
generation will settle it, because every set so far was written by whoever
was also building the thing being measured.

This record does not fix the classifier. It builds the smallest thing that
would let the question be answered, and stops.

## Decision

**Record the questions people actually ask — off by default, redacted, and
labelled by a person.**

`queryLog.ts` appends one line per query: the text, what the keyword
classifier made of it, whether any keyword matched, and a date. It is wired
into `runPipeline` before resolution, so a query is recorded whether or not
the run succeeds — logging only successes would collect exactly the queries
the classifier already handles.

Three properties, each a decision rather than an implementation detail:

**Off unless switched on.** Logging happens only when `TERRIUM_QUERY_LOG`
names a file. No default path, no implicit location. A tool whose entire
argument is that it refuses to invent data should not quietly start
collecting it either.

**No identifiers, by construction.** No user, session or request id, no
address, no headers, and a date rather than a timestamp — a time of day would
let one person's session be reassembled by timing. Not because those are hard
to strip later, but because a log that never held them cannot leak them, and
a lab asked to turn this on should be able to read the file and see that.
Emails, URLs and long digit strings are redacted, and the redaction *names*
what it removed.

**Labelled by a human, and the tool refuses to help.** `labelQueryLog.ts`
presents each query with the classifier's guess and takes a verdict:
Enter accepts, a domain name corrects, `s` skips, `q` saves and quits. It
saves after every decision, so an interrupted session leaves its labels
behind, and it reloads on the next run so nobody labels the same query twice.

Labelling with an LLM was the obvious shortcut and is the one thing that
would destroy the result: the LLM classifier would score ~100% on such a set
by construction, and the keyword classifier's score would measure
agreement-with-a-model rather than correctness. ADR 0170 hit the shared-author
failure one level down; a model labeller would be the same mistake one level
down again.

**The useful number needs no labelling at all.** `make query-log` reports the
**fallback rate on real questions** — the fraction matching no keyword —
straight from the log. That is the single most useful fact nobody currently
has, and it costs a lab nothing but switching the variable on.

## Verification

End-to-end, six queries through the real capture path:

```
{"query":"Can you help me set up that biological timer circuit I read about?",
 "keywordDomain":"mm","keywordMatched":false,"date":"2026-08-23","source":"BIOL201-demo"}
...
{"query":"email me at [redacted:email] when the enzyme run finishes", ...}
```

Redaction applied, fallbacks flagged, no identifier fields present.

The summary over those six refuses to quote a rate:

```
  fallbacks: 3 of 6
  NOT QUOTING A RATE: fewer than 30 queries.
  A percentage over a handful of queries claims more than the sample supports.
```

Exit codes: **3** when logging was never switched on, and **3** for an empty
log. "Nobody has collected any" and "a rate of zero" are different facts.
(GNU make collapses every recipe failure to its own exit 2 — it prints
`Error 3`, so a human sees the distinction, and a caller needing the code
runs the script directly. Said here because the Makefile cannot preserve it.)

Mutations, `docs/mutations/adr-0171-query-log.json`, **5 caught, 0 not
caught**:

| id | mutation | caught |
|---|---|---|
| Q1 | logging turns itself on with a default path | yes |
| Q2 | redaction skipped, raw query written | yes |
| Q3 | a failed write reports success | yes |
| Q4 | the summary quotes a rate at any sample size | yes |
| Q5 | an ambiguous label prefix resolves to its first match | yes |

Q1 is the one that matters in the field: nothing errors and nothing looks
different, a deployment that never opted in simply begins writing student
text to disk.

Full api-server suite: **730 tests, all passing** — 34 of them new.

## Consequences

A teaching lab can now answer the question three records have ended on, in
two steps: set `TERRIUM_QUERY_LOG`, run `make query-log` at the end of term.
Labelling fifty of the collected queries turns the fallback rate into a real
accuracy, and that set — unlike all five existing ones — would be evidence.

**What this does not check.**

- **No real queries have been collected.** This builds the path and walks it
  with six synthetic queries. Every number in every classifier record still
  comes from sets nobody outside this repository wrote. That sentence is not
  retired by this record; it is made answerable.
- **The redaction is three crude regexes.** Emails, URLs, long digit
  strings. It will not catch a name, an address written in words, or an
  identifier in an unusual format. The documentation tells a lab to read
  what they collected before sharing it, which is a procedure, not a
  guarantee.
- **Consent is out of scope and left to the deployment.** Nothing here tells
  a student their query is being recorded. Whether that notice is needed,
  and where it belongs, is a decision for whoever turns the variable on —
  and this record does not make it for them.
- **The 30-query floor is a judgement**, not a statistical bound. Nothing
  fails if it were 20 or 50.
- **A labelled set is one person's reading.** The file says so in its own
  `_warning` field. A second labeller would disagree somewhere, and nothing
  here measures how often.
