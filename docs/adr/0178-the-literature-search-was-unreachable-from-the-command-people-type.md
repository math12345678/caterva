# ADR 0178: The literature search was unreachable from the command people type.

**Status:** Accepted

**Date:** 2026-09-22

**Relates to:** ADR 0149 (`report --fixture`, the offline path that made a
literature-backed document demonstrable), ADR 0176 (the assay window, whose
pH/temperature/buffer reporting shows up in every document this produces),
ADR 0177 (the release that shipped the composer as an app without this).

## Context

Terrium's claim is that every number can be traced to where it came from.
The machinery that does it works: on 2026-09-22 a single live call returned

    Km = 0.03 mM, Homo sapiens, BRENDA reference 286469

for EC 1.1.1.27 and pyruvate, along with the fact that a second equally
well-evidenced row says 0.398 mM — a 13.3-fold disagreement between papers,
reported as disagreement rather than folded into an average.

None of that was reachable from anything a person types.

- `terrium compose "..." --subject "lactate dehydrogenase"` records the
  subject and prints *"Subject named but no search was run in this
  report."* The CLI never calls `compose_and_parameterise`, the function
  that would run the search.
- `compose_and_parameterise` itself, called directly, failed every scout
  with `ModuleNotFoundError: No module named 'fallback_logic'` — the
  resolvers live in `Tests/`, which is a flat module directory on
  `sys.path` only under pytest's `conftest.py`. **The run reported
  `converged=True` while every scout inside it had failed**, which is the
  shape of failure this project exists to refuse.
- With `Tests/` on the path it failed differently: `reaction_Km needs an EC
  number to resolve through BRENDA; none was identified`.
  `ComposedModel.parameter_requests()` builds a `ParameterRequest` per
  quantity and never fills in `ec_number`, `substrate` or `organism`, three
  fields the dataclass declares and BRENDA requires.
- The one path that did work, `scripts/report_lab.py`, reads a JSON payload
  on stdin. That is correct for the TypeScript CLI that calls it and
  unusable for a person: the first question anyone has — "what is the Km of
  this enzyme, and who measured it" — required hand-writing a JSON object
  with six keys.

So the product's central claim was true of the code and false of the
experience. The owner of the repository, reading a composed model's twelve
placeholder constants, said: *I NEED REAL DATA WITH REAL CITATIONS. THAT IS
THE WHOLE POINT.* They were right, and nothing in the shipped interface
offered it.

## Decision

**`scripts/cite.py`: the existing literature path behind flags a person can
type.**

```bash
make cite EC=1.1.1.27 SUBSTRATE=pyruvate ORGANISM="Homo sapiens"
python3 scripts/cite.py --ec 3.1.1.7 --organism "Homo sapiens" \
    --substrate acetylcholine --quantity km --quantity kcat
```

It builds `report_lab`'s payload and hands it over. It does **not**
re-implement the resolution, the ranking, the condition reporting or the
document: a second rendering path would drift from the first, and the drift
would surface in front of the reader. `--fixture` keeps the offline route
that ADR 0149 established.

Verified live against three enzymes on the day this was written: LDH
(EC 1.1.1.27) Km 0.03 mM, BRENDA ref 286469; acetylcholinesterase
(EC 3.1.1.7) Km 0.0714 mM, BRENDA ref 713996, measured at pH 7.4, 37 °C in
0.1 M MOPS, with kcat reported as **not sourced** rather than filled in;
hexokinase (EC 2.7.1.1) Km 6 mM, BRENDA ref 641068. An ambiguous name is
refused with every candidate named, because a wrong EC number is a citation
for the wrong protein rather than merely a wrong value.

## The four things, and how each was done (2026-09-22, same day)

`compose` now searches:

```bash
terrium compose "Michaelis-Menten with a competitive inhibitor" \
    --subject 1.1.1.27 --organism "Homo sapiens" --substrate pyruvate
```

returns a model whose Km and Ki are BRENDA's, each with its reference, and
whose kcat is still the motif library's placeholder and says so:

    **2 of 3 constant(s) came from the literature**, searched for
    `1.1.1.27` in Homo sapiens, substrate pyruvate.

    | `reaction_Ki`   | 0.00059 mM | literature (Homo sapiens) | BRENDA ref 739793 |
    | `reaction_Km`   | 0.03 mM    | literature (Homo sapiens) | BRENDA ref 286469 |
    | `reaction_kcat` | 100.0 1/s  | **placeholder**           | searched the kcat table and found nothing |

The four things it needed, and what each turned out to be:

**1. `Terium/checkout.py`.** One helper, `literature_module(name)`, used by
all seven sites that reach into `Tests/`. It tries the package form, the
flat form, then puts the checkout's `Tests/` on `sys.path` and retries, and
raises `LiteratureLayerUnavailable` naming the reason when there is no such
directory -- which is the honest state from a wheel or the app folder, and
a fact a caller can report rather than a traceback three frames away.

**2. `ComposedModel` carries `organism` and `substrate`**, and
`parameter_requests()` fills `ec_number`, `substrate` and `organism`. The
EC number is resolved ONCE on the model rather than per scout, which is
what `ParameterRequest.ec_number`'s own comment always said it was for. A
subject that is already an EC number is used as given; a NAME returns
`None` from `ComposedModel.ec_number` and the CLI asks the literature
layer's `ec_number_for_name`, which refuses ambiguity by naming every
candidate.

