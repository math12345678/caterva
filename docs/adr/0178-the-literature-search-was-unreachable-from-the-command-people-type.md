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

## What was NOT done, and what it would take

**`compose` still does not search.** The two halves remain separate:
`compose` gives a checked mechanism with placeholder constants, `cite`
gives measured constants with citations, and joining them is manual. The
guide says so where a reader will hit it.

Joining them needs four things, none of them speculative:

1. `ComposedModel.parameter_requests()` to fill `ec_number` (accepting an EC
   directly, or resolving a name through `Tests/enzyme_lookup.py`'s
   `ec_number_for_name`, which already refuses ambiguity), `substrate` and
   `organism`. The substrate is not on `Quantity` and would have to come
   from the user — a motif knows it needs a Km, not what it is a Km *for*.
2. `compose` and its CLI to accept `--organism` and `--substrate`, and to
   call `compose_and_parameterise` when a subject is named.
3. A decision about partial resolution. `with_resolved_values` raises
   rather than substituting some constants and leaving others at
   placeholders, which is the right default and exactly the case that
   occurs in practice: for acetylcholinesterase, Km resolves and kcat does
   not. A composed model that is half measured needs the report to carry
   the origin per constant, which the CSV export already does and the
   network does not.
4. The scouts' `Tests/` import to work outside pytest, or those resolvers
   to move into the package. This is the same limit ADR 0177 recorded for
   the app folder, and it is why `cite` needs the checkout.

Until then, **a `compose` report's numbers came from nowhere and the report
says so on every page.**

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