**3. `ComposedModel.with_measured()`** returns a new model with the
literature's values substituted and the measurements recorded, and
`unmeasured` subtracts them. The network is rebuilt by
`export.provenance_of`, already the one place that decides an origin, so
the numbers a report simulates and the numbers its audit trail prints
cannot disagree. **A partial result stays partial**: the strictness of
`with_resolved_values` (which refuses to substitute some and leave others)
is right for the agent path and wrong here, because partial is the normal
case -- BRENDA has a Km for acetylcholinesterase and no kcat. The report
lists the measured and the still-placeholder in one table and says of the
latter that they were "searched ... and found nothing, which is a different
fact from their not having been looked for".

**4. The CLI** gained `--organism` and `--substrate`, and
`_search_the_literature` runs the search before the analyses, so stability,
sensitivity, the time course and the verdict all read the literature's
numbers. Every failure there is a NOTE on the report rather than an
exception: a search that could not run must not cost the reader the
structure, the invariants and the dimensions, which are true regardless.
Exports search too, so an SBML file and the report beside it cannot
disagree about what was measured.

## A sixth: the rows the resolver did not pick

Wiring the search surfaced the gap it was hiding. BRENDA holds two equally
well evidenced values of Km for EC 1.1.1.27 and pyruvate in *Homo sapiens*,
0.03 mM and 0.398 mM, and the resolver picks the lower while saying the
evidence does not justify picking. `ParameterSource.candidates` carries
both. `measured_from_search` read value, unit, organism, citation,
cross-species and the three assay axes, and not that field, so the model
received one number with one citation.

A cited number presented alone reads as MORE settled than a placeholder,
not less. The first composed report to carry real data therefore made a
13-fold disagreement invisible, which is the laundering this project exists
to refuse, one layer up from the placeholder case. The lab-report path had
printed the disagreement since it was written, so the two halves of Terrium
disagreed about how honest to be.

`Measurement` now carries `alternatives` and a `disagreement` property, and
the report prints a section naming the span, the fold range and the
references. It distinguishes two cases the wording must not blur:

- **Several sources, several values.** "which one is right is a question
  about the papers."
- **One source, several rows.** BRENDA's two Ki rows for this enzyme are
  both reference 739793: one publication, two measurements, usually
  different conditions or a different inhibitor. Calling that "the
  literature disagrees" would invent a controversy, and telling the reader
  to decide which paper to believe would send them to one paper to
  adjudicate itself.

A note on the tests, which is the more general lesson. Three mutations were
run against this work: drop the rows at the conversion, call one paper two
papers, and skip the section. The second and third failed a test; **the
first, which is the actual defect, failed none** -- every test built a
`Measurement` by hand with `alternatives=` already set and so pinned the
rendering rather than the wiring. That is the same shape as the fixture
problem in the fifth item above: a test that constructs the state it means
to verify can only confirm the code's mistakes back to it. A test that goes
through `measured_from_search` was added, and the mutation fails now.

## A seventh: the conditions, and what they are for

The same shape as the sixth, one field along. `Measurement` carries
`assay_ph`, `assay_temperature_c`, `assay_buffer` and `assay_unreported`;
its own comment quotes Lisa Jeske (BRENDA curation, DSMZ) naming exactly
these as what makes a resolved value meaningless without them, and the CSV
export prints them in columns of their own. The composed report did not.

So the report now lists them per constant, and does the thing they are for:
it compares the constants that state comparable axes and says whether a
model built from them describes one experiment or several, against
`model_compatibility`'s own `PH_UNITS_SERIOUS` (1.0) and
`TEMPERATURE_C_SERIOUS` (10.0 °C, from a Q10 of 2-3). The thresholds are
read from that module rather than restated, so one judgement does not
become two that can drift apart.

Two details worth keeping:

- **A source that stated no conditions is named**, in those words. "The
  paper did not report a pH" is permanent and sends a researcher to the
  bench; "Terrium has no pH" may be a parser bug. Measured on EC 1.1.1.27:
  the Ki row states pH 7.5 and 37 °C and the Km row states nothing, so the
  two cannot be checked against each other, and the report says so instead
  of comparing what it has and calling it clean.
- **With fewer than two comparable constants nothing is claimed.** An
  earlier draft printed "the measured constants can be read as describing
  comparable experiments" over a single constant -- a check that cannot
  fail, in the position a reader takes for one that did.

## A fifth thing, found on the way

`citation_text` in `Terium/agents/adapters.py` looked for an attribute
called `reference`. `Citation` declares **`reference_id`**. The attribute
never existed, so every BRENDA citation fell through to `url` and every
artefact built from the agent stack printed

    url:https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27

which names the enzyme page, not the reference. Two measurements from two
different papers produced the identical string. Measured after the fix, the
same model's two constants cite `BRENDA ref 286469` and `BRENDA ref
739793` -- different papers, as they always were. BRENDA has no working
per-reference deep link (`Tests/citation.py` establishes this at length,
having live-checked it), so the reference id was the only thing that
identified which row a number came from, and it was the one field being
dropped.

## Consequences

- The project's central claim is now demonstrable in one command by someone
  who has never read the code.
- `make cite` joins `make demo` as a thing to show a lab. `demo` is the
  fixed offline example; `cite` is their own enzyme.
- A refusal is the product working. An ambiguous enzyme name, a substrate
  nothing has been assayed for, and a quantity no paper reports each come
  back as a named refusal rather than a number.
- The gap between `compose` and `cite` is now written down in three places
  (here, the guide, and the `cite.py` docstring) rather than being
  discovered by a reader who assumed a composed model was sourced.
